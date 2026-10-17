# authenticate.py
from rest_framework_simplejwt.authentication import JWTAuthentication


class CustomCookieAuthentication(JWTAuthentication):
    def authenticate(self, request):
        # 1. Extract the token from the HTTP-Only cookie
        raw_token = request.COOKIES.get('access_token')

        if raw_token is None:
            return None

        # 2. Validate the token using SimpleJWT's native methods
        validated_token = self.get_validated_token(raw_token)

        return self.get_user(validated_token), validated_token
