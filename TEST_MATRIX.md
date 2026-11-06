# EazyShop — Master Regression & Edge-Case Test Matrix
**Baseline:** 81 existing tests (all passing).
**Add:** ~48 new backend tests + ~12 E2E tests across the 4 remediation phases.
**All tests live in:** `api/tests.py` (new sections appended) + `frontend/src/pages/*.test.e2e.js` (Playwright).

---

## Test Matrix

### FIN-01 / FIN-09 / FIN-13 — Authoritative Pricing, Stock, Idempotency
| ID | Scenario | Input | Expected | Type |
|---|---|---|---|---|
| `test_fin01_server_total` | Client sends wrong total | `total_price=1.00`, product=₹1000 | `order.total_price == 1000.00` | Unit |
| `test_fin01_client_price_ignored` | Client sends wrong item price | `price=1.00` for ₹1000 item | `order_item.price == 1000.00` | Unit |
| `test_fin01_negative_tamper` | Negative price/total | `total_price=-500` | 400 Bad Request | Unit |
| `test_fin01_zero_qty` | Zero/negative quantity | `quantity=0` | 400 | Unit |
| `test_fin01_deleted_product` | Product deleted mid-request | product then deleted in same txn | 400, no order | Unit |
| `test_fin01_approved_only` | Unapproved product | `approval_status=pending` | 400 | Unit |
| `test_fin09_stock_starvation` | 1 item in stock | 100 concurrent requests (threaded, `select_for_update`) | Exactly 1 order created, stock=0 | Concurrency |
| `test_fin09_atomic_rollback` | Insufficient stock detected late | second concurrent request after first locks | 400, no order created | Concurrency |
| `test_fin06_phantom_stock` | Cancel restores only-deducted stock | cancel order created by wallet flow | stock unchanged (no double-restore) | Unit |
| `test_fin13_idempotency` | Retry same order request | duplicate `idempotency_key` | 409 Conflict, single order | Unit |
| `test_fin05_razorpay_stock_deducted` | Standard checkout | payment captured | stock decremented by qty | Unit |

### FIN-02 / FIN-03 / FIN-04 / FIN-07 / FIN-08 / FIN-16 — Gift Card, Payment, Split-Pay, Refund
| ID | Scenario | Input | Expected | Type |
|---|---|---|---|---|
| `test_fin02_forged_amount` | Pay ₹10, verify with `amount=500000` | tampered amount | GiftCard balance == 10.00, no mint of 500000 | Unit |
| `test_fin02_amount_from_gateway` | Verify | amount fetched from `payment.fetch()` only | server-total authoritative | Unit |
| `test_fin03_replay_single_use` | Same `razorpay_payment_id` twice | 2nd verify | 400 "already fulfilled" | Unit |
| `test_fin03_replay_concurrent` | 10 concurrent replays of one payment | thread pool | exactly 1 GiftCard minted | Concurrency |
| `test_fin02_signature_tamper` | Valid payment_id, bad signature | forged signature | 400 | Unit |
| `test_fin04_readonly_payments` | Customer POST/PATCH/DELETE `/api/payments/` | fake completed payment | 405/403 | Unit |
| `test_fin04_customer_sees_own` | Customer GET `/api/payments/` | other users' payments | only own orders | Unit |
| `test_fin04_admin_sees_all` | Admin GET | all payments | visible | Unit |
| `test_fin07_split_double_spend` | 2 tabs spend same wallet balance | concurrent `verify_razorpay_payment` | exactly 1 succeeds, other 400 | Concurrency |
| `test_fin07_wallet_rollback` | Split payment, Razorpay fails | signature error after wallet reserved | wallet restored to pre-order balance | Unit |
| `test_fin07_get_or_create_txid` | Wallet-first order + Razorpay verify | `Payment.objects.get_or_create` | Razorpay transaction_id stored | Unit |
| `test_fin08_amount_verified` | Underpaid Razorpay | `payment.fetch()['amount'] < order_total` | 400 payment not marked paid | Unit |
| `test_fin16_refund_webhook` | `payment.refunded` event | Razorpay refund | order refunded + refund record | Unit |
| `test_fin15_invoice_labels` | Generate invoice for cancelled/unpaid order | | invoice says correct status ("Cancelled", not "Refunded") | Unit |

### SEC-01 / SEC-02 / SEC-07 / SEC-08 / SEC-10 / SEC-12 — RBAC & Authorization
| ID | Scenario | Input | Expected | Type |
|---|---|---|---|---|
| `test_s01_delete_admin_blocked` | Customer `DELETE /api/users/1/` | any user id | 403 | Unit |
| `test_s01_delete_self_blocked` | Customer `DELETE /api/users/<self>/` | self id | 400 | Unit |
| `test_s01_delete_vendor_blocked` | Seller deletes other seller | other seller id | 403 | Unit |
| `test_s01_admin_can_delete` | Admin deletes user | customer id | 200/204 | Unit |
| `test_s02_patch_competitor` | Vendor A patches Vendor B's product | competitor product id | 403/404 | Unit |
| `test_s02_soft_delete_competitor` | Vendor A deletes competitor product | 403/404 | Unit |
| `test_s02_own_product_editable` | Vendor patches own product | own product id | 200 | Unit |
| `test_s02_admin_edit_any` | Admin edits any product | any product id | 200 | Unit |
| `test_s02_create_isolated` | Vendor creates product | vendor field set | vendor == creator | Unit |
| `test_s07_category_public_create_blocked` | Unauthenticated POST category | create category | 401 | Unit |
| `test_s08_wallet_balance_hidden` | Customer GET `/api/users/` | `wallet_balance` in response | absent | Unit |
| `test_s08_pii_leak_blocked` | Customer GET `/api/users/{other}/` | email/phone | absent | Unit |
| `test_s08_admin_pii_visible` | Admin GET `/api/users/` | PII fields | visible | Unit |
| `test_s10_ssrf_pdf` | Image URL points to metadata/internal | `http://169.254.169.254/...` | 400/exception, no outbound request | Unit |
| `test_s10_allowlist` | Image URL from allowed domain | public CDN | image rendered | Unit |
| `test_s12_own_order_delete` | Customer DELETE own order | own order id | 200 (documented behavior) | Unit |
| `test_s12_foreign_order_delete` | Customer DELETE other user's order | other order id | 404 | Unit |

### SEC-05 / SEC-06 / SEC-11 / SEC-15 / SEC-16 / SEC-17 — Auth Hardening
| ID | Scenario | Input | Expected | Type |
|---|---|---|---|---|
| `test_s05_otp_bruteforce_lockout` | 6+ wrong OTP attempts | repeated wrong otp | attempt 6 → 429 + OTP invalidated | Unit |
| `test_s05_otp_timed_out` | OTP older than 5 min | old OTP | 400 expired | Unit |
| `test_s05_csrf_cookie_auth` | Cross-site POST with cookie-auth victim | CSRF-missing request | 403 Forbidden | Unit |
| `test_s06_csrf_mitigation_active` | Valid same-origin request | valid CSRF token | 200 | Unit |
| `test_s11_no_token_in_json` | Login response | `response.data` | no `access`/`refresh` keys | Unit |
| `test_s11_httponly_cookies` | Login response cookies | `access_token` | `httponly=True` | Unit |
| `test_s15_hsts_header` | Production request | response headers | `Strict-Transport-Security` present | Unit |
| `test_s16_logout_blacklist` | Logout with valid token | `POST /api/logout/` | subsequent request with token → 401 | Unit |
| `test_s17_secure_otp` | OTP entropy | 1000 generated OTPs | no duplicates, uniform distribution | Unit |

### ARCH-01 / ARCH-02 / ARCH-04 / ARCH-05 / ARCH-08 — Infrastructure
| ID | Scenario | Input | Expected | Type |
|---|---|---|---|---|
| `test_arch01_cache_sharing` | Multi-worker OTP | OTP generated in worker A, verified in worker B | success (Redis-backed) | Integration |
| `test_arch05_pooler_healthcheck` | Stale connection | after idle > 300s | connection reused cleanly | Integration |
| `test_arch08_indexes_exist` | Catalog filter query | EXPLAIN ANALYZE on `vendor + approval_status` filter | IndexScan, not SeqScan | Integration |
| `test_arch08_orderitem_index` | Order items filter | `?order=...` and `?vendor=...` | IndexScan | Integration |

### FE-P0 / FE-P1 — Frontend Security & Reliability (Jest + E2E)
| ID | Scenario | Expected | Type |
|---|---|---|---|
| `test_fe_p0_error_boundary` | Child throws | app renders fallback, not WSOD | Jest |
| `test_fe_p0_null_product_card` | `item.product = null` | graceful fallback card | Jest |
| `test_fe_p02_refresh_no_deadlock` | Expired refresh token | redirect to login, no freeze | Jest |
| `test_fe_p02_plain_axios_refresh` | interceptor called | refresh uses unintercepted axios | Jest |
| `test_fe_p03_no_double_submit` | rapid double-click on Place Order | exactly 1 order created | E2E (Playwright) |
| `test_fe_p03_loading_guard` | loading state set before SDK load | button disabled | E2E |
| `test_fe_p1_lazy_chunks` | code-split bundles | < 500 KB initial JS | Lighthouse |
| `test_fe_p2_404_route` | unknown path `/x/y/z` | PageNotFound component, not blank | E2E |
| `test_fe_p2_127_url_migration` | production builds | no `127.0.0.1` in bundle | Jest |
| `test_fe_p2_order_success_refresh` | refresh after order success | receipt persists | E2E |
| `test_fe_p3_cart_badge` | add item to cart | badge shows count | E2E |
| `test_fe_p3_console_not_patched` | runtime error in prod | error logged to console | Jest |

---

## Test Execution Commands

```bash
# Baseline (existing 81)
./ecomenv/bin/python manage.py test api --keepdb

# All backend security tests
./ecomenv/bin/python manage.py test api --keepdb -v 2

# Concurrency stress (wallet double-spend, stock starvation)
./ecomenv/bin/python manage.py test api.EazyShopTitaniumTestSuite.test_fin09_stock_starvation api.EazyShopTitaniumTestSuite.test_fin07_split_double_spend --keepdb

# Frontend unit
cd frontend && npm test -- --watchAll=false

# E2E (after deploying staging)
npx playwright test
```

---

## Regression Gate (must pass before every PR merge)

1. `./ecomenv/bin/python manage.py check` — 0 issues
2. `./ecomenv/bin/python manage.py test api --keepdb` — 81 + new tests pass
3. `ruff check api` — clean
4. Frontend `npm test` — clean
5. Migrations: `python manage.py makemigrations --check --dry-run` — no pending changes
