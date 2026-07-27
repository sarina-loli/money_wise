# MoneyWise — Personal Money Management System (Complete)

Premium fintech-styled Django project — fully built out per the original spec.

## Feature set

- **Auth**: Register, Login, Logout, Forgot/Reset Password (Django's
  built-in password-reset flow with custom templates + console email
  backend for local testing)
- **Dashboard**: animated stat cards (balance, income, expenses, remaining
  budget), income-vs-expense trend chart, category breakdown doughnut,
  financial health score ring, budget overview, savings goals summary,
  recent transactions — all via Chart.js
- **Income** — full CRUD, categorized (Salary, Business, Freelance, Bonus,
  Gift, Investment, Rental, Other), search + filter + pagination
- **Expenses** — full CRUD with receipt upload, categorized (Food,
  Shopping, Transport, Education, Health, Entertainment, Utilities,
  Insurance, Travel, Investment, Other), search + filter + pagination
- **Transactions** — combined, filterable, paginated income + expense feed
- **Budgets** — monthly limit per category, animated progress bars,
  automatic in-app notifications at 80% (warning) and 100%+ (exceeded)
- **Savings Goals** — target vs. saved, deadline, "Add Funds" action,
  automatic goal-completion notification
- **Reports** — weekly/monthly/yearly views with trend + category charts,
  CSV export (opens in Excel/Sheets) and a print-to-PDF view
- **Notifications** — budget warnings/exceeded, goal completed, large
  spending alerts; mark as read / mark all as read
- **Calendar** — month grid showing daily income/expense totals
- **Profile & Settings** — avatar, name, email, currency, theme,
  notification preferences (all persisted via a `Profile` model)
- **Static pages** — About, Contact, Privacy Policy, Terms, Help Center, 404
- Landing page: hero, animated counters, features, how-it-works,
  testimonials, pricing, FAQ accordion, newsletter form
- Full design system in `static/css/style.css` (your color palette, CSS
  variables, shadows) + `static/js/main.js` (page loader, scroll reveal,
  counters, typing effect, ripple buttons, accordion, dark/light mode
  toggle, sidebar + quick-add menu, toast auto-dismiss) — vanilla JS only
- SQLite for development; PostgreSQL swap-in notes in `settings.py`

## Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt

python manage.py makemigrations
python manage.py migrate

python manage.py createsuperuser   # optional, for /admin/
python manage.py runserver
```

Visit **http://127.0.0.1:8000/** for the landing page,
**http://127.0.0.1:8000/app/dashboard/** once logged in, and
**http://127.0.0.1:8000/admin/** for the Django admin.

### Password reset in development

The email backend is the console backend — reset links print to the
terminal running `runserver`. Swap `EMAIL_BACKEND` in `settings.py` for
real SMTP in production.

### Exports

- **Export Excel** on the Reports page downloads a CSV (opens natively in
  Excel/Google Sheets — no extra binary dependencies required).
- **Export PDF** opens a clean, print-ready statement page; use the
  browser's "Print → Save as PDF" to generate a PDF file.

### Testing payments (PayPal Sandbox)

Payments for the Pro/Family plans go through PayPal (`billing/paypal.py`,
`billing/views.py`). To test the full checkout → capture → webhook flow
locally:

1. **Create sandbox credentials.**
   - Log in at https://developer.paypal.com/dashboard/ (a free developer
     account is enough — no real business account needed).
   - Under **Apps & Credentials**, make sure you're on the **Sandbox**
     tab, then **Create App**. Copy the **Client ID** and **Secret**.
   - Under **Sandbox → Accounts**, PayPal auto-creates a test *business*
     account (this represents your app) and a test *personal* account
     (this is the "buyer" you'll log in as during checkout). You can view/
     reset the buyer's password from there — you'll need it to log in on
     PayPal's sandbox checkout page.

2. **Fill in `.env`** (copy from `.env.example` if you don't have one yet):
   ```
   PAYPAL_MODE=sandbox
   PAYPAL_CLIENT_ID=<your sandbox client id>
   PAYPAL_CLIENT_SECRET=<your sandbox secret>
   PAYPAL_WEBHOOK_ID=<see step 3>
   ```

3. **Set up the webhook** (optional for local testing, required before
   going live). PayPal's servers can't reach `127.0.0.1`, so for local
   testing either skip this — the return-URL flow alone (step 4) is enough
   to complete a payment — or expose your dev server with a tunnel (e.g.
   `ngrok http 8000`) and:
   - In your sandbox app, click **Add Webhook**, point it at
     `https://<your-tunnel-domain>/billing/webhook/paypal/`, and subscribe
     to at least **Checkout order approved** and **Payment capture
     completed**.
   - Copy the generated **Webhook ID** into `PAYPAL_WEBHOOK_ID` in `.env`.

4. **Run through a checkout.**
   - `python manage.py runserver`, log into the app, and click **Subscribe**
     on the Pro or Family plan (landing page pricing section).
   - You'll be redirected to PayPal's sandbox checkout. Log in with the
     sandbox **personal/buyer** account's email + password from step 1,
     then approve the payment.
   - PayPal redirects you back to `billing:payment_return`, which captures
     the order server-to-server and shows the success page. Check
     **Payment History** (`/billing/history/`) or `/admin/` to see the
     `Payment` row, including the raw PayPal responses.
   - To test a cancelled/failed payment, back out of the sandbox checkout
     page instead of approving — you'll land on the failed-payment page.

No real money ever moves in sandbox mode — only PayPal sandbox test
accounts can complete a "payment" against sandbox credentials.

### Switching to PostgreSQL for production

Uncomment `psycopg2-binary` in `requirements.txt` and swap the
`DATABASES` block in `config/settings.py` (a ready-to-uncomment block is
included inline) using `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`,
`DB_PORT` environment variables.

## Project structure

```
moneymgmt/
├── manage.py
├── config/              # settings, root urls, wsgi/asgi
├── core/                # landing page, static pages (about/contact/privacy/terms/help), 404
├── accounts/            # auth, Profile model, profile & settings pages
├── finance/             # dashboard, income, expenses, budgets, savings,
│                          transactions, reports, notifications, calendar
├── templates/           # base.html, app_base.html (sidebar shell), 404.html
├── static/
│   ├── css/style.css    # full design system + animations
│   └── js/main.js       # interactions
└── media/                # user uploads (avatars, receipts)
```

## A note on testing

This project was hand-written in a sandboxed environment without network
access, so it could not be pip-installed or run end-to-end here. Every
Python file was syntax-checked (`py_compile`), every Django template tag
was checked for balanced `{% %}` pairs, and every `{% url %}` reference
and view function referenced from `urls.py` was cross-checked against its
definition — but please run `python manage.py check` and click through
the flows locally before treating this as production-ready.

