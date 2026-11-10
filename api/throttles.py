from rest_framework.throttling import SimpleRateThrottle, UserRateThrottle
from rest_framework.settings import api_settings

class AuthRateThrottle(SimpleRateThrottle):
    """
    Burst rate throttling for authentication endpoints (login, register, OTP, password reset).
    Applies universally by IP address (to both unauthenticated and authenticated requests)
    to prevent credential stuffing, email flooding, and CPU exhaustion from password hashing.
    """
    scope = 'auth'

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return self.cache_format % {
            'scope': self.scope,
            'ident': ident
        }

    def get_rate(self):
        rates = getattr(api_settings, 'DEFAULT_THROTTLE_RATES', {})
        return rates.get(self.scope) or self.THROTTLE_RATES.get(self.scope)


class CheckoutRateThrottle(UserRateThrottle):
    """
    Rate throttling for order creation and checkout endpoints.
    Protects payment gateway API limits, database row locking, and inventory reservation.
    """
    scope = 'checkout'

    def get_rate(self):
        rates = getattr(api_settings, 'DEFAULT_THROTTLE_RATES', {})
        return rates.get(self.scope) or self.THROTTLE_RATES.get(self.scope)
