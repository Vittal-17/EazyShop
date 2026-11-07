"""Validate processed refunds outside locks; account for each refund exactly once."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum, Max
from django.utils import timezone

from .models import (GiftCard, GiftCardTransaction, Order, Payment, Product,
                     ProviderPaymentClaim, ProviderRefund, PurchaseIntent, User,
                     record_wallet_transaction)
from .settlement import validate_wallet


def validate_refund_entity(refund):
    if (not isinstance(refund, dict)
        or any(not isinstance(refund.get(field), str) or not 1 <= len(refund[field]) <= 100
               for field in ('id', 'payment_id'))
        or refund.get('status') != 'processed' or refund.get('currency') != 'INR'
        or type(refund.get('amount')) is not int or refund['amount'] <= 0):
        raise ValidationError('Invalid processed refund evidence.')


def fetch_refund_payment(client, refund):
    validate_refund_entity(refund)
    # Even known claims require independent cumulative evidence. No DB locks here.
    payment = client.payment.fetch(refund['payment_id'], timeout=5)
    if (not isinstance(payment, dict) or payment.get('id') != refund['payment_id']
        or not isinstance(payment.get('order_id'), str) or not payment['order_id']
        or payment.get('currency') != refund['currency']
        or payment.get('status') not in ('captured', 'refunded')
        or type(payment.get('amount')) is not int or payment['amount'] <= 0
        or type(payment.get('amount_refunded')) is not int
        or not refund['amount'] <= payment['amount_refunded'] <= payment['amount']):
        raise ValidationError('Refund does not match provider payment evidence.')
    return payment


@transaction.atomic
def record_processed_refund(refund, payment):
    """Caller supplies a signed/verified refund and independently fetched payment.

    Partial evidence freezes settlement, retaining original stock and wallet legs.
    Only a complete unique-refund sum can reverse an unfulfilled purchase.
    """
    validate_refund_entity(refund)
    candidate = PurchaseIntent.objects.filter(provider_order_id=payment.get('order_id')).first()
    if not candidate:
        raise ValidationError('Refund purchase requires reconciliation.')
    order = Order.objects.select_for_update().get(pk=candidate.order_id) if candidate.order_id else None
    intent = PurchaseIntent.objects.select_for_update().get(pk=candidate.pk)
    if (payment.get('id') != refund['payment_id'] or payment.get('currency') != intent.currency
        or refund['currency'] != intent.currency or type(payment.get('amount')) is not int
        or payment['amount'] != intent.expected_amount or payment.get('status') not in ('captured', 'refunded')
        or type(payment.get('amount_refunded')) is not int
        or not refund['amount'] <= payment['amount_refunded'] <= intent.expected_amount):
        raise ValidationError('Refund does not match immutable purchase terms.')
    if order:
        validate_wallet(intent, order)
    try:
        with transaction.atomic():
            claim, _ = ProviderPaymentClaim.objects.get_or_create(payment_id=refund['payment_id'], defaults={
                'intent': intent, 'provider_order_id': intent.provider_order_id,
                'amount': intent.expected_amount, 'currency': intent.currency, 'state': 'refund_pending',
            })
    except IntegrityError:
        raise ValidationError('Purchase already has a different payment claim.')
    if (claim.intent_id != intent.pk or claim.provider_order_id != intent.provider_order_id
        or claim.amount != intent.expected_amount or claim.currency != intent.currency
        or claim.state == 'quarantined'):
        raise ValidationError('Refund belongs to another or quarantined purchase.')
    try:
        with transaction.atomic():
            evidence, _ = ProviderRefund.objects.get_or_create(refund_id=refund['id'], defaults={
                'claim': claim, 'amount': refund['amount'], 'currency': refund['currency'],
                'provider_cumulative': payment['amount_refunded'],
            })
    except IntegrityError:
        raise ValidationError('Conflicting refund evidence.')
    if (evidence.claim_id != claim.pk or evidence.amount != refund['amount']
        or evidence.currency != refund['currency']):
        raise ValidationError('Refund ID has different persisted terms.')
    totals = claim.refunds.aggregate(total=Sum('amount'), reported=Max('provider_cumulative'))
    # Out-of-order fetches may be older than previously persisted snapshots.
    known_cumulative = max(totals['reported'], payment['amount_refunded'])
    if totals['total'] > known_cumulative or totals['total'] > claim.amount:
        raise ValidationError('Processed refund sum exceeds provider evidence.')
    full = totals['total'] == claim.amount and known_cumulative == claim.amount
    if claim.state == 'refunded' and not full:
        # Pre-review terminal rows may lack itemized evidence. Never downgrade or reopen.
        raise ValidationError('Historical terminal refund requires reconciliation.')
    claim.state = 'refunded' if full else 'refund_pending'
    claim.save(update_fields=['state', 'updated_at'])
    intent.state = 'refunded' if full else 'reconciliation'
    if order:
        local_payment, created = Payment.objects.get_or_create(transaction_id=claim.pk, defaults={
            'order': order, 'payment_method': 'razorpay', 'amount': Decimal(claim.amount) / 100,
            'status': 'refund_pending',
        })
        if local_payment.order_id != order.pk or local_payment.payment_method == 'wallet' or local_payment.amount * 100 != claim.amount:
            raise ValidationError('Refund conflicts with the local payment.')
        local_payment.status = 'refunded' if full else 'refund_pending'
        local_payment.save(update_fields=['status'])
    elif intent.gift_card_id:
        card = GiftCard.objects.select_for_update().get(pk=intent.gift_card_id)
        card.is_active = False  # Freeze even partial refunds without erasing the original balance.
        card.save(update_fields=['is_active'])
        if GiftCardTransaction.objects.filter(gift_card=card, transaction_type='REDEEM').exists():
            intent.state = 'reconciliation'  # Spent value needs an audited recovery decision.
    intent.save(update_fields=['state', 'updated_at'])
    if full and order and order.status in ('pending', 'pending_payment', 'paid', 'processing'):
        reverse_unfulfilled_order(order)
    return full


def reverse_unfulfilled_order(order):
    """Order and intent already locked. User -> sorted products matches checkout."""
    user = User.objects.select_for_update().get(pk=order.user_id)
    order.status = 'cancelled'
    order.save(update_fields=['status'])
    items = list(order.order_items.exclude(status='cancelled'))
    products = {p.pk: p for p in Product.objects.select_for_update().filter(
        pk__in=sorted({item.product_id for item in items if item.product_id})).order_by('pk')}
    for item in items:
        item.status = 'cancelled'
        item.save(update_fields=['status'])
        if item.product_id in products:
            product = products[item.product_id]
            product.stock += item.quantity
            product.save(update_fields=['stock'])
    for wallet in order.payment.select_for_update().filter(payment_method='wallet', status='completed'):
        record_wallet_transaction(user=user, amount=wallet.amount, transaction_type='REFUND_ORDER',
            reference_id=f'ORDER-{order.pk}', description=f'Wallet return after full gateway refund for Order #{order.pk}')
        wallet.status = 'refunded'
        wallet.save(update_fields=['status'])
