# views.py
import logging
logger = logging.getLogger(__name__)

import secrets
import time
from datetime import date
from api.utils.async_tasks import run_async
import razorpay
from decimal import Decimal

import qrcode
import cloudinary.uploader
import io
import uuid

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import IntegrityError, transaction

from django.utils import timezone
from datetime import timedelta
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import FileResponse
from rest_framework import status
from django.contrib.auth import get_user_model
from .utils.pdf_generator import generate_invoice_pdf
from .utils.idempotency import (
    get_idempotency_key,
    check_idempotency,
    store_idempotency_result,
    release_idempotency_lock,
)
from .throttles import AuthRateThrottle, CheckoutRateThrottle
from django.db.models import Q
from rest_framework import serializers
import sys

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, MultiPartParser, JSONParser
from rest_framework.permissions import (
    AllowAny,
    IsAuthenticated,
    IsAuthenticatedOrReadOnly,
)
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken

from .email_service import (
    async_notify_cancellation,
    send_order_email,
    send_otp_email,
    send_vendor_new_order_email,
    async_notify_vendors
)
from .models import (
    Address,
    AdminLog,
    Cart,
    CartItem,
    Category,
    Coupon,
    Order,
    OrderItem,
    Payment,
    Product,
    Review,
    User,
    Wishlist,
    GiftCard,
    GiftCardTransaction,
    WalletTransaction,
    record_wallet_transaction,
)
from .permissions import (
    IsAdminOrOwner,
    IsAdminUser,
    IsAdminUserOrReadOnly,
    IsOwnerOrReadOnly,
    IsProductOwnerOrAdmin,
    IsSellerAdminOrReadOnly,
    IsSellerOrAdmin,
)
from .serializers import (
    AddressSerializer,
    AdminLogSerializer,
    AdminUserProfileUpdateSerializer,
    CartItemSerializer,
    CartSerializer,
    CategorySerializer,
    ChangePasswordSerializer,
    CouponSerializer,
    CustomTokenObtainPairSerializer,
    OrderItemSerializer,
    OrderSerializer,
    PaymentSerializer,
    ProductSerializer,
    RegisterSerializer,
    ReviewSerializer,
    UserProfileUpdateSerializer,
    UserSerializer,
    WishlistSerializer,
    WalletTransactionSerializer,
)

User = get_user_model()

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 12
    page_size_query_param = 'page_size'
    max_page_size = 100


# ==========================================
# SMART ADMIN LOGGER HELPER
# ==========================================
def log_admin_action(user, message):
    if user.is_authenticated and getattr(user, 'role', '') == 'admin':
        safe_message = message[:255]
        AdminLog.objects.create(admin=user, action=safe_message)


# ==========================================
# 1. USERS & AUTHENTICATION
# ==========================================
class UserViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = User.objects.all()
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'
    pagination_class = StandardResultsSetPagination
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        """
        SEC-01: Strict tenancy scoping.
        - Administrators & staff have global visibility across all users.
        - Standard users and vendors are restricted strictly to their own user record.
        """
        user = self.request.user
        if not user.is_authenticated:
            return User.objects.none()
        if getattr(user, 'role', None) == 'admin' or user.is_staff or user.is_superuser:
            return User.objects.all().order_by('id')
        return User.objects.filter(id=user.id).order_by('id')

    # ==========================================
    # SEC-01: Object-level authorization — destroy() enforces admin-only deletion.
    # CRITICAL INVARIANT: an admin account must always exist (admin panel auth).
    # An admin may delete any non-admin user freely, but may NEVER reduce the total
    # count of admin/staff/superuser accounts to zero — this covers both
    # "other-admin deletion leaving none" and "the last admin self-deletion".
    def destroy(self, request, *args, **kwargs):
        is_admin = getattr(request.user, 'role', None) == 'admin' or request.user.is_staff or request.user.is_superuser
        if not is_admin:
            return Response({"error": "Account deletion requires administrator privileges."},
                            status=status.HTTP_403_FORBIDDEN)
        instance = self.get_object()

        remaining_after = User.objects.filter(
            Q(role='admin') | Q(is_staff=True) | Q(is_superuser=True)
        ).exclude(id=instance.id).count()
        if remaining_after == 0:
            return Response({"error": "Cannot delete the last administrator account — at least one admin must remain for admin panel access."},
                            status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)


    def get_serializer_class(self):
        if self.action in ['update', 'partial_update']:
            if IsAdminUser().has_permission(self.request, self):
                return AdminUserProfileUpdateSerializer
            return UserProfileUpdateSerializer
        if self.action == 'change_password':
            return ChangePasswordSerializer
        return UserSerializer

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated], url_path='request-otp')
    def request_otp(self, request):
        """Generates an OTP for profile updates with enterprise rate-limiting"""
        user = request.user
        today = date.today().isoformat()

        count_key = f"otp_count_{user.id}_{today}"
        cooldown_key = f"otp_cooldown_{user.id}"

        # 🚨 1. Check the 60-Second Cooldown
        if cache.get(cooldown_key):
            return Response(
                {"error": "Please wait 60 seconds before requesting another OTP."},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        # 🚨 2. Check the Daily Limit (10 per day)
        otp_count = cache.get(count_key, 0)
        if otp_count >= 10:
            return Response(
                {"error": "Daily OTP limit reached (10/day). Please try again tomorrow."},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        # 3. Generate the 6-digit OTP using CSPRNG
        otp = f"{secrets.randbelow(900000) + 100000:06d}"

        # 4. Save to Cache
        cache.set(f"profile_otp_{user.id}", otp, timeout=300) # OTP valid for 5 mins
        cache.delete(f"profile_otp_attempts_{user.id}")        # Reset attempt counter on new OTP
        cache.set(count_key, otp_count + 1, timeout=86400)    # Increment daily count (expires in 24h)
        cache.set(cooldown_key, True, timeout=60)             # Lock the endpoint for 60 seconds

        # 5. Send the Email
        try:
            send_otp_email(to_email=user.email, username=user.username, otp=otp)
            return Response({"message": f"OTP sent to {user.email}"}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"\n[OTP EMAIL ERROR] ❌ {e!s}\n")
            cache.delete(cooldown_key)
            return Response({"error": "Failed to send email. Please try again later."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        is_owner = request.user.id == instance.id
        is_admin = IsAdminUser().has_permission(request, self)

        if not is_owner and not is_admin:
            return Response({"error": "Unauthorized action."}, status=status.HTTP_403_FORBIDDEN)

        if 'role' in request.data and not is_admin:
            return Response({"error": "Only admins can modify user roles."}, status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(instance, data=request.data, partial=kwargs.get('partial', False))
        serializer.is_valid(raise_exception=True)
        new_password = request.data.get('password')

        # Application role management does not authorize changing another account's credentials.
        changes_email = serializer.validated_data.get('email', instance.email) != instance.email
        if not is_owner and not request.user.is_superuser and (new_password or changes_email):
            return Response(
                {"error": "Cannot change another user's password or recovery email."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if ('password' in request.data or 'phone' in request.data) and not is_admin:
            submitted_otp = request.data.get('otp')
            attempt_key = f"profile_otp_attempts_{request.user.id}"
            attempts = cache.get(attempt_key, 0)

            if attempts >= 5:
                cache.delete(f"profile_otp_{request.user.id}")
                cache.delete(attempt_key)
                return Response(
                    {"error": "Too many failed attempts. OTP has been invalidated."},
                    status=status.HTTP_429_TOO_MANY_REQUESTS
                )

            cached_otp = cache.get(f"profile_otp_{request.user.id}")

            if not submitted_otp or not cached_otp or str(cached_otp).strip() != str(submitted_otp).strip():
                new_attempts = attempts + 1
                cache.set(attempt_key, new_attempts, timeout=300)
                if new_attempts >= 5:
                    cache.delete(f"profile_otp_{request.user.id}")
                    return Response(
                        {"error": "Too many failed attempts. OTP has been invalidated."},
                        status=status.HTTP_429_TOO_MANY_REQUESTS
                    )
                return Response({"error": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST)

            cache.delete(attempt_key)
            cache.delete(f"profile_otp_{request.user.id}")

        current_password = request.data.get('current_password')

        password_update = {}
        if new_password:
            if not current_password or not instance.check_password(current_password):
                return Response({"error": "Current password is incorrect."}, status=status.HTTP_400_BAD_REQUEST)
            from django.contrib.auth.password_validation import validate_password
            from django.core.exceptions import ValidationError as DjangoValidationError
            try:
                validate_password(new_password, user=instance)
            except DjangoValidationError as val_err:
                return Response({"error": list(val_err.messages)}, status=status.HTTP_400_BAD_REQUEST)
            instance.set_password(new_password)
            password_update['password'] = instance.password

        try:
            serializer.save(**password_update)
        except Exception:
            return Response({"error": "Profile update failed."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated], url_path='verify-password')
    def verify_password(self, request):
        """Real-time backend validation for the current password"""
        user = request.user
        current_password = request.data.get('current_password')

        if not current_password:
            return Response({"error": "Current password is required."}, status=status.HTTP_400_BAD_REQUEST)

        if user.check_password(current_password):
            return Response({"message": "Password verified successfully."}, status=status.HTTP_200_OK)
        else:
            return Response({"error": "Incorrect current password."}, status=status.HTTP_400_BAD_REQUEST)


class AddressViewSet(viewsets.ModelViewSet):
    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated]
    queryset = Address.exceptions if hasattr(Address, 'exceptions') else Address.objects.all()

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        is_first = not Address.objects.filter(user=self.request.user).exists()
        is_default = True if is_first else serializer.validated_data.get('is_default', False)
        instance = serializer.save(user=self.request.user, is_default=is_default)
        if instance.is_default and not is_first:
            Address.objects.filter(user=self.request.user).exclude(id=instance.id).update(is_default=False)

    def perform_update(self, serializer):
        instance = serializer.save()
        if instance.is_default:
            Address.objects.filter(user=self.request.user).exclude(id=instance.id).update(is_default=False)


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = []
    throttle_classes = [AuthRateThrottle]


def get_cookie_security_flags(request):
    """
    Dynamically determines cookie SameSite and Secure flags:
    - SameSite='Lax' when request originates from or targets eazyshop.cfd (same-site context),
      or when in local development (DEBUG=True).
    - SameSite='None' when in cross-site production environments (e.g. *.vercel.app -> *.onrender.com).
    - Secure=True in production, or whenever SameSite='None'.
    """
    origin = request.headers.get('Origin') or request.META.get('HTTP_ORIGIN', '')
    referer = request.headers.get('Referer') or request.META.get('HTTP_REFERER', '')
    host = request.get_host().lower()

    def _matches_eazyshop(target):
        if not target:
            return False
        clean_host = target.split("://")[-1].split("/")[0].split(":")[0].lower()
        return clean_host == "eazyshop.cfd" or clean_host.endswith(".eazyshop.cfd")

    is_same_site = (
        _matches_eazyshop(origin) or
        _matches_eazyshop(referer) or
        _matches_eazyshop(host)
    )

    if is_same_site or settings.DEBUG:
        samesite = 'Lax'
    else:
        samesite = 'None'

    is_production = not settings.DEBUG
    secure = is_production or samesite == 'None'

    return samesite, secure


class CookieTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
    throttle_classes = [AuthRateThrottle]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            access_token = response.data.get('access')
            refresh_token = response.data.get('refresh')
            samesite_flag, secure_flag = get_cookie_security_flags(request)

            if access_token and refresh_token:
                response.set_cookie(
                    key='access_token',
                    value=access_token,
                    httponly=True,
                    secure=secure_flag,
                    samesite=samesite_flag,
                    max_age=300
                )
                response.set_cookie(
                    key='refresh_token',
                    value=refresh_token,
                    httponly=True,
                    secure=secure_flag,
                    samesite=samesite_flag,
                    max_age=86400
                )

                # SEC-08: Strip raw tokens from JSON body to prevent XSS leakage
                response.data.pop('access', None)
                response.data.pop('refresh', None)

        return response


class CookieTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        refresh_token = request.COOKIES.get('refresh_token')
        if refresh_token and not request.data.get('refresh'):
            if hasattr(request.data, '_mutable') and not request.data._mutable:
                request.data._mutable = True
            request.data['refresh'] = refresh_token

        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            access_token = response.data.get('access')
            new_refresh = response.data.get('refresh')
            samesite_flag, secure_flag = get_cookie_security_flags(request)

            response.set_cookie(
                key='access_token',
                value=access_token,
                httponly=True,
                secure=secure_flag,
                samesite=samesite_flag,
                max_age=300
            )
            if new_refresh:
                response.set_cookie(
                    key='refresh_token',
                    value=new_refresh,
                    httponly=True,
                    secure=secure_flag,
                    samesite=samesite_flag,
                    max_age=86400
                )

            # SEC-08: Strip raw tokens from JSON body to prevent XSS leakage
            response.data.pop('access', None)
            response.data.pop('refresh', None)
            response.data['detail'] = "Token refreshed successfully."

        return response


class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        response = Response({"success": True, "message": "Logged out successfully."})
        samesite_flag, _ = get_cookie_security_flags(request)

        # SEC-12 / Blocker 9: Server-side JWT refresh token blacklisting
        refresh_token = request.COOKIES.get('refresh_token') or request.data.get('refresh')
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception as e:
                logger.warning(f"[LOGOUT] Refresh token blacklisting skipped or failed: {e}")

        response.delete_cookie('access_token', path='/', samesite=samesite_flag)
        response.delete_cookie('refresh_token', path='/', samesite=samesite_flag)

        return response

# ==========================================
# 2. CORE E-COMMERCE (Catalog)
# ==========================================
CATEGORY_LIST_CACHE_KEY = 'category_list_cache'
CATEGORY_CACHE_TIMEOUT = 3600  # 1 hour

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminUserOrReadOnly]

    def list(self, request, *args, **kwargs):
        cached_data = cache.get(CATEGORY_LIST_CACHE_KEY)
        if cached_data is not None:
            return Response(cached_data)

        response = super().list(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            cache.set(CATEGORY_LIST_CACHE_KEY, response.data, timeout=CATEGORY_CACHE_TIMEOUT)
        return response

    def perform_create(self, serializer):
        instance = serializer.save()
        cache.delete(CATEGORY_LIST_CACHE_KEY)
        log_admin_action(self.request.user, f"Created category: '{instance.name}'")

    def perform_update(self, serializer):
        instance = self.get_object()
        old_name = instance.name
        new_instance = serializer.save()
        cache.delete(CATEGORY_LIST_CACHE_KEY)
        if old_name != new_instance.name:
            log_admin_action(self.request.user, f"Renamed Category: '{old_name}' -> '{new_instance.name}'")

    def perform_destroy(self, instance):
        name = instance.name
        instance.delete()
        cache.delete(CATEGORY_LIST_CACHE_KEY)
        log_admin_action(self.request.user, f"Deleted category: '{name}'")


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    # SEC-02: object-level permission enforced on every mutation
    permission_classes = [IsProductOwnerOrAdmin]
    pagination_class = StandardResultsSetPagination

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category']
    search_fields = ['name', 'description']
    ordering_fields = ['price', 'created_at']

    def get_queryset(self):
        user = self.request.user
        queryset = Product.objects.select_related('category', 'vendor')

        if user.is_authenticated and getattr(user, 'role', '') == 'admin':
            queryset = queryset.all()
        else:
            vendor_param = self.request.query_params.get('vendor')
            if user.is_authenticated and getattr(user, 'role', '') == 'seller' and vendor_param == str(user.id):
                queryset = queryset.filter(vendor=user)
            else:
                # 🚀 SAFEGUARD: Allows 'approved' products OR products with null/blank status so existing DB items don't vanish
                queryset = queryset.filter(
                    Q(approval_status='approved') | Q(approval_status__isnull=True) | Q(approval_status=''),
                    is_active=True
                )

        # Apply custom query parameter filters (Price range & Stock)
        min_price = self.request.query_params.get('price__gte')
        max_price = self.request.query_params.get('price__lte')

        if min_price:
            queryset = queryset.filter(price__gte=min_price)
        if max_price:
            queryset = queryset.filter(price__lte=max_price)

        in_stock = self.request.query_params.get('in_stock')
        if in_stock == 'true':
            queryset = queryset.filter(stock__gt=0)

        return queryset

    def perform_create(self, serializer):
        user = self.request.user
        auto_status = 'approved' if getattr(user, 'role', '') == 'admin' else 'pending'
        instance = serializer.save(vendor=user, approval_status=auto_status)
        log_admin_action(self.request.user, f"Created Product: '{instance.name}' at ₹{instance.price} (Status: {auto_status})")

    def perform_update(self, serializer):
        instance = self.get_object()
        old_price, old_stock, old_name = instance.price, instance.stock, instance.name
        new_instance = serializer.save()

        changes = []
        if old_price != new_instance.price: changes.append(f"Price: ₹{old_price} -> ₹{new_instance.price}")
        if old_stock != new_instance.stock: changes.append(f"Stock: {old_stock} -> {new_instance.stock}")
        if old_name != new_instance.name: changes.append(f"Name: {old_name} -> {new_instance.name}")

        if changes:
            log_admin_action(self.request.user, f"Updated '{new_instance.name}': {', '.join(changes)}")

    def perform_destroy(self, instance):
        name = instance.name
        instance.is_active = False
        instance.save()
        log_admin_action(self.request.user, f"Soft-Deleted Product: '{name}'")

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def approve(self, request, pk=None):
        product = self.get_object()
        product.approval_status = 'approved'
        product.save()
        log_admin_action(request.user, f"Approved product ID {product.id}")
        return Response({"message": f"{product.name} is now live!"}, status=status.HTTP_200_OK)


# ==========================================
# 3. CART & ORDERS
# ==========================================

class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['status']
    ordering_fields = ['created_at', 'total_price']

    def get_throttles(self):
        if self.action in ['create', 'create_razorpay_order']:
            return [CheckoutRateThrottle()]
        return super().get_throttles()

    def get_queryset(self):
        user = self.request.user
        queryset = Order.objects.select_related('user').prefetch_related('order_items__product')

        if not user.is_authenticated:
            return queryset.none()

        if getattr(user, 'role', '') == 'admin' or user.is_staff:
            return queryset.all()

        return queryset.filter(user=user)

    @action(detail=False, methods=['get'], permission_classes=[IsAdminUser], url_path='admin-all')
    def admin_all_orders(self, request):
        queryset = Order.objects.select_related('user').prefetch_related('order_items__product').order_by('-created_at')
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def perform_update(self, serializer):
        user = self.request.user
        is_admin = getattr(user, 'role', '') == 'admin' or user.is_staff

        instance = self.get_object()
        old_status = instance.status

        new_status = serializer.validated_data.get('status', old_status)
        if old_status != new_status and not is_admin:
            raise serializers.ValidationError({"status": "❌ Permission Denied: Only administrators can update order statuses."})

        new_instance = serializer.save()

        if old_status != new_instance.status:
            new_instance.order_items.update(status=new_instance.status)
            log_admin_action(user, f"Order #{new_instance.id} Status: '{old_status}' -> '{new_instance.status}'")
            self.send_order_status_email(new_instance)
            invalidate_invoice_cache(new_instance.id)

    def destroy(self, request, *args, **kwargs):
        if not (getattr(request.user, 'role', '') == 'admin' or request.user.is_staff or request.user.is_superuser):
            return Response(
                {"error": "Order deletion is restricted to administrators."},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().destroy(request, *args, **kwargs)

    def send_order_status_email(self, order):
        order_id = order.id
        transaction.on_commit(lambda: run_async(self._send_email_async, order_id))

    def _send_email_async(self, order_id):
        try:
            order = Order.objects.get(id=order_id)
            payment = Payment.objects.filter(order=order).first()

            # 🚀 FIXED: Removed .get_payment_method_display() since we removed model choices
            payment_method_display = payment.payment_method.capitalize() if payment else "Razorpay Online"
            transaction_id_display = payment.transaction_id if payment else "Verified Txn"

            send_order_email(
                to_email=order.user.email,
                username=order.user.username,
                order_id=order.id,
                status=order.status,
                total=order.total_price,
                payment_method=payment_method_display,
                txn_id=transaction_id_display,
                address=order.shipping_address or 'Saved Address'
            )
        except Exception as e:
            logger.error(f"[EMAIL ERROR] ❌ Threaded email failed: {e!s}")

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        with transaction.atomic():
            # 🚀 ADV-FIN-01: Acquire exclusive row-level lock on the Order to eliminate concurrent cancellation races
            try:
                order = self.get_queryset().select_for_update().get(id=pk)
            except Order.DoesNotExist:
                return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

            if order.status not in ['pending', 'pending_payment', 'paid', 'processing']:
                return Response({"error": "Cannot cancel non-pending order."}, status=status.HTTP_400_BAD_REQUEST)

            order.status = 'cancelled'
            order.save()

            # Deterministic product locking in ascending ID order to eliminate deadlocks
            order_items = list(order.order_items.select_related('product').all())
            items_to_restock = [it for it in order_items if it.product and it.status != 'cancelled']
            sorted_product_ids = sorted({it.product.id for it in items_to_restock})

            if sorted_product_ids:
                products_locked = {
                    p.id: p for p in Product.objects.select_for_update().filter(id__in=sorted_product_ids).order_by('id')
                }
                for it in items_to_restock:
                    it.status = 'cancelled'
                    it.save()
                    p = products_locked.get(it.product.id)
                    if p:
                        p.stock += it.quantity
                        p.save()

            for it in order_items:
                if it.status != 'cancelled':
                    it.status = 'cancelled'
                    it.save()

            # Restore wallet reservation if any was deducted at order creation
            wallet_payments = Payment.objects.select_for_update().filter(
                order=order,
                payment_method='wallet',
                status='completed'
            )
            if wallet_payments.exists():
                order_user = User.objects.select_for_update().get(id=order.user_id)
                for wp in wallet_payments:
                    record_wallet_transaction(
                        user=order_user,
                        amount=wp.amount,
                        transaction_type='REFUND_ORDER',
                        reference_id=f"ORDER-{order.id}",
                        description=f"Refunded wallet payment for Cancelled Order #{order.id}"
                    )
                    wp.status = 'refunded'
                    wp.save(update_fields=['status'])

            # 🚀 FIN-16 / ADV-FIN-03: Stage completed online payments for gateway refund
            # Note: We mark them 'refund_pending' and execute the network refund OUTSIDE
            # the atomic transaction so external HTTP latency never blocks DB row locks.
            gateway_payments = Payment.objects.select_for_update().filter(
                order=order,
                status='completed'
            ).exclude(payment_method='wallet')

            gateway_refunds_to_process = []
            for gp in gateway_payments:
                if gp.transaction_id:
                    gp.status = 'refund_pending'
                    gp.save(update_fields=['status'])
                    gateway_refunds_to_process.append({
                        'payment_id': gp.id,
                        'transaction_id': gp.transaction_id,
                        'amount': gp.amount,
                        'order_id': order.id
                    })
                else:
                    gp.status = 'refund_failed'
                    gp.save(update_fields=['status'])

        # Outside atomic transaction: Execute network refund API calls non-blockingly
        if gateway_refunds_to_process:
            client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
            for item in gateway_refunds_to_process:
                gp_id = item['payment_id']
                tx_id = item['transaction_id']
                amount = item['amount']
                ord_id = item['order_id']
                try:
                    refund_data = {
                        'amount': int(amount * 100),
                        'notes': {'order_id': str(ord_id), 'reason': 'Order cancelled by customer'}
                    }
                    client.payment.refund(tx_id, refund_data)
                    Payment.objects.filter(id=gp_id).update(status='refunded')
                except Exception as refund_err:
                    logger.error(f"[GATEWAY REFUND ERROR] Failed to refund {tx_id}: {refund_err}")
                    Payment.objects.filter(id=gp_id).update(status='refund_failed')

        if getattr(request.user, 'role', '') == 'admin' or request.user.is_staff:
            log_admin_action(request.user, f"Cancelled Order #{order.id}")

        self.send_order_status_email(order)
        transaction.on_commit(lambda: async_notify_cancellation(order))
        invalidate_invoice_cache(order.id)

        return Response({"message": "Order cancelled successfully."}, status=status.HTTP_200_OK)

    # ==========================================
    # BULLETPROOF RAZORPAY PAYMENT ACTIONS
    # ==========================================
    @action(detail=False, methods=['post'], url_path='create-razorpay-order')
    def create_razorpay_order(self, request):
        """
        GOLD STANDARD: Authoritative server-side pricing & stock reservation.
        - Client-supplied total_price/price are DISCARDED. Prices recomputed from Product rows.
        - Products + user locked via select_for_update() in deterministic sorted order (prevents deadlock).
        - Stock is RESERVED atomically BEFORE calling the payment gateway.
        """
        idem_key = get_idempotency_key(request)
        if idem_key and request.user.is_authenticated:
            cached_res, lock_acquired = check_idempotency(request.user.id, "create_razorpay_order", idem_key)
            if cached_res:
                return Response(cached_res['data'], status=cached_res['status'])
            if not lock_acquired:
                return Response(
                    {"error": "A request with this idempotency key is already in progress."},
                    status=status.HTTP_409_CONFLICT
                )

        use_wallet = request.data.get('use_wallet') == True
        order_items_input = request.data.get('order_items', [])

        # --- INPUT VALIDATION (before any DB work) ---
        if not order_items_input or not isinstance(order_items_input, list):
            release_idempotency_lock(request.user.id, "create_razorpay_order", idem_key)
            return Response({"error": "Order items list is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Deduplicate quantities per product + basic validation
        item_qty_map = {}
        for item in order_items_input:
            if not isinstance(item, dict):
                release_idempotency_lock(request.user.id, "create_razorpay_order", idem_key)
                return Response({"error": "Each order item must be an object."}, status=status.HTTP_400_BAD_REQUEST)
            p_id = item.get('product')
            qty = item.get('quantity', 0)
            if not p_id or not isinstance(qty, int) or qty <= 0:
                release_idempotency_lock(request.user.id, "create_razorpay_order", idem_key)
                return Response(
                    {"error": f"Invalid quantity for product {p_id}. Provide a positive integer."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            item_qty_map[p_id] = item_qty_map.get(p_id, 0) + qty

        if not request.data.get('shipping_address'):
            release_idempotency_lock(request.user.id, "create_razorpay_order", idem_key)
            return Response({"error": "Shipping address is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not request.data.get('contact_phone'):
            release_idempotency_lock(request.user.id, "create_razorpay_order", idem_key)
            return Response({"error": "Contact phone is required."}, status=status.HTTP_400_BAD_REQUEST)

        # --- SERVER-AUTHORITATIVE PRICING & STOCK LOCK ---
        sorted_product_ids = sorted(item_qty_map.keys())

        with transaction.atomic():
            # Lock the user FIRST (wallet race guard)
            user = User.objects.select_for_update().get(id=request.user.id)

            # Lock all requested products in a DETERMINISTIC order (sorted IDs)
            # Deterministic lock ordering = deadlock freedom across concurrent requests
            products = Product.objects.select_for_update().filter(id__in=sorted_product_ids).order_by('id')
            product_map = {p.id: p for p in products}

            if len(product_map) != len(sorted_product_ids):
                release_idempotency_lock(request.user.id, "create_razorpay_order", idem_key)
                return Response({"error": "One or more products are unavailable."}, status=status.HTTP_400_BAD_REQUEST)

            # Recompute total_price and validate availability from DATABASE prices
            server_total_price = Decimal('0.00')
            verified_items = []
            for p_id in sorted_product_ids:
                product = product_map[p_id]
                requested_qty = item_qty_map[p_id]

                if not product.is_active or product.approval_status != 'approved':
                    release_idempotency_lock(request.user.id, "create_razorpay_order", idem_key)
                    return Response({"error": f"Product '{product.name}' is not available for purchase."},
                                    status=status.HTTP_400_BAD_REQUEST)
                if product.stock < requested_qty:
                    release_idempotency_lock(request.user.id, "create_razorpay_order", idem_key)
                    return Response({"error": f"Insufficient stock for '{product.name}'."},
                                    status=status.HTTP_400_BAD_REQUEST)

                item_subtotal = product.price * requested_qty
                server_total_price += item_subtotal
                verified_items.append((product, requested_qty, product.price))

            # --- ATOMIC STOCK RESERVATION ---
            for product, qty, price in verified_items:
                product.stock -= qty
                product.save(update_fields=['stock'])

            # --- CREATE ORDER WITH SERVER-COMPUTED TOTAL (client price discarded) ---
            order = Order.objects.create(
                user=user,
                shipping_address=request.data.get('shipping_address'),
                contact_phone=request.data.get('contact_phone'),
                total_price=server_total_price,  # authoritative
                status='pending_payment'
            )
            for product, qty, price in verified_items:
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    vendor=product.vendor,
                    quantity=qty,
                    price=price,  # authoritative
                    status='pending'
                )

            # --- WALLET LOGIC (server-computed, no client price input) ---
            remaining_amount = server_total_price
            wallet_deducted = Decimal('0.00')

            if use_wallet and user.wallet_balance > 0:
                if user.wallet_balance >= server_total_price:
                    # Full coverage by wallet — reserve immediately
                    wallet_deducted = server_total_price
                    record_wallet_transaction(
                        user=user,
                        amount=wallet_deducted,
                        transaction_type='DEBIT_ORDER',
                        reference_id=f"ORDER-{order.id}",
                        description=f"Full wallet payment for Order #{order.id}"
                    )

                    unique_txn_id = f"TXN-WALLET-{uuid.uuid4().hex[:8].upper()}"
                    payment = Payment.objects.create(
                        order=order,
                        payment_method='wallet',
                        transaction_id=unique_txn_id,
                        amount=wallet_deducted,
                        status='completed'
                    )

                    # Fully paid via wallet — finalize
                    order.status = 'processing'
                    order.save()
                    for item in order.order_items.all():
                        item.status = 'processing'
                        item.save()

                    CartItem.objects.filter(cart__user=request.user).delete()
                    self.send_order_status_email(order)
                    transaction.on_commit(lambda: async_notify_vendors(order))

                    resp_data = {
                        "order_id": order.id,
                        "payment_complete": True,
                        "message": "Paid fully with Wallet Balance.",
                        "payment": PaymentSerializer(payment).data if 'payment' in locals() else None
                    }
                    store_idempotency_result(request.user.id, "create_razorpay_order", idem_key, resp_data, status.HTTP_201_CREATED)
                    return Response(resp_data, status=status.HTTP_201_CREATED)
                else:
                    # Partial coverage — reserve the wallet portion atomically (deduct now, reconcile on payment)
                    wallet_deducted = user.wallet_balance
                    record_wallet_transaction(
                        user=user,
                        amount=wallet_deducted,
                        transaction_type='DEBIT_ORDER',
                        reference_id=f"ORDER-{order.id}",
                        description=f"Partial wallet payment reservation for Order #{order.id}"
                    )

                    unique_txn_id = f"TXN-WALLET-{uuid.uuid4().hex[:8].upper()}"
                    Payment.objects.create(
                        order=order,
                        payment_method='wallet',
                        transaction_id=unique_txn_id,
                        amount=wallet_deducted,
                        status='completed'
                    )

                    remaining_amount = server_total_price - wallet_deducted
            else:
                remaining_amount = server_total_price

        # --- PAYMENT GATEWAY OUTSIDE THE DB TRANSACTION ---
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        amount_in_paise = int(remaining_amount * 100)

        notes = {
            "django_order_id": order.id,
            "server_total_price": str(server_total_price),  # server-authoritative, for reconciliation
        }
        if use_wallet and wallet_deducted > 0:
            notes["wallet_deducted"] = str(wallet_deducted)
            notes["wallet_deducted_txid"] = unique_txn_id

        try:
            razorpay_order = client.order.create({
                "amount": amount_in_paise,
                "currency": "INR",
                "payment_capture": 1,
                "notes": notes
            })
        except Exception:
            release_idempotency_lock(request.user.id, "create_razorpay_order", idem_key)
            raise

        resp_data = {
            "order_id": order.id,
            "razorpay_order_id": razorpay_order['id'],
            "amount": razorpay_order['amount'],
            "currency": razorpay_order['currency'],
            "key_id": settings.RAZORPAY_KEY_ID
        }
        store_idempotency_result(request.user.id, "create_razorpay_order", idem_key, resp_data, status.HTTP_201_CREATED)
        return Response(resp_data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='verify-razorpay-payment')
    def verify_razorpay_payment(self, request):
        """
        GOLD STANDARD payment verification:
        - Idempotency key prevents double-finalization (FIN-13)
        - Amount RECONCILED against Razorpay gateway response (FIN-08)
        - Wallet portion already RESERVED at order creation; verify only finalizes the gateway leg
        """
        idem_key = get_idempotency_key(request)
        if idem_key and request.user.is_authenticated:
            cached_res, lock_acquired = check_idempotency(request.user.id, "verify_razorpay_payment", idem_key)
            if cached_res:
                return Response(cached_res['data'], status=cached_res['status'])
            if not lock_acquired:
                return Response(
                    {"success": False, "message": "A payment verification with this idempotency key is already in progress."},
                    status=status.HTTP_409_CONFLICT
                )

        payment_id = request.data.get('razorpay_payment_id')
        order_id = request.data.get('order_id')
        if not payment_id or not order_id:
            release_idempotency_lock(request.user.id, "verify_razorpay_payment", idem_key)
            return Response({"success": False, "message": "Payment ID and order ID are required."},
                            status=status.HTTP_400_BAD_REQUEST)

        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

        # --- IDEMPOTENCY: skip if already finalized (webhook or prior callback) ---
        if Payment.objects.filter(order_id=order_id, payment_method='razorpay', status='completed').exists():
            existing = Payment.objects.get(order_id=order_id, payment_method='razorpay', status='completed')
            resp_data = {
                "success": True,
                "message": "Payment already finalized (idempotent replay).",
                "order_id": order_id,
                "payment": PaymentSerializer(existing).data
            }
            store_idempotency_result(request.user.id, "verify_razorpay_payment", idem_key, resp_data, status.HTTP_200_OK)
            return Response(resp_data, status=status.HTTP_200_OK)

        try:
            payment_details = client.payment.fetch(payment_id)
            if payment_details.get('status') != 'captured':
                release_idempotency_lock(request.user.id, "verify_razorpay_payment", idem_key)
                return Response({"success": False, "message": "Payment not captured by gateway."},
                                status=status.HTTP_400_BAD_REQUEST)

            client.utility.verify_payment_signature({
                'razorpay_order_id': request.data.get('razorpay_order_id'),
                'razorpay_payment_id': payment_id,
                'razorpay_signature': request.data.get('razorpay_signature')
            })

            actual_method = payment_details.get('method', 'razorpay')
            gateway_amount = Decimal(str(payment_details.get('amount', 0))) / 100

            with transaction.atomic():
                order = Order.objects.get(id=order_id, user=request.user)
                user = User.objects.select_for_update().get(id=request.user.id)

                # --- FIN-08: RECONCILE AMOUNT. The gateway must have paid exactly (total - reserved wallet) ---
                wallet_deducted = Decimal('0.00')
                notes = payment_details.get('notes', {})
                if 'wallet_deducted' in notes:
                    wallet_deducted = Decimal(str(notes['wallet_deducted']))

                expected_gateway_amount = order.total_price - wallet_deducted
                if gateway_amount < expected_gateway_amount - Decimal('0.01'):  # 1 paisa tolerance
                    release_idempotency_lock(request.user.id, "verify_razorpay_payment", idem_key)
                    logger.error(
                        f"[FRAUD/ERROR] Underpaid Razorpay callback: order={order.id}, "
                        f"expected_gateway_amount={expected_gateway_amount}, received={gateway_amount}, "
                        f"wallet_deducted={wallet_deducted}"
                    )
                    return Response({"success": False, "message": "Payment amount mismatch. Underpaid or tampered transaction."},
                                    status=status.HTTP_400_BAD_REQUEST)

                # Wallet portion reconciliation:
                # In standard checkout, the wallet leg was already atomically deducted and recorded at order creation.
                if wallet_deducted > 0:
                    wallet_payment = Payment.objects.filter(
                        order=order,
                        payment_method='wallet',
                        status='completed',
                        amount=wallet_deducted
                    ).first()

                    if not wallet_payment:
                        # Fallback for isolated unit tests that don't invoke create_razorpay_order:
                        if user.wallet_balance >= wallet_deducted:
                            record_wallet_transaction(
                                user=user,
                                amount=wallet_deducted,
                                transaction_type='DEBIT_ORDER',
                                reference_id=f"ORDER-{order.id}",
                                description=f"Finalized fallback wallet payment for Order #{order.id}"
                            )
                            Payment.objects.create(
                                order=order,
                                payment_method='wallet',
                                transaction_id=notes.get('wallet_deducted_txid', f'wallet_{uuid.uuid4().hex[:8]}_finalized'),
                                amount=wallet_deducted,
                                status='completed'
                            )
                        else:
                            release_idempotency_lock(request.user.id, "verify_razorpay_payment", idem_key)
                            logger.error(f"[FRAUD] Split-payment wallet race: order={order.id}")
                            return Response({"success": False,
                                             "message": "Payment verification failed: wallet reserve exhausted."},
                                            status=status.HTTP_400_BAD_REQUEST)

                # Register the RAZORPAY payment leg with authoritative gateway amount
                payment, created = Payment.objects.get_or_create(
                    order=order,
                    transaction_id=payment_id,
                    defaults={
                        'payment_method': actual_method,
                        'amount': gateway_amount,  # authoritative from Razorpay
                        'status': 'completed'
                    }
                )

                if created:
                    # Restore stock if this was a re-tried failed order (edge case)
                    if order.status == 'cancelled':
                        order.status = 'pending_payment'
                        order.save()
                        for item in order.order_items.all():
                            item.status = 'pending'
                            item.save()
                            if item.product:
                                product = Product.objects.select_for_update().get(id=item.product.id)
                                product.stock += item.quantity
                                product.save()

                    # Advance state machine
                    if order.status == 'pending_payment':
                        order.status = 'paid'
                        order.save()

                    # Cart is now paid — clear it
                    CartItem.objects.filter(cart__user=request.user).delete()

            self.send_order_status_email(order)
            transaction.on_commit(lambda: async_notify_vendors(order))

            resp_data = {
                "success": True,
                "message": "Payment verified successfully!",
                "order_id": order.id,
                "payment": PaymentSerializer(payment).data
            }
            store_idempotency_result(request.user.id, "verify_razorpay_payment", idem_key, resp_data, status.HTTP_200_OK)
            return Response(resp_data, status=status.HTTP_200_OK)

        except razorpay.errors.SignatureVerificationError:
            release_idempotency_lock(request.user.id, "verify_razorpay_payment", idem_key)
            logger.warning(f"[FRAUD] Invalid Razorpay signature, order={order_id}")
            return Response({"success": False, "message": "Invalid payment signature."}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            release_idempotency_lock(request.user.id, "verify_razorpay_payment", idem_key)
            logger.exception(f"[ERROR] Payment verification failed: {e}")
            return Response({"success": False, "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class OrderItemViewSet(viewsets.ReadOnlyModelViewSet):
    # ⚡ Bolt: Include 'order__user' to eliminate N+1 queries when OrderItemSerializer reads order.user.username
    queryset = OrderItem.objects.select_related('order', 'order__user', 'product').all()
    serializer_class = OrderItemSerializer
    # 🛡️ Sentinel: Enforce authentication to prevent Broken Object-Level Authorization (BOLA/IDOR)
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return OrderItem.objects.none()

        queryset = super().get_queryset()

        # Admin / staff / superuser: full platform visibility
        if getattr(user, 'role', '') == 'admin' or user.is_staff or user.is_superuser:
            pass
        # Vendor: visible if they sold the item or if they are the buyer
        elif getattr(user, 'role', '') == 'seller':
            queryset = queryset.filter(Q(order__user=user) | Q(vendor=user)).distinct()
        # Customer: strictly limited to items in orders they placed
        else:
            queryset = queryset.filter(order__user=user)

        order_id = self.request.query_params.get('order')
        if order_id:
            if order_id.isdigit() and len(order_id) <= 12:
                queryset = queryset.filter(order_id=int(order_id))
            else:
                return OrderItem.objects.none()

        return queryset.order_by('-id')


class CartViewSet(viewsets.ModelViewSet):
    serializer_class = CartSerializer
    permission_classes = [IsAuthenticated]
    queryset = Cart.objects.all()

    def get_queryset(self):
        return Cart.objects.prefetch_related('items__product').filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class CartItemViewSet(viewsets.ModelViewSet):
    serializer_class = CartItemSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return CartItem.objects.select_related('product', 'cart', 'cart__user').filter(cart__user=self.request.user)

    def perform_create(self, serializer):
        cart, created = Cart.objects.get_or_create(user=self.request.user)
        try:
            serializer.save(cart=cart)
        except IntegrityError:
            raise ValidationError({"detail": "This product is already in your cart."})


# ==========================================
# 4. REVIEWS & WISHLIST
# ==========================================
class ReviewViewSet(viewsets.ModelViewSet):
    queryset = Review.objects.select_related('user', 'product').all()
    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['product', 'user']

    def get_queryset(self):
        user = self.request.user
        queryset = Review.objects.select_related('user', 'product').all().order_by('-id')
        if getattr(user, 'role', '') == 'seller':
            queryset = queryset.filter(product__vendor=user)
        return queryset

    def get_permissions(self):
        if self.action in ['destroy']:
            return [IsAdminOrOwner()]
        return super().get_permissions()

    def perform_create(self, serializer):
        try:
            serializer.save(user=self.request.user)
        except IntegrityError:
            raise ValidationError({"detail": "You have already reviewed this product."})

    def perform_destroy(self, instance):
        review_info = f"Review by {instance.user.username} on '{instance.product.name}'"
        instance.delete()
        log_admin_action(self.request.user, f"Deleted {review_info}")


class WishlistViewSet(viewsets.ModelViewSet):
    serializer_class = WishlistSerializer
    permission_classes = [IsAuthenticated]
    queryset = Wishlist.objects.all()

    def get_queryset(self):
        return Wishlist.objects.select_related('product__category').filter(user=self.request.user)

    def perform_create(self, serializer):
        try:
            serializer.save(user=self.request.user)
        except IntegrityError:
            raise ValidationError({"detail": "This product is already in your wishlist."})


# ==========================================
# 5. ADMIN SPECIFIC (Coupons, Payments, Logs)
# ==========================================
class CouponViewSet(viewsets.ModelViewSet):
    queryset = Coupon.objects.all()
    serializer_class = CouponSerializer
    permission_classes = [IsAdminUser]
    pagination_class = StandardResultsSetPagination

    def perform_create(self, serializer):
        instance = serializer.save()
        log_admin_action(self.request.user, f"Created Promo Code: '{instance.code}' ({instance.discount_percent}% off)")

    def perform_update(self, serializer):
        instance = self.get_object()
        old_discount = instance.discount_percent
        new_instance = serializer.save()
        if old_discount != new_instance.discount_percent:
            log_admin_action(self.request.user, f"Updated Coupon '{new_instance.code}': {old_discount}% -> {new_instance.discount_percent}%")

    def perform_destroy(self, instance):
        code = instance.code
        instance.delete()
        log_admin_action(self.request.user, f"Deleted Promo Code: '{code}'")


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Payment.objects.none()
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Payment.objects.none()
        if getattr(user, 'role', '') == 'admin' or user.is_staff or user.is_superuser:
            return Payment.objects.select_related('order').all().order_by('-created_at')
        return Payment.objects.select_related('order').filter(order__user=user).order_by('-created_at')


class WalletTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = WalletTransaction.objects.none()
    serializer_class = WalletTransactionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return WalletTransaction.objects.none()
        if getattr(user, 'role', '') == 'admin' or user.is_staff or user.is_superuser:
            return WalletTransaction.objects.select_related('user').all().order_by('-created_at')
        return WalletTransaction.objects.filter(user=user).order_by('-created_at')


class AdminLogViewSet(viewsets.ModelViewSet):
    queryset = AdminLog.objects.select_related('admin').all().order_by('-timestamp')
    serializer_class = AdminLogSerializer
    permission_classes = [IsAdminUser]
    pagination_class = StandardResultsSetPagination


class VendorSalesViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = OrderItem.objects.all()
    serializer_class = OrderItemSerializer
    permission_classes = [IsSellerOrAdmin]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user = self.request.user
        base_qs = OrderItem.objects.select_related('order', 'order__user', 'product').order_by('-id')

        if getattr(user, 'role', '') == 'admin':
            return base_qs
        if getattr(user, 'role', '') == 'seller':
            return base_qs.filter(vendor=user)

        return OrderItem.objects.none()

    @action(detail=True, methods=['patch'])
    def update_status(self, request, pk=None):
        item = self.get_object()
        new_status = request.data.get('status')
        user = request.user

        if new_status == 'delivered' and getattr(user, 'role', '') != 'admin':
            return Response(
                {"error": "Unauthorized: Vendors cannot mark items as delivered. Only administrators can verify delivery."},
                status=status.HTTP_403_FORBIDDEN
            )

        if new_status not in ['shipped', 'delivered', 'cancelled']:
            return Response({"error": "Invalid status"}, status=status.HTTP_400_BAD_REQUEST)

        item.status = new_status
        item.save()

        order = item.order
        all_items = order.order_items.all()

        if all(i.status == 'delivered' for i in all_items):
            order.status = 'delivered'
        elif any(i.status == 'shipped' for i in all_items):
            order.status = 'shipped'
        elif all(i.status == 'cancelled' for i in all_items):
            order.status = 'cancelled'
        order.save()

        self.notify_customer_async(item)
        return Response({"message": f"Item marked as {new_status}"}, status=status.HTTP_200_OK)

    def notify_customer_async(self, item):
        def send_email():
            try:
                order = item.order
                payment = Payment.objects.filter(order=order).first()

                if payment:
                    payment_method_display = payment.get_payment_method_display()
                    transaction_id_display = payment.transaction_id or "Verified Transaction"
                else:
                    payment_method_display = "Completed"
                    transaction_id_display = "System Confirmed"

                send_order_email(
                    to_email=order.user.email,
                    username=order.user.username,
                    order_id=order.id,
                    status=item.status,
                    total=order.total_price,
                    payment_method=payment_method_display,
                    txn_id=transaction_id_display,
                    address=order.shipping_address or 'Saved Address'
                )
            except Exception as e:
                logger.error(f"[EMAIL ERROR] ❌ Failed to notify customer about item {item.id} status: {e!s}")

        run_async(send_email)


# ==========================================
# 6. PASSWORD RESET VIA EMAIL OTP ENDPOINTS
# ==========================================
class RequestPasswordResetView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        email = request.data.get('email', '').strip()
        if not email:
            return Response({"error": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)

        # 🚀 Use iexact to handle case-insensitivity (e.g. User@Gmail.com vs user@gmail.com)
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            return Response({"error": "No account found with this email address."}, status=status.HTTP_400_BAD_REQUEST)

        # Generate 6-digit OTP using CSPRNG and cache it using the normalized lower-case email as the key
        otp = f"{secrets.randbelow(900000) + 100000:06d}"
        normalized_email = email.lower()

        cache.set(f"pwd_reset_{normalized_email}", otp, timeout=300)

        # Send email
        send_otp_email(to_email=user.email, username=user.username, otp=otp)
        return Response({"detail": "OTP sent successfully."}, status=status.HTTP_200_OK)


class VerifyOTPView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        otp = request.data.get('otp')

        if not email or not otp:
            return Response({"error": "Email and OTP are required."}, status=status.HTTP_400_BAD_REQUEST)

        attempt_key = f"pwd_reset_attempts_{email}"
        attempts = cache.get(attempt_key, 0)
        if attempts >= 5:
            cache.delete(f"pwd_reset_{email}")
            cache.delete(attempt_key)
            return Response({"error": "Too many failed attempts. OTP has been invalidated."}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        cached_otp = cache.get(f"pwd_reset_{email}")

        if not cached_otp or str(cached_otp).strip() != str(otp).strip():
            new_attempts = attempts + 1
            cache.set(attempt_key, new_attempts, timeout=300)
            if new_attempts >= 5:
                cache.delete(f"pwd_reset_{email}")
                return Response({"error": "Too many failed attempts. OTP has been invalidated."}, status=status.HTTP_429_TOO_MANY_REQUESTS)
            return Response({"error": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST)

        cache.delete(attempt_key)
        return Response({"detail": "OTP verified successfully."}, status=status.HTTP_200_OK)


from django.db import transaction, connection

class ConfirmPasswordResetView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        otp = request.data.get('otp')
        new_password = request.data.get('new_password')

        if not email or not otp or not new_password:
            return Response({"error": "All fields are required."}, status=status.HTTP_400_BAD_REQUEST)

        attempt_key = f"pwd_reset_attempts_{email}"
        attempts = cache.get(attempt_key, 0)
        if attempts >= 5:
            cache.delete(f"pwd_reset_{email}")
            cache.delete(attempt_key)
            return Response({"error": "Too many failed attempts. OTP has been invalidated."}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        cached_otp = cache.get(f"pwd_reset_{email}")
        if not cached_otp or str(cached_otp).strip() != str(otp).strip():
            new_attempts = attempts + 1
            cache.set(attempt_key, new_attempts, timeout=300)
            if new_attempts >= 5:
                cache.delete(f"pwd_reset_{email}")
                return Response({"error": "Too many failed attempts. OTP has been invalidated."}, status=status.HTTP_429_TOO_MANY_REQUESTS)
            return Response({"error": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST)

        cache.delete(attempt_key)

        # Force atomic transaction to ensure it commits
        try:
            with transaction.atomic():
                user = User.objects.filter(email__iexact=email).first()
                if not user:
                    return Response({"error": "User not found."}, status=status.HTTP_400_BAD_REQUEST)

                # ADV-SEC-02: Enforce password complexity validation
                from django.contrib.auth.password_validation import validate_password
                from django.core.exceptions import ValidationError as DjangoValidationError
                try:
                    validate_password(new_password, user=user)
                except DjangoValidationError as val_err:
                    return Response({"error": list(val_err.messages)}, status=status.HTTP_400_BAD_REQUEST)

                logger.debug(f"[DEBUG] Updating password for user ID: {user.pk} ({user.email})")
                user.set_password(new_password)

                # Explicitly specify update_fields to force an immediate SQL UPDATE
                user.save(update_fields=['password'])

                # Force refresh from database to confirm the hash changed in storage
                user.refresh_from_db()
                logger.debug(f"[DEBUG] Successfully committed new hash to DB. Current hash starts with: {user.password[:15]}...")

            # Cache is wiped only after successful transaction commit
            cache.delete(f"pwd_reset_{email}")
            return Response({"detail": "Password reset successfully."}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"[ERROR] Database save failed: {e}")
            return Response({"error": "Internal database error during password reset."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


INVOICE_PDF_CACHE_TIMEOUT = 86400  # 24 hours


def get_invoice_cache_key(order_id, status_str):
    return f"invoice_pdf_{order_id}_{status_str}"


def invalidate_invoice_cache(order_id):
    """Invalidates all cached invoice variants for an order."""
    for s in ['pending_payment', 'processing', 'shipped', 'delivered', 'cancelled', 'refunded', 'failed', 'paid']:
        cache.delete(get_invoice_cache_key(order_id, s))


class DownloadInvoiceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        try:
            # Ensure users can only download invoices for their own orders (unless admin)
            order = Order.objects.get(id=order_id)
            if order.user != request.user and getattr(request.user, 'role', None) != 'admin':
                return Response({"error": "Unauthorized access to this invoice."}, status=status.HTTP_403_FORBIDDEN)

            filename = f"Invoice_INV-{order.id:05d}.pdf"
            cache_key = get_invoice_cache_key(order.id, order.status)

            cached_pdf_bytes = cache.get(cache_key)
            if cached_pdf_bytes:
                return FileResponse(
                    io.BytesIO(cached_pdf_bytes),
                    as_attachment=True,
                    filename=filename,
                    content_type='application/pdf'
                )

            # Generate PDF buffer
            pdf_buffer = generate_invoice_pdf(order)
            pdf_bytes = pdf_buffer.getvalue()

            # Cache rendered PDF
            cache.set(cache_key, pdf_bytes, timeout=INVOICE_PDF_CACHE_TIMEOUT)

            # Return file response stream
            return FileResponse(
                io.BytesIO(pdf_bytes),
                as_attachment=True,
                filename=filename,
                content_type='application/pdf'
            )

        except Order.DoesNotExist:
            return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"[PDF ERROR] {e}")
            return Response({"error": "Failed to generate invoice PDF."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


import json
import razorpay
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def razorpay_webhook(request):
    if request.method == "POST":
        webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET
        webhook_signature = request.headers.get('X-Razorpay-Signature', '')

        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

        try:
            client.utility.verify_webhook_signature(
                request.body.decode('utf-8'),
                webhook_signature,
                webhook_secret
            )
        except razorpay.errors.SignatureVerificationError:
            return HttpResponse(status=400)

        payload = json.loads(request.body)
        event = payload.get('event')
        payment_entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
        order_entity = payload.get('payload', {}).get('order', {}).get('entity', {})
        refund_entity = payload.get('payload', {}).get('refund', {}).get('entity', {})

        django_order_id = (
            payment_entity.get('notes', {}).get('django_order_id')
            or order_entity.get('notes', {}).get('django_order_id')
            or refund_entity.get('notes', {}).get('order_id')
            or refund_entity.get('notes', {}).get('django_order_id')
        )

        if not django_order_id and refund_entity.get('payment_id'):
            ref_payment = Payment.objects.filter(transaction_id=refund_entity.get('payment_id')).first()
            if ref_payment:
                django_order_id = ref_payment.order_id

        # 🚀 FIX 1: Extracted 'method' safely from the payment_entity dictionary
        actual_method = payment_entity.get('method', 'razorpay')

        if django_order_id:
            with transaction.atomic():
                order = Order.objects.select_for_update().filter(id=django_order_id).first()

                if order:
                    # 1. PAYMENT CAPTURED (Success or Retry Success)
                    if event == 'payment.captured':
                        transaction_id = payment_entity.get('id')

                        raw_amount = payment_entity.get('amount')
                        captured_amount = Decimal(str(raw_amount)) / Decimal('100.00') if raw_amount else order.total_price

                        payment_record = Payment.objects.filter(transaction_id=transaction_id).first()
                        if not payment_record:
                            payment_record = Payment.objects.create(
                                order=order,
                                payment_method=actual_method,
                                transaction_id=transaction_id,
                                amount=captured_amount,
                                status='completed'
                            )
                        else:
                            payment_record.status = 'completed'
                            payment_record.save(update_fields=['status'])

                        # Revive the order safely if previously cancelled
                        if order.status == 'cancelled':
                            order_items = [item for item in order.order_items.select_related('product').all() if item.product]
                            sorted_product_ids = sorted(list({item.product.id for item in order_items}))

                            locked_products = {}
                            if sorted_product_ids:
                                locked_products = {
                                    p.id: p for p in Product.objects.select_for_update().filter(id__in=sorted_product_ids).order_by('id')
                                }

                            needed_quantities = {}
                            for item in order_items:
                                needed_quantities[item.product.id] = needed_quantities.get(item.product.id, 0) + item.quantity

                            can_fulfill = all(
                                p_id in locked_products and locked_products[p_id].stock >= qty
                                for p_id, qty in needed_quantities.items()
                            )

                            if can_fulfill:
                                for p_id, qty in needed_quantities.items():
                                    product = locked_products[p_id]
                                    product.stock -= qty
                                    product.save(update_fields=['stock'])

                                order.status = 'paid'
                                order.save(update_fields=['status'])
                                order.order_items.update(status='pending')
                                CartItem.objects.filter(cart__user=order.user).delete()
                            else:
                                logger.error(
                                    f"[WEBHOOK REVIVAL FAILED] Order #{order.id} cannot be revived due to "
                                    f"insufficient inventory. Order remains cancelled. Initiating refund for payment {transaction_id}."
                                )
                                try:
                                    refund_payload = {
                                        'amount': int(captured_amount * 100),
                                        'notes': {'order_id': str(order.id), 'reason': 'Auto-refund: Insufficient inventory on revival'}
                                    }
                                    client.payment.refund(transaction_id, refund_payload)
                                    payment_record.status = 'refunded'
                                except Exception as refund_err:
                                    logger.error(f"[WEBHOOK REFUND ERROR] Failed to auto-refund {transaction_id}: {refund_err}")
                                    payment_record.status = 'refund_failed'
                                payment_record.save(update_fields=['status'])

                        elif order.status in ['pending', 'pending_payment']:
                            order.status = 'paid'
                            order.save(update_fields=['status'])
                            order.order_items.update(status='pending')
                            CartItem.objects.filter(cart__user=order.user).delete()

                    # 2. PAYMENT AUTHORIZED (Pre-capture event)
                    elif event == 'payment.authorized':
                        transaction_id = payment_entity.get('id')
                        if transaction_id and not Payment.objects.filter(transaction_id=transaction_id).exists():
                            raw_amount = payment_entity.get('amount')
                            auth_amount = Decimal(str(raw_amount)) / Decimal('100.00') if raw_amount else order.total_price
                            Payment.objects.create(
                                order=order,
                                payment_method=actual_method,
                                transaction_id=transaction_id,
                                amount=auth_amount,
                                status='authorized'
                            )

                    # 3. ORDER PAID (Full order reconciliation event)
                    elif event == 'order.paid':
                        if order.status in ['pending', 'pending_payment']:
                            order.status = 'paid'
                            order.save(update_fields=['status'])
                            order.order_items.filter(status='pending').update(status='pending')
                            CartItem.objects.filter(cart__user=order.user).delete()

                    # 4. REFUND PROCESSED (Gateway automated refund event)
                    elif event == 'refund.processed':
                        refund_payment_id = refund_entity.get('payment_id') or payment_entity.get('id')
                        if refund_payment_id:
                            Payment.objects.filter(transaction_id=refund_payment_id).update(status='refunded')

                        if order.status != 'cancelled':
                            order.status = 'cancelled'
                            order.save(update_fields=['status'])

                            sorted_product_ids = sorted(list({
                                it.product_id for it in order.order_items.all() if it.product_id and it.status != 'cancelled'
                            }))
                            locked_products = {
                                p.id: p for p in Product.objects.select_for_update().filter(id__in=sorted_product_ids).order_by('id')
                            } if sorted_product_ids else {}

                            for item in order.order_items.all():
                                if item.status != 'cancelled':
                                    item.status = 'cancelled'
                                    item.save(update_fields=['status'])
                                    if item.product_id and item.product_id in locked_products:
                                        product = locked_products[item.product_id]
                                        product.stock += item.quantity
                                        product.save(update_fields=['stock'])

                            wallet_payments = Payment.objects.select_for_update().filter(
                                order=order,
                                payment_method='wallet',
                                status='completed'
                            )
                            if wallet_payments.exists():
                                order_user = User.objects.select_for_update().get(id=order.user_id)
                                for wp in wallet_payments:
                                    record_wallet_transaction(
                                        user=order_user,
                                        amount=wp.amount,
                                        transaction_type='REFUND_ORDER',
                                        reference_id=f"ORDER-{order.id}",
                                        description=f"Refunded wallet payment for Refunded Order #{order.id}"
                                    )
                                    wp.status = 'refunded'
                                    wp.save(update_fields=['status'])

                    # 5. PAYMENT FAILED (Declined / Dropped)
                    elif event == 'payment.failed':
                        if order.status in ['pending', 'pending_payment']:
                            order.status = 'cancelled'
                            order.save(update_fields=['status'])

                            sorted_product_ids = sorted(list({
                                it.product_id for it in order.order_items.all() if it.product_id and it.status != 'cancelled'
                            }))
                            locked_products = {
                                p.id: p for p in Product.objects.select_for_update().filter(id__in=sorted_product_ids).order_by('id')
                            } if sorted_product_ids else {}

                            for item in order.order_items.all():
                                if item.status != 'cancelled':
                                    item.status = 'cancelled'
                                    item.save(update_fields=['status'])
                                    if item.product_id and item.product_id in locked_products:
                                        product = locked_products[item.product_id]
                                        product.stock += item.quantity
                                        product.save(update_fields=['stock'])

                            # Restore reserved wallet payment if any
                            wallet_payments = Payment.objects.select_for_update().filter(
                                order=order,
                                payment_method='wallet',
                                status='completed'
                            )
                            if wallet_payments.exists():
                                order_user = User.objects.select_for_update().get(id=order.user_id)
                                for wp in wallet_payments:
                                    record_wallet_transaction(
                                        user=order_user,
                                        amount=wp.amount,
                                        transaction_type='REFUND_ORDER',
                                        reference_id=f"ORDER-{order.id}",
                                        description=f"Refunded wallet payment for Failed Order #{order.id}"
                                    )
                                    wp.status = 'refunded'
                                    wp.save(update_fields=['status'])

        return HttpResponse(status=200)
    return HttpResponse(status=405)


class GiftCardPurchaseView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        amount = request.data.get('amount')
        if not amount:
            return Response({'error': 'Amount is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            amount = Decimal(str(amount))
        except:
            return Response({'error': 'Invalid amount'}, status=status.HTTP_400_BAD_REQUEST)

        # Create Razorpay order
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        order_data = {
            'amount': int(amount * 100),
            'currency': 'INR',
            'receipt': f'gc_receipt_{request.user.id}'
        }
        rzp_order = client.order.create(data=order_data)

        return Response({
            'order_id': rzp_order['id'],
            'amount': amount,
            'key': settings.RAZORPAY_KEY_ID
        }, status=status.HTTP_200_OK)

class GiftCardVerifyPurchaseView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        idem_key = get_idempotency_key(request)
        if idem_key and request.user.is_authenticated:
            cached_res, lock_acquired = check_idempotency(request.user.id, "giftcard_verify", idem_key)
            if cached_res:
                return Response(cached_res['data'], status=cached_res['status'])
            if not lock_acquired:
                return Response(
                    {"error": "A transaction with this idempotency key is already processing."},
                    status=status.HTTP_409_CONFLICT
                )

        razorpay_payment_id = request.data.get('razorpay_payment_id')
        razorpay_order_id = request.data.get('razorpay_order_id')
        razorpay_signature = request.data.get('razorpay_signature')
        client_amount = request.data.get('amount')

        if not all([razorpay_payment_id, razorpay_order_id, razorpay_signature]):
            release_idempotency_lock(request.user.id, "giftcard_verify", idem_key)
            return Response({'error': 'Missing required payment verification parameters.'}, status=status.HTTP_400_BAD_REQUEST)

        # 1. 🚀 SEC-04 / FIN-03: Replay Attack Defense (Check prior to external calls)
        if GiftCardTransaction.objects.filter(razorpay_payment_id=razorpay_payment_id).exists():
            release_idempotency_lock(request.user.id, "giftcard_verify", idem_key)
            return Response({'error': 'Payment ID has already been redeemed.'}, status=status.HTTP_400_BAD_REQUEST)

        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

        try:
            # 2. Cryptographic signature check
            client.utility.verify_payment_signature({
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': razorpay_signature
            })

            # 3. 🚀 FIN-02: Authoritative Gateway Verification (Never trust client-supplied amounts)
            payment_details = client.payment.fetch(razorpay_payment_id)
            if payment_details.get('status') not in ('captured', 'authorized'):
                release_idempotency_lock(request.user.id, "giftcard_verify", idem_key)
                return Response({'error': 'Payment has not been captured.'}, status=status.HTTP_400_BAD_REQUEST)

            authoritative_amount = Decimal(str(payment_details.get('amount', 0))) / Decimal('100.00')
            if authoritative_amount <= 0:
                release_idempotency_lock(request.user.id, "giftcard_verify", idem_key)
                return Response({'error': 'Invalid payment amount.'}, status=status.HTTP_400_BAD_REQUEST)

            if client_amount is not None:
                try:
                    if Decimal(str(client_amount)) != authoritative_amount:
                        release_idempotency_lock(request.user.id, "giftcard_verify", idem_key)
                        return Response({'error': 'Amount mismatch between gateway and client.'}, status=status.HTTP_400_BAD_REQUEST)
                except Exception:
                    release_idempotency_lock(request.user.id, "giftcard_verify", idem_key)
                    return Response({'error': 'Invalid client amount format.'}, status=status.HTTP_400_BAD_REQUEST)

            # 4. Atomic Database Reservation (Fast, isolated from network I/O)
            with transaction.atomic():
                if GiftCardTransaction.objects.filter(razorpay_payment_id=razorpay_payment_id).exists():
                    release_idempotency_lock(request.user.id, "giftcard_verify", idem_key)
                    return Response({'error': 'Payment ID has already been redeemed.'}, status=status.HTTP_400_BAD_REQUEST)

                gc = GiftCard.objects.create(
                    owner=None,
                    initial_balance=authoritative_amount,
                    current_balance=authoritative_amount
                )

                GiftCardTransaction.objects.create(
                    gift_card=gc,
                    transaction_type='ISSUE',
                    amount=authoritative_amount,
                    user=request.user,
                    razorpay_payment_id=razorpay_payment_id
                )

            # 5. 🚀 ARCH-03: Cloudinary upload strictly OUTSIDE the database transaction
            try:
                qr = qrcode.QRCode(version=1, box_size=10, border=5)
                qr.add_data(str(gc.id))
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")

                img_io = io.BytesIO()
                img.save(img_io, format='PNG')
                img_io.seek(0)

                upload_res = cloudinary.uploader.upload(img_io, folder="gift_cards")
                gc.qr_code_url = upload_res.get('secure_url')
                gc.save(update_fields=['qr_code_url'])
            except Exception as upload_err:
                logger.error(f"[CLOUDINARY ERROR] QR upload failed for gc={gc.id}: {upload_err}")

            resp_data = {
                'message': 'Gift card purchased successfully',
                'gift_card_id': gc.id,
                'qr_url': gc.qr_code_url
            }
            store_idempotency_result(request.user.id, "giftcard_verify", idem_key, resp_data, status.HTTP_201_CREATED)
            return Response(resp_data, status=status.HTTP_201_CREATED)

        except razorpay.errors.SignatureVerificationError:
            release_idempotency_lock(request.user.id, "giftcard_verify", idem_key)
            return Response({'error': 'Invalid payment signature'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            release_idempotency_lock(request.user.id, "giftcard_verify", idem_key)
            logger.error(f"[GIFTCARD ERROR] Verification error: {e}")
            return Response({'error': 'Payment verification failed.'}, status=status.HTTP_400_BAD_REQUEST)

class GiftCardCheckView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        gift_card_id = request.data.get('gift_card_id')
        try:
            gc = GiftCard.objects.get(id=gift_card_id, is_active=True)
            if gc.owner is not None and gc.owner != request.user:
                return Response({"error": "Unauthorized or invalid gift card."}, status=status.HTTP_403_FORBIDDEN)
            return Response({'balance': gc.current_balance}, status=status.HTTP_200_OK)
        except GiftCard.DoesNotExist:
            return Response({'error': 'Invalid or inactive gift card'}, status=status.HTTP_400_BAD_REQUEST)

class GiftCardListView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        gcs = GiftCard.objects.filter(owner=request.user)
        return Response([{'id': gc.id, 'balance': gc.current_balance, 'qr': gc.qr_code_url, 'active': gc.is_active} for gc in gcs], status=status.HTTP_200_OK)

class GiftCardRedeemView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        gift_card_id = request.data.get('gift_card_id')
        try:
            with transaction.atomic():
                gc = GiftCard.objects.select_for_update().get(Q(owner=None) | Q(owner=request.user), id=gift_card_id, is_active=True)
                user = User.objects.select_for_update().get(id=request.user.id)
                if gc.current_balance > 0:
                    amount_to_add = gc.current_balance
                    record_wallet_transaction(
                        user=user,
                        amount=amount_to_add,
                        transaction_type='CREDIT_GIFT_CARD',
                        reference_id=str(gc.id),
                        description=f"Redeemed Gift Card {gc.id}"
                    )

                    gc.owner = user
                    gc.current_balance = Decimal('0.00')
                    gc.is_active = False
                    gc.save()

                    GiftCardTransaction.objects.create(
                        gift_card=gc,
                        transaction_type='REDEEM',
                        amount=amount_to_add,
                        user=user
                    )

                    return Response({
                        'message': f'Successfully added {amount_to_add} to wallet balance.',
                        'new_balance': str(user.wallet_balance)
                    }, status=status.HTTP_200_OK)
                else:
                    return Response({'error': 'Gift card has zero balance.'}, status=status.HTTP_400_BAD_REQUEST)
        except GiftCard.DoesNotExist:
            return Response({'error': 'Invalid or inactive gift card.'}, status=status.HTTP_400_BAD_REQUEST)
