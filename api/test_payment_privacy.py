from unittest.mock import patch

from django.core.cache import cache
from rest_framework.test import APITestCase

from .models import Order, Payment, User


class PaymentPrivacyTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.buyer = User.objects.create_user('buyer', 'buyer@example.invalid')
        self.other = User.objects.create_user('other', 'other@example.invalid')
        self.order = Order.objects.create(user=self.other, total_price=50, gateway_order_id='order_foreign')
        self.payment = Payment.objects.create(
            order=self.order, transaction_id='pay_foreign', amount=50, status='completed',
        )
        self.client.force_authenticate(self.buyer)

    @patch('api.views.razorpay.Client')
    def test_foreign_completed_payment_is_never_disclosed(self, gateway):
        for prefix in ('/api/orders/', '/api/secure/api/orders/'):
            response = self.client.post(prefix + 'verify-razorpay-payment/', {
                'order_id': self.order.pk, 'razorpay_payment_id': 'arbitrary',
                'razorpay_order_id': self.order.gateway_order_id,
            }, format='json')
            self.assertEqual(response.status_code, 400)
            self.assertNotIn('payment', response.data)
            self.assertNotIn(self.payment.transaction_id, str(response.data))
        gateway.assert_not_called()

    @patch('api.views.razorpay.Client')
    def test_foreign_pending_nonexistent_and_malformed_ids_never_query_gateway(self, gateway):
        for fields in (
            {'order_id': self.order.pk}, {'order_id': 999999}, {'order_id': []},
            {'order_id': {}}, {'order_id': True}, {'order_id': -1}, {'order_id': '9' * 100},
            {'order_id': '9' * 5000}, {'order_id': 'invalid'}, {'razorpay_payment_id': []},
            {'razorpay_order_id': {}}, {'razorpay_payment_id': ''},
        ):
            response = self.client.post('/api/orders/verify-razorpay-payment/', {
                'order_id': self.order.pk, 'razorpay_payment_id': self.payment.transaction_id,
                'razorpay_order_id': self.order.gateway_order_id, **fields,
            }, format='json')
            self.assertEqual(response.status_code, 400)
            self.assertNotIn('payment', response.data)
        gateway.assert_not_called()

    def test_payment_list_detail_and_order_detail_are_owner_scoped(self):
        from django.contrib.auth.models import Permission
        actors = [self.buyer, User.objects.create_user('seller', 'seller@example.invalid', role='seller'),
                  User.objects.create_user('staff', 'staff@example.invalid', is_staff=True)]
        for actor in actors:
            self.client.force_authenticate(actor)
            self.assertEqual(self.client.get(f'/api/payments/{self.payment.pk}/').status_code, 404)
            self.assertEqual(self.client.get('/api/payments/').data['count'], 0)
            for prefix in ('/api/orders/', '/api/secure/api/orders/'):
                self.assertEqual(self.client.get(f'{prefix}{self.order.pk}/').status_code, 404)
        staff = actors[-1]
        staff.user_permissions.add(Permission.objects.get(content_type__app_label='api', codename='view_order'))
        staff = User.objects.get(pk=staff.pk)
        for actor in (self.other, staff, User.objects.create_user('administrator', 'admin@example.invalid', role='admin')):
            self.client.force_authenticate(actor)
            self.assertEqual(self.client.get(f'/api/payments/{self.payment.pk}/').status_code, 200)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f'/api/payments/{self.payment.pk}/').status_code, 401)

    def settled_order(self):
        from .models import Product, OrderItem
        from .settlement import record_gateway_capture
        order = Order.objects.create(user=self.buyer, total_price=50, gateway_order_id='order_owned', status='pending_payment')
        product = Product.objects.create(name='Fixture', price=50, stock=10)
        OrderItem.objects.create(order=order, product=product, price=50, quantity=1)
        entity = {'id': 'pay_owned', 'order_id': order.gateway_order_id, 'amount': 5000,
                  'currency': 'INR', 'status': 'captured', 'method': 'card'}
        payment, _ = record_gateway_capture(order, entity)
        return order, payment

    @patch('api.views.razorpay.Client')
    def test_same_order_settled_replay_uses_persisted_evidence(self, gateway):
        order, payment = self.settled_order()
        for prefix in ('/api/orders/', '/api/secure/api/orders/'):
            for key in ('same-key', 'different-key', ''):
                response = self.client.post(prefix + 'verify-razorpay-payment/', {
                    'order_id': order.pk, 'razorpay_payment_id': payment.transaction_id,
                    'razorpay_order_id': order.gateway_order_id, 'idempotency_key': key,
                }, format='json')
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(response.data['payment']['id'], payment.pk)
        self.assertEqual(order.payment.count(), 1)
        gateway.assert_not_called()

    @patch('api.views.razorpay.Client')
    def test_cached_success_cannot_bypass_authorization_or_refund_state(self, gateway):
        from .utils.idempotency import store_idempotency_result
        order, payment = self.settled_order()
        # Simulate an old-version cache entry remaining across deployment.
        store_idempotency_result(self.buyer.pk, 'verify_razorpay_payment', 'cached-key',
            {'success': True, 'order_id': order.pk, 'payment': {'id': payment.pk}}, 200)
        base = {'order_id': order.pk, 'razorpay_payment_id': payment.transaction_id,
                'razorpay_order_id': order.gateway_order_id, 'idempotency_key': 'cached-key'}
        for fields in ({'order_id': self.order.pk}, {'razorpay_payment_id': self.payment.transaction_id},
                       {'razorpay_payment_id': 'unrelated'}, {'razorpay_order_id': 'unrelated'}):
            response = self.client.post('/api/orders/verify-razorpay-payment/', {**base, **fields}, format='json')
            self.assertEqual(response.status_code, 400)
            self.assertNotIn('payment', response.data)
        payment.status = 'refunded'
        payment.save(update_fields=['status'])
        self.assertEqual(self.client.post('/api/orders/verify-razorpay-payment/', base, format='json').status_code, 400)
        gateway.assert_not_called()

    @patch('api.views.razorpay.Client')
    def test_admin_visibility_does_not_grant_customer_payment_verification(self, gateway):
        for actor in (None, User.objects.create_user('admin', 'admin@example.invalid', role='admin'),
                      User.objects.create_user('privileged', 'privileged@example.invalid', is_staff=True, is_superuser=True)):
            self.client.force_authenticate(actor)
            response = self.client.post('/api/orders/verify-razorpay-payment/', {
                'order_id': self.order.pk, 'razorpay_payment_id': self.payment.transaction_id,
                'razorpay_order_id': self.order.gateway_order_id,
            }, format='json')
            self.assertEqual(response.status_code, 401 if actor is None else 400)
        gateway.assert_not_called()

    @patch('api.views.razorpay.Client')
    def test_unrelated_foreign_payment_rejected_for_owned_pending_order(self, gateway):
        order = Order.objects.create(user=self.buyer, total_price=50, gateway_order_id='order_pending')
        response = self.client.post('/api/orders/verify-razorpay-payment/', {
            'order_id': order.pk, 'razorpay_payment_id': self.payment.transaction_id,
            'razorpay_order_id': order.gateway_order_id, 'razorpay_signature': 'fixture',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('payment', response.data)
        gateway.assert_not_called()
        order.refresh_from_db()
        self.assertEqual(order.status, 'pending')
        self.assertFalse(order.payment.exists())

    @patch('api.views.razorpay.Client')
    def test_unverified_completed_record_never_replays_success(self, gateway):
        order, payment = self.settled_order()
        payment.verified_at = None
        payment.save(update_fields=['verified_at'])
        response = self.client.post('/api/orders/verify-razorpay-payment/', {
            'order_id': order.pk, 'razorpay_payment_id': payment.transaction_id,
            'razorpay_order_id': order.gateway_order_id,
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('payment', response.data)
        gateway.assert_not_called()
