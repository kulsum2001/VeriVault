"""
Django settings for the VeriVault project.

SQLite only, no third-party services. Every option that matters for a real
deployment can be overridden with an environment variable (see README.md).
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default):
    value = os.environ.get(name)
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------
SECRET_KEY = os.environ.get(
    "VERIVAULT_SECRET_KEY",
    "django-insecure-verivault-dev-key-change-me-before-deploying-0123456789",
)
DEBUG = env_bool("VERIVAULT_DEBUG", True)
ALLOWED_HOSTS = env_list("VERIVAULT_ALLOWED_HOSTS", ["localhost", "127.0.0.1", "[::1]", "testserver"])
CSRF_TRUSTED_ORIGINS = env_list("VERIVAULT_CSRF_TRUSTED_ORIGINS", [])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.sitemaps",
    "accounts.apps.AccountsConfig",
    "vault.apps.VaultConfig",
    "api.apps.ApiConfig",
    "core.apps.CoreConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "myproject.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site",
            ],
        },
    },
]

WSGI_APPLICATION = "myproject.wsgi.application"
ASGI_APPLICATION = "myproject.asgi.application"

# --------------------------------------------------------------------------
# Database (SQLite3 only)
# --------------------------------------------------------------------------
# VERIVAULT_DATA_DIR lets a host with a persistent disk (Render, Fly.io, a VPS)
# point the database and file storage at a mounted volume with one env var,
# instead of the app's own (often ephemeral) code directory. Unset locally -
# everything then lives inside the project folder exactly as before.
DATA_DIR = Path(os.environ.get("VERIVAULT_DATA_DIR", BASE_DIR))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "db.sqlite3",
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------
AUTH_USER_MODEL = "auth.User"
AUTHENTICATION_BACKENDS = ["accounts.backends.EmailOrUsernameBackend"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "vault:dashboard"
LOGOUT_REDIRECT_URL = "core:home"

# Failed-login throttling (uses the local-memory cache; no Redis needed).
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 15 * 60
# How long a password re-entry unlocks sensitive documents.
REAUTH_WINDOW_SECONDS = 10 * 60

# --------------------------------------------------------------------------
# Internationalisation
# --------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------
# Static & media
# --------------------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# WhiteNoise serves static files directly from the app process, so a
# deployment needs nothing extra (no S3, no separate static host, no CDN)
# to get CSS/JS/images. Static files are code assets, rebuilt on every
# deploy by `collectstatic` - they don't need to live on a persistent disk.
# The compressed, cache-busting manifest storage only works after
# `collectstatic` has run, so it's used in production only; local dev
# (`runserver`, tests) keeps Django's plain static storage, which needs no
# build step.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if not DEBUG
            else "django.contrib.staticfiles.storage.StaticFilesStorage"
        )
    },
}

# Public media (profile pictures only) - served by runserver when DEBUG=True,
# and by WhiteNoise otherwise falls back to Django's normal view - fine for
# small personal deployments; move to S3/R2 for anything bigger.
MEDIA_URL = "media/"
MEDIA_ROOT = DATA_DIR / "media"

# Vault documents live OUTSIDE the public media tree and are only ever served
# through permission-checked views (see vault/storage.py).
VAULT_STORAGE_ROOT = DATA_DIR / "vault_storage"

# Upload rules
VAULT_MAX_UPLOAD_MB = 25
VAULT_DEFAULT_QUOTA_MB = 500
VAULT_BLOCKED_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".com", ".msi", ".scr", ".pif", ".vbs", ".vbe",
    ".js", ".jse", ".wsf", ".ps1", ".sh", ".jar", ".dll", ".apk", ".app",
    ".html", ".htm", ".svg", ".php",
}
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # non-file form data
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # larger files stream to temp files

# --------------------------------------------------------------------------
# Security
# --------------------------------------------------------------------------
X_FRAME_OPTIONS = "SAMEORIGIN"  # PDF previews are framed from the same origin
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 12
SESSION_SAVE_EVERY_REQUEST = False

if not DEBUG:
    SESSION_COOKIE_SECURE = env_bool("VERIVAULT_HTTPS", True)
    CSRF_COOKIE_SECURE = env_bool("VERIVAULT_HTTPS", True)
    SECURE_SSL_REDIRECT = env_bool("VERIVAULT_HTTPS", True)
    SECURE_HSTS_SECONDS = 31536000 if env_bool("VERIVAULT_HTTPS", True) else 0

# --------------------------------------------------------------------------
# Email (console backend - password reset mails are printed to the terminal)
# --------------------------------------------------------------------------
EMAIL_BACKEND = os.environ.get("VERIVAULT_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = "VeriVault <no-reply@verivault.local>"

# --------------------------------------------------------------------------
# Cache (local memory; used for login throttling only)
# --------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "verivault-default",
    }
}

# --------------------------------------------------------------------------
# Site
# --------------------------------------------------------------------------
SITE_NAME = "VeriVault"
SITE_TAGLINE = "Your documents, sealed and provable."
SITE_DESCRIPTION = (
    "VeriVault is a secure digital document vault: store, organise, share and "
    "verify important documents with SHA-256 fingerprints, version history, "
    "expiry reminders and a complete audit trail."
)
SITE_URL = os.environ.get("VERIVAULT_SITE_URL", "http://127.0.0.1:8000")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
}
