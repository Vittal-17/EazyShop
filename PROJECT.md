# Project: EazyShop Enterprise Production Audit

## Architecture
- **Backend**: Django / Django REST Framework (`api/`, `ecommerce_platform/`)
- **Frontend**: React SPA (`frontend/`)
- **Database**: Relational models in Django ORM (`api/models.py`)
- **Payment & External Services**: Razorpay gateway, Brevo email API

## Feature Inventory
| # | Feature / Area | Description | Milestone | Source |
|---|----------------|-------------|-----------|--------|
| 1 | Financial & Payment Integrity | Razorpay flow, double-spend, amount tampering, wallet balance, state machine, inventory races | M1 | ORIGINAL_REQUEST §R1 |
| 2 | High-Concurrency & Scalability | DB locking, SQLite vs Postgres, connection starvation, sync blocking (Brevo/Razorpay), caching | M2 | ORIGINAL_REQUEST §R2 |
| 3 | Security, Auth & RBAC | Dual-mode auth, JWT lifecycle, cookies, CORS, CSRF, Customer/Vendor/Admin RBAC, IDOR | M3 | ORIGINAL_REQUEST §R3 |
| 4 | Frontend Reliability & UX | Error boundaries, network recovery, cart/checkout state races, localStorage sync, bundle/perf | M4 | ORIGINAL_REQUEST §R4 |
| 5 | Deliverable Synthesis & Review | AUDIT_REPORT.md synthesis (Executive summary, P0-P3, failure scenarios, snippets, 30-60-90 plan) | M5 | ORIGINAL_REQUEST §R5 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Financial & Payment Integrity Audit | Deep audit of Razorpay, wallet, orders, inventory locking | none | DONE |
| M2 | High-Concurrency & Scalability Audit | Database concurrency, blocking operations, caching, pooling | none | DONE |
| M3 | Security, Authentication & RBAC Audit | Auth modes, tokens, headers, RBAC matrix, IDOR vulnerabilities | none | DONE |
| M4 | Frontend Reliability & UX Audit | React error boundaries, checkout races, localStorage, performance | none | DONE |
| M5 | Audit Synthesis & Reporting | Comprehensive AUDIT_REPORT.md generation and review verification | M1, M2, M3, M4 | IN_PROGRESS |

## Code Layout
- Root: `/home/vittal/Projects/EazyShop`
- Agent metadata: `/home/vittal/Projects/EazyShop/.agents/`
- Backend: `/home/vittal/Projects/EazyShop/api`, `/home/vittal/Projects/EazyShop/ecommerce_platform`
- Deliverable: `/home/vittal/Projects/EazyShop/AUDIT_REPORT.md`
