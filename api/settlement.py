"""Trusted purchase creation and capture finalization; no provider I/O under locks."""
import base64
import io
from decimal import Decimal

import qrcode
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import (CartItem, GiftCard, GiftCardTransaction, Order, Payment,
                     ProviderPaymentClaim, PurchaseIntent)


def create_provider_order(intent, client):
    # UUID receipt is diagnostic only. Webhooks never bind purchases using notes/receipt.
    try:
        result = client.order.create(data={
            'amount': intent.expected_amount, 'currency': intent.currency,
            'receipt': intent.id.hex, 'payment_capture': 1,
        }, timeout=5)
        if (not isinstance(result.get('id'), str) or not 1 <= len(result['id']) <= 100
                or type(result.get('amount')) is not int or result['amount'] != intent.expected_amount
                or result.get('currency') != intent.currency):
            raise ValidationError('Provider order does not match purchase terms.')
        with transaction.atomic():
            # Same order -> intent lock order as cancellation/fulfillment.
            order = Order.objects.select_for_update().get(pk=intent.order_id) if intent.order_id else None
            current = PurchaseIntent.objects.select_for_update().get(pk=intent.pk)
            current.provider_order_id = result['id']
            if current.state == 'creating':
                current.state = 'pending'
            current.save(update_fields=['provider_order_id', 'state', 'updated_at'])
            if order:
                order.gateway_order_id = result['id']
                order.save(update_fields=['gateway_order_id'])
        intent.refresh_from_db()
        return result
    except Exception:
        # Unknown outcome: retain reservation and receipt for reconciliation. Never
        # retry provider creation on this intent; a timeout may have created an order.
        PurchaseIntent.objects.filter(pk=intent.pk, state='creating').update(state='reconciliation', updated_at=timezone.now())
        raise


def validate_capture(intent, entity):
    if (
        not isinstance(entity, dict)
        or not isinstance(entity.get('id'), str) or not 1 <= len(entity['id']) <= 100
        or not intent.provider_order_id or entity.get('order_id') != intent.provider_order_id
        or entity.get('status') != 'captured' or entity.get('currency') != intent.currency
        or entity.get('amount_refunded', 0) != 0
        or type(entity.get('amount')) is not int or entity['amount'] != intent.expected_amount
        or intent.expected_amount <= 0
        or not isinstance(entity.get('method', 'razorpay'), str)
        or entity.get('method', 'razorpay') in ('', 'wallet')
    ):
        raise ValidationError('Capture does not match the authorized purchase.')


def claim_capture(intent, entity):
    """Caller holds the intent lock. Global PK arbitrates even cross-purpose races."""
    validate_capture(intent, entity)
    try:
        with transaction.atomic():
            claim, created = ProviderPaymentClaim.objects.get_or_create(
                payment_id=entity['id'], defaults={
                    'intent': intent, 'provider_order_id': intent.provider_order_id,
                    'amount': entity['amount'], 'currency': intent.currency,
                })
    except IntegrityError:
        raise ValidationError('Purchase already has another payment claim.')
    if (claim.intent_id != intent.pk or claim.provider_order_id != intent.provider_order_id
            or claim.amount != intent.expected_amount or claim.currency != intent.currency
            or claim.state not in ('captured', 'refund_pending')):
        raise ValidationError('Payment is unavailable for this purchase.')
    return claim, created


def validate_wallet(intent, order):
    if intent.purchaser_id != order.user_id or intent.expected_amount + intent.wallet_amount != int(order.total_price * 100):
        raise ValidationError('Purchase terms do not match the order.')
    if intent.wallet_amount:
        debit = intent.wallet_debit
        if (not debit or debit.user_id != order.user_id or debit.transaction_type != 'DEBIT_ORDER'
                or debit.amount * 100 != intent.wallet_amount or debit.reference_id != f'ORDER-{order.pk}'):
            raise ValidationError('Wallet reservation lacks ledger evidence.')
    wallet_statuses = ('completed', 'refunded') if order.status == 'cancelled' else ('completed',)
    wallet_legs = order.payment.filter(payment_method='wallet', status__in=wallet_statuses)
    if wallet_legs.filter(verified_at__isnull=True).exists():
        raise ValidationError('Wallet payment lacks ledger-backed verification.')
    wallet_total = sum(wallet_legs.values_list('amount', flat=True), Decimal(0))
    if wallet_total * 100 != intent.wallet_amount:
        raise ValidationError('Wallet payment does not match its reservation.')


@transaction.atomic
def record_gateway_capture(order, entity):
    order = Order.objects.select_for_update().get(pk=order.pk)
    intent = PurchaseIntent.objects.select_for_update().filter(order=order, purpose='merchandise').first()
    if not intent or intent.provider_order_id != order.gateway_order_id:
        raise ValidationError('Order lacks a trusted purchase intent; reconciliation required.')
    validate_wallet(intent, order)
    if intent.state not in ('pending', 'settled', 'cancelled', 'failed'):
        raise ValidationError('Purchase is closed or requires reconciliation.')
    claim, claimed = claim_capture(intent, entity)
    captured_amount = Decimal(entity['amount']) / 100
    payment = Payment.objects.filter(transaction_id=entity['id']).first()
    if payment and payment.order_id != order.pk:
        raise ValidationError('Payment belongs to another order.')
    if payment and payment.verified_at:
        if payment.amount != captured_amount or claimed:
            raise ValidationError('Capture lacks consistent settlement evidence.')
        return payment, False
    if order.status not in ('pending', 'pending_payment', 'cancelled'):
        raise ValidationError('Order no longer accepts payments.')
    if payment is None:
        payment = Payment(order=order, transaction_id=entity['id'])
    elif payment.status != 'authorized':
        raise ValidationError('Payment is not eligible for capture.')
    payment.payment_method = entity.get('method', 'razorpay')
    payment.amount = captured_amount
    payment.status = 'refund_pending' if order.status == 'cancelled' else 'completed'
    payment.verified_at = timezone.now()
    payment.save()
    if order.status == 'cancelled':
        claim.state = 'refund_pending'
        claim.save(update_fields=['state', 'updated_at'])
        return payment, True
    if intent.state != 'pending':
        raise ValidationError('Closed intent cannot settle.')
    intent.state = 'settled'
    intent.save(update_fields=['state', 'updated_at'])
    order.status = 'paid'
    order.save(update_fields=['status'])
    CartItem.objects.filter(cart__user_id=order.user_id).delete()
    return payment, True


@transaction.atomic
def settle_gift_capture(intent_id, entity):
    intent = PurchaseIntent.objects.select_for_update().get(pk=intent_id, purpose='gift_card')
    if intent.state in ('cancelled', 'failed'):
        claim, _ = claim_capture(intent, entity)
        claim.state = 'refund_pending'
        claim.save(update_fields=['state', 'updated_at'])
        intent.state = 'reconciliation'
        intent.save(update_fields=['state', 'updated_at'])
        return None, False  # Persist a late capture; never mint value or auto-retry refunds.
    if intent.state not in ('pending', 'settled'):
        raise ValidationError('Gift purchase is closed or requires reconciliation.')
    claim, created = claim_capture(intent, entity)
    if intent.state == 'settled':
        if created or not intent.gift_card_id or claim.state != 'captured':
            raise ValidationError('Gift purchase lacks settlement evidence.')
        return intent.gift_card, False
    if intent.gift_card_id:
        raise ValidationError('Gift already issued.')
    amount = Decimal(intent.expected_amount) / 100
    card = GiftCard.objects.create(owner=None, initial_balance=amount, current_balance=amount)
    GiftCardTransaction.objects.create(gift_card=card, transaction_type='ISSUE', amount=amount,
        user_id=intent.purchaser_id, razorpay_payment_id=claim.payment_id)
    intent.gift_card = card
    intent.state = 'settled'
    intent.save(update_fields=['gift_card', 'state', 'updated_at'])
    return card, True


def gift_response(card):
    # Bearer redemption credentials must never be uploaded to public image hosting.
    image = qrcode.make(str(card.pk))
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return {'message': 'Gift card purchased successfully', 'gift_card_id': card.pk,
            'amount': card.initial_balance, 'active': card.is_active,
            'qr_url': 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')}


def checkout_response(intent):
    if intent.state == 'settled' and intent.purpose == 'merchandise':
        intent.order.require_verified_settlement()
        return {'order_id': intent.order_id, 'intent_id': str(intent.pk), 'payment_complete': True,
                'message': 'Purchase already settled.'}
    if intent.state == 'settled' and intent.purpose == 'gift_card':
        if not intent.gift_card_id or not ProviderPaymentClaim.objects.filter(intent=intent, state='captured').exists():
            raise ValidationError('Gift purchase requires reconciliation.')
        return {'intent_id': str(intent.pk), 'order_id': intent.provider_order_id,
                'payment_complete': True, **gift_response(intent.gift_card)}
    if intent.state != 'pending' or not intent.provider_order_id:
        raise ValidationError('Purchase is closed or awaiting reconciliation. Do not retry with a new key.')
    if intent.purpose == 'gift_card':
        return {'intent_id': str(intent.pk), 'order_id': intent.provider_order_id,
                'amount': Decimal(intent.expected_amount) / 100, 'key': settings.RAZORPAY_KEY_ID}
    return {'intent_id': str(intent.pk), 'order_id': intent.order_id, 'razorpay_order_id': intent.provider_order_id,
            'amount': intent.expected_amount, 'currency': intent.currency, 'key_id': settings.RAZORPAY_KEY_ID}
