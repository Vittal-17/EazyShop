from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import CartItem, Payment


@transaction.atomic
def record_gateway_capture(order, entity):
    """Record a validated Razorpay capture while the caller holds the order lock."""
    payment_id = entity.get('id')
    amount = entity.get('amount')
    method = entity.get('method', 'razorpay')
    if (
        not isinstance(payment_id, str) or not payment_id
        or not order.gateway_order_id or entity.get('order_id') != order.gateway_order_id
        or entity.get('status') != 'captured' or entity.get('currency') != 'INR'
        or entity.get('amount_refunded', 0) != 0
        or type(amount) is not int or amount <= 0
        or not isinstance(method, str) or not method or method == 'wallet'
    ):
        raise ValidationError("Capture does not match the stored gateway order.")

    wallet_legs = order.payment.filter(payment_method='wallet', verified_at__isnull=False)
    wallet_status = ('completed', 'refunded') if order.status == 'cancelled' else ('completed',)
    wallet_total = sum(wallet_legs.filter(status__in=wallet_status).values_list('amount', flat=True), Decimal('0'))
    captured_amount = Decimal(amount) / 100
    if captured_amount + wallet_total != order.total_price:
        raise ValidationError("Captured amount does not match the order balance.")

    payment = Payment.objects.filter(transaction_id=payment_id).first()
    if payment and payment.order_id != order.pk:
        raise ValidationError("Payment belongs to another order.")
    if payment and payment.verified_at:
        if payment.amount != captured_amount:
            raise ValidationError("Capture does not match the recorded payment.")
        return payment, False
    if order.status not in ('pending', 'pending_payment', 'cancelled'):
        raise ValidationError("Order no longer accepts payments.")

    if payment is None:
        payment = Payment(order=order, transaction_id=payment_id)
    elif payment.status != 'authorized':
        raise ValidationError("Payment is not eligible for capture.")
    payment.payment_method = method
    payment.amount = captured_amount
    payment.status = 'refund_pending' if order.status == 'cancelled' else 'completed'
    payment.verified_at = timezone.now()
    payment.save()

    if order.status == 'cancelled':
        return payment, True

    order.status = 'paid'
    order.save(update_fields=['status'])
    CartItem.objects.filter(cart__user_id=order.user_id).delete()
    return payment, True
