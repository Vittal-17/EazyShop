# Browser cookie authentication

React uses one credentialed Axios client in `frontend/src/utils/axios.js`. It gets
`GET /api/csrf/` before unsafe requests, retains the masked `csrfToken` in memory,
and sends `X-CSRFToken`. JavaScript never needs to read an API-domain cookie.
Bootstrap and successful credential responses use `Cache-Control: no-store`.
Do not cache these routes in a CDN or reverse proxy.

`POST /api/token/`, `/api/token/refresh/` and `/api/logout/` require Django's CSRF
and Origin/HTTPS Referer validation, including when anonymous or access has
expired. Login rotates CSRF and returns the new masked token. JWTs are returned
only in host-only HttpOnly cookies with path `/`; their expiration matches
SimpleJWT's configured lifetimes (10 minutes / 7 days). Refresh rotates and
blacklists the previous refresh token. Logout blacklists refresh and clears both
cookies; revocation infrastructure failures return 503 rather than success.
Already-issued access tokens remain valid until their short expiration.

Explicit bearer authentication remains supported for non-browser clients.
An ambient access cookie still requires CSRF even if a bearer header is present.
The browser has no bearer fallback or JWT local/session-storage contract.
Public registration and OTP recovery ignore expired ambient sessions and retain
their existing credential/OTP validation. Signed Razorpay webhooks retain their
separate signature authentication.

## Deployment prerequisites

Set `REACT_APP_API_URL` to the API origin before building React. CORS allowed
origins and CSRF trusted origins must list the exact frontend origins, with no
wildcards. Production requires HTTPS and `DEBUG=False`. The proxy must strip
untrusted forwarded headers before setting the trusted HTTPS proxy header.

| Topology | Cookie policy | Requirements |
| --- | --- | --- |
| Same HTTPS origin | `AUTH_COOKIE_SAMESITE=Lax` (default) | API at the configured origin |
| HTTPS sibling subdomains | `Lax` | Exact frontend CORS and CSRF origin, credentials enabled |
| Different HTTPS sites, e.g. Vercel to Render | `AUTH_COOKIE_SAMESITE=None` | Exact frontend CORS and CSRF origin; browser must permit third-party cookies |
| Local HTTP | `DEBUG=True`, `Lax` | Use the same loopback hostname for frontend and API; local origins are trusted in debug only |

One policy configures JWT, CSRF and Django session cookies. `None` always requires
Secure; production always requires Secure. Previous independent
`CSRF_COOKIE_SAMESITE`, `CSRF_COOKIE_SECURE`, `SESSION_COOKIE_SAMESITE` and
`SESSION_COOKIE_SECURE` environment overrides no longer control these cookies.
Cookies remain host-only; do not introduce a parent-domain cookie override.
When changing deployments, clear obsolete cookies if their Domain/Path differed.

Cross-site cookie restrictions in browsers cannot be bypassed by CORS or a CSRF
header. Prefer same-site domains when third-party cookies are blocked. Do not
restore JavaScript-accessible JWTs as a workaround. Deploy frontend and backend
together; old clients without CSRF bootstrap will receive 403 on login/refresh.

The client shares a refresh promise within the page, retries each failed request
at most once, and recognizes late 401s from the previous credential generation.
CSRF rotation in another tab gets one bootstrap/retry only after a server CSRF
rejection. Network failures reject all waiters without pretending logout succeeded.
Separate tabs can still race refresh rotation; reauthentication may be needed.
Login verifies cookie acceptance with a profile request before reporting success.

## Payment verification

Both order-router mounts verify ownership before any payment query, replay or
provider call. Verification remains an owner operation. Administrative payment
visibility follows the existing order-view authorization policy. Replays match
the order's persisted gateway ID, exact transaction ID, verified completed payment
and full settlement evidence; cached success payloads are no longer authoritative.
Cancelled/refunded or unrelated payments cannot replay success. No payment schema
or settlement algorithm changes are required for this remediation.

## Regression tests

Run `python manage.py test api.test_cookie_auth api.test_payment_privacy
api.test_fulfillment api.tests.UserPrivilegeRegressionTests --noinput` with isolated
test database/cache/email settings and mock provider credentials. Then run the full
`python manage.py test api --noinput`, Django system/migration checks, and
`CI=true npm test -- --watchAll=false --runInBand` plus `CI=true npm run build` in
`frontend`. Never point verification settings at production services.

Browser verification for this change exercised the real Axios client against a
disposable Django server in four clean Chromium profiles: local HTTP, same-origin
HTTPS, sibling HTTPS subdomains and different HTTPS sites. Each covered login,
HttpOnly cookie isolation, POST/PATCH/DELETE, concurrent expired-access recovery,
and logout (32 assertions). HTTPS used local fixture certificates, so this does
not validate deployed TLS/proxy configuration. Firefox, Safari and policies that
block third-party cookies still require deployment verification.

Django's masked-token/header and Origin validation guidance is documented at
https://docs.djangoproject.com/en/5.2/howto/csrf/ .
