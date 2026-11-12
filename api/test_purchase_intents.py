import hashlib
import hmac
from unittest.mock import patch

import razorpay
from django.conf import settings
from django.core.cache import cache
from rest_framework.test import APITestCase

from .models import GiftCard, Order, Payment, Product, User, WalletTransaction


class PurchaseIntentTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.buyer = User.objects.create_user('intent-buyer', 'intent-buyer@example.invalid')
        self.product = Product.objects.create(name='Fixture', price=50, stock=5, approval_status='approved')
        self.client.force_authenticate(self.buyer)
        self.capture = {'id': 'pay_fixture', 'order_id': 'order_fixture', 'amount': 5000,
                        'currency': 'INR', 'status': 'captured', 'method': 'card', 'amount_refunded': 0}
        self.gateway = self.enterContext(patch('api.views.razorpay.Client')).return_value
        # Exercise the SDK's real signature checker without provider I/O.
        self.gateway.utility = razorpay.utility.utility.Utility(type('Client', (), {'auth': (settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)})())
        self.gateway.order.create.return_value = {'id': 'order_fixture', 'amount': 5000, 'currency': 'INR'}
        self.gateway.payment.fetch.return_value = self.capture
        self.enterContext(patch('cloudinary.uploader.upload', return_value={'secure_url': 'https://fixture.invalid/qr'}))

    def proof(self):
        message = self.capture['order_id'] + '|' + self.capture['id']
        signature = hmac.new(settings.RAZORPAY_KEY_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()
        return {'razorpay_order_id': self.capture['order_id'], 'razorpay_payment_id': self.capture['id'],
                'razorpay_signature': signature}

    def checkout(self):
        response = self.client.post('/api/orders/create-razorpay-order/', {
            'shipping_address': 'Fixture', 'contact_phone': '1234',
            'order_items': [{'product': self.product.pk, 'quantity': 1}],
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_merchandise_capture_cannot_also_mint_gift_card(self):
        order = self.checkout()
        verified = self.client.post('/api/orders/verify-razorpay-payment/',
                                    {**self.proof(), 'order_id': order['order_id']}, format='json')
        self.assertEqual(verified.status_code, 200, verified.data)
        minted = self.client.post('/api/gift-cards/verify/', {**self.proof(), 'amount': 50}, format='json')
        if minted.status_code == 201:
            self.client.post('/api/gift-cards/redeem/', {'gift_card_id': minted.data['gift_card_id']}, format='json')
        self.buyer.refresh_from_db()
        self.assertEqual(minted.status_code, 400,
                         f'Paid merchandise plus gift issuance: cards={GiftCard.objects.count()}, wallet={self.buyer.wallet_balance}')
        self.assertFalse(GiftCard.objects.exists())
        self.assertFalse(WalletTransaction.objects.exists())
        self.assertEqual(self.buyer.wallet_balance, 0)
        self.assertEqual(Payment.objects.filter(status='completed').count(), 1)
        self.assertEqual(Order.objects.get(pk=order['order_id']).status, 'paid')

    def gift_purchase(self, provider_id='order_gift', key=None):
        self.gateway.order.create.return_value = {'id': provider_id, 'amount': 5000, 'currency': 'INR'}
        response = self.client.post('/api/gift-cards/purchase/', {'amount': '50.00', 'idempotency_key': key}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.capture.update(order_id=provider_id, id='pay_gift')
        return response.data

    def verify(self, order=None):
        return self.client.post('/api/orders/verify-razorpay-payment/' if order else '/api/gift-cards/verify/',
            {**self.proof(), **({'order_id': order['order_id']} if order else {})}, format='json')

    def webhook(self, event='payment.captured', entity=None, payload=None):
        import json
        body = json.dumps({'event': event, 'payload': payload or {'payment': {'entity': entity or self.capture}}})
        signature = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
        return self.client.post('/api/webhooks/razorpay/', body, content_type='application/json', HTTP_X_RAZORPAY_SIGNATURE=signature)

    def full_refund_payload(self):
        self.gateway.payment.fetch.return_value = {**self.capture, 'amount_refunded': self.capture['amount'], 'status': 'refunded'}
        return {'refund': {'entity': {'id': 'rfnd_' + self.capture['id'], 'payment_id': self.capture['id'],
            'currency': 'INR', 'amount': self.capture['amount'], 'status': 'processed'}}}

    def financial_state(self):
        from .models import ProviderPaymentClaim, PurchaseIntent
        return {model.__name__: list(model.objects.order_by('pk').values())
                for model in (User, Product, Order, Payment, GiftCard, WalletTransaction, ProviderPaymentClaim, PurchaseIntent)}

    def test_gift_capture_cannot_pay_merchandise(self):
        self.gift_purchase()
        self.assertEqual(self.verify().status_code, 201)
        self.gateway.order.create.return_value = {'id': 'order_merch', 'amount': 5000, 'currency': 'INR'}
        order = self.checkout()
        before = self.financial_state()
        self.assertEqual(self.verify(order).status_code, 400)
        self.assertEqual(self.financial_state(), before)
        self.assertEqual(GiftCard.objects.count(), 1)

    def test_persisted_terms_reject_all_invalid_capture_variants(self):
        for purpose in ('merchandise', 'gift_card'):
            with self.subTest(purpose=purpose):
                if purpose == 'merchandise':
                    order = self.checkout()
                else:
                    self.gift_purchase()
                    order = None
                valid = dict(self.capture)
                for bad in ({'order_id': 'unrelated'}, {'currency': 'USD'}, {'amount': 4999}, {'amount': 5001},
                            {'amount': True}, {'amount': '5000'}, {'status': 'authorized'}, {'status': 'failed'},
                            {'status': 'refunded'}, {'amount_refunded': 1}, {'id': 'foreign'},
                            {'method': ''}, {'method': '   '}, {'method': None}, {'method': 123},
                            {'method': 'wallet\x00extra'}, {'method': 'a' * 51}):
                    with self.subTest(bad=bad):
                        before = self.financial_state()
                        self.gateway.payment.fetch.return_value = {**valid, **bad, 'notes': {'purpose': purpose, 'wallet_deducted': 50}}
                        self.assertEqual(self.verify(order).status_code, 400)
                        self.assertEqual(self.financial_state(), before)
                self.gateway.payment.fetch.return_value = self.capture

    def test_foreign_accounts_and_admin_cannot_verify_or_recover_gift(self):
        self.gift_purchase()
        proof = self.proof()
        for name, fields in (('stranger', {}), ('seller', {'role': 'seller'}), ('staff', {'is_staff': True}),
                             ('admin', {'role': 'admin'})):
            actor = User.objects.create_user(name, f'{name}@example.invalid', **fields)
            self.client.force_authenticate(actor)
            before = self.financial_state()
            self.assertEqual(self.client.post('/api/gift-cards/verify/', proof, format='json').status_code, 400)
            self.assertEqual(self.client.get('/api/gift-cards/purchase/').data, [])
            self.assertEqual(self.financial_state(), before)
        self.gateway.payment.fetch.assert_not_called()
        self.client.force_authenticate(None)
        for url in ('purchase/', 'verify/', 'redeem/'):
            self.assertEqual(self.client.post('/api/gift-cards/' + url, proof, format='json').status_code, 401)

    def test_same_intent_retries_webhooks_and_recipient_redemption_once(self):
        from .models import ProviderPaymentClaim, GiftCardTransaction
        self.gift_purchase()
        self.assertEqual(self.webhook().status_code, 200)
        self.assertEqual(self.webhook().status_code, 200)
        issued = self.verify()
        self.assertEqual(issued.status_code, 201)
        self.assertEqual(self.verify().data['gift_card_id'], issued.data['gift_card_id'])
        recovered = self.client.get('/api/gift-cards/purchase/').data
        self.assertEqual(recovered[0]['gift_card_id'], issued.data['gift_card_id'])
        self.assertTrue(issued.data['qr_url'].startswith('data:image/png;base64,'))
        self.assertFalse(GiftCard.objects.get().qr_code_url)
        recipient = User.objects.create_user('recipient', 'recipient@example.invalid')
        self.client.force_authenticate(recipient)
        self.assertEqual(self.client.get('/api/gift-cards/purchase/').data, [])
        for expected in (200, 400):
            self.assertEqual(self.client.post('/api/gift-cards/redeem/', {'gift_card_id': issued.data['gift_card_id']}, format='json').status_code, expected)
        recipient.refresh_from_db()
        self.assertEqual(recipient.wallet_balance, 50)
        self.assertEqual(ProviderPaymentClaim.objects.count(), 1)
        self.assertEqual(GiftCardTransaction.objects.filter(transaction_type='ISSUE').count(), 1)
        self.assertEqual(WalletTransaction.objects.filter(transaction_type='CREDIT_GIFT_CARD').count(), 1)

    def test_wrong_signature_and_forged_notes_cannot_create_intent(self):
        before = self.financial_state()
        self.capture['notes'] = {'django_order_id': 1, 'purpose': 'gift_card', 'user_id': self.buyer.pk}
        self.assertEqual(self.verify().status_code, 400)
        self.assertEqual(self.webhook().status_code, 503)
        self.assertEqual(self.financial_state(), before)
        self.gift_purchase()
        proof = {**self.proof(), 'razorpay_signature': 'f' * 64}
        self.assertEqual(self.client.post('/api/gift-cards/verify/', proof, format='json').status_code, 400)
        self.assertFalse(GiftCard.objects.exists())

    def test_creation_timeouts_persist_intent_and_prevent_duplicate_reservations(self):
        from .models import PurchaseIntent
        self.gateway.order.create.side_effect = TimeoutError('fixture unknown outcome')
        data = {'shipping_address': 'Fixture', 'contact_phone': '123', 'idempotency_key': 'uncertain',
                'order_items': [{'product': self.product.pk, 'quantity': 1}]}
        for expected in (503, 409):
            cache.clear()
            self.assertEqual(self.client.post('/api/orders/create-razorpay-order/', data, format='json').status_code, expected)
        self.assertEqual(Order.objects.count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 4)
        self.assertEqual(PurchaseIntent.objects.get().state, 'reconciliation')
        self.assertEqual(self.gateway.order.create.call_count, 1)
        data = {'amount': 50, 'idempotency_key': 'gift-unknown'}
        for expected in (503, 409):
            self.assertEqual(self.client.post('/api/gift-cards/purchase/', data, format='json').status_code, expected)
        self.assertEqual(self.gateway.order.create.call_count, 2)
        self.assertFalse(GiftCard.objects.exists())

    def test_fetch_timeout_and_local_crash_are_retryable_without_double_issuance(self):
        from .models import ProviderPaymentClaim
        self.gift_purchase()
        self.gateway.payment.fetch.side_effect = TimeoutError('fixture')
        self.assertEqual(self.verify().status_code, 503)
        self.gateway.payment.fetch.side_effect = None
        with patch('api.settlement.GiftCardTransaction.objects.create', side_effect=RuntimeError('fixture crash')):
            self.assertEqual(self.verify().status_code, 503)
        self.assertFalse(GiftCard.objects.exists())
        self.assertFalse(ProviderPaymentClaim.objects.exists())
        self.assertEqual(self.webhook().status_code, 200)
        self.assertEqual(self.verify().status_code, 201)
        self.assertEqual(GiftCard.objects.count(), 1)

    def test_failed_or_refunded_gift_never_mints_or_redeems(self):
        from .models import PurchaseIntent
        self.gift_purchase()
        self.assertEqual(self.webhook('payment.failed', {**self.capture, 'status': 'failed'}).status_code, 200)
        self.assertEqual(self.verify().status_code, 201)
        self.assertEqual(self.webhook().status_code, 200)
        self.assertEqual(GiftCard.objects.count(), 1)
        self.gift_purchase('order_gift_refund')
        self.capture['id'] = 'pay_gift_refund'
        issued = self.verify()
        self.assertEqual(issued.status_code, 201)
        self.assertEqual(self.webhook('refund.processed', payload=self.full_refund_payload()).status_code, 200)
        self.assertEqual(self.verify().status_code, 400)
        self.assertEqual(self.client.post('/api/gift-cards/redeem/', {'gift_card_id': issued.data['gift_card_id']}, format='json').status_code, 400)
        self.assertEqual(PurchaseIntent.objects.get(provider_order_id='order_gift_refund').state, 'refunded')
        self.assertFalse(WalletTransaction.objects.exists())

    def test_legacy_cards_and_payment_records_do_not_create_settlement_evidence(self):
        legacy = GiftCard.objects.create(initial_balance=50, current_balance=50)
        self.assertEqual(self.client.post('/api/gift-cards/redeem/', {'gift_card_id': legacy.pk}, format='json').status_code, 400)
        self.assertFalse(WalletTransaction.objects.exists())
        order = Order.objects.create(user=self.buyer, total_price=50, gateway_order_id='legacy')
        from .models import OrderItem
        from django.utils import timezone
        from django.core.exceptions import ValidationError
        OrderItem.objects.create(order=order, price=50)
        Payment.objects.create(order=order, amount=50, transaction_id='legacy', status='completed', verified_at=timezone.now())
        with self.assertRaises(ValidationError):
            order.require_verified_settlement()

    def test_gift_amount_and_nested_purchase_terms_are_server_controlled(self):
        from .models import PurchaseIntent
        for amount in (0, -1, 'NaN', 'Infinity', '0.001', '100000000', [], True):
            self.assertEqual(self.client.post('/api/gift-cards/purchase/', {'amount': amount}, format='json').status_code, 400)
        self.assertFalse(PurchaseIntent.objects.exists())
        self.gift_purchase()
        intent = PurchaseIntent.objects.get()
        from django.core.exceptions import ValidationError
        for field, value in (('purpose', 'merchandise'), ('expected_amount', 1), ('currency', 'USD')):
            intent.refresh_from_db()
            setattr(intent, field, value)
            with self.assertRaises(ValidationError):
                intent.save()

    def test_global_claim_unique_constraint_and_administrative_writes_blocked(self):
        from django.db import IntegrityError, transaction
        from django.contrib import admin
        from django.test import RequestFactory
        from .models import ProviderPaymentClaim, PurchaseIntent, GiftCardTransaction, ProviderEvent
        self.gift_purchase()
        self.assertEqual(self.verify().status_code, 201)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProviderPaymentClaim.objects.create(payment_id=self.capture['id'], state='quarantined')
        request = RequestFactory().get('/admin/')
        request.user = User.objects.create_superuser('root', 'root@example.invalid', 'fixture')
        for model in (GiftCard, GiftCardTransaction, PurchaseIntent, ProviderPaymentClaim, ProviderEvent):
            model_admin = admin.site._registry[model]
            self.assertFalse(model_admin.has_add_permission(request))
            self.assertFalse(model_admin.has_change_permission(request))
            self.assertFalse(model_admin.has_delete_permission(request))

    def test_database_rejects_bulk_rebinding_and_terminal_reactivation(self):
        from .models import PurchaseIntent, ProviderPaymentClaim
        from django.db import transaction, IntegrityError
        self.gift_purchase()
        self.assertEqual(self.verify().status_code, 201)
        intent = PurchaseIntent.objects.get()
        for changes in ({'expected_amount': 1}, {'provider_order_id': 'new'}, {'currency': 'USD'}):
            with self.assertRaises(IntegrityError), transaction.atomic():
                PurchaseIntent.objects.filter(pk=intent.pk).update(**changes)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProviderPaymentClaim.objects.update(amount=1)
        PurchaseIntent.objects.update(state='refunded')
        with self.assertRaises(IntegrityError), transaction.atomic():
            PurchaseIntent.objects.update(state='settled')

    def test_wallet_and_split_terms_require_real_ledger_and_atomic_settlement(self):
        from .models import PurchaseIntent, ProviderPaymentClaim
        from decimal import Decimal
        from django.core.exceptions import ValidationError
        for balance in ('50.00', '20.00'):
            self.buyer.wallet_balance = Decimal(balance)
            self.buyer.save(update_fields=['wallet_balance'])
            self.gateway.order.create.return_value = {'id': 'order_split', 'amount': 3000, 'currency': 'INR'}
            response = self.client.post('/api/orders/create-razorpay-order/', {
                'shipping_address': 'Fixture', 'contact_phone': '123', 'use_wallet': True,
                'wallet_amount': 99999, 'purpose': 'gift_card',
                'order_items': [{'product': self.product.pk, 'quantity': 1}],
            }, format='json')
            self.assertEqual(response.status_code, 201, response.data)
            order = Order.objects.get(pk=response.data['order_id'])
            intent = PurchaseIntent.objects.get(order=order)
            self.assertEqual(intent.wallet_amount, int(Decimal(balance) * 100))
            self.assertEqual(intent.wallet_debit.amount, Decimal(balance))
            if balance == '50.00':
                self.assertTrue(response.data['payment_complete'])
                order.require_verified_settlement()
            else:
                with self.assertRaises(ValidationError):
                    order.require_verified_settlement()
                self.capture.update(order_id='order_split', amount=3000, id='pay_split')
                before = self.financial_state()
                with patch('api.settlement.CartItem.objects.filter', side_effect=RuntimeError('after capture write')):
                    self.assertEqual(self.verify({'order_id': order.pk}).status_code, 503)
                self.assertEqual(self.financial_state(), before)
                self.assertFalse(ProviderPaymentClaim.objects.exists())
                self.assertEqual(self.verify({'order_id': order.pk}).status_code, 200)
                order.require_verified_settlement()
        self.assertEqual(WalletTransaction.objects.filter(transaction_type='DEBIT_ORDER').count(), 2)


    def test_refund_after_gift_redemption_requires_reconciliation_not_second_credit(self):
        self.gift_purchase()
        issued = self.verify()
        self.assertEqual(self.client.post('/api/gift-cards/redeem/', {'gift_card_id': issued.data['gift_card_id']}, format='json').status_code, 200)
        payload = self.full_refund_payload()
        for _ in range(2):
            self.assertEqual(self.webhook('refund.processed', payload=payload).status_code, 200)
        self.assertEqual(PurchaseIntent.objects.get().state, 'reconciliation')
        self.assertEqual(ProviderPaymentClaim.objects.get().state, 'refunded')
        self.buyer.refresh_from_db()
        self.assertEqual(self.buyer.wallet_balance, 50)
        self.assertEqual(WalletTransaction.objects.count(), 1)
        self.assertEqual(self.verify().status_code, 400)
        self.assertNotEqual(self.webhook().status_code, 200)

    def test_gift_refund_before_capture_and_stale_failed_events_cannot_mint(self):
        self.gift_purchase()
        self.gateway.payment.fetch.return_value = {**self.capture, 'amount_refunded': 5000}
        self.assertEqual(self.webhook('refund.processed', payload=self.full_refund_payload()).status_code, 200)
        self.assertEqual(PurchaseIntent.objects.get().state, 'refunded')
        self.assertEqual(self.verify().status_code, 400)
        self.assertNotEqual(self.webhook().status_code, 200)
        self.assertFalse(GiftCard.objects.exists())
        self.assertFalse(WalletTransaction.objects.exists())
        self.gateway.payment.fetch.return_value = self.capture
        self.gift_purchase('order_second')
        self.capture['id'] = 'pay_second'
        self.assertEqual(self.verify().status_code, 201)
        self.assertEqual(self.webhook('payment.failed').status_code, 200)
        self.assertEqual(PurchaseIntent.objects.get(provider_order_id='order_second').state, 'settled')
        self.assertEqual(self.verify().status_code, 201)
        self.assertEqual(GiftCard.objects.count(), 1)

    def test_historical_cancellation_and_unverified_wallet_refunds_are_quarantined(self):
        legacy = Order.objects.create(user=self.buyer, total_price=50)
        Payment.objects.create(order=legacy, amount=50, payment_method='wallet', status='completed', transaction_id='forged-wallet')
        before = self.financial_state()
        self.assertEqual(self.client.post(f'/api/orders/{legacy.pk}/cancel/').status_code, 409)
        self.assertEqual(self.financial_state(), before)
        current = self.checkout()
        order = Order.objects.get(pk=current['order_id'])
        Payment.objects.create(order=order, amount=50, payment_method='wallet', status='completed', transaction_id='forged-extra-wallet')
        before = self.financial_state()
        self.assertEqual(self.client.post(f'/api/orders/{order.pk}/cancel/').status_code, 409)
        self.assertEqual(self.financial_state(), before)
        self.gateway.payment.refund.assert_not_called()

    def test_gateway_response_mismatch_and_unknown_refund_remain_unsettled(self):
        self.gateway.order.create.return_value['amount'] = 1
        response = self.client.post('/api/gift-cards/purchase/', {'amount': 50}, format='json')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(PurchaseIntent.objects.get().state, 'reconciliation')
        self.assertFalse(GiftCard.objects.exists())
        self.gateway.order.create.return_value = {'id': 'order_fixture', 'amount': 5000, 'currency': 'INR'}
        order = self.checkout()
        self.assertEqual(self.verify(order).status_code, 200)
        self.gateway.payment.refund.return_value = {'status': 'pending'}
        self.assertEqual(self.client.post(f"/api/orders/{order['order_id']}/cancel/").status_code, 200)
        self.assertEqual(Payment.objects.get().status, 'refund_pending')
        self.assertEqual(ProviderPaymentClaim.objects.get().state, 'refund_pending')
        self.assertEqual(self.verify(order).status_code, 400)
        self.assertEqual(self.client.post(f"/api/orders/{order['order_id']}/cancel/").status_code, 400)
        self.gateway.payment.refund.assert_called_once()
        self.assertEqual(self.webhook('refund.processed', payload=self.full_refund_payload()).status_code, 200)
        self.assertEqual(Payment.objects.get().status, 'refunded')

    def test_report_is_read_only_and_omits_bearer_credentials(self):
        from django.core.management import call_command
        from io import StringIO
        self.gift_purchase()
        issued = self.verify()
        before = self.financial_state()
        output = StringIO()
        call_command('purchase_reconciliation_report', stdout=output)
        self.assertIn('legacy_orders_without_intent', output.getvalue())
        self.assertNotIn(str(issued.data['gift_card_id']), output.getvalue())
        self.assertNotIn(self.capture['id'], output.getvalue())
        self.assertEqual(self.financial_state(), before)



from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import connections, transaction
from django.core.exceptions import ValidationError
from django.test import TransactionTestCase
from rest_framework.test import APIClient
from .models import PurchaseIntent, ProviderPaymentClaim, OrderItem
from .settlement import record_gateway_capture, settle_gift_capture


class PurchaseIntentConcurrencyTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.assertEqual(connections['default'].vendor, 'postgresql')
        self.buyer = User.objects.create_user('race', 'race@example.invalid')

    def fixture(self, purpose, suffix):
        order = None
        if purpose == 'merchandise':
            order = Order.objects.create(user=self.buyer, total_price=50, status='pending_payment', gateway_order_id='order_' + suffix)
            OrderItem.objects.create(order=order, price=50)
        intent = PurchaseIntent.objects.create(purchaser=self.buyer, purpose=purpose, order=order,
            expected_amount=5000, provider_order_id='order_' + suffix, state='pending')
        entity = {'id': 'pay_' + suffix, 'order_id': intent.provider_order_id, 'amount': 5000,
                  'currency': 'INR', 'status': 'captured'}
        return intent, entity

    def race(self, functions):
        barrier = Barrier(len(functions), timeout=10)
        def run(fn):
            connections.close_all()
            try:
                with connections['default'].cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute('SELECT pg_backend_pid()')
                    pid = cursor.fetchone()[0]
                barrier.wait()
                return fn(), pid
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=len(functions)) as executor:
            futures = [executor.submit(run, fn) for fn in functions]
            results = [future.result(timeout=20) for future in futures]
        self.assertEqual(len({pid for _, pid in results}), len(functions))
        return [result for result, _ in results]

    def test_browser_webhook_race_finalizes_each_purpose_once(self):
        import json
        for purpose in ('gift_card', 'merchandise'):
            intent, entity = self.fixture(purpose, purpose)
            signature = hmac.new(settings.RAZORPAY_KEY_SECRET.encode(),
                f"{intent.provider_order_id}|{entity['id']}".encode(), hashlib.sha256).hexdigest()
            proof = {'razorpay_order_id': intent.provider_order_id, 'razorpay_payment_id': entity['id'],
                     'razorpay_signature': signature, 'order_id': intent.order_id}
            body = json.dumps({'event': 'payment.captured', 'payload': {'payment': {'entity': entity}}})
            web_signature = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
            def browser():
                client = APIClient()
                client.force_authenticate(self.buyer)
                url = '/api/gift-cards/verify/' if purpose == 'gift_card' else '/api/orders/verify-razorpay-payment/'
                return client.post(url, proof, format='json').status_code
            def webhook():
                return APIClient().post('/api/webhooks/razorpay/', body, content_type='application/json',
                    HTTP_X_RAZORPAY_SIGNATURE=web_signature).status_code
            with patch('api.views.razorpay.Client') as gateway, patch('api.views.async_notify_vendors'):
                gateway.return_value.utility = razorpay.utility.utility.Utility(type('Client', (), {'auth': (settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)})())
                def fetch(*args, **kwargs):
                    self.assertFalse(connections['default'].in_atomic_block)
                    return entity
                gateway.return_value.payment.fetch.side_effect = fetch
                self.assertEqual(self.race([browser, webhook]), [201 if purpose == 'gift_card' else 200, 200])
            intent.refresh_from_db()
            self.assertEqual(intent.state, 'settled')
            self.assertEqual(ProviderPaymentClaim.objects.filter(intent=intent).count(), 1)
        self.assertEqual(GiftCard.objects.count(), 1)
        self.assertEqual(Payment.objects.count(), 1)

    def test_concurrent_cross_purpose_claim_has_only_one_financial_outcome(self):
        merchandise, merch_capture = self.fixture('merchandise', 'merch')
        gift, gift_capture = self.fixture('gift_card', 'gift')
        merch_capture['id'] = gift_capture['id'] = 'one_global_payment'
        def capture_merch():
            try:
                record_gateway_capture(merchandise.order, merch_capture)
                return 'settled'
            except ValidationError:
                return 'rejected'
        def capture_gift():
            try:
                settle_gift_capture(gift.pk, gift_capture)
                return 'settled'
            except ValidationError:
                return 'rejected'
        self.assertEqual(sorted(self.race([capture_merch, capture_gift])), ['rejected', 'settled'])
        self.assertEqual(ProviderPaymentClaim.objects.count(), 1)
        self.assertEqual(Payment.objects.count() + GiftCard.objects.count(), 1)
        self.assertEqual(PurchaseIntent.objects.filter(state='settled').count(), 1)

    def test_concurrent_same_key_creates_provider_order_once_without_locks_during_io(self):
        product = Product.objects.create(name='Fixture', price=50, stock=2, approval_status='approved')
        def checkout():
            client = APIClient()
            client.force_authenticate(self.buyer)
            return client.post('/api/orders/create-razorpay-order/', {
                'shipping_address': 'Fixture', 'contact_phone': '123', 'idempotency_key': 'race-key',
                'order_items': [{'product': product.pk, 'quantity': 1}],
            }, format='json').status_code
        with patch('api.views.razorpay.Client') as gateway:
            def create(data, **kwargs):
                self.assertFalse(connections['default'].in_atomic_block)
                return {'id': 'order_once', 'amount': 5000, 'currency': 'INR'}
            gateway.return_value.order.create.side_effect = create
            outcomes = self.race([checkout, checkout])
            self.assertIn(201, outcomes)
            self.assertTrue(all(code in (201, 409) for code in outcomes))
            self.assertEqual(gateway.return_value.order.create.call_count, 1)
        self.assertEqual(Order.objects.count(), 1)
        product.refresh_from_db()
        self.assertEqual(product.stock, 1)


class PurchaseIntentMigrationTests(TransactionTestCase):
    def test_forward_quarantines_legacy_ids_and_rollback_preserves_history(self):
        from django.db.migrations.executor import MigrationExecutor
        connection = connections['default']
        self.assertEqual(connection.settings_dict['NAME'], 'eazyshop_test')
        old_target = [('api', '0024_protect_order_history')]
        new_target = [('api', '0028_purchase_request_fingerprint')]
        executor = MigrationExecutor(connection)
        executor.migrate(old_target)
        try:
            old = executor.loader.project_state(old_target).apps
            buyer = old.get_model('api', 'User').objects.create(username='historical', email='historical@example.invalid')
            order = old.get_model('api', 'Order').objects.create(user_id=buyer.pk, total_price=50, status='paid')
            old.get_model('api', 'Payment').objects.create(order_id=order.pk, amount=50, transaction_id='legacy_shared', status='completed')
            card = old.get_model('api', 'GiftCard').objects.create(initial_balance=50, current_balance=50)
            old.get_model('api', 'GiftCardTransaction').objects.create(gift_card_id=card.pk, user_id=buyer.pk,
                transaction_type='ISSUE', amount=50, razorpay_payment_id='legacy_shared')
            executor = MigrationExecutor(connection)
            executor.migrate(new_target)
            self.assertEqual(ProviderPaymentClaim.objects.count(), 1)
            self.assertEqual(ProviderPaymentClaim.objects.get().state, 'quarantined')
            self.assertIsNone(ProviderPaymentClaim.objects.get().intent_id)
            self.assertFalse(PurchaseIntent.objects.exists())
            self.assertEqual(Payment.objects.get().amount, 50)
            self.assertEqual(GiftCard.objects.get().current_balance, 50)
            MigrationExecutor(connection).migrate(old_target)
            self.assertEqual(old.get_model('api', 'Payment').objects.get().transaction_id, 'legacy_shared')
            self.assertEqual(old.get_model('api', 'GiftCard').objects.get().current_balance, 50)
        finally:
            MigrationExecutor(connection).migrate(new_target)
