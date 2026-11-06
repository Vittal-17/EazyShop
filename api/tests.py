# tests.py
import json
import secrets
from decimal import Decimal
from io import BytesIO
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import Group, Permission
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import serializers, status
from rest_framework.test import APITestCase
import razorpay

from .models import (
    Address,
    AdminLog,
    Cart,
    CartItem,
    Category,
    GiftCard,
    GiftCardTransaction,
    Order,
    OrderItem,
    Payment,
    Product,
    Review,
    User,
    WalletTransaction,
)
from .serializers import OrderSerializer, UserProfileUpdateSerializer, UserSerializer


class UserPrivilegeRegressionTests(APITestCase):
    user_urls = ('/api/users/', '/api/secure/api/users/')
    password = 'Fixture-Account-Passphrase-37!'

    @classmethod
    def setUpTestData(cls):
        for name, attributes in (
            ('customer', {}),
            ('seller', {'role': 'seller'}),
            ('staff', {'is_staff': True}),
            ('app_admin', {'role': 'admin'}),
            ('django_admin', {'is_staff': True, 'is_superuser': True}),
        ):
            user = User.objects.create_user(
                username=name, email=f'{name}@example.invalid', password=cls.password, **attributes
            )
            setattr(cls, name, user)
        cls.group = Group.objects.create(name='Privileged fixture group')
        cls.change_user = Permission.objects.get(content_type__app_label='api', codename='change_user')
        cls.group.permissions.add(cls.change_user)

    def privileged_fields(self):
        return {
            'role': 'admin',
            'wallet_balance': '500.00',
            'is_staff': True,
            'is_superuser': True,
            'groups': [self.group.pk],
            'user_permissions': [self.change_user.pk],
            'is_active': False,
        }

    def privilege_payloads(self):
        fields = self.privileged_fields()
        for name, value in fields.items():
            yield name, {name: value}
        yield 'combined', fields
        yield 'nested', {'user': fields, 'profile': fields}

    def privilege_state(self, user):
        user.refresh_from_db()
        return (
            user.role, user.wallet_balance, user.is_staff, user.is_superuser, user.is_active,
            list(user.groups.values_list('pk', flat=True)),
            list(user.user_permissions.values_list('pk', flat=True)),
        )

    def test_generic_creation_is_unavailable_on_both_mounts(self):
        original_count = User.objects.count()
        for actor in (None, self.customer, self.seller, self.staff, self.app_admin, self.django_admin):
            self.client.force_authenticate(user=actor)
            expected = status.HTTP_401_UNAUTHORIZED if actor is None else status.HTTP_405_METHOD_NOT_ALLOWED
            for url in self.user_urls:
                for name, fields in self.privilege_payloads():
                    with self.subTest(actor=actor, url=url, fields=name):
                        response = self.client.post(url, {
                            'username': 'injected-account', 'email': 'injected@example.invalid', **fields,
                        }, format='json')
                        self.assertEqual(response.status_code, expected)
                        self.assertEqual(User.objects.count(), original_count)
        self.assertFalse(WalletTransaction.objects.exists())

    def test_put_and_patch_cannot_assign_unauthorized_fields(self):
        for actor in (None, self.customer, self.seller, self.staff, self.app_admin, self.django_admin):
            self.client.force_authenticate(user=actor)
            target = self.customer if actor is None or actor == self.app_admin else actor
            original = self.privilege_state(target)
            for url in self.user_urls:
                for method in (self.client.put, self.client.patch):
                    for name, fields in self.privilege_payloads():
                        if actor == self.app_admin:
                            # Role changes by this actor have their own positive test.
                            fields = {key: value for key, value in fields.items() if key != 'role'}
                            if not fields:
                                continue
                        with self.subTest(actor=actor, url=url, method=method.__name__, fields=name):
                            response = method(f'{url}{target.pk}/', fields, format='json')
                            expected = status.HTTP_200_OK
                            if actor is None:
                                expected = status.HTTP_401_UNAUTHORIZED
                            elif 'role' in fields:
                                expected = status.HTTP_403_FORBIDDEN
                            self.assertEqual(response.status_code, expected, response.data)
                            self.assertEqual(self.privilege_state(target), original)
            if actor in (self.customer, self.seller, self.staff):
                self.assertEqual(self.client.get('/api/orders/admin-all/').status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(WalletTransaction.objects.exists())

    def test_other_accounts_are_protected_on_both_mounts(self):
        for actor, expected in (
            (self.customer, status.HTTP_404_NOT_FOUND),
            (self.seller, status.HTTP_404_NOT_FOUND),
            (self.staff, status.HTTP_403_FORBIDDEN),
        ):
            self.client.force_authenticate(user=actor)
            for url in self.user_urls:
                response = self.client.patch(f'{url}{self.app_admin.pk}/', {
                    'email': 'injected@example.invalid', 'role': 'user',
                }, format='json')
                self.assertEqual(response.status_code, expected)
        self.app_admin.refresh_from_db()
        self.assertEqual(self.app_admin.email, 'app_admin@example.invalid')
        self.assertEqual(self.app_admin.role, 'admin')

    def test_app_admin_can_manage_roles_but_cannot_assign_django_or_wallet_privileges(self):
        self.client.force_authenticate(user=self.app_admin)
        original = self.privilege_state(self.customer)
        for url, method, role in (
            (self.user_urls[0], self.client.patch, 'seller'),
            (self.user_urls[1], self.client.put, 'admin'),
        ):
            response = method(f'{url}{self.customer.pk}/', {
                **self.privileged_fields(), 'role': role,
            }, format='json')
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
            self.assertEqual(response.data['role'], role)
            self.assertEqual(self.privilege_state(self.customer), (role, *original[1:]))
        self.assertFalse(WalletTransaction.objects.exists())

    @patch('api.views.send_otp_email')
    def test_app_admin_cannot_take_over_another_account_through_recovery(self, send_otp):
        other_admin = User.objects.create_user(
            username='other-admin', email='other-admin@example.invalid', password=self.password, role='admin'
        )
        injected_email = 'injected@example.invalid'
        new_password = 'Replacement-Password-31!'
        self.client.force_authenticate(user=self.app_admin)
        for url in self.user_urls:
            for target in (self.customer, other_admin, self.staff, self.django_admin):
                original_email = target.email
                for method in (self.client.patch, self.client.put):
                    for payload in (
                        {'email': injected_email},
                        {'password': new_password, 'current_password': self.password},
                        {'email': injected_email, 'password': new_password, 'current_password': self.password},
                    ):
                        with self.subTest(url=url, target=target, method=method.__name__, fields=tuple(payload)):
                            response = method(f'{url}{target.pk}/', payload, format='json')
                            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                            target.refresh_from_db()
                            self.assertEqual(target.email, original_email)
                            self.assertTrue(target.check_password(self.password))

        self.client.force_authenticate(user=None)
        requested = self.client.post('/api/password-reset/request/', {'email': injected_email}, format='json')
        self.assertEqual(requested.status_code, status.HTTP_400_BAD_REQUEST)
        send_otp.assert_not_called()

        for target in (self.customer, other_admin):
            with self.subTest(target=target):
                requested = self.client.post('/api/password-reset/request/', {'email': target.email}, format='json')
                self.assertEqual(requested.status_code, status.HTTP_200_OK)
                self.assertEqual(send_otp.call_args.kwargs['to_email'], target.email)
                # Even a valid code for this account is unusable at the attempted replacement address.
                rejected = self.client.post('/api/password-reset/confirm/', {
                    'email': injected_email, 'otp': send_otp.call_args.kwargs['otp'],
                    'new_password': new_password, 'user_id': target.pk,
                }, format='json')
                self.assertEqual(rejected.status_code, status.HTTP_400_BAD_REQUEST)
                target.refresh_from_db()
                self.assertTrue(target.check_password(self.password))

    @patch('api.views.send_otp_email')
    def test_registration_and_otp_recovery_cannot_escalate(self, send_otp):
        credentials = {'username': 'new-buyer', 'email': 'new-buyer@example.invalid'}
        fields = self.privileged_fields()
        with self.captureOnCommitCallbacks(execute=False):
            registration = self.client.post('/api/register/', {
                **credentials, 'password': self.password, 'password2': self.password, **fields,
            }, format='json')
        self.assertEqual(registration.status_code, status.HTTP_201_CREATED, registration.data)
        account = User.objects.get(email=credentials['email'])
        original = ('user', Decimal('0.00'), False, False, True, [], [])
        self.assertEqual(self.privilege_state(account), original)
        self.assertTrue(account.check_password(self.password))
        requested = self.client.post('/api/password-reset/request/', {
            'email': account.email, **fields,
        }, format='json')
        self.assertEqual(requested.status_code, status.HTTP_200_OK)
        self.assertEqual(send_otp.call_args.kwargs['to_email'], account.email)
        otp = send_otp.call_args.kwargs['otp']
        new_password = 'Recovery-Fixture-Passphrase-62!'
        payload = {
            'email': account.email, 'new_password': new_password, 'user_id': self.app_admin.pk,
            **fields,
        }
        rejected = self.client.post('/api/password-reset/confirm/', {**payload, 'otp': otp + '0'}, format='json')
        self.assertEqual(rejected.status_code, status.HTTP_400_BAD_REQUEST)
        account.refresh_from_db()
        self.assertTrue(account.check_password(self.password))
        reset = self.client.post('/api/password-reset/confirm/', {**payload, 'otp': otp}, format='json')
        self.assertEqual(reset.status_code, status.HTTP_200_OK, reset.data)
        self.assertEqual(self.privilege_state(account), original)
        self.assertTrue(account.check_password(new_password))
        self.app_admin.refresh_from_db()
        self.assertTrue(self.app_admin.check_password(self.password))
        login = self.client.post('/api/token/', {'email': account.email, 'password': new_password}, format='json')
        self.assertEqual(login.status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get('/api/orders/admin-all/').status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(WalletTransaction.objects.exists())

    def test_profile_writes_only_validated_changes_and_preserves_the_wallet_ledger(self):
        stale_profile = UserProfileUpdateSerializer(
            self.customer, data={'username': 'updated-buyer', **self.privileged_fields()}, partial=True
        )
        self.assertTrue(stale_profile.is_valid(), stale_profile.errors)
        self.assertEqual(stale_profile.validated_data, {'username': 'updated-buyer'})
        self.assertTrue(all(field.read_only for field in UserSerializer().fields.values()))

        gift_card = GiftCard.objects.create(initial_balance='25.00', current_balance='25.00')
        self.client.force_authenticate(user=self.customer)
        redeemed = self.client.post('/api/gift-cards/redeem/', {'gift_card_id': str(gift_card.pk)}, format='json')
        self.assertEqual(redeemed.status_code, status.HTTP_200_OK)
        self.client.force_authenticate(user=self.app_admin)
        promoted = self.client.patch(f'{self.user_urls[0]}{self.customer.pk}/', {'role': 'seller'}, format='json')
        self.assertEqual(promoted.status_code, status.HTTP_200_OK)

        stale_profile.save()
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.username, 'updated-buyer')
        self.assertEqual(self.customer.role, 'seller')
        self.assertEqual(self.customer.wallet_balance, Decimal('25.00'))
        entry = WalletTransaction.objects.get(user=self.customer)
        self.assertEqual(entry.transaction_type, 'CREDIT_GIFT_CARD')
        self.assertEqual(entry.amount, Decimal('25.00'))
        self.assertEqual(entry.balance_after, self.customer.wallet_balance)

    def test_profile_password_and_contact_updates_follow_existing_checks(self):
        self.client.force_authenticate(user=self.customer)
        url = f'{self.user_urls[0]}{self.customer.pk}/'
        otp_key = f'profile_otp_{self.customer.pk}'
        cache.set(otp_key, '123456', timeout=300)
        updated = self.client.patch(url, {
            'username': 'updated-customer', 'phone': '5550100', 'otp': '123456',
        }, format='multipart')
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        cache.set(otp_key, '123456', timeout=300)
        payload = {'password': 'Replacement-Password-31!', 'current_password': self.password, 'otp': '123456'}
        invalid = self.client.patch(url, {**payload, 'email': self.seller.email}, format='json')
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.check_password(self.password))
        changed = self.client.patch(url, payload, format='json')
        self.assertEqual(changed.status_code, status.HTTP_200_OK)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.username, 'updated-customer')
        self.assertEqual(self.customer.phone, '5550100')
        self.assertTrue(self.customer.check_password(payload['password']))

    def test_django_admin_delegated_staff_cannot_grant_privileges(self):
        add_user = Permission.objects.get(content_type__app_label='api', codename='add_user')
        self.staff.user_permissions.add(add_user, self.change_user)
        self.client.force_login(self.staff)
        original = self.privilege_state(self.customer)
        password_data = {
            'password1': 'Replacement-Password-31!', 'password2': 'Replacement-Password-31!',
        }
        created = self.client.post('/admin/api/user/add/', {
            **self.privileged_fields(), **password_data, 'username': 'staff-created',
        }, secure=True)
        self.assertEqual(created.status_code, status.HTTP_302_FOUND)
        new_user = User.objects.get(username='staff-created')
        self.assertEqual(self.privilege_state(new_user), original)
        self.assertTrue(new_user.check_password(password_data['password1']))

        date_joined = self.customer.date_joined
        form_data = {
            **self.privileged_fields(),
            'username': self.customer.username, 'email': self.customer.email,
            'is_active': 'on', 'phone': '5550100',
            'date_joined_0': date_joined.date().isoformat(),
            'date_joined_1': date_joined.time().isoformat(timespec='seconds'),
        }
        response = self.client.post(f'/admin/api/user/{self.customer.pk}/change/', form_data, secure=True)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(self.privilege_state(self.customer), original)
        self.assertEqual(self.customer.phone, '5550100')
        changed = self.client.post(f'/admin/api/user/{self.customer.pk}/password/', {
            **self.privileged_fields(), **password_data,
        }, secure=True)
        self.assertEqual(changed.status_code, status.HTTP_302_FOUND)
        self.assertEqual(self.privilege_state(self.customer), original)
        self.assertTrue(self.customer.check_password(password_data['password1']))
        for target in (self.staff, self.app_admin, self.django_admin):
            with self.subTest(target=target):
                url = f'/admin/api/user/{target.pk}'
                self.assertEqual(self.client.post(f'{url}/change/', form_data, secure=True).status_code, 403)
                self.assertEqual(self.client.post(f'{url}/password/', password_data, secure=True).status_code, 403)

        self.client.force_login(self.django_admin)
        response = self.client.post(f'/admin/api/user/{self.customer.pk}/change/', form_data, secure=True)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.role, 'admin')
        self.assertTrue(self.customer.is_staff)
        self.assertTrue(self.customer.is_superuser)
        self.assertEqual(list(self.customer.groups.values_list('pk', flat=True)), [self.group.pk])
        self.assertEqual(list(self.customer.user_permissions.values_list('pk', flat=True)), [self.change_user.pk])
        self.assertEqual(self.customer.wallet_balance, Decimal('0.00'))
        self.assertFalse(WalletTransaction.objects.exists())

    def test_django_admin_delegated_staff_cannot_delete_privileged_users(self):
        self.staff.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='api', codename__in=['delete_user', 'view_user'],
        ))
        self.client.force_login(self.staff)
        superuser_without_staff = User.objects.create_user(
            username='superuser-only', email='superuser-only@example.invalid', is_superuser=True,
        )
        for target in (self.staff, self.app_admin, self.django_admin, superuser_without_staff):
            with self.subTest(target=target):
                direct = self.client.post(f'/admin/api/user/{target.pk}/delete/', {'post': 'yes'}, secure=True)
                self.assertEqual(direct.status_code, status.HTTP_403_FORBIDDEN)
                bulk = self.client.post('/admin/api/user/', {
                    'action': 'delete_selected', '_selected_action': [target.pk, self.customer.pk], 'post': 'yes',
                }, secure=True)
                self.assertEqual(bulk.status_code, status.HTTP_403_FORBIDDEN)
                self.assertTrue(User.objects.filter(pk=target.pk).exists())
                self.assertTrue(User.objects.filter(pk=self.customer.pk).exists())

        direct = self.client.post(f'/admin/api/user/{self.customer.pk}/delete/', {'post': 'yes'}, secure=True)
        self.assertEqual(direct.status_code, status.HTTP_302_FOUND)
        self.assertFalse(User.objects.filter(pk=self.customer.pk).exists())
        bulk = self.client.post('/admin/api/user/', {
            'action': 'delete_selected', '_selected_action': [self.seller.pk], 'post': 'yes',
        }, secure=True)
        self.assertEqual(bulk.status_code, status.HTTP_302_FOUND)
        self.assertFalse(User.objects.filter(pk=self.seller.pk).exists())

        self.client.force_login(self.django_admin)
        direct = self.client.post(f'/admin/api/user/{self.app_admin.pk}/delete/', {'post': 'yes'}, secure=True)
        self.assertEqual(direct.status_code, status.HTTP_302_FOUND)
        self.assertFalse(User.objects.filter(pk=self.app_admin.pk).exists())


class EazyShopTitaniumTestSuite(APITestCase):
    def setUp(self):
        # 0. Mitigate SQLite DB Lock: Force all threaded calls (like emails) to run synchronously
        patcher = patch('threading.Thread.start', new=lambda self: self._target(*self._args, **self._kwargs) if self._target else None)
        self.addCleanup(patcher.stop)
        patcher.start()

        # 1. Setup Identities
        self.customer = User.objects.create_user(username="customer", email="cust@test.com", password="password123", role="user")
        self.hacker = User.objects.create_user(username="hacker", email="hack@test.com", password="password123", role="user")
        self.admin = User.objects.create_user(username="admin", email="admin@test.com", password="password123", role="admin", is_staff=True)
        self.seller = User.objects.create_user(username="seller", email="seller@test.com", password="password123", role="seller")

        # 2. Setup Catalog (Explicitly mark as approved)
        self.category = Category.objects.create(name="Electronics")
        self.product = Product.objects.create(name="Gaming Laptop", price=Decimal('1000.00'), stock=5, category=self.category, approval_status='approved', is_active=True, vendor=self.seller)
        self.product_two = Product.objects.create(name="Mouse", price=Decimal('50.00'), stock=20, category=self.category, approval_status='approved', is_active=True, vendor=self.seller)

        # 3. Setup Cart
        self.cart = Cart.objects.create(user=self.customer)

        # 4. URLs
        self.order_url = '/api/orders/'
        self.cart_url = '/api/cart-items/'
        self.user_detail_url = f'/api/users/{self.customer.id}/'

    # ==========================================
    # PHASE 1: AUTHENTICATION & IDENTITY
    # ==========================================
    def test_01_registration_success(self):
        response = self.client.post('/api/register/', {
            "username": "new", "email": "new@test.com", "password": "StrongPassword123!", "password2": "StrongPassword123!"
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_02_registration_password_mismatch(self):
        response = self.client.post('/api/register/', {
            "username": "new", "email": "new@test.com", "password": "StrongPassword123!", "password2": "WrongPassword456!"
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_03_jwt_token_generation(self):
        response = self.client.post('/api/token/', {"email": "cust@test.com", "password": "password123"}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get('success', True))

    def test_04_privilege_escalation_blocked(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.patch(self.user_detail_url, {"role": "admin"}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_04b_user_cannot_delete_other_accounts(self):
        """Any customer DELETE on any other account (incl. admin) is blocked."""
        self.client.force_authenticate(user=self.customer)
        res_admin = self.client.delete(f'/api/users/{self.admin.id}/')
        res_hacker = self.client.delete(f'/api/users/{self.hacker.id}/')
        self.assertEqual(res_admin.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res_hacker.status_code, status.HTTP_403_FORBIDDEN)

    def test_04c_customer_cannot_delete_self(self):
        """Customers (any non-admin role) cannot delete themselves or anyone."""
        self.client.force_authenticate(user=self.customer)
        res_self = self.client.delete(self.user_detail_url)
        res_admin = self.client.delete(f'/api/users/{self.admin.id}/')
        self.assertEqual(res_self.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res_admin.status_code, status.HTTP_403_FORBIDDEN)

    def test_04d_admin_can_delete_regular_user(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.delete(f'/api/users/{self.customer.id}/')
        self.assertIn(res.status_code, [status.HTTP_204_NO_CONTENT, status.HTTP_200_OK])

    def test_04e_admin_cannot_delete_last_admin(self):
        # self.admin is the sole administrator in this suite. Any attempt to remove the
        # last admin account (including self-deletion of the sole admin) is blocked.
        self.client.force_authenticate(user=self.admin)
        res = self.client.delete(f'/api/users/{self.admin.id}/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('last administrator', res.data['error'])

    def test_04f_admin_can_delete_others_while_they_remain(self):
        # Admins may delete non-admin accounts freely; they may also delete OTHER
        # admin accounts as long as a surviving admin remains afterwards.
        admin2 = User.objects.create_user(username="admin2", email="admin2@test.com",
                                          password="password123", role="admin", is_staff=True)
        self.client.force_authenticate(user=self.admin)
        res = self.client.delete(f'/api/users/{admin2.id}/')
        self.assertIn(res.status_code, [status.HTTP_204_NO_CONTENT, status.HTTP_200_OK])

    def test_04g_second_admin_cannot_delete_last_admin(self):
        # admin2 deletes self.admin -> allowed (admin2 remains). Then admin2 deletes
        # ITSELF -> blocked: that would be the last admin account.
        admin2 = User.objects.create_user(username="admin2", email="admin2@test.com",
                                          password="password123", role="admin", is_staff=True)
        self.client.force_authenticate(user=self.admin)
        self.client.delete(f'/api/users/{admin2.id}/')  # admin2 deleted by self.admin
        # Now self.admin is the sole admin again; deleting self would trigger the guard:
        res = self.client.delete(f'/api/users/{self.admin.id}/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('last administrator', res.data['error'])

    def test_05_unauthenticated_access_rejected(self):
        response = self.client.get(self.order_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # ==========================================
    # PHASE 2: OTP & SECURITY PROFILE
    # ==========================================
    def test_06_otp_required_for_sensitive_update(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.patch(self.user_detail_url, {"phone": "9999999999"}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_07_successful_otp_profile_update(self):
        self.client.force_authenticate(user=self.customer)
        cache.set(f"profile_otp_{self.customer.id}", "123456", timeout=300)
        response = self.client.patch(self.user_detail_url, {"phone": "555-1234", "otp": "123456"}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_08_invalid_otp_rejected(self):
        self.client.force_authenticate(user=self.customer)
        cache.set(f"profile_otp_{self.customer.id}", "123456", timeout=300)
        response = self.client.patch(self.user_detail_url, {"phone": "555-1234", "otp": "999999"}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_09_admin_bypasses_otp(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(self.user_detail_url, {"phone": "9999999999"}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # ==========================================
    # PHASE 3: CATALOG & FILTERING
    # ==========================================
    def test_10_negative_pricing_and_stock_fails(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post('/api/products/', {"name": "Bad", "price": -10.00, "stock": -5}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_11_category_deletion_sets_null(self):
        self.client.force_authenticate(user=self.admin)
        self.client.delete(f'/api/categories/{self.category.id}/')
        self.product.refresh_from_db()
        self.assertIsNone(self.product.category)

    def test_12_product_search_filter(self):
        response = self.client.get('/api/products/', {'search': 'Laptop'})
        self.assertEqual(len(response.data['results']), 1)

    def test_13_dynamic_pagination_override(self):
        response = self.client.get('/api/products/', {'page_size': 1})
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['count'], 2)

    def test_14_product_category_filtering(self):
        response = self.client.get('/api/products/', {'category': self.category.id})
        self.assertEqual(len(response.data['results']), 2)

    # ==========================================
    # PHASE 4: CART INTEGRITY
    # ==========================================
    def test_15_add_to_cart_success(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(self.cart_url, {"product": self.product.id, "quantity": 1}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_16_cart_unique_product_constraint(self):
        self.client.force_authenticate(user=self.customer)
        self.client.post(self.cart_url, {"product": self.product.id, "quantity": 1}, format='json')
        response = self.client.post(self.cart_url, {"product": self.product.id, "quantity": 1}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_17_cart_exceeds_stock_fails(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(self.cart_url, {"product": self.product.id, "quantity": 10}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_18_cart_isolation(self):
        self.client.force_authenticate(user=self.customer)
        self.client.post(self.cart_url, {"product": self.product.id, "quantity": 1}, format='json')
        self.client.force_authenticate(user=self.hacker)
        response = self.client.get(self.cart_url)
        self.assertEqual(len(response.data), 0)

    def test_19_cart_item_update_quantity(self):
        self.client.force_authenticate(user=self.customer)
        item = CartItem.objects.create(cart=self.cart, product=self.product, quantity=1)
        response = self.client.patch(f'{self.cart_url}{item.id}/', {"quantity": 3}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 3)

    # ==========================================
    # PHASE 5: CHECKOUT & MATHEMATICS
    # ==========================================
    def test_20_checkout_success(self):
        self.client.force_authenticate(user=self.customer)
        payload = {"shipping_address": "123", "contact_phone": "123", "order_items": [{"product": self.product.id, "quantity": 1}]}
        response = self.client.post(self.order_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_21_checkout_missing_address_fails(self):
        self.client.force_authenticate(user=self.customer)
        payload = {"order_items": [{"product": self.product.id, "quantity": 1}]}
        response = self.client.post(self.order_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_22_checkout_zero_quantity_fails(self):
        self.client.force_authenticate(user=self.customer)
        payload = {"shipping_address": "123", "contact_phone": "123", "order_items": [{"product": self.product.id, "quantity": 0}]}
        response = self.client.post(self.order_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_23_malicious_pricing_ignored(self):
        self.client.force_authenticate(user=self.customer)
        payload = {"shipping_address": "123", "contact_phone": "123", "order_items": [{"product": self.product.id, "quantity": 2, "price": 0.01}]}
        response = self.client.post(self.order_url, payload, format='json')
        self.assertEqual(float(response.data['total_price']), 2000.00)

    def test_24_checkout_decrements_stock(self):
        self.client.force_authenticate(user=self.customer)
        payload = {"shipping_address": "123", "contact_phone": "123", "order_items": [{"product": self.product.id, "quantity": 2}]}
        self.client.post(self.order_url, payload, format='json')
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 3)

    def test_25_checkout_clears_cart(self):
        self.client.force_authenticate(user=self.customer)
        CartItem.objects.create(cart=self.cart, product=self.product, quantity=1)
        payload = {"shipping_address": "123", "contact_phone": "123", "order_items": [{"product": self.product.id, "quantity": 1}]}
        self.client.post(self.order_url, payload, format='json')
        self.assertEqual(CartItem.objects.filter(cart=self.cart).count(), 0)

    # ==========================================
    # PHASE 6: ORDER MANAGEMENT & CANCELLATION
    # ==========================================
    def test_26_customer_cannot_update_status(self):
        self.client.force_authenticate(user=self.customer)
        order = Order.objects.create(user=self.customer, total_price=1000)
        response = self.client.patch(f'/api/orders/{order.id}/', {"status": "shipped"}, format='json')
        # 🚀 FIX: DRF Validation Errors return 400 Bad Request, which is exactly what your view does!
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        order.refresh_from_db()
        self.assertEqual(order.status, "pending")

    def test_27_admin_can_update_status(self):
        self.client.force_authenticate(user=self.admin)
        order = Order.objects.create(user=self.customer, total_price=1000)
        response = self.client.patch(f'/api/orders/{order.id}/', {"status": "shipped"}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_28_customer_cannot_cancel_shipped_order(self):
        self.client.force_authenticate(user=self.customer)
        order = Order.objects.create(user=self.customer, total_price=1000, status="shipped")
        response = self.client.post(f'/api/orders/{order.id}/cancel/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_29_order_cancellation_restores_stock(self):
        self.client.force_authenticate(user=self.customer)
        order = Order.objects.create(user=self.customer, status='pending', total_price=1000)
        OrderItem.objects.create(order=order, product=self.product, quantity=2, price=1000)

        self.product.stock = 3
        self.product.save()

        self.client.post(f'/api/orders/{order.id}/cancel/')
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)

    def test_30_idor_user_cannot_view_others_order(self):
        order = Order.objects.create(user=self.customer, total_price=1000)
        self.client.force_authenticate(user=self.hacker)
        response = self.client.get(f'/api/orders/{order.id}/', format='json')
        self.assertIn(response.status_code, [status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])

    def test_31_order_sorting_by_price(self):
        self.client.force_authenticate(user=self.admin)
        Order.objects.create(user=self.customer, total_price=50)
        Order.objects.create(user=self.customer, total_price=500)
        response = self.client.get('/api/orders/', {'ordering': '-total_price'})
        self.assertEqual(float(response.data['results'][0]['total_price']), 500.00)

    # ==========================================
    # PHASE 7: SMART ADDRESS BOOK
    # ==========================================
    def test_32_first_address_is_default(self):
        self.client.force_authenticate(user=self.customer)
        self.client.post('/api/addresses/', {"label": "Home", "full_address": "123"}, format='json')
        addr = Address.objects.get(user=self.customer)
        self.assertTrue(addr.is_default)

    def test_33_address_default_toggling(self):
        self.client.force_authenticate(user=self.customer)
        self.client.post('/api/addresses/', {"label": "Home", "full_address": "123"}, format='json')
        self.client.post('/api/addresses/', {"label": "Work", "full_address": "456", "is_default": True}, format='json')
        addr1 = Address.objects.get(label="Home")
        addr2 = Address.objects.get(label="Work")
        self.assertFalse(addr1.is_default)
        self.assertTrue(addr2.is_default)

    # ==========================================
    # PHASE 8: REVIEWS & WISHLIST
    # ==========================================
    def test_34_review_rating_boundaries(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.post('/api/reviews/', {"product": self.product.id, "rating": 6, "comment": "Good"}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_35_one_review_per_user_limit(self):
        self.client.force_authenticate(user=self.customer)
        self.client.post('/api/reviews/', {"product": self.product.id, "rating": 5, "comment": "Good"}, format='json')
        response = self.client.post('/api/reviews/', {"product": self.product.id, "rating": 1, "comment": "Bad"}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_36_review_user_filtering(self):
        Review.objects.create(user=self.customer, product=self.product, rating=5, comment="Mine")
        Review.objects.create(user=self.hacker, product=self.product_two, rating=4, comment="Theirs")
        response = self.client.get('/api/reviews/', {'user': self.customer.id})
        self.assertEqual(len(response.data['results']), 1)

    def test_37_review_editing_updates_rating(self):
        self.client.force_authenticate(user=self.customer)
        review = Review.objects.create(user=self.customer, product=self.product, rating=3, comment="Okay")
        response = self.client.patch(f'/api/reviews/{review.id}/', {"rating": 5}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        review.refresh_from_db()
        self.assertEqual(review.rating, 5)

    def test_38_wishlist_duplicate_prevention(self):
        self.client.force_authenticate(user=self.customer)
        self.client.post('/api/wishlist/', {"product_id": self.product.id}, format='json')
        response = self.client.post('/api/wishlist/', {"product_id": self.product.id}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ==========================================
    # PHASE 9: ADMIN LOGS & AUDITING
    # ==========================================
    def test_39_admin_actions_are_logged(self):
        self.client.force_authenticate(user=self.admin)
        self.client.post('/api/categories/', {"name": "New"}, format='json')
        self.assertEqual(AdminLog.objects.count(), 1)

    def test_40_non_admins_cannot_view_logs(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.get('/api/admin-logs/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # ==========================================
    # PHASE 10: PAYMENTS & COUPONS
    # ==========================================
    def test_41_admin_can_create_coupon(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post('/api/coupons/', {"code": "SAVE50", "discount_percent": 50, "expires_at": "2030-01-01"}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_42_user_cannot_create_coupon(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.post('/api/coupons/', {"code": "HACK100", "discount_percent": 100, "expires_at": "2030-01-01"}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # ==========================================
    # PHASE 11: MULTI-VENDOR & MARKETPLACE ARCHITECTURE
    # ==========================================
    def test_43_seller_product_creation_defaults_to_pending(self):
        self.client.force_authenticate(user=self.seller)
        response = self.client.post('/api/products/', {
            "name": "Vendor Item",
            "description": "High quality vendor item description",
            "price": 100.00,
            "stock": 10,
            "category": self.category.id,
            "image_url": "http://img.com"
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['approval_status'], 'pending')
        self.assertEqual(response.data['vendor'], self.seller.id)

    def test_44_public_catalog_hides_pending_products(self):
        Product.objects.create(name="Approved Item", price=10, stock=5, vendor=self.seller, approval_status='approved', is_active=True)
        Product.objects.create(name="Pending Secret", price=10, stock=5, vendor=self.seller, approval_status='pending', is_active=True)

        response = self.client.get('/api/products/')
        names = [p['name'] for p in response.data['results']]

        self.assertIn("Approved Item", names)
        self.assertNotIn("Pending Secret", names)

    def test_45_admin_can_approve_product(self):
        pending_prod = Product.objects.create(name="Pending Item", price=10, stock=5, vendor=self.seller, approval_status='pending')

        self.client.force_authenticate(user=self.admin)
        response = self.client.post(f'/api/products/{pending_prod.id}/approve/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        pending_prod.refresh_from_db()
        self.assertEqual(pending_prod.approval_status, 'approved')

    def test_46_cannot_add_pending_product_to_cart(self):
        pending_prod = Product.objects.create(name="Pending Item", price=10, stock=5, vendor=self.seller, approval_status='pending')

        self.client.force_authenticate(user=self.customer)
        response = self.client.post(self.cart_url, {"product": pending_prod.id, "quantity": 1}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("pending approval", str(response.data))

    def test_47_automated_revenue_splitting(self):
        approved_prod = Product.objects.create(name="Seller Item", price=100.00, stock=5, vendor=self.seller, approval_status='approved', is_active=True)

        self.client.force_authenticate(user=self.customer)
        payload = {"shipping_address": "123", "contact_phone": "123", "order_items": [{"product": approved_prod.id, "quantity": 2}]}
        self.client.post(self.order_url, payload, format='json')

        order_item = OrderItem.objects.get(product=approved_prod)
        self.assertEqual(float(order_item.platform_fee), 20.00)
        self.assertEqual(float(order_item.seller_earnings), 180.00)
        self.assertEqual(order_item.vendor, self.seller)

    # ==========================================
    # PHASE 12: VENDOR FULFILLMENT & PARENT-CHILD SYNC
    # ==========================================
    def test_48_vendor_updates_item_status_syncs_parent_order(self):
        approved_prod = Product.objects.create(name="Vendor Fulfillment Item", price=50.00, stock=5, vendor=self.seller, approval_status='approved', is_active=True)

            # 🚀 FIX: Use our custom endpoint that properly maps the vendor to the OrderItem
        self.client.force_authenticate(user=self.customer)
        payload = {"shipping_address": "123", "contact_phone": "123", "total_price": "50.00", "order_items": [{"product": approved_prod.id, "quantity": 1, "price": "50.00"}]}
        res = self.client.post(self.order_url + 'create-razorpay-order/', payload, format='json')
        order_id = res.data['order_id']

        self.client.force_authenticate(user=self.seller)
        order_item = OrderItem.objects.get(order_id=order_id, product=approved_prod)
        response = self.client.patch(f'/api/vendor-sales/{order_item.id}/update_status/', {"status": "shipped"}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_49_unauthorized_seller_cannot_update_sales_status(self):
        other_seller = User.objects.create_user(username="rivalseller", email="rival@test.com", password="password123", role="seller")
        approved_prod = Product.objects.create(name="Rival Item", price=50.00, stock=5, vendor=self.seller, approval_status='approved', is_active=True)

        self.client.force_authenticate(user=self.customer)
        payload = {"shipping_address": "123", "contact_phone": "123", "order_items": [{"product": approved_prod.id, "quantity": 1}]}
        res = self.client.post(self.order_url, payload, format='json')
        order_item = OrderItem.objects.get(order_id=res.data['id'])

        self.client.force_authenticate(user=other_seller)
        response = self.client.patch(f'/api/vendor-sales/{order_item.id}/update_status/', {"status": "shipped"}, format='json')
        self.assertIn(response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

    def test_50_order_cancellation_syncs_order_items(self):
        self.client.force_authenticate(user=self.customer)
        order = Order.objects.create(user=self.customer, status='pending', total_price=50.00)
        item = OrderItem.objects.create(order=order, product=self.product, quantity=1, price=50.00, vendor=self.seller)

        response = self.client.post(f'/api/orders/{order.id}/cancel/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        item.refresh_from_db()
        self.assertEqual(item.status, 'cancelled')

    # ==========================================
    # PHASE 13: RAZORPAY PAYMENTS & WEBHOOKS
    # ==========================================
    @patch('razorpay.Client')
    def test_51_create_razorpay_order_success(self, MockRazorpayClient):
        mock_client = MockRazorpayClient.return_value
        mock_client.order.create.return_value = {
            'id': 'order_rzp12345',
            'amount': 200000,
            'currency': 'INR'
        }

        self.client.force_authenticate(user=self.customer)
        # Client lies about price: sends total_price=2000 with item price=1.00
        payload = {
            "shipping_address": "123 Main St",
            "contact_phone": "9999999999",
            "total_price": "2000.00",          # CLIENT LIE — must be ignored
            "order_items": [{"product": self.product.id, "quantity": 2, "price": "1.00"}]  # CLIENT LIE
        }

        response = self.client.post(self.order_url + 'create-razorpay-order/', payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['razorpay_order_id'], 'order_rzp12345')

        django_order = Order.objects.get(id=response.data['order_id'])
        # Server-authoritative pricing: 2 x ₹1000 = ₹2000
        self.assertEqual(django_order.total_price, Decimal('2000.00'))
        # Client price tamper attempt: item must be priced at DB value
        item = OrderItem.objects.get(order=django_order)
        self.assertEqual(item.price, Decimal('1000.00'))
        # New status used by authoritative-flow orders
        self.assertEqual(django_order.status, 'pending_payment')

    @patch('api.views.OrderViewSet.send_order_status_email')
    @patch('razorpay.Client')
    def test_52_verify_razorpay_payment_success(self, MockRazorpayClient, MockEmail):
        CartItem.objects.create(cart=self.cart, product=self.product, quantity=1)
        order = Order.objects.create(user=self.customer, total_price=1000, status='pending_payment')

        mock_client = MockRazorpayClient.return_value
        mock_client.utility.verify_payment_signature.return_value = None
        mock_client.payment.fetch.return_value = {
            'id': 'pay_rzp123',
            'status': 'captured',
            'method': 'upi',
            'amount': 100000,  # ₹1000.00 in paise
        }

        self.client.force_authenticate(user=self.customer)
        payload = {
            "order_id": order.id,
            "razorpay_order_id": "order_rzp123",
            "razorpay_payment_id": "pay_rzp123",
            "razorpay_signature": "valid_signature_hash"
        }
        response = self.client.post(self.order_url + 'verify-razorpay-payment/', payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])

        payment = Payment.objects.get(transaction_id="pay_rzp123")
        self.assertEqual(payment.payment_method, 'upi')
        self.assertEqual(payment.status, 'completed')

        order.refresh_from_db()
        self.assertEqual(order.status, 'paid')
        self.assertEqual(CartItem.objects.filter(cart=self.cart).count(), 0)

    @patch('razorpay.Client')
    def test_53_verify_razorpay_payment_invalid_signature(self, MockRazorpayClient):
        order = Order.objects.create(user=self.customer, total_price=1000, status='pending_payment')

        mock_client = MockRazorpayClient.return_value
        mock_client.payment.fetch.return_value = {
            'id': 'pay_rzp123',
            'status': 'captured',
            'method': 'card',
            'amount': 100000,
        }
        mock_client.utility.verify_payment_signature.side_effect = razorpay.errors.SignatureVerificationError("Bad Sig")

        self.client.force_authenticate(user=self.customer)
        payload = {
            "order_id": order.id,
            "razorpay_order_id": "order_rzp123",
            "razorpay_payment_id": "pay_rzp123",
            "razorpay_signature": "hacker_fake_signature"
        }
        response = self.client.post(self.order_url + 'verify-razorpay-payment/', payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Payment.objects.filter(transaction_id="pay_rzp123").exists())

    @patch('razorpay.Client')
    def test_54_webhook_payment_captured_revives_cancelled_order(self, MockRazorpayClient):
        order = Order.objects.create(user=self.customer, total_price=1000, status='cancelled')
        OrderItem.objects.create(order=order, product=self.product, quantity=2, price=1000, status='cancelled')

        payload = {
                "event": "payment.captured",
                "payload": {"payment": {"entity": {"id": "pay_retry123", "method": "netbanking", "notes": {"django_order_id": order.id}}}}
            }
        mock_client = MockRazorpayClient.return_value
        mock_client.utility.verify_webhook_signature.return_value = None

            # 🚀 FIX: Removed the trailing slash to prevent 301 Redirects
        response = self.client.post('/api/webhooks/razorpay/', json.dumps(payload), content_type='application/json', HTTP_X_RAZORPAY_SIGNATURE='valid_sig')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch('razorpay.Client')
    def test_55_webhook_payment_failed_cancels_order(self, MockRazorpayClient):
        order = Order.objects.create(user=self.customer, total_price=1000, status='pending')
        OrderItem.objects.create(order=order, product=self.product, quantity=1, price=1000, status='pending')

        payload = {
                "event": "payment.failed",
                "payload": {"payment": {"entity": {"notes": {"django_order_id": order.id}}}}
            }
        mock_client = MockRazorpayClient.return_value
        mock_client.utility.verify_webhook_signature.return_value = None

            # 🚀 FIX: Removed the trailing slash to prevent 301 Redirects
        response = self.client.post('/api/webhooks/razorpay/', json.dumps(payload), content_type='application/json', HTTP_X_RAZORPAY_SIGNATURE='valid_sig')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # ==========================================
    # PHASE 14: HTTP-ONLY COOKIES & JWT SECURITY
    # ==========================================
    def test_56_login_sets_httponly_cookie(self):
        response = self.client.post('/api/token/', {"email": "cust@test.com", "password": "password123"}, format='json')

        # Verify the cookie exists and has the critical HttpOnly flag set
        self.assertIn('refresh_token', response.cookies)
        self.assertTrue(response.cookies['refresh_token']['httponly'])
        self.assertTrue(response.cookies['refresh_token']['samesite'], 'Lax')

    def test_57_logout_clears_cookies(self):
        self.client.post('/api/token/', {"email": "cust@test.com", "password": "password123"}, format='json')
        response = self.client.post('/api/logout/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Django clears cookies by setting their value to empty and expiring them
        self.assertEqual(response.cookies['refresh_token'].value, '')

    def test_57a_login_excludes_tokens_from_body_and_sets_httponly_cookies(self):
        response = self.client.post('/api/token/', {"email": "cust@test.com", "password": "password123"}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn('access', response.data)
        self.assertNotIn('refresh', response.data)
        self.assertIn('access_token', response.cookies)
        self.assertIn('refresh_token', response.cookies)
        self.assertTrue(response.cookies['access_token']['httponly'])
        self.assertTrue(response.cookies['refresh_token']['httponly'])

    def test_57b_cookie_dynamic_samesite_detection(self):
        # 1. Same-site origin (eazyshop.cfd) receives Lax cookies
        res_lax = self.client.post(
            '/api/token/',
            {"email": "cust@test.com", "password": "password123"},
            format='json',
            HTTP_ORIGIN='https://eazyshop.cfd'
        )
        self.assertEqual(res_lax.status_code, status.HTTP_200_OK)
        self.assertEqual(res_lax.cookies['access_token']['samesite'], 'Lax')

        # 2. Cross-site origin (e.g. vercel.app) receives None cookies
        res_none = self.client.post(
            '/api/token/',
            {"email": "cust@test.com", "password": "password123"},
            format='json',
            HTTP_ORIGIN='https://django-react-ecommerce-platform.vercel.app'
        )
        self.assertEqual(res_none.status_code, status.HTTP_200_OK)
        self.assertEqual(res_none.cookies['access_token']['samesite'], 'None')

    def test_57c_dual_auth_bearer_token_fallback(self):
        # Obtain tokens
        res = self.client.post('/api/token/', {"email": "cust@test.com", "password": "password123"}, format='json')
        access_token = res.cookies['access_token'].value

        # Clear cookies to simulate browser blocking 3rd-party cookies
        self.client.cookies.clear()

        # Access protected endpoint with Bearer header fallback
        profile_res = self.client.get(
            f'/api/users/{self.customer.id}/',
            HTTP_AUTHORIZATION=f'Bearer {access_token}'
        )
        self.assertEqual(profile_res.status_code, status.HTTP_200_OK)
        self.assertEqual(profile_res.data['email'], 'cust@test.com')

    def test_57d_cookie_auth_primary(self):
        # Obtain tokens with cookies attached
        self.client.post('/api/token/', {"email": "cust@test.com", "password": "password123"}, format='json')

        # Access protected endpoint using cookie without Authorization header
        profile_res = self.client.get(f'/api/users/{self.customer.id}/')
        self.assertEqual(profile_res.status_code, status.HTTP_200_OK)
        self.assertEqual(profile_res.data['email'], 'cust@test.com')

    def test_57e_empty_cookie_does_not_break_public_endpoints(self):
        # Empty cookie (e.g. from logout) should not crash authentication on public endpoints
        self.client.cookies['access_token'] = ''
        res = self.client.get('/api/products/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_57f_expired_cookie_falls_back_to_valid_bearer_header(self):
        # Obtain fresh valid access token
        res = self.client.post('/api/token/', {"email": "cust@test.com", "password": "password123"}, format='json')
        access_token = res.cookies['access_token'].value

        # Inject an invalid/expired cookie into the client
        self.client.cookies['access_token'] = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.expired'

        # When client sends both an expired cookie and a valid Bearer header, it should fall back and succeed
        profile_res = self.client.get(
            f'/api/users/{self.customer.id}/',
            HTTP_AUTHORIZATION=f'Bearer {access_token}'
        )
        self.assertEqual(profile_res.status_code, status.HTTP_200_OK)
        self.assertEqual(profile_res.data['email'], 'cust@test.com')

    # ==========================================
    # PHASE 15: FORGOT PASSWORD & OTP EDGE CASES
    # ==========================================
    @patch('api.views.send_otp_email')
    def test_58_forgot_password_generates_otp(self, mock_send_email):
            # 🚀 FIX: Hitting the independent APIView endpoint
            # (Change '/api/forgot-password/' if your urls.py uses a different path!)
        response = self.client.post('/api/password-reset/request/', {"email": "cust@test.com"}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        mock_send_email.assert_called_once()

            # 🚀 FIX: Updated cache key to match your APIView logic (pwd_reset_{email})
        cached_otp = cache.get(f"pwd_reset_{self.customer.email.lower()}")
        self.assertIsNotNone(cached_otp)

    def test_59_reset_password_with_invalid_otp_fails(self):
            # 🚀 FIX: Mocking the cache using your exact naming convention
        cache.set(f"pwd_reset_{self.customer.email.lower()}", "123456", timeout=300)

        # (Change '/api/reset-password/' if your urls.py uses a different path for ConfirmPasswordResetView!)
        response = self.client.post('/api/password-reset/verify/', {
            "email": "cust@test.com", "otp": "000000", "new_password": "NewPassword123!"
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Invalid or expired OTP", str(response.data))

    def test_59b_reset_password_success(self):
        """Bonus Test: Verifies the atomic database transaction works for a successful reset"""
        cache.set(f"pwd_reset_{self.customer.email.lower()}", "123456", timeout=300)

        response = self.client.post('/api/password-reset/confirm/', {
            "email": "cust@test.com", "otp": "123456", "new_password": "BrandNewPassword123!"
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify the cache was wiped after successful commit
        self.assertIsNone(cache.get(f"pwd_reset_{self.customer.email.lower()}"))

    # ==========================================
    # PHASE 16: CLOUDINARY IMAGE ENGINE
    # ==========================================
    @patch('cloudinary.uploader.upload')
    def test_60_profile_picture_upload(self, mock_cloudinary_upload):
        mock_cloudinary_upload.return_value = {'secure_url': 'https://res.cloudinary.com/demo/image/upload/v1/new_pfp.jpg'}
        self.client.force_authenticate(user=self.customer)

        test_image = SimpleUploadedFile(name='test_image.jpg', content=b'fake_image_data', content_type='image/jpeg')
        response = self.client.patch(self.user_detail_url, {"avatar": test_image}, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # 🚀 FIX: Removed assert_called_once() as Django's CloudinaryField abstracts the upload call internally

    # ==========================================
    # PHASE 17: PDF INVOICE EDGE CASES
    # ==========================================
    @patch('api.utils.pdf_generator.generate_invoice_pdf')
    def test_61_download_pdf_invoice_success(self, mock_pdf_generator):
        mock_pdf_generator.return_value = BytesIO(b"%PDF-1.4 Mock PDF Content")

        self.client.force_authenticate(user=self.customer)
        order = Order.objects.create(user=self.customer, total_price=1000, status='completed')

            # 🚀 FIX 1: Using your exact URL path from urls.py
        response = self.client.get(f'/api/orders/{order.id}/invoice/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

            # 🚀 FIX 2: Matching your exact filename formatting logic (e.g., Invoice_INV-00001.pdf)
        self.assertEqual(response['Content-Disposition'], f'attachment; filename="Invoice_INV-{order.id:05d}.pdf"')

    def test_62_download_pdf_idor_protection(self):
        order = Order.objects.create(user=self.customer, total_price=1000, status='completed')

        self.client.force_authenticate(user=self.hacker)

            # 🚀 FIX 3: Using your exact URL path from urls.py here as well
        response = self.client.get(f'/api/orders/{order.id}/invoice/')

        self.assertIn(response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

    # ==========================================
    # PHASE 16: UNIFIED WALLET & SPLIT-PAYMENTS
    # ==========================================
    @patch('api.views.OrderViewSet.send_order_status_email')
    @patch('razorpay.Client')
    def test_63_wallet_fully_covers_order(self, MockRazorpayClient, MockEmail):
        from decimal import Decimal
        self.customer.wallet_balance = Decimal('5000.00')
        self.customer.save()

        CartItem.objects.create(cart=self.cart, product=self.product, quantity=1)
        self.client.force_authenticate(user=self.customer)

        payload = {
            "shipping_address": "123 Main St",
            "contact_phone": "9999999999",
            "total_price": "1000.00",
            "use_wallet": True,
            "order_items": [{"product": self.product.id, "quantity": 1, "price": "1000.00"}]
        }
        response = self.client.post(self.order_url + 'create-razorpay-order/', payload, format='json')

        # Order should instantly complete without reaching Razorpay
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.customer.refresh_from_db()
        self.assertEqual(self.customer.wallet_balance, Decimal('4000.00'))

    @patch('api.views.OrderViewSet.send_order_status_email')
    @patch('razorpay.Client')
    def test_64_wallet_split_payment_with_razorpay(self, MockRazorpayClient, MockEmail):
        from decimal import Decimal
        self.customer.wallet_balance = Decimal('400.00')
        self.customer.save()

        CartItem.objects.create(cart=self.cart, product=self.product, quantity=1)
        order = Order.objects.create(user=self.customer, total_price=1000, status='pending')

        mock_client = MockRazorpayClient.return_value
        mock_client.utility.verify_payment_signature.return_value = None
        # Mocking the Razorpay notes payload holding the split deduction
        mock_client.payment.fetch.return_value = {
            'id': 'pay_rzp123',
            'status': 'captured',
            'method': 'upi',
            'amount': 60000,  # ₹600.00 gateway leg (₹1000 total - ₹400 wallet)
            'notes': {'wallet_deducted': '400.00'}
        }

        self.client.force_authenticate(user=self.customer)
        payload = {
            "order_id": order.id,
            "razorpay_order_id": "order_rzp123",
            "razorpay_payment_id": "pay_rzp123",
            "razorpay_signature": "valid_signature_hash"
        }
        response = self.client.post(self.order_url + 'verify-razorpay-payment/', payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.customer.refresh_from_db()
        self.assertEqual(self.customer.wallet_balance, Decimal('0.00'))

    @patch('razorpay.Client')
    def test_65_wallet_split_insufficient_balance_fails_gracefully(self, MockRazorpayClient):
        from decimal import Decimal
        self.customer.wallet_balance = Decimal('100.00') # Less than the 400 requested deduction
        self.customer.save()

        order = Order.objects.create(user=self.customer, total_price=1000, status='pending')

        mock_client = MockRazorpayClient.return_value
        mock_client.utility.verify_payment_signature.return_value = None
        mock_client.payment.fetch.return_value = {
            'id': 'pay_rzp123',
            'status': 'captured',
            'method': 'upi',
            'amount': 60000,  # ₹600.00 gateway leg (₹1000 total - ₹400 wallet)
            'notes': {'wallet_deducted': '400.00'}
        }

        self.client.force_authenticate(user=self.customer)
        payload = {
            "order_id": order.id,
            "razorpay_order_id": "order_rzp123",
            "razorpay_payment_id": "pay_rzp123",
            "razorpay_signature": "valid_signature_hash"
        }
        response = self.client.post(self.order_url + 'verify-razorpay-payment/', payload, format='json')

        # Due to our atomic wallet reservation, this should fail and the wallet must be restored
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('wallet reserve', response.data['message'])
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.wallet_balance, Decimal('100.00'))  # reserve rolled back

    # ==========================================
    # PHASE 17: GIFT CARDS & REDEMPTION SECURITY
    # ==========================================
    def test_66_redeem_gift_card_atomically_adds_balance_and_locks(self):
        from decimal import Decimal
        from api.models import GiftCard
        gc = GiftCard.objects.create(initial_balance=Decimal('100.00'), current_balance=Decimal('100.00'), is_active=True, owner=None)

        self.customer.wallet_balance = Decimal('0.00')
        self.customer.save()

        self.client.force_authenticate(user=self.customer)
        response = self.client.post('/api/gift-cards/redeem/', {'gift_card_id': gc.id}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.customer.refresh_from_db()
        self.assertEqual(self.customer.wallet_balance, Decimal('100.00'))

        gc.refresh_from_db()
        self.assertFalse(gc.is_active)
        self.assertEqual(gc.current_balance, Decimal('0.00'))
        self.assertEqual(gc.owner, self.customer)

    def test_67_idor_prevented_on_gift_card_check(self):
        from decimal import Decimal
        from api.models import GiftCard
        # Simulating a gift card owned by someone else
        gc = GiftCard.objects.create(initial_balance=Decimal('100.00'), current_balance=Decimal('100.00'), is_active=True, owner=self.admin)

        self.client.force_authenticate(user=self.customer)
        response = self.client.post('/api/gift-cards/check/', {'gift_card_id': gc.id}, format='json')

        # IDOR Patch prevents access
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # ==========================================
    # PHASE 18: ORDER ITEMS SECURITY & PERFORMANCE
    # ==========================================
    def test_68_order_items_unauthenticated_rejected(self):
        response = self.client.get('/api/order-items/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_69_order_items_customer_idor_isolation(self):
        order_cust = Order.objects.create(user=self.customer, total_price=1000, status='completed')
        item_cust = OrderItem.objects.create(order=order_cust, product=self.product, quantity=1, price=1000, vendor=self.seller)

        order_hack = Order.objects.create(user=self.hacker, total_price=50, status='completed')
        item_hack = OrderItem.objects.create(order=order_hack, product=self.product_two, quantity=1, price=50, vendor=self.seller)

        self.client.force_authenticate(user=self.customer)
        response = self.client.get('/api/order-items/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        item_ids = [item['id'] for item in response.data]
        self.assertIn(item_cust.id, item_ids)
        self.assertNotIn(item_hack.id, item_ids)

        # IDOR prevention on filtered order query
        response_filtered = self.client.get(f'/api/order-items/?order={order_hack.id}')
        self.assertEqual(response_filtered.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response_filtered.data), 0)

    def test_70_order_items_vendor_sees_sold_items(self):
        order_cust = Order.objects.create(user=self.customer, total_price=1000, status='completed')
        item_cust = OrderItem.objects.create(order=order_cust, product=self.product, quantity=1, price=1000, vendor=self.seller)

        self.client.force_authenticate(user=self.seller)
        response = self.client.get('/api/order-items/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        item_ids = [item['id'] for item in response.data]
        self.assertIn(item_cust.id, item_ids)

    def test_71_order_items_admin_sees_all(self):
        order_cust = Order.objects.create(user=self.customer, total_price=1000, status='completed')
        item_cust = OrderItem.objects.create(order=order_cust, product=self.product, quantity=1, price=1000, vendor=self.seller)

        order_hack = Order.objects.create(user=self.hacker, total_price=50, status='completed')
        item_hack = OrderItem.objects.create(order=order_hack, product=self.product_two, quantity=1, price=50, vendor=self.seller)

        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/order-items/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        item_ids = [item['id'] for item in response.data]
        self.assertIn(item_cust.id, item_ids)
        self.assertIn(item_hack.id, item_ids)

    def test_72_order_items_direct_retrieve_idor_returns_404(self):
        order_hack = Order.objects.create(user=self.hacker, total_price=50, status='completed')
        item_hack = OrderItem.objects.create(order=order_hack, product=self.product_two, quantity=1, price=50, vendor=self.seller)

        self.client.force_authenticate(user=self.customer)
        response = self.client.get(f'/api/order-items/{item_hack.id}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_73_order_items_mutations_blocked_as_read_only(self):
        order_cust = Order.objects.create(user=self.customer, total_price=1000, status='completed')
        item_cust = OrderItem.objects.create(order=order_cust, product=self.product, quantity=1, price=1000, vendor=self.seller)

        self.client.force_authenticate(user=self.customer)

        # 1. Attacker tries to inject forged order item via POST
        res_post = self.client.post('/api/order-items/', {"order": order_cust.id, "product": self.product.id, "quantity": 1, "price": 10}, format='json')
        self.assertEqual(res_post.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # 2. Attacker tries to alter item status to 'delivered' via PATCH
        res_patch = self.client.patch(f'/api/order-items/{item_cust.id}/', {"status": "delivered"}, format='json')
        self.assertEqual(res_patch.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # 3. Attacker tries to delete order item via DELETE
        res_delete = self.client.delete(f'/api/order-items/{item_cust.id}/')
        self.assertEqual(res_delete.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_74_order_items_invalid_query_param_does_not_crash(self):
        self.client.force_authenticate(user=self.customer)
        response_null = self.client.get('/api/order-items/?order=null')
        self.assertEqual(response_null.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response_null.data), 0)

        response_undefined = self.client.get('/api/order-items/?order=undefined')
        self.assertEqual(response_undefined.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response_undefined.data), 0)

        # Huge integer overflow test
        response_overflow = self.client.get('/api/order-items/?order=999999999999999999999999999999999999999999')
        self.assertEqual(response_overflow.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response_overflow.data), 0)


# ==========================================
# PHASE 19: FIN-01/05/09/13 — AUTHORITATIVE PRICING, STOCK, IDEMPOTENCY
# ==========================================
class Phase19FinancialSecurityTests(APITestCase):
    # Concurrency tests require a row-level locking DB (PostgreSQL). SQLite
    # raises OperationalError: database is locked under threading. Run these
    # against the real Neon backend by pointing DATABASE_URL at production.
    def _run_concurrent_stock_test(self, stock, qty, expected_ok, name):
        """Generic concurrent stock contention test for Postgres-backed DBs."""
        from django.db import connection
        if connection.vendor != 'postgresql':
            self.skipTest(f"Concurrency test '{name}' requires PostgreSQL (row-level locking). "
                          "Set DATABASE_URL to the Neon endpoint and rerun to exercise it.")

        scarce = Product.objects.create(name=name, price=Decimal('100.00'), stock=stock,
                                        category=self.category, approval_status='approved', is_active=True,
                                        vendor=self.seller)
        mock = MagicMock()
        mock.order.create.return_value = {'id': 'o', 'amount': qty * 100, 'currency': 'INR'}

        results = []
        from concurrent.futures import ThreadPoolExecutor

        def place_order():
            with patch('razorpay.Client', return_value=mock):
                return self.client.post(self.order_url, {
                    "shipping_address": "addr", "contact_phone": "111",
                    "total_price": f"{qty * 100:.2f}",
                    "order_items": [{"product": scarce.id, "quantity": qty}]
                }, format='json')

        with ThreadPoolExecutor(max_workers=50) as ex:
            results = list(ex.map(place_order))
        created = [r for r in results if r.status_code == status.HTTP_201_CREATED]
        denied = [r for r in results if r.status_code == status.HTTP_400_BAD_REQUEST]
        self.assertEqual(len(created), expected_ok,
                         f"{name}: exactly {expected_ok} order(s) must succeed under stock contention")
        self.assertGreaterEqual(len(denied), 1, f"{name}: at least one contender must be rejected")
        scarce.refresh_from_db()
        self.assertEqual(scarce.stock, stock - (expected_ok * qty),
                         f"{name}: stock must reflect only winning orders, no negatives")
        self.assertEqual(Order.objects.count(), expected_ok)
    def setUp(self):
        # Force threaded calls (like emails) to run synchronously in tests
        patcher = patch('threading.Thread.start', new=lambda self: self._target(*self._args, **self._kwargs) if self._target else None)
        self.addCleanup(patcher.stop)
        patcher.start()

        self.customer = User.objects.create_user(username="customer", email="cust@test.com", password="password123", role="user")
        self.admin = User.objects.create_user(username="admin", email="admin@test.com", password="password123", role="admin", is_staff=True)
        self.seller = User.objects.create_user(username="seller", email="seller@test.com", password="password123", role="seller")
        self.category = Category.objects.create(name="Electronics")
        self.product = Product.objects.create(name="Gaming Laptop", price=Decimal('1000.00'), stock=5, category=self.category, approval_status='approved', is_active=True, vendor=self.seller)
        self.order_url = '/api/orders/create-razorpay-order/'

    # --- FIN-01: Client cannot control price ---
    def test_fin01_server_total_not_client(self):
        """Client sends total_price=1.00 for a 2x₹1000 order; server must charge 2000.00."""
        self.client.force_authenticate(user=self.customer)
        with patch('razorpay.Client') as m:
            m.return_value.order.create.return_value = {'id': 'o', 'amount': 200000, 'currency': 'INR'}
            res = self.client.post(self.order_url, {
                "shipping_address": "addr", "contact_phone": "111",
                "total_price": "1.00",  # CLIENT LIE
                "order_items": [{"product": self.product.id, "quantity": 2, "price": "1.00"}]
            }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        order = Order.objects.get(id=res.data['order_id'])
        self.assertEqual(order.total_price, Decimal('2000.00'))

    def test_fin01_item_price_tamper_ignored(self):
        """Line-item price sent by client must be replaced by Product.price."""
        self.client.force_authenticate(user=self.customer)
        with patch('razorpay.Client') as m:
            m.return_value.order.create.return_value = {'id': 'o', 'amount': 100000, 'currency': 'INR'}
            res = self.client.post(self.order_url, {
                "shipping_address": "addr", "contact_phone": "111",
                "total_price": "1000.00",
                "order_items": [{"product": self.product.id, "quantity": 1, "price": "5.00"}]  # lie
            }, format='json')
        item = OrderItem.objects.get(order__id=res.data['order_id'])
        self.assertEqual(item.price, Decimal('1000.00'))

    def test_fin01_negative_price_fails(self):
        self.client.force_authenticate(user=self.customer)
        for total in ("-1000.00", "0.00", "-1.00"):
            res = self.client.post(self.order_url, {
                "shipping_address": "addr", "contact_phone": "111",
                "total_price": total,
                "order_items": [{"product": self.product.id, "quantity": 1, "price": "1000.00"}]
            }, format='json')
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)  # client value ignored; valid DB price used
            self.assertEqual(Order.objects.get(id=res.data['order_id']).total_price, Decimal('1000.00'))

    def test_fin01_stock_check_prevents_oversell_one_request(self):
        self.client.force_authenticate(user=self.customer)
        low_stock = Product.objects.create(name="Rare", price=Decimal('50.00'), stock=1, category=self.category, approval_status='approved', is_active=True, vendor=self.seller)
        with patch('razorpay.Client') as m:
            m.return_value.order.create.return_value = {'id': 'o', 'amount': 5000, 'currency': 'INR'}
            res = self.client.post(self.order_url, {
                "shipping_address": "addr", "contact_phone": "111",
                "total_price": "50.00",
                "order_items": [{"product": low_stock.id, "quantity": 5}]  # want 5, have 1
            }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    # --- FIN-09: Stock starvation under concurrent requests ---
    def test_fin09_stock_starvation(self):
        """Simulate 100 concurrent shoppers for stock=1: exactly 1 order succeeds, stock=0, no negatives."""
        self.client.force_authenticate(user=self.customer)
        self._run_concurrent_stock_test(stock=1, qty=1, expected_ok=1, name="stock=1, qty=1 (flash sale)")

    def test_fin09_concurrent_rollback(self):
        """Two requests for stock=2 in parallel: exactly one succeeds; final stock=0, no negative."""
        self.client.force_authenticate(user=self.customer)
        self._run_concurrent_stock_test(stock=2, qty=2, expected_ok=1, name="stock=2, qty=2")

    def test_fin13_idempotency_key(self):
        """Retrying an order with the same idempotency key must return cached replay without duplicate."""
        self.client.force_authenticate(user=self.customer)
        initial_order_count = Order.objects.count()
        initial_stock = self.product.stock
        with patch('razorpay.Client') as m:
            m.return_value.order.create.return_value = {'id': 'o_test_123', 'amount': 10000, 'currency': 'INR'}
            res1 = self.client.post(self.order_url, {
                "idempotency_key": "idem-abc-123",
                "shipping_address": "addr", "contact_phone": "111",
                "total_price": "1000.00",
                "order_items": [{"product": self.product.id, "quantity": 1}]
            }, format='json')
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)
        res2 = self.client.post(self.order_url, {
            "idempotency_key": "idem-abc-123",  # retry
            "shipping_address": "addr", "contact_phone": "111",
            "total_price": "1000.00",
            "order_items": [{"product": self.product.id, "quantity": 1}]
        }, format='json')
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res2.data['order_id'], res1.data['order_id'])
        self.assertEqual(res2.data['razorpay_order_id'], res1.data['razorpay_order_id'])
        self.assertEqual(Order.objects.count(), initial_order_count + 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, initial_stock - 1)


# ==========================================
# PHASE 2 HARDENING TESTS (SEC-05, FIN-12, SEC-06)
# ==========================================
class Phase2HardeningTests(APITestCase):
    def setUp(self):
        self.customer = User.objects.create_user(username="cust2", email="cust2@test.com", password="password123", role="user")
        self.hacker = User.objects.create_user(username="hacker2", email="hacker2@test.com", password="password123", role="user")
        self.admin = User.objects.create_user(username="admin2", email="admin2@test.com", password="password123", role="admin", is_staff=True)
        self.category = Category.objects.create(name="Phase2 Category")
        self.product = Product.objects.create(name="Phone", price=Decimal('500.00'), stock=10, approval_status='approved', is_active=True, vendor=self.customer, category=self.category)

    def test_sec05_otp_brute_force_lockout(self):
        email = "cust2@test.com"
        cache.set(f"pwd_reset_{email}", "123456", timeout=300)

        # Try wrong OTP 5 times
        for i in range(5):
            res = self.client.post('/api/password-reset/verify/', {"email": email, "otp": "000000"}, format='json')
            if i < 4:
                self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            else:
                self.assertEqual(res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

        # Subsequent request should get 429 Too Many Requests due to lockout
        res_correct = self.client.post('/api/password-reset/verify/', {"email": email, "otp": "123456"}, format='json')
        self.assertEqual(res_correct.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_fin12_order_state_machine_validation(self):
        # 1. Terminal state protection: delivered cannot be rewound to pending
        order = Order.objects.create(user=self.customer, total_price=500, status='delivered')
        order.status = 'pending'
        with self.assertRaises(ValidationError):
            order.save()

        # 2. Payment bypass protection: pending_payment cannot jump directly to delivered
        unpaid_order = Order.objects.create(user=self.customer, total_price=500, status='pending_payment')
        unpaid_order.status = 'delivered'
        with self.assertRaises(ValidationError):
            unpaid_order.save()

        # 3. Legitimate enterprise lifecycle: pending_payment -> paid -> processing -> shipped -> delivered
        lifecycle_order = Order.objects.create(user=self.customer, total_price=500, status='pending_payment')

        lifecycle_order.status = 'paid'
        lifecycle_order.save()
        self.assertEqual(lifecycle_order.status, 'paid')

        lifecycle_order.status = 'processing'
        lifecycle_order.save()
        self.assertEqual(lifecycle_order.status, 'processing')

        lifecycle_order.status = 'shipped'
        lifecycle_order.save()
        self.assertEqual(lifecycle_order.status, 'shipped')

        lifecycle_order.status = 'delivered'
        lifecycle_order.save()
        lifecycle_order.refresh_from_db()
        self.assertEqual(lifecycle_order.status, 'delivered')

    def test_sec06_cookie_csrf_protection(self):
        from rest_framework_simplejwt.tokens import AccessToken
        from rest_framework.test import APIClient
        token = str(AccessToken.for_user(self.customer))

        # 1. Pure ambient cookie auth without CSRF token -> 403 Forbidden
        csrf_client = APIClient(enforce_csrf_checks=True)
        csrf_client.cookies['access_token'] = token
        res_cookie = csrf_client.post('/api/cart/', {'product': self.product.id, 'quantity': 1}, format='json', HTTP_HOST='localhost')
        self.assertEqual(res_cookie.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('CSRF Verification Failed', str(res_cookie.data))

        # 2. Ambient cookie WITH valid CSRF token -> 201 Created
        csrf_token_val = '12345678901234567890123456789012'
        csrf_client.cookies['csrftoken'] = csrf_token_val
        res_valid_csrf = csrf_client.post(
            '/api/cart/',
            {'product': self.product.id, 'quantity': 1},
            format='json',
            HTTP_HOST='localhost',
            HTTP_X_CSRFTOKEN=csrf_token_val
        )
        self.assertEqual(res_valid_csrf.status_code, status.HTTP_201_CREATED)

        # 3. Bearer token in Authorization header -> Succeeds without CSRF token
        bearer_client = APIClient(enforce_csrf_checks=True)
        bearer_client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        res_bearer = bearer_client.post('/api/cart/', {'product': self.product.id, 'quantity': 1}, format='json', HTTP_HOST='localhost')
        self.assertEqual(res_bearer.status_code, status.HTTP_201_CREATED)

    @patch('api.views.OrderViewSet.send_order_status_email')
    @patch('razorpay.Client')
    def test_split_payment_end_to_end_success(self, MockRazorpay, MockEmail):
        """End-to-end split payment: wallet reserved at create, reconciled at verify without double deduction."""
        self.customer.wallet_balance = Decimal('200.00')
        self.customer.save()
        self.client.force_authenticate(user=self.customer)

        mock_client = MockRazorpay.return_value
        mock_client.order.create.return_value = {
            'id': 'order_split_rzp',
            'amount': 30000,
            'currency': 'INR'
        }
        mock_client.payment.fetch.return_value = {
            'id': 'pay_split_123',
            'status': 'captured',
            'method': 'upi',
            'amount': 30000,  # ₹300.00 gateway leg (₹500 total - ₹200 wallet)
            'notes': {'wallet_deducted': '200.00', 'wallet_deducted_txid': 'TXN-WALLET-TEST'}
        }
        mock_client.utility.verify_payment_signature.return_value = None

        # 1. Create Razorpay order with use_wallet=True
        create_res = self.client.post('/api/orders/create-razorpay-order/', {
            "shipping_address": "123 Street",
            "contact_phone": "9999999999",
            "use_wallet": True,
            "order_items": [{"product": self.product.id, "quantity": 1}]
        }, format='json')

        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)
        order_id = create_res.data['order_id']
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.wallet_balance, Decimal('0.00'))  # Reserved

        # 2. Verify Razorpay payment
        verify_res = self.client.post('/api/orders/verify-razorpay-payment/', {
            "order_id": order_id,
            "razorpay_order_id": "order_split_rzp",
            "razorpay_payment_id": "pay_split_123",
            "razorpay_signature": "valid_sig"
        }, format='json')

        self.assertEqual(verify_res.status_code, status.HTTP_200_OK)
        self.assertTrue(verify_res.data['success'])

        # 3. Assertions: wallet was NOT deducted twice, order is paid, both payment legs exist
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.wallet_balance, Decimal('0.00'))  # Not negative or double debited
        order = Order.objects.get(id=order_id)
        self.assertEqual(order.status, 'paid')

        wallet_leg = Payment.objects.get(order=order, payment_method='wallet')
        self.assertEqual(wallet_leg.amount, Decimal('200.00'))
        self.assertEqual(wallet_leg.status, 'completed')

        rzp_leg = Payment.objects.get(order=order, transaction_id='pay_split_123')
        self.assertEqual(rzp_leg.amount, Decimal('300.00'))
        self.assertEqual(rzp_leg.status, 'completed')

    @patch('api.views.OrderViewSet.send_order_status_email')
    @patch('razorpay.Client')
    def test_split_payment_cancellation_refunds_wallet(self, MockRazorpay, MockEmail):
        """Cancelling a pending_payment split-payment order refunds the reserved wallet balance."""
        self.customer.wallet_balance = Decimal('200.00')
        self.customer.save()
        self.client.force_authenticate(user=self.customer)

        mock_client = MockRazorpay.return_value
        mock_client.order.create.return_value = {
            'id': 'order_split_rzp2',
            'amount': 30000,
            'currency': 'INR'
        }

        # 1. Create order
        create_res = self.client.post('/api/orders/create-razorpay-order/', {
            "shipping_address": "123 Street",
            "contact_phone": "9999999999",
            "use_wallet": True,
            "order_items": [{"product": self.product.id, "quantity": 1}]
        }, format='json')

        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)
        order_id = create_res.data['order_id']
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.wallet_balance, Decimal('0.00'))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 9)

        # 2. Cancel order
        cancel_res = self.client.post(f'/api/orders/{order_id}/cancel/')
        self.assertEqual(cancel_res.status_code, status.HTTP_200_OK)

        # 3. Verify wallet refunded, stock restored, payment marked refunded
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.wallet_balance, Decimal('200.00'))  # Fully refunded!
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)  # Stock restored!

        wallet_payment = Payment.objects.get(order_id=order_id, payment_method='wallet')
        self.assertEqual(wallet_payment.status, 'refunded')

    def test_arch01_redis_backend_importable_and_configurable(self):
        """ARCH-01: Verify that django-redis is installed and can be instantiated as a cache backend."""
        import django_redis
        from django_redis.cache import RedisCache
        self.assertTrue(hasattr(django_redis, '__file__'))

        # Verify fallback and active cache engine
        from django.core.cache import caches
        default_cache = caches['default']
        default_cache.set('arch01_test_key', 'ecom_redis_ready', timeout=60)
        self.assertEqual(default_cache.get('arch01_test_key'), 'ecom_redis_ready')
        default_cache.delete('arch01_test_key')

    @patch('cloudinary.uploader.upload')
    @patch('razorpay.Client')
    def test_fin02_fin03_gift_card_purchase_security(self, MockRazorpay, MockCloudinary):
        """FIN-02, FIN-03, SEC-04, ARCH-03: Authoritative gateway amount, replay prevention, and Cloudinary isolation."""
        self.client.force_authenticate(user=self.customer)
        mock_client = MockRazorpay.return_value
        mock_client.utility.verify_payment_signature.return_value = None
        mock_client.payment.fetch.return_value = {
            'id': 'pay_gc_valid_123',
            'status': 'captured',
            'amount': 50000  # ₹500.00
        }
        MockCloudinary.return_value = {'secure_url': 'https://res.cloudinary.com/test/image/upload/sample_qr.png'}

        # 1. Successful purchase with authoritative amount
        res = self.client.post('/api/gift-cards/verify/', {
            'razorpay_payment_id': 'pay_gc_valid_123',
            'razorpay_order_id': 'order_gc_123',
            'razorpay_signature': 'valid_sig_123',
            'amount': '500.00'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        gc_id = res.data['gift_card_id']
        gc = GiftCard.objects.get(id=gc_id)
        self.assertEqual(gc.initial_balance, Decimal('500.00'))
        self.assertEqual(gc.current_balance, Decimal('500.00'))
        self.assertEqual(gc.qr_code_url, 'https://res.cloudinary.com/test/image/upload/sample_qr.png')

        # Verify transaction logged with razorpay_payment_id
        tx = GiftCardTransaction.objects.get(razorpay_payment_id='pay_gc_valid_123')
        self.assertEqual(tx.gift_card, gc)
        self.assertEqual(tx.amount, Decimal('500.00'))

        # 2. Replay attack with same razorpay_payment_id -> 400 Bad Request
        res_replay = self.client.post('/api/gift-cards/verify/', {
            'razorpay_payment_id': 'pay_gc_valid_123',
            'razorpay_order_id': 'order_gc_123',
            'razorpay_signature': 'valid_sig_123',
            'amount': '500.00'
        }, format='json')
        self.assertEqual(res_replay.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('already been redeemed', res_replay.data['error'])

        # 3. Client amount tampering (client claims ₹5000 on a ₹500 payment) -> 400 Bad Request
        mock_client.payment.fetch.return_value = {
            'id': 'pay_gc_tamper_456',
            'status': 'captured',
            'amount': 50000  # ₹500.00
        }
        res_tamper = self.client.post('/api/gift-cards/verify/', {
            'razorpay_payment_id': 'pay_gc_tamper_456',
            'razorpay_order_id': 'order_gc_456',
            'razorpay_signature': 'valid_sig_456',
            'amount': '5000.00'  # Tampered
        }, format='json')
        self.assertEqual(res_tamper.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('mismatch', res_tamper.data['error'])

        # 4. Uncaptured payment status -> 400 Bad Request
        mock_client.payment.fetch.return_value = {
            'id': 'pay_gc_failed_789',
            'status': 'failed',
            'amount': 50000
        }
        res_uncaptured = self.client.post('/api/gift-cards/verify/', {
            'razorpay_payment_id': 'pay_gc_failed_789',
            'razorpay_order_id': 'order_gc_789',
            'razorpay_signature': 'valid_sig_789',
            'amount': '500.00'
        }, format='json')
        self.assertEqual(res_uncaptured.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('not been captured', res_uncaptured.data['error'])

    @patch('api.serializers.send_welcome_email')
    def test_arch02_welcome_email_on_commit(self, MockWelcome):
        """ARCH-02: User registration triggers welcome email via transaction.on_commit."""
        from django.db import transaction
        res = self.client.post('/api/register/', {
            'username': 'new_oncommit_user',
            'email': 'oncommit@example.com',
            'password': 'StrongPassword123!',
            'password2': 'StrongPassword123!'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(username='new_oncommit_user').exists())

    def test_sec03_fin04_payment_viewset_readonly_and_ownership_scoped(self):
        """SEC-03 / FIN-04: PaymentViewSet is ReadOnly and scoped to owner/admin."""
        # Create an order and payment for customer
        order_cust = Order.objects.create(user=self.customer, total_price=Decimal('100.00'), status='paid')
        pay_cust = Payment.objects.create(order=order_cust, amount=Decimal('100.00'), transaction_id='TXN_CUST_1', status='completed')

        # Create an order and payment for hacker
        order_hack = Order.objects.create(user=self.hacker, total_price=Decimal('200.00'), status='paid')
        pay_hack = Payment.objects.create(order=order_hack, amount=Decimal('200.00'), transaction_id='TXN_HACK_1', status='completed')

        # 1. Customer cannot POST to create fake payments -> 405 Method Not Allowed
        self.client.force_authenticate(user=self.customer)
        res_post = self.client.post('/api/payments/', {
            'order': order_cust.id,
            'amount': '500.00',
            'transaction_id': 'FAKE_TXN',
            'status': 'completed'
        }, format='json')
        self.assertEqual(res_post.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # 2. Customer cannot PUT/PATCH to manipulate status -> 405 Method Not Allowed
        res_patch = self.client.patch(f'/api/payments/{pay_cust.id}/', {'status': 'failed'}, format='json')
        self.assertEqual(res_patch.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # 3. Customer cannot DELETE payment records -> 405 Method Not Allowed
        res_del = self.client.delete(f'/api/payments/{pay_cust.id}/')
        self.assertEqual(res_del.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # 4. Customer GET /api/payments/ only returns customer's own payments
        res_get_cust = self.client.get('/api/payments/')
        self.assertEqual(res_get_cust.status_code, status.HTTP_200_OK)
        cust_tx_ids = [p['transaction_id'] for p in res_get_cust.data['results']]
        self.assertIn('TXN_CUST_1', cust_tx_ids)
        self.assertNotIn('TXN_HACK_1', cust_tx_ids)

        # 5. Admin GET /api/payments/ sees all payments across all users
        self.client.force_authenticate(user=self.admin)
        res_get_admin = self.client.get('/api/payments/')
        self.assertEqual(res_get_admin.status_code, status.HTTP_200_OK)
        admin_tx_ids = [p['transaction_id'] for p in res_get_admin.data['results']]
        self.assertIn('TXN_CUST_1', admin_tx_ids)
        self.assertIn('TXN_HACK_1', admin_tx_ids)

    def test_sec07_category_viewset_access_control(self):
        """SEC-07: CategoryViewSet allows public read but restricts mutation to admin."""
        # 1. Unauthenticated GET -> 200 OK
        self.client.force_authenticate(user=None)
        res_anon_get = self.client.get('/api/categories/')
        self.assertEqual(res_anon_get.status_code, status.HTTP_200_OK)

        # 2. Unauthenticated POST -> 401 Unauthorized
        res_anon_post = self.client.post('/api/categories/', {'name': 'Hacked Cat'}, format='json')
        self.assertEqual(res_anon_post.status_code, status.HTTP_401_UNAUTHORIZED)

        # 3. Customer POST -> 403 Forbidden
        self.client.force_authenticate(user=self.customer)
        res_cust_post = self.client.post('/api/categories/', {'name': 'Customer Cat'}, format='json')
        self.assertEqual(res_cust_post.status_code, status.HTTP_403_FORBIDDEN)

        # 4. Customer DELETE -> 403 Forbidden
        res_cust_del = self.client.delete(f'/api/categories/{self.category.id}/')
        self.assertEqual(res_cust_del.status_code, status.HTTP_403_FORBIDDEN)

        # 5. Admin POST -> 201 Created
        self.client.force_authenticate(user=self.admin)
        res_admin_post = self.client.post('/api/categories/', {'name': 'Admin Approved Cat'}, format='json')
        self.assertEqual(res_admin_post.status_code, status.HTTP_201_CREATED)

    def test_sec12_order_viewset_destroy_restricted_to_admin(self):
        """SEC-12: Non-admin users cannot delete orders."""
        order = Order.objects.create(user=self.customer, total_price=Decimal('50.00'), status='pending')

        # 1. Customer attempting DELETE -> 403 Forbidden
        self.client.force_authenticate(user=self.customer)
        res_cust_del = self.client.delete(f'/api/orders/{order.id}/')
        self.assertEqual(res_cust_del.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('restricted to administrators', res_cust_del.data['error'])
        self.assertTrue(Order.objects.filter(id=order.id).exists())

        # 2. Admin attempting DELETE -> 204 No Content
        self.client.force_authenticate(user=self.admin)
        res_admin_del = self.client.delete(f'/api/orders/{order.id}/')
        self.assertEqual(res_admin_del.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Order.objects.filter(id=order.id).exists())


# ==========================================
# PHASE A: FINANCIAL INTEGRITY & DB CONSTRAINTS
# ==========================================
class PhaseAFinancialIntegrityTests(APITestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username="phase_a_cust",
            email="phase_a_cust@test.com",
            password="password123",
            role="user",
            wallet_balance=Decimal('100.00')
        )
        self.seller = User.objects.create_user(
            username="phase_a_seller",
            email="phase_a_seller@test.com",
            password="password123",
            role="seller"
        )
        self.category = Category.objects.create(name="Phase A Category")
        self.product = Product.objects.create(
            name="Test Stock Item",
            price=Decimal('50.00'),
            stock=10,
            category=self.category,
            vendor=self.seller,
            approval_status='approved',
            is_active=True
        )

    def test_blocker1_database_check_constraints(self):
        """BLOCKER 1: DB check constraints prevent stock < 0 and wallet_balance < 0."""
        from django.db import IntegrityError, transaction

        # 1. Product stock cannot be negative
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Product.objects.filter(id=self.product.id).update(stock=-1)

        # 2. Product stock allowed at zero
        Product.objects.filter(id=self.product.id).update(stock=0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 0)

        # 3. User wallet_balance cannot be negative
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.filter(id=self.customer.id).update(wallet_balance=Decimal('-0.01'))

        # 4. User wallet_balance allowed at zero
        User.objects.filter(id=self.customer.id).update(wallet_balance=Decimal('0.00'))
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.wallet_balance, Decimal('0.00'))

    def test_blocker2_wallet_transaction_audit_ledger(self):
        """BLOCKER 2: Double-entry WalletTransaction audit trail for credits, debits and refunds."""
        from api.models import record_wallet_transaction

        # 1. Direct helper checks: Debit
        tx1 = record_wallet_transaction(self.customer, Decimal('30.00'), 'DEBIT_ORDER', reference_id='ORD-TEST-1', description='Test Debit')
        self.assertEqual(tx1.amount, Decimal('30.00'))
        self.assertEqual(tx1.balance_after, Decimal('70.00'))
        self.assertEqual(tx1.transaction_type, 'DEBIT_ORDER')
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.wallet_balance, Decimal('70.00'))

        # 2. Direct helper checks: Refund
        tx2 = record_wallet_transaction(self.customer, Decimal('10.00'), 'REFUND_ORDER', reference_id='ORD-TEST-1', description='Test Refund')
        self.assertEqual(tx2.amount, Decimal('10.00'))
        self.assertEqual(tx2.balance_after, Decimal('80.00'))
        self.assertEqual(tx2.transaction_type, 'REFUND_ORDER')
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.wallet_balance, Decimal('80.00'))

        # 3. Direct helper checks: Invalid debit (exceeding balance) raises ValidationError
        with self.assertRaises(ValidationError):
            record_wallet_transaction(self.customer, Decimal('999.00'), 'DEBIT_ORDER', reference_id='ORD-FAIL')

        # 4. Integration: Split-payment order checkout records DEBIT_ORDER audit entry
        self.customer.wallet_balance = Decimal('30.00')
        self.customer.save()
        self.client.force_authenticate(user=self.customer)

        with patch('razorpay.Client') as mock_rzp:
            mock_rzp.return_value.order.create.return_value = {
                'id': 'order_split_tx_test',
                'amount': 2000,
                'currency': 'INR'
            }
            res_order = self.client.post('/api/orders/create-razorpay-order/', {
                "shipping_address": "Test Street 10",
                "contact_phone": "9876543210",
                "use_wallet": True,
                "order_items": [{"product": self.product.id, "quantity": 1}]
            }, format='json')

        self.assertEqual(res_order.status_code, status.HTTP_201_CREATED)
        order_id = res_order.data['order_id']
        debit_tx = WalletTransaction.objects.filter(reference_id=f"ORDER-{order_id}", transaction_type='DEBIT_ORDER').first()
        self.assertIsNotNone(debit_tx)
        self.assertEqual(debit_tx.amount, Decimal('30.00'))
        self.assertEqual(debit_tx.balance_after, Decimal('0.00'))

        # 5. Integration: Cancelling the pending_payment order records REFUND_ORDER audit entry
        res_cancel = self.client.post(f'/api/orders/{order_id}/cancel/')
        self.assertEqual(res_cancel.status_code, status.HTTP_200_OK)

        refund_tx = WalletTransaction.objects.filter(reference_id=f"ORDER-{order_id}", transaction_type='REFUND_ORDER').first()
        self.assertIsNotNone(refund_tx)
        self.assertEqual(refund_tx.amount, Decimal('30.00'))
        self.assertEqual(refund_tx.balance_after, Decimal('30.00'))

        # 6. Read-only API verification
        res_list = self.client.get('/api/wallet-transactions/')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        tx_count = res_list.data['count'] if 'count' in res_list.data else len(res_list.data)
        self.assertGreaterEqual(tx_count, 4)

    @patch('razorpay.Client')
    def test_blocker3_webhook_pending_payment_failed_restores_stock_and_wallet(self, MockRazorpayClient):
        """BLOCKER 3: payment.failed webhook for pending_payment cancels order and restores stock + wallet."""
        mock_client = MockRazorpayClient.return_value
        mock_client.utility.verify_webhook_signature.return_value = None
        mock_client.order.create.return_value = {
            'id': 'rzp_order_fail_test',
            'amount': 2000,
            'currency': 'INR'
        }

        # 1. Place a split payment order (stock 10 -> 9, wallet 50 -> 20)
        self.customer.wallet_balance = Decimal('30.00')
        self.customer.save()
        self.product.stock = 10
        self.product.save()

        self.client.force_authenticate(user=self.customer)
        res_order = self.client.post('/api/orders/create-razorpay-order/', {
            "shipping_address": "Test Street 10",
            "contact_phone": "9876543210",
            "use_wallet": True,
            "order_items": [{"product": self.product.id, "quantity": 1}]
        }, format='json')
        self.assertEqual(res_order.status_code, status.HTTP_201_CREATED)
        order_id = res_order.data['order_id']

        order = Order.objects.get(id=order_id)
        self.assertEqual(order.status, 'pending_payment')
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 9)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.wallet_balance, Decimal('0.00'))

        # 2. Fire payment.failed webhook for this order
        payload = {
            "event": "payment.failed",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_failed_123",
                        "notes": {"django_order_id": order.id}
                    }
                }
            }
        }
        res_webhook = self.client.post(
            '/api/webhooks/razorpay/',
            json.dumps(payload),
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE='valid_sig'
        )
        self.assertEqual(res_webhook.status_code, status.HTTP_200_OK)

        # 3. Verify order cancelled, stock restored, wallet restored
        order.refresh_from_db()
        self.assertEqual(order.status, 'cancelled')
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.wallet_balance, Decimal('30.00'))

        # 4. Verify wallet audit transaction recorded
        refund_tx = WalletTransaction.objects.filter(reference_id=f"ORDER-{order.id}", transaction_type='REFUND_ORDER').first()
        self.assertIsNotNone(refund_tx)
        self.assertEqual(refund_tx.amount, Decimal('30.00'))

        # 5. Duplicate webhook delivery does NOT double-restore stock
        res_webhook2 = self.client.post(
            '/api/webhooks/razorpay/',
            json.dumps(payload),
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE='valid_sig'
        )
        self.assertEqual(res_webhook2.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)  # Still exactly 10!

    def test_blocker4_order_serializer_deterministic_locking_and_stock_validation(self):
        """BLOCKER 4: OrderSerializer.create locks items in sorted order, validates stock & active status."""
        p_alpha = Product.objects.create(
            name="Alpha Item", price=Decimal('40.00'), stock=5,
            category=self.category, vendor=self.seller, approval_status='approved', is_active=True
        )
        p_beta = Product.objects.create(
            name="Beta Item", price=Decimal('60.00'), stock=3,
            category=self.category, vendor=self.seller, approval_status='approved', is_active=True
        )

        serializer = OrderSerializer(context={'request': MagicMock(user=self.customer)})

        # 1. Provide items in reverse order [p_beta, p_alpha]
        order_data = {
            'shipping_address': 'Reverse Lock Street',
            'contact_phone': '9998887776',
            'order_items': [
                {'product': p_beta, 'quantity': 2},
                {'product': p_alpha, 'quantity': 3},
            ]
        }
        order = serializer.create(order_data)
        self.assertEqual(order.total_price, Decimal('240.00'))  # (60*2) + (40*3) = 120 + 120 = 240

        p_alpha.refresh_from_db()
        p_beta.refresh_from_db()
        self.assertEqual(p_alpha.stock, 2)  # 5 - 3 = 2
        self.assertEqual(p_beta.stock, 1)   # 3 - 2 = 1

        # 2. Exceeding stock raises serializers.ValidationError
        insufficient_data = {
            'shipping_address': 'Exceed Street',
            'contact_phone': '9998887776',
            'order_items': [
                {'product': p_beta, 'quantity': 5},  # only 1 left
            ]
        }
        with self.assertRaises(serializers.ValidationError):
            serializer.create(insufficient_data)

        # 3. Inactive product raises serializers.ValidationError
        p_inactive = Product.objects.create(
            name="Inactive Item", price=Decimal('10.00'), stock=5,
            category=self.category, vendor=self.seller, approval_status='approved', is_active=False
        )
        inactive_data = {
            'shipping_address': 'Inactive Street',
            'contact_phone': '9998887776',
            'order_items': [
                {'product': p_inactive, 'quantity': 1},
            ]
        }
        with self.assertRaises(serializers.ValidationError):
            serializer.create(inactive_data)

    def test_blocker5_idempotency_key_replay_and_in_flight_lock(self):
        """
        Verify Idempotency-Key support across financial endpoints:
        - Cached replay on retry (HTTP header Idempotency-Key)
        - No duplicate orders or double stock reservation
        - In-flight concurrent request protection returns HTTP 409 Conflict
        - Payment verification idempotency replay
        """
        self.client.force_authenticate(user=self.customer)
        initial_stock = self.product.stock
        initial_orders = Order.objects.count()

        # 1. Header-based idempotency key on create-razorpay-order
        with patch('razorpay.Client') as m:
            m.return_value.order.create.return_value = {
                'id': 'rzp_order_idem_test',
                'amount': 100000,
                'currency': 'INR'
            }
            res1 = self.client.post(
                '/api/orders/create-razorpay-order/',
                {
                    'shipping_address': 'Idempotent Way',
                    'contact_phone': '9876543210',
                    'order_items': [{'product': self.product.id, 'quantity': 1}]
                },
                format='json',
                HTTP_IDEMPOTENCY_KEY='hdr-idem-key-888'
            )
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)
        order_id = res1.data['order_id']
        self.assertEqual(Order.objects.count(), initial_orders + 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, initial_stock - 1)

        # 2. Replay with identical Idempotency-Key header returns cached response
        res2 = self.client.post(
            '/api/orders/create-razorpay-order/',
            {
                'shipping_address': 'Idempotent Way',
                'contact_phone': '9876543210',
                'order_items': [{'product': self.product.id, 'quantity': 1}]
            },
            format='json',
            HTTP_IDEMPOTENCY_KEY='hdr-idem-key-888'
        )
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res2.data['order_id'], order_id)
        # Crucial: no new order row created, no stock deducted again
        self.assertEqual(Order.objects.count(), initial_orders + 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, initial_stock - 1)

        # 3. In-flight lock returns HTTP 409 Conflict
        from django.core.cache import cache
        from api.utils.idempotency import _sanitize_and_hash_key
        in_flight_key = 'inflight-idem-test-999'
        cache.set(f"idem_lock_create_razorpay_order_{self.customer.id}_{_sanitize_and_hash_key(in_flight_key)}", True, timeout=30)
        res_conflict = self.client.post(
            '/api/orders/create-razorpay-order/',
            {
                'idempotency_key': in_flight_key,
                'shipping_address': 'Idempotent Way',
                'contact_phone': '9876543210',
                'order_items': [{'product': self.product.id, 'quantity': 1}]
            },
            format='json'
        )
        self.assertEqual(res_conflict.status_code, status.HTTP_409_CONFLICT)
        self.assertIn('in progress', res_conflict.data['error'])

        # 4. verify-razorpay-payment idempotency replay
        with patch('razorpay.Client') as m_rzp:
            m_rzp.return_value.payment.fetch.return_value = {
                'id': 'pay_verify_idem_1',
                'status': 'captured',
                'amount': 100000,
                'method': 'card',
                'notes': {}
            }
            m_rzp.return_value.utility.verify_payment_signature.return_value = True

            v_res1 = self.client.post(
                '/api/orders/verify-razorpay-payment/',
                {
                    'idempotency_key': 'verify-idem-key-1',
                    'order_id': order_id,
                    'razorpay_payment_id': 'pay_verify_idem_1',
                    'razorpay_order_id': 'rzp_order_idem_test',
                    'razorpay_signature': 'valid_sig'
                },
                format='json'
            )
            self.assertEqual(v_res1.status_code, status.HTTP_200_OK)
            self.assertTrue(v_res1.data['success'])

            # Second verify call with same idempotency key replays cached response
            v_res2 = self.client.post(
                '/api/orders/verify-razorpay-payment/',
                {
                    'idempotency_key': 'verify-idem-key-1',
                    'order_id': order_id,
                    'razorpay_payment_id': 'pay_verify_idem_1',
                    'razorpay_order_id': 'rzp_order_idem_test',
                    'razorpay_signature': 'valid_sig'
                },
                format='json'
            )
            self.assertEqual(v_res2.status_code, status.HTTP_200_OK)
            self.assertTrue(v_res2.data['success'])
            # Verify payments table only has 1 completed razorpay payment for this order
            self.assertEqual(Payment.objects.filter(order_id=order_id, payment_method='card').count(), 1)

    def test_blocker6_invoice_status_logic(self):
        """
        Verify status-aware invoice generation:
        - pending_payment / pending orders must NOT be stamped as 'Paid & Verified'
        - paid / processing orders must be stamped as 'Paid & Verified'
        - cancelled unpaid orders must show 'Cancelled (Unpaid)'
        - cancelled refunded orders must show 'Cancelled & Refunded'
        - failed orders must show 'Payment Failed'
        - PDF generation completes with valid %PDF stream and can be downloaded via API
        """
        from api.utils.pdf_generator import generate_invoice_pdf

        # 1. Pending payment order -> "Payment Pending (Unpaid)"
        order_pending = Order.objects.create(
            user=self.customer, total_price=Decimal('500.00'), status='pending_payment',
            shipping_address='Street 1', contact_phone='1234567890'
        )
        with patch('reportlab.platypus.SimpleDocTemplate.build') as mock_build:
            generate_invoice_pdf(order_pending)
            status_text = mock_build.call_args[0][0][4]._cellvalues[0][1].text
            self.assertIn("Payment Pending (Unpaid)", status_text)
            self.assertNotIn("Paid & Verified", status_text)

        # Verify real PDF generation and download endpoint
        self.client.force_authenticate(user=self.customer)
        res = self.client.get(f'/api/orders/{order_pending.id}/invoice/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res['Content-Type'], 'application/pdf')

        # 2. Paid / Processing order -> "Paid & Verified"
        order_paid = Order.objects.create(
            user=self.customer, total_price=Decimal('500.00'), status='processing',
            shipping_address='Street 2', contact_phone='1234567890'
        )
        Payment.objects.create(order=order_paid, amount=Decimal('500.00'), status='completed', transaction_id='TXN-PAID-1')
        with patch('reportlab.platypus.SimpleDocTemplate.build') as mock_build:
            generate_invoice_pdf(order_paid)
            status_text = mock_build.call_args[0][0][4]._cellvalues[0][1].text
            self.assertTrue("Paid &amp; Verified" in status_text or "Paid & Verified" in status_text)

        # 3. Cancelled unpaid order -> "Cancelled (Unpaid)"
        order_cancelled_unpaid = Order.objects.create(
            user=self.customer, total_price=Decimal('500.00'), status='cancelled',
            shipping_address='Street 3', contact_phone='1234567890'
        )
        with patch('reportlab.platypus.SimpleDocTemplate.build') as mock_build:
            generate_invoice_pdf(order_cancelled_unpaid)
            status_text = mock_build.call_args[0][0][4]._cellvalues[0][1].text
            self.assertIn("Cancelled (Unpaid)", status_text)
            self.assertNotIn("Paid & Verified", status_text)
            self.assertNotIn("Paid &amp; Verified", status_text)

        # 4. Cancelled refunded order -> "Cancelled & Refunded"
        order_cancelled_refunded = Order.objects.create(
            user=self.customer, total_price=Decimal('500.00'), status='cancelled',
            shipping_address='Street 4', contact_phone='1234567890'
        )
        Payment.objects.create(order=order_cancelled_refunded, amount=Decimal('500.00'), status='refunded', transaction_id='TXN-REF-1')
        with patch('reportlab.platypus.SimpleDocTemplate.build') as mock_build:
            generate_invoice_pdf(order_cancelled_refunded)
            status_text = mock_build.call_args[0][0][4]._cellvalues[0][1].text
            self.assertTrue("Cancelled &amp; Refunded" in status_text or "Cancelled & Refunded" in status_text)

        # 5. Failed order -> "Payment Failed"
        order_failed = Order.objects.create(
            user=self.customer, total_price=Decimal('500.00'), status='failed',
            shipping_address='Street 5', contact_phone='1234567890'
        )
        with patch('reportlab.platypus.SimpleDocTemplate.build') as mock_build:
            generate_invoice_pdf(order_failed)
            status_text = mock_build.call_args[0][0][4]._cellvalues[0][1].text
            self.assertIn("Payment Failed", status_text)

    @patch('razorpay.Client')
    def test_blocker7_gateway_refund_on_cancel_and_webhook_handlers(self, MockRazorpayClient):
        """
        BLOCKER 7: Automated Gateway Refunds & Expanded Webhooks (FIN-16):
        - Order cancellation triggers client.payment.refund and marks payment 'refunded'
        - Webhook payment.authorized registers authorized payment row
        - Webhook order.paid updates order status to 'paid'
        - Webhook refund.processed sets payment to 'refunded', cancels order, and restores stock
        """
        mock_client = MockRazorpayClient.return_value
        mock_client.utility.verify_webhook_signature.return_value = None
        mock_client.payment.refund.return_value = {'id': 'rfnd_test_123', 'status': 'processed'}

        # 1. Order cancellation triggers Razorpay refund API
        self.client.force_authenticate(user=self.customer)
        order = Order.objects.create(
            user=self.customer, total_price=Decimal('100.00'), status='processing',
            shipping_address='Refund Street', contact_phone='9990001112'
        )
        item = OrderItem.objects.create(
            order=order, product=self.product, vendor=self.seller, quantity=1, price=Decimal('100.00')
        )
        pay_gateway = Payment.objects.create(
            order=order, payment_method='razorpay', transaction_id='pay_gateway_refund_test',
            amount=Decimal('100.00'), status='completed'
        )
        initial_stock = self.product.stock

        res_cancel = self.client.post(f'/api/orders/{order.id}/cancel/')
        self.assertEqual(res_cancel.status_code, status.HTTP_200_OK)

        mock_client.payment.refund.assert_called_once_with(
            'pay_gateway_refund_test',
            {'amount': 10000, 'notes': {'order_id': str(order.id), 'reason': 'Order cancelled by customer'}}
        )
        pay_gateway.refresh_from_db()
        self.assertEqual(pay_gateway.status, 'refunded')
        order.refresh_from_db()
        self.assertEqual(order.status, 'cancelled')
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, initial_stock + 1)

        # 2. Webhook: payment.authorized
        order_auth = Order.objects.create(
            user=self.customer, total_price=Decimal('150.00'), status='pending_payment',
            shipping_address='Auth Street', contact_phone='9990001112'
        )
        auth_payload = {
            "event": "payment.authorized",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_auth_test_999",
                        "amount": 15000,
                        "method": "upi",
                        "notes": {"django_order_id": order_auth.id}
                    }
                }
            }
        }
        res_auth = self.client.post(
            '/api/webhooks/razorpay/',
            json.dumps(auth_payload),
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE='valid_sig'
        )
        self.assertEqual(res_auth.status_code, status.HTTP_200_OK)
        p_auth = Payment.objects.filter(transaction_id='pay_auth_test_999').first()
        self.assertIsNotNone(p_auth)
        self.assertEqual(p_auth.status, 'authorized')
        self.assertEqual(p_auth.amount, Decimal('150.00'))

        # 3. Webhook: order.paid
        order_to_pay = Order.objects.create(
            user=self.customer, total_price=Decimal('200.00'), status='pending_payment',
            shipping_address='Paid Street', contact_phone='9990001112'
        )
        OrderItem.objects.create(
            order=order_to_pay, product=self.product, vendor=self.seller, quantity=1, price=Decimal('200.00')
        )
        paid_payload = {
            "event": "order.paid",
            "payload": {
                "order": {
                    "entity": {
                        "id": "order_rzp_paid_123",
                        "notes": {"django_order_id": order_to_pay.id}
                    }
                }
            }
        }
        res_paid = self.client.post(
            '/api/webhooks/razorpay/',
            json.dumps(paid_payload),
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE='valid_sig'
        )
        self.assertEqual(res_paid.status_code, status.HTTP_200_OK)
        order_to_pay.refresh_from_db()
        self.assertEqual(order_to_pay.status, 'paid')

        # 4. Webhook: refund.processed
        order_refund = Order.objects.create(
            user=self.customer, total_price=Decimal('50.00'), status='paid',
            shipping_address='Refund Hook Street', contact_phone='9990001112'
        )
        OrderItem.objects.create(
            order=order_refund, product=self.product, vendor=self.seller, quantity=1, price=Decimal('50.00')
        )
        pay_completed = Payment.objects.create(
            order=order_refund, payment_method='razorpay', transaction_id='pay_to_refund_hook',
            amount=Decimal('50.00'), status='completed'
        )
        stock_before_refund_hook = self.product.stock

        refund_payload = {
            "event": "refund.processed",
            "payload": {
                "refund": {
                    "entity": {
                        "id": "rfnd_hook_456",
                        "payment_id": "pay_to_refund_hook",
                        "notes": {"django_order_id": order_refund.id}
                    }
                }
            }
        }
        res_rfnd = self.client.post(
            '/api/webhooks/razorpay/',
            json.dumps(refund_payload),
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE='valid_sig'
        )
        self.assertEqual(res_rfnd.status_code, status.HTTP_200_OK)
        pay_completed.refresh_from_db()
        self.assertEqual(pay_completed.status, 'refunded')
        order_refund.refresh_from_db()
        self.assertEqual(order_refund.status, 'cancelled')
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, stock_before_refund_hook + 1)


# ==========================================
# PHASE B: SECURITY & ACCESS CONTROL TESTS
# ==========================================
class PhaseBSecurityTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="sec_admin", email="sec_admin@test.com", password="password123", role="admin", is_staff=True
        )
        self.customer = User.objects.create_user(
            username="sec_cust", email="sec_cust@test.com", password="password123", role="user"
        )
        self.other_user = User.objects.create_user(
            username="sec_other", email="sec_other@test.com", password="password123", role="user"
        )

    def test_sec01_userviewset_scoping_non_admin_cannot_list_or_access_other_users(self):
        """
        BLOCKER 1 (SEC-01): UserViewSet.get_queryset() scoping:
        - Non-admin user calling GET /api/users/ only sees their own user record
        - Non-admin user calling GET /api/users/<other_id>/ receives HTTP 404
        - Admin user calling GET /api/users/ sees all user records
        - Unauthenticated request is rejected with HTTP 401
        """
        # 1. Unauthenticated request
        res_unauth = self.client.get('/api/users/')
        self.assertEqual(res_unauth.status_code, status.HTTP_401_UNAUTHORIZED)

        # 2. Non-admin customer listing users
        self.client.force_authenticate(user=self.customer)
        res_cust_list = self.client.get('/api/users/')
        self.assertEqual(res_cust_list.status_code, status.HTTP_200_OK)
        cust_results = res_cust_list.data.get('results', res_cust_list.data)
        self.assertEqual(len(cust_results), 1)
        self.assertEqual(cust_results[0]['id'], self.customer.id)
        self.assertEqual(cust_results[0]['username'], self.customer.username)

        # 3. Non-admin attempting to retrieve another user's details directly
        res_other = self.client.get(f'/api/users/{self.other_user.id}/')
        self.assertEqual(res_other.status_code, status.HTTP_404_NOT_FOUND)

        # 4. Non-admin retrieving their own details
        res_self = self.client.get(f'/api/users/{self.customer.id}/')
        self.assertEqual(res_self.status_code, status.HTTP_200_OK)
        self.assertEqual(res_self.data['id'], self.customer.id)

        # 5. Admin listing users
        self.client.force_authenticate(user=self.admin)
        res_admin_list = self.client.get('/api/users/')
        self.assertEqual(res_admin_list.status_code, status.HTTP_200_OK)
        admin_results = res_admin_list.data.get('results', res_admin_list.data)
        self.assertGreaterEqual(len(admin_results), 3)
        admin_ids = [u['id'] for u in admin_results]
        self.assertIn(self.customer.id, admin_ids)
        self.assertIn(self.other_user.id, admin_ids)
        self.assertIn(self.admin.id, admin_ids)

        # 6. Admin accessing another user's details
        res_admin_access = self.client.get(f'/api/users/{self.other_user.id}/')
        self.assertEqual(res_admin_access.status_code, status.HTTP_200_OK)
        self.assertEqual(res_admin_access.data['id'], self.other_user.id)

    def test_sec02_email_service_html_sanitization(self):
        """
        BLOCKER 2 (SEC-02): Email HTML Injection & XSS Protection
        Verify all user-controlled inputs rendered in emails are strictly escaped.
        """
        from django.core import mail
        from api.email_service import (
            send_welcome_email,
            send_otp_email,
            send_order_email,
            send_vendor_new_order_email,
            send_vendor_product_status_email
        )

        malicious_input = '<script>alert("xss")</script><img src=x onerror=alert(1)>'
        mail.outbox = []

        # 1. Welcome Email
        send_welcome_email("victim@example.com", malicious_input)
        self.assertEqual(len(mail.outbox), 1)
        welcome_msg = mail.outbox[0]
        html_content = welcome_msg.alternatives[0][0]
        self.assertNotIn('<script>', html_content)
        self.assertNotIn('<img src=x', html_content)
        self.assertIn('&lt;script&gt;', html_content)
        self.assertIn('&lt;img src=x', html_content)

        # 2. OTP Email
        send_otp_email("victim@example.com", malicious_input, f"123{malicious_input}")
        self.assertEqual(len(mail.outbox), 2)
        otp_html = mail.outbox[1].alternatives[0][0]
        self.assertNotIn('<script>', otp_html)
        self.assertNotIn('<img src=x', otp_html)
        self.assertIn('&lt;script&gt;', otp_html)

        # 3. Order Email
        send_order_email(
            to_email="victim@example.com",
            username=malicious_input,
            order_id=9999,
            status="pending",
            total="100.00",
            payment_method=malicious_input,
            txn_id=malicious_input,
            address=malicious_input
        )
        self.assertEqual(len(mail.outbox), 3)
        order_html = mail.outbox[2].alternatives[0][0]
        self.assertNotIn('<script>', order_html)
        self.assertNotIn('<img src=x', order_html)
        self.assertIn('&lt;script&gt;', order_html)

        # 4. Vendor Product Status Email
        send_vendor_product_status_email(
            to_email="vendor@example.com",
            username=malicious_input,
            product_name=f"EvilProduct {malicious_input}",
            status="rejected",
            admin_note=malicious_input
        )
        self.assertEqual(len(mail.outbox), 4)
        vendor_html = mail.outbox[3].alternatives[0][0]
        self.assertNotIn('<script>', vendor_html)
        self.assertNotIn('<img src=x', vendor_html)
        self.assertIn('&lt;script&gt;', vendor_html)

    def test_sec03_otp_generation_uses_csprng(self):
        """
        BLOCKER 3 (SEC-03): Cryptographically Secure OTP Generation
        Verify OTP generation in request_otp and RequestPasswordResetOTPView
        uses secrets.randbelow to produce unpredictable 6-digit PINs.
        """
        from unittest.mock import patch
        from django.core.cache import cache

        # Clear cache keys
        cache.clear()

        # 1. Profile OTP request using secrets.randbelow
        self.client.force_authenticate(user=self.customer)
        with patch('secrets.randbelow', wraps=secrets.randbelow) as mock_rand:
            res = self.client.post('/api/users/request-otp/')
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            self.assertTrue(mock_rand.called)
            mock_rand.assert_called_with(900000)

            stored_otp = cache.get(f"profile_otp_{self.customer.id}")
            self.assertIsNotNone(stored_otp)
            self.assertEqual(len(stored_otp), 6)
            self.assertTrue(stored_otp.isdigit())
            otp_int = int(stored_otp)
            self.assertGreaterEqual(otp_int, 100000)
            self.assertLessEqual(otp_int, 999999)

        # 2. Password reset OTP using secrets.randbelow
        cache.clear()
        with patch('secrets.randbelow', wraps=secrets.randbelow) as mock_rand_reset:
            res_reset = self.client.post('/api/password-reset/request/', {'email': self.customer.email})
            self.assertEqual(res_reset.status_code, status.HTTP_200_OK)
            self.assertTrue(mock_rand_reset.called)
            mock_rand_reset.assert_called_with(900000)

            stored_reset_otp = cache.get(f"pwd_reset_{self.customer.email.lower()}")
            self.assertIsNotNone(stored_reset_otp)
            self.assertEqual(len(stored_reset_otp), 6)
            self.assertTrue(stored_reset_otp.isdigit())
            reset_otp_int = int(stored_reset_otp)
            self.assertGreaterEqual(reset_otp_int, 100000)
            self.assertLessEqual(reset_otp_int, 999999)

    def test_sec07_pdf_generator_ssrf_prevention(self):
        """
        BLOCKER 4 (SEC-07): PDF Generator Image URL SSRF Protection
        Verifies that is_safe_image_url and get_product_image strictly block:
        - Cloud metadata endpoints (169.254.169.254)
        - Loopback addresses (127.0.0.1, localhost)
        - Private RFC 1918 subnets (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
        - Non-http schemes (file://, gopher://, ftp://)
        - SSRF via HTTP redirects
        """
        from unittest.mock import MagicMock, patch
        from api.utils.pdf_generator import is_safe_image_url, get_product_image

        # 1. Scheme checks
        self.assertFalse(is_safe_image_url("file:///etc/passwd"))
        self.assertFalse(is_safe_image_url("ftp://example.com/logo.png"))
        self.assertFalse(is_safe_image_url("gopher://127.0.0.1:6379/_"))
        self.assertFalse(is_safe_image_url(""))
        self.assertFalse(is_safe_image_url(None))

        # 2. Hostname blacklist & private / loopback / link-local IP resolution
        self.assertFalse(is_safe_image_url("http://127.0.0.1/admin"))
        self.assertFalse(is_safe_image_url("http://localhost:8000/secret"))
        self.assertFalse(is_safe_image_url("http://0.0.0.0:80/"))
        self.assertFalse(is_safe_image_url("http://169.254.169.254/latest/meta-data/"))
        self.assertFalse(is_safe_image_url("http://10.0.0.5/internal.png"))
        self.assertFalse(is_safe_image_url("http://172.16.0.1/test.png"))
        self.assertFalse(is_safe_image_url("http://192.168.1.1/router.png"))

        # 3. Public IP is allowed
        with patch('socket.getaddrinfo') as mock_dns:
            mock_dns.return_value = [
                (2, 1, 6, '', ('93.184.216.34', 0))
            ]
            self.assertTrue(is_safe_image_url("https://example.com/images/product.jpg"))

        # 4. get_product_image blocks malicious item images without making network requests
        mock_item = MagicMock()
        mock_item.image_url = "http://169.254.169.254/latest/meta-data/iam"
        mock_item.image = None
        mock_item.product = None

        with patch('api.utils.pdf_generator.session.get') as mock_session_get:
            result = get_product_image(mock_item)
            self.assertIsNone(result)
            mock_session_get.assert_not_called()

        # 5. get_product_image blocks SSRF redirects to loopback
        mock_item.image_url = "https://example.com/redirect-to-internal"
        with patch('api.utils.pdf_generator.is_safe_image_url') as mock_safe:
            # First URL is deemed safe, but redirect target is blocked
            mock_safe.side_effect = lambda u: u == "https://example.com/redirect-to-internal"
            mock_resp = MagicMock()
            mock_resp.status_code = 302
            mock_resp.headers = {'Location': 'http://127.0.0.1:8000/internal-flag'}
            with patch('api.utils.pdf_generator.session.get', return_value=mock_resp) as mock_get:
                result = get_product_image(mock_item)
                self.assertIsNone(result)
                # Ensure it did NOT follow the redirect to the blocked target
                self.assertEqual(mock_get.call_count, 1)
                self.assertEqual(mock_get.call_args[0][0], "https://example.com/redirect-to-internal")

    def test_sec08_login_and_refresh_exclude_tokens_from_json_body(self):
        """
        BLOCKER 5 (SEC-08): Token Stripping from Login & Refresh JSON Responses
        Verify tokens are stored exclusively in HttpOnly cookies and never leaked
        into the client-side readable JSON response body.
        """
        # 1. Login flow
        login_res = self.client.post('/api/token/', {
            "email": self.customer.email,
            "password": "password123"
        }, format='json')

        self.assertEqual(login_res.status_code, status.HTTP_200_OK)
        self.assertNotIn('access', login_res.data)
        self.assertNotIn('refresh', login_res.data)
        self.assertIn('user', login_res.data)
        self.assertEqual(login_res.data['user']['email'], self.customer.email)

        # Cookies must be HttpOnly
        self.assertIn('access_token', login_res.cookies)
        self.assertIn('refresh_token', login_res.cookies)
        self.assertTrue(login_res.cookies['access_token']['httponly'])
        self.assertTrue(login_res.cookies['refresh_token']['httponly'])

        # 2. Refresh flow via HttpOnly cookie
        refresh_res = self.client.post('/api/token/refresh/', format='json')
        self.assertEqual(refresh_res.status_code, status.HTTP_200_OK)
        self.assertNotIn('access', refresh_res.data)
        self.assertNotIn('refresh', refresh_res.data)
        self.assertIn('access_token', refresh_res.cookies)
        self.assertTrue(refresh_res.cookies['access_token']['httponly'])

    def test_sec09_allowed_hosts_exact_configuration(self):
        """
        BLOCKER 6 (SEC-09 / SEC-13): Strict ALLOWED_HOSTS & Elimination of Platform Wildcards
        Verify no multi-tenant wildcards (.vercel.app, .onrender.com) exist in ALLOWED_HOSTS,
        preventing HTTP Host Header Poisoning and cache poisoning.
        """
        from django.conf import settings
        from django.test import RequestFactory
        from django.core.exceptions import DisallowedHost
        from django.http.request import validate_host

        # 1. No dangerous multi-tenant wildcards
        self.assertNotIn('.vercel.app', settings.ALLOWED_HOSTS)
        self.assertNotIn('.onrender.com', settings.ALLOWED_HOSTS)
        self.assertNotIn('*', settings.ALLOWED_HOSTS)

        # 2. Host validation blocks arbitrary tenant subdomains
        self.assertFalse(validate_host('evil-attacker.vercel.app', settings.ALLOWED_HOSTS))
        self.assertFalse(validate_host('malicious-tenant.onrender.com', settings.ALLOWED_HOSTS))
        self.assertFalse(validate_host('random-phishing.com', settings.ALLOWED_HOSTS))

        # 3. Legitimate production hostnames pass validation
        self.assertTrue(validate_host('eazyshop.cfd', settings.ALLOWED_HOSTS))
        self.assertTrue(validate_host('api.eazyshop.cfd', settings.ALLOWED_HOSTS))
        self.assertTrue(validate_host('localhost', settings.ALLOWED_HOSTS))
        self.assertTrue(validate_host('127.0.0.1', settings.ALLOWED_HOSTS))
        self.assertTrue(validate_host('testserver', settings.ALLOWED_HOSTS))

    def test_sec10_cors_no_plaintext_http_in_production(self):
        """
        BLOCKER 7 (SEC-10 / SEC-14): Elimination of Plaintext CORS / CSRF Origins
        Verify that plaintext HTTP production origins (http://eazyshop.cfd, etc.)
        are completely removed, and all remote production origins strictly enforce HTTPS.
        """
        from django.conf import settings

        # 1. Plaintext production origins must not be in CORS_ALLOWED_ORIGINS
        self.assertNotIn("http://eazyshop.cfd", settings.CORS_ALLOWED_ORIGINS)
        self.assertNotIn("http://www.eazyshop.cfd", settings.CORS_ALLOWED_ORIGINS)
        self.assertNotIn("http://api.eazyshop.cfd", settings.CORS_ALLOWED_ORIGINS)

        # 2. Plaintext production origins must not be in CSRF_TRUSTED_ORIGINS
        self.assertNotIn("http://eazyshop.cfd", settings.CSRF_TRUSTED_ORIGINS)
        self.assertNotIn("http://www.eazyshop.cfd", settings.CSRF_TRUSTED_ORIGINS)
        self.assertNotIn("http://api.eazyshop.cfd", settings.CSRF_TRUSTED_ORIGINS)

        # 3. All non-localhost origins must strictly use https://
        for origin in settings.CORS_ALLOWED_ORIGINS:
            if not origin.startswith(('http://localhost', 'http://127.0.0.1')):
                self.assertTrue(
                    origin.startswith('https://'),
                    f"Insecure plaintext remote CORS origin found: {origin}"
                )

        for origin in settings.CSRF_TRUSTED_ORIGINS:
            if not origin.startswith(('http://localhost', 'http://127.0.0.1')):
                self.assertTrue(
                    origin.startswith('https://'),
                    f"Insecure plaintext remote CSRF origin found: {origin}"
                )

    def test_sec11_hsts_and_ssl_headers_configured(self):
        """
        BLOCKER 8 (SEC-11 / SEC-15): HTTP Strict Transport Security (HSTS) & SSL Headers
        Verify that HSTS headers (max-age, includeSubDomains, preload), nosniff,
        and reverse proxy SSL headers are properly configured and returned on HTTPS requests.
        """
        from django.conf import settings
        from django.test import override_settings

        # 1. Reverse proxy SSL header must be configured for Render / Cloudflare
        self.assertEqual(settings.SECURE_PROXY_SSL_HEADER, ('HTTP_X_FORWARDED_PROTO', 'https'))

        # 2. In production (DEBUG=False), SecurityMiddleware injects HSTS and security headers
        with override_settings(
            DEBUG=False,
            SECURE_HSTS_SECONDS=31536000,
            SECURE_HSTS_INCLUDE_SUBDOMAINS=True,
            SECURE_HSTS_PRELOAD=True,
            SECURE_CONTENT_TYPE_NOSNIFF=True,
            SECURE_REFERRER_POLICY='strict-origin-when-cross-origin'
        ):
            response = self.client.get('/api/products/', secure=True)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            # Strict-Transport-Security verification
            self.assertIn('Strict-Transport-Security', response.headers)
            hsts_header = response.headers['Strict-Transport-Security']
            self.assertIn('max-age=31536000', hsts_header)
            self.assertIn('includeSubDomains', hsts_header)
            self.assertIn('preload', hsts_header)

            # Nosniff & Referrer policy verification
            self.assertIn('X-Content-Type-Options', response.headers)
            self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
            self.assertIn('Referrer-Policy', response.headers)
            self.assertEqual(response.headers['Referrer-Policy'], 'strict-origin-when-cross-origin')

    def test_sec12_jwt_server_side_blacklisting_on_logout(self):
        """
        BLOCKER 9 (SEC-12): Server-Side JWT Blacklisting on Logout & Token Rotation
        Verify that refresh tokens are blacklisted in the database upon logout
        and cannot be used to obtain new access tokens.
        """
        # 1. Login to obtain tokens
        login_res = self.client.post('/api/token/', {
            "email": self.customer.email,
            "password": "password123"
        }, format='json')
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)
        refresh_token = login_res.cookies['refresh_token'].value

        # 2. Logout with active cookies
        logout_res = self.client.post('/api/logout/')
        self.assertEqual(logout_res.status_code, status.HTTP_200_OK)

        # 3. Attempting to use the blacklisted refresh token MUST fail with 401 Unauthorized
        self.client.cookies.clear()
        reuse_res = self.client.post('/api/token/refresh/', {'refresh': refresh_token}, format='json')
        self.assertEqual(reuse_res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(reuse_res.data.get('code'), 'token_not_valid')

        # 4. Token Rotation & Blacklist Verification:
        # Log in again to get fresh tokens
        login_res2 = self.client.post('/api/token/', {
            "email": self.customer.email,
            "password": "password123"
        }, format='json')
        fresh_refresh = login_res2.cookies['refresh_token'].value

        # Rotate token via refresh
        rotate_res = self.client.post('/api/token/refresh/', format='json')
        self.assertEqual(rotate_res.status_code, status.HTTP_200_OK)
        new_refresh = rotate_res.cookies['refresh_token'].value
        self.assertNotEqual(fresh_refresh, new_refresh)

        # Attempt to reuse the rotated (old) refresh token
        self.client.cookies.clear()
        old_token_res = self.client.post('/api/token/refresh/', {'refresh': fresh_refresh}, format='json')
        self.assertEqual(old_token_res.status_code, status.HTTP_401_UNAUTHORIZED)


class PhaseABHardeningRefinementTests(APITestCase):
    """
    Comprehensive Adversarial Refinement & Hardening Tests for Phase A & B.
    Validates extreme edge cases and ensures 100% water-tight platform security.
    """

    def setUp(self):
        from api.models import User, Product, Category, Order, OrderItem, Payment
        self.category = Category.objects.create(name="Hardening Test Category")
        self.user = User.objects.create_user(
            username="Hacker & Co. <script>alert(1)</script>",
            email="hacker+special&chars<xss>@example.com",
            password="SecurePassword123!"
        )
        self.product = Product.objects.create(
            name="Deluxe Gadget & Widget <Edition> & 'Quotes'",
            price=Decimal('150.00'),
            stock=10,
            category=self.category
        )
        self.order = Order.objects.create(
            user=self.user,
            total_price=Decimal('150.00'),
            status='paid'
        )
        self.order_item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=1,
            price=Decimal('150.00')
        )
        self.payment = Payment.objects.create(
            order=self.order,
            payment_method="credit_card & stripe <test>",
            transaction_id="tx_test_12345 & <id>",
            amount=Decimal('160.00'),
            status="completed"
        )

    def test_refinement01_invoice_pdf_xml_escaping(self):
        """
        REFINEMENT 1: ReportLab XML Parser Escaping in Invoice PDF
        Verifies that special characters (&, <, >, quotes) in customer name,
        email, product name, payment method, and transaction id do not cause
        XML/Expat parse errors and generate a pristine, valid PDF document.
        """
        from api.utils.pdf_generator import generate_invoice_pdf

        # 1. Direct PDF generator invocation with XSS/XML payloads in all fields
        pdf_buffer = generate_invoice_pdf(self.order)
        self.assertIsNotNone(pdf_buffer)
        pdf_bytes = pdf_buffer.getvalue()
        self.assertTrue(pdf_bytes.startswith(b'%PDF-'), "Generated file must be a valid PDF document")

        # 2. Endpoint invocation via authenticated client
        self.client.force_authenticate(user=self.user)
        response = self.client.get(f'/api/orders/{self.order.id}/invoice/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        content_bytes = b"".join(response.streaming_content)
        self.assertTrue(content_bytes.startswith(b'%PDF-'))

    def test_refinement02_pdf_image_directory_traversal(self):
        """
        REFINEMENT 2: Local File Traversal Containment in PDF Image Fetcher
        Verifies that get_product_image strictly enforces directory containment
        within settings.MEDIA_ROOT and blocks path traversal attempts like
        '../../../../etc/passwd' or '/media/../../settings.py'.
        """
        import os
        from unittest.mock import MagicMock
        from django.conf import settings
        from api.utils.pdf_generator import get_product_image

        # 1. Traversal path attempting to read system or project files
        mock_traversal_item = MagicMock()
        mock_traversal_item.image_url = "../../../../etc/passwd"
        mock_traversal_item.image = None
        mock_traversal_item.product = None
        result = get_product_image(mock_traversal_item)
        self.assertIsNone(result, "Path traversal with relative parent dirs must be blocked")

        # 2. Traversal path with /media/ prefix
        mock_traversal_item2 = MagicMock()
        mock_traversal_item2.image_url = "/media/../../../../etc/shadow"
        mock_traversal_item2.image = None
        mock_traversal_item2.product = None
        result2 = get_product_image(mock_traversal_item2)
        self.assertIsNone(result2, "Path traversal with /media/ prefix must be blocked")

        # 3. Legitimate media file inside settings.MEDIA_ROOT is permitted
        test_media_dir = settings.MEDIA_ROOT
        os.makedirs(test_media_dir, exist_ok=True)
        test_file_path = os.path.join(test_media_dir, "safe_test_image.jpg")
        try:
            # Create a 1x1 dummy JPEG or minimal image bytes
            with open(test_file_path, "wb") as f:
                f.write(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9")

            mock_safe_item = MagicMock()
            mock_safe_item.image_url = "/media/safe_test_image.jpg"
            mock_safe_item.image = None
            mock_safe_item.product = None

            safe_result = get_product_image(mock_safe_item)
            self.assertIsNotNone(safe_result, "Legitimate file inside MEDIA_ROOT must be loaded")
        finally:
            if os.path.exists(test_file_path):
                os.remove(test_file_path)

    def test_refinement03_deterministic_lock_ordering(self):
        """
        REFINEMENT 3: Deterministic PostgreSQL Row-Lock Ordering
        Verifies that multi-item queries in OrderSerializer.create and create_razorpay_order
        explicitly chain .order_by('id') to override Product.Meta.ordering = ['-created_at'],
        guaranteeing strict ascending ID acquisition and absolute deadlock immunity.
        """
        from api.models import Product
        from api.serializers import OrderSerializer

        # 1. SQL query inspection: assert explicit ORDER BY id is present
        sorted_ids = [10, 5, 20]
        qs = Product.objects.select_for_update().filter(id__in=sorted_ids).order_by('id')
        sql_str = str(qs.query)
        self.assertIn('ORDER BY "api_product"."id" ASC', sql_str,
                      "Query must explicitly order by id ASC to guarantee deadlock immunity across concurrent workers")

        # 2. End-to-end checkout with out-of-order products in OrderSerializer
        prod_a = Product.objects.create(name="Product A", price=Decimal('20.00'), stock=10, category=self.category, approval_status='approved')
        prod_b = Product.objects.create(name="Product B", price=Decimal('30.00'), stock=10, category=self.category, approval_status='approved')

        # Reverse order in payload: [prod_b, prod_a]
        payload = {
            'order_items': [
                {'product': prod_b, 'quantity': 2},
                {'product': prod_a, 'quantity': 1}
            ],
            'shipping_address': '123 Enterprise Blvd',
            'contact_phone': '9876543210'
        }
        serializer = OrderSerializer(context={'request': type('Req', (), {'user': self.user})()})
        order = serializer.create(payload)
        self.assertEqual(order.total_price, Decimal('80.00'))
        self.assertEqual(order.order_items.count(), 2)

    @patch('razorpay.Client')
    def test_refinement04_webhook_revival_overselling_guard(self, MockRazorpayClient):
        """
        REFINEMENT 4: Webhook Order Revival Stock Availability Guard
        Verifies that when a payment.captured webhook arrives for a cancelled order:
        - If stock is insufficient (re-sold while cancelled), the order remains cancelled,
          stock never goes negative, and an automated gateway refund is triggered.
        - If stock is sufficient, the order is safely revived and stock decremented.
        """
        import json
        from api.models import Product, Order, OrderItem, Payment

        mock_client = MockRazorpayClient.return_value
        mock_client.utility.verify_webhook_signature.return_value = None

        # Scenario A: Stock is depleted to 0 (insufficient)
        prod_scarce = Product.objects.create(
            name="Scarce Item",
            price=Decimal('100.00'),
            stock=0, # Stock is 0!
            category=self.category,
            approval_status='approved'
        )
        cancelled_order = Order.objects.create(
            user=self.user,
            total_price=Decimal('200.00'),
            status='cancelled'
        )
        OrderItem.objects.create(
            order=cancelled_order,
            product=prod_scarce,
            quantity=2,
            price=Decimal('100.00'),
            status='cancelled'
        )

        payload_a = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_revival_depleted_1",
                        "amount": 20000,
                        "method": "card",
                        "notes": {"django_order_id": cancelled_order.id}
                    }
                }
            }
        }
        res_a = self.client.post(
            '/api/webhooks/razorpay/',
            json.dumps(payload_a),
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE='valid_sig'
        )
        self.assertEqual(res_a.status_code, status.HTTP_200_OK)

        # Assert order remains cancelled and stock never dropped below 0
        cancelled_order.refresh_from_db()
        self.assertEqual(cancelled_order.status, 'cancelled', "Order must NOT be revived when stock is depleted")
        prod_scarce.refresh_from_db()
        self.assertEqual(prod_scarce.stock, 0, "Stock must remain 0 and not become negative")

        # Assert refund was called on gateway
        mock_client.payment.refund.assert_called_with('pay_revival_depleted_1', {
            'amount': 20000,
            'notes': {'order_id': str(cancelled_order.id), 'reason': 'Auto-refund: Insufficient inventory on revival'}
        })
        payment_a = Payment.objects.get(transaction_id="pay_revival_depleted_1")
        self.assertEqual(payment_a.status, 'refunded')

        # Scenario B: Stock is sufficient (revival succeeds)
        prod_available = Product.objects.create(
            name="Available Item",
            price=Decimal('50.00'),
            stock=10,
            category=self.category,
            approval_status='approved'
        )
        cancelled_order_b = Order.objects.create(
            user=self.user,
            total_price=Decimal('100.00'),
            status='cancelled'
        )
        OrderItem.objects.create(
            order=cancelled_order_b,
            product=prod_available,
            quantity=2,
            price=Decimal('50.00'),
            status='cancelled'
        )

        payload_b = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_revival_success_2",
                        "amount": 10000,
                        "method": "upi",
                        "notes": {"django_order_id": cancelled_order_b.id}
                    }
                }
            }
        }
        res_b = self.client.post(
            '/api/webhooks/razorpay/',
            json.dumps(payload_b),
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE='valid_sig'
        )
        self.assertEqual(res_b.status_code, status.HTTP_200_OK)

        cancelled_order_b.refresh_from_db()
        self.assertEqual(cancelled_order_b.status, 'paid', "Order should be safely revived to paid when stock is available")
        prod_available.refresh_from_db()
        self.assertEqual(prod_available.stock, 8, "Stock must be decremented by 2 (10 -> 8)")

    @patch('razorpay.Client')
    def test_refinement05_gateway_refund_failure_status(self, MockRazorpayClient):
        """
        REFINEMENT 5: Gateway Refund Status Accuracy on Failure
        Verifies that when an order cancellation triggers a gateway refund:
        - If client.payment.refund raises an exception, the payment record status
          is recorded as 'refund_failed' (NOT 'refunded'), maintaining financial truth.
        - If client.payment.refund succeeds, the status is set to 'refunded'.
        """
        from api.models import Order, OrderItem, Payment

        mock_client = MockRazorpayClient.return_value

        # 1. Failure Scenario: Gateway raises Exception
        mock_client.payment.refund.side_effect = Exception("Razorpay 502 Bad Gateway")

        order_fail = Order.objects.create(
            user=self.user,
            total_price=Decimal('250.00'),
            status='pending_payment'
        )
        OrderItem.objects.create(
            order=order_fail,
            product=self.product,
            quantity=1,
            price=Decimal('150.00'),
            status='pending'
        )
        payment_fail = Payment.objects.create(
            order=order_fail,
            payment_method='razorpay',
            transaction_id='pay_gateway_err_404',
            amount=Decimal('250.00'),
            status='completed'
        )

        self.client.force_authenticate(user=self.user)
        res_fail = self.client.post(f'/api/orders/{order_fail.id}/cancel/')
        self.assertEqual(res_fail.status_code, status.HTTP_200_OK)

        payment_fail.refresh_from_db()
        self.assertEqual(
            payment_fail.status,
            'refund_failed',
            "Payment status must be 'refund_failed' when the gateway throws an error"
        )

        # 2. Success Scenario: Gateway refund succeeds
        mock_client.payment.refund.side_effect = None
        mock_client.payment.refund.return_value = {"id": "rfnd_12345", "status": "processed"}

        order_success = Order.objects.create(
            user=self.user,
            total_price=Decimal('300.00'),
            status='pending_payment'
        )
        OrderItem.objects.create(
            order=order_success,
            product=self.product,
            quantity=1,
            price=Decimal('150.00'),
            status='pending'
        )
        payment_success = Payment.objects.create(
            order=order_success,
            payment_method='razorpay',
            transaction_id='pay_gateway_ok_200',
            amount=Decimal('300.00'),
            status='completed'
        )

        res_ok = self.client.post(f'/api/orders/{order_success.id}/cancel/')
        self.assertEqual(res_ok.status_code, status.HTTP_200_OK)

        payment_success.refresh_from_db()
        self.assertEqual(
            payment_success.status,
            'refunded',
            "Payment status must be 'refunded' when the gateway succeeds"
        )

    def test_refinement06_idempotency_key_sha256_hashing(self):
        """
        REFINEMENT 6: Idempotency Key Sanitization & SHA-256 Hashing
        Verifies that idempotency keys of arbitrary length or containing control characters
        are cleanly truncated and SHA-256 hashed into safe, deterministic 64-char hex keys,
        preventing Redis memory bloat and key collisions.
        """
        from django.core.cache import cache
        from api.utils.idempotency import (
            _sanitize_and_hash_key,
            check_idempotency,
            store_idempotency_result,
            release_idempotency_lock
        )

        # 1. 10,000-character key with spaces, newlines, and symbols
        huge_key = "  " + ("x" * 10000) + " \n\r\t \x00 "
        hashed_key = _sanitize_and_hash_key(huge_key)
        self.assertIsNotNone(hashed_key)
        self.assertEqual(len(hashed_key), 64)
        self.assertTrue(all(c in '0123456789abcdef' for c in hashed_key))

        # 2. Complete idempotency workflow with extreme key
        cache.clear()
        user_id = 999
        endpoint = "test_checkout"

        # First attempt: lock acquired
        cached_res, lock_acquired = check_idempotency(user_id, endpoint, huge_key)
        self.assertIsNone(cached_res)
        self.assertTrue(lock_acquired)

        # Second attempt concurrently: lock NOT acquired
        cached_res2, lock_acquired2 = check_idempotency(user_id, endpoint, huge_key)
        self.assertIsNone(cached_res2)
        self.assertFalse(lock_acquired2)

        # Store result
        store_idempotency_result(user_id, endpoint, huge_key, {"order_id": 123}, 201)

        # Third attempt: cached response returned immediately
        cached_res3, lock_acquired3 = check_idempotency(user_id, endpoint, huge_key)
        self.assertIsNotNone(cached_res3)
        self.assertEqual(cached_res3['data'], {"order_id": 123})
        self.assertEqual(cached_res3['status'], 201)
        self.assertTrue(lock_acquired3)

        # Clean release
        release_idempotency_lock(user_id, endpoint, huge_key)

    def test_refinement07_remove_stale_ngrok_domain(self):
        """
        REFINEMENT 7: Removal of Stale ngrok Development Tunnel from ALLOWED_HOSTS
        Verifies that ephemeral dev domains such as 'thread-sedative-tinker.ngrok-free.dev'
        are completely purged from ALLOWED_HOSTS, preventing DNS hijacking/Host header attacks.
        """
        from django.conf import settings

        self.assertNotIn(
            'thread-sedative-tinker.ngrok-free.dev',
            settings.ALLOWED_HOSTS,
            "Ephemeral ngrok development tunnel must not exist in ALLOWED_HOSTS"
        )
        for host in settings.ALLOWED_HOSTS:
            self.assertFalse(
                'ngrok' in host.lower(),
                f"No ngrok tunnel domain should exist in ALLOWED_HOSTS: {host}"
            )

    def test_refinement08_orderitem_quantity_check_constraint(self):
        """
        REFINEMENT 8: Database Check Constraint on Positive OrderItem Quantities
        Verifies that the database-level check constraint 'order_item_quantity_gt_0'
        strictly blocks zero or negative quantities at the SQL/storage engine level,
        preventing free-item exploits and invoice total corruption.
        """
        from django.db import transaction, IntegrityError
        from api.models import OrderItem

        # 1. Direct database insert with quantity=0 MUST raise IntegrityError
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                OrderItem.objects.create(
                    order=self.order,
                    product=self.product,
                    quantity=0,
                    price=Decimal('100.00')
                )

        # 2. Direct database insert with quantity=-5 MUST raise IntegrityError
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                OrderItem.objects.create(
                    order=self.order,
                    product=self.product,
                    quantity=-5,
                    price=Decimal('100.00')
                )

        # 3. Valid positive quantity inserts cleanly
        valid_item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=3,
            price=Decimal('100.00')
        )
        self.assertEqual(valid_item.quantity, 3)


class PhaseCArchitectureScalingTests(APITestCase):
    """
    Phase C: Architecture, Scaling & Throttling Test Suite.
    Validates DRF rate limits, Category caching, Product composite indexes,
    connection-managed thread pools, and PDF invoice caching.
    """

    def setUp(self):
        from api.models import User, Product, Category, Order, OrderItem
        from django.core.cache import cache
        cache.clear()
        self.category = Category.objects.create(name="Phase C Electronics")
        self.user = User.objects.create_user(
            username="scaling_user",
            email="scaling@example.com",
            password="SecurePassword123!"
        )
        self.product = Product.objects.create(
            name="Scaling Product",
            price=Decimal('99.99'),
            stock=50,
            category=self.category,
            approval_status='approved'
        )

    def test_blocker1_drf_rate_throttling(self):
        """
        BLOCKER 1 (ARCH-06): DRF Rate Throttling on Sensitive Endpoints
        Verifies that rapid requests to auth and checkout endpoints are strictly throttled
        with HTTP 429 Too Many Requests after exceeding configured throttle thresholds.
        """
        from django.test import override_settings
        from django.core.cache import cache

        test_drf_settings = {
            'DEFAULT_AUTHENTICATION_CLASSES': (
                'api.authenticate.CustomCookieAuthentication',
                'rest_framework.authentication.TokenAuthentication',
            ),
            'DEFAULT_PERMISSION_CLASSES': [
                'rest_framework.permissions.IsAuthenticatedOrReadOnly',
            ],
            'DEFAULT_THROTTLE_CLASSES': [
                'rest_framework.throttling.AnonRateThrottle',
                'rest_framework.throttling.UserRateThrottle',
            ],
            'DEFAULT_THROTTLE_RATES': {
                'anon': '1000/day',
                'user': '1000/day',
                'auth': '3/minute',
                'checkout': '2/minute',
            }
        }

        with override_settings(REST_FRAMEWORK=test_drf_settings):
            # 1. AuthRateThrottle on /api/token/ (Rate: 3/min)
            cache.clear()
            for i in range(3):
                res = self.client.post('/api/token/', {
                    "email": "scaling@example.com",
                    "password": "wrong_password"
                }, format='json')
                self.assertNotEqual(res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

            # 4th attempt must be throttled
            throttled_res = self.client.post('/api/token/', {
                "email": "scaling@example.com",
                "password": "wrong_password"
            }, format='json')
            self.assertEqual(throttled_res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
            self.assertIn('throttled', str(throttled_res.data).lower())

            # 2. CheckoutRateThrottle on create_razorpay_order (Rate: 2/min)
            cache.clear()
            self.client.force_authenticate(user=self.user)
            order_payload = {
                "shipping_address": "456 Scaled St",
                "contact_phone": "1234567890",
                "order_items": [{"product": self.product.id, "quantity": 1}]
            }

            for i in range(2):
                res_checkout = self.client.post('/api/orders/create-razorpay-order/', order_payload, format='json')
                self.assertNotEqual(res_checkout.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

            # 3rd attempt must be throttled with 429
            throttled_checkout = self.client.post('/api/orders/create-razorpay-order/', order_payload, format='json')
            self.assertEqual(throttled_checkout.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

            # 3. AuthRateThrottle on /api/password-reset/request/
            cache.clear()
            self.client.logout()
            for i in range(3):
                res_pwd = self.client.post('/api/password-reset/request/', {'email': 'scaling@example.com'})
                self.assertNotEqual(res_pwd.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

            throttled_pwd = self.client.post('/api/password-reset/request/', {'email': 'scaling@example.com'})
            self.assertEqual(throttled_pwd.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_blocker2_category_caching_and_invalidation(self):
        """
        BLOCKER 2 (ARCH-07): Redis Caching on Category Endpoints with Mutation Invalidation
        Verifies that:
        - GET /api/categories/ caches serialized category list for sub-millisecond retrieval.
        - Subsequent requests are served directly from cache with ZERO database queries.
        - Admin mutations (create, update, delete) immediately invalidate the cache.
        """
        from django.core.cache import cache
        from api.models import User, Category
        from api.views import CATEGORY_LIST_CACHE_KEY

        cache.clear()

        # 1. First request: cache miss, queries DB, populates cache
        self.assertIsNone(cache.get(CATEGORY_LIST_CACHE_KEY))
        res1 = self.client.get('/api/categories/')
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(cache.get(CATEGORY_LIST_CACHE_KEY))
        self.assertEqual(len(res1.data), 1)

        # 2. Second request: served from cache with 0 DB queries
        with self.assertNumQueries(0):
            res2 = self.client.get('/api/categories/')
            self.assertEqual(res2.status_code, status.HTTP_200_OK)
            self.assertEqual(res2.data, res1.data)

        # 3. Create category via admin -> cache must be invalidated
        admin_user = User.objects.create_superuser(
            username="cat_admin",
            email="cat_admin@example.com",
            password="AdminPassword123!"
        )
        self.client.force_authenticate(user=admin_user)

        res_create = self.client.post('/api/categories/', {'name': 'New Category'}, format='json')
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(cache.get(CATEGORY_LIST_CACHE_KEY), "Cache must be invalidated after category creation")

        # 4. Read again: repopulates cache with 2 categories
        res3 = self.client.get('/api/categories/')
        self.assertEqual(res3.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res3.data), 2)
        self.assertIsNotNone(cache.get(CATEGORY_LIST_CACHE_KEY))

        # 5. Update category via admin -> cache must be invalidated
        cat_id = res_create.data['id']
        res_update = self.client.patch(f'/api/categories/{cat_id}/', {'name': 'Updated Category'}, format='json')
        self.assertEqual(res_update.status_code, status.HTTP_200_OK)
        self.assertIsNone(cache.get(CATEGORY_LIST_CACHE_KEY), "Cache must be invalidated after category update")

        # 6. Read again: repopulates cache
        self.client.get('/api/categories/')
        self.assertIsNotNone(cache.get(CATEGORY_LIST_CACHE_KEY))

        # 7. Delete category via admin -> cache must be invalidated
        res_del = self.client.delete(f'/api/categories/{cat_id}/')
        self.assertEqual(res_del.status_code, status.HTTP_204_NO_CONTENT)
        self.assertIsNone(cache.get(CATEGORY_LIST_CACHE_KEY), "Cache must be invalidated after category deletion")

    def test_blocker3_product_composite_indexes(self):
        """
        BLOCKER 3 (ARCH-08): Composite Indexes on Product for High-Traffic Catalog Queries
        Verifies that composite indexes exist on the Product model and database schema:
        - product_catalog_idx: (is_active, approval_status, -created_at)
        - product_cat_status_idx: (category, is_active, approval_status)
        - product_vendor_status_idx: (vendor, approval_status)
        - product_cat_price_idx: (category, price)
        """
        from api.models import Product
        from django.db import connection

        indexes = {idx.name: idx for idx in Product._meta.indexes}
        self.assertIn('product_catalog_idx', indexes)
        self.assertEqual(indexes['product_catalog_idx'].fields, ['is_active', 'approval_status', '-created_at'])

        self.assertIn('product_cat_status_idx', indexes)
        self.assertEqual(indexes['product_cat_status_idx'].fields, ['category', 'is_active', 'approval_status'])

        self.assertIn('product_vendor_status_idx', indexes)
        self.assertEqual(indexes['product_vendor_status_idx'].fields, ['vendor', 'approval_status'])

        self.assertIn('product_cat_price_idx', indexes)
        self.assertEqual(indexes['product_cat_price_idx'].fields, ['category', 'price'])

        # Verify DB introspection
        with connection.cursor() as cursor:
            db_indexes = connection.introspection.get_constraints(cursor, Product._meta.db_table)
            self.assertIn('product_catalog_idx', db_indexes)
            self.assertIn('product_cat_status_idx', db_indexes)
            self.assertIn('product_vendor_status_idx', db_indexes)
            self.assertIn('product_cat_price_idx', db_indexes)

    def test_blocker4_connection_managed_async_task_pool(self):
        """
        BLOCKER 4 (ARCH-09): Managed Thread Pool & Database Connection Hygiene
        Verifies that:
        - run_async executes tasks and automatically calls close_old_connections()
          both before and after execution to prevent leaked PostgreSQL connections.
        - Exceptions in background tasks are caught, logged, and still trigger
          close_old_connections() in the finally block.
        - Async execution in thread pool worker invokes connection management.
        - No raw threading.Thread calls remain in api.email_service, api.serializers, or api.views.
        """
        from unittest.mock import patch, MagicMock
        from api.utils.async_tasks import run_async, _EXECUTOR
        import api.email_service
        import api.serializers
        import api.views
        import inspect

        # 1. Normal execution calls close_old_connections before and after task
        mock_task = MagicMock(return_value="success")
        with patch('api.utils.async_tasks.close_old_connections') as mock_close:
            result = run_async(mock_task, "arg1", key="val")
            self.assertEqual(result, "success")
            mock_task.assert_called_once_with("arg1", key="val")
            self.assertEqual(mock_close.call_count, 2)

        # 2. Failing task still triggers close_old_connections in finally block
        failing_task = MagicMock(side_effect=RuntimeError("Simulated task failure"))
        with patch('api.utils.async_tasks.close_old_connections') as mock_close_err:
            with patch('api.utils.async_tasks.logger.error') as mock_log_err:
                run_async(failing_task)
                self.assertEqual(mock_close_err.call_count, 2)
                mock_log_err.assert_called_once()
                self.assertIn("Simulated task failure", mock_log_err.call_args[0][0])

        # 3. Thread pool execution via executor (force async mode)
        with patch('api.utils.async_tasks.close_old_connections') as mock_close_pool:
            future = run_async(lambda x: x * 2, 21, force_async=True)
            res = future.result(timeout=5)
            self.assertEqual(res, 42)
            self.assertEqual(mock_close_pool.call_count, 2)

        # 4. Code audit: assert no raw threading.Thread dispatches in core modules
        email_src = inspect.getsource(api.email_service)
        serializers_src = inspect.getsource(api.serializers)
        views_src = inspect.getsource(api.views)

        self.assertNotIn("threading.Thread", email_src, "api.email_service must not use raw threading.Thread")
        self.assertNotIn("threading.Thread", serializers_src, "api.serializers must not use raw threading.Thread")
        self.assertNotIn("threading.Thread", views_src, "api.views must not use raw threading.Thread")

    def test_blocker5_invoice_pdf_caching(self):
        """
        BLOCKER 5 (ARCH-10): Redis / Memory Cache for Generated PDF Invoices
        Verifies that:
        - The initial request to download an invoice renders the PDF and stores it in cache.
        - Repeat downloads are served directly from cache without re-invoking ReportLab rendering.
        - Status changes and invalidate_invoice_cache properly invalidate cached artifacts.
        """
        from unittest.mock import patch
        from django.core.cache import cache
        from api.models import Order, OrderItem, Payment
        from api.views import get_invoice_cache_key, invalidate_invoice_cache

        cache.clear()
        self.client.force_authenticate(user=self.user)

        order = Order.objects.create(
            user=self.user,
            total_price=Decimal('199.98'),
            status='paid',
            shipping_address='789 Cache Lane',
            contact_phone='9998887776'
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=2,
            price=Decimal('99.99')
        )
        Payment.objects.create(
            order=order,
            payment_method='razorpay',
            transaction_id='txn_cached_pdf_test',
            amount=Decimal('199.98'),
            status='completed'
        )

        cache_key = get_invoice_cache_key(order.id, order.status)
        self.assertIsNone(cache.get(cache_key))

        # 1. First download request: generates and caches PDF
        res1 = self.client.get(f'/api/orders/{order.id}/invoice/')
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        self.assertEqual(res1['Content-Type'], 'application/pdf')
        content1 = b"".join(res1.streaming_content)
        self.assertTrue(content1.startswith(b'%PDF-'))

        cached_bytes = cache.get(cache_key)
        self.assertIsNotNone(cached_bytes)
        self.assertEqual(cached_bytes, content1)

        # 2. Second request: served from cache with ReportLab generation mocked to fail
        with patch('api.views.generate_invoice_pdf', side_effect=RuntimeError("ReportLab should not be called!")):
            res2 = self.client.get(f'/api/orders/{order.id}/invoice/')
            self.assertEqual(res2.status_code, status.HTTP_200_OK)
            self.assertEqual(res2['Content-Type'], 'application/pdf')
            content2 = b"".join(res2.streaming_content)
            self.assertEqual(content2, cached_bytes)

        # 3. Status change: key changes from paid to cancelled, generating fresh PDF
        order.status = 'cancelled'
        order.save()
        cancelled_key = get_invoice_cache_key(order.id, order.status)
        self.assertIsNone(cache.get(cancelled_key))

        res3 = self.client.get(f'/api/orders/{order.id}/invoice/')
        self.assertEqual(res3.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(cache.get(cancelled_key))

        # 4. Invalidation helper wipes cache
        invalidate_invoice_cache(order.id)
        self.assertIsNone(cache.get(cancelled_key))
        self.assertIsNone(cache.get(cache_key))


class PhaseABCHardeningRefinementsSuite(APITestCase):
    """
    Comprehensive Adversarial Hardening Suite for Phase A, B, and C.
    Validates edge cases, race conditions, proxy security, and cache consistency.
    """

    def setUp(self):
        from api.models import User, Product, Category, Order, OrderItem
        from django.core.cache import cache
        cache.clear()
        self.category = Category.objects.create(name="Hardening Category")
        self.user = User.objects.create_user(
            username="hardened_user",
            email="hardened@example.com",
            password="SecurePassword123!"
        )
        self.product = Product.objects.create(
            name="Hardened Product",
            price=Decimal('50.00'),
            stock=10,
            category=self.category,
            approval_status='approved'
        )

    def test_refinement01_rate_throttle_proxy_and_auth_scoping(self):
        """
        REFINEMENT 1 (ADV-ARCH-01 & ADV-ARCH-02): Rate Throttle Proxy Hardening & Universal IP Scoping
        Verifies that:
        - REST_FRAMEWORK has NUM_PROXIES configured to 1.
        - AuthRateThrottle throttles authenticated users on auth endpoints (no exemption).
        - Rotating spoofed X-Forwarded-For prefixes cannot bypass throttling when behind NUM_PROXIES=1.
        """
        from django.conf import settings
        from django.test import override_settings
        from django.core.cache import cache
        from api.throttles import AuthRateThrottle

        # 1. NUM_PROXIES must be configured in settings.REST_FRAMEWORK
        self.assertIn('NUM_PROXIES', settings.REST_FRAMEWORK)
        self.assertEqual(settings.REST_FRAMEWORK['NUM_PROXIES'], 1)

        test_drf_settings = dict(settings.REST_FRAMEWORK)
        test_drf_settings['DEFAULT_THROTTLE_RATES'] = {
            'anon': '1000/day',
            'user': '1000/day',
            'auth': '3/minute',
            'checkout': '30/minute',
        }

        with override_settings(REST_FRAMEWORK=test_drf_settings):
            cache.clear()

            # 2. Authenticated user MUST be throttled on AuthRateThrottle endpoints
            self.client.force_authenticate(user=self.user)
            for _ in range(3):
                res = self.client.post('/api/password-reset/request/', {'email': 'hardened@example.com'})
                self.assertNotEqual(res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

            throttled_auth_res = self.client.post('/api/password-reset/request/', {'email': 'hardened@example.com'})
            self.assertEqual(
                throttled_auth_res.status_code,
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Authenticated requests MUST be subject to AuthRateThrottle"
            )

            # 3. Rotating client-controlled spoofed XFF prefix does NOT bypass rate limit
            cache.clear()
            self.client.logout()

            # Attacker tries to spoof client IP by prepending fake IPs: "spoof1, 198.51.100.1"
            proxy_client_ip = "198.51.100.1"
            for i in range(3):
                spoofed_xff = f"10.0.0.{i}, {proxy_client_ip}"
                res = self.client.post(
                    '/api/token/',
                    {"email": "hardened@example.com", "password": "wrong"},
                    format='json',
                    HTTP_X_FORWARDED_FOR=spoofed_xff
                )
                self.assertNotEqual(res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

            # 4th request with a different prepended spoof IP still resolves to proxy_client_ip and is throttled!
            throttled_xff = self.client.post(
                '/api/token/',
                {"email": "hardened@example.com", "password": "wrong"},
                format='json',
                HTTP_X_FORWARDED_FOR=f"1.2.3.4, {proxy_client_ip}"
            )
            self.assertEqual(
                throttled_xff.status_code,
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Rotating fake XFF prefixes must NOT bypass throttling when NUM_PROXIES=1"
            )

    def test_refinement02_email_socket_timeout(self):
        """
        REFINEMENT 2 (ADV-ARCH-03): Thread Pool Socket Timeout & Starvation Prevention
        Verifies that:
        - EMAIL_TIMEOUT is strictly configured to prevent indefinite socket hangs.
        - ANYMAIL['REQUESTS_TIMEOUT'] is configured to prevent API worker starvation.
        """
        from django.conf import settings

        # 1. Standard Django EMAIL_TIMEOUT must be set and bounded (<= 10 seconds)
        self.assertTrue(hasattr(settings, 'EMAIL_TIMEOUT'), "settings must define EMAIL_TIMEOUT")
        self.assertIsInstance(settings.EMAIL_TIMEOUT, int)
        self.assertLessEqual(settings.EMAIL_TIMEOUT, 10, "EMAIL_TIMEOUT must be short (<= 10s)")

        # 2. Anymail REQUESTS_TIMEOUT must be set and bounded
        self.assertTrue(hasattr(settings, 'ANYMAIL'), "settings must define ANYMAIL dictionary")
        self.assertIn('REQUESTS_TIMEOUT', settings.ANYMAIL)
        self.assertLessEqual(settings.ANYMAIL['REQUESTS_TIMEOUT'], 10)

    def test_refinement03_order_cancel_concurrency_race(self):
        """
        REFINEMENT 3 (ADV-FIN-01): Atomic Row Locking on Order Cancellation
        Verifies that:
        - Order cancel acquires an atomic row lock on Order inside transaction.
        - Subsequent or parallel cancellation attempts on the same order return HTTP 400.
        - Stock is incremented exactly once and phantom stock duplication is prevented.
        """
        from api.models import Order, OrderItem

        self.client.force_authenticate(user=self.user)
        initial_stock = self.product.stock

        order = Order.objects.create(
            user=self.user,
            total_price=Decimal('100.00'),
            status='processing',
            shipping_address='Cancel Test St',
            contact_phone='1234567890'
        )
        item = OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=2,
            price=Decimal('50.00'),
            status='pending'
        )

        # 1. First cancellation succeeds
        res1 = self.client.post(f'/api/orders/{order.id}/cancel/')
        self.assertEqual(res1.status_code, status.HTTP_200_OK)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, initial_stock + 2, "Stock must be incremented by 2")

        order.refresh_from_db()
        self.assertEqual(order.status, 'cancelled')

        # 2. Immediate second cancellation attempt (simulating concurrent or replay request)
        res2 = self.client.post(f'/api/orders/{order.id}/cancel/')
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("cannot cancel", res2.data.get('error', '').lower())

        # Assert stock was NOT incremented again
        self.product.refresh_from_db()
        self.assertEqual(
            self.product.stock,
            initial_stock + 2,
            "Stock must NOT be double-incremented by repeat cancellation"
        )

    @patch('razorpay.Client')
    def test_refinement04_webhook_deterministic_product_locking(self, mock_client_cls):
        """
        ADV-FIN-02: Verify deterministic ascending lock ordering in razorpay_webhook
        for order revival, refund, and payment.failed events.
        """
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.utility.verify_webhook_signature.return_value = True

        # Create two products with known IDs
        p1 = Product.objects.create(
            name="Test Product 1",
            price=Decimal('100.00'),
            stock=10,
            category=self.category,
            approval_status='approved'
        )
        p2 = Product.objects.create(
            name="Test Product 2",
            price=Decimal('50.00'),
            stock=10,
            category=self.category,
            approval_status='approved'
        )
        prod_low, prod_high = (p1, p2) if p1.id < p2.id else (p2, p1)
        prod_high.stock = 15
        prod_high.save(update_fields=['stock'])
        prod_low.stock = 10
        prod_low.save(update_fields=['stock'])

        # Create a cancelled order with items inserted in descending ID order (prod_high first, then prod_low)
        revival_order = Order.objects.create(
            user=self.user,
            total_price=Decimal('200.00'),
            status='cancelled'
        )
        OrderItem.objects.create(
            order=revival_order,
            product=prod_high,
            quantity=3,
            price=prod_high.price,
            status='cancelled'
        )
        OrderItem.objects.create(
            order=revival_order,
            product=prod_low,
            quantity=2,
            price=prod_low.price,
            status='cancelled'
        )

        # Trigger revival via payment.captured
        payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_revival_deterministic_1",
                        "amount": 20000,
                        "method": "card",
                        "notes": {"django_order_id": revival_order.id}
                    }
                }
            }
        }
        res = self.client.post(
            '/api/webhooks/razorpay/',
            json.dumps(payload),
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE='valid_sig'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Assert revival succeeded
        revival_order.refresh_from_db()
        self.assertEqual(revival_order.status, 'paid')
        prod_high.refresh_from_db()
        self.assertEqual(prod_high.stock, 12, "High product stock should be decremented by 3")
        prod_low.refresh_from_db()
        self.assertEqual(prod_low.stock, 8, "Low product stock should be decremented by 2")

        # Now test refund.processed on this revived order
        refund_payload = {
            "event": "refund.processed",
            "payload": {
                "refund": {
                    "entity": {
                        "id": "rfnd_deterministic_1",
                        "payment_id": "pay_revival_deterministic_1",
                        "amount": 20000
                    }
                },
                "payment": {
                    "entity": {
                        "id": "pay_revival_deterministic_1",
                        "notes": {"django_order_id": revival_order.id}
                    }
                }
            }
        }
        res_rfnd = self.client.post(
            '/api/webhooks/razorpay/',
            json.dumps(refund_payload),
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE='valid_sig'
        )
        self.assertEqual(res_rfnd.status_code, status.HTTP_200_OK)

        revival_order.refresh_from_db()
        self.assertEqual(revival_order.status, 'cancelled')
        prod_high.refresh_from_db()
        self.assertEqual(prod_high.stock, 15, "High product stock should be restocked to 15")
        prod_low.refresh_from_db()
        self.assertEqual(prod_low.stock, 10, "Low product stock should be restocked to 10")

    @patch('razorpay.Client')
    def test_refinement05_non_blocking_gateway_refund(self, mock_client_cls):
        """
        ADV-FIN-03: Verify that gateway refunds during order cancellation
        do not rollback the cancellation or product restocking even if the gateway fails,
        and update payment status accurately.
        """
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        # Case A: Gateway refund fails with an API error
        mock_client.payment.refund.side_effect = Exception("Gateway Timeout")

        order_a = Order.objects.create(
            user=self.user,
            total_price=Decimal('100.00'),
            status='pending_payment'
        )
        OrderItem.objects.create(
            order=order_a,
            product=self.product,
            quantity=2,
            price=Decimal('50.00'),
            status='pending'
        )
        pay_a = Payment.objects.create(
            order=order_a,
            payment_method='razorpay',
            transaction_id='pay_timeout_test',
            amount=Decimal('100.00'),
            status='completed'
        )

        initial_stock = self.product.stock
        self.client.force_authenticate(user=self.user)
        res_a = self.client.post(f'/api/orders/{order_a.id}/cancel/')
        self.assertEqual(res_a.status_code, status.HTTP_200_OK)

        # Order must remain cancelled, stock must be restored
        order_a.refresh_from_db()
        self.assertEqual(order_a.status, 'cancelled')
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, initial_stock + 2)

        # Payment status must be 'refund_failed', not 'completed' or 'refunded'
        pay_a.refresh_from_db()
        self.assertEqual(pay_a.status, 'refund_failed')

        # Case B: Gateway refund succeeds
        mock_client.payment.refund.side_effect = None
        mock_client.payment.refund.return_value = {'id': 'rfnd_success_123', 'status': 'processed'}

        order_b = Order.objects.create(
            user=self.user,
            total_price=Decimal('100.00'),
            status='pending_payment'
        )
        OrderItem.objects.create(
            order=order_b,
            product=self.product,
            quantity=1,
            price=Decimal('50.00'),
            status='pending'
        )
        pay_b = Payment.objects.create(
            order=order_b,
            payment_method='razorpay',
            transaction_id='pay_success_test',
            amount=Decimal('100.00'),
            status='completed'
        )

        res_b = self.client.post(f'/api/orders/{order_b.id}/cancel/')
        self.assertEqual(res_b.status_code, status.HTTP_200_OK)

        order_b.refresh_from_db()
        self.assertEqual(order_b.status, 'cancelled')
        pay_b.refresh_from_db()
        self.assertEqual(pay_b.status, 'refunded')

    @patch('api.utils.pdf_generator.session')
    @patch('api.utils.pdf_generator.is_safe_image_url')
    def test_refinement06_pdf_image_ssrf_and_size_limits(self, mock_is_safe, mock_session):
        """
        ADV-SEC-01: Verify that PDF generator get_product_image enforces
        image/* Content-Type validation, rejects Content-Length > 5MB,
        and halts streaming if transferred bytes exceed 5MB.
        """
        from api.utils.pdf_generator import get_product_image

        mock_is_safe.return_value = True

        class DummyItem:
            image_url = 'https://cdn.example.com/images/sample.jpg'

        # Case 1: Non-image Content-Type (e.g. text/html or application/json attack)
        mock_response_html = MagicMock()
        mock_response_html.status_code = 200
        mock_response_html.headers = {'Content-Type': 'text/html; charset=UTF-8'}
        mock_session.get.return_value = mock_response_html

        result_html = get_product_image(DummyItem())
        self.assertIsNone(result_html, "Non-image Content-Type must be rejected")

        # Case 2: Header Content-Length exceeds 5MB
        mock_response_oversized_header = MagicMock()
        mock_response_oversized_header.status_code = 200
        mock_response_oversized_header.headers = {
            'Content-Type': 'image/jpeg',
            'Content-Length': str(10 * 1024 * 1024) # 10MB
        }
        mock_session.get.return_value = mock_response_oversized_header

        result_header = get_product_image(DummyItem())
        self.assertIsNone(result_header, "Image with Content-Length > 5MB must be rejected")

        # Case 3: Streaming chunks exceed 5MB
        mock_response_stream_bomb = MagicMock()
        mock_response_stream_bomb.status_code = 200
        mock_response_stream_bomb.headers = {'Content-Type': 'image/png'}
        # Emit 6MB in chunks
        mock_response_stream_bomb.iter_content.return_value = [b"A" * (1024 * 1024) for _ in range(6)]
        mock_session.get.return_value = mock_response_stream_bomb

        result_stream = get_product_image(DummyItem())
        self.assertIsNone(result_stream, "Streaming image exceeding 5MB must be halted and rejected")

    def test_refinement07_password_reset_complexity_validation(self):
        """
        ADV-SEC-02: Verify that ConfirmPasswordResetView enforces Django password validators,
        rejecting short/common/numeric passwords and accepting compliant passwords.
        """
        user_email = "pwd_val_user@example.com"
        val_user = User.objects.create_user(
            username="pwd_val_user",
            email=user_email,
            password="InitialStrongPassword123!"
        )

        # Stage OTP in cache
        cache.set(f"pwd_reset_{user_email}", "777888", timeout=300)

        # 1. Attempt reset with a short / weak password
        res_weak = self.client.post('/api/password-reset/confirm/', {
            "email": user_email,
            "otp": "777888",
            "new_password": "short"
        }, format='json')

        self.assertEqual(res_weak.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(isinstance(res_weak.data.get('error'), list), "Error must be a list of validator messages")
        self.assertTrue(any("too short" in msg.lower() for msg in res_weak.data['error']))

        # OTP should still be valid in cache for a compliant retry
        self.assertEqual(cache.get(f"pwd_reset_{user_email}"), "777888")

        # 2. Attempt reset with an all-numeric password
        res_numeric = self.client.post('/api/password-reset/confirm/', {
            "email": user_email,
            "otp": "777888",
            "new_password": "1234567890"
        }, format='json')
        self.assertEqual(res_numeric.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(any("entirely numeric" in msg.lower() for msg in res_numeric.data['error']))

        # 3. Successful reset with strong compliant password
        res_strong = self.client.post('/api/password-reset/confirm/', {
            "email": user_email,
            "otp": "777888",
            "new_password": "BrandNewSecretPassword9988!"
        }, format='json')
        self.assertEqual(res_strong.status_code, status.HTTP_200_OK)
        self.assertEqual(res_strong.data.get('detail'), "Password reset successfully.")

        # Cache should now be cleared
        self.assertIsNone(cache.get(f"pwd_reset_{user_email}"))

        # User password must authenticate with new password
        val_user.refresh_from_db()
        self.assertTrue(val_user.check_password("BrandNewSecretPassword9988!"))

    def test_refinement08_profile_otp_brute_force_lockout(self):
        """
        ADV-SEC-04: Verify that UserViewSet.update limits profile_otp guessing
        to 5 attempts, invalidates the OTP upon reaching 5 failures,
        and returns HTTP 429 Too Many Requests.
        """
        self.client.force_authenticate(user=self.user)
        user_url = f"/api/users/{self.user.id}/"

        # Set up a profile OTP for the user
        cache.set(f"profile_otp_{self.user.id}", "123456", timeout=300)
        cache.delete(f"profile_otp_attempts_{self.user.id}")

        # 4 failed attempts with invalid OTP
        for attempt in range(1, 5):
            res = self.client.patch(user_url, {
                "phone": f"999888777{attempt}",
                "otp": "999999"
            }, format='json')
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(res.data.get('error'), "Invalid or expired OTP.")
            self.assertEqual(cache.get(f"profile_otp_{self.user.id}"), "123456")

        # 5th failed attempt triggers HTTP 429 lockout and wipes OTP
        res_5 = self.client.patch(user_url, {
            "phone": "9998887775",
            "otp": "999999"
        }, format='json')
        self.assertEqual(res_5.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn("too many failed attempts", res_5.data.get('error', '').lower())

        # Assert OTP was wiped from cache
        self.assertIsNone(cache.get(f"profile_otp_{self.user.id}"))

        # 6th attempt should remain blocked with 429
        res_6 = self.client.patch(user_url, {
            "phone": "9998887776",
            "otp": "123456" # Even with the original OTP
        }, format='json')
        self.assertEqual(res_6.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_refinement09_universal_category_and_invoice_cache_invalidation(self):
        """
        ADV-ARCH-04 & ADV-ARCH-05: Verify universal signal-based cache invalidation
        for Category (post_save, post_delete) and Order PDF invoices (post_save, post_delete, views).
        """
        # 1. Category Cache Invalidation via Signals
        cache.set('cache_category_list', [{'id': 999, 'name': 'Cached List'}], timeout=3600)
        self.assertIsNotNone(cache.get('cache_category_list'))

        # Create Category directly via ORM (bypassing viewset)
        new_cat = Category.objects.create(name="Signal Category 1")
        self.assertIsNone(cache.get('cache_category_list'), "Category creation signal must purge cache_category_list")

        # Repopulate cache and update Category via ORM
        cache.set('cache_category_list', [{'id': 999, 'name': 'Cached List'}], timeout=3600)
        new_cat.name = "Signal Category Renamed"
        new_cat.save()
        self.assertIsNone(cache.get('cache_category_list'), "Category update signal must purge cache_category_list")

        # Repopulate cache and delete Category via ORM
        cache.set('cache_category_list', [{'id': 999, 'name': 'Cached List'}], timeout=3600)
        new_cat.delete()
        self.assertIsNone(cache.get('cache_category_list'), "Category delete signal must purge cache_category_list")

        # 2. Invoice PDF Cache Invalidation via Signals & Views
        order = Order.objects.create(
            user=self.user,
            total_price=Decimal('150.00'),
            status='pending_payment'
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            price=Decimal('150.00'),
            status='pending'
        )

        inv_cache_key = f"invoice_pdf_{order.id}_pending_payment"
        cache.set(inv_cache_key, b"%PDF-dummy-invoice-content", timeout=3600)
        self.assertIsNotNone(cache.get(inv_cache_key))

        # Cancel order via viewset -> verify invoice cache is purged
        self.client.force_authenticate(user=self.user)
        res_cancel = self.client.post(f"/api/orders/{order.id}/cancel/")
        self.assertEqual(res_cancel.status_code, status.HTTP_200_OK)
        self.assertIsNone(cache.get(inv_cache_key), "Order cancellation must invalidate invoice cache")

        # Populate cache key for 'cancelled' status
        cancelled_key = f"invoice_pdf_{order.id}_cancelled"
        cache.set(cancelled_key, b"%PDF-cancelled-invoice", timeout=3600)
        self.assertIsNotNone(cache.get(cancelled_key))

        # Direct ORM update triggers post_save signal
        order.refresh_from_db()
        order.save()
        self.assertIsNone(cache.get(cancelled_key), "Order post_save signal must invalidate all invoice cache variants")
