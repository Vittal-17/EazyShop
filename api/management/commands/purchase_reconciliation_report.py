"""Read-only local inventory; deliberately never calls a payment provider."""
import json
from django.core.management.base import BaseCommand
from api.models import Order, GiftCard, PurchaseIntent, ProviderPaymentClaim, ProviderEvent, Payment, ProviderRefund


class Command(BaseCommand):
    help = 'Report quarantined/unknown purchases without printing PII, payment IDs or gift-card bearer codes.'

    def handle(self, *args, **options):
        report = {
            'legacy_orders_without_intent': Order.objects.filter(purchase_intent__isnull=True).count(),
            'legacy_cards_without_intent': GiftCard.objects.filter(purchase_intent__isnull=True).count(),
            'quarantined_payment_ids': ProviderPaymentClaim.objects.filter(state='quarantined').count(),
            'unresolved_intents': PurchaseIntent.objects.filter(state__in=['creating', 'reconciliation']).count(),
            'closed_gift_purchases': PurchaseIntent.objects.filter(purpose='gift_card', state__in=['failed', 'refunded', 'reconciliation']).count(),
            'unresolved_events': ProviderEvent.objects.exclude(state='processed').count(),
            'pending_or_unknown_refunds': Payment.objects.filter(status__in=['refund_pending', 'refund_failed']).count(),
            'terminal_claims_without_refund_evidence': ProviderPaymentClaim.objects.filter(state='refunded', refunds__isnull=True).count(),
            'processed_refund_records': ProviderRefund.objects.count(),
            'claims_awaiting_refund': ProviderPaymentClaim.objects.filter(state='refund_pending').count(),
        }
        self.stdout.write(json.dumps(report, sort_keys=True))
