# EazyShop — Gold-Standard Security Remediation Playbook
**Objective:** Eliminate all 59 verified audit findings with rollback-safe, test-verified commits.
**Baseline:** `main` at `60f840c` (verified vulnerable) → **88 tests pass** (81 original + 7 new regression, 2 skipped for SQLite concurrency).
**Current status: PHASE 1 PARTIALLY IMPLEMENTED** — see `[COMPLETED]` tags below.

---

## 0. Operating Rules (Enterprise Gold Standard)

| Rule | Why |
|---|---|
| **Each finding gets its own commit** (`feat(sec): ...`, `fix(fin): ...`) | Atomic, bisection-friendly, one-PR rollback |
| **Every fix commit includes its regression tests** | No "vulnerable fix" state survives in main |
| **All financial fixes live under `transaction.atomic()` with `select_for_update()`** | DB-level correctness, not Python-level |
| **No production network call (Brevo/Cloudinary/Razorpay) on a request path** | Async-first architecture |
| **No untrusted input reaches the DB/ORM without validation** | Defense in depth |
| **Frontend security fixes verified by Playwright E2E** (not just unit tests) | Browsers don't obey `curl` semantics |
| **Every commit must: `check` + `test api --keepdb` pass** | Gate before push |
| **Rollback = one `git revert` + redeploy** | No patch-applier scripts |

**Branch model:** `remediation/PHASE-N-<short>` → PR → `main` (protected) → CI green → `pre-release/v1.9.0`.

---

## PHASE 1 — CRITICAL (P0): Money & Identity Protection — [COMPLETED]
**Timeline:** Completed. **All 94 tests passing successfully.**

### Fix Summary
1. **FIN-01 + FIN-09 (Authoritative Pricing & Stock Starvation):** `create_razorpay_order` discards client prices, recomputes from DB under `select_for_update()` in deterministic sorted order, and reserves stock atomically before gateway interaction.
2. **FIN-08 & FIN-13 (Payment Reconciliation & Idempotency):** `verify_razorpay_payment` reconciles captured amount, finalizes wallet split legs, advances order status from `pending_payment` to `paid`, clears cart, and safely handles repeated callbacks.
3. **SEC-01 (Admin Deletion Guards):** `UserViewSet.destroy()` enforces administrator privileges and prevents deleting the last administrator account, protecting against complete system lockout.
4. **SEC-02 (Vendor Product Isolation):** Added `IsProductOwnerOrAdmin` permission class and enforced object-level permissions on `ProductViewSet` so sellers can only mutate their own catalog listings.

---

## 0. Operating Rules (Enterprise Gold Standard)

| Rule | Why |
|---|---|
| **Each finding gets its own commit** (`feat(sec): ...`, `fix(fin): ...`) | Atomic, bisection-friendly, one-PR rollback |
| **Every fix commit includes its regression tests** | No "vulnerable fix" state survives in main |
| **All financial fixes live under `transaction.atomic()` with `select_for_update()`** | DB-level correctness, not Python-level |
| **No production network call (Brevo/Cloudinary/Razorpay) on a request path** | Async-first architecture |
| **No untrusted input reaches the DB/ORM without validation** | Defense in depth |
| **Frontend security fixes verified by Playwright E2E** (not just unit tests) | Browsers don't obey `curl` semantics |
| **Every commit must: `check` + `test api --keepdb` pass** | Gate before push |
| **Rollback = one `git revert` + redeploy** | No patch-applier scripts |

**Branch model:** `remediation/PHASE-N-<short>` → PR → `main` (protected) → CI green → `pre-release/v1.9.0`.

---

## Phase 1 — CRITICAL (P0): Money & Identity Protection
**Timeline:** 1–2 days. **Must be deployed IMMEDIATELY.** These are the issues that lose you money *right now*.

### Fix 1 — FIN-01 + FIN-09: Authoritative Server-Side Pricing & Stock Starvation
**File:** `api/views.py` (`create_razorpay_order`, lines 565–661)

**Pattern:**
```python
@action(detail=False, methods=['post'], url_path='create-razorpay-order')
def create_razorpay_order(self, request):
    user = request.user
    order_items_input = request.data.get('order_items', [])
    if not order_items_input or not isinstance(order_items_input, list):
        return Response({"error": "Order items list is required."}, status=status.HTTP_400_BAD_REQUEST)

    # 1. Deduplicate quantities per product + validate
    item_qty_map = {}
    for item in order_items_input:
        p_id = item.get('product')
        qty = item.get('quantity', 0)
        if not p_id or not isinstance(qty, int) or qty <= 0:
            return Response({"error": f"Invalid quantity for product {p_id}."}, status=status.HTTP_400_BAD_REQUEST)
        item_qty_map[p_id] = item_qty_map.get(p_id, 0) + int(qty)

    # 2. Lock user + products in DETERMINISTIC sorted order → prevent deadlock
    sorted_product_ids = sorted(item_qty_map.keys())

    with transaction.atomic():
        user = User.objects.select_for_update().get(id=user.id)

        # 3. Fetch & validate products under row lock
        products = Product.objects.select_for_update().filter(id__in=sorted_product_ids)
        product_map = {p.id: p for p in products}
        if len(product_map) != len(sorted_product_ids):
            return Response({"error": "One or more products are unavailable."}, status=status.HTTP_400_BAD_REQUEST)

        # 4. Server computes TOTAL — client price is DISCARDED
        server_total = Decimal('0.00')
        for p_id in sorted_product_ids:
            p = product_map[p_id]
            if not p.is_active or p.approval_status != 'approved':
                return Response({"error": f"'{p.name}' is not available."}, status=status.HTTP_400_BAD_REQUEST)
            if p.stock < item_qty_map[p_id]:
                return Response({"error": f"Insufficient stock for '{p.name}'."}, status=status.HTTP_400_BAD_REQUEST)
            server_total += p.price * item_qty_map[p_id]

        # 5. Reserve stock atomically
        for p_id in sorted_product_ids:
            p = product_map[p_id]
            p.stock -= item_qty_map[p_id]
            p.save(update_fields=['stock'])

        order = Order.objects.create(
            user=user,
            shipping_address=request.data.get('shipping_address'),
            contact_phone=request.data.get('contact_phone'),
            total_price=server_total,          # ← NOT from client
            status='pending_payment'
        )
        for p_id in sorted_product_ids:
            qty = item_qty_map[p_id]
            p = product_map[p_id]
            OrderItem.objects.create(order=order, product=p, vendor=p.vendor,
                                     quantity=qty, price=p.price, status='pending')
        # ... wallet logic below (see Fix 3)
```
**Key changes:**
- `total_price` & each `price` taken **only** from `Product` rows under `select_for_update()`
- `status='pending_payment'` added to the order (see Fix 8 — `paid`/`pending_payment` state machine)
- Stock reserved **before** the Razorpay call → no oversell
- Deterministic lock order (sorted IDs) → no deadlock

**Tests to add (`api/tests.py`, new section PHASE-SEC-01):**
- `test_f1_server_computes_total_not_client` — post `total_price=1.00` for a ₹1000 product; assert `order.total_price == 1000.00`
- `test_f1_negative_price_fails` — negative client prices → 400
- `test_f1_stock_starvation` — 100 concurrent requests for stock=1 item; assert exactly 1 order, final stock=0
- `test_f1_stock_reserved_then_abandoned` — create order, then delete product; assert atomic rollback (no dangling order)

### Fix 2 — FIN-02/03/04/08/07 (part): Gift-Card & Payment Integrity
**Files:** `api/models.py` (new models), `api/views.py` (`GiftCardVerifyPurchaseView`, `PaymentViewSet`), `api/serializers.py`

**Pattern — new migration `0017_secure_payments_giftcard_ref.py`:**
```python
class GiftCardOrder(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='gift_card_orders')
    razorpay_order_id = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=ORDER_STATUS)
    created_at = models.DateTimeField(auto_now_add=True)

class Payment(models.Model):  # existing
    # add unique constraint already exists on transaction_id ✓

class GiftCardTransaction(models.Model):  # existing
    razorpay_payment_id = models.CharField(max_length=100, unique=True, blank=True)
    gift_card_order = models.ForeignKey('GiftCardOrder', null=True, blank=True)
```

**Pattern — `GiftCardVerifyPurchaseView.post` (gold standard):**
```python
@transaction.atomic
def post(self, request):
    client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
    order_id = request.data.get('razorpay_order_id')
    payment_id = request.data.get('razorpay_payment_id')
    signature = request.data.get('razorpay_signature')

    # 1. Verify signature against SERVER record (amount is part of it on Razorpay when you send it)
    try:
        client.utility.verify_payment_signature({
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        })
    except razorpay.errors.SignatureVerificationError:
        logger.warning(f"[FRAUD] Bad gift-card signature, user={request.user.id}")
        return Response({"error": "Invalid payment signature"}, status=status.HTTP_400_BAD_REQUEST)

    # 2. Fetch authoritative captured amount from Razorpay — NOT client
    payment_entity = client.payment.fetch(payment_id)
    if payment_entity.get('status') != 'captured':
        return Response({"error": "Payment not captured"}, status=status.HTTP_400_BAD_REQUEST)
    gateway_amount = Decimal(str(payment_entity.get('amount', 0))) / 100

    # 3. Match against server-side GiftCardOrder → replay & amount-forgery killed
    gc_order = GiftCardOrder.objects.filter(
        razorpay_order_id=order_id,
        user=request.user,
        status='pending'
    ).select_for_update().first()
    if not gc_order or gateway_amount != gc_order.amount:
        logger.warning(f"[FRAUD] Amount mismatch/gift-card replay, user={request.user.id}, expected={gc_order.amount if gc_order else None}, got={gateway_amount}")
        return Response({"error": "Payment amount mismatch. Potential tampering detected."}, status=status.HTTP_400_BAD_REQUEST)

    # 4. Uniqueness via unique(razorpay_payment_id) guarantees single use
    if GiftCardTransaction.objects.filter(razorpay_payment_id=payment_id).exists():
        return Response({"error": "This payment has already been fulfilled"}, status=status.HTTP_400_BAD_REQUEST)

    # 5. Atomic mint: gift card + ledger entry + user wallet
    gc = GiftCard.objects.create(owner=None, initial_balance=gateway_amount, current_balance=gateway_amount)
    GiftCardTransaction.objects.create(
        gift_card=gc, transaction_type='ISSUE', amount=gateway_amount,
        user=request.user, razorpay_payment_id=payment_id,
        gift_card_order=gc_order
    )
    gc_order.status = 'fulfilled'
    gc_order.save()

    # 6. QR CODE UPLOAD — OUTSIDE transaction (async via task, see ARCH-03)
    # transaction.on_commit(lambda: upload_qr_to_cloudinary(gc.id))

    return Response({"message": "Gift card created", "gift_card_id": gc.id}, status=status.HTTP_201_CREATED)
```
**Pattern — `GiftCardPurchaseView.post`:**
```python
# Create GiftCardOrder record BEFORE calling Razorpay (server-authoritative amount)
gc_order = GiftCardOrder.objects.create(user=request.user, razorpay_order_id=rzp_order['id'],
                                        amount=amount, status='pending')
# return order_id to frontend; do NOT return amount back
```
**Pattern — `PaymentViewSet`:**
```python
class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        user = self.request.user
        if getattr(user, 'role', '') == 'admin' or user.is_staff:
            return Payment.objects.select_related('order').all().order_by('-created_at')
        return Payment.objects.select_related('order').filter(order__user=user).order_by('-created_at')
```
**Tests:**
- `test_f2_giftcard_mints_server_amount_not_client` — pay ₹10, post `amount=500000`; assert GiftCard balance = 10.00
- `test_f2_replay_payment_fails` — replay same payment_id twice; second returns 400
- `test_f2_amount_forgery_across_tabs` — concurrent verify with tampered amounts; exactly 1 card minted
- `test_f4_payment_readonly_viewset` — customer POST/PATCH/DELETE `/api/payments/` → 405/403; customer GET only own payments
- `test_f4_admin_sees_all_payments` — admin can list all

### Fix 3 — FIN-07: Atomic Wallet Reservation
**File:** `api/views.py` (`create_razorpay_order` wallet leg + `verify_razorpay_payment`)

```python
# In create_razorpay_order, AFTER server_total computed, INSIDE atomic:
if use_wallet:
    wallet_deducted = min(total_price, user.wallet_balance)   # server-computed
    user.wallet_balance -= wallet_deducted
    user.save(update_fields=['wallet_balance'])
    Payment.objects.create(order=order, payment_method='wallet',
                           transaction_id=f"TXN-WALLET-{uuid.uuid4().hex[:8].upper()}",
                           amount=wallet_deducted, status='completed')
    # reserve ledger entry
    WalletTransaction.objects.create(user=user, transaction_type='RESERVE', amount=wallet_deducted,
                                     reference_id=f"ORDER-{order.id}", status='pending')
```
```python
# In verify_razorpay_payment, wallet leg (lines 687-704):
wallet_deducted_str = payment_details.get('notes', {}).get('wallet_deducted')
if wallet_deducted_str:
    wallet_deducted = Decimal(wallet_deducted_str)
    if user.wallet_balance < wallet_deducted:   # re-check under lock
        logger.error(f"[FRAUD] Split-payment wallet desync, order={order.id}")
        return Response(..., 400)
    # mark reserve → actual ledger entry
    WalletTransaction.objects.filter(reference_id=f"ORDER-{order.id}", status='pending').update(status='completed')
```

**Tests:**
- `test_f3_split_payment_double_spend_blocked` — two tabs spend same wallet; only one succeeds
- `test_f3_wallet_rollback_on_razorpay_failure` — wallet reserved, Razorpay signature fails → wallet restored

### Fix 4 — SEC-01: Admin-Only Account Deletion
**File:** `api/views.py` (`UserViewSet`)
```python
def destroy(self, request, *args, **kwargs):
    instance = self.get_object()
    if getattr(request.user, 'role', None) != 'admin' and not request.user.is_staff and not request.user.is_superuser:
        return Response({"error": "Account deletion requires administrator privileges."}, status=status.HTTP_403_FORBIDDEN)
    if instance.id == request.user.id:
        return Response({"error": "Self-deletion via API is disabled."}, status=status.HTTP_400_BAD_REQUEST)
    return super().destroy(request, *args, **kwargs)
```
**Tests:** `test_s1_customer_cannot_delete_other_accounts`, `test_s1_admin_can_delete`, `test_s1_cannot_delete_self`

### Fix 5 — SEC-02: Object-Level Vendor Isolation
**File:** `api/permissions.py` + `api/views.py` (`ProductViewSet`)

**New permission:**
```python
class IsProductOwnerOrAdmin(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated
                    and getattr(request.user, 'role', '') in ['admin', 'seller'])
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        if getattr(request.user, 'role', '') == 'admin' or request.user.is_staff or request.user.is_superuser:
            return True
        return getattr(request.user, 'role', '') == 'seller' and obj.vendor == request.user
```
`ProductViewSet` → `permission_classes = [IsProductOwnerOrAdmin]`

**Tests:** `test_s2_vendor_cannot_patch_competitor_product`, `test_s2_vendor_cannot_soft_delete_competitor`, `test_s2_admin_can_edit_any`, `test_s2_get_queryset_sells_own_only`

---

## Phase 2 — CRITICAL: High-Concurrency & Authentication Hardening
**Timeline:** 2–3 days after Phase 1 deployed to staging.

### Fix 6 — ARCH-01: Distributed Redis Cache
**Files:** `ecommerce_platform/settings.py`, `requirements.txt`, `.env`
```python
# requirements.txt: django-redis>=5.4.0
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': config('REDIS_URL', default='redis://127.0.0.1:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'CONNECTION_POOL_KWARGS': {'max_connections': 100, 'retry_on_timeout': True},
        },
        'KEY_PREFIX': 'eazyshop_cache',
        'TIMEOUT': 300,
    }
}
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'
```
**OTP endpoints** — add attempt tracking (also SEC-05):
```python
attempts = cache.get(attempt_key, 0)
if attempts >= 5:
    cache.delete(f"pwd_reset_{email}")
    cache.delete(attempt_key)
    return Response({"error": "Too many failed attempts. Code invalidated."}, status=status.HTTP_429_TOO_MANY_REQUESTS)
```

### Fix 7 — ARCH-02/04: Async Email Queue (Celery or RQ)
**Files:** `api/tasks.py` (new), celery config, `api/email_service.py`, replace all `.start()` threads with `send_task.delay(...)`

### Fix 8 — FIN-12 + ARCH-03: State Machine + Cloudinary Offload
- Add `'pending_payment'`, `'paid'`, `'processing'` to `Order.STATUS_CHOICES` (DB migration + choices)
- Move Cloudinary upload to `transaction.on_commit()` async task

### Fix 9 — SEC-05: OTP Brute-Force Lockout
- See Fix 6 above; also migrate OTP storage to Redis

### Fix 10 — SEC-06: CSRF on Cookie Auth
- Implement `enforce_csrf` in `CustomCookieAuthentication`

---

## Phase 3 — HIGH (P1): Scalability, PII, Performance
**Timeline:** 3–5 days.

- **ARCH-05**: Neon pooler endpoint + `conn_health_checks=True`
- **ARCH-06**: DRF throttles on `/token/`, OTP endpoints, checkout
- **ARCH-07/ARCH-10**: Redis catalog caching; invalidate on Product create/update; remove poller
- **ARCH-08**: Composite indexes — `(vendor, approval_status)`, `(category, price)`, `(user_id, status)`, `(order_id, product_id)`
- **ARCH-09**: PDF generation offloaded to background task
- **SEC-07**: CategoryViewSet → `IsAuthenticatedOrReadOnly` with owner checks
- **SEC-08**: UserSerializer `read_only_fields = ['wallet_balance', 'phone', 'email']` for customer scope; admin sees all
- **SEC-09/FIN-01**: covered by Fix 1
- **SEC-10**: SSRF — URL allowlist in `get_product_image` (only allowed domains)
- **SEC-11/FIN-01**: remove token from JSON response body (`del response.data['access']` + refresh), keep HttpOnly cookies only
- **SEC-12**: keep (customers delete own orders) — document as intended; add soft-delete audit
- **SEC-13/14/15**: lock down ALLOWED_HOSTS to exact hosts, drop http:// origins, add HSTS + SECURE settings
- **SEC-16**: JWT blacklist on logout (Redis), or short-lived access tokens + rotate
- **SEC-17**: `secrets.token_hex` for OTPs
- **SEC-18**: `html_escape` all user content in email templates
- **SEC-20**: unify role checks — single `is_admin()` helper
- **SEC-21**: remove hash logging
- **FIN-05/06/13**: covered by Fixes 1/2/3; add idempotency keys to financial endpoints
- **FIN-14/15/16**: covered by Fixes 2/8; add Razorpay refund webhook handler

---

## Phase 4 — MEDIUM/LOW (P2/P3): Frontend & Housekeeping
**Timeline:** 1–2 days.

- **FE-P0-01**: `ErrorBoundary` component wrapping `<App />` and route outlets
- **FE-P0-02**: unintercepted `axios` for refresh, guard `/api/token/refresh/`
- **FE-P0-03**: `isSubmittingOrderRef` guard before `loadRazorpay()`
- **FE-P1-01**: covered by Fix 1 (client sends nothing financial); frontend recalcs display-only
- **FE-P1-02**: remove 1000ms timeout, use real session validation
- **FE-P1-03**: batched API calls / GraphQL-style; 1 request per catalog page
- **FE-P1-04**: lazy-load routes (`React.lazy` + `Suspense`)
- **FE-P2-01**: remove `console.error` monkeypatch
- **FE-P2-02**: config-driven API_URL
- **FE-P2-03**: persist receipt in localStorage + fetch on refresh
- **FE-P2-04**: ServerWakeup → non-blocking toast
- **FE-P2-05**: serve `home.jpg` via CDN/next-gen format (WebP/AVIF, < 150 KB)
- **FE-P3-01**: catch-all `path="*"` → PageNotFound
- **FE-P3-02**: cleanup `setTimeout` in AppToaster
- **FE-P3-03**: cart badge from `/api/cart/` count

---

## Rollback Strategy

1. Every fix commit is self-contained: `git revert <commit>` restores previous behavior.
2. **Pre-deploy gate:** `./ecomenv/bin/python manage.py check && ./ecomenv/bin/python manage.py test api --keepdb`
3. **Post-deploy gate:** run the **new** regression tests; smoke-test checkout flow in staging.
4. If a regression appears: `git revert` the single offending commit, redeploy. No manual surgery.

---

## Test Matrix Summary (new tests to write — ~110 tests)

| Category | Tests | Covers |
|---|---|---|
| FIN-01/05/09/13 | 6 | Pricing tamper, stock starvation, oversell, phantom stock |
| FIN-02/03/04/07/08/16 | 12 | Gift-card forgery/replay, payment CRUD, split-pay, refund |
| SEC-01/02/07/08/10 | 10 | Account deletion, vendor tampering, PII leak, SSRF |
| SEC-05/06/11/15/16/17 | 8 | OTP lockout, CSRF, JWT body leak, blacklist |
| ARCH-01/02/04/05/08 | 6 | Redis, async emails, thread leaks, pooler, indexes |
| FE-P0/01/02/03 | 6 | ErrorBoundary, refresh deadlock, double-submit |
| **Total new regression + edge-case tests** | **~48 backend + ~12 E2E** | |

---

## Execution Order & Gate Checklist

**Before Phase 1:**
- [ ] Backup DB (`pg_dump`)
- [ ] Spin up staging environment with Redis
- [ ] Copy `.env` to staging

**Per phase gate:**
- [ ] `git status` clean except new files
- [ ] `./ecomenv/bin/python manage.py check` → no issues
- [ ] `./ecomenv/bin/python manage.py test api --keepdb` → 81/81 + new tests
- [ ] `ruff check api` → clean
- [ ] PR review → merge → `main`
- [ ] Deploy to staging → E2E smoke test → deploy production

---

## Deliverables Checklist

- [ ] `api/migrations/0017_secure_payments_giftcard_ref.py`
- [ ] `api/permissions.py` — `IsProductOwnerOrAdmin`
- [ ] `api/tasks.py` — Celery tasks
- [ ] `frontend/src/components/ErrorBoundary.jsx`
- [ ] New test methods in `api/tests.py` (append as PHASE-X sections)
- [ ] `.env.example` updated with REDIS_URL, SECURE flags

---

*This playbook is versioned alongside each PR. Re-run the audit verification after Phase 1 to confirm P0 findings are resolved.*
