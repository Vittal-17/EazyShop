"""Initialization retry identity must include the original commercial request."""
from rest_framework.test import APITestCase
from . import test_purchase_intents as fixtures
from .models import Order, PurchaseIntent


class PurchaseRequestTermsTests(APITestCase):
    setUp = fixtures.PurchaseIntentTests.setUp
    def financial_state(self):
        from .models import OrderItem, GiftCardTransaction, ProviderRefund
        snapshot = fixtures.PurchaseIntentTests.financial_state(self)
        for model in (OrderItem, GiftCardTransaction, ProviderRefund):
            snapshot[model.__name__] = list(model.objects.order_by('pk').values())
        return snapshot

    def merchandise(self, **changes):
        return {'idempotency_key': 'same-key', 'shipping_address': 'Original address', 'contact_phone': '12345',
                'order_items': [{'product': self.product.pk, 'quantity': 1}], **changes}

    def test_same_key_changed_merchandise_terms_conflict(self):
        url = '/api/orders/create-razorpay-order/'
        first = self.client.post(url, self.merchandise(), format='json')
        self.assertEqual(first.status_code, 201)
        before = self.financial_state()
        conflict = self.client.post(url, self.merchandise(shipping_address='Different address'), format='json')
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(self.financial_state(), before)
        self.assertNotIn('razorpay_order_id', conflict.data)
        self.assertEqual(self.gateway.order.create.call_count, 1)

    def test_same_key_changed_gift_denomination_conflicts(self):
        url = '/api/gift-cards/purchase/'
        self.assertEqual(self.client.post(url, {'amount': 50, 'idempotency_key': 'gift-key'}, format='json').status_code, 200)
        before = self.financial_state()
        conflict = self.client.post(url, {'amount': 500, 'idempotency_key': 'gift-key'}, format='json')
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(self.financial_state(), before)
        self.assertNotIn('order_id', conflict.data)
        self.assertEqual(PurchaseIntent.objects.count(), 1)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(self.gateway.order.create.call_count, 1)

    def test_every_changed_merchandise_term_rejected_with_reserved_wallet_unchanged(self):
        from decimal import Decimal
        from .models import Product, WalletTransaction
        other = Product.objects.create(name='Other', price=50, stock=5, approval_status='approved')
        self.buyer.wallet_balance = Decimal('20.00')
        self.buyer.save(update_fields=['wallet_balance'])
        self.gateway.order.create.return_value['amount'] = 3000
        original = self.merchandise(use_wallet=True)
        url = '/api/orders/create-razorpay-order/'
        self.assertEqual(self.client.post(url, original, format='json').status_code, 201)
        for change in (
            {'order_items': [{'product': other.pk, 'quantity': 1}]},
            {'order_items': [{'product': self.product.pk, 'quantity': 2}]},
            {'shipping_address': 'A different address'},
            {'contact_phone': '54321'},
            {'use_wallet': False},
            {'shipping_address': 'original address'},
            {'contact_phone': '+12345'},
        ):
            with self.subTest(change=change):
                before = self.financial_state()
                response = self.client.post(url, {**original, **change}, format='json')
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.data['code'], 'purchase_request_conflict')
                self.assertEqual(self.financial_state(), before)
                self.assertNotIn('razorpay_order_id', response.data)
                self.assertEqual(self.gateway.order.create.call_count, 1)
        self.assertEqual(WalletTransaction.objects.count(), 1)
        self.buyer.refresh_from_db()
        self.assertEqual(self.buyer.wallet_balance, 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 4)

    def test_canonical_equivalent_retries_do_not_debit_or_reserve_again(self):
        from .models import Product, WalletTransaction
        other = Product.objects.create(name='Other', price=50, stock=5, approval_status='approved')
        self.buyer.wallet_balance = 20
        self.buyer.save(update_fields=['wallet_balance'])
        self.gateway.order.create.return_value['amount'] = 13000
        first_terms = self.merchandise(use_wallet=True, shipping_address='  Café\r\nUnit 1  ', contact_phone=' 12345 ',
            order_items=[{'product': other.pk, 'quantity': 1}, {'product': self.product.pk, 'quantity': 1}, {'product': self.product.pk, 'quantity': 1}])
        url = '/api/orders/create-razorpay-order/'
        first = self.client.post(url, first_terms, format='json')
        self.assertEqual(first.status_code, 201)
        equivalent = self.merchandise(use_wallet=True, shipping_address='Cafe\u0301\nUnit 1',
            order_items=[{'product': self.product.pk, 'quantity': 2, 'price': -1}, {'product': other.pk, 'quantity': 1}], total_price=1)
        before = self.financial_state()
        for _ in range(2):
            retry = self.client.post(url, equivalent, format='json')
            self.assertEqual(retry.status_code, 201)
            self.assertEqual(retry.data, first.data)
            self.assertEqual(self.financial_state(), before)
        self.assertEqual(PurchaseIntent.objects.count(), 1)
        self.assertEqual(self.gateway.order.create.call_count, 1)
        self.assertEqual(WalletTransaction.objects.count(), 1)
        order = Order.objects.get()
        self.assertEqual(order.shipping_address, 'Café\nUnit 1')
        self.assertEqual(order.contact_phone, '12345')

    def test_gift_minor_unit_equivalents_retry_one_intent(self):
        url = '/api/gift-cards/purchase/'
        first = self.client.post(url, {'amount': '50.00', 'idempotency_key': 'gift'}, format='json')
        self.assertEqual(first.status_code, 200)
        before = self.financial_state()
        for amount in (50, 50.0, '050.000', '5E1', ' 50.00 '):
            retry = self.client.post(url, {'amount': amount, 'idempotency_key': 'gift'}, format='json')
            self.assertEqual(retry.status_code, 200)
            self.assertEqual(retry.data, first.data)
            self.assertEqual(self.financial_state(), before)
        self.assertEqual(self.gateway.order.create.call_count, 1)
        self.assertEqual(PurchaseIntent.objects.count(), 1)

    def test_omitted_wallet_choice_equals_false_but_true_conflicts_with_zero_balance(self):
        url = '/api/orders/create-razorpay-order/'
        original = self.client.post(url, self.merchandise(), format='json')
        self.assertEqual(original.status_code, 201)
        before = self.financial_state()
        self.assertEqual(self.client.post(url, self.merchandise(use_wallet=False), format='json').data, original.data)
        self.assertEqual(self.client.post(url, self.merchandise(use_wallet=True), format='json').status_code, 409)
        self.assertEqual(self.financial_state(), before)
        self.assertEqual(self.gateway.order.create.call_count, 1)

    def test_original_fingerprint_survives_price_stock_and_contact_edits(self):
        url = '/api/orders/create-razorpay-order/'
        original = self.client.post(url, self.merchandise(), format='json')
        self.assertEqual(original.status_code, 201)
        order = Order.objects.get()
        self.assertEqual(self.client.patch(f'/api/orders/{order.pk}/', {'shipping_address': 'Approved later edit'}, format='json').status_code, 200)
        self.product.price = 500
        self.product.stock = 0
        self.product.save(update_fields=['price', 'stock'])
        before = self.financial_state()
        self.assertEqual(self.client.post(url, self.merchandise(), format='json').data, original.data)
        self.assertEqual(self.client.post(url, self.merchandise(shipping_address='Approved later edit'), format='json').status_code, 409)
        self.assertEqual(self.financial_state(), before)
        self.assertEqual(self.gateway.order.create.call_count, 1)

    def test_failed_attempt_and_unknown_outcomes_preserve_binding(self):
        url = '/api/orders/create-razorpay-order/'
        original = self.client.post(url, self.merchandise(), format='json')
        self.assertEqual(original.status_code, 201)
        self.assertEqual(fixtures.PurchaseIntentTests.webhook(self, 'payment.failed', {**self.capture, 'status': 'failed'}).status_code, 200)
        self.assertEqual(self.client.post(url, self.merchandise(), format='json').data, original.data)
        before = self.financial_state()
        self.assertEqual(self.client.post(url, self.merchandise(contact_phone='999'), format='json').status_code, 409)
        self.assertEqual(self.financial_state(), before)
        self.gateway.order.create.side_effect = TimeoutError('Unknown provider order creation')
        self.assertEqual(self.client.post('/api/gift-cards/purchase/', {'amount': 50, 'idempotency_key': 'unknown'}, format='json').status_code, 503)
        before = self.financial_state()
        same = self.client.post('/api/gift-cards/purchase/', {'amount': 50, 'idempotency_key': 'unknown'}, format='json')
        self.assertEqual(same.status_code, 409)
        self.assertNotEqual(same.data.get('code'), 'purchase_request_conflict')
        changed = self.client.post('/api/gift-cards/purchase/', {'amount': 500, 'idempotency_key': 'unknown'}, format='json')
        self.assertEqual(changed.status_code, 409)
        self.assertEqual(changed.data['code'], 'purchase_request_conflict')
        self.assertEqual(self.financial_state(), before)
        self.assertEqual(self.gateway.order.create.call_count, 2)

    def test_settled_wallet_and_gateway_retries_validate_original_terms(self):
        url = '/api/orders/create-razorpay-order/'
        self.buyer.wallet_balance = 50
        self.buyer.save(update_fields=['wallet_balance'])
        terms = self.merchandise(use_wallet=True)
        original = self.client.post(url, terms, format='json')
        self.assertTrue(original.data['payment_complete'])
        before = self.financial_state()
        retry = self.client.post(url, terms, format='json')
        self.assertEqual(retry.status_code, 201)
        self.assertTrue(retry.data['payment_complete'])
        self.assertEqual(retry.data['order_id'], original.data['order_id'])
        self.assertEqual(self.client.post(url, {**terms, 'use_wallet': False}, format='json').status_code, 409)
        self.assertEqual(self.financial_state(), before)
        self.gateway.order.create.assert_not_called()
        terms = self.merchandise(idempotency_key='gateway')
        created = self.client.post(url, terms, format='json')
        self.assertEqual(created.status_code, 201)
        proof = fixtures.PurchaseIntentTests.proof(self)
        self.assertEqual(self.client.post('/api/orders/verify-razorpay-payment/', {**proof, 'order_id': created.data['order_id']}, format='json').status_code, 200)
        before = self.financial_state()
        retry = self.client.post(url, terms, format='json')
        self.assertEqual(retry.status_code, 201)
        self.assertTrue(retry.data['payment_complete'])
        self.assertEqual(self.client.post(url, {**terms, 'contact_phone': '999'}, format='json').status_code, 409)
        self.assertEqual(self.financial_state(), before)
        self.assertEqual(self.gateway.order.create.call_count, 1)

    def test_settled_gift_recovers_original_card_only_for_matching_amount(self):
        url = '/api/gift-cards/purchase/'
        original = self.client.post(url, {'amount': 50, 'idempotency_key': 'gift'}, format='json')
        self.assertEqual(original.status_code, 200)
        proof = fixtures.PurchaseIntentTests.proof(self)
        issued = self.client.post('/api/gift-cards/verify/', proof, format='json')
        self.assertEqual(issued.status_code, 201)
        before = self.financial_state()
        retry = self.client.post(url, {'amount': '50.00', 'idempotency_key': 'gift'}, format='json')
        self.assertEqual(retry.status_code, 200)
        self.assertTrue(retry.data['payment_complete'])
        self.assertEqual(retry.data['gift_card_id'], issued.data['gift_card_id'])
        self.assertEqual(retry.data['order_id'], original.data['order_id'])
        changed = self.client.post(url, {'amount': 51, 'idempotency_key': 'gift'}, format='json')
        self.assertEqual(changed.status_code, 409)
        self.assertNotIn('gift_card_id', changed.data)
        self.assertEqual(self.financial_state(), before)
        self.assertEqual(self.gateway.order.create.call_count, 1)

    def test_malformed_snapshot_and_wallet_fields_are_not_coerced(self):
        for fields in ({'shipping_address': []}, {'shipping_address': '   '}, {'contact_phone': 12345},
                       {'use_wallet': 'false'}, {'use_wallet': 1}, {'contact_phone': '1' * 21}):
            before = self.financial_state()
            response = self.client.post('/api/orders/create-razorpay-order/', self.merchandise(**fields), format='json')
            self.assertEqual(response.status_code, 400)
            self.assertEqual(self.financial_state(), before)
        self.gateway.order.create.assert_not_called()

    def test_fingerprint_is_immutable_through_model_and_bulk_updates(self):
        from django.core.exceptions import ValidationError
        from django.db import IntegrityError, transaction
        self.assertEqual(self.client.post('/api/orders/create-razorpay-order/', self.merchandise(), format='json').status_code, 201)
        intent = PurchaseIntent.objects.get()
        original = intent.request_fingerprint
        self.assertEqual(len(original), 64)
        intent.request_fingerprint = 'a' * 64
        with self.assertRaises(ValidationError):
            intent.save(update_fields=['request_fingerprint'])
        with self.assertRaises(IntegrityError), transaction.atomic():
            PurchaseIntent.objects.filter(pk=intent.pk).update(request_fingerprint='b' * 64)
        intent.refresh_from_db()
        self.assertEqual(intent.request_fingerprint, original)

    def test_pre_migration_merchandise_fails_closed_and_gift_uses_immutable_amount(self):
        legacy_order = Order.objects.create(user=self.buyer, total_price=50, status='pending_payment')
        PurchaseIntent.objects.create(order=legacy_order, purchaser=self.buyer, purpose='merchandise',
            expected_amount=5000, provider_order_id='legacy', state='pending', idempotency_key='same-key')
        before = self.financial_state()
        response = self.client.post('/api/orders/create-razorpay-order/', self.merchandise(), format='json')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['code'], 'purchase_request_unverifiable')
        self.assertEqual(self.financial_state(), before)
        PurchaseIntent.objects.create(purchaser=self.buyer, purpose='gift_card', expected_amount=5000,
            provider_order_id='legacy_gift', state='pending', idempotency_key='gift')
        before = self.financial_state()
        retry = self.client.post('/api/gift-cards/purchase/', {'amount': '50.00', 'idempotency_key': 'gift'}, format='json')
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.data['order_id'], 'legacy_gift')
        self.assertEqual(self.client.post('/api/gift-cards/purchase/', {'amount': 51, 'idempotency_key': 'gift'}, format='json').status_code, 409)
        self.assertEqual(self.financial_state(), before)
        self.gateway.order.create.assert_not_called()


from django.test import TransactionTestCase
from django.db import connections
from unittest.mock import patch
from rest_framework.test import APIClient
from .models import Product, WalletTransaction, Payment, ProviderPaymentClaim, GiftCard


class RequestTermsConcurrencyTests(TransactionTestCase):
    setUp = fixtures.PurchaseIntentConcurrencyTests.setUp
    race = fixtures.PurchaseIntentConcurrencyTests.race

    def test_concurrent_conflicting_merchandise_retry_has_only_one_reservation(self):
        product = Product.objects.create(name='Fixture', price=50, stock=5, approval_status='approved')
        self.buyer.wallet_balance = 20
        self.buyer.save(update_fields=['wallet_balance'])
        def purchase(quantity):
            client = APIClient()
            client.force_authenticate(self.buyer)
            response = client.post('/api/orders/create-razorpay-order/', {
                'idempotency_key': 'race', 'shipping_address': 'Fixture', 'contact_phone': '123', 'use_wallet': True,
                'order_items': [{'product': product.pk, 'quantity': quantity}],
            }, format='json')
            return response.status_code, response.data
        with patch('api.views.razorpay.Client') as gateway:
            def create(data, **kwargs):
                self.assertFalse(connections['default'].in_atomic_block)
                return {'id': 'order_race', 'amount': data['amount'], 'currency': 'INR'}
            gateway.return_value.order.create.side_effect = create
            results = self.race([lambda: purchase(1), lambda: purchase(2)])
            self.assertEqual(sorted(code for code, _ in results), [201, 409])
            conflict = next(data for code, data in results if code == 409)
            self.assertEqual(conflict['code'], 'purchase_request_conflict')
            self.assertNotIn('razorpay_order_id', conflict)
            self.assertEqual(gateway.return_value.order.create.call_count, 1)
        self.assertEqual(PurchaseIntent.objects.count(), 1)
        self.assertEqual(Order.objects.count(), 1)
        winner = Order.objects.get()
        quantity = winner.order_items.get().quantity
        product.refresh_from_db()
        self.buyer.refresh_from_db()
        self.assertEqual(product.stock, 5 - quantity)
        self.assertEqual(self.buyer.wallet_balance, 0)
        self.assertEqual(WalletTransaction.objects.count(), 1)
        self.assertEqual(WalletTransaction.objects.get().amount, 20)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertFalse(ProviderPaymentClaim.objects.exists())
        self.assertEqual(PurchaseIntent.objects.get().expected_amount, quantity * 5000 - 2000)

    def test_concurrent_conflicting_gift_denominations_create_one_provider_order(self):
        def purchase(amount):
            client = APIClient()
            client.force_authenticate(self.buyer)
            response = client.post('/api/gift-cards/purchase/', {'amount': amount, 'idempotency_key': 'race'}, format='json')
            return response.status_code, response.data
        with patch('api.views.razorpay.Client') as gateway:
            gateway.return_value.order.create.side_effect = lambda data, **kwargs: {
                'id': 'order_gift_race', 'amount': data['amount'], 'currency': 'INR'}
            results = self.race([lambda: purchase('50.00'), lambda: purchase('75.00')])
            self.assertEqual(sorted(code for code, _ in results), [200, 409])
            conflict = next(data for code, data in results if code == 409)
            self.assertEqual(conflict['code'], 'purchase_request_conflict')
            self.assertNotIn('order_id', conflict)
            self.assertEqual(gateway.return_value.order.create.call_count, 1)
        intent = PurchaseIntent.objects.get()
        self.assertIn(intent.expected_amount, (5000, 7500))
        self.assertEqual(intent.provider_order_id, 'order_gift_race')
        self.assertFalse(Order.objects.exists())
        self.assertFalse(Payment.objects.exists())
        self.assertFalse(WalletTransaction.objects.exists())
        self.assertFalse(ProviderPaymentClaim.objects.exists())
        self.assertFalse(GiftCard.objects.exists())


class RequestFingerprintMigrationTests(TransactionTestCase):
    def test_additive_fingerprint_migration_does_not_invent_original_terms(self):
        from django.db.migrations.executor import MigrationExecutor
        from django.db import IntegrityError, transaction
        connection = connections['default']
        self.assertEqual(connection.settings_dict['NAME'], 'eazyshop_test')
        old_target = [('api', '0027_processed_refund_evidence')]
        new_target = [('api', '0028_purchase_request_fingerprint')]
        MigrationExecutor(connection).migrate(old_target)
        try:
            old = MigrationExecutor(connection).loader.project_state(old_target).apps
            user = old.get_model('api', 'User').objects.create(username='migration', email='migration@example.invalid')
            order = old.get_model('api', 'Order').objects.create(user_id=user.pk, total_price=50, shipping_address='Snapshot', status='pending_payment')
            intent = old.get_model('api', 'PurchaseIntent').objects.create(purchaser_id=user.pk, purpose='merchandise',
                order_id=order.pk, expected_amount=5000, provider_order_id='existing', state='pending', idempotency_key='old')
            MigrationExecutor(connection).migrate(new_target)
            self.assertIsNone(PurchaseIntent.objects.get().request_fingerprint)
            with self.assertRaises(IntegrityError), transaction.atomic():
                PurchaseIntent.objects.filter(pk=intent.pk).update(request_fingerprint='a' * 64)
            MigrationExecutor(connection).migrate(old_target)
            self.assertEqual(old.get_model('api', 'PurchaseIntent').objects.get().expected_amount, 5000)
            self.assertEqual(old.get_model('api', 'Order').objects.get().shipping_address, 'Snapshot')
        finally:
            MigrationExecutor(connection).migrate(new_target)
        self.assertIsNone(PurchaseIntent.objects.get().request_fingerprint)
