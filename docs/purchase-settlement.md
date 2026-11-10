# Purchase intents and payment reconciliation (Mission 005)

## Contract and trust boundaries

Checkout computes merchandise totals from locked product rows, reserves stock and
any wallet contribution, and creates a `PurchaseIntent` in the same transaction.
Gift checkout validates a positive INR amount with exactly representable minor
units and persists a gift intent. The authenticated purchaser, purpose, object,
currency, gateway amount and wallet debit are immutable. PostgreSQL triggers also
reject bulk rebinding or reopening a closed intent. The provider-order binding is
write-once. Full wallet checkout has a zero gateway leg and a recorded wallet debit;
it does not fabricate a provider capture.

Only then does the application create the Razorpay order, outside database locks,
with a five-second request timeout. Its UUID receipt identifies the local intent
for an operator; receipts and notes are never payment authorization. The response
must match the persisted amount/currency before its ID is bound and exposed.

Both browser verification and signed `payment.captured`/`order.paid` webhooks use
`api/settlement.py`. Browser access is scoped to the intent purchaser before any
payment lookup or provider call, and the signature uses the persisted provider
order ID. The fetched (or signed webhook) payment must have the matching ID, order,
INR currency, exact positive integer amount, captured status and zero refunded
amount. Authorized-only payments do not settle. Provider notes cannot supply a
wallet contribution or ownership. Administrator visibility grants no right to
verify another buyer's purchase.

`ProviderPaymentClaim.payment_id` is a global primary key across both purposes;
its intent is one-to-one. Concurrent claims cannot assign the same payment to
another purchase, or a second payment to the same intent. Claim and financial
outcome commit atomically. Merchandise locks order then intent; gift issuance
locks intent. Cancellation and webhook restocking lock user before sorted products,
matching checkout. Provider I/O always precedes or follows the locked transaction.

A settled intent and captured claim (or a full wallet-funded intent) are additional
requirements for Mission 002 fulfillment. Refunded/cancelled purchases cannot
reactivate. Wallet refunds require the original debit and verified payment leg.
Generic payment APIs remain read-only, and financial Django-admin records,
including gift cards/intents/claims, cannot be added, changed or deleted.

## Retry and delivery behavior

Send a stable `Idempotency-Key` header or `idempotency_key` body value (at most 128
characters) on purchase initialization. Uniqueness is durable per purchaser and
purpose, not cache-dependent. Existing clients without a key still work but each
initialization is a separate purchase; they must adopt this contract for safe
initialization retries. React retains a scoped key in sessionStorage across refresh
and unknown outcomes, clearing it only after confirmed settlement/cancellation. A failed attempt releases
the UI submission lock and resumes the same key/provider order; it does not
create a new purchase. A reordered failure or dismissal after a capture callback
never clears the unresolved key or automatically cancels that purchase.
No JWT or gift-card code is written to that storage.

Initialization keys are also bound to immutable canonical request terms, stored
as a SHA-256 fingerprint (not an additional copy of customer address/contact data).
Merchandise terms include sorted product IDs with duplicate quantities aggregated,
shipping/contact snapshots and the explicit wallet-use choice. Product IDs and
quantities retain the positive JSON integer contract; wallet use is a JSON boolean
with omitted meaning false. Snapshots normalize Unicode NFC, line endings and outer
whitespace, preserving interior whitespace, case, punctuation and phone leading
zeros. Gift terms contain the exact integer minor-unit amount, so equivalent decimal
representations compare equally. Server prices and current wallet/stock balances
are not retry inputs: an identical retry recovers the original financial terms.

A valid but changed request under the same key returns HTTP 409 with code
`purchase_request_conflict` before provider calls or financial mutation. React shows
the server message and retains the key; it never rotates an unresolved key to evade
the conflict. Restore the original request or resolve the existing purchase first.
Identical pending retries return the same checkout identifiers; settled retries
recover the existing purchase, including the original gift without reopening the
gateway. Creating/unknown provider outcomes still return 409 without a second
provider request, since a safe checkout identifier may not yet exist.

- `payment.failed` and `payment.authorized` are attempt-level observations in the
  signed-event inbox. They do not close the purchase, release stock, refund a wallet
  debit or claim the payment. A later captured event (same or different attempt ID)
  can settle an eligible pending purchase exactly once. Explicit cancellation and
  terminal refund guards still apply.
- A capture verified twice returns the same authorized financial outcome.
- Gift issuance creates the card and ISSUE transaction atomically; each intent
  has at most one card. The purchaser can recover recent purchases through
  authenticated `GET /api/gift-cards/purchase/` and the gift page. The endpoint
  returns the most recent 100 intents; older purchases require operator support.
- Gift codes are bearer redemption credentials, intentionally shareable with the
  recipient. The unclaimed card has no recipient owner until one atomic redemption
  credits the recipient wallet and records the ledger. The purchaser alone can
  retrieve an unclaimed code. QR images are returned inline over the authenticated
  response; no new redemption code is uploaded to public Cloudinary storage.
- Failed local finalization rolls back the claim, payment/card and state together.
  Retrying the same proof or delivering the signed webhook can finalize it later.
- Signed events have a durable, deduplicated inbox containing only a body hash,
  event type and provider identifiers, not raw payment/customer data. Unknown or
  rejected financial events remain marked `reconciliation`; retryable unknowns
  return 503. No success shortcut skips current financial-state checks.
- Provider-order creation timeout/invalid response/local binding failure is an
  **unknown outcome**, not proof of failure. The intent remains `reconciliation`,
  with stock/wallet reservations intact. The same key returns 409 and does not
  call order creation again. The customer may cancel a known merchandise order
  to release its validated reservation; the unresolved intent is retained.
- Capture-fetch timeouts return 503; retry the same purchase. Do not pay again.
- A late merchandise capture is recorded as refund-pending without reopening the
  order; one refund attempt occurs outside locks. A late gift capture for an explicitly closed or historical failed intent
  is claimed as refund-pending and requires reconciliation; no card is issued.
  New failed-attempt webhooks no longer put gift intents into that terminal state.
- A cancellation stages a refund before provider I/O. A processed response and a
  signed refund event use the same accounting service. Each needs a refund ID,
  bound payment ID, INR currency, positive integer amount and processed status,
  plus an independent provider payment fetch outside locks. The fetch must match
  the stored order/currency/captured amount, with a valid cumulative refunded
  amount. Pending responses stay pending; exceptions remain `refund_failed`
  (an **unknown outcome**, despite that historical label). A repeated cancellation
  does not submit another refund.
- Migration 0027 adds `ProviderRefund`: globally unique refund ID, payment-claim
  reference, processed minor-unit amount, currency, provider cumulative snapshot
  and timestamp. Service writes are append-only and Django admin is read-only.
  A duplicate refund is not counted twice; changed terms for an existing ID fail.
  Both the sum of distinct processed refunds and provider cumulative evidence must
  equal the original captured amount before classification as fully refunded.
  A newer provider counter by itself cannot fill missing refund evidence.
- Partial or incomplete refund evidence sets the intent to `reconciliation` and
  the claim/payment to `refund_pending`. No automatic restock, order cancellation
  or wallet credit follows a partial webhook. Further fulfillment is blocked.
  Generic cancellation is blocked while these processed liabilities are unresolved.
  Later cumulative full evidence may reverse an unfulfilled order and return its
  original wallet reservation exactly once. Explicit customer cancellation that
  preceded the refund has already released those reservations; refund accounting
  never releases them again. Shipped/delivered orders need a separate returns
  decision; gateway refunds do not automatically restock them.
- Any processed gift refund freezes redemption without erasing the card's recorded
  balance. A full provider refund is distinguished from a partial one in the claim
  and evidence ledger. If the card was already redeemed, the purchase remains in
  `reconciliation` even after a full gateway refund. It receives no second credit
  or invented negative wallet balance. Spent-value recovery requires a deliberate,
  audited business decision.

## Rollout and legacy quarantine

Use a maintenance window: stop old application writers and drain in-flight
checkout before applying 0025 through 0028, then deploy backend and frontend together.
Mixed old/new writers bypass the intent contract and are unsupported. Back up and
verify restore procedures first. Keep migrations 0023/0024 intact.

0025 adds intents, the global payment-claim table and the signed-event inbox. It
reserves every historical non-wallet Payment ID and GiftCardTransaction payment
ID as **quarantined**, collapsing overlaps without modifying existing orders,
payments, cards, wallet balances or ledgers. It does not infer who paid or fabricate
purchase intents. 0026 adds PostgreSQL immutable-binding triggers. Review migration 0027 adds the
processed-refund evidence table without altering 0025/0026. These migrations
were tested forward and backward on the isolated test database.

0028 adds the nullable request fingerprint and a PostgreSQL trigger preventing
changes, including NULL-to-value rewrites. It preserves 0025–0027 unchanged and does
not invent historical request evidence. Pre-0028 merchandise initialization retries
return 409 `purchase_request_unverifiable`: mutable order snapshots and the original
wallet-use choice cannot safely be reconstructed. Existing verification, order
history and eligible cancellation paths remain available; operators must reconcile
unresolved purchases without replacing their keys. Legacy gifts can be compared
using their already immutable expected minor-unit amount, without a backfill.

Historical orders without an intent cannot newly fulfill or use automatic
cancellation/refund logic. Historical cards without settled intents cannot redeem.
Existing balances/history remain visible and unchanged. Previously published QR
images cannot be recalled by this patch: assess old codes and provider evidence
before restoring any historical redemption capability.

Run the read-only inventory in the deliberately selected environment:

```bash
# Local only; .env.local must identify the isolated eazyshop_dev role/database.
ecomenv/bin/python manage.py purchase_reconciliation_report
```

It prints counts only, not customer data, provider payment IDs or gift-card codes.
Privileged operators can inspect the read-only intent/claim/event admin records.
Review all legacy records and quarantined claims before taking any financial action.
The report also counts terminal claims without itemized refund evidence. Old
misclassified refunds or intents closed by pre-review `payment.failed` handling
are not automatically reopened: their histories can overlap customer cancellation
or actual refunds. Reconcile them deliberately; no new migration invents evidence.
For current partial claims, the unrefunded provider liability is `claim.amount`
minus the sum of its distinct `ProviderRefund.amount` values. An intent in
reconciliation may also include missing itemized evidence or spent gift liability;
inspect the recorded provider counters and wallet ledger rather than interpreting
that subtraction as permission to pay or credit anything.
There is intentionally no public or generic-admin “mark paid” or unquarantine action.

For unresolved purchases, an authorized operator must independently reconcile the
provider account's order/payment/refund records against the immutable local terms,
UUID receipt, purchaser, ledger, stock and all historical claims. A receipt/note
alone is insufficient. Check actual refund status before attempting another refund.
Record the evidence and decision in the organization's restricted audit system.
Any historical adoption or recovery that would mutate bindings needs a separately
reviewed, narrowly scoped migration/tool; do not disable triggers or hand-edit rows.
Do not auto-credit or reissue when evidence is missing or a payment funded both
legacy purposes. This patch intentionally does not automate that adjudication.

Rollback is schema-reversible but is not a safe payment-enabled runtime rollback:
0028 -> 0027 drops fingerprint evidence; preserve it in a backup before rollback
and disable purchase initialization on the old application.
0027 -> 0026 drops only the new refund evidence table; preserve/export that
evidence before rollback. 0026 -> 0025 removes triggers; 0025 -> 0024 drops only the three new tables and
preserves original commerce rows. Export/backup intent/claim/inbox history before
any rollback. Keep checkout, redemption, webhooks and fulfillment disabled when
running the old vulnerable application. Reverting only 0027 still restores the unsafe
pre-review refund policy; disable refund processing during rollback. Prefer a
forward fix after new purchases.

## Verification and operational limits

Run on the isolated PostgreSQL test identity; the runner blocks all provider/network
access and mocks payment, media and email integrations:

```bash
ecomenv/bin/python manage.py test api.test_purchase_intents --noinput -v 2
ecomenv/bin/python manage.py test --noinput -v 2
ecomenv/bin/python manage.py check
ecomenv/bin/python manage.py makemigrations --check --dry-run
cd frontend
CI=true npm test -- --watchAll=false --runInBand
npm run build
```

The regression file uses real SDK HMAC verification and PostgreSQL independent
connections for browser/webhook races, cross-purpose claims and repeated keys.
Migration tests rewind only the guarded `eazyshop_test` schema and restore the
latest migration in a finally block. Existing tests that constructed paid fixtures
now explicitly construct trusted intent evidence in `purchase_test_utils.py`;
application code and migrations never import that fixture helper.

No live provider or browser sandbox transaction was performed. Signature/HTTP
contracts were tested with provider fakes. Before deployment verify the configured
provider account, captured/refund event subscriptions, secrets, retry delivery and
application origins in a dedicated sandbox. Monitor reconciliation counts and
aged creating/pending intents: no background reconciliation worker or automatic
reservation expiration was introduced. A process crash between persistence and
provider creation can leave a creating intent; operators must resolve it rather
than assume it was never sent. Notification delivery remains the existing
best-effort mechanism; it is not part of settlement authority. Partial provider
refunds freeze fulfillment/redemption and require an operator to reconcile the
remaining liability; itemized evidence is durable, but this is not a new customer
partial-refund or returns product flow.

## Initial submission results (2026-11-07; review results follow)

- Pre-fix isolated reproduction: 1 failing regression demonstrated a real SDK-signed
  capture settling merchandise and issuing a second ₹50 gift credit. The same test
  now passes and asserts no gift card or extra wallet ledger entry exists.
- `ecomenv/bin/python manage.py test api.test_purchase_intents api.test_fulfillment --noinput -v 2`:
  **34 passed, 0 failed, 0 skipped** (4.265 seconds).
- `ecomenv/bin/python manage.py test --noinput -v 2`:
  **224 passed, 0 failed, 0 skipped** (116.321 seconds). All 201 baseline named tests
  remain present; 23 new tests cover intents, capture evidence, rollback, recovery,
  migration quarantine and concurrency. All three original and three new real
  PostgreSQL concurrency regressions ran. No deadlocks were observed in those runs;
  this is not a throughput benchmark or a proof of deadlock freedom.
- Database evidence: PostgreSQL **18.6**, Debian `18.6-1.pgdg12+2`, database and login
  both `eazyshop_test`. Test identity/configuration and external-network guards
  remained enabled. No production or unrelated database was contacted.
- `CI=true npm test -- --watchAll=false --runInBand` in `frontend`:
  **62 passed, 0 failed, 21 suites passed** (8.484 seconds), including all 56 baseline
  frontend tests. `npm run build`: compiled successfully.
- `ecomenv/bin/python manage.py check`: no issues.
- `ecomenv/bin/python manage.py makemigrations --check --dry-run`: no changes detected.
- `ecomenv/bin/python manage.py check --deploy`: five local-profile warnings,
  W004/W008/W012/W016/W018 (HSTS, HTTPS redirect, secure session/CSRF cookies, DEBUG).
  These local settings are not a production configuration or deployment approval.
- Migration 0024 -> 0026 -> 0024 -> 0026 was exercised with historical payment/card
  fixtures. Commerce history survived rollback, overlapping legacy IDs produced
  one quarantined claim, and immutable-binding triggers were restored. No existing
  migration file was modified. Only the isolated test schema was migrated here;
  development/deployment migration execution remains an explicit rollout step.
- Initial implementation runs exposed fixture assumptions and a new expiry-field
  typo, all corrected before the final passing runs. Frontend initial failures
  required Web Crypto support in jsdom and explicit SDK mock initialization.
  No baseline tests were removed, renamed or skipped to obtain a passing result.

## Review corrections and final verification (2026-11-07)

Two review findings were reproduced before changing implementation, using the
SDK's real HMAC verifier and isolated signed webhook fixtures. All three initial
regressions failed: failed -> captured left merchandise cancelled, gift capture
returned 503 after failure, and a partial split-payment refund cancelled the order.

The corrected implementation treats failure as an attempt observation, so a later
capture can settle the original pending intent. Unique claims still arbitrate
browser/webhook races. Explicit cancellation, full refund and reconciliation
states are never reopened. React releases its failed-attempt submission lock and
reuses the same persisted purchase key/order. Capture uncertainty retains that key;
a subsequent failure or dismissal cannot automatically cancel/discard it.

The previous refund branch trusted a payment ID without checking processed amount,
currency or cumulative evidence. `api/refunds.py` now validates complete refund
records and independently fetched payment evidence, then applies global refund-ID
deduplication and cumulative accounting in one transaction. Partial liabilities
freeze settlement without restoring stock or wallet funds. Only itemized cumulative
full refunds reverse an eligible unfulfilled purchase. Refund-response handling
from explicit cancellation uses the same validator; incomplete responses cannot
mark a refund complete. The additional table in 0027 is necessary to distinguish
separate partial refunds from duplicate deliveries and retain their evidence.

Validation executed:

- Pre-fix: `ecomenv/bin/python manage.py test api.test_payment_attempts_refunds.AttemptRefundTests --noinput -v 2`
  — 3 expected failures establishing both defects. The same scenarios pass now.
- Focused: `ecomenv/bin/python manage.py test api.test_payment_attempts_refunds api.test_purchase_intents.PurchaseIntentMigrationTests --noinput -v 2`
  — 20 passed, 0 failed/skipped, 3.041 seconds, before adding the final dedicated
  0026 -> 0027 rollback case. That additional case passed in the final full suite.
- Final full: `ecomenv/bin/python manage.py test --noinput -v 2`
  — **244 passed, 0 failed, 0 skipped**, 113.710 seconds. All 201 original baseline
  test names remain; the 224 initial Mission 005 tests plus 20 review tests are
  accounted for. Historical failure-webhook test names were retained, but their
  old cancellation assertions were intentionally corrected to preserve pending
  reservations. Provider refund fixtures now include the required evidence.
- Real PostgreSQL independent-connection cases include failed-attempt -> concurrent
  browser/webhook capture for both purposes, duplicate partial refund delivery,
  and concurrent cumulative-full refund delivery. There were no observed deadlocks.
  Existing stock, shipment, global claim and idempotent checkout races remain green.
- Coverage includes same/different failed attempts, reordered failures/captures,
  explicit cancellation before late capture, duplicate/conflicting refund IDs,
  malformed/wrong-currency/overstated refunds, provider timeouts, local crash/ledger
  rollback, partial/full refunds before capture, recipient redemption, spent gift
  liabilities and partial-cancellation rejection. Assertions include item/order
  state, stock, original debit/refund ledgers, claim, intent, card and ISSUE records.
- `CI=true npm --prefix frontend test -- --watchAll=false --runInBand`
  — **66 passed, 0 failed, 21 suites passed**, 8.598 seconds. New React tests verify
  retrying a failed attempt with the same key/provider order and preserving keys
  after unresolved captures with reordered failure/dismissal callbacks.
- `npm run build` from `frontend` — compiled successfully.
- `ecomenv/bin/python manage.py check` — no issues.
- `ecomenv/bin/python manage.py makemigrations --check --dry-run` — no changes detected.
- `ecomenv/bin/python manage.py check --deploy` — the same five local-profile
  warnings, security.W004/W008/W012/W016/W018; no production configuration was used.
- Migration tests exercised 0024 -> 0027 -> 0024 -> 0027 and independently
  0026 -> 0027 -> 0026 -> 0027 with existing intent/claim/card records. Existing
  financial data survived; no refund evidence was invented. Migrations 0025/0026
  were byte-compared with the previous external patch and are unchanged.
- `git diff --check` passed. Only read-only Git inspection/export was used.

Deployment still requires a coordinated migration/application rollout and review
of pre-review terminal records without refund evidence. Partial/spent liabilities,
missing provider events and unknown outcomes still require operator reconciliation;
there is no new automatic refund-retry worker or reservation-expiry job. No live
provider, production database or real browser payment was exercised. Test provider
calls are fakes, and the isolated PostgreSQL runner blocks external networking.

## Final review: canonical initialization requests (2026-11-07)

- Before the fix, `ecomenv/bin/python manage.py test api.test_purchase_request_terms --noinput -v 2`
  produced **2 expected failures**: changed merchandise address returned 201 and
  changed gift denomination returned 200 under the original key, instead of 409.
- Expanded request-term API regressions: **13 passed**, 0 failures/skips. The final
  file adds two independent-connection PostgreSQL conflicting-retry races and one
  migration test, for **16 new backend tests** total.
- `ecomenv/bin/python manage.py test --noinput -v 2`: **260 passed, 0 failed,
  0 skipped**, 116.085 seconds. All 244 previous named backend tests remain present.
  Coverage includes all changed commercial fields, normalization, unchanged stock,
  wallet/ledger/order/intent/claim state on rejection, failed/unknown outcomes,
  settled recovery, legacy evidence and ORM/bulk fingerprint immutability.
  Concurrent conflicting merchandise and gift retries each created one intent and
  one mocked provider order. No deadlock was observed in these runs.
- Migration 0027 -> 0028 -> 0027 -> 0028 preserved existing commerce records and
  restored fingerprint immutability. Existing 0025–0027 files were byte-compared
  against the previous exported patch and are unchanged.
- `CI=true npm --prefix frontend test -- --watchAll=false --runInBand`:
  **69 passed, 0 failed, 21 suites passed**, 9.229 seconds; all 66 previous tests
  retained. Three additions cover checkout/gift conflict messaging and retained
  keys, plus settled gift recovery without a new gateway checkout.
- `npm run build` in `frontend`: compiled successfully.
- `ecomenv/bin/python manage.py check`: no issues.
- `ecomenv/bin/python manage.py makemigrations --check --dry-run`: no changes detected.
- `ecomenv/bin/python manage.py check --deploy`: five expected local-profile
  warnings, security.W004/W008/W012/W016/W018; not production deployment approval.

The legacy merchandise recovery limitation above is intentional fail-closed
behavior, not an inferred backfill. No production or live provider access occurred.
Real-browser payment behavior remains unverified; React behavior was exercised
with mocked checkout and API responses. Existing reconciliation/operational limits
continue to apply.
