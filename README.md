# EazyShop Enterprise Ecommerce Platform

A production-grade, full-stack multi-vendor ecommerce ecosystem engineered with **Django REST Framework** on the backend and **React.js** on the frontend. EazyShop combines enterprise-grade financial workflows (Razorpay, Digital Wallets, and Gift Cards) with strict ACID transactional safety, pessimistic inventory row-locking, and responsive UI/UX.

---

## 🌐 Live Deployments

- **Official Domain:** [https://eazyshop.cfd](https://eazyshop.cfd)
- **Primary Vercel Mirror:** [https://eazyshop-store.vercel.app](https://eazyshop-store.vercel.app)
- **Legacy Demo:** [https://django-react-ecommerce-platform.vercel.app](https://django-react-ecommerce-platform.vercel.app)

---

## 🚀 What's New in v1.8.0

EazyShop **v1.8.0** delivers a major upgrade introducing a unified financial engine, live payment processing, and cross-tab state synchronization:

1. **Razorpay Payment Gateway Integration**:
   - Complete checkout processing supporting UPI, Credit/Debit cards, Net Banking, and Wallets via the Razorpay Web SDK.
   - Cryptographic HMAC-SHA256 signature verification (`verify-razorpay-payment`) preventing payment tampering.
   - Dedicated webhook listener (`/api/webhooks/razorpay/`) with automated order revival upon asynchronous capture.

2. **Unified Digital Wallet & Split Checkout**:
   - Built-in user wallet balance (`wallet_balance`) with instant balance debiting and top-up capabilities.
   - Flexible split checkout: pay orders entirely via wallet balance or combine wallet funds with Razorpay for the difference.

3. **Digital Gift Cards Engine**:
   - Purchase and generate digital gift cards directly through Razorpay.
   - Atomic gift card redemption with database row locks preventing double-spend and race conditions.
   - Unique UUID card identifiers, balance checking endpoint, and transaction auditing log.

4. **Real-Time Cross-Tab State Synchronization**:
   - Integrated browser `BroadcastChannel` protocol (`eazyshop_wallet_sync`) that automatically synchronizes wallet balances and auth state across multiple browser tabs without requiring a page reload.
   - Fresh profile hydration on mount (`refreshUser`) to eliminate stale cached balances on edge-hosted frontends (Vercel).

5. **Dynamic PDF Tax Invoices**:
   - ReportLab-powered PDF invoice generator with glassmorphism aesthetics and company branding.
   - Custom INR currency formatter avoiding standard font glyph errors (`Rs. XX,XXX.XX`).
   - Payment method badges, unique transaction IDs, and customer shipping breakdown.

6. **Server Wake-Up Overlay**:
   - Graceful cold-start detection for free-tier or containerized cloud backends (Render / Koyeb / Railway).
   - Animated modal displaying rotating initialization statuses while pinging the backend until warm.

7. **Expanded Titanium Test Suite**:
   - Test suite extended from 50 to **68 tests** (100% passing) covering concurrency, IDOR protections, split payments, webhook handling, and gift card race conditions.

8. **Domain Expansion**:
   - Allowed hosts, CORS, and CSRF support for the custom production domain `eazyshop.cfd` and `*.eazyshop.cfd`.

---

## 📦 Key Architectural Features

### 🛒 Multi-Vendor Marketplace (90/10 Split)
- **Automated Revenue Allocation:** The platform takes an automated 10% fee while seller accounts receive 90% of item sales.
- **Vendor Fulfillment Dashboard:** Vendors manage sales, update item status (`pending`, `shipped`, `delivered`), and track revenue.
- **Product Approval Pipeline:** Seller-submitted products enter a `pending` state until verified by platform administrators.

### 🔒 Enterprise Security & Authentication
- **HTTP-Only JWT Cookies:** Refresh and access tokens stored in `SameSite=None`, `Secure` cookies, mitigating XSS attack surfaces.
- **Silent Refresh Queue:** Interceptor in Axios handles simultaneous expired requests seamlessly without dropping user actions.
- **IDOR Protection:** Strict query filtering prevents unauthorized users from inspecting or modifying foreign orders, gift cards, or addresses.
- **OTP-Based Account Recovery:** Two-factor password reset using secure 6-digit one-time passcodes and timed expiration.

### ⚡ Inventory & Order Lifecycle Management
- **Pessimistic Row-Locking:** Uses `select_for_update()` during order placement to eliminate race conditions and overselling.
- **Self-Healing Order Cancellation:** Customers can cancel unfulfilled orders, triggering automated stock restorations and item status updates.
- **Address & Phone Integrity:** Strict validation requiring confirmed delivery address and contact numbers prior to checkout initiation.

---

## 🛠 Tech Stack

### Backend
- **Framework:** Django 5.2 & Django REST Framework 3.16
- **Database:** PostgreSQL (Neon Serverless) / SQLite (Development)
- **Authentication:** `djangorestframework-simplejwt` (HTTP-Only Cookies)
- **Payment Gateway:** Razorpay SDK 2.0.1
- **Media Storage:** Cloudinary (`django-cloudinary-storage`)
- **Email Service:** Anymail (Brevo / Sendinblue v3 API)
- **PDF Invoicing:** ReportLab 5.0.0
- **Static Files:** WhiteNoise 6.9.0
- **Testing:** Django TestCase & Unittest (68 tests)

### Frontend
- **Framework:** React 19 & React DOM 19
- **Routing:** React Router DOM v6
- **State & Context:** React Context API with `BroadcastChannel`
- **Styling:** Styled Components (CSS-in-JS)
- **Motion & UI:** Framer Motion 12
- **Networking:** Axios 1.8 with automatic 401 retry queues
- **Icons:** React Icons & Heroicons
- **Notifications:** React Hot Toast
- **Payment UI:** Razorpay Web SDK

---

## 📂 Project Structure

```text
EazyShop/
├── api/                           # Django REST Framework backend application
│   ├── management/commands/       # Custom management commands (image migrations, etc.)
│   ├── migrations/                # Database migration history (0001 to 0016)
│   ├── utils/                     # Helper modules (PDF generator, currency formatters)
│   ├── admin.py                   # Django admin dashboard registrations
│   ├── authenticate.py            # Cookie-based JWT authentication class
│   ├── backends.py                # Case-insensitive email authentication backend
│   ├── email_service.py           # Brevo transactional email dispatchers
│   ├── models.py                  # Domain models (User, Product, Order, GiftCard, Wallet)
│   ├── permissions.py             # Custom role-based DRF permissions
│   ├── serializers.py             # Model and hyperlinked DRF serializers
│   ├── tests.py                   # 68-test comprehensive integration test suite
│   ├── urls.py                    # API route definitions
│   └── views.py                   # ViewSets, Razorpay actions, and webhook controllers
├── ecommerce_platform/            # Django project core configuration
│   ├── asgi.py                    # ASGI entrypoint
│   ├── settings.py                # Unified Django settings (CORS, CSRF, JWT, DB)
│   ├── urls.py                    # Root URL router
│   └── wsgi.py                    # WSGI entrypoint
├── frontend/                      # React single-page application
│   ├── public/                    # Manifest, favicon, and HTML template
│   └── src/
│       ├── assets/                # Images and static design assets
│       ├── components/            # Reusable components (Navbar, ModalPortal, ServerWakeup)
│       ├── context/               # AuthContext with cross-tab wallet sync
│       ├── pages/                 # Route views (Home, Cart, Checkout, GiftCards, Dashboard)
│       ├── sections/              # Modular dashboard & vendor views
│       ├── styles/                # Global and animation styles
│       └── utils/                 # Client utilities (Axios instance, currency formatting)
├── .env.example                   # Environment variable template with documentation
├── build.sh                       # Production deployment script for Render
├── manage.py                      # Django CLI utility
├── package.json                   # Root package descriptor
└── requirements.txt               # Locked backend Python dependencies
```

---

## 🚀 Getting Started

### Prerequisites
- **Python:** 3.12 or newer
- **Node.js:** 18.x or newer & npm
- **Database:** PostgreSQL or SQLite

---

### Backend Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Vittal-17/EazyShop.git
   cd EazyShop
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv ecomenv
   source ecomenv/bin/activate  # On Windows: ecomenv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your PostgreSQL, Razorpay, Cloudinary, and Brevo credentials
   ```

5. **Run database migrations:**
   ```bash
   python manage.py migrate
   ```

6. **Start the development server:**
   ```bash
   python manage.py runserver
   ```
   Backend will be available at `http://127.0.0.1:8000/`.

---

### Frontend Setup

1. **Navigate to the frontend directory:**
   ```bash
   cd frontend
   ```

2. **Install frontend dependencies:**
   ```bash
   npm install
   ```

3. **Start the React dev server:**
   ```bash
   npm start
   ```
   Frontend will run at `http://localhost:3000/`.

---

## 🧪 Running the Test Suite

EazyShop includes the **Titanium Test Suite** with 68 comprehensive unit and integration tests covering security, role isolation, inventory atomicity, Razorpay webhooks, and gift card race conditions.

```bash
# Run the complete test suite
python manage.py test

# Run tests with verbose output
python manage.py test -v 2
```

To run frontend component tests:
```bash
cd frontend
npm test -- --watchAll=false
```

---

## 🔐 Environment Variables Reference

See [`.env.example`](./.env.example) for a complete template. Key variables:

| Variable | Description | Example / Default |
| :--- | :--- | :--- |
| `SECRET_KEY` | Django cryptographic signing key | Strong random string |
| `DEBUG` | Enable/disable debug mode | `True` in dev, `False` in prod |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@host/db` |
| `FRONTEND_URL` | Origin for transactional email links | `https://eazyshop.cfd` |
| `RAZORPAY_KEY_ID` | Razorpay public key identifier | `rzp_test_...` |
| `RAZORPAY_KEY_SECRET` | Razorpay secret API key | Secret key string |
| `RAZORPAY_WEBHOOK_SECRET` | Signature verification for webhooks | Webhook secret string |
| `CLOUDINARY_URL` | Cloudinary asset storage URI | `cloudinary://key:secret@cloud` |
| `BREVO_API_KEY` | Brevo (Sendinblue) transactional key | `xkeysib-...` |
| `DEFAULT_FROM_EMAIL` | Sender address for emails | `updates.eazyshop@gmail.com` |
| `REACT_APP_API_URL` | Frontend API destination | `http://127.0.0.1:8000` |

---

## 📜 Version History

- **v1.8.0** *(Current)* — Live Razorpay gateway integration, unified user wallet with split payments, digital gift card engine with instant atomic redemption, cross-tab `BroadcastChannel` synchronization, 68-test Titanium suite, PDF tax invoice generator, and custom domain `eazyshop.cfd`.
- **v1.7.0** — Enterprise security hardening, HTTP-Only SameSite=None cookie JWT auth, Cloudinary image migration, Brevo OTP account recovery, and Neon DB connection pooling.
- **v1.6.0** — Multi-vendor marketplace rollout, automated 90/10 platform commission split, vendor order fulfillment dashboard, and seller revenue analytics.
- **v1.5.0** — Customer reviews, product ratings, admin audit logging, and coupon engine.
- **v1.4.0** — User profile management, address book with default toggling, and customer wishlist.
- **v1.3.0** — Order tracking dashboard, pending order cancellation with inventory restoration.
- **v1.2.0** — Mobile-first responsive redesign with Framer Motion and Styled Components.
- **v1.1.0** — Pessimistic inventory locking and cart uniqueness constraints.
- **v1.0.0** — Initial release with Django REST Framework and React baseline.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
