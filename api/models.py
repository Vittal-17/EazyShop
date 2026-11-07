import uuid
from decimal import Decimal

from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import Exists, OuterRef, Subquery, Sum
from django.db.models.functions import Cast, Round


# ==========================================
# USERS & ADDRESSES
# ==========================================
class User(AbstractUser):
    email = models.EmailField(unique=True)
    ROLE_CHOICES = (
        ('user', 'Customer'),
        ('seller', 'Vendor / Seller'),
        ('admin', 'Administrator'),
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='user')
    phone = models.CharField(max_length=20, blank=True, null=True, unique=True)
    wallet_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True, null=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        # Index email and role for faster authentication and admin filtering
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['role']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(wallet_balance__gte=Decimal('0.00')),
                name='user_wallet_balance_gte_0'
            )
        ]

    def __str__(self):
        return self.email

class Address(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='addresses')
    label = models.CharField(max_length=50, default='Home')
    full_address = models.TextField()
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_default', '-created_at']

    def __str__(self):
        return f"{self.label} - {self.user.username}"


# ==========================================
# E-COMMERCE CORE (CATALOG)
# ==========================================
class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']

    def __str__(self):
        return self.name

class Product(models.Model):
    APPROVAL_CHOICES = (
        ('pending', 'Pending Approval'),
        ('approved', 'Approved & Live'),
        ('rejected', 'Rejected'),
    )
    name = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    stock = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='products')
    image_url = models.URLField()
    created_at = models.DateTimeField(auto_now_add=True)

    vendor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='listed_products', null=True)
    approval_status = models.CharField(max_length=20, choices=APPROVAL_CHOICES, default='pending')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        # Massive performance boost for catalog filtering/sorting
        indexes = [
            models.Index(fields=['category']),
            models.Index(fields=['price']),
            models.Index(fields=['created_at']),
            models.Index(fields=['is_active', 'approval_status', '-created_at'], name='product_catalog_idx'),
            models.Index(fields=['category', 'is_active', 'approval_status'], name='product_cat_status_idx'),
            models.Index(fields=['vendor', 'approval_status'], name='product_vendor_status_idx'),
            models.Index(fields=['category', 'price'], name='product_cat_price_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(stock__gte=0),
                name='product_stock_gte_0'
            )
        ]

    def __str__(self):
        return self.name


# ==========================================
# CART SYSTEM
# ==========================================
class Cart(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cart')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Cart of {self.user.username}"

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])

    class Meta:
        # Prevents duplicate entries of the same product in a single cart
        constraints = [
            models.UniqueConstraint(fields=['cart', 'product'], name='unique_cart_item')
        ]

    def __str__(self):
        return f"{self.quantity} x {self.product.name} in cart of {self.cart.user.username}"


# ==========================================
# ORDER SYSTEM
# ==========================================
class OrderQuerySet(models.QuerySet):
    def with_verified_settlement(self):
        payments = Payment.objects.filter(order_id=OuterRef('pk'))
        verified_total = (
            payments.filter(status='completed', verified_at__isnull=False, amount__gt=0)
            .order_by().values('order_id')
            .annotate(total=Sum(Cast(Round(models.F('amount') * 100), models.BigIntegerField()))).values('total')
        )
        return self.alias(total_minor=Cast(Round(models.F('total_price') * 100), models.BigIntegerField())).filter(
            Exists(OrderItem.objects.filter(order_id=OuterRef('pk')).exclude(status='cancelled')),
            Exists(PurchaseIntent.objects.filter(order_id=OuterRef('pk'), state='settled', purpose='merchandise')
                .filter(models.Q(expected_amount=0) | models.Q(claim__state='captured'))),
            ~Exists(payments.filter(status__in=['refunded', 'refund_pending', 'refund_failed'])),
            total_price__gt=0,
            total_minor=Subquery(verified_total),
        )

    def fulfillable(self):
        return self.with_verified_settlement().filter(status__in=Order.FULFILLABLE_STATUSES)


class Order(models.Model):
    FULFILLABLE_STATUSES = ('paid', 'processing', 'shipped', 'delivered')
    CONTACT_FIELDS = ('shipping_address', 'contact_phone')
    CONTACT_EDITABLE_STATUSES = ('pending', 'pending_payment', 'paid', 'processing')
    objects = OrderQuerySet.as_manager()

    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('pending_payment', 'Pending Payment'),
        ('paid', 'Paid'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled')
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='orders')
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    shipping_address = models.TextField(blank=True, null=True)
    contact_phone = models.CharField(max_length=20, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    gateway_order_id = models.CharField(max_length=100, null=True, blank=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        # Supercharges dashboard queries for specific order statuses
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['created_at']),
        ]

    def require_verified_settlement(self):
        if not Order.objects.with_verified_settlement().filter(pk=self.pk).exists():
            raise ValidationError("Order does not have verified payment settlement.")

    def save(self, *args, **kwargs):
        if self._state.adding:
            if self.status in self.FULFILLABLE_STATUSES:
                raise ValidationError("A new order cannot start in a paid or fulfillment state.")
            return super().save(*args, **kwargs)

        with transaction.atomic():
            current = Order.objects.select_for_update().get(pk=self.pk)
            fields = kwargs.get('update_fields')
            contact_changed = any(
                (fields is None or field in fields) and getattr(self, field) != getattr(current, field)
                for field in self.CONTACT_FIELDS
            )
            if contact_changed and (
                current.status not in self.CONTACT_EDITABLE_STATUSES
                or current.order_items.filter(status__in=['shipped', 'delivered']).exists()
            ):
                raise ValidationError("Shipping and contact details are locked after fulfillment starts or the order closes.")
            if (fields is None or 'status' in fields) and current.status != self.status:
                transitions = {
                    'pending': ('pending_payment', 'paid', 'processing', 'cancelled'),
                    'pending_payment': ('paid', 'processing', 'cancelled'),
                    'paid': ('processing', 'shipped', 'cancelled'),
                    'processing': ('shipped', 'cancelled'),
                    'shipped': ('delivered', 'cancelled'),
                }
                if self.status not in transitions.get(current.status, ()):
                    raise ValidationError("Invalid order status transition.")
                if self.status in self.FULFILLABLE_STATUSES:
                    self.require_verified_settlement()
                active_items = self.order_items.exclude(status='cancelled')
                if self.status == 'shipped' and not active_items.filter(status__in=['shipped', 'delivered']).exists():
                    raise ValidationError("Ship an order item before advancing the order.")
                if self.status == 'delivered' and active_items.exclude(status='delivered').exists():
                    raise ValidationError("All active order items must be delivered first.")
            self.full_clean()
            result = super().save(*args, **kwargs)
            if self.status == 'cancelled':
                PurchaseIntent.objects.filter(order=self).exclude(state__in=['refunded', 'reconciliation']).update(state='cancelled', updated_at=timezone.now())
            return result


class OrderItem(models.Model):

    ITEM_STATUS_CHOICES = (
        ('pending', 'Pending Fulfillment'),
        ('shipped', 'Shipped by Vendor'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    )

    order = models.ForeignKey('Order', on_delete=models.PROTECT, related_name='order_items')
    product = models.ForeignKey('Product', on_delete=models.SET_NULL, null=True, related_name='order_history')
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    price = models.DecimalField(max_digits=10, decimal_places=2)

    # Vendor Fulfillment & Finance Architecture
    vendor = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, related_name='vendor_sales')
    status = models.CharField(max_length=20, choices=ITEM_STATUS_CHOICES, default='pending')

    # The EazyShop Business Model (Platform takes 10%, Seller keeps 90%)
    platform_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    seller_earnings = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(quantity__gt=0),
                name='order_item_quantity_gt_0'
            )
        ]

    def save(self, *args, **kwargs):
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=self.order_id)
            if self._state.adding:
                if self.status in ('shipped', 'delivered') or order.status in Order.FULFILLABLE_STATUSES:
                    raise ValidationError("Cannot add an item to a settled order or create a fulfilled item.")
                total = Decimal(str(self.price)) * self.quantity
                self.platform_fee = total * Decimal('0.10')
                self.seller_earnings = total - self.platform_fee
                return super().save(*args, **kwargs)

            current = OrderItem.objects.get(pk=self.pk)
            fields = kwargs.get('update_fields')
            if current.order_id != self.order_id:
                raise ValidationError("Cannot move an order item to a different order.")
            if (fields is not None and 'status' not in fields) or current.status == self.status:
                return super().save(*args, **kwargs)
            if self.status == 'cancelled' and order.status == 'cancelled':
                return super().save(*args, **kwargs)

            next_status = {'pending': 'shipped', 'processing': 'shipped', 'shipped': 'delivered'}
            if order.status not in ('paid', 'processing', 'shipped') or next_status.get(current.status) != self.status:
                raise ValidationError("Invalid order item fulfillment transition.")
            order.require_verified_settlement()
            super().save(*args, **kwargs)

            if self.status == 'shipped' and order.status != 'shipped':
                order.status = 'shipped'
                order.save(update_fields=['status'])
            elif self.status == 'delivered' and not order.order_items.exclude(status__in=['cancelled', 'delivered']).exists():
                order.status = 'delivered'
                order.save(update_fields=['status'])

    def __str__(self):
        return f"{self.quantity} x {self.product.name if self.product else 'Deleted Product'} (Order #{self.order.id})"


# ==========================================
# REVIEWS & WISHLIST
# ==========================================
class Review(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reviews')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    rating = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        # User can only leave ONE review per product
        constraints = [
            models.UniqueConstraint(fields=['user', 'product'], name='unique_product_review')
        ]

    def __str__(self):
        return f"Review by {self.user.username} on {self.product.name}"

class Wishlist(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wishlist')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        # User cannot add the same product to their wishlist twice
        constraints = [
            models.UniqueConstraint(fields=['user', 'product'], name='unique_wishlist_item')
        ]

    def __str__(self):
        return f"{self.user.username}'s Wishlist: {self.product.name}"


# ==========================================
# PAYMENTS & PROMOS
# ==========================================
class Coupon(models.Model):
    code = models.CharField(max_length=50, unique=True)
    discount_percent = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(100)])
    expires_at = models.DateField()

    class Meta:
        indexes = [
            models.Index(fields=['code']),
        ]

    def __str__(self):
        return self.code

class Payment(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('authorized', 'Authorized'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
        ('refund_failed', 'Refund Failed'),
    )
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='payment')

    # 🚀 REMOVED choices=PAYMENT_METHODS, increased max_length to handle Razorpay's dynamic strings
    payment_method = models.CharField(max_length=50, default='razorpay')

    transaction_id = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    verified_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['transaction_id']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"Payment {self.transaction_id} - {self.status}"


# ==========================================
# ADMIN LOGS
# ==========================================
class AdminLog(models.Model):
    admin = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    action = models.CharField(max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"Admin {self.admin.username}: {self.action}"


# ==========================================
# GIFT CARDS
# ==========================================
class GiftCard(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='gift_cards', null=True, blank=True)
    initial_balance = models.DecimalField(max_digits=10, decimal_places=2)
    current_balance = models.DecimalField(max_digits=10, decimal_places=2)
    qr_code_url = models.URLField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"GiftCard {self.id} - Balance: {self.current_balance}"

class GiftCardTransaction(models.Model):
    TYPE_CHOICES = (
        ('ISSUE', 'Issue'),
        ('REDEEM', 'Redeem'),
        ('REFUND', 'Refund'),
    )
    gift_card = models.ForeignKey(GiftCard, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    order = models.ForeignKey('Order', on_delete=models.SET_NULL, null=True, blank=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.transaction_type} of {self.amount} on {self.gift_card.id}"


# ==========================================
# WALLET AUDIT LEDGER
# ==========================================
class WalletTransaction(models.Model):
    TRANSACTION_TYPES = (
        ('CREDIT_GIFT_CARD', 'Gift Card Redemption'),
        ('DEBIT_ORDER', 'Order Checkout'),
        ('REFUND_ORDER', 'Order Cancellation Refund'),
        ('ADMIN_ADJUSTMENT', 'Admin Adjustment'),
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wallet_transactions')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    balance_after = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(max_length=25, choices=TRANSACTION_TYPES)
    reference_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['transaction_type']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.transaction_type}: {self.amount} (Balance: {self.balance_after})"


def record_wallet_transaction(user, amount, transaction_type, reference_id=None, description=""):
    """
    Atomically adjust user wallet balance and insert a WalletTransaction ledger row.
    Amount should be positive Decimal.
    For DEBIT_ORDER, user balance is decremented by amount.
    For CREDIT_GIFT_CARD / REFUND_ORDER / ADMIN_ADJUSTMENT, user balance is incremented by amount.
    """
    amount = Decimal(str(amount))
    if amount <= Decimal('0.00'):
        raise ValidationError("Wallet transaction amount must be strictly positive.")

    if transaction_type == 'DEBIT_ORDER':
        if user.wallet_balance < amount:
            raise ValidationError("Insufficient wallet balance for debit.")
        user.wallet_balance -= amount
    elif transaction_type in ['CREDIT_GIFT_CARD', 'REFUND_ORDER', 'ADMIN_ADJUSTMENT']:
        user.wallet_balance += amount
    else:
        raise ValidationError(f"Invalid transaction type: {transaction_type}")

    user.save(update_fields=['wallet_balance'])

    tx = WalletTransaction.objects.create(
        user=user,
        amount=amount,
        balance_after=user.wallet_balance,
        transaction_type=transaction_type,
        reference_id=str(reference_id) if reference_id else None,
        description=description
    )
    return tx


# ==========================================
# UNIVERSAL CACHE INVALIDATION SIGNALS
# ==========================================
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache


@receiver([post_save, post_delete], sender=Category)
def invalidate_category_cache_signal(sender, **kwargs):
    """
    ADV-ARCH-04: Universal cache invalidation for Category mutations.
    Ensures any category create/update/delete across views, admin, management commands,
    or direct ORM updates purges 'cache_category_list'.
    """
    cache.delete('cache_category_list')


@receiver([post_save, post_delete], sender=Order)
def invalidate_order_invoice_cache_signal(sender, instance, **kwargs):
    """
    ADV-ARCH-05: Universal cache invalidation for Order mutations (PDF invoices).
    Ensures any status change or order mutation purges all cached invoice variants.
    """
    for s in ['pending_payment', 'processing', 'shipped', 'delivered', 'cancelled', 'refunded', 'failed', 'paid']:
        cache.delete(f"invoice_pdf_{instance.id}_{s}")

class PurchaseIntent(models.Model):
    """Server-created commercial terms. Legacy records deliberately have no intent."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purpose = models.CharField(max_length=16, choices=[('merchandise', 'Merchandise'), ('gift_card', 'Gift card')])
    purchaser = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    order = models.OneToOneField(Order, null=True, blank=True, on_delete=models.PROTECT, related_name='purchase_intent')
    gift_card = models.OneToOneField('GiftCard', null=True, blank=True, on_delete=models.PROTECT, related_name='purchase_intent')
    provider_order_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    currency = models.CharField(max_length=3, default='INR')
    expected_amount = models.PositiveBigIntegerField()  # provider leg, minor units
    wallet_amount = models.PositiveBigIntegerField(default=0)
    wallet_debit = models.OneToOneField('WalletTransaction', null=True, blank=True, on_delete=models.PROTECT)
    idempotency_key = models.CharField(max_length=128, null=True, blank=True)
    request_fingerprint = models.CharField(max_length=64, null=True, editable=False)
    state = models.CharField(max_length=20, default='creating', choices=[(v, v) for v in (
        'creating', 'pending', 'settled', 'cancelled', 'failed', 'refunded', 'reconciliation')])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['purchaser', 'purpose', 'idempotency_key'], name='purchase_request_once'),
            models.CheckConstraint(condition=models.Q(currency='INR'), name='intent_currency_inr'),
            models.CheckConstraint(condition=models.Q(expected_amount__gt=0) | models.Q(wallet_amount__gt=0), name='intent_positive_total'),
            models.CheckConstraint(condition=(models.Q(purpose='merchandise', order__isnull=False, gift_card__isnull=True) |
                models.Q(purpose='gift_card', order__isnull=True, wallet_amount=0, expected_amount__gt=0)), name='intent_purpose_object'),
            models.CheckConstraint(condition=(models.Q(wallet_amount=0, wallet_debit__isnull=True) |
                models.Q(wallet_amount__gt=0, wallet_debit__isnull=False)), name='intent_wallet_evidence'),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            current = type(self).objects.get(pk=self.pk)
            immutable = ('purpose', 'purchaser_id', 'order_id', 'currency', 'expected_amount',
                         'wallet_amount', 'wallet_debit_id', 'idempotency_key', 'request_fingerprint')
            if any(getattr(current, f) != getattr(self, f) for f in immutable):
                raise ValidationError('Purchase terms are immutable.')
            for field in ('provider_order_id', 'gift_card_id'):
                if getattr(current, field) is not None and getattr(current, field) != getattr(self, field):
                    raise ValidationError('Purchase binding is immutable.')
            if current.state in ('cancelled', 'failed', 'refunded', 'reconciliation') and self.state in ('pending', 'settled'):
                raise ValidationError('A closed purchase cannot be reactivated.')
        return super().save(*args, **kwargs)


class ProviderPaymentClaim(models.Model):
    """One global provider payment namespace, including quarantined historical IDs."""
    payment_id = models.CharField(max_length=100, primary_key=True)
    intent = models.OneToOneField(PurchaseIntent, null=True, blank=True, on_delete=models.PROTECT, related_name='claim')
    provider_order_id = models.CharField(max_length=100, blank=True)
    amount = models.PositiveBigIntegerField(default=0)
    currency = models.CharField(max_length=3, blank=True)
    state = models.CharField(max_length=20, default='captured', choices=[(v, v) for v in (
        'captured', 'refunded', 'quarantined', 'refund_pending')])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ProviderEvent(models.Model):
    """Signed-event inbox, without customer PII or bearer gift-card credentials."""
    fingerprint = models.CharField(max_length=64, primary_key=True)
    event = models.CharField(max_length=40)
    payment_id = models.CharField(max_length=100, blank=True)
    provider_order_id = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=20, default='received')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ProviderRefund(models.Model):
    """Immutable processed refund evidence; amounts are provider-currency minor units."""
    refund_id = models.CharField(max_length=100, primary_key=True)
    claim = models.ForeignKey(ProviderPaymentClaim, on_delete=models.PROTECT, related_name='refunds')
    amount = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3)
    provider_cumulative = models.PositiveBigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name='refund_amount_positive'),
            models.CheckConstraint(condition=models.Q(provider_cumulative__gte=models.F('amount')), name='refund_cumulative_covers_event'),
            models.CheckConstraint(condition=models.Q(currency='INR'), name='refund_currency_inr'),
        ]
