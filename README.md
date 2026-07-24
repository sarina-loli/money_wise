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

