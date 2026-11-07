"""Versioned canonical initialization terms, independent of mutable order state."""
import hashlib
import json
import unicodedata

from django.core.exceptions import ValidationError


def request_fingerprint(terms):
    encoded = json.dumps(terms, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def merchandise_terms(data, quantities):
    snapshots = {}
    for field in ('shipping_address', 'contact_phone'):
        value = data.get(field)
        if not isinstance(value, str):
            raise ValidationError(f'{field} must be text.')
        # Only formatting equivalences: preserve case, punctuation and interior spacing.
        value = unicodedata.normalize('NFC', value.replace('\r\n', '\n').replace('\r', '\n')).strip()
        if not value:
            raise ValidationError(f'{field} is required.')
        if field == 'contact_phone' and len(value) > 20:
            raise ValidationError('Contact phone must be at most 20 characters.')
        snapshots[field] = value
    use_wallet = data.get('use_wallet', False)
    if type(use_wallet) is not bool:
        raise ValidationError('use_wallet must be a boolean.')
    return {'version': 1, 'purpose': 'merchandise',
            'items': [{'product': pk, 'quantity': quantities[pk]} for pk in sorted(quantities)],
            **snapshots, 'use_wallet': use_wallet}


def gift_terms(amount_minor):
    return {'version': 1, 'purpose': 'gift_card', 'amount_minor': amount_minor}


def request_conflict(intent, terms):
    evidence = intent.request_fingerprint
    if evidence is None and intent.purpose == 'gift_card':
        # The sole original gift term is already immutable and exact. No mutable
        # order fields or wallet-use assumptions are used to infer merchandise terms.
        evidence = request_fingerprint(gift_terms(intent.expected_amount))
    if evidence is None:
        return {'code': 'purchase_request_unverifiable',
                'error': 'Original purchase request evidence is unavailable; reconciliation is required. '
                         'Recover the existing purchase before starting another. Do not replace this key.'}
    if evidence != request_fingerprint(terms):
        return {'code': 'purchase_request_conflict',
                'error': 'This purchase key belongs to different items, delivery details, wallet choice or gift amount. '
                         'Restore the original request or resolve the existing purchase first. Do not replace this key.'}
    return None
