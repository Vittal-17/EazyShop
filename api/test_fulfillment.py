import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.db.models.deletion import ProtectedError
from django.test import TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone
from rest_framework.test import APITestCase

from .fulfillment import fulfill_order
from .models import Order, OrderItem, Payment, Product, User, WalletTransaction


class OrderFulfillmentTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.buyer = User.objects.create_user('buyer', 'buyer@example.invalid', wallet_balance='100.00')
        cls.seller = User.objects.create_user('seller', 'seller@example.invalid', role='seller')
        cls.other = User.objects.create_user('other', 'other@example.invalid', role='seller')
        cls.admin = User.objects.create_user('appadmin', 'appadmin@example.invalid', role='admin')
        cls.staff = User.objects.create_user('staff', 'staff@example.invalid', is_staff=True)
        cls.staff.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='api', codename__in=['view_order', 'change_order', 'change_orderitem', 'change_payment'],
        ))
        cls.product = Product.objects.create(
            name='Fixture', price='50.00', stock=10, approval_status='approved', vendor=cls.seller,
        )
        cls.second = Product.objects.create(
            name='Second fixture', price='50.00', stock=10, approval_status='approved', vendor=cls.other,
        )

    def checkout(self, **fields):
        return self.client.post('/api/orders/create-razorpay-order/', {
            'shipping_address': 'Private shipping address', 'contact_phone': '1234',
            'order_items': [{'product': self.product.pk, 'quantity': 1}], **fields,
        }, format='json')

    def vendor_update(self, item, status):
        return self.client.patch(f'/api/vendor-sales/{item.pk}/update_status/', {'status': status}, format='json')

    def test_generic_create_disabled_for_every_actor_and_mount(self):
        for actor in (None, self.buyer, self.seller, self.staff, self.admin):
            self.client.force_authenticate(actor)
            for prefix in ('/api/orders/', '/api/secure/api/orders/'):
                for state in ('paid', 'shipped', 'delivered', 'cancelled', 'refunded'):
                    response = self.client.post(prefix, {
                        'status': state, 'user': self.other.pk, 'total_price': '0.01',
                        'shipping_address': 'Fixture', 'contact_phone': '1234',
                        'order_items': [{'product': self.product.pk, 'quantity': 1, 'status': state}],
                    }, format='json')
                    self.assertEqual(response.status_code, 401 if actor is None else 405)
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.checkout(order_items=[]).status_code, 400)
        self.product.refresh_from_db()
        self.buyer.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
        self.assertEqual(self.buyer.wallet_balance, 100)
        self.assertFalse(Order.objects.exists())
        self.assertFalse(Payment.objects.exists())
        self.assertFalse(WalletTransaction.objects.exists())

    def test_unpaid_hidden_and_blocked_across_apis_admin_and_models(self):
        order = Order.objects.create(user=self.buyer, total_price=50, status='pending_payment', shipping_address='Private')
        item = OrderItem.objects.create(order=order, product=self.product, vendor=self.seller, price=50)
        Payment.objects.create(order=order, transaction_id='unverified', amount=50, status='completed')
        self.client.force_authenticate(self.seller)
        self.assertEqual(self.vendor_update(item, 'shipped').status_code, 404)
        self.assertEqual(self.client.get(f'/api/order-items/{item.pk}/').status_code, 404)
        self.assertEqual(self.client.get('/api/vendor-sales/').data['count'], 0)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.vendor_update(item, 'shipped').status_code, 400)
        for actor in (self.buyer, self.staff, self.admin):
            self.client.force_authenticate(actor)
            for prefix in ('/api/orders/', '/api/secure/api/orders/'):
                for state in ('paid', 'processing', 'shipped', 'delivered', 'refunded'):
                    self.assertEqual(self.client.patch(
                        f'{prefix}{order.pk}/', {'status': state}, format='json',
                    ).status_code, 400)
                self.assertEqual(self.client.patch(f'{prefix}{order.pk}/', {
                    'order_items': [{'id': item.pk, 'status': 'shipped'}],
                }, format='json').status_code, 400)

        order.status = 'paid'
        with self.assertRaises(ValidationError):
            order.save(update_fields=['status'])
        item.status = 'shipped'
        with self.assertRaises(ValidationError):
            item.save(update_fields=['status'])
        with self.assertRaises(ValidationError):
            Order.objects.create(user=self.buyer, total_price=50, status='shipped')

        self.client.force_authenticate(None)
        self.client.force_login(self.staff)
        for model, pk in [('order', order.pk), ('orderitem', item.pk), ('payment', order.payment.get().pk)]:
            self.assertEqual(self.client.post(f'/admin/api/{model}/{pk}/change/', {
                'status': 'shipped', 'verified_at': timezone.now().isoformat(),
            }, secure=True).status_code, 403)
        for action in ('ship_orders', 'deliver_orders'):
            self.client.post('/admin/api/order/', {'action': action, '_selected_action': [order.pk]}, secure=True)
        order.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual((order.status, item.status), ('pending_payment', 'pending'))
        self.assertEqual(order.payment.count(), 1)
        self.assertFalse(order.payment.get().verified_at)
        self.assertFalse(WalletTransaction.objects.exists())

    def test_view_only_staff_cannot_mutate_another_customers_order(self):
        viewer = User.objects.create_user('viewer', 'viewer@example.invalid', is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(content_type__app_label='api', codename='view_order'))
        order = Order.objects.create(user=self.buyer, total_price=50, status='pending_payment')
        url = f'/api/orders/{order.pk}/'
        self.client.force_authenticate(viewer)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.patch(url, {'shipping_address': 'Replacement'}, format='json').status_code, 403)
        self.assertEqual(self.client.post(f'{url}cancel/').status_code, 403)
        self.assertEqual(self.client.delete(url).status_code, 405)
        order.refresh_from_db()
        self.assertEqual(order.status, 'pending_payment')
        self.assertIsNone(order.shipping_address)

    def test_financial_history_is_protected_from_api_admin_and_cascade_deletion(self):
        self.client.force_authenticate(self.buyer)
        created = self.checkout(use_wallet=True)
        self.assertEqual(created.status_code, 201)
        order = Order.objects.get(pk=created.data['order_id'])
        empty = Order.objects.create(user=self.buyer, total_price=50)
        self.staff.user_permissions.add(Permission.objects.get(content_type__app_label='api', codename='delete_order'))
        superuser = User.objects.create_superuser('root', 'root@example.invalid')

        for actor in (None, self.buyer, self.seller, self.staff, self.admin, superuser):
            self.client.force_authenticate(actor)
            for prefix in ('/api/orders/', '/api/secure/api/orders/'):
                with self.subTest(actor=actor, prefix=prefix):
                    self.assertEqual(self.client.delete(f'{prefix}{order.pk}/').status_code, 401 if actor is None else 405)
        self.client.force_authenticate(self.admin)
        for prefix in ('/api/users/', '/api/secure/api/users/'):
            self.assertEqual(self.client.delete(f'{prefix}{self.buyer.pk}/').status_code, 409)

        self.client.force_authenticate(None)
        for actor in (self.staff, superuser):
            self.client.force_login(actor)
            self.assertEqual(self.client.post(f'/admin/api/order/{order.pk}/delete/', {'post': 'yes'},
                                              secure=True).status_code, 403)
            changelist = self.client.get('/admin/api/order/', secure=True)
            self.assertNotContains(changelist, 'value="delete_selected"')
            self.client.post('/admin/api/order/', {
                'action': 'delete_selected', '_selected_action': [order.pk, empty.pk], 'post': 'yes',
            }, secure=True)
            self.assertTrue(Order.objects.filter(pk=empty.pk).exists())
        account_delete = self.client.post(f'/admin/api/user/{self.buyer.pk}/delete/', {'post': 'yes'}, secure=True)
        self.assertEqual(account_delete.status_code, 200)
        with self.assertRaises(ProtectedError):
            Order.objects.filter(pk=order.pk).delete()
        with self.assertRaises(ProtectedError):
            User.objects.filter(pk=self.buyer.pk).delete()

        order.refresh_from_db()
        self.assertEqual(order.status, 'processing')
        self.assertEqual(order.order_items.count(), 1)
        self.assertEqual(order.payment.get().status, 'completed')
        self.assertEqual(WalletTransaction.objects.get(user=self.buyer).reference_id, f'ORDER-{order.pk}')

    def test_contact_can_change_until_first_shipment_and_then_stays_frozen(self):
        self.client.force_authenticate(self.buyer)
        created = self.checkout(use_wallet=True, order_items=[
            {'product': self.product.pk, 'quantity': 1}, {'product': self.second.pk, 'quantity': 1},
        ])
        self.assertEqual(created.status_code, 201)
        order = Order.objects.get(pk=created.data['order_id'])
        url = f'/api/orders/{order.pk}/'
        snapshot = {'shipping_address': 'Corrected address', 'contact_phone': '5550100'}
        self.assertEqual(self.client.patch(url, snapshot, format='json').status_code, 200)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.patch(url, {'contact_phone': '5550101'}, format='json').status_code, 404)

        stale = Order.objects.get(pk=order.pk)
        self.client.force_authenticate(self.seller)
        self.assertEqual(self.vendor_update(order.order_items.get(vendor=self.seller), 'shipped').status_code, 200)
        stale.shipping_address = 'Stale writer'
        with self.assertRaises(ValidationError):
            stale.save(update_fields=['shipping_address'])

        for actor in (self.buyer, self.staff, self.admin):
            self.client.force_authenticate(actor)
            for prefix in ('/api/orders/', '/api/secure/api/orders/'):
                for method in (self.client.put, self.client.patch):
                    self.assertEqual(method(f'{prefix}{order.pk}/', {
                        'shipping_address': 'Replacement', 'contact_phone': '5550102',
                    }, format='json').status_code, 400)
        fulfill_order(order.pk, 'shipped')
        fulfill_order(order.pk, 'delivered')
        self.assertEqual(self.client.patch(url, {'contact_phone': '5550103'}, format='json').status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status, 'delivered')
        self.assertEqual(order.shipping_address, snapshot['shipping_address'])
        self.assertEqual(order.contact_phone, snapshot['contact_phone'])

    def test_cancelled_orders_retain_their_last_pre_fulfillment_contact(self):
        order = Order.objects.create(user=self.buyer, total_price=50, status='pending_payment')
        url = f'/api/orders/{order.pk}/'
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.client.put(url, {'contact_phone': '5550100'}, format='json').status_code, 200)
        self.assertEqual(self.client.post(f'{url}cancel/').status_code, 200)
        self.assertEqual(self.client.patch(url, {'contact_phone': None}, format='json').status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status, 'cancelled')
        self.assertEqual(order.contact_phone, '5550100')

    def test_wallet_mixed_vendor_delivery_and_atomic_rollback(self):
        self.client.force_authenticate(self.buyer)
        result = self.checkout(use_wallet=True, status='delivered', user=self.other.pk, total_price='0.01',
                               order_items=[
                                   {'product': self.product.pk, 'quantity': 1, 'status': 'delivered', 'price': '0.01'},
                                   {'product': self.second.pk, 'quantity': 1, 'status': 'cancelled'},
                               ])
        self.assertEqual(result.status_code, 201, result.data)
        order = Order.objects.get(pk=result.data['order_id'])
        first, second = order.order_items.order_by('pk')
        self.assertEqual((order.user_id, order.total_price, order.status), (self.buyer.pk, 100, 'processing'))
        self.assertEqual((first.status, second.status), ('pending', 'pending'))
        self.assertEqual(WalletTransaction.objects.get().amount, 100)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.vendor_update(first, 'shipped').status_code, 404)
        self.client.force_authenticate(self.seller)
        self.assertEqual(self.vendor_update(first, 'delivered').status_code, 403)
        self.assertEqual(self.vendor_update(first, 'shipped').status_code, 200)
        self.assertEqual(self.vendor_update(first, 'shipped').status_code, 200)

        self.client.force_authenticate(self.admin)
        rejected = self.client.patch(f'/api/orders/{order.pk}/', {'status': 'delivered'}, format='json')
        self.assertEqual(rejected.status_code, 400)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.status, second.status), ('shipped', 'pending'))

        self.client.force_authenticate(self.other)
        self.assertEqual(self.vendor_update(second, 'shipped').status_code, 200)
        self.client.force_authenticate(None)
        self.client.force_login(self.staff)
        self.client.post('/admin/api/order/', {'action': 'deliver_orders', '_selected_action': [order.pk]}, secure=True)
        order.refresh_from_db()
        self.assertEqual(order.status, 'delivered')
        self.assertEqual(set(order.order_items.values_list('status', flat=True)), {'delivered'})

    @patch('razorpay.Client')
    def test_gateway_and_split_require_exact_bound_capture(self, gateway):
        for use_wallet, wallet_amount in ((False, '0.00'), (True, '12.34')):
            with self.subTest(use_wallet=use_wallet):
                self.buyer.wallet_balance = wallet_amount
                self.buyer.save(update_fields=['wallet_balance'])
                self.client.force_authenticate(self.buyer)
                gateway_id = f'order_fixture_{use_wallet}'
                payment_id = f'payment_fixture_{use_wallet}'
                amount = 3766 if use_wallet else 5000
                gateway.return_value.order.create.return_value = {'id': gateway_id, 'amount': amount, 'currency': 'INR'}
                result = self.checkout(use_wallet=use_wallet)
                self.assertEqual(result.status_code, 201, result.data)
                order = Order.objects.get(pk=result.data['order_id'])
                item = order.order_items.get()
                self.client.force_authenticate(self.seller)
                self.assertEqual(self.vendor_update(item, 'shipped').status_code, 404)
                self.client.force_authenticate(self.buyer)
                details = dict(id=payment_id, order_id=gateway_id, amount=amount, currency='INR', status='captured')
                proof = dict(order_id=order.pk, razorpay_payment_id=payment_id,
                             razorpay_order_id=gateway_id, razorpay_signature='fixture')
                verify_url = '/api/orders/verify-razorpay-payment/'
                for invalid in ({'order_id': 'unrelated'}, {'amount': amount - 1}, {'currency': 'USD'}, {'status': 'authorized'}):
                    gateway.return_value.payment.fetch.return_value = {**details, **invalid, 'notes': {'wallet_deducted': '50'}}
                    self.assertEqual(self.client.post(verify_url, proof, format='json').status_code, 400)
                    self.assertFalse(Payment.objects.filter(transaction_id=payment_id).exists())
                gateway.return_value.payment.fetch.return_value = details
                self.assertEqual(self.client.post(verify_url, proof, format='json').status_code, 200)
                self.assertEqual(self.client.post(verify_url, proof, format='json').status_code, 200)
                self.assertEqual(Payment.objects.filter(transaction_id=payment_id, verified_at__isnull=False).count(), 1)
                self.client.force_authenticate(self.seller)
                self.assertEqual(self.vendor_update(item, 'shipped').status_code, 200)

    @patch('razorpay.Client')
    def test_signed_webhook_refunds_cancelled_capture_without_reopening(self, gateway):
        order = Order.objects.create(user=self.buyer, total_price=50, status='cancelled', gateway_order_id='bound')
        item = OrderItem.objects.create(order=order, product=self.product, vendor=self.seller, price=50, status='cancelled')
        payload = {'event': 'payment.captured', 'payload': {'payment': {'entity': {
            'id': 'late', 'order_id': 'bound', 'amount': 5000, 'currency': 'INR', 'status': 'captured',
        }}}}
        for _ in range(2):
            response = self.client.post('/api/webhooks/razorpay/', json.dumps(payload),
                                        content_type='application/json', HTTP_X_RAZORPAY_SIGNATURE='fixture')
            self.assertEqual(response.status_code, 200)
        gateway.return_value.payment.refund.assert_called_once()
        self.assertEqual(order.payment.get().status, 'refund_pending')
        order.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual((order.status, item.status), ('cancelled', 'cancelled'))
        self.client.force_authenticate(self.seller)
        self.assertEqual(self.vendor_update(item, 'shipped').status_code, 404)

    @patch('razorpay.Client')
    def test_refund_before_capture_does_not_enable_shipment(self, gateway):
        self.client.force_authenticate(self.buyer)
        gateway.return_value.order.create.return_value = {'id': 'bound', 'amount': 5000, 'currency': 'INR'}
        created = self.checkout()
        self.assertEqual(created.status_code, 201)
        order = Order.objects.get(pk=created.data['order_id'])
        item = order.order_items.get()
        capture = {'id': 'refunded-first', 'order_id': 'bound', 'amount': 5000, 'currency': 'INR', 'status': 'captured'}
        gateway.return_value.payment.fetch.return_value = {**capture, 'amount_refunded': 5000}
        refund = {'refund': {'entity': {'payment_id': 'refunded-first'}}}

        for event, payload, expected in (
            ('refund.processed', refund, 200),
            ('payment.captured', {'payment': {'entity': capture}}, 400),
        ):
            response = self.client.post('/api/webhooks/razorpay/', json.dumps({'event': event, 'payload': payload}),
                                        content_type='application/json', HTTP_X_RAZORPAY_SIGNATURE='fixture')
            self.assertEqual(response.status_code, expected)
        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(order.status, 'cancelled')
        self.assertEqual(order.payment.get().status, 'refunded')
        self.assertEqual(self.product.stock, 10)
        self.client.force_authenticate(self.seller)
        self.assertEqual(self.vendor_update(item, 'shipped').status_code, 404)


class FulfillmentLockTests(TransactionTestCase):
    @skipUnlessDBFeature('has_select_for_update')
    def test_concurrent_duplicate_shipment_changes_one_line_once(self):
        user = User.objects.create_user('buyer', 'buyer@example.invalid')
        order = Order.objects.create(user=user, total_price=50, status='pending_payment')
        item = OrderItem.objects.create(order=order, price=50)
        Payment.objects.create(order=order, transaction_id='capture', amount=50,
                               status='completed', verified_at=timezone.now())
        order.status = 'paid'
        order.save(update_fields=['status'])
        barrier = Barrier(2, timeout=10)

        def ship():
            close_old_connections()
            try:
                barrier.wait()
                return len(fulfill_order(order.pk, 'shipped', item_id=item.pk)[1])
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            calls = [executor.submit(ship) for _ in range(2)]
            self.assertEqual(sorted(call.result(timeout=15) for call in calls), [0, 1])
        order.refresh_from_db()
        self.assertEqual(order.status, 'shipped')
