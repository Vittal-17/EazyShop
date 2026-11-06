from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase, APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from .models import User


@override_settings(
    CSRF_TRUSTED_ORIGINS=['https://shop.example.invalid'],
    CORS_ALLOWED_ORIGINS=['https://shop.example.invalid'],
    AUTH_COOKIE_SECURE=True, AUTH_COOKIE_SAMESITE='Lax',
    CSRF_COOKIE_SECURE=True, CSRF_COOKIE_SAMESITE='Lax',
)
class CookieAuthenticationTests(APITestCase):
    password = 'Fixture-Password-For-Browser-27!'
    origin = 'https://shop.example.invalid'

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('browser', 'browser@example.invalid', cls.password)

    def setUp(self):
        cache.clear()
        self.client = APIClient(enforce_csrf_checks=True)
        self.csrf = None

    def bootstrap(self):
        response = self.client.get('/api/csrf/', secure=True, HTTP_ORIGIN=self.origin)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertEqual(response['Access-Control-Allow-Origin'], self.origin)
        self.assertEqual(response['Access-Control-Allow-Credentials'], 'true')
        self.csrf = response.data['csrfToken']
        self.assertEqual(len(self.csrf), 64)
        self.assertNotEqual(self.csrf, self.client.cookies['csrftoken'].value)
        return response

    def post(self, path, data=None, **headers):
        return self.client.post(path, data or {}, format='json', secure=True,
                                HTTP_ORIGIN=self.origin, HTTP_X_CSRFTOKEN=self.csrf or '', **headers)

    def login(self):
        self.bootstrap()
        old_csrf = self.csrf
        response = self.post('/api/token/', {'email': self.user.email, 'password': self.password})
        self.assertEqual(response.status_code, 200, response.data)
        self.csrf = response.data['csrfToken']
        self.assertNotEqual(self.csrf, old_csrf)
        self.assertNotIn('access', response.data)
        self.assertNotIn('refresh', response.data)
        return response

    def test_clean_cookie_journey_create_patch_delete_refresh_logout(self):
        login = self.login()
        for name, lifetime in [('access', 'ACCESS_TOKEN_LIFETIME'), ('refresh', 'REFRESH_TOKEN_LIFETIME')]:
            cookie = login.cookies[f'{name}_token']
            self.assertTrue(cookie['httponly'])
            self.assertTrue(cookie['secure'])
            self.assertEqual(cookie['samesite'], 'Lax')
            self.assertEqual(cookie['domain'], '')
            self.assertEqual(cookie['path'], '/')
            self.assertEqual(cookie['max-age'], int(settings.SIMPLE_JWT[lifetime].total_seconds()))
        response = self.post('/api/addresses/', {
            'full_address': 'Test street, Test city, 123456',
        })
        self.assertEqual(response.status_code, 201, response.data)
        path = f"/api/addresses/{response.data['id']}/"
        headers = dict(secure=True, HTTP_ORIGIN=self.origin, HTTP_X_CSRFTOKEN=self.csrf)
        self.assertEqual(self.client.patch(path, {'full_address': 'Updated city'}, format='json', **headers).status_code, 200)
        self.assertEqual(self.client.delete(path, **headers).status_code, 204)
        old_refresh = self.client.cookies['refresh_token'].value
        refreshed = self.post('/api/token/refresh/')
        self.assertEqual(refreshed.status_code, 200)
        self.assertNotIn('access', refreshed.data)
        self.assertNotIn('refresh', refreshed.data)
        self.assertNotEqual(old_refresh, self.client.cookies['refresh_token'].value)
        current_refresh = self.client.cookies['refresh_token'].value
        self.assertEqual(self.post('/api/logout/').status_code, 200)
        self.assertFalse(self.client.cookies['access_token'].value)
        self.assertFalse(self.client.cookies['refresh_token'].value)
        for token in (old_refresh, current_refresh):
            self.assertEqual(self.post('/api/token/refresh/', {'refresh': token}).status_code, 401)
        self.assertEqual(self.client.get(f'/api/users/{self.user.pk}/', secure=True).status_code, 401)

    def test_cookie_setters_reject_missing_invalid_and_foreign_origin_csrf(self):
        self.bootstrap()
        for path in ('/api/token/', '/api/token/refresh/', '/api/logout/'):
            data = {'email': self.user.email, 'password': self.password}
            for header, origin in (('', self.origin), ('invalid', self.origin), (self.csrf, 'https://evil.example.invalid'), (self.csrf, 'null')):
                response = self.client.post(path, data, format='json', secure=True,
                                            HTTP_X_CSRFTOKEN=header, HTTP_ORIGIN=origin)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.data['code'], 'csrf_failed')
                self.assertNotIn('access_token', response.cookies)
        self.client.cookies.clear()
        self.assertEqual(self.post('/api/token/', data).status_code, 403)

    def test_authenticated_writes_reject_csrf_even_with_bearer_header(self):
        self.login()
        access = self.client.cookies['access_token'].value
        for method in ('post', 'put', 'patch', 'delete'):
            for origin, token in ((self.origin, ''), (self.origin, 'bad'), ('https://evil.example.invalid', self.csrf)):
                response = getattr(self.client, method)(f'/api/users/{self.user.pk}/', {}, format='json',
                    secure=True, HTTP_ORIGIN=origin, HTTP_X_CSRFTOKEN=token,
                    HTTP_AUTHORIZATION=f'Bearer {access}')
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.data['code'], 'csrf_failed')

    def test_bearer_only_writes_work_without_csrf_and_invalid_bearer_fails(self):
        token = str(AccessToken.for_user(self.user))
        path = f'/api/users/{self.user.pk}/'
        response = self.client.patch(path, {'first_name': 'Bearer'}, format='json',
                                     HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.patch(path, {}, format='json', HTTP_AUTHORIZATION='Bearer invalid').status_code, 401)

    def test_rotated_csrf_rejects_old_token_but_bootstrap_recovers(self):
        self.bootstrap()
        old = self.csrf
        self.login()
        self.csrf = old
        self.assertEqual(self.post('/api/token/refresh/').status_code, 403)
        self.bootstrap()
        self.assertEqual(self.post('/api/token/refresh/').status_code, 200)

    def test_expired_access_returns_401_then_cookie_refresh_recovers(self):
        self.login()
        expired = AccessToken.for_user(self.user)
        expired.set_exp(lifetime=timedelta(seconds=-1))
        self.client.cookies['access_token'] = str(expired)
        path = f'/api/users/{self.user.pk}/'
        self.assertEqual(self.client.get(path, secure=True).status_code, 401)
        self.assertEqual(self.post('/api/token/refresh/').status_code, 200)
        self.assertEqual(self.client.get(path, secure=True).status_code, 200)

    def test_expired_refresh_and_logout_with_expired_access(self):
        self.login()
        expired = RefreshToken.for_user(self.user)
        expired.set_exp(lifetime=timedelta(seconds=-1))
        self.client.cookies['refresh_token'] = str(expired)
        self.client.cookies['access_token'] = 'expired-token'
        self.assertEqual(self.post('/api/token/refresh/').status_code, 401)
        self.assertEqual(self.post('/api/logout/').status_code, 200)

    def test_logout_revocation_failure_is_not_success(self):
        self.login()
        with patch('api.views.RefreshToken.blacklist', side_effect=RuntimeError('fixture failure')):
            response = self.post('/api/logout/')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('refresh_token', response.cookies)
        self.assertTrue(self.client.cookies['refresh_token'].value)

    def test_cookie_refresh_cannot_be_switched_by_body(self):
        self.login()
        other = User.objects.create_user('other', 'other@example.invalid')
        response = self.post('/api/token/refresh/', {'refresh': str(RefreshToken.for_user(other))})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AccessToken(response.cookies['access_token'].value)['user_id'], self.user.pk)

    @override_settings(AUTH_COOKIE_SAMESITE='None', CSRF_COOKIE_SAMESITE='None')
    def test_cross_site_policy_and_cors_header_preflight(self):
        bootstrap = self.bootstrap()
        self.assertEqual(bootstrap.cookies['csrftoken']['samesite'], 'None')
        self.assertTrue(bootstrap.cookies['csrftoken']['secure'])
        self.assertTrue(bootstrap.cookies['csrftoken']['httponly'])
        response = self.login()
        self.assertEqual(response.cookies['access_token']['samesite'], 'None')
        self.assertTrue(response.cookies['access_token']['secure'])
        preflight = self.client.options('/api/token/', secure=True, HTTP_ORIGIN=self.origin,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST', HTTP_ACCESS_CONTROL_REQUEST_HEADERS='content-type,x-csrftoken')
        self.assertEqual(preflight['Access-Control-Allow-Origin'], self.origin)
        self.assertIn('x-csrftoken', preflight['Access-Control-Allow-Headers'])
        foreign = self.client.get('/api/csrf/', secure=True, HTTP_ORIGIN='https://evil.example.invalid')
        self.assertNotIn('Access-Control-Allow-Origin', foreign)

    def test_https_referer_required_without_origin(self):
        self.bootstrap()
        data = {'email': self.user.email, 'password': self.password}
        for referer, expected in (('', 403), ('https://evil.example.invalid/', 403), (self.origin + '/', 200)):
            response = self.client.post('/api/token/', data, format='json', secure=True,
                HTTP_X_CSRFTOKEN=self.csrf, HTTP_REFERER=referer)
            self.assertEqual(response.status_code, expected)

    @override_settings(AUTH_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False,
                       CSRF_TRUSTED_ORIGINS=['http://localhost:3000'])
    def test_explicit_local_development_contract(self):
        response = self.client.get('/api/csrf/', HTTP_HOST='localhost')
        response = self.client.post('/api/token/', {'email': self.user.email, 'password': self.password},
            format='json', HTTP_HOST='localhost', HTTP_ORIGIN='http://localhost:3000',
            HTTP_X_CSRFTOKEN=response.data['csrfToken'])
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.cookies['access_token']['secure'])
        self.assertEqual(response.cookies['access_token']['samesite'], 'Lax')

    def test_signed_webhook_does_not_require_browser_csrf(self):
        import hashlib
        import hmac
        import json
        body = json.dumps({'event': 'fixture.ignored', 'payload': {}})
        signature = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
        for value, expected in (('invalid', 400), (signature, 200)):
            response = self.client.post('/api/webhooks/razorpay/', body, content_type='application/json',
                secure=True, HTTP_X_RAZORPAY_SIGNATURE=value, HTTP_ORIGIN='https://provider.example.invalid')
            self.assertEqual(response.status_code, expected)

    def test_csrf_contract_preserves_registration_and_recovery_requests(self):
        self.client.cookies['access_token'] = 'expired-session'
        self.bootstrap()
        registered = self.post('/api/register/', {
            'username': 'new-browser', 'email': 'new-browser@example.invalid',
            'password': self.password, 'password2': self.password, 'first_name': 'New',
        })
        self.assertEqual(registered.status_code, 201, registered.data)
        with patch('api.views.send_otp_email'):
            response = self.post('/api/password-reset/request/', {'email': self.user.email})
        self.assertEqual(response.status_code, 200)
        otp = cache.get(f'pwd_reset_{self.user.email}')
        self.assertEqual(self.post('/api/password-reset/verify/', {
            'email': self.user.email, 'otp': otp,
        }).status_code, 200)
        reset = self.post('/api/password-reset/confirm/', {
            'email': self.user.email, 'otp': otp, 'new_password': 'Recovered-Fixture-Passphrase-94!',
            'role': 'admin', 'wallet_balance': '90000.00', 'is_superuser': True,
        })
        self.assertEqual(reset.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, 'user')
        self.assertFalse(self.user.is_superuser)
        self.assertEqual(self.user.wallet_balance, 0)
        self.assertTrue(self.user.check_password('Recovered-Fixture-Passphrase-94!'))
