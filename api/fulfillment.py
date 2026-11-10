from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Order


@transaction.atomic
def fulfill_order(order_id, status, *, item_id=None, vendor_id=None):
    """Advance an order or one assigned item. Lock the parent before its lines."""
    order = Order.objects.select_for_update().get(pk=order_id)
    if status not in ('shipped', 'delivered'):
        raise ValidationError("Invalid fulfillment status.")
    order.require_verified_settlement()
    if order.status not in Order.FULFILLABLE_STATUSES:
        raise ValidationError("Order is not eligible for fulfillment.")
    if order.status == 'delivered' and status == 'shipped':
        raise ValidationError("A delivered order cannot return to shipping.")

    items = order.order_items.select_for_update().order_by('pk')
    if item_id is not None:
        items = items.filter(pk=item_id)
        if vendor_id is not None:
            items = items.filter(vendor_id=vendor_id)
    else:
        items = items.exclude(status='cancelled')
        if status == 'shipped':
            items = items.exclude(status='delivered')
    items = list(items)
    if not items:
        raise ValidationError("No eligible items for this fulfillment operation.")

    changed = []
    for item in items:
        if item.status != status:
            item.status = status
            item.save(update_fields=['status'])
            changed.append(item)
    order.refresh_from_db()
    return order, changed
