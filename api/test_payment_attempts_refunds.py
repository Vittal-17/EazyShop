"""Signed attempt/refund regressions using isolated provider fakes."""
from decimal import Decimal

from rest_framework.test import APITestCase
from . import test_purchase_intents as fixtures
from .models import Order, Payment, GiftCard, GiftCardTransaction, PurchaseIntent, ProviderPaymentClaim, WalletTransaction


class AttemptRefundTests(APITestCase):
    setUp = fixtures.PurchaseIntentTests.setUp
    proof = fixtures.PurchaseIntentTests.proof
    checkout = fixtures.PurchaseIntentTests.checkout
    gift_purchase = fixtures.PurchaseIntentTests.gift_purchase
    verify = fixtures.PurchaseIntentTests.verify
    webhook = fixtures.PurchaseIntentTests.webhook
    def financial_state(self):
        from .models import ProviderRefund, OrderItem
        state = fixtures.PurchaseIntentTests.financial_state(self)
        for model in (ProviderRefund, OrderItem, GiftCardTransaction):
            state[model.__name__] = list(model.objects.order_by('pk').values())
        return state

    def refund(self, refund_id='rfnd_one', amount=1000, cumulative=1000, **fields):
        self.gateway.payment.fetch.return_value = {**self.capture, 'amount_refunded': cumulative,
            'status': 'refunded' if cumulative == self.capture['amount'] else 'captured'}
        entity = {'id': refund_id, 'payment_id': self.capture['id'], 'currency': 'INR',
                  'amount': amount, 'status': 'processed', **fields}
        return self.webhook('refund.processed', payload={'refund': {'entity': entity}})

    def test_failed_attempt_then_capture_settles_merchandise_once(self):
        data = self.checkout()
        self.assertEqual(self.webhook('payment.failed', {**self.capture, 'status': 'failed'}).status_code, 200)
        self.assertEqual(self.webhook().status_code, 200)
        order = Order.objects.get(pk=data['order_id'])
        self.assertEqual(order.status, 'paid')
        self.assertEqual(self.webhook().status_code, 200)
        self.assertEqual(ProviderPaymentClaim.objects.count(), 1)
        self.assertEqual(Payment.objects.filter(status='completed').count(), 1)
        self.assertFalse(WalletTransaction.objects.exists())

    def test_failed_attempt_then_capture_issues_one_gift(self):
        self.gift_purchase()
        self.assertEqual(self.webhook('payment.failed', {**self.capture, 'status': 'failed'}).status_code, 200)
        self.assertEqual(self.webhook().status_code, 200)
        self.assertEqual(self.webhook().status_code, 200)
        self.assertEqual(PurchaseIntent.objects.get().state, 'settled')
        self.assertEqual(GiftCard.objects.count(), 1)
        self.assertEqual(GiftCardTransaction.objects.filter(transaction_type='ISSUE').count(), 1)
        self.assertEqual(ProviderPaymentClaim.objects.count(), 1)
        self.assertFalse(WalletTransaction.objects.exists())

    def split_checkout(self):
        self.buyer.wallet_balance = Decimal('20.00')
        self.buyer.save(update_fields=['wallet_balance'])
        self.gateway.order.create.return_value = {'id': 'order_fixture', 'amount': 3000, 'currency': 'INR'}
        response = self.client.post('/api/orders/create-razorpay-order/', {
            'shipping_address': 'Fixture', 'contact_phone': '123', 'use_wallet': True,
            'order_items': [{'product': self.product.pk, 'quantity': 1}],
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.capture['amount'] = 3000
        self.assertEqual(self.verify(response.data).status_code, 200)
        return Order.objects.get(pk=response.data['order_id'])

    def test_partial_refund_does_not_reverse_order_or_credit_wallet(self):
        order = self.split_checkout()
        self.assertEqual(self.refund(amount=1000, cumulative=1000).status_code, 200)
        order.refresh_from_db()
        self.buyer.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(order.status, 'paid')
        self.assertEqual(order.order_items.get().status, 'pending')
        self.assertEqual(self.product.stock, 4)
        self.assertEqual(self.buyer.wallet_balance, 0)
        self.assertEqual(PurchaseIntent.objects.get().state, 'reconciliation')
        self.assertEqual(ProviderPaymentClaim.objects.get().state, 'refund_pending')
        self.assertEqual(order.payment.exclude(payment_method='wallet').get().status, 'refund_pending')
        self.assertEqual(order.payment.get(payment_method='wallet').status, 'completed')
        self.assertEqual(WalletTransaction.objects.count(), 1)

    def test_multiple_failed_attempts_and_reordered_failure_keep_same_purchase(self):
        data = self.checkout()
        for payment_id in ('pay_first', 'pay_second', 'pay_second'):
            self.assertEqual(self.webhook('payment.failed', {**self.capture, 'id': payment_id, 'status': 'failed'}).status_code, 200)
            self.assertEqual(PurchaseIntent.objects.get().state, 'pending')
            self.assertFalse(ProviderPaymentClaim.objects.exists())
            self.product.refresh_from_db()
            self.assertEqual(self.product.stock, 4)
        self.assertEqual(self.verify(data).status_code, 200)
        self.assertEqual(self.webhook('payment.failed', {**self.capture, 'status': 'failed'}).status_code, 200)
        self.assertEqual(self.webhook().status_code, 200)
        self.assertEqual(self.verify(data).status_code, 200)
        self.assertEqual(Payment.objects.filter(status='completed').count(), 1)
        self.assertEqual(PurchaseIntent.objects.get().state, 'settled')

    def test_explicit_cancellation_before_late_capture_never_reactivates(self):
        data = self.checkout()
        self.assertEqual(self.webhook('payment.failed', {**self.capture, 'status': 'failed'}).status_code, 200)
        self.assertEqual(self.client.post(f"/api/orders/{data['order_id']}/cancel/").status_code, 200)
        for _ in range(2):
            self.assertEqual(self.webhook().status_code, 200)
        self.assertEqual(Order.objects.get().status, 'cancelled')
        self.assertEqual(Payment.objects.get().status, 'refund_pending')
        self.assertEqual(ProviderPaymentClaim.objects.get().state, 'refund_pending')
        self.gateway.payment.refund.assert_called_once()
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)
        self.assertFalse(WalletTransaction.objects.exists())

    def test_multiple_partials_duplicate_and_cumulative_full_reverse_once(self):
        from .models import ProviderRefund
        order = self.split_checkout()
        for refund_id, amount, cumulative in [('rfnd_a', 1000, 1000), ('rfnd_a', 1000, 1000), ('rfnd_b', 500, 1500)]:
            self.assertEqual(self.refund(refund_id, amount, cumulative).status_code, 200)
            order.refresh_from_db()
            self.product.refresh_from_db()
            self.buyer.refresh_from_db()
            self.assertEqual((order.status, self.product.stock, self.buyer.wallet_balance), ('paid', 4, 0))
            self.assertFalse(WalletTransaction.objects.filter(transaction_type='REFUND_ORDER').exists())
            self.assertEqual(self.client.post(f'/api/orders/{order.pk}/cancel/').status_code, 409)
        self.assertEqual(ProviderRefund.objects.count(), 2)
        for _ in range(2):
            self.assertEqual(self.refund('rfnd_c', 1500, 3000).status_code, 200)
        order.refresh_from_db()
        self.product.refresh_from_db()
        self.buyer.refresh_from_db()
        self.assertEqual((order.status, self.product.stock, self.buyer.wallet_balance), ('cancelled', 5, 20))
        self.assertEqual(ProviderRefund.objects.count(), 3)
        self.assertEqual(order.order_items.get().status, 'cancelled')
        self.assertEqual(PurchaseIntent.objects.get().state, 'refunded')
        self.assertEqual(ProviderPaymentClaim.objects.get().state, 'refunded')
        self.assertEqual(order.payment.filter(status='refunded').count(), 2)
        self.assertEqual(WalletTransaction.objects.filter(transaction_type='REFUND_ORDER').count(), 1)
        self.assertEqual(self.verify({'order_id': order.pk}).status_code, 400)
        self.assertEqual(self.webhook().status_code, 400)

    def test_full_provider_counter_alone_is_not_itemized_refund_evidence(self):
        from .models import ProviderRefund
        order = self.split_checkout()
        self.assertEqual(self.refund('rfnd_last', 2000, 3000).status_code, 200)
        self.assertEqual(PurchaseIntent.objects.get().state, 'reconciliation')
        self.assertEqual(Order.objects.get().status, 'paid')
        # Earlier refund arrives with an older provider snapshot. No double count.
        self.assertEqual(self.refund('rfnd_first', 1000, 1000).status_code, 200)
        self.assertEqual(PurchaseIntent.objects.get().state, 'refunded')
        self.assertEqual(ProviderRefund.objects.count(), 2)
        self.assertEqual(WalletTransaction.objects.filter(transaction_type='REFUND_ORDER').count(), 1)
        self.assertEqual(self.refund('rfnd_first', 1000, 3000).status_code, 200)
        self.assertEqual(ProviderRefund.objects.count(), 2)

    def test_malformed_refunds_leave_all_financial_state_unchanged(self):
        from .models import ProviderRefund
        self.split_checkout()
        invalid = [({'amount': value}, 1000) for value in (None, True, '1000', 0, -1, 3001)]
        invalid += [({'currency': 'USD'}, 1000), ({'status': 'pending'}, 1000), ({'id': ''}, 1000),
                    ({'payment_id': 'foreign'}, 1000), ({}, True), ({}, -1), ({}, 999), ({}, 3001)]
        for fields, cumulative in invalid:
            with self.subTest(fields=fields, cumulative=cumulative):
                before = self.financial_state()
                response = self.refund(cumulative=cumulative, **fields)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.financial_state(), before)
                self.assertFalse(ProviderRefund.objects.exists())
        for bad in ({'currency': 'USD'}, {'order_id': 'unrelated'}, {'amount': 2999}, {'status': 'failed'}):
            self.gateway.payment.fetch.return_value = {**self.capture, 'amount_refunded': 1000, **bad}
            before = self.financial_state()
            response = self.webhook('refund.processed', payload={'refund': {'entity': {
                'id': 'bad_fetch', 'payment_id': self.capture['id'], 'amount': 1000, 'currency': 'INR', 'status': 'processed'}}})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(self.financial_state(), before)
            self.assertFalse(ProviderRefund.objects.exists())

    def test_refund_id_conflicts_and_excess_cumulative_sum_roll_back(self):
        from .models import ProviderRefund
        self.split_checkout()
        self.assertEqual(self.refund('rfnd_one', 1000, 1000).status_code, 200)
        for refund_id, amount, cumulative in [('rfnd_one', 2000, 3000), ('rfnd_extra', 2500, 3000), ('rfnd_extra', 1000, 1000)]:
            before = self.financial_state()
            self.assertEqual(self.refund(refund_id, amount, cumulative).status_code, 400)
            self.assertEqual(self.financial_state(), before)
            self.assertEqual(ProviderRefund.objects.count(), 1)

    def test_gift_partials_freeze_without_erasing_balance_or_crediting_wallet(self):
        from .models import ProviderRefund
        self.gift_purchase()
        issued = self.verify()
        for refund_id, amount, cumulative in [('rfnd_a', 2000, 2000), ('rfnd_a', 2000, 2000), ('rfnd_b', 3000, 5000)]:
            self.assertEqual(self.refund(refund_id, amount, cumulative).status_code, 200)
            card = GiftCard.objects.get()
            self.assertFalse(card.is_active)
            self.assertEqual(card.current_balance, 50)
            self.assertEqual(card.initial_balance, 50)
            self.assertEqual(self.client.post('/api/gift-cards/redeem/', {'gift_card_id': issued.data['gift_card_id']}, format='json').status_code, 400)
            self.assertEqual(GiftCardTransaction.objects.filter(transaction_type='ISSUE').count(), 1)
            self.assertFalse(WalletTransaction.objects.exists())
        self.assertEqual(PurchaseIntent.objects.get().state, 'refunded')
        self.assertEqual(ProviderPaymentClaim.objects.get().state, 'refunded')
        self.assertEqual(ProviderRefund.objects.count(), 2)
        self.assertEqual(self.verify().status_code, 400)

    def test_partial_before_capture_never_issues_value_and_full_closes_purchase(self):
        self.gift_purchase()
        self.assertEqual(self.refund('rfnd_a', 1000, 1000).status_code, 200)
        self.assertFalse(GiftCard.objects.exists())
        self.assertEqual(self.webhook().status_code, 409)
        self.assertEqual(self.refund('rfnd_b', 4000, 5000).status_code, 200)
        self.assertEqual(PurchaseIntent.objects.get().state, 'refunded')
        self.assertFalse(GiftCard.objects.exists())
        self.assertFalse(WalletTransaction.objects.exists())

    def test_unknown_refund_fetch_is_retryable_without_financial_changes(self):
        self.split_checkout()
        before = self.financial_state()
        self.gateway.payment.fetch.side_effect = TimeoutError('isolated timeout')
        self.assertEqual(self.refund().status_code, 503)
        self.assertEqual(self.financial_state(), before)
        self.gateway.payment.fetch.side_effect = None
        self.assertEqual(self.refund().status_code, 200)

    def test_retry_key_after_failed_attempt_returns_original_pending_purchase(self):
        purchase = self.gift_purchase(key='same-request')
        self.assertEqual(self.webhook('payment.failed', {**self.capture, 'status': 'failed'}).status_code, 200)
        retry = self.client.post('/api/gift-cards/purchase/', {'amount': 50, 'idempotency_key': 'same-request'}, format='json')
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.data['order_id'], purchase['order_id'])
        self.assertEqual(self.gateway.order.create.call_count, 1)
        self.assertEqual(self.verify().status_code, 201)

    def test_partial_refund_failure_rolls_back_evidence_and_all_financial_writes(self):
        from unittest.mock import patch
        from .models import ProviderRefund
        self.split_checkout()
        before = self.financial_state()
        with patch('api.refunds.PurchaseIntent.save', side_effect=RuntimeError('fixture local failure')):
            self.assertEqual(self.refund().status_code, 503)
        self.assertEqual(self.financial_state(), before)
        self.assertFalse(ProviderRefund.objects.exists())
        self.assertEqual(self.refund().status_code, 200)
        self.assertEqual(ProviderRefund.objects.count(), 1)

    def test_complete_refund_failure_does_not_partially_reverse_stock_or_wallet(self):
        from unittest.mock import patch
        from .models import ProviderRefund
        self.split_checkout()
        before = self.financial_state()
        with patch('api.refunds.record_wallet_transaction', side_effect=RuntimeError('fixture ledger failure')):
            self.assertEqual(self.refund(amount=3000, cumulative=3000).status_code, 503)
        self.assertEqual(self.financial_state(), before)
        self.assertFalse(ProviderRefund.objects.exists())
        self.assertEqual(self.refund(amount=3000, cumulative=3000).status_code, 200)
        self.assertEqual(WalletTransaction.objects.filter(transaction_type='REFUND_ORDER').count(), 1)

    def test_duplicate_refund_id_cannot_move_to_another_purchase(self):
        self.split_checkout()
        self.assertEqual(self.refund('global_refund', 1000, 1000).status_code, 200)
        self.gift_purchase()
        self.capture['amount'] = 5000
        self.gateway.payment.fetch.return_value = self.capture
        self.assertEqual(self.verify().status_code, 201)
        before = self.financial_state()
        self.assertEqual(self.refund('global_refund', 1000, 1000).status_code, 400)
        self.assertEqual(self.financial_state(), before)

    def test_refunds_after_redemption_preserve_spent_value_for_reconciliation(self):
        self.gift_purchase()
        issued = self.verify()
        self.assertEqual(self.client.post('/api/gift-cards/redeem/', {'gift_card_id': issued.data['gift_card_id']}, format='json').status_code, 200)
        for refund_id, amount, cumulative in [('rfnd_part', 1000, 1000), ('rfnd_rest', 4000, 5000)]:
            self.assertEqual(self.refund(refund_id, amount, cumulative).status_code, 200)
            self.buyer.refresh_from_db()
            self.assertEqual(self.buyer.wallet_balance, 50)
            self.assertEqual(PurchaseIntent.objects.get().state, 'reconciliation')
            self.assertEqual(GiftCard.objects.get().current_balance, 0)
            self.assertEqual(WalletTransaction.objects.count(), 1)
        self.assertEqual(ProviderPaymentClaim.objects.get().state, 'refunded')
        self.assertEqual(self.verify().status_code, 400)



from django.test import TransactionTestCase
from django.db import connections
from unittest.mock import patch
from rest_framework.test import APIClient
from django.conf import settings
import hashlib
import hmac
import json
import razorpay


class AttemptRefundConcurrencyTests(TransactionTestCase):
    setUp = fixtures.PurchaseIntentConcurrencyTests.setUp
    fixture = fixtures.PurchaseIntentConcurrencyTests.fixture
    race = fixtures.PurchaseIntentConcurrencyTests.race

    def signed(self, event, entity, kind='payment'):
        body = json.dumps({'event': event, 'payload': {kind: {'entity': entity}}})
        signature = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
        return APIClient().post('/api/webhooks/razorpay/', body, content_type='application/json', HTTP_X_RAZORPAY_SIGNATURE=signature).status_code

    def sdk_utility(self):
        return razorpay.utility.utility.Utility(type('Client', (), {'auth': (settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)})())

    def test_failed_attempt_followed_by_browser_webhook_race_for_each_purpose(self):
        for purpose in ('merchandise', 'gift_card'):
            intent, entity = self.fixture(purpose, purpose)
            with patch('api.views.razorpay.Client') as gateway, patch('api.views.async_notify_vendors'):
                gateway.return_value.utility = self.sdk_utility()
                gateway.return_value.payment.fetch.return_value = entity
                self.assertEqual(self.signed('payment.failed', {**entity, 'status': 'failed'}), 200)
                proof = {'razorpay_order_id': intent.provider_order_id, 'razorpay_payment_id': entity['id'],
                    'order_id': intent.order_id, 'razorpay_signature': hmac.new(settings.RAZORPAY_KEY_SECRET.encode(),
                        f"{intent.provider_order_id}|{entity['id']}".encode(), hashlib.sha256).hexdigest()}
                def browser():
                    client = APIClient()
                    client.force_authenticate(self.buyer)
                    url = '/api/orders/verify-razorpay-payment/' if purpose == 'merchandise' else '/api/gift-cards/verify/'
                    return client.post(url, proof, format='json').status_code
                self.assertEqual(self.race([browser, lambda: self.signed('payment.captured', entity)]),
                                 [200 if purpose == 'merchandise' else 201, 200])
                self.assertEqual(self.signed('payment.failed', {**entity, 'status': 'failed'}), 200)
                self.assertEqual(self.signed('payment.captured', entity), 200)
            intent.refresh_from_db()
            self.assertEqual(intent.state, 'settled')
            self.assertEqual(ProviderPaymentClaim.objects.filter(intent=intent).count(), 1)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(GiftCard.objects.count(), 1)
        self.assertEqual(GiftCardTransaction.objects.filter(transaction_type='ISSUE').count(), 1)
        self.assertFalse(WalletTransaction.objects.exists())

    def test_concurrent_duplicate_partials_and_full_refund_credit_wallet_once(self):
        from .models import Product, ProviderRefund
        self.buyer.wallet_balance = 20
        self.buyer.save(update_fields=['wallet_balance'])
        product = Product.objects.create(name='Fixture', price=50, stock=5, approval_status='approved')
        client = APIClient()
        client.force_authenticate(self.buyer)
        entity = {'id': 'pay_race', 'order_id': 'order_race', 'amount': 3000, 'currency': 'INR', 'status': 'captured'}
        with patch('api.views.razorpay.Client') as gateway, patch('api.views.async_notify_vendors'):
            gateway.return_value.utility = self.sdk_utility()
            gateway.return_value.order.create.return_value = {'id': 'order_race', 'amount': 3000, 'currency': 'INR'}
            self.assertEqual(client.post('/api/orders/create-razorpay-order/', {
                'shipping_address': 'Fixture', 'contact_phone': '123', 'use_wallet': True,
                'order_items': [{'product': product.pk, 'quantity': 1}],
            }, format='json').status_code, 201)
            self.assertEqual(self.signed('payment.captured', entity), 200)
            for refund_id, amount, cumulative in [('rfnd_first', 1000, 1000), ('rfnd_second', 2000, 3000)]:
                refund = {'id': refund_id, 'payment_id': entity['id'], 'amount': amount, 'currency': 'INR', 'status': 'processed'}
                def fetch(*args, **kwargs):
                    self.assertFalse(connections['default'].in_atomic_block)
                    return {**entity, 'amount_refunded': cumulative}
                gateway.return_value.payment.fetch.side_effect = fetch
                self.assertEqual(self.race([lambda: self.signed('refund.processed', refund, 'refund')] * 2), [200, 200])
                product.refresh_from_db()
                self.buyer.refresh_from_db()
                if cumulative == 1000:
                    self.assertEqual(product.stock, 4)
                    self.assertEqual(self.buyer.wallet_balance, 0)
                    self.assertEqual(ProviderRefund.objects.count(), 1)
                    self.assertFalse(WalletTransaction.objects.filter(transaction_type='REFUND_ORDER').exists())
            self.assertEqual(product.stock, 5)
            self.assertEqual(self.buyer.wallet_balance, 20)
            self.assertEqual(ProviderRefund.objects.count(), 2)
            self.assertEqual(WalletTransaction.objects.filter(transaction_type='REFUND_ORDER').count(), 1)
            self.assertEqual(PurchaseIntent.objects.get().state, 'refunded')
            self.assertEqual(ProviderPaymentClaim.objects.get().state, 'refunded')


class RefundMigrationTests(TransactionTestCase):
    def test_additive_refund_migration_keeps_existing_intent_claim_and_card(self):
        from django.db.migrations.executor import MigrationExecutor
        from .models import ProviderRefund
        connection = connections['default']
        self.assertEqual(connection.settings_dict['NAME'], 'eazyshop_test')
        old_target = [('api', '0026_immutable_purchase_bindings')]
        new_target = [('api', '0027_processed_refund_evidence')]
        MigrationExecutor(connection).migrate(old_target)
        try:
            old = MigrationExecutor(connection).loader.project_state(old_target).apps
            user = old.get_model('api', 'User').objects.create(username='migration', email='migration@example.invalid')
            card = old.get_model('api', 'GiftCard').objects.create(initial_balance=50, current_balance=50)
            intent = old.get_model('api', 'PurchaseIntent').objects.create(purchaser_id=user.pk, purpose='gift_card',
                expected_amount=5000, provider_order_id='order_existing', gift_card_id=card.pk, state='settled')
            old.get_model('api', 'ProviderPaymentClaim').objects.create(payment_id='pay_existing', intent_id=intent.pk,
                provider_order_id='order_existing', amount=5000, currency='INR', state='captured')
            MigrationExecutor(connection).migrate(new_target)
            self.assertFalse(ProviderRefund.objects.exists())
            ProviderRefund.objects.create(refund_id='rfnd_fixture', claim_id='pay_existing', amount=1000,
                currency='INR', provider_cumulative=1000)
            MigrationExecutor(connection).migrate(old_target)
            self.assertEqual(old.get_model('api', 'PurchaseIntent').objects.get().state, 'settled')
            self.assertEqual(old.get_model('api', 'ProviderPaymentClaim').objects.get().amount, 5000)
            self.assertEqual(old.get_model('api', 'GiftCard').objects.get().current_balance, 50)
        finally:
            MigrationExecutor(connection).migrate([('api', '0028_purchase_request_fingerprint')])
        self.assertFalse(ProviderRefund.objects.exists())
        self.assertEqual(PurchaseIntent.objects.get().provider_order_id, 'order_existing')
