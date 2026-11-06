from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.middleware.csrf import CsrfViewMiddleware
from rest_framework import exceptions


class EnforceCSRF(CsrfViewMiddleware):
    def _reject(self, request, reason):
        return reason


class CustomCookieAuthentication(JWTAuthentication):
    def authenticate(self, request):
        # 1. Explicit Authorization header (Bearer token in header is immune to cross-site ambient cookie CSRF)
        header = self.get_header(request)
        if header is not None:
            raw_token = self.get_raw_token(header)
            if raw_token is not None:
                try:
                    validated_token = self.get_validated_token(raw_token)
                    return self.get_user(validated_token), validated_token
                except (InvalidToken, TokenError):
                    pass

        # 2. Ambient Cookie authentication: read HTTP-Only access_token cookie
        raw_token = request.COOKIES.get('access_token')

        if raw_token:
            # 🚀 SEC-06: Enforce CSRF validation for ambient cookie-authenticated state-changing requests
            if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
                csrf_middleware = EnforceCSRF(lambda r: None)
                reason = csrf_middleware.process_view(request, None, (), {})
                if reason and not getattr(request, '_dont_enforce_csrf_checks', False):
                    raise exceptions.PermissionDenied(f'CSRF Verification Failed: {reason}')

            try:
                validated_token = self.get_validated_token(raw_token)
                return self.get_user(validated_token), validated_token
            except (InvalidToken, TokenError):
                pass

        return None
