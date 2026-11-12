from decimal import Decimal

from rest_framework.test import APITestCase

from . import test_purchase_intents as fixtures
from .models import (
    GiftCard,
    GiftCardTransaction,
    Order,
    Payment,
    ProviderPaymentClaim,
    ProviderRefund,
    PurchaseIntent,
    WalletTransaction,
)


class GatewayWalletTests(APITestCase):
    setUp = fixtures.PurchaseIntentTests.setUp
    proof = fixtures.PurchaseIntentTests.proof
    checkout = fixtures.PurchaseIntentTests.checkout
    gift_purchase = fixtures.PurchaseIntentTests.gift_purchase
    verify = fixtures.PurchaseIntentTests.verify
    webhook = fixtures.PurchaseIntentTests.webhook
    financial_state = fixtures.PurchaseIntentTests.financial_state

    def order_paid_webhook(self, entity=None):
        payment_entity = entity or {**self.capture, 'method': 'wallet'}
        payload = {
            'payment': {'entity': payment_entity},
            'order': {'entity': {'id': payment_entity['order_id']}},
        }
        return self.webhook(event='order.paid', payload=payload)

    def split_checkout(self):
        self.buyer.wallet_balance = Decimal('20.00')
        self.buyer.save(update_fields=['wallet_balance'])
        self.gateway.order.create.return_value = {'id': 'order_fixture', 'amount': 3000, 'currency': 'INR'}
        response = self.client.post('/api/orders/create-razorpay-order/', {
            'shipping_address': 'Fixture', 'contact_phone': '1234', 'use_wallet': True,
            'order_items': [{'product': self.product.pk, 'quantity': 1}],
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.capture['amount'] = 3000
        return Order.objects.get(pk=response.data['order_id'])

    def test_external_wallet_capture_settles_merchandise(self):
        """Permanent positive regression asserting successful merchandise settlement via Razorpay external wallet.

        RED before fix: fails with AssertionError: 400 != 200 because validate_capture rejects method='wallet'.
        GREEN after fix: passes unchanged with HTTP 200, order paid, payment completed, and verified settlement.
        """
        data = self.checkout()
        self.capture['method'] = 'wallet'
        response = self.verify(data)
        self.assertEqual(response.status_code, 200, response.data)
        order = Order.objects.get(pk=data['order_id'])
        self.assertEqual(order.status, 'paid')
        payment = order.payment.get(transaction_id=self.capture['id'])
        self.assertEqual(payment.payment_method, 'razorpay_wallet')
        self.assertEqual(payment.status, 'completed')
        self.assertIsNotNone(payment.verified_at)
        self.assertTrue(Order.objects.with_verified_settlement().filter(pk=order.pk).exists())
        self.assertFalse(WalletTransaction.objects.exists())
        self.assertEqual(self.buyer.wallet_balance, Decimal(0))

    def test_padded_wallet_method_normalizes_to_razorpay_wallet(self):
        data = self.checkout()
        self.capture['method'] = ' wallet '
        response = self.verify(data)
        self.assertEqual(response.status_code, 200, response.data)
        order = Order.objects.get(pk=data['order_id'])
        self.assertEqual(order.status, 'paid')
        payment = order.payment.get(transaction_id=self.capture['id'])
        self.assertEqual(payment.payment_method, 'razorpay_wallet')

    def test_valid_method_length_boundary_50_chars(self):
        data = self.checkout()
        self.capture['method'] = 'a' * 50
        response = self.verify(data)
        self.assertEqual(response.status_code, 200, response.data)
        payment = Order.objects.get(pk=data['order_id']).payment.get(transaction_id=self.capture['id'])
        self.assertEqual(payment.payment_method, 'a' * 50)

    def test_webhook_first_settles_and_browser_replay_idempotent(self):
        data = self.checkout()
        self.capture['method'] = 'wallet'
        hook_res = self.webhook(event='payment.captured', entity=self.capture)
        self.assertEqual(hook_res.status_code, 200)
        order = Order.objects.get(pk=data['order_id'])
        self.assertEqual(order.status, 'paid')
        self.assertEqual(PurchaseIntent.objects.get(order=order).state, 'settled')

        # Replay 1: Duplicate payment.captured webhook
        dup_capture = self.webhook(event='payment.captured', entity=self.capture)
        self.assertEqual(dup_capture.status_code, 200)

        # Replay 2: Genuine signed order.paid webhook
        order_paid_res = self.order_paid_webhook()
        self.assertEqual(order_paid_res.status_code, 200)

        # Replay 3: Browser verify-razorpay-payment replay
        browser_res = self.verify(data)
        self.assertEqual(browser_res.status_code, 200)
        self.assertTrue(browser_res.data['success'])
        self.assertEqual(browser_res.data['message'], 'Payment verified successfully!')

        self.assertEqual(ProviderPaymentClaim.objects.count(), 1)
        self.assertEqual(Payment.objects.filter(order=order).count(), 1)
        self.assertEqual(Payment.objects.get(order=order).payment_method, 'razorpay_wallet')
        self.assertFalse(WalletTransaction.objects.exists())

    def test_split_payment_internal_wallet_and_external_wallet(self):
        order = self.split_checkout()
        self.capture['method'] = 'wallet'
        verify_res = self.verify({'order_id': order.pk})
        self.assertEqual(verify_res.status_code, 200, verify_res.data)
        order.refresh_from_db()
        self.assertEqual(order.status, 'paid')

        wallet_leg = order.payment.get(payment_method='wallet')
        self.assertEqual(wallet_leg.amount, Decimal('20.00'))
        self.assertEqual(wallet_leg.status, 'completed')

        gateway_leg = order.payment.get(payment_method='razorpay_wallet')
        self.assertEqual(gateway_leg.amount, Decimal('30.00'))
        self.assertEqual(gateway_leg.status, 'completed')

        self.assertEqual(WalletTransaction.objects.count(), 1)
        self.assertEqual(WalletTransaction.objects.get().transaction_type, 'DEBIT_ORDER')
        self.buyer.refresh_from_db()
        self.assertEqual(self.buyer.wallet_balance, Decimal(0))
        self.assertTrue(Order.objects.with_verified_settlement().filter(pk=order.pk).exists())

    def test_gift_card_purchase_with_razorpay_wallet(self):
        self.gift_purchase()
        self.capture['method'] = 'wallet'
        verify_res = self.verify()
        self.assertEqual(verify_res.status_code, 201, verify_res.data)
        self.assertEqual(GiftCard.objects.count(), 1)
        card = GiftCard.objects.get()
        self.assertEqual(card.initial_balance, Decimal('50.00'))
        self.assertEqual(card.current_balance, Decimal('50.00'))

        self.assertEqual(GiftCardTransaction.objects.filter(transaction_type='ISSUE').count(), 1)
        self.assertFalse(WalletTransaction.objects.exists())
        self.assertEqual(self.buyer.wallet_balance, Decimal(0))

        # Replay should be idempotent
        replay_res = self.verify()
        self.assertEqual(replay_res.status_code, 201)
        self.assertEqual(replay_res.data['gift_card_id'], card.pk)
        self.assertEqual(GiftCard.objects.count(), 1)

    def test_processed_refund_on_external_wallet_order_and_replay_idempotency(self):
        data = self.checkout()
        self.capture['method'] = 'wallet'
        self.assertEqual(self.verify(data).status_code, 200)
        order = Order.objects.get(pk=data['order_id'])
        self.assertEqual(order.status, 'paid')

        self.gateway.payment.fetch.return_value = {
            **self.capture, 'status': 'refunded', 'amount': 5000,
            'amount_refunded': 5000, 'method': 'wallet',
        }
        refund_payload = {
            'refund': {'entity': {
                'id': 'rfnd_ext_full', 'payment_id': self.capture['id'],
                'currency': 'INR', 'amount': 5000, 'status': 'processed',
            }}
        }
        res = self.webhook(event='refund.processed', payload=refund_payload)
        self.assertEqual(res.status_code, 200)

        order.refresh_from_db()
        self.assertEqual(order.status, 'cancelled')
        payment = order.payment.get(transaction_id=self.capture['id'])
        self.assertEqual(payment.status, 'refunded')
        self.assertEqual(ProviderPaymentClaim.objects.get().state, 'refunded')
        self.assertEqual(ProviderRefund.objects.count(), 1)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)  # Restocked once
        self.assertFalse(WalletTransaction.objects.exists())
        self.assertEqual(self.buyer.wallet_balance, Decimal(0))

        # Replay duplicate refund webhook
        dup_res = self.webhook(event='refund.processed', payload=refund_payload)
        self.assertEqual(dup_res.status_code, 200)
        self.assertEqual(ProviderRefund.objects.count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)
        self.assertFalse(WalletTransaction.objects.exists())

    def test_split_payment_cancellation_refund_accounting(self):
        order = self.split_checkout()
        self.capture['method'] = 'wallet'
        self.assertEqual(self.verify({'order_id': order.pk}).status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, 'paid')

        self.gateway.payment.refund.return_value = {
            'id': 'rfnd_split_pending', 'amount': 3000, 'currency': 'INR', 'status': 'pending',
        }
        cancel_res = self.client.post(f'/api/orders/{order.pk}/cancel/')
        self.assertEqual(cancel_res.status_code, 200)

        order.refresh_from_db()
        self.assertEqual(order.status, 'cancelled')
        self.gateway.payment.refund.assert_called_once_with(
            self.capture['id'],
            {'amount': 3000, 'notes': {'order_id': str(order.pk), 'reason': 'Order cancelled by customer'}},
            timeout=5
        )

        self.buyer.refresh_from_db()
        self.assertEqual(self.buyer.wallet_balance, Decimal('20.00'))
        self.assertEqual(WalletTransaction.objects.filter(transaction_type='REFUND_ORDER').count(), 1)
        self.assertEqual(WalletTransaction.objects.get(transaction_type='REFUND_ORDER').amount, Decimal('20.00'))

        gateway_leg = order.payment.get(payment_method='razorpay_wallet')
        self.assertEqual(gateway_leg.status, 'refund_pending')
        wallet_leg = order.payment.get(payment_method='wallet')
        self.assertEqual(wallet_leg.status, 'refunded')

    def test_cancellation_gateway_refund_failure_marks_refund_failed(self):
        data = self.checkout()
        self.capture['method'] = 'wallet'
        self.assertEqual(self.verify(data).status_code, 200)
        self.gateway.payment.refund.side_effect = Exception('Gateway connection timeout')

        cancel_res = self.client.post(f"/api/orders/{data['order_id']}/cancel/")
        self.assertEqual(cancel_res.status_code, 200)
        order = Order.objects.get(pk=data['order_id'])
        self.assertEqual(order.status, 'cancelled')
        payment = order.payment.get(transaction_id=self.capture['id'])
        self.assertEqual(payment.status, 'refund_failed')

    def test_late_wallet_capture_after_cancellation_triggers_gateway_refund(self):
        data = self.checkout()
        self.assertEqual(self.client.post(f"/api/orders/{data['order_id']}/cancel/").status_code, 200)
        order = Order.objects.get(pk=data['order_id'])
        self.assertEqual(order.status, 'cancelled')

        self.capture['method'] = 'wallet'
        self.gateway.payment.refund.return_value = {'id': 'rfnd_late', 'status': 'processed'}
        hook_res = self.webhook(event='payment.captured', entity=self.capture)
        self.assertEqual(hook_res.status_code, 200)

        order.refresh_from_db()
        self.assertEqual(order.status, 'cancelled')
        payment = order.payment.get(transaction_id=self.capture['id'])
        self.assertEqual(payment.payment_method, 'razorpay_wallet')
        self.assertEqual(payment.status, 'refund_pending')
        self.gateway.payment.refund.assert_called_once_with(
            self.capture['id'],
            {'amount': 5000, 'notes': {'order_id': str(order.pk), 'reason': 'Capture after order cancellation'}},
            timeout=5
        )
        self.assertFalse(WalletTransaction.objects.exists())

        # Replay late capture webhook
        dup_res = self.webhook(event='payment.captured', entity=self.capture)
        self.assertEqual(dup_res.status_code, 200)
        self.assertEqual(self.gateway.payment.refund.call_count, 1)

    def test_malformed_methods_rejected(self):
        data = self.checkout()
        for bad_method in ('', '   ', None, 123, 'wallet\x00injected', 'a' * 51):
            with self.subTest(bad_method=repr(bad_method)):
                before = self.financial_state()
                self.gateway.payment.fetch.return_value = {**self.capture, 'method': bad_method}
                res = self.verify(data)
                self.assertEqual(res.status_code, 400)
                self.assertEqual(self.financial_state(), before)

    def test_split_payment_cancellation_immediately_processed_refund(self):
        order = self.split_checkout()
        self.capture['method'] = 'wallet'
        self.assertEqual(self.verify({'order_id': order.pk}).status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, 'paid')

        self.gateway.payment.refund.return_value = {
            'id': 'rfnd_split_proc', 'payment_id': self.capture['id'],
            'amount': 3000, 'currency': 'INR', 'status': 'processed',
        }
        self.gateway.payment.fetch.return_value = {
            **self.capture, 'status': 'captured', 'amount': 3000,
            'amount_refunded': 3000, 'method': 'wallet',
        }
        cancel_res = self.client.post(f'/api/orders/{order.pk}/cancel/')
        self.assertEqual(cancel_res.status_code, 200)

        order.refresh_from_db()
        self.assertEqual(order.status, 'cancelled')
        self.buyer.refresh_from_db()
        self.assertEqual(self.buyer.wallet_balance, Decimal('20.00'))
        self.assertEqual(WalletTransaction.objects.filter(transaction_type='REFUND_ORDER').count(), 1)
        self.assertEqual(WalletTransaction.objects.get(transaction_type='REFUND_ORDER').amount, Decimal('20.00'))

        ext_payment = order.payment.get(payment_method='razorpay_wallet')
        self.assertEqual(ext_payment.status, 'refunded')
        self.assertEqual(order.payment.get(payment_method='wallet').status, 'refunded')
        self.assertEqual(ProviderPaymentClaim.objects.get().state, 'refunded')
        self.assertEqual(PurchaseIntent.objects.get().state, 'refunded')
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)

        # Duplicate refund.processed webhook delivery
        dup_res = self.webhook(event='refund.processed', payload={
            'refund': {'entity': {
                'id': 'rfnd_split_proc', 'payment_id': self.capture['id'],
                'currency': 'INR', 'amount': 3000, 'status': 'processed',
            }}
        })
        self.assertEqual(dup_res.status_code, 200)
        self.assertEqual(ProviderRefund.objects.count(), 1)
        self.assertEqual(WalletTransaction.objects.filter(transaction_type='REFUND_ORDER').count(), 1)
        self.buyer.refresh_from_db()
        self.assertEqual(self.buyer.wallet_balance, Decimal('20.00'))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)
