from django.middleware.csrf import CsrfViewMiddleware
from rest_framework import exceptions
from rest_framework_simplejwt.authentication import JWTAuthentication


class EnforceCSRF(CsrfViewMiddleware):
    def _reject(self, request, reason):
        return reason


def enforce_csrf(request):
    # DRF views are middleware-exempt. Explicitly run Django's complete token,
    # Origin and HTTPS Referer validation, including on anonymous cookie setters.
    raw_request = getattr(request, '_request', request)
    middleware = EnforceCSRF(lambda r: None)
    middleware.process_request(raw_request)
    reason = middleware.process_view(raw_request, None, (), {})
    if reason:
        raise exceptions.PermissionDenied({
            'detail': f'CSRF Verification Failed: {reason}', 'code': 'csrf_failed',
        })


class CustomCookieAuthentication(JWTAuthentication):
    def authenticate(self, request):
        raw_token = request.COOKIES.get('access_token')
        if raw_token:
            enforce_csrf(request)
        # Explicit bearer compatibility never suppresses ambient-cookie CSRF.
        bearer = super().authenticate(request)
        if bearer is not None:
            return bearer
        if raw_token:
            validated_token = self.get_validated_token(raw_token)
            return self.get_user(validated_token), validated_token
        return None
