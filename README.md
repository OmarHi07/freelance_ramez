# rawnaq_accessories1

A bilingual online store for **`rawnaq_accessories1`** (Instagram: [@rawnaq_accessories1](https://www.instagram.com/rawnaq_accessories1/)), a girls' accessories shop.

> The official business name is written exactly as `rawnaq_accessories1` — same spelling in Arabic and English, never translated or capitalised. It lives in one place, `core.constants.BUSINESS_NAME`, and templates read it through the `{% business_name %}` tag.

- **Arabic** is the default language (right-to-left), at `/ar/`. **English** is the second language (left-to-right), at `/en/`.
- Shoppers browse **by brand**, add items to a cart without an account, and sign in only at checkout.
- There is **no online payment**. After checkout the order is saved, and the customer can open WhatsApp with a ready-made message to the store.
- The owner runs the store from a phone-friendly dashboard at **`/owner/`**. The standard Django admin at `/django-admin/` is kept as a technical fallback.
- Prices are shown in Israeli new shekels (₪). The store time zone is Asia/Jerusalem.

> This is version 1. Some things need the owner's confirmation before launch. See the [Launch checklist](#launch-checklist).

---

## Contents

1. [Features](#features)
2. [Architecture](#architecture)
3. [Folder structure](#folder-structure)
4. [Local setup: Windows PowerShell](#local-setup--windows-powershell)
5. [Local setup: macOS / Linux](#local-setup--macos--linux)
6. [Docker Compose setup](#docker-compose-setup)
7. [PostgreSQL configuration](#postgresql-configuration)
8. [Environment variables (`.env`)](#environment-variables-env)
9. [Everyday commands](#everyday-commands): migrations, demo data, owner account, server, tests, Ruff, static files, translations
10. [Product codes, options and image cropping](#product-codes-options-and-image-cropping)
11. [Production image storage](#production-image-storage)
12. [Deployment: Render or Railway](#deployment--render-or-railway)
13. [Custom domain and HTTPS checklist](#custom-domain-and-https-checklist)
14. [Database backup checklist](#database-backup-checklist)
15. [Orders, stock and discounts](#orders-stock-and-discounts)
16. [WhatsApp: behavior and limits](#whatsapp--behavior-and-limitations)
17. [Future: official WhatsApp Business Platform](#future-official-whatsapp-business-platform-integration)
18. [Security notes](#security-notes)
19. [Privacy checklist for addresses and coordinates](#privacy-checklist-addresses-and-coordinates)
20. [Launch checklist](#launch-checklist), including the logo spelling issue

---

## Features

**Storefront**
- Mobile-first, elegant baby-pink design, with a correct Arabic RTL layout and self-hosted fonts.
- Home page with a hero, large brand cards, an optional sale banner, featured products, new arrivals, and Instagram/WhatsApp links in the footer.
- **Brand pages** use the brand's own colors. Text colors are picked automatically for contrast, and colors must be valid `#RRGGBB` values.
- Brand pages can be filtered by category, availability, brand-confirmation status and price, and sorted by newest or price (both directions). HTMX updates the results without reloading the page.
- **Product pages** have an image gallery, variants (color, size and so on) with live price and stock, a quantity selector, and add-to-cart. They also show a clear badge: *Confirmed by brand*, *Not confirmed by brand* or *Status unknown*. Related products from the same brand appear at the bottom.
- The anonymous cart is stored in the server-side session and is **merged safely** into the customer's cart when she logs in.

**Accounts**
- Customers register with email, password, full name and phone, and log in with their email. Logout, password reset and password change are included.
- Customers get a profile page, saved delivery addresses, order history, and an order-status page with a progress tracker.
- Repeated failed logins are throttled with **django-axes** (5 failures → 15-minute cool-off per email + IP).

**Checkout**
- A manual delivery address is required: city/town, street and building/house number. Apartment, postal code and landmark/notes are optional.
- The optional **"Use my current location"** button always shows an explanation first. It asks the browser for the location **once**, and only after the customer confirms. Coordinates, accuracy and a consent timestamp are stored **on that order only**. Checkout works normally if location is refused or unavailable.
- All totals are calculated **on the server**. Totals sent by the browser are ignored.

**Owner dashboard (`/owner/`)**
- Overview cards: new orders, active products, low-stock variants, customers, and sales for the last 7 and 30 days. A list of recent orders follows.
- Orders: search and filters (live with HTMX), order detail, status updates, internal notes, a Google Maps link when the customer shared a location, and a button to message the customer on WhatsApp.
- Products, with **automatic product and option codes (SKUs)** — the owner never types one — and multiple images with preview, ordering, main picture and delete.
- **Variants & stock** offers two option types per row: *Standard / قياسي* (the server fills both localized names, so only the stock quantity is needed) or *Custom option / خيار مخصص* (Arabic and English names, optional colour name and swatch).
- An **Instagram-style crop editor** for every picture: drag, zoom, rotate, reset and apply, with the exact frame the storefront will use. It works with touch, keyboard, RTL and reduced motion, and existing pictures can be reframed with **Adjust crop**.
- Brands, categories and promotions (create, edit, delete, with delete confirmations).
- A stock page (low stock, out of stock, all), customer list and detail, and store settings.
- Arabic and English labels, helpful empty states, and a responsive layout for phones.

---

## Architecture

| Layer | Choice |
|---|---|
| Language / framework | Python 3.13, Django 5.2 (server-rendered templates) |
| Database | PostgreSQL 16 via psycopg 3 (`DATABASE_URL`) |
| Front end | Django templates, custom CSS with CSS variables and logical properties, small vanilla JS, HTMX 2 (vendored, no build step) |
| Images | Pillow. Uploads are re-encoded to WebP, EXIF (including GPS) is stripped, and a thumbnail is generated |
| Static files | WhiteNoise (compressed and hashed in production) |
| App server | Gunicorn |
| Config | django-environ (`.env` locally, platform variables in production) |
| Media storage | Local disk in development; S3-compatible storage or Cloudinary in production |
| Login throttling | django-axes |
| Quality | pytest + pytest-django, Ruff, GitHub Actions CI |

### Django apps

| App | Responsibility |
|---|---|
| `core` | Site settings (singleton), home page, health check, security headers, validators, image helpers, template tags, error pages, logo tool |
| `accounts` | Custom `User` (email login), registration, profile, saved addresses, password flows |
| `catalog` | Brands, categories, products, variants, images, promotions, storefront pages, demo seed |
| `cart` | Session/user carts, HTMX cart updates, safe merge on login |
| `orders` | Checkout, orders with snapshots, status history, WhatsApp link |
| `dashboard` | Owner dashboard (staff only) |

### Service modules

Business rules live in services, not in templates or views.

| Module | What it does |
|---|---|
| `catalog/services/pricing.py` | **Discount calculation**: finds the one best promotion per item, rounds with `Decimal`, calculates cart/order totals and delivery fees |
| `orders/services/creation.py` | **Order creation** inside `transaction.atomic()`: locks the cart, re-checks availability, recalculates totals, snapshots names and prices |
| `orders/services/status.py` | **Status transitions** and stock: deducts stock once on confirmation, restores it once on cancellation, with row locks |
| `orders/services/whatsapp.py` | **WhatsApp message and link generation** (`wa.me/972553003327`) |
| `orders/services/notifications.py` | Notifier interface (`ClickToChatNotifier` today, replaceable later) |
| `cart/services.py` | Cart lookup, add/update/remove, normalization, merge |

### Data model (summary)

- `SiteSettings` (single row): store names (fixed to the official business name and not editable by the owner), WhatsApp numbers, Instagram URL, delivery fee, free-delivery threshold, delivery notice, sale banner.
- `Brand`, `Category`, `Product` (`brand` foreign key, `categories` many-to-many), `ProductVariant` (stock, optional price override, color), `ProductImage`, `Promotion`.
- `Product.sku` and `ProductVariant.sku` are generated by `catalog/skus.py` (`RAW-P-…` / `RAW-V-…`, random UUID hex). They are `editable=False`, so no form — not even a forged POST — can set or change them, and they stay unique and stable for the life of the row. Order items keep their own SKU snapshot.
- `Cart`, `CartItem`.
- `Order` (UUID primary key and a readable `RNQ-YYYYMMDD-XXXX` number), `OrderItem` (price and name snapshots), `OrderStatusHistory`.
- Money is always `DecimalField` / `Decimal`, never a float.
- Database constraints enforce the important rules: valid hex colors, non-negative stock, percentage ≤ 100, a promotion's target matching its scope, one primary image per product, consistent order totals and line totals, and coordinates only together with a consent timestamp.

---

## Folder structure

```
.
├── manage.py
├── config/                  # settings (base / development / production / test), urls, wsgi, storage helper
├── core/                    # site settings, health check, middleware, validators, images, template tags
├── accounts/                # custom user, addresses, auth views
├── catalog/                 # catalogue models, skus.py, pricing service, storefront views, seed_demo, demo_assets/
├── cart/                    # cart models/services/views, cleanup_carts command
├── orders/                  # checkout, order services (creation, status, whatsapp, notifications)
├── dashboard/               # /owner/ views, forms, staff permissions
├── templates/               # all HTML templates (storefront, account, dashboard, errors)
├── static/                  # css/, js/, img/, fonts/ (OFL), vendor/htmx/ (0BSD), vendor/cropperjs/ (MIT)
├── locale/                  # ar + en .po/.mo translation files
├── design/reference/        # original logo location + notes
├── scripts/                 # generate_demo_assets.py (original placeholder artwork)
├── .github/workflows/ci.yml
├── Dockerfile, docker-compose.yml, gunicorn.conf.py
├── requirements.txt, requirements-dev.txt, requirements-cloudinary.txt
├── pyproject.toml           # pytest + Ruff configuration
└── .env.example
```

Each app keeps its own `tests/` folder. Shared fixtures are in `conftest.py`.

---

## Local setup — Windows PowerShell

Prerequisites: [Python 3.13](https://www.python.org/downloads/) and [PostgreSQL 16](https://www.postgresql.org/download/windows/). Use the StackBuilder installer and remember the `postgres` password. Git is optional.

```powershell
# 1. Get the code (or extract the ZIP) and open the folder
cd C:\path\to\freelance_ramez

# 2. Create and activate a virtual environment
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
# If activation is blocked:  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# 3. Install dependencies
python -m pip install --upgrade pip
pip install -r requirements-dev.txt

# 4. Create the database (see "PostgreSQL configuration"), for example in "SQL Shell (psql)":
#    CREATE ROLE rawnaq LOGIN PASSWORD 'change-me-locally' CREATEDB;
#    CREATE DATABASE rawnaq OWNER rawnaq;

# 5. Environment file
Copy-Item .env.example .env
# Edit .env if your database password differs:
#    DATABASE_URL=postgres://rawnaq:change-me-locally@localhost:5432/rawnaq

# 6. Database, demo data, owner account
python manage.py migrate
python manage.py seed_demo
python manage.py createsuperuser

# 7. Run
python manage.py runserver
```

Open <http://127.0.0.1:8000/> (redirects to `/ar/`). The dashboard is at <http://127.0.0.1:8000/owner/>.

> Translation `.mo` files are already compiled in the repository. You only need GNU gettext if you change translations (see [Translations](#translations)).

## Local setup — macOS / Linux

```bash
# Prerequisites: Python 3.13 and PostgreSQL 16
#   macOS:  brew install python@3.13 postgresql@16 && brew services start postgresql@16
#   Ubuntu: sudo apt install python3.13 python3.13-venv postgresql

python3.13 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-dev.txt

# Database (macOS: psql postgres  |  Linux: sudo -u postgres psql)
#   CREATE ROLE rawnaq LOGIN PASSWORD 'change-me-locally' CREATEDB;
#   CREATE DATABASE rawnaq OWNER rawnaq;

cp .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py createsuperuser
python manage.py runserver
```

## Docker Compose setup

This needs Docker Desktop, or Docker Engine with Compose v2.24 or newer.

```bash
cp .env.example .env          # optional; Compose supplies working defaults
docker compose up --build     # starts PostgreSQL 16 + Django on http://localhost:8000
docker compose exec web python manage.py seed_demo
docker compose exec web python manage.py createsuperuser
docker compose exec web pytest
```

The source folder is mounted into the container, so code changes reload automatically. The database is stored in the `pgdata` volume. You can also reach it from your machine on port **5433**.

---

## PostgreSQL configuration

The app reads a single `DATABASE_URL`:

```
postgres://USER:PASSWORD@HOST:PORT/DBNAME
```

Create a dedicated role and database:

```sql
CREATE ROLE rawnaq LOGIN PASSWORD 'choose-a-strong-password' CREATEDB;
CREATE DATABASE rawnaq OWNER rawnaq;
```

`CREATEDB` is only needed locally, so the test runner can create its temporary `test_rawnaq` database. On hosting platforms, use the connection string the platform gives you. Keep `sslmode=require` if it includes it. Persistent connections are enabled (`DATABASE_CONN_MAX_AGE`, default 60 seconds) with health checks.

---

## Environment variables (`.env`)

Copy `.env.example` to `.env` for local work. **Never commit `.env`.** In production, set the variables in your hosting dashboard.

| Variable | Purpose | Example |
|---|---|---|
| `DJANGO_SECRET_KEY` | Required in production (40+ random characters) | `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated host names | `rawnaq.example,www.rawnaq.example` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Full HTTPS origins | `https://rawnaq.example,https://www.rawnaq.example` |
| `SITE_URL` | Public base URL for the owner link in WhatsApp messages | `https://rawnaq.example` |
| `DATABASE_URL` | PostgreSQL connection | `postgres://…` |
| `TRUSTED_PROXY_COUNT` | Reverse proxies in front of the app (Render/Railway: `1`) | `1` |
| `DJANGO_SECURE_SSL_REDIRECT`, `DJANGO_SECURE_HSTS_*` | HTTPS settings (production) | see file |
| `EMAIL_URL`, `DEFAULT_FROM_EMAIL` | Password-reset email (SMTP) | `smtp+tls://user:pass@smtp.example.com:587` |
| `MEDIA_STORAGE_BACKEND` | `local`, `s3` or `cloudinary` | `s3` |
| `S3_*` | S3-compatible storage settings | see below |
| `CLOUDINARY_URL` | Cloudinary credentials | `cloudinary://…` |
| `CSP_EXTRA_IMG_SRC` | Extra image origins allowed by the Content-Security-Policy | `https://media.rawnaq.example` |
| `AXES_FAILURE_LIMIT`, `AXES_COOLOFF_MINUTES` | Login throttling | `5`, `15` |
| `LOW_STOCK_THRESHOLD` | Low-stock warning level | `3` |

Settings modules: `config.settings.development` (default for `manage.py`), `config.settings.production` (default for `wsgi.py` and the Docker image), and `config.settings.test` (used by pytest). Production refuses to start without a strong secret key, `DJANGO_ALLOWED_HOSTS` and `DATABASE_URL`.

---

## Everyday commands

### Migrations
```bash
python manage.py migrate                        # apply
python manage.py makemigrations                 # after model changes
python manage.py makemigrations --check --dry-run   # CI check: nothing missing
```

### Demo data
```bash
python manage.py seed_demo
```
This command is idempotent: running it again updates the same rows. It creates 4 editable demo brands, 5 categories, 12 products with variants and original placeholder illustrations, and three promotions: one for a single product (20%), one for a brand (₪10) and one store-wide (10%). It also fills in the sale-banner and delivery-notice text if they are empty. **It never creates user accounts or passwords.** Delete or edit the demo items from `/owner/` before launch.

### Owner account
There is no public admin sign-up. Create the first owner account on the server:
```bash
python manage.py createsuperuser     # asks for email, full name, password
```
Staff accounts (`is_staff`) can use `/owner/`. Give extra staff `is_staff` from `/django-admin/`.

### Run the development server
```bash
python manage.py runserver           # http://127.0.0.1:8000/
```

### Tests
```bash
pytest                    # full suite (needs PostgreSQL; uses config.settings.test)
pytest orders -k stock    # a subset
```
The suite covers: browsing, the anonymous cart and merging it on login, checkout authentication, per-user order isolation, staff-only dashboard routes (every URL is checked automatically), catalog CRUD permissions, discount dates, scopes and best-discount selection, server-side totals, price snapshots, deducting stock once and restoring it once, invalid status transitions, the international WhatsApp number, Arabic and English pages, optional location, upload validation, security headers and the seed command.

### Ruff
```bash
ruff check .
ruff format .            # or: ruff format --check .
```

### Static files
```bash
python manage.py collectstatic --noinput
```
Development serves static files automatically. In production, WhiteNoise serves compressed, hashed files. The Docker image runs `collectstatic` during the build.

### Translations
Template and code strings are written in English and translated in `locale/ar/LC_MESSAGES/django.po`. Product, brand and category content uses explicit `_ar` / `_en` database fields instead. After changing any text:
```bash
python manage.py makemessages -l ar -l en --ignore=.venv
# edit locale/ar/LC_MESSAGES/django.po
python manage.py compilemessages --ignore=.venv
```
This requires GNU gettext (`brew install gettext`, `apt install gettext`, or gettext for Windows).

### Maintenance
```bash
python manage.py cleanup_carts --days 30             # delete stale anonymous carts
python manage.py purge_order_locations --days 30     # privacy: clear coordinates from finished orders
python manage.py axes_reset                          # clear all login lockouts
python manage.py prepare_logo_mark …                 # see design/reference/README.md
```

---

## Product codes, options and image cropping

### Product codes (SKUs) are generated, never typed

`catalog/skus.py` produces `RAW-P-A1B2C3D4E5F6` for a product and `RAW-V-A1B2C3D4E5F6` for an
option, from random UUID hex. The generators are field defaults, and both fields are
`editable=False`, so:

- the owner form has no SKU input at all, and a forged `sku` in a POST is ignored;
- a code is created once and never changes when names, brands, slugs or options are edited;
- codes are unique (enforced by the database) and safe to create concurrently — no `MAX(id) + 1`;
- codes assigned by hand before this change are kept exactly as they are.

Generated codes stay visible, read-only, in the product list, the product page ("Product code"),
the stock page, order details and the Django admin (where they are also searchable).

### Standard and custom options

Each row of **Variants & stock** picks an option type:

| Option type | What the owner fills in | What the server stores |
| --- | --- | --- |
| **Standard / قياسي** | stock, optional price override, order, active | `name_ar = "قياسي"`, `name_en = "Standard"` |
| **Custom option / خيار مخصص** | Arabic and English names, optional colour name and swatch, stock, … | exactly what was entered |

The mode is a **form-only** field (`dashboard.forms.OptionMode`): nothing was added to the database,
because a variant is "standard" precisely when it carries those two names. JavaScript only shows and
hides the name fields; the server fills them in, requires both names in custom mode, and falls back
to custom for a missing or unknown mode, so a forged POST cannot skip validation. Every product
still needs at least one active option.

### The crop editor

Every owner image field opens a crop modal with a locked aspect ratio, drag-to-move, a zoom slider
and buttons, rotate left/right, reset, cancel and apply. `static/js/image-cropper.js` is one
component shared by all of them; [Cropper.js](https://github.com/fengyuanchen/cropperjs) 1.6.2 (MIT)
is **vendored** under `static/vendor/cropperjs/`, never loaded from a CDN, so the dashboard stays
inside `script-src 'self'`.

| Image | Ratio | Stored at most | Preview |
| --- | --- | --- | --- |
| Brand logo | 1:1 | 800 × 800 | circular mask, square file |
| Brand banner (the brand page background) | 16:5 | 1920 × 600 | wide hero |
| Category image | 1:1 | 800 × 800 | square |
| Product image | 1:1 | 1600 × 1600 | square |

Brand **cards** are drawn from the brand colours; the banner is the background of that brand's own page.

The cropped picture is submitted as an ordinary multipart file (a `Blob`, never base64 in a hidden
field), and object URLs are revoked as they are replaced. **The browser is never trusted:** the
server re-validates the file type and decoded content, rejects SVG, animated GIF, broken and
oversized files, applies EXIF rotation, strips all metadata including GPS, gives the file a random
name, converts to WebP, and **centre-crops anything that arrives with the wrong aspect ratio** — so a
plain upload with JavaScript off ends up the same shape. A crop that is already correct (within 1%)
is left untouched. Small pictures are never upscaled; the owner gets a warning that the result may
look soft.

**Adjust crop** reframes a picture that is already stored: the current same-origin file is loaded
back into the cropper and submitted as a replacement. Replacing a product image regenerates its
thumbnail, and the old files are deleted only **after the database transaction commits**.

---

## Production image storage

Images are stored as files in a storage backend, **never in PostgreSQL**. Every upload is checked (real JPEG/PNG/WebP content, ≤ 5 MB, ≤ 6000 px, SVG rejected), then re-encoded to WebP with metadata removed.

Render and Railway containers have **temporary disks**. Use object storage in production:

### Option A — S3-compatible (recommended: Cloudflare R2, AWS S3, Backblaze B2, DigitalOcean Spaces)
```
MEDIA_STORAGE_BACKEND=s3
S3_BUCKET_NAME=rawnaq-media
S3_ACCESS_KEY_ID=…
S3_SECRET_ACCESS_KEY=…
S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com   # omit for AWS S3
S3_REGION_NAME=auto                                              # e.g. eu-central-1 for AWS
S3_CUSTOM_DOMAIN=media.rawnaq.example                            # public bucket / CDN domain
S3_QUERYSTRING_AUTH=False
CSP_EXTRA_IMG_SRC=https://media.rawnaq.example
```
Make the bucket (or the custom domain in front of it) publicly readable for product images only. Use an access key limited to that bucket.

### Option B — Cloudinary
```bash
pip install -r requirements-cloudinary.txt
```
```
MEDIA_STORAGE_BACKEND=cloudinary
CLOUDINARY_URL=cloudinary://API_KEY:API_SECRET@CLOUD_NAME
CSP_EXTRA_IMG_SRC=https://res.cloudinary.com
```
In the Dockerfile, install `requirements-cloudinary.txt` instead of `requirements.txt`.

### Option C — Local disk (single server only)
If you run one server with a **persistent volume** mounted at `/app/media`, set `DJANGO_SERVE_MEDIA_FILES=True`. This is fine for a small staging site, not for scaling.

The storage choice is made in one place: `config/storage.py`.

---

## Deployment — Render or Railway

The repository deploys with the included **Dockerfile**. It uses Gunicorn, runs as a non-root user, and has a health check on `/healthz/`.

**Common production variables**

```
DJANGO_SECRET_KEY=<generated>
DJANGO_ALLOWED_HOSTS=<your-app-host>,rawnaq.example,www.rawnaq.example
DJANGO_CSRF_TRUSTED_ORIGINS=https://<your-app-host>,https://rawnaq.example,https://www.rawnaq.example
SITE_URL=https://rawnaq.example
DATABASE_URL=<from the platform>
TRUSTED_PROXY_COUNT=1
EMAIL_URL=smtp+tls://…
DEFAULT_FROM_EMAIL=rawnaq_accessories1 <no-reply@rawnaq.example>
MEDIA_STORAGE_BACKEND=s3   (+ S3_* variables)
```

### Render
1. **New → PostgreSQL**. Choose a region close to Israel (e.g. Frankfurt). Copy the *Internal Database URL*.
2. **New → Web Service**, connect the GitHub repo, and choose runtime **Docker**.
3. Add the variables above, with `DATABASE_URL` set to the internal URL.
4. **Health Check Path:** `/healthz/`.
5. **Migrations:** set the *Pre-Deploy Command* to `python manage.py migrate --noinput`. If your plan has no pre-deploy step, override the Docker command with
   `sh -c "python manage.py migrate --noinput && gunicorn config.wsgi:application -c gunicorn.conf.py"`.
6. After the first deploy, open **Shell** and run `python manage.py createsuperuser`. Optionally run `python manage.py seed_demo` on staging.

### Railway
1. **New Project → Deploy from GitHub repo**. Railway detects the Dockerfile.
2. **Add → Database → PostgreSQL**. In the web service variables, set `DATABASE_URL=${{Postgres.DATABASE_URL}}`.
3. Add the common variables. Railway sets `PORT` automatically; Gunicorn uses it.
4. Service **Settings → Deploy**: set the *Pre-deploy command* to `python manage.py migrate --noinput`, and the *Healthcheck path* to `/healthz/`.
5. **Networking → Generate Domain** (or add your custom domain), then update `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` and `SITE_URL`.
6. Create the owner with `railway run python manage.py createsuperuser`, or from the service shell.
7. For media, use S3/R2 (recommended). If you use a Railway volume with local storage instead, mount it at `/app/media` and set `DJANGO_SERVE_MEDIA_FILES=True`. The image runs as a non-root user, so check Railway's volume-permission guidance (for example `RAILWAY_RUN_UID=0`).

---

## Custom domain and HTTPS checklist

- [ ] Add the domain (and `www`) in the hosting dashboard. Create the DNS records it shows (CNAME/ALIAS/A).
- [ ] Wait for the platform's automatic TLS certificate. Open `https://` and confirm the padlock.
- [ ] Update `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` (with `https://`) and `SITE_URL`.
- [ ] Keep `DJANGO_SECURE_SSL_REDIRECT=True` and `TRUSTED_PROXY_COUNT=1`.
- [ ] Start with `DJANGO_SECURE_HSTS_SECONDS=3600`. After a week without HTTPS problems, raise it to `31536000`. Enable `…INCLUDE_SUBDOMAINS` / `…PRELOAD` only if **every** subdomain is HTTPS.
- [ ] Run `python manage.py check --deploy` with production variables. Only the HSTS preload/subdomain warnings you chose to accept should remain.
- [ ] Test: log in, place a test order, open the WhatsApp link, and open the owner link from WhatsApp while logged out (it must ask you to log in).
- [ ] Choose one canonical domain and redirect the other (for example `www` → apex) at the platform/DNS level.
- [ ] Set up email sending (SPF/DKIM for the sending domain) and test the password reset.

## Database backup checklist

- [ ] Turn on the platform's automatic daily backups or point-in-time recovery for PostgreSQL. Check the retention period.
- [ ] Keep an extra off-platform copy each week:
      `pg_dump --format=custom --no-owner "$DATABASE_URL" > rawnaq-$(date +%F).dump`
- [ ] Store dumps encrypted, in a different account or region from the app.
- [ ] **Test a restore** into a scratch database at least once a quarter:
      `pg_restore --no-owner --dbname "$SCRATCH_DATABASE_URL" rawnaq-YYYY-MM-DD.dump`
- [ ] Turn on object versioning or lifecycle rules for the media bucket (product images are not in the database).
- [ ] Take a backup before every deploy that includes migrations.
- [ ] Keep production environment variables in a password manager so the app can be rebuilt.

---

## Orders, stock and discounts

**Status flow**

```
PENDING ──► RECEIVED ──► CONFIRMED ──► PREPARING ──► OUT_FOR_DELIVERY ──► DELIVERED
   │            │            │              │                 │
   └────────────┴────────────┴──────────────┴─────────────────┴──► CANCELLED
(PENDING can also go straight to CONFIRMED.)  DELIVERED and CANCELLED are final.
```

- Every change is saved in `OrderStatusHistory`, with the time and the staff user who made it.
- **Stock is not reduced at checkout.** It is reduced **once**, when the owner sets the order to **CONFIRMED**. The order and variant rows are locked (`SELECT … FOR UPDATE`) and `stock_deducted_at` is recorded. If any item is short, nothing is deducted and the owner sees which SKUs are short. Stock can never go negative (service check plus a database constraint).
- If a confirmed order is **cancelled**, stock is restored **once** (`stock_restored_at`). Cancelling an order that was never confirmed does not touch stock.
- Orders keep **snapshots**: customer name, email and phone; the full address; and for each item the product name, variant, SKU, quantity, original unit price, discount, final unit price and line total. Later edits to products or promotions never change past orders.
- Order numbers look like `RNQ-20260921-AB12`. Customer pages use the order UUID. Customers can only see their own orders; any other order returns "not found".

**Discount rules**

- A promotion can be a percentage or a fixed amount. It has a start date and an optional end date, an enabled switch, a priority, and a scope: the whole store, a brand, a category or one product.
- **Only one promotion applies to an item. Discounts never stack.** The highest priority wins. When priorities are equal, the biggest discount for that item wins. Remaining ties go to the most specific scope.
- A percentage must be between 1 and 100. A fixed discount is capped at the item price, so a price can never go below zero. A product-scope fixed discount larger than the product price is rejected in the form.
- Discounted prices show the original price with a strike-through and the final price prominently.
- The same pricing code runs on the server when the order is created. Totals from the browser are never trusted.
- Delivery fee: the `SiteSettings.default_delivery_fee`, which becomes free at or above the optional free-delivery threshold (after discounts).

---

## WhatsApp — behavior and limitations

After checkout:
1. The order is saved in PostgreSQL. **The database is the authoritative record.**
2. The confirmation page shows the order number, total and status, and a **"Send order via WhatsApp"** button.
3. The button opens `https://wa.me/972553003327?text=…` with a short message in the customer's language. The message includes a "New rawnaq_accessories1 order" heading, the order number, the customer's name, the total, and a link to the order in the owner dashboard (`https://<site>/owner/orders/<uuid>/`).
4. The owner link **requires a logged-in staff account**. Knowing the URL is not enough: anonymous visitors are sent to the login page, and customers get "403 Forbidden".

Limitations, which the site states clearly to customers:
- The website **only opens** WhatsApp. It cannot send messages or know whether the customer pressed *Send*.
- Pressing the button records `whatsapp_opened_at`, the first time it was pressed. This is **not** "sent". It is shown in the dashboard as "Opened".
- If the customer never sends the message, the order still appears in `/owner/` as **Pending**. Check the dashboard regularly.
- The store number is editable in **Store settings** (international digits only, e.g. `972553003327`). The displayed number is `0553003327`.

## Future: official WhatsApp Business Platform integration

Views only use the notifier interface in `orders/services/notifications.py`:

```python
class OrderNotifier(ABC):
    def new_order(self, order, *, request=None) -> NotificationResult: ...
```

To send owner alerts automatically later:
1. Create a Meta Business account and a WhatsApp Business Platform (Cloud API) app. Register a sender phone number, and get a message **template** approved (for example "New order {{1}}, total {{2}}").
2. Implement `CloudApiNotifier(OrderNotifier)`. It should POST to the Graph API `/{phone-number-id}/messages` endpoint with the template, using a system-user access token stored in an environment variable. It returns `NotificationResult(delivered_by_server=True, …)` and stores the returned message id.
3. Run it from a background job (for example a small task queue, or a `transaction.on_commit` hook that enqueues the job) so checkout never waits on Meta. Add retries and handle status webhooks.
4. Set `ORDER_NOTIFIER_BACKEND=orders.services.notifications.CloudApiNotifier`.
5. Keep the click-to-chat button for customers who want to chat. Version 1 needs **no** Meta credentials.

---

## Security notes

- A custom user model has been used from the first migration. Authentication uses Django sessions (no JWT), CSRF protection on every form and HTMX request, and strong password validation (minimum 10 characters, common/numeric/similarity checks).
- **Login throttling** uses django-axes on (email, IP). Emails are normalized so changing letter case cannot bypass it. Client IPs are only taken from `X-Forwarded-For` when `TRUSTED_PROXY_COUNT` is set.
- **Staff checks are enforced twice** for every dashboard route: each view class checks, and every URL pattern is wrapped. A test walks every dashboard URL as an anonymous user, a customer and staff. The admin URL is not hidden as a security measure; access control is what protects it.
- `next` redirects are only followed when they point to this site.
- Production uses HTTPS redirect, secure/HttpOnly cookies, HSTS, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: same-origin`, COOP, a strict **Content-Security-Policy** (no inline scripts anywhere), and a `Permissions-Policy` that allows geolocation only for this site.
- Brand colors are validated as `#RRGGBB` in forms, models and a database `CHECK`, and filtered again in templates. No CSS from the database is ever output directly.
- Uploads are checked for real image content, size and dimensions, then re-encoded (which removes EXIF/GPS and any embedded payload). Uploaded files get random names.
- Public order URLs use UUIDs. Every customer order query is filtered by the logged-in user.
- Logs are structured JSON in production and **contain no customer personal data**. Gunicorn access logs leave out IP addresses and query strings. Axes verbose logging is off.
- Pages are paginated, and catalog/order queries use `select_related` / `prefetch_related` (a test caps the brand page's query count).

## Privacy checklist (addresses and coordinates)

- [ ] **Location is optional** and requested only after the customer presses "Use my current location" and confirms the explanation. The browser is asked **once** (no tracking, `watchPosition` is never used). Location is never requested during registration.
- [ ] Coordinates, accuracy and a consent timestamp are stored **only on that order**, and only when consent was given. Saved addresses never store coordinates. The database rejects coordinates without a consent timestamp.
- [ ] Only staff can see addresses and coordinates. Customers see only their own orders and addresses.
- [ ] Decide on a retention period and schedule `python manage.py purge_order_locations --days 30`. It clears coordinates from delivered or cancelled orders and keeps the written address.
- [ ] Delete stale anonymous carts regularly: `python manage.py cleanup_carts`.
- [ ] If a customer asks for her account to be deleted: delete the user in `/django-admin/`. Saved addresses and the cart are deleted. Orders keep their snapshot for business records, with the customer link removed. Also check `axes` records (`python manage.py axes_reset_username <email>`).
- [ ] Add a short privacy notice page and link it in the footer before launch. Mention that WhatsApp is a third-party service with its own terms.
- [ ] Limit who has staff accounts. Remove staff access when someone leaves.
- [ ] Never paste customer data into logs, issues or chats. Backups contain personal data, so store them encrypted.

---

## Launch checklist

- [ ] **Logo spelling:** the supplied logo image appears to read **`Rawnaq_accessoris1`**, but the official business name is **`rawnaq_accessories1`**. Ask the owner whether to correct the logo artwork. The website itself renders the name as HTML text, so it is spelled correctly on the site.
- [ ] **Logo file:** the original logo was not included in this version. Save it unmodified in `design/reference/`, then run `python manage.py prepare_logo_mark` to create the cropped face mark for the header (see `design/reference/README.md`). The current header mark is a neutral placeholder.
- [x] **Business name:** settled as `rawnaq_accessories1`, used unchanged on Arabic and English pages, in the owner dashboard, in emails and in WhatsApp messages. To change it later, edit `core.constants.BUSINESS_NAME`, add a data migration for the `SiteSettings` row, and re-translate the few strings that interpolate `%(store)s` in `locale/ar/LC_MESSAGES/django.po`.
- [ ] Confirm the delivery fee (demo: ₪20.00), the free-delivery threshold, and the delivery notice text.
- [ ] Replace or delete the demo brands, products, images and promotions (all created by `seed_demo`). Turn off the demo sale banner.
- [ ] Confirm the brand-verification status of every product with the owner.
- [ ] Create the owner account with `createsuperuser`, using a strong unique password.
- [ ] Configure production email and media storage, and complete the HTTPS and backup checklists above.
- [ ] Place a real test order end-to-end on the production domain, then cancel it.

---

## License

No open-source license is included. All rights reserved by the project owner unless they decide otherwise. Bundled third-party assets keep their own licenses: IBM Plex Sans Arabic, El Messiri and Cormorant Garamond under the SIL Open Font License 1.1 (see `static/fonts/*/OFL.txt`), and HTMX under Zero-Clause BSD (`static/vendor/htmx/LICENSE`). The demo illustrations in `catalog/demo_assets/` are original artwork generated by `scripts/generate_demo_assets.py`.
