import hashlib
import time
from django.core.cache import cache
from rest_framework.response import Response
from rest_framework import status

def _sanitize_and_hash_key(idempotency_key):
    """
    Sanitize and SHA-256 hash idempotency key to prevent Redis memory bloat,
    spaces/control-character issues, and cache key collisions.
    """
    if not idempotency_key:
        return None
    raw_str = str(idempotency_key).strip()[:256]
    return hashlib.sha256(raw_str.encode('utf-8')).hexdigest()

def get_idempotency_key(request):
    """Extract idempotency key from HTTP header or request payload."""
    key = request.headers.get('Idempotency-Key')
    if not key and hasattr(request, 'data') and isinstance(request.data, dict):
        key = request.data.get('idempotency_key')
    return str(key).strip() if key else None

def check_idempotency(user_id, endpoint_name, idempotency_key):
    """
    Check if an idempotent request has already been completed or is in-flight.
    Returns:
        (cached_response, lock_acquired)
        - If cached_response is not None: caller should immediately return Response(cached_response['data'], status=cached_response['status'])
        - If not lock_acquired: concurrent request is processing with this key
    """
    if not idempotency_key or not user_id:
        return None, True

    key_hash = _sanitize_and_hash_key(idempotency_key)
    cache_key = f"idem_{endpoint_name}_{user_id}_{key_hash}"
    cached = cache.get(cache_key)
    if cached:
        return cached, True

    lock_key = f"idem_lock_{endpoint_name}_{user_id}_{key_hash}"
    # Atomic test-and-set lock for in-flight protection (valid for 30s)
    lock_acquired = cache.add(lock_key, True, timeout=30)
    if not lock_acquired:
        # Check one more time in case it just finished
        cached = cache.get(cache_key)
        if cached:
            return cached, True
        return None, False

    return None, True

def store_idempotency_result(user_id, endpoint_name, idempotency_key, response_data, status_code, timeout=300):
    """Store the completed idempotent response and release the in-flight lock."""
    if not idempotency_key or not user_id:
        return

    key_hash = _sanitize_and_hash_key(idempotency_key)
    cache_key = f"idem_{endpoint_name}_{user_id}_{key_hash}"
    lock_key = f"idem_lock_{endpoint_name}_{user_id}_{key_hash}"

    cache.set(cache_key, {'data': response_data, 'status': status_code}, timeout=timeout)
    cache.delete(lock_key)

def release_idempotency_lock(user_id, endpoint_name, idempotency_key):
    """Release in-flight lock if an error occurs before completion."""
    if not idempotency_key or not user_id:
        return
    key_hash = _sanitize_and_hash_key(idempotency_key)
    lock_key = f"idem_lock_{endpoint_name}_{user_id}_{key_hash}"
    cache.delete(lock_key)
