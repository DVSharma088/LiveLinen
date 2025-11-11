"""
Django settings for hrms (LiveLinen) project.

Combined: development-friendly (load_dotenv) and production-friendly (env-driven).
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url

# Base dir
BASE_DIR = Path(__file__).resolve().parent.parent

# Load local .env for development convenience (ignored in git)
load_dotenv(BASE_DIR / ".env")

# --------------------------
# SECURITY
# --------------------------
SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "dev-fallback-key-please-set-DJANGO_SECRET_KEY-in-env"
)

DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() in ("1", "true", "yes")

_allowed_hosts_raw = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")
ALLOWED_HOSTS = [h.strip() for h in _allowed_hosts_raw.split(",") if h.strip()]

# --------------------------
# APPS
# --------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third-party apps
    "rest_framework",
    "crispy_forms",
    "crispy_bootstrap5",
    "channels",

    # Local apps
    "core",
    "vendors",
    "rawmaterials.apps.RawmaterialsConfig",
    "components.apps.ComponentsConfig",
    "finished_products",
    "workorders.apps.WorkordersConfig",
    "dispatch.apps.DispatchConfig",
    "chat",
    "category_master.apps.CategoryMasterConfig",
    "size_master",
    "category_master_new.apps.CategoryMasterNewConfig",
    "costing_sheet",
    "issue_material",
]

# --------------------------
# MIDDLEWARE
# --------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # <--- WhiteNoise (serves static files)
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.DashboardLoginRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# --------------------------
# URL / WSGI / ASGI
# --------------------------
ROOT_URLCONF = "hrms.urls"
WSGI_APPLICATION = "hrms.wsgi.application"
ASGI_APPLICATION = "hrms.asgi.application"

# --------------------------
# TEMPLATES
# --------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.csrf",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.unread_notifications_count",
            ],
        },
    },
]

# --------------------------
# DATABASE
# --------------------------
# Prefer DATABASE_URL (Render Postgres). Fall back to existing env fields or sqlite.
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    DATABASES = {"default": dj_database_url.parse(DATABASE_URL, conn_max_age=600)}
else:
    # Keep backward-compatible env-based DB config (as in your original file)
    DATABASES = {
        "default": {
            "ENGINE": os.getenv("DJANGO_DB_ENGINE", "django.db.backends.sqlite3"),
            "NAME": os.getenv("DJANGO_DB_NAME", str(BASE_DIR / "db.sqlite3")),
            "USER": os.getenv("DJANGO_DB_USER", ""),
            "PASSWORD": os.getenv("DJANGO_DB_PASSWORD", ""),
            "HOST": os.getenv("DJANGO_DB_HOST", ""),
            "PORT": os.getenv("DJANGO_DB_PORT", ""),
        }
    }

# --------------------------
# AUTH / PASSWORD VALIDATION
# --------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --------------------------
# INTERNATIONALIZATION
# --------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# --------------------------
# STATIC & MEDIA
# --------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# WhiteNoise recommended storage for production
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# --------------------------
# DEFAULT PK
# --------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------
# CHANNEL LAYERS
# --------------------------
if os.getenv("DJANGO_CHANNELS_BACKEND") == "channels_redis":
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")],
            },
        }
    }
else:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        },
    }

# --------------------------
# CUSTOM SETTINGS
# --------------------------
PACKAGING_HANDOFF_THRESHOLD_HOURS = int(os.getenv("PACKAGING_HANDOFF_THRESHOLD_HOURS", "2"))

# --------------------------
# AUTH / LOGIN
# --------------------------
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "login"

LOGIN_EXEMPT_URLS = [
    r"^accounts/login/$",
    r"^accounts/logout/$",
    r"^accounts/password_reset/",
    r"^static/",
    r"^media/",
    r"^admin/login/",
    r"^health/?$",
    r"^size-master/ajax/category-sizes/",
]

# --------------------------
# EMAIL & ADMINS
# --------------------------
EMAIL_BACKEND = os.getenv(
    "DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = os.getenv("DJANGO_DEFAULT_FROM_EMAIL", "no-reply@livelinen.com")
SITE_NAME = os.getenv("DJANGO_SITE_NAME", "LiveLinen")

ADMINS_RAW = os.getenv("DJANGO_ADMINS", "")
if ADMINS_RAW:
    ADMINS = [
        tuple(part.strip() for part in a.split(":"))
        for a in ADMINS_RAW.split(",")
        if ":" in a
    ]
else:
    ADMINS = []

# SMTP email config (only if using SMTP backend)
if os.getenv("DJANGO_EMAIL_BACKEND") == "django.core.mail.backends.smtp.EmailBackend":
    EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
    EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
    EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() in ("1", "true", "yes")
    EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")

# Low stock alert recipients (preserve existing defaults)
STOCK_ALERT_RECIPIENTS = [
    os.getenv("STOCK_ALERT_PRIMARY", "devvrat@livelinen.com"),
    os.getenv("STOCK_ALERT_SECONDARY", "devvrat@livelinen.com"),
]

# --------------------------
# SECURITY HARDENING (applied when DEBUG is False)
# --------------------------
if not DEBUG:
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", 31536000))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv("SECURE_HSTS_INCLUDE_SUBDOMAINS", "True").lower() in ("1", "true", "yes")
    SECURE_HSTS_PRELOAD = os.getenv("SECURE_HSTS_PRELOAD", "True").lower() in ("1", "true", "yes")

# --------------------------
# LOGGING: basic console logger (good for Render)
# --------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.getenv("DJANGO_LOG_LEVEL", "INFO")},
}
