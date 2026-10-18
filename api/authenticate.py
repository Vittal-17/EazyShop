from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


class CustomCookieAuthentication(JWTAuthentication):
    def authenticate(self, request):
        # 1. Primary: Extract token from the HTTP-Only cookie
        raw_token = request.COOKIES.get('access_token')

        if raw_token:
            try:
                validated_token = self.get_validated_token(raw_token)
                return self.get_user(validated_token), validated_token
            except (InvalidToken, TokenError):
                # If cookie is expired or invalid, fall back to Authorization header
                pass

        # 2. Fallback: If cookie is blocked, absent, empty, or invalid, read Authorization: Bearer <token> header
        return super().authenticate(request)
