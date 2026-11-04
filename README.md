# YatraLine — Bus Booking Backend + Frontend

FastAPI + SQLAlchemy + SQLite implementation of the architecture we sketched:
server-authoritative seat locking, OTP verification before payment, and a
payment flow that only confirms a booking once a signature is actually
verified (no more `setTimeout(...900)` fake confirmations).

## Run it

```bash
pip install -r requirements.txt
python seed.py              # creates yatraline.db and seeds demo buses/routes
uvicorn app.main:app --reload --port 8000
```

Then open **http://localhost:8000** — the frontend is served from the same
app, hitting its own `/api/...` routes.

## What's implemented

- **Auth/OTP** (`/api/auth`) — 6-digit OTP, hashed + salted at rest (never
  stored plaintext), 5-minute expiry, max attempts, resend cooldown.
- **Search** (`/api/buses/search`, `/api/buses/{id}/seats`) — live seat
  availability computed from the DB, not a static array.
- **Seat locking** (`/api/seats/hold`, `/api/seats/release`) — a seat moves
  `AVAILABLE -> HELD -> BOOKED`; holds expire after 10 minutes and are
  lazily reclaimed. This is what stops two people from buying the same seat.
- **Bookings** (`/api/bookings`) — created in `PENDING`, only advances to
  `AWAITING_PAYMENT` once `/confirm-otp` links a *verified* OTP session to
  the booking's user.
- **Payments** (`/api/payments`) — `create-order` + `verify` mirror
  Razorpay's order/payment/signature shape. Seats only flip to `BOOKED` and
  the booking to `CONFIRMED` after the HMAC signature checks out server-side.
  `/payments/webhook` is a stub for the gateway's server-to-server callback.
- **Admin** (`/api/admin`) — dashboard totals, booking list, audit log feed.
- **Audit logging** — OTP requests/verifications, booking creation, OTP
  confirmation, and payment outcomes are all logged to `AuditLog`.

## Important: getting real Razorpay working

The frontend loads Razorpay's actual `checkout.js` and opens the real payment
modal — but it needs your own **Razorpay test-mode key** to actually process
a payment:

1. Sign up at https://dashboard.razorpay.com (test mode needs no business
   verification) and copy your **Key ID** and **Key Secret** from
   Settings → API Keys.
2. Copy `.env.example` to `.env` and fill in your real values:
   ```bash
   cp .env.example .env
   # then edit .env with your actual Key ID / Key Secret
   ```
   `.env` is loaded automatically on startup (see `app/main.py`), so you
   don't need to `export` anything by hand each session. (If you'd rather
   set them as shell environment variables directly, that still works too —
   `.env` just means you don't have to repeat it every time.)
3. That's it — `/api/payments/create-order` will hand that key to the
   Razorpay checkout widget, and `/api/payments/verify` already implements
   the exact HMAC-SHA256(order_id + "|" + payment_id, key_secret) scheme
   Razorpay uses to sign real payments, so it verifies real transactions
   without any code changes.

Without real keys set, `RAZORPAY_KEY_ID`/`SECRET` default to placeholders and
`create-order` falls back to generating a local order ID instead of calling
Razorpay's Orders API. **The real Razorpay checkout widget will always show
"Payment Failed" immediately in this state** — before you even reach a card
field — because it validates the order ID against Razorpay's own servers,
and a locally-generated one isn't real. This is expected: it means you
haven't set up `.env` yet, not that something is broken. A
`POST /api/payments/_dev/sign-mock-payment` dev-only endpoint is included so
you can still exercise the full create-order → verify round trip via
curl/Postman without a live key — **delete it before deploying**, since a
real gateway's signature must come from the gateway, never from your own
backend.

## Frontend

`frontend/index.html` is your original YatraLine UI, unchanged in look and
feel (Bebas Neue/Inter/Space Mono, navy/amber theme, the same seat map and
ticket-stub layout) — the only additions are:
- an **OTP verification view** inserted between passenger details and
  payment (required by the booking state machine), and
- a **contact block** (name/email/phone) on the passenger-details step so
  there's somewhere to send the OTP.

Everything that used to be a hardcoded `BUSES` array or a `window.storage` /
`localStorage` call now hits the FastAPI backend instead — search, seat
maps, seat holds, bookings, payment, "My Bookings", and the Admin dashboard
(including a new **Audit Log** table) are all read from and written to
`yatraline.db`.

## Environment variables (set for production)

| Variable | Purpose |
|---|---|
| `OTP_PEPPER` | Salt mixed into OTP hashing |
| `OTP_DELIVERY_MODE` | `dev` (logs/returns OTP) or `production` (must wire a real SMS/email provider in `security.deliver_otp`) |
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` | Real gateway credentials |

## Next steps (in the order the plan called for)

1. ✅ Project structure, models, SQLite init, seed data
2. ✅ Full API surface + seat locking
3. ✅ OTP verification wired into the booking state machine
4. ✅ Payment verification (mocked signature scheme, same shape as Razorpay)
5. **Left for you:** swap the mock gateway for real Razorpay test-mode keys
   and `checkout.js`; add an admin-auth dependency before exposing `/api/admin`
   anywhere but localhost; wire a real SMS/email provider into
   `security.deliver_otp` for production OTP delivery.

## Project layout

```
yatraline/
├── app/
│   ├── main.py          # FastAPI app, router wiring, static frontend mount
│   ├── database.py      # SQLAlchemy engine/session
│   ├── models.py        # ORM models (User, Booking, SeatInventory, ...)
│   ├── schemas.py        # Pydantic request/response models
│   ├── security.py       # OTP hashing, HMAC signature verification
│   └── routers/
│       ├── auth.py       # /api/auth/*
│       ├── buses.py      # /api/buses/*
│       ├── seats.py      # /api/seats/*
│       ├── bookings.py   # /api/bookings/*
│       ├── payments.py   # /api/payments/*
│       └── admin.py      # /api/admin/*
├── frontend/index.html   # search -> seats -> passengers -> OTP -> payment -> ticket
├── seed.py               # demo buses/routes/seat inventory
└── requirements.txt
```
