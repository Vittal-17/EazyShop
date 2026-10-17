from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    GiftCardPurchaseView,
    GiftCardVerifyPurchaseView,
    GiftCardCheckView,
    GiftCardListView,
    GiftCardRedeemView,
    AddressViewSet,
    AdminLogViewSet,
    CartItemViewSet,
    CartViewSet,
    CategoryViewSet,
    CookieTokenObtainPairView,
    CookieTokenRefreshView,
    CouponViewSet,
    LogoutView,
    OrderItemViewSet,
    OrderViewSet,
    PaymentViewSet,
    ProductViewSet,
    RegisterView,
    ReviewViewSet,
    UserViewSet,
    VendorSalesViewSet,
    WishlistViewSet,VerifyOTPView,RequestPasswordResetView,ConfirmPasswordResetView,DownloadInvoiceView,razorpay_webhook
)

# Public API router
router = DefaultRouter()
router.register(r'users', UserViewSet, basename='users')
router.register(r'vendor-sales', VendorSalesViewSet, basename='vendor-sales')
router.register(r'addresses', AddressViewSet, basename='address')
router.register(r'categories', CategoryViewSet)
router.register(r'products', ProductViewSet)
router.register(r'orders', OrderViewSet, basename='orders')
router.register(r'order-items', OrderItemViewSet)
router.register(r'reviews', ReviewViewSet)
router.register(r'wishlist', WishlistViewSet)
router.register(r'coupons', CouponViewSet)
router.register(r'payments', PaymentViewSet)
router.register(r'admin-logs', AdminLogViewSet)
router.register(r'cart', CartViewSet, basename='cart')
router.register(r'cart-items', CartItemViewSet, basename='cart-items')

# Admin-only API router (strictly for frontend admin panel)
admin_router = DefaultRouter()
admin_router.register(r'users', UserViewSet, basename='admin-users')
admin_router.register(r'products', ProductViewSet, basename='admin-products')
admin_router.register(r'orders', OrderViewSet, basename='admin-orders')

urlpatterns = [
    path('gift-cards/', GiftCardListView.as_view(), name='gift-card-list'),
    path('gift-cards/redeem/', GiftCardRedeemView.as_view(), name='gift-card-redeem'),
    path('gift-cards/check/', GiftCardCheckView.as_view(), name='gift-card-check'),
    path('gift-cards/purchase/', GiftCardPurchaseView.as_view(), name='gift-card-purchase'),
    path('gift-cards/verify/', GiftCardVerifyPurchaseView.as_view(), name='gift-card-verify'),
    path('', include(router.urls)),  # public API
    path('secure/api/', include(admin_router.urls)),  # protected admin-only API for React
    path('register/', RegisterView.as_view(), name='register'),
    path('token/', CookieTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', CookieTokenRefreshView.as_view(), name='token_refresh'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('password-reset/request/', RequestPasswordResetView.as_view(), name='password-reset-request'),
    path('password-reset/verify/', VerifyOTPView.as_view(), name='password-reset-verify'),
    path('password-reset/confirm/', ConfirmPasswordResetView.as_view(), name='password-reset-confirm'),
    path('orders/<int:order_id>/invoice/', DownloadInvoiceView.as_view(), name='download-invoice'),
    path('webhooks/razorpay/', razorpay_webhook, name='razorpay-webhook'),
]
