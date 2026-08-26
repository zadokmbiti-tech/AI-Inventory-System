# SmartStock AI

Inventory intelligence for growing Kenyan SME retailers  stock tracking, sales
recording, VAT-aware invoicing, low-stock alerts, and AI-powered demand
forecasting, in one lightweight web app.

## Features

- **Dashboard**  revenue, VAT collected, gross profit, margin, and sales KPIs
  over a selectable period, plus a revenue-by-day chart and top products.
- **Products**  full CRUD with SKU, cost/selling price, stock unit, reorder
  point/quantity, and Kenya VAT tax category (Standard 16%, Reduced, Zero-rated,
  Exempt).
- **Record Sale**  build a multi-item sale, auto-calculates VAT and totals,
  supports cash / M-Pesa / credit payment methods, and prints a receipt.
- **Stock In / Adjustment**  log stock received, adjustments, and
  loss/spoilage against any product.
- **Records**  store receipts, invoices, and delivery notes with an attached
  PDF/image file per record.
- **Alerts**  automatic low-stock and out-of-stock alerts with urgency
  levels.
- **Forecast**  AI demand forecasting per product (Prophet-based) with a
  predicted-sales-by-week chart and an "Apply AI Reorder Suggestion" action.
- **Subscription / Licensing**  30-day license keys with renewal; API access
  is gated once a license expires.
- Light/dark theme, mobile-responsive layout with a collapsible sidebar.

## Tech Stack

- **Backend:** FastAPI (Python), SQLAlchemy, PostgreSQL, Alembic migrations
- **Forecasting:** Prophet, scikit-learn, pandas, numpy
- **Auth:** JWT (python-jose) + bcrypt password hashing
- **Email:** Resend (password reset links)
- **File storage:** Vercel Blob (document attachments)
- **Frontend:** Vanilla HTML/CSS/JavaScript + Chart.js (no build step, served
  directly by FastAPI via Jinja2 templates)

## Project Structure

```
AI-Inventory System/
├── main.py                  # FastAPI app entrypoint
├── app/
│   ├── config.py             # Settings (env-based)
│   ├── database.py           # SQLAlchemy engine/session
│   ├── models/                # ORM models
│   ├── schemas/                # Pydantic request/response schemas
│   ├── routers/                # /api/auth, /api/products, /api/stock, /api/ai, /api/documents, /api/license
│   ├── services/                # auth, email, license, file storage helpers
│   └── ml/                       # forecasting / reorder intelligence
├── frontend/
│   ├── templates/index.html   # single-page app shell
│   └── static/
│       ├── css/style.css       # theme + responsive layout
│       └── js/app.js            # all frontend logic (SPA-style page switching)
├── migrations/                # raw SQL migrations
├── run_local.sh                # one-shot local setup + run script
└── requirements.txt
```

## Getting Started (Local Development)

### Prerequisites

- Python 3.11+
- A PostgreSQL database (local or hosted, e.g. Neon/Supabase)

### Quick start

```bash
chmod +x run_local.sh
./run_local.sh
```

This script will:
1. Copy `.env.example` to `.env` if one doesn't exist yet.
2. Create a virtual environment (`venv/`).
3. Install dependencies from `requirements.txt`.
4. Start the server with `uvicorn main:app --reload` on `http://localhost:8000`.

Edit `.env` with your real values before (or after) the first run  at minimum
`DATABASE_URL` and `SECRET_KEY`.

### Manual setup

```bash
python3 -m venv venv
source venv/bin/activate        # venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env             # then fill in the values
uvicorn main:app --reload
```

### Environment variables

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `SECRET_KEY` | JWT signing secret |
| `ALGORITHM` | JWT algorithm (e.g. `HS256`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime |
| `DEBUG` | `True`/`False` |
| `RESEND_API_KEY` | API key for sending password-reset emails via Resend |
| `EMAIL_FROM` | From address for outgoing emails |
| `FRONTEND_BASE_URL` | Base URL used to build password-reset links, and the app's own origin (used for CORS + the auth cookie) |
| `CORS_ORIGINS` | Optional comma-separated extra browser origins allowed to call the API, beyond `FRONTEND_BASE_URL` |

Database tables are created automatically on startup (see `lifespan` in
`main.py`); use the SQL files in `migrations/` for incremental schema changes
on an existing database.

## Usage

Once running, open `http://localhost:8000` in a browser (desktop or mobile 
the UI is responsive), register a business account, and sign in. Interactive
API documentation is available at `http://localhost:8000/docs`.

## Security

- **Auth cookie, not localStorage.** Login sets an `httpOnly`, `SameSite=Lax`
  cookie holding the JWT; the frontend never stores the token in JS-readable
  storage, so it can't be stolen via an XSS bug. The token is also returned
  in the login response body for API clients and the `/docs` "Authorize"
  button.
- **`DEBUG` controls production hardening.** With `DEBUG=False`: `/docs`,
  `/redoc`, and `/openapi.json` are disabled, the auth cookie requires HTTPS
  (`secure=True`), and an HSTS header is sent. Set `DEBUG=False` before
  deploying publicly.
- **CORS is locked to an allow-list** built from `FRONTEND_BASE_URL` plus
  `CORS_ORIGINS`  never re-enable `allow_origins=["*"]`, since the app
  relies on cookies and a wildcard origin can't be combined with credentials.
- **Rate limiting** (via `slowapi`) throttles `/api/auth/login` (10/min),
  `/api/auth/register` (5/hour), `/api/auth/forgot-password` (5/hour), and
  `/api/auth/reset-password` (10/hour) per IP, to slow brute-force and
  account-enumeration attempts.
- **Password rules**: minimum 8 characters, at least one letter and one
  digit, enforced on both registration and password reset.
- **Document uploads are content-sniffed**, not just trusted by their
  declared `Content-Type`  the actual file bytes must match a real
  PDF/JPEG/PNG/WEBP signature before the file is accepted.
- **Security headers** (`X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, `Permissions-Policy`, and `Strict-Transport-Security`
  in production) are set on every response.
- Rotate `SECRET_KEY` and any other credentials in `.env` before making this
  repo public or deploying  the current values in your local `.env` should
  be treated as compromised if they were ever shared or committed.

## Notes

- License renewal on the Subscription page currently simulates a successful
  M-Pesa payment; wiring in the real M-Pesa Daraja STK Push callback is a
  planned next step.
- The forecasting endpoints require enough historical sales data per product
  to produce a meaningful prediction.
