from decimal import Decimal
from api.utils.async_tasks import run_async

from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from .email_service import send_welcome_email
from .models import (
    GiftCard,
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
    WalletTransaction,
)


# ==========================================
# 1. USERS & AUTHENTICATION
# ==========================================
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'role', 'phone', 'profile_picture', 'wallet_balance']
        read_only_fields = fields

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'password2')

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({'password': "Passwords don't match."})
        return attrs

    def create(self, validated_data):
        user = User(username=validated_data['username'], email=validated_data['email'])
        user.set_password(validated_data['password'])
        user.save()

        # 🚀 The New Welcome Email Trigger isolated via on_commit hook
        transaction.on_commit(lambda: run_async(send_welcome_email, user.email, user.username))

        return user

class UserProfileUpdateSerializer(serializers.ModelSerializer):
    profile_picture = serializers.ImageField(required=False)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'phone', 'role', 'profile_picture']
        read_only_fields = ['id', 'role']
        extra_kwargs = {'email': {'required': False}, 'username': {'required': False}}

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        # A full-row save could overwrite a concurrent wallet or role change.
        if validated_data:
            instance.save(update_fields=validated_data.keys())
        return instance


class AdminUserProfileUpdateSerializer(UserProfileUpdateSerializer):
    class Meta(UserProfileUpdateSerializer.Meta):
        read_only_fields = ['id']

class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True)

    def validate_current_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Incorrect current password.")
        return value

class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = '__all__'
        read_only_fields = ['user']


# ==========================================
# 2. CATALOG (CATEGORIES & PRODUCTS)
# ==========================================
class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'

class ProductSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source='vendor.username', read_only=True)

    class Meta:
        model = Product
        fields = '__all__'
        read_only_fields = ['id', 'vendor', 'approval_status', 'created_at']


# ==========================================
# 3. CART SYSTEM
# ==========================================
class CartItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_image = serializers.URLField(source='product.image_url', read_only=True)
    price = serializers.DecimalField(source='product.price', max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = CartItem
        fields = ['id', 'product', 'product_name', 'product_image', 'price', 'quantity']

    def validate(self, data):
        product = data.get('product')
        if not product and self.instance:
            product = self.instance.product
        quantity = data.get('quantity', 1)

        # 🚀 NEW SECURITY CHECK: Block unapproved or inactive products
        if product and (not getattr(product, 'is_active', True) or getattr(product, 'approval_status', 'approved') != 'approved'):
            raise serializers.ValidationError({
                'product': "This product is pending approval and cannot be purchased yet."
            })

        if product and quantity > product.stock:
            raise serializers.ValidationError({
                'quantity': f"Sorry, we only have {product.stock} of these in stock right now."
            })
        return data

class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)

    class Meta:
        model = Cart
        fields = ['id', 'user', 'created_at', 'items']
        read_only_fields = ['id', 'user', 'created_at']


# ==========================================
# 4. ORDER & CHECKOUT SYSTEM
# ==========================================
class OrderItemSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='product.name', read_only=True)
    description = serializers.CharField(source='product.description', read_only=True)
    image_url = serializers.CharField(source='product.image_url', read_only=True)

    # 🚀 Add these fields to expose customer info and address directly to the vendor sale item
    username = serializers.CharField(source='order.user.username', read_only=True)
    shipping_address = serializers.CharField(source='order.shipping_address', read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            'id', 'order', 'product', 'quantity', 'price',
            'name', 'description', 'image_url', 'status', 'seller_earnings',
            'username', 'shipping_address'  # 🚀 Included here
        ]
        read_only_fields = ['id', 'price', 'seller_earnings', 'order', 'username', 'shipping_address']


class OrderSerializer(serializers.ModelSerializer):
    order_items = OrderItemSerializer(many=True)

    class Meta:
        model = Order
        fields = [
            'id', 'user', 'status', 'created_at', 'order_items',
            'total_price', 'shipping_address', 'contact_phone'
        ]
        read_only_fields = ['id', 'user', 'created_at', 'total_price']

    def validate(self, data):
        if not self.instance:
            shipping_address = data.get('shipping_address')
            contact_phone = data.get('contact_phone')
            if not shipping_address or not str(shipping_address).strip() or not contact_phone or not str(contact_phone).strip():
                raise serializers.ValidationError("Order placement failed: A valid shipping address and contact phone number are compulsory.")
        return data

    def update(self, instance, validated_data):
        request = self.context.get('request')
        user = request.user if request else None

        if 'status' in validated_data:
            if user and getattr(user, 'role', None) == 'admin':
                instance.status = validated_data['status']
            else:
                raise PermissionDenied(detail="You do not have permission to do this!")

        instance.shipping_address = validated_data.get('shipping_address', instance.shipping_address)
        instance.contact_phone = validated_data.get('contact_phone', instance.contact_phone)
        instance.save()
        return instance

    def create(self, validated_data):
        order_items_data = validated_data.pop('order_items')
        user = validated_data.pop('user', self.context['request'].user)

        with transaction.atomic():
            # Deterministic lock ordering: sort product IDs to guarantee deadlock freedom
            product_ids = sorted({item_data['product'].id for item_data in order_items_data})
            products_qs = Product.objects.select_for_update().filter(id__in=product_ids).order_by('id')
            products_map = {p.id: p for p in products_qs}

            total_price = Decimal('0.00')

            for item_data in order_items_data:
                product_id = item_data['product'].id
                product = products_map.get(product_id)

                # 🚨 SECURITY CHECK: Ensure product hasn't been soft-deleted or rejected
                if not product or not getattr(product, 'is_active', True) or getattr(product, 'approval_status', 'approved') != 'approved':
                    product_name = product.name if product else f"ID {product_id}"
                    raise serializers.ValidationError(f"Checkout failed: '{product_name}' is no longer available.")

                if item_data['quantity'] > product.stock:
                    raise serializers.ValidationError(f"Checkout failed: '{product.name}' only has {product.stock} units left.")

                actual_price = product.price
                total_price += item_data['quantity'] * actual_price

                # Inject server-verified data into the dictionary
                item_data['price'] = actual_price
                item_data['vendor'] = product.vendor  # 🚀 THIS ROUTES THE FUNDS!

                product.stock -= item_data['quantity']
                product.save(update_fields=['stock'])

            order = Order.objects.create(user=user, total_price=total_price, **validated_data)

            for item_data in order_items_data:
                OrderItem.objects.create(order=order, **item_data)

            if 'request' in self.context:
                CartItem.objects.filter(cart__user=self.context['request'].user).delete()

        return order


# ==========================================
# 5. REVIEWS, WISHLIST & ADMIN TOOLS
# ==========================================
class ReviewSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = Review
        fields = ['id', 'product', 'product_name', 'rating', 'comment', 'created_at', 'username']
        read_only_fields = ['user']

class WishlistSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(), source='product', write_only=True
    )

    class Meta:
        model = Wishlist
        fields = ['id', 'product', 'product_id', 'created_at']
        read_only_fields = ['user', 'created_at']

class CouponSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coupon
        fields = '__all__'

class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = '__all__'

class AdminLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdminLog
        fields = '__all__'


# serializers.py
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Custom claims added to token payload
        token["username"] = user.username
        token["email"] = user.email

        return token

    def validate(self, attrs):
        # Run standard SimpleJWT validation (checks username/password)
        super().validate(attrs)

        # Generate tokens for the authenticated user
        refresh = self.get_token(self.user)
        access = refresh.access_token

        # Build clean response data dictionary
        data = {}
        data["success"] = True
        data["message"] = "Login successful. Tokens attached via cookies."
        data["user"] = {
            "id": self.user.id,
            "username": self.user.username,
            "email": self.user.email,
        }

        # 🚀 Temporarily expose tokens here so CookieTokenObtainPairView can read them
        # before stripping them out of the final JSON body.
        data["access"] = str(access)
        data["refresh"] = str(refresh)

        return data
class GiftCardSerializer(serializers.ModelSerializer):
    class Meta:
        model = GiftCard
        fields = '__all__'


class WalletTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletTransaction
        fields = ['id', 'amount', 'balance_after', 'transaction_type', 'reference_id', 'description', 'created_at']
        read_only_fields = fields
