from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm
from django.core.exceptions import ValidationError

from .fulfillment import fulfill_order

# Explicit imports are safer than *
from .models import (
    GiftCard,
    GiftCardTransaction,
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
)


class UserAdminPasswordChangeForm(AdminPasswordChangeForm):
    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save(update_fields=['password'])
        return user


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    change_password_form = UserAdminPasswordChangeForm
    list_display = ('username', 'email', 'role', 'is_staff', 'is_active')
    list_filter = ('role', 'is_staff', 'is_superuser')
    # Custom fieldsets ensure we don't break the default UserAdmin
    fieldsets = BaseUserAdmin.fieldsets + (
        (None, {'fields': ('role', 'phone')}),
    )

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if request.user.is_superuser:
            return fields
        return (*fields, 'role', 'is_staff', 'is_superuser', 'groups', 'user_permissions')

    def _is_protected_user(self, request, obj):
        return obj is not None and not request.user.is_superuser and (
            obj.is_staff or obj.is_superuser or obj.role == 'admin'
        )

    def has_change_permission(self, request, obj=None):
        if self._is_protected_user(request, obj):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if self._is_protected_user(request, obj):
            return False
        return super().has_delete_permission(request, obj)

    def save_model(self, request, obj, form, change):
        if not change:
            return super().save_model(request, obj, form, change)
        changed_fields = set(form.changed_data) & {field.name for field in obj._meta.concrete_fields}
        if changed_fields:
            obj.save(update_fields=changed_fields)

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'stock', 'category', 'created_at')
    list_filter = ('category',)
    search_fields = ('name', 'description')

class CommerceRecordAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(CommerceRecordAdmin):
    list_display = ('id', 'user', 'total_price', 'status', 'created_at', 'contact_phone')
    list_filter = ('status', 'created_at')
    search_fields = ('user__username', 'shipping_address')
    actions = ['ship_orders', 'deliver_orders']

    def has_fulfill_permission(self, request):
        return request.user.has_perm('api.change_order')

    def _fulfill_orders(self, request, queryset, status):
        for order_id in queryset.values_list('pk', flat=True):
            try:
                fulfill_order(order_id, status)
            except (Order.DoesNotExist, ValidationError) as exc:
                self.message_user(request, f"Order #{order_id}: {exc}", level=messages.ERROR)

    @admin.action(permissions=['fulfill'], description='Ship selected settled orders')
    def ship_orders(self, request, queryset):
        self._fulfill_orders(request, queryset, 'shipped')

    @admin.action(permissions=['fulfill'], description='Deliver selected shipped orders')
    def deliver_orders(self, request, queryset):
        self._fulfill_orders(request, queryset, 'delivered')

@admin.register(OrderItem)
class OrderItemAdmin(CommerceRecordAdmin):
    list_display = ('order', 'product', 'quantity', 'price')

@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ('user', 'label', 'full_address', 'is_default')
    list_filter = ('is_default',)

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('product', 'user', 'rating', 'created_at')
    search_fields = ('product__name', 'user__username')

@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ('user', 'product', 'created_at')

@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ('code', 'discount_percent', 'expires_at')
    search_fields = ('code',)

@admin.register(Payment)
class PaymentAdmin(CommerceRecordAdmin):
    list_display = ('order', 'payment_method', 'amount', 'status', 'created_at')
    list_filter = ('status', 'payment_method')

@admin.register(AdminLog)
class AdminLogAdmin(admin.ModelAdmin):
    list_display = ('admin', 'action', 'timestamp')
    search_fields = ('admin__username', 'action')

@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at')
    search_fields = ('user__username',)

@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ('cart', 'product', 'quantity')
    search_fields = ('product__name', 'cart__user__username')
admin.site.register(GiftCard, CommerceRecordAdmin)
admin.site.register(GiftCardTransaction, CommerceRecordAdmin)
from .models import PurchaseIntent, ProviderPaymentClaim, ProviderEvent
admin.site.register(PurchaseIntent, CommerceRecordAdmin)
admin.site.register(ProviderPaymentClaim, CommerceRecordAdmin)
admin.site.register(ProviderEvent, CommerceRecordAdmin)

from .models import ProviderRefund
admin.site.register(ProviderRefund, CommerceRecordAdmin)
