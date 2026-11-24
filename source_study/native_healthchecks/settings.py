"""Configuration for a real Django API boundary, with original application modules."""
import os
from hc.settings import *
from .contracts import SECRET

SECRET_KEY = SECRET
SITE_ROOT = "http://testserver"
PING_ENDPOINT = "http://testserver/ping/"
ALLOWED_HOSTS = ["testserver"]
DEBUG = False
INSTALLED_APPS = ["django.contrib.auth", "django.contrib.contenttypes", "hc.accounts", "hc.api"]
ROOT_URLCONF = "hc.api.urls"
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware", "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware"]
MIGRATION_MODULES = {"accounts": None, "api": None}
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": os.environ["HEALTHCHECKS_DB"]}}
LOGGING_CONFIG = None
MAILERS = {}
S3_BUCKET = None
STATSD_HOST = None
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [], "APP_DIRS": True, "OPTIONS": {"context_processors": []}}]
