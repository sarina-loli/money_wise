"""
Django settings for the Personal Money Management System.
"""
from pathlib import Path
import os
import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Reads a .env file in the project root (same folder as manage.py) if present.
# Copy .env.example to .env and fill in real values — .env is gitignored.
load_dotenv(BASE_DIR / '.env')

# -------------------------------------------------------------------------
# SECURITY
# -------------------------------------------------------------------------
SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'dev-only-secret-key-CHANGE-THIS-IN-PRODUCTION-1234567890'
)

DEBUG = os.environ.get("DJANGO_DEBUG", "False") == "True"

ALLOWED_HOSTS = os.environ.get(
    "DJANGO_ALLOWED_HOSTS",
    "127.0.0.1,localhost,money-wise-aa1n.onrender.com"
).split(",")

# -------------------------------------------------------------------------
# APPLICATIONS
# -------------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',

    # Local apps
    'core',
    'accounts',
    'finance',
    'billing',
    'households',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.site_settings',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# -------------------------------------------------------------------------
# DATABASE
# -------------------------------------------------------------------------
DATABASES = {
    "default": dj_database_url.config(
        default=os.environ.get("DATABASE_URL")
    )
}
# For production (PostgreSQL), set these environment variables and swap the
# ENGINE to 'django.db.backends.postgresql':
#   DATABASES['default'] = {
#       'ENGINE': 'django.db.backends.postgresql',
#       'NAME': os.environ.get('DB_NAME'),
#       'USER': os.environ.get('DB_USER'),
#       'PASSWORD': os.environ.get('DB_PASSWORD'),
#       'HOST': os.environ.get('DB_HOST', 'localhost'),
#       'PORT': os.environ.get('DB_PORT', '5432'),
#   }

# -------------------------------------------------------------------------
# PASSWORD VALIDATION
# -------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# -------------------------------------------------------------------------
# INTERNATIONALIZATION
# -------------------------------------------------------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# -------------------------------------------------------------------------
# STATIC & MEDIA FILES
# -------------------------------------------------------------------------
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# -------------------------------------------------------------------------
# AUTH
# -------------------------------------------------------------------------
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'finance:dashboard'
LOGOUT_REDIRECT_URL = 'core:landing'

# -------------------------------------------------------------------------
# EMAIL (console backend for development — password reset emails print to
# the terminal that's running `runserver`. Swap to an SMTP backend in prod.)
# -------------------------------------------------------------------------
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = 'MoneyWise <no-reply@moneywise.app>'

SITE_NAME = 'MoneyWise'

# -------------------------------------------------------------------------
# BILLING
# -------------------------------------------------------------------------
# No payment processor is wired up in this build. "Checking out" just
# starts a local free trial (see billing/views.py and billing/plans.py) —
# no card is collected and nothing is ever charged. Plug a real provider
# back in here when you're ready to accept payments.
SITE_URL = os.environ.get('SITE_URL', 'http://127.0.0.1:8000')
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

EMAIL_HOST = "smtp.gmail.com"

EMAIL_PORT = 587

EMAIL_USE_TLS = True

EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL")
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER