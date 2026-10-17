# views.py
import logging
logger = logging.getLogger(__name__)

import random
import threading
import time
from datetime import date
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
from django.db.models import Q
from rest_framework import serializers
import sys

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import (
    AllowAny,
    IsAuthenticated,
    IsAuthenticatedOrReadOnly,
)
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

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
)
from .permissions import (
    IsAdminOrOwner,
    IsAdminUser,
    IsOwnerOrReadOnly,
    IsSellerAdminOrReadOnly,
    IsSellerOrAdmin,
)
from .serializers import (
    AddressSerializer,
    AdminLogSerializer,
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
class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'
    pagination_class = StandardResultsSetPagination
    parser_classes = [MultiPartParser, FormParser]


    def get_serializer_class(self):
        if self.action in ['update', 'partial_update']:
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

        # 3. Generate the 6-digit OTP
        otp = str(random.randint(100000, 999999))

        # 4. Save to Cache
        cache.set(f"profile_otp_{user.id}", otp, timeout=300) # OTP valid for 5 mins
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
        is_admin = getattr(request.user, 'role', None) == 'admin'

        if not is_owner and not is_admin:
            return Response({"error": "Unauthorized action."}, status=status.HTTP_403_FORBIDDEN)

        if 'role' in request.data and not is_admin:
            return Response({"error": "Only admins can modify user roles."}, status=status.HTTP_403_FORBIDDEN)

        if ('password' in request.data or 'phone' in request.data) and not is_admin:
            submitted_otp = request.data.get('otp')
            cached_otp = cache.get(f"profile_otp_{request.user.id}")

            if not submitted_otp or not cached_otp or str(cached_otp).strip() != str(submitted_otp).strip():
                return Response({"error": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST)
            cache.delete(f"profile_otp_{request.user.id}")

        new_password = request.data.get('password')
        current_password = request.data.get('current_password')

        if new_password:
            if not current_password or not instance.check_password(current_password):
                return Response({"error": "Current password is incorrect."}, status=status.HTTP_400_BAD_REQUEST)
            instance.set_password(new_password)
            instance.save()

        try:
            return super().update(request, *args, **kwargs)
        except Exception:
            return Response({"error": "Profile update failed."}, status=status.HTTP_400_BAD_REQUEST)

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


class CookieTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            access_token = response.data.get('access')
            refresh_token = response.data.get('refresh')
            # 🚀 DYNAMIC SECURITY: Uses Lax/HTTP locally, and None/HTTPS in production
            is_production = not settings.DEBUG

            if access_token and refresh_token:
                response.set_cookie(
                    key='access_token',
                    value=access_token,
                    httponly=True,
                    secure=True,        # 🚀 FORCES HTTPS TRANSMISSION
                    samesite='None',    # 🚀 ALLOWS CROSS-DOMAIN COOKIES
                    max_age=300
                )
                response.set_cookie(
                    key='refresh_token',
                    value=refresh_token,
                    httponly=True,
                    secure=True,        # 🚀 FORCES HTTPS TRANSMISSION
                    samesite='None',    # 🚀 ALLOWS CROSS-DOMAIN COOKIES
                    max_age=86400
                )
                del response.data['access']
                del response.data['refresh']

        return response


class CookieTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        refresh_token = request.COOKIES.get('refresh_token')
        if refresh_token:
            request.data['refresh'] = refresh_token

        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            access_token = response.data.get('access')

            # 🚀 DYNAMIC SECURITY: Uses Lax/HTTP locally, and None/HTTPS in production
            is_production = not settings.DEBUG

            response.set_cookie(
                key='access_token',
                value=access_token,
                httponly=True,
                secure=is_production,
                samesite='None' if is_production else 'Lax',
                max_age=300
            )
            del response.data['access']

        return response


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        response = Response({"success": True, "message": "Logged out successfully."})

        # 🚀 DYNAMIC SECURITY: The deletion request must perfectly match the creation flags
        is_production = not settings.DEBUG
        samesite_flag = 'None' if is_production else 'Lax'

        response.delete_cookie('access_token', path='/', samesite=samesite_flag)
        response.delete_cookie('refresh_token', path='/', samesite=samesite_flag)

        return response

# ==========================================
# 2. CORE E-COMMERCE (Catalog)
# ==========================================
class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]

    def perform_create(self, serializer):
        instance = serializer.save()
        log_admin_action(self.request.user, f"Created category: '{instance.name}'")

    def perform_update(self, serializer):
        instance = self.get_object()
        old_name = instance.name
        new_instance = serializer.save()
        if old_name != new_instance.name:
            log_admin_action(self.request.user, f"Renamed Category: '{old_name}' -> '{new_instance.name}'")

    def perform_destroy(self, instance):
        name = instance.name
        instance.delete()
        log_admin_action(self.request.user, f"Deleted category: '{name}'")


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [IsSellerAdminOrReadOnly]
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

    def send_order_status_email(self, order):
        threading.Thread(target=self._send_email_async, args=(order.id,)).start()

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
        order = self.get_object()

        if order.status != 'pending':
            return Response({"error": "Cannot cancel non-pending order."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            order.status = 'cancelled'
            order.save()

            for item in order.order_items.all():
                item.status = 'cancelled'
                item.save()

                if item.product:
                    product = Product.objects.select_for_update().get(id=item.product.id)
                    product.stock += item.quantity
                    product.save()

        if getattr(request.user, 'role', '') == 'admin' or request.user.is_staff:
            log_admin_action(request.user, f"Cancelled Order #{order.id}")

        self.send_order_status_email(order)
        async_notify_cancellation(order)

        return Response({"message": "Order cancelled successfully."}, status=status.HTTP_200_OK)

    # ==========================================
    # BULLETPROOF RAZORPAY PAYMENT ACTIONS
    # ==========================================
    @action(detail=False, methods=['post'], url_path='create-razorpay-order')
    def create_razorpay_order(self, request):
        use_wallet = request.data.get('use_wallet') == True

        with transaction.atomic():
            order = Order.objects.create(
                user=request.user,
                shipping_address=request.data.get('shipping_address'),
                contact_phone=request.data.get('contact_phone'),
                total_price=request.data.get('total_price'),
                status='pending'
            )

            for item_data in request.data.get('order_items', []):
                product = Product.objects.get(id=item_data['product'])
                OrderItem.objects.create(
                                    order=order,
                                    product=product,
                                    vendor=product.vendor,
                                    quantity=item_data['quantity'],
                                    price=item_data['price']
                                )

            total_price = Decimal(str(order.total_price))
            remaining_amount = total_price
            wallet_deducted = Decimal('0.00')

            # We need a select_for_update to lock the user row to prevent race conditions on wallet balance
            user = User.objects.select_for_update().get(id=request.user.id)

            if use_wallet and user.wallet_balance > 0:
                if user.wallet_balance >= total_price:
                    # Full coverage by wallet
                    wallet_deducted = total_price
                    user.wallet_balance -= total_price
                    user.save()

                    order.status = 'processing'
                    order.save()

                    unique_txn_id = f"TXN-WALLET-{uuid.uuid4().hex[:8].upper()}"

                    payment = Payment.objects.create(
                        order=order,
                        payment_method='wallet',
                        transaction_id=unique_txn_id,
                        amount=total_price,
                        status='completed'
                    )

                    for item in order.order_items.all():
                        item.product.stock -= item.quantity
                        item.product.save()
                        item.status = 'processing'
                        item.save()

                    CartItem.objects.filter(cart__user=request.user).delete()
                    self.send_order_status_email(order)

                    return Response({
                        "order_id": order.id,
                        "payment_complete": True,
                        "message": "Paid fully with Wallet Balance.",
                        "payment": PaymentSerializer(payment).data
                    }, status=status.HTTP_201_CREATED)
                else:
                    # Partial coverage
                    wallet_deducted = user.wallet_balance
                    remaining_amount = total_price - wallet_deducted
                    # Don't deduct from user here yet! We deduct in verify_razorpay_payment or we can deduct here.
                    # It's safer to just pass it in notes and let verify do it, or lock here.
                    # Actually, we shouldn't deduct until payment succeeds.

        # 2. Initialize Razorpay and hide our Django Order ID inside the session notes
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        amount_in_paise = int(remaining_amount * 100)

        notes = {
            "django_order_id": order.id
        }
        if use_wallet and wallet_deducted > 0:
            notes["wallet_deducted"] = str(wallet_deducted)

        razorpay_order = client.order.create({
            "amount": amount_in_paise,
            "currency": "INR",
            "payment_capture": 1,
            "notes": notes
        })

        return Response({
            "order_id": order.id,
            "razorpay_order_id": razorpay_order['id'],
            "amount": razorpay_order['amount'],
            "currency": razorpay_order['currency'],
            "key_id": settings.RAZORPAY_KEY_ID
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='verify-razorpay-payment')
    def verify_razorpay_payment(self, request):
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

        razorpay_order_id = request.data.get('razorpay_order_id')
        razorpay_payment_id = request.data.get('razorpay_payment_id')
        razorpay_signature = request.data.get('razorpay_signature')
        django_order_id = request.data.get('order_id')

        # Here fetching payment_details is correct because we are calling the API
        payment_details = client.payment.fetch(razorpay_payment_id)
        actual_method = payment_details.get('method', 'razorpay')

        try:
            client.utility.verify_payment_signature({
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': razorpay_signature
            })

            with transaction.atomic():
                order = Order.objects.get(id=django_order_id, user=request.user)
                user = User.objects.select_for_update().get(id=request.user.id)

                wallet_deducted_str = payment_details.get('notes', {}).get('wallet_deducted')
                if wallet_deducted_str:
                    wallet_deducted = Decimal(wallet_deducted_str)
                    if wallet_deducted > 0:
                        if user.wallet_balance >= wallet_deducted:
                            user.wallet_balance -= wallet_deducted
                            user.save()
    
                            # We also register a separate payment record for the wallet portion
                            Payment.objects.create(
                                order=order,
                                payment_method='wallet',
                                transaction_id=f'wallet_{uuid.uuid4().hex[:8]}_split',
                                amount=wallet_deducted,
                                status='completed'
                            )
                        else:
                            return Response({"success": False, "message": "Payment verification failed: Insufficient wallet balance to fulfill split payment deduction."}, status=status.HTTP_400_BAD_REQUEST)

                payment, created = Payment.objects.get_or_create(
                    order=order,
                    defaults={
                        'payment_method': actual_method,
                        'transaction_id': razorpay_payment_id,
                        'amount': Decimal(str(payment_details.get('amount', 0))) / 100, # actual amount paid via razorpay
                        'status': 'completed'
                    }
                )

                if created:
                    # 🚀 FIX 2: Strict indentation to prevent double-deducting stock
                    if order.status == 'cancelled':
                        order.status = 'pending'
                        order.save()

                        # Re-deduct the stock and un-cancel the items
                        for item in order.order_items.all():
                            item.status = 'pending'
                            item.save()
                            if item.product:
                                product = Product.objects.select_for_update().get(id=item.product.id)
                                product.stock -= item.quantity
                                product.save()

                    # Safely clear user's shopping cart (Happens for all successful payments)
                    CartItem.objects.filter(cart__user=request.user).delete()

            self.send_order_status_email(order)
            # async_notify_vendors(order)
            # log_admin_action(...)

            return Response({
                "success": True,
                "message": "Payment verified successfully!",
                "order_id": order.id,
                "payment": PaymentSerializer(payment).data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"success": False, "message": str(e)}, status=400)



class OrderItemViewSet(viewsets.ModelViewSet):
    queryset = OrderItem.objects.select_related('order', 'product').all()
    serializer_class = OrderItemSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        order_id = self.request.query_params.get('order')
        if order_id:
            queryset = queryset.filter(order_id=order_id)
        return queryset


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


class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.select_related('order').all()
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def perform_update(self, serializer):
        instance = self.get_object()
        old_status = instance.status
        new_instance = serializer.save()
        if old_status != new_instance.status:
            log_admin_action(self.request.user, f"Payment Tx #{new_instance.transaction_id} Status: '{old_status}' -> '{new_instance.status}'")


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

        threading.Thread(target=send_email).start()


# ==========================================
# 6. PASSWORD RESET VIA EMAIL OTP ENDPOINTS
# ==========================================
class RequestPasswordResetView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip()
        if not email:
            return Response({"error": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)

        # 🚀 Use iexact to handle case-insensitivity (e.g. User@Gmail.com vs user@gmail.com)
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            return Response({"error": "No account found with this email address."}, status=status.HTTP_400_BAD_REQUEST)

        # Generate 6-digit OTP and cache it using the normalized lower-case email as the key
        otp = str(random.randint(100000, 999999))
        normalized_email = email.lower()

        cache.set(f"pwd_reset_{normalized_email}", otp, timeout=300)

        # Send email
        send_otp_email(to_email=user.email, username=user.username, otp=otp)
        return Response({"detail": "OTP sent successfully."}, status=status.HTTP_200_OK)


class VerifyOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        otp = request.data.get('otp')

        if not email or not otp:
            return Response({"error": "Email and OTP are required."}, status=status.HTTP_400_BAD_REQUEST)

        cached_otp = cache.get(f"pwd_reset_{email}")

        if not cached_otp or str(cached_otp).strip() != str(otp).strip():
            return Response({"error": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"detail": "OTP verified successfully."}, status=status.HTTP_200_OK)


from django.db import transaction, connection

class ConfirmPasswordResetView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        otp = request.data.get('otp')
        new_password = request.data.get('new_password')

        if not email or not otp or not new_password:
            return Response({"error": "All fields are required."}, status=status.HTTP_400_BAD_REQUEST)

        cached_otp = cache.get(f"pwd_reset_{email}")
        if not cached_otp or str(cached_otp).strip() != str(otp).strip():
            return Response({"error": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST)

        # Force atomic transaction to ensure it commits
        try:
            with transaction.atomic():
                user = User.objects.filter(email__iexact=email).first()
                if not user:
                    return Response({"error": "User not found."}, status=status.HTTP_400_BAD_REQUEST)

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


class DownloadInvoiceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        try:
            # Ensure users can only download invoices for their own orders (unless admin)
            order = Order.objects.get(id=order_id)
            if order.user != request.user and getattr(request.user, 'role', None) != 'admin':
                return Response({"error": "Unauthorized access to this invoice."}, status=status.HTTP_403_FORBIDDEN)

            # Generate PDF buffer
            pdf_buffer = generate_invoice_pdf(order)

            # Return file response stream
            filename = f"Invoice_INV-{order.id:05d}.pdf"
            return FileResponse(pdf_buffer, as_attachment=True, filename=filename, content_type='application/pdf')

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
        django_order_id = payment_entity.get('notes', {}).get('django_order_id')

        # 🚀 FIX 1: Extracted 'method' safely from the payment_entity dictionary
        actual_method = payment_entity.get('method', 'razorpay')

        if django_order_id:
            with transaction.atomic():
                order = Order.objects.filter(id=django_order_id).first()

                if order:
                    # 1. PAYMENT CAPTURED (Success or Retry Success)
                    if event == 'payment.captured':
                        transaction_id = payment_entity.get('id')

                        if not Payment.objects.filter(transaction_id=transaction_id).exists():
                            Payment.objects.create(
                                order=order,
                                payment_method=actual_method,
                                transaction_id=transaction_id,
                                amount=order.total_price,
                                status='completed'
                            )

                            # Revive the order if a previous attempt failed
                            if order.status == 'cancelled':
                                order.status = 'pending'
                                order.save()

                                for item in order.order_items.all():
                                    item.status = 'pending'
                                    item.save()
                                    if item.product:
                                        product = Product.objects.select_for_update().get(id=item.product.id)
                                        product.stock -= item.quantity
                                        product.save()

                            CartItem.objects.filter(cart__user=order.user).delete()

                    # 2. PAYMENT FAILED (Declined / Dropped)
                    elif event == 'payment.failed':
                        if order.status == 'pending':
                            order.status = 'cancelled'
                            order.save()

                            for item in order.order_items.all():
                                item.status = 'cancelled'
                                item.save()
                                if item.product:
                                    product = Product.objects.select_for_update().get(id=item.product.id)
                                    product.stock += item.quantity
                                    product.save()

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
        razorpay_payment_id = request.data.get('razorpay_payment_id')
        razorpay_order_id = request.data.get('razorpay_order_id')
        razorpay_signature = request.data.get('razorpay_signature')
        amount = request.data.get('amount')

        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

        try:
            client.utility.verify_payment_signature({
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': razorpay_signature
            })

            # Signature verified. Create Gift Card inside an atomic block for safety
            with transaction.atomic():
                gc = GiftCard.objects.create(
                    owner=None,
                    initial_balance=amount,
                    current_balance=amount
                )

                GiftCardTransaction.objects.create(
                    gift_card=gc,
                    transaction_type='ISSUE',
                    amount=amount,
                    user=request.user
                )

                # Generate QR Code
                qr = qrcode.QRCode(version=1, box_size=10, border=5)
                qr.add_data(str(gc.id))
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")

                img_io = io.BytesIO()
                img.save(img_io, format='PNG')
                img_io.seek(0)

                upload_res = cloudinary.uploader.upload(img_io, folder="gift_cards")
                gc.qr_code_url = upload_res.get('secure_url')
                gc.save()

            return Response({
                'message': 'Gift card purchased successfully',
                'gift_card_id': gc.id,
                'qr_url': gc.qr_code_url
            }, status=status.HTTP_201_CREATED)

        except razorpay.errors.SignatureVerificationError:
            return Response({'error': 'Invalid payment signature'}, status=status.HTTP_400_BAD_REQUEST)

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
                    user.wallet_balance += amount_to_add
                    user.save()
                    
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
