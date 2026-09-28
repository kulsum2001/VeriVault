# VeriVault

A secure digital document vault built with Django 6 and SQLite - store, organise,
share and verify the documents that matter (passports, policies, contracts,
certificates) with SHA-256 fingerprints, full version history, expiring share
links, public verification certificates, expiry reminders, a rule-based vault
"health" advisor, a full audit trail and a token-authenticated JSON API.

No PostgreSQL, MySQL, Node.js, Docker, Redis, Celery or paid/external API keys
are required. Everything runs on the Django dev server with SQLite. The only
two Python packages needed are Django itself and `qrcode` (used to draw the
2FA setup QR code as a lightweight vector image - no image library required).

## Quick start

```bash
# from the folder that contains myproject/
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r myproject/requirements.txt

cd myproject
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000/ - the app itself, http://127.0.0.1:8000/admin/ - the
customised Django admin, http://127.0.0.1:8000/api/docs/ - the API reference.

### Optional: load realistic sample data

```bash
python manage.py seed_data --with-admin
```

Creates three demo users (`demo`, `priya`, `arjun`, password `Demo@12345` for
all) with ~26 documents covering every category, versions, folders, tags,
share links, a user-to-user share, certified documents, an archived and a
trashed document, expiring/expired items and two weeks of activity history -
plus an `admin` / `admin12345` superuser. Run with `--reset` to rebuild it.

## Project layout

```
myproject/
├── manage.py
├── requirements.txt
├── myproject/          # settings, root urls, wsgi/asgi
├── accounts/           # auth, profile, 2FA (TOTP), API tokens, throttling
├── vault/              # documents, folders, tags, sharing, audit log,
│                       #   rule-based intelligence layer, management commands
├── api/                # JSON API (hand-rolled, no DRF dependency)
├── core/                # marketing pages, error pages, sitemap, test helpers
├── templates/           # HTML templates (base, layouts, per-app)
├── static/              # app.css, main.js, theme.js, favicon
├── media/                # profile pictures (created on first upload)
├── vault_storage/        # private document files - never served directly
└── db.sqlite3            # created by `migrate`
```

## Feature tour

- **Documents** - upload, categorise (10 categories), tag, fold into nested
  folders, mark sensitive/critical, favourite, archive, search and filter
  (category, folder, tag, expiry, sensitivity, status), sort, bulk actions,
  grid/list views, pagination.
- **Integrity** - a SHA-256 fingerprint is recorded on upload and on every new
  version; re-check any document (or the whole vault) on demand; mismatches
  are flagged everywhere.
- **Versions** - every re-upload becomes a new version; download or restore
  any earlier version without losing history.
- **Sharing** - expiring, password-protectable, download-capped public
  links; or direct view/download access for another VeriVault user. Critical
  documents cannot be shared by public link.
- **Verification certificates** - publish a document's fingerprint under a
  short code (`VV-XXXX-XXXX-XXXX`); anyone can check a file against it on
  `/verify/` - fingerprinting happens in their browser via the Web Crypto
  API, so the file itself is never uploaded.
- **Rule-based intelligence** (`vault/intelligence.py`, pure Python, no
  external AI service): category/tag/expiry-hint suggestions from a
  filename, a 0-100 vault health score with prioritised recommendations, an
  "essential documents" checklist, duplicate detection by fingerprint, and a
  related-documents ranking.
- **Expiry reminders** - set an issue/expiry date; get in-app notifications
  before renewal, tunable per user (`expiry_alert_days`).
- **Security** - private on-disk storage outside the web root with
  permission-checked downloads, optional TOTP two-factor authentication,
  password re-entry ("re-auth") before opening sensitive/critical documents,
  login throttling, a strict Content-Security-Policy, blocked executable
  uploads, and a full audit log (view/download/share/verify/sign-in, IP +
  user agent) exportable as CSV.
- **REST-style JSON API** - token authentication, documents (CRUD, search,
  download, versions, related), folders, tags, sharing, insights, activity,
  notifications and public verification. See `/api/docs/`.
- **SEO & polish** - `robots.txt`, `sitemap.xml`, Open Graph tags,
  `application/ld+json`, custom 400/403/404/500 pages, dark mode, responsive
  layout, accessible forms.

## Management commands

```bash
python manage.py seed_data [--reset] [--with-admin]   # sample data
python manage.py purge_trash [--days N]                # hard-delete old trash (default 30)
python manage.py check_expiries                        # notifications + deactivate lapsed links
python manage.py verify_integrity                       # re-check every stored file's fingerprint
```

`purge_trash` and `check_expiries` are meant to run on a schedule (cron, a
scheduled task, etc.) in a real deployment; there is no background worker.

## Running the tests

```bash
python manage.py test
```

51 tests cover models, forms, views, the rule-based intelligence layer,
authentication (including 2FA and throttling) and the JSON API.

## Deploying (e.g. to Render)

VeriVault is a normal Django app, so it deploys anywhere that runs Python -
Render, Railway, Fly.io, a plain VPS. The one thing to get right on any of
them: **this app stores real data on disk** (the SQLite database, uploaded
documents, avatars), so the host needs a *persistent* disk, not just an
ephemeral container filesystem - otherwise every redeploy wipes your vault.

The project ships ready for this:
- `gunicorn` - a production application server (`manage.py runserver` is
  dev-only and is never used in production)
- `whitenoise` - serves CSS/JS/images directly from the app, so there's no
  separate static-file host to set up
- `build.sh` - installs dependencies and runs `collectstatic`
- `render.yaml` - a ready-made Render Blueprint (see below)
- `VERIVAULT_DATA_DIR` - one environment variable that moves the database,
  media and document storage onto a mounted disk, wherever that disk lives

### Deploying to Render

1. Push this project to a GitHub/GitLab repo (Render deploys from a repo, not
   a zip upload).
2. In the Render dashboard: **New → Blueprint**, point it at your repo. It
   will read `render.yaml` and set up the service and a 1GB persistent disk
   automatically. Render's persistent disks require a **paid** plan (Starter
   or above) - the free tier's filesystem is wiped on every restart, which
   would lose every uploaded document.
3. Once the service is created, open its **Settings** to see its real URL
   (something like `verivault-xyz.onrender.com`), then update three
   environment variables to match it exactly:
   - `VERIVAULT_ALLOWED_HOSTS`
   - `VERIVAULT_CSRF_TRUSTED_ORIGINS` (include the `https://`)
   - `VERIVAULT_SITE_URL` (include the `https://`)
4. Deploy. On first boot the start command runs `migrate` automatically and
   creates the database on the persistent disk - no manual step needed.
5. Create your admin account with Render's **Shell** tab:
   ```bash
   python manage.py createsuperuser
   ```

**Prefer to set it up by hand instead of the Blueprint?** Create a Web
Service pointing at your repo with:
- Build command: `./build.sh`
- Start command: `python manage.py migrate --noinput && gunicorn myproject.wsgi:application --bind 0.0.0.0:$PORT`
- A persistent disk mounted at, say, `/var/data`
- The environment variables listed under Configuration below, plus
  `VERIVAULT_DATA_DIR` set to that same mount path

**Why migrate runs in the start command, not the build command:** Render's
build step runs on a separate, disk-less machine - it can't reach the
persistent disk, so a migration there would silently apply to a database
that gets thrown away. Running it at the start of the start command means it
always runs against the real, persisted database, every time the service
boots.

### Other platforms

The same pieces (`gunicorn`, `whitenoise`, `VERIVAULT_DATA_DIR` pointed at a
mounted volume, `migrate` run at startup rather than build time) apply
almost unchanged on Railway, Fly.io, or a plain VPS with systemd - only the
exact place you configure a "build command" vs a "start command" and attach
a disk differs.

## Configuration

Everything works with zero configuration. To override defaults, copy
`.env.example` to `.env` (or export the variables) - see that file for the
full list (`VERIVAULT_SECRET_KEY`, `VERIVAULT_DEBUG`, `VERIVAULT_ALLOWED_HOSTS`,
`VERIVAULT_SITE_URL`, `VERIVAULT_HTTPS`, `VERIVAULT_EMAIL_BACKEND`,
`VERIVAULT_CSRF_TRUSTED_ORIGINS`, `VERIVAULT_DATA_DIR`, `VERIVAULT_SERVE_MEDIA`).
Password reset e-mails are printed to the console by default.

## Notes & limitations

- SQLite only, by design - fine for personal or small-team use; swap
  `DATABASES` in `myproject/settings.py` for anything larger.
- No encryption at rest is added by the application - use full-disk
  encryption on the host, and HTTPS in transit, for a real deployment.
- The API is hand-rolled on top of plain Django (no Django REST Framework),
  to keep the dependency list to just Django.
