"""Explicit trusted intent evidence for pre-existing isolated regression fixtures.

Never used by application code or migrations; historical production rows are not backfilled.
"""
from decimal import Decimal
from .models import PurchaseIntent, ProviderPaymentClaim


def intent_for_order(order, settled=False):
    if not order.gateway_order_id:
        order.gateway_order_id = f'fixture-order-{order.pk}'
        order.save(update_fields=['gateway_order_id'])
    intent, _ = PurchaseIntent.objects.get_or_create(order=order, defaults={
        'purchaser': order.user, 'purpose': 'merchandise', 'expected_amount': int(Decimal(str(order.total_price)) * 100),
        'provider_order_id': order.gateway_order_id, 'state': 'cancelled' if order.status == 'cancelled' else 'pending',
    })
    if settled:
        from django.utils import timezone
        payment = order.payment.exclude(payment_method='wallet').get()
        payment.verified_at = timezone.now()
        payment.save(update_fields=['verified_at'])
        ProviderPaymentClaim.objects.get_or_create(payment_id=payment.transaction_id, defaults={
            'intent': intent, 'provider_order_id': intent.provider_order_id, 'amount': intent.expected_amount,
            'currency': 'INR', 'state': 'captured',
        })
        intent.state = 'settled'
        intent.save(update_fields=['state'])
    return intent


def intent_for_gift(card, purchaser):
    intent = PurchaseIntent.objects.create(purchaser=purchaser, purpose='gift_card', gift_card=card,
        expected_amount=int(Decimal(str(card.initial_balance)) * 100), provider_order_id=f'fixture-gift-{card.pk}', state='settled')
    ProviderPaymentClaim.objects.create(payment_id=f'fixture-gift-{card.pk}', intent=intent,
        provider_order_id=intent.provider_order_id, amount=intent.expected_amount, currency='INR')
    return intent


def refund_fixture(payment, order):
    """A complete processed response and independent provider cumulative snapshot."""
    amount = int(Decimal(str(payment.amount)) * 100)
    refund = {'id': f'rfnd_{payment.transaction_id}', 'payment_id': payment.transaction_id,
              'amount': amount, 'currency': 'INR', 'status': 'processed'}
    capture = {'id': payment.transaction_id, 'order_id': order.gateway_order_id,
               'amount': amount, 'amount_refunded': amount, 'currency': 'INR', 'status': 'refunded'}
    return refund, capture
