# Local PostgreSQL 18

Only PostgreSQL runs in Docker. Django, React and `ecomenv` remain native. The
Compose project is `eazyshop-local`, with a dedicated `postgres_data` named volume.
The official image is pinned to PostgreSQL 18.6/bookworm and a registry digest.
PostgreSQL 18 stores PGDATA at `/var/lib/postgresql/18/docker`; the volume mounts
at `/var/lib/postgresql`, **not** the old `/var/lib/postgresql/data` location.
[Official image documentation](https://hub.docker.com/_/postgres).

## First setup and daily use

Inspect existing ports/services before setup. Defaults use localhost port 5433;
this workstation uses **5434**, because unrelated services already occupy 5432 and
5433. Do not stop those services or reuse their volumes.

```bash
source ecomenv/bin/activate
python scripts/setup_local_db.py --port 5434
docker compose --env-file .env.postgres config --quiet
docker compose --env-file .env.postgres up -d --wait
python manage.py migrate --noinput
python manage.py check
python manage.py runserver 127.0.0.1:8002
```

Port 8000 is also occupied on this workstation. React can run natively with
`REACT_APP_API_URL=http://127.0.0.1:8002 npm start` from `frontend` when the browser
also uses `127.0.0.1`. For `localhost`, use that hostname consistently instead.
See [the cookie-auth contract](browser-auth.md) for origin settings.

Setup generates three ignored mode-0600 files without printing credentials:

- `.env.postgres`: bootstrap credentials, independent dev/test passwords, host port.
- `.env.local`: dev DATABASE_URL, generated Django secret and placeholder providers.
- `.env.test`: separate TEST_DATABASE_URL and isolated test settings.

Tracked `.env.*.example` files contain placeholders only. Setup refuses to overwrite
existing credentials; rerunning daily requires only `up -d --wait`. Do not change
password files and expect an existing volume to reinitialize. Rotate database role
passwords deliberately and update the matching files together. Never print expanded
Compose configuration or connection URLs in shared logs.

## Fail-closed environment selection

Ordinary commands and WSGI/ASGI startup default to `EAZYSHOP_RUNTIME=local`.
They require `.env.local` with non-empty SECRET_KEY and DATABASE_URL entries.
The file's URL and any process DATABASE_URL override must both identify only the
isolated `eazyshop_dev` login/database on literal loopback. A missing, incomplete,
invalid or remote local profile raises an error before any database connection.
Legacy `.env` is never discovered or used as a fallback. EAZYSHOP_ENV_FILE alone
is rejected in local mode; environment variables cannot conceal a missing profile.

Production requires **EAZYSHOP_RUNTIME=production in the process environment**.
Putting that selector inside a dotenv file does not opt in. Configure it deliberately
on the deployment service and on its migration/release command:

```bash
# Deployment supplies DATABASE_URL, SECRET_KEY, provider settings and DEBUG=False
# through its secret/environment configuration. No dotenv file is read by default.
EAZYSHOP_RUNTIME=production gunicorn ecommerce_platform.wsgi:application
# Alternatively, explicitly select a protected production file:
EAZYSHOP_RUNTIME=production EAZYSHOP_ENV_FILE=/absolute/path/to/production.env \
  gunicorn ecommerce_platform.wsgi:application
```

For a reviewed file-based deployment, `.env` can still be selected explicitly with
both `EAZYSHOP_RUNTIME=production` and `EAZYSHOP_ENV_FILE=.env`. Relative paths are
resolved against the repository root. An explicitly selected missing file is an
error. Process values override the selected file, preserving platform-provided
DATABASE_URL and Neon's `sslmode=require`. Production has no implicit dotenv
fallback either. Set DEBUG=False and the established HTTPS, host and origin settings
in that deployment. Do not run these production commands on this workstation or
use real remote URLs to verify selection; regression tests use synthetic values.

Test commands always select `.env.test` (or explicit environment-only CI values),
ignore both production selectors and DATABASE_URL, and validate TEST_DATABASE_URL
against the isolated `eazyshop_test` identity. There is no SQLite fallback in any
mode. Local connections time out in five seconds when the service is unavailable.

## Local sandbox integrations

The setup helper creates placeholder integration values only on initial setup and
refuses to overwrite existing files. This review does not regenerate or replace
user-managed credentials. Keep the generated local DATABASE_URL and signing key;
edit the ignored `.env.local` deliberately to enable development integrations:

- Set RAZORPAY_KEY_ID to your provider-issued **test-mode** key (`rzp_test_...`),
  with its matching test secret and a separate sandbox webhook secret. Never copy
  live payment credentials or the whole legacy `.env` into the local profile.
- Set FRONTEND_URL, CORS_ALLOWED_ORIGINS and CSRF_TRUSTED_ORIGINS to the exact local
  frontend origins, using consistent loopback hostnames. Follow the cookie-auth
  contract for any deliberate HTTPS sandbox deployment. Do not broaden origins
  to wildcards or weaken production cookie settings.
- Configure a dedicated development Cloudinary account and test email/Brevo sender
  when needed. Configure REDIS_URL only for a deliberately isolated development
  cache. Do not reuse production media, email, cache or database services.
- Process-level integration settings intentionally override `.env.local` values.
  Check the launch environment if a sandbox value appears ineffective; never
  print secret values to diagnose precedence. A remote process DATABASE_URL
  remains rejected in local mode.

Unconfigured placeholders do not provide working gateway/email/media integrations.
Automated tests continue to use mocks and isolated settings; sandbox connectivity
is a separate manual check and was not exercised during this review. Credentials
remain in ignored private files or process environments, never tracked examples.

## Database privileges and automated tests

`eazyshop_dev` owns only `eazyshop_dev`; `eazyshop_test` owns only `eazyshop_test`.
Neither is a superuser or has CREATEDB, CREATEROLE, replication or RLS-bypass rights.
PUBLIC has no connection rights on either database. Each login cannot connect to
the other's database. The test login can connect to the empty `postgres`
maintenance database solely for Django's database-existence inspection; it has no
schema creation privileges there. Bootstrap credentials are never used by Django.

The initializer creates both databases once. Tests use the already-created test
database with forced `keepdb`; they do not create or drop databases. Standard Django
transaction rollback/flush isolates test cases. A startup flush, under the exclusive
run lock, clears leftovers from interrupted runs before fixtures load. Treat this database as disposable
and never put development records in it. A session advisory lock rejects overlapping
suite invocations. `--parallel` process pools are rejected; dedicated concurrency
tests still run real threads, transactions and independent PostgreSQL connections.
The test role has 10-second lock and 60-second statement timeouts.

```bash
python manage.py test api --noinput -v 2
python manage.py test api.test_postgresql api.test_fulfillment.FulfillmentLockTests --noinput -v 2
python manage.py test api.test_cookie_auth api.test_payment_privacy api.test_fulfillment api.tests.UserPrivilegeRegressionTests --noinput -v 2
python manage.py check
DEBUG=False python manage.py check --deploy
python manage.py makemigrations --check --dry-run
# In frontend:
CI=true npm test -- --watchAll=false --runInBand
```

Tests select `.env.test` regardless of EAZYSHOP_RUNTIME/EAZYSHOP_ENV_FILE, ignore DATABASE_URL, and
validate TEST_DATABASE_URL before connecting. They use local-memory email, cache
and storage, placeholder provider keys, and reject external DNS/socket connections.
Provider interactions must be mocked. CI can generate the ignored files with the
same setup command, launch this Compose service and run the same tests. Do not
reuse a production test database or grant CREATEDB to make tests pass.

The two former stock tests used TestCase transactions invisible to worker
connections, shared one client, patched thread startup, and called `executor.map`
without an iterable. They now live in `api.test_postgresql` as TransactionTestCase
cases. The last-unit test runs 100 distinct buyers across 20 concurrent workers;
the two-unit test starts two buyers together. Both assert backend connection IDs,
exact response counts, inventory, order count and a single mocked gateway order.
The existing duplicate-shipment test remains in `api.test_fulfillment`.

## Stop, restart and persistence

```bash
docker compose --env-file .env.postgres stop
docker compose --env-file .env.postgres start --wait
docker compose --env-file .env.postgres restart postgres
docker compose --env-file .env.postgres up -d --wait
```

`down` removes the Compose container/network but preserves the named volume.
**Never use `down -v`, volume removal, or system prune with volumes** for normal
shutdown or rollback. A restart policy of `unless-stopped` and a TCP readiness
healthcheck are configured. Healthcheck readiness is not a backup guarantee.

## PostgreSQL backups and restores

Backups contain PII and password hashes. Keep `.local/backups` private, outside Git,
and copy important archives to protected durable storage. Do not store credentials
in shell history or command-line connection URLs.

```bash
umask 077
mkdir -p .local/backups
docker compose --env-file .env.postgres exec -T postgres \
  pg_dump -U eazyshop_dev -d eazyshop_dev -Fc > .local/backups/development.dump
docker compose --env-file .env.postgres exec -T postgres \
  pg_restore --list < .local/backups/development.dump
```

For a restore drill, use a **new, explicitly named database in this local cluster**,
not production, the active dev database or an unrelated database. CREATE must
succeed; stop if the destination already exists. These commands do not overwrite
an existing database:

```bash
docker compose --env-file .env.postgres exec -T postgres psql -v ON_ERROR_STOP=1 \
  -U eazyshop_bootstrap -d postgres -c 'CREATE DATABASE eazyshop_restore_check OWNER eazyshop_dev'
docker compose --env-file .env.postgres exec -T postgres psql -v ON_ERROR_STOP=1 \
  -U eazyshop_bootstrap -d postgres -c 'REVOKE ALL ON DATABASE eazyshop_restore_check FROM PUBLIC'
docker compose --env-file .env.postgres exec -T postgres pg_restore \
  -U eazyshop_dev -d eazyshop_restore_check --no-owner --no-acl --exit-on-error \
  < .local/backups/development.dump
docker compose --env-file .env.postgres exec -T postgres psql \
  -U eazyshop_dev -d eazyshop_restore_check -c 'SELECT count(*) FROM django_migrations'
# Only after verification, remove the temporary database created above:
docker compose --env-file .env.postgres exec -T postgres psql -v ON_ERROR_STOP=1 \
  -U eazyshop_bootstrap -d postgres -c 'DROP DATABASE eazyshop_restore_check'
```

Verify record counts and migration fingerprints before adopting a restore.
Restoring over an existing database requires a new backup and explicit review;
do not use `--clean` on a populated database. Bootstrap is only for deliberate
local administration. Preserve credential files securely for disaster recovery;
data dumps do not contain login passwords. Use a fresh timestamped backup filename
instead of overwriting a previous archive.

## Legacy SQLite preservation and optional import

The original `db.sqlite3` is never deleted or migrated in place. Setup uses SQLite's
backup API (including committed WAL content), checks integrity, and stores a
mode-0600 timestamped backup plus a printed SHA256 under `.local/backups`.
Discovery found one customer, three orders, one payment, one gift card, two gift-card
transactions, one address, four carts, one product and two administrative log rows.
The old database has API migrations through 0022. These are potentially valuable
records; **no automatic data import was performed**.

An optional import should be a separately reviewed operation:

1. Stop SQLite writers, keep the original and verified backup, and create a second
   private SQLite working copy using SQLite's backup API. Never use the original as
   the working copy. Record per-table counts and financial totals privately.
2. In a one-off offline export script, initialize Django settings, override
   `settings.DATABASES` **before `django.setup()`** with the SQLite working-copy
   path, and use local-memory email/cache/storage. Run existing migrations on that
   copy only. This explicit offline export override is not a supported application
   backend or a fallback in settings.
3. Use Django `dumpdata api auth.group --natural-foreign --indent 2` into an ignored,
   mode-0600 fixture. Do not export content types, generated auth permissions,
   sessions or JWT blacklist rows. Inspect foreign-key relations, user groups,
   decimals, constraints and file references. Media files are separate from DB data.
4. First trial `loaddata` in a separately created empty local import database, under
   a one-off reviewed settings override. Migrate that database before loading.
   Never import into the dedicated automated-test database. Keep the normal local
   database guards intact.
5. Validate counts, ownership, snapshots, stock, wallet totals and payment evidence.
   Migrations 0023/0024 remain unchanged; legacy payment rows do **not** acquire
   trusted `verified_at` evidence merely by import. Do not invent gateway IDs or
   mark historical orders settled to bypass Mission 002 safeguards. Reconcile
   those records separately before any fulfillment.
6. Only after successful reconciliation, back up the destination and approve a
   deliberate import into an empty development database. Do not mix fixture IDs
   into an already populated database. Keep SQLite and all backups until reviewed.

## Rollback

Stop the EazyShop Compose service without removing its volume. Preserve all three
local environment files and the SQLite backup. Do not repoint this application's
normal settings at SQLite; that is intentionally rejected. A separately reviewed
code rollback can use the original SQLite data in its original compatible code
version. To return to an approved production configuration, explicitly set
EAZYSHOP_RUNTIME=production and select its environment variables or protected file
through the deployment process; this
local setup never connects to or changes Neon. Restore PostgreSQL archives only
into reviewed local destinations as described above.

## Mission 004 verification (2026-11-07, Asia/Kolkata)

- Server: PostgreSQL 18.6 (Debian 18.6-1.pgdg12+2), x86_64; Django reports
  `postgresql`, `current_database=eazyshop_dev`, `current_user=eazyshop_dev`.
- Actual host binding: `127.0.0.1:5434`. PGDATA: `/var/lib/postgresql/18/docker`.
- `python manage.py migrate --noinput`: all 57 existing migrations applied, including
  API 0023 and 0024. No migration files changed.
- `python manage.py test api --noinput -v 2`: **188 passed, 0 failed, 0 skipped**.
- `python manage.py test api.test_postgresql api.test_fulfillment.FulfillmentLockTests
  --noinput -v 2`: **5 passed, 0 skipped**, including all three formerly skipped
  concurrency tests and two configuration tests.
- `CI=true npm test -- --watchAll=false --runInBand` in `frontend`: **56 passed**
  across 19 suites. No frontend implementation changes.
- Compose configuration, Django check/deployment check, migration consistency,
  Ruff undefined-name checks and patch whitespace checks passed.
- Both local logins authenticated correctly, rejected bad passwords and were denied
  connections to the other database. No administrative role flags were granted.
- A second suite invocation was rejected before setup/flush while the first held
  the advisory lock. Test provider networking remained disabled.
- Dev database was dumped and restored into a newly created temporary local DB;
  the 57-row migration fingerprint matched. The temporary restore DB was removed.
  The real development database survived restart with the same fingerprint.
- Stopping only this service caused a PostgreSQL OperationalError, with no SQLite
  fallback; the service was then restarted and checked again.
- Original SQLite and its backup have identical schema/records. SQLite and
  PostgreSQL backups remain private under `.local/backups`. No legacy rows were
  imported into development, and no production or unrelated database was accessed.

An initial suite attempt exposed a test-only override dropping Anymail's existing
request timeout; the override was corrected to preserve it. No deadlocks or
business-logic failures occurred in the final runs. Existing PDF worker tests log
missing uncommitted fixture products without failing assertions; this task did
not change that application path. Passing these scenarios is not a general
proof of financial/concurrency correctness or production readiness.

### Mission 004 review fix — environment selection

Before the fix, two synthetic settings tests reproduced successful selection of a
remote database when `.env.local` was absent: once through a legacy `.env`, and
once through process DATABASE_URL. No connection was opened. Both paths now raise
ImproperlyConfigured; explicit production selection and Neon SSL parsing still work.

- `ecomenv/bin/python -m unittest api.test_environment -v`: **13 passed**, with
  temporary synthetic files and database/network connections forbidden.
- `ecomenv/bin/python manage.py test api --noinput -v 2`: **201 passed, 0 failed,
  0 skipped** on the isolated PostgreSQL database, including all three concurrency
  tests and Mission 001–003 coverage.
- `CI=true npm test -- --watchAll=false --runInBand` in `frontend`: **56 passed**
  across 19 suites.
- Django check, `DEBUG=False` deployment check, migration consistency, relevant
  Ruff checks and patch whitespace checks passed. No migration changes.

No existing local/sandbox credential files were regenerated or edited. No production
configuration file or database was accessed during review verification. Production
operators must set the process-level opt-in before rollout; verification of real
remote infrastructure and sandbox integrations remains outside this change.
