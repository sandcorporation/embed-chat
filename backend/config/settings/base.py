import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "corsheaders",
    "apps.tenants",
    "apps.chat",
    "apps.rag",
    "apps.memory",
    "apps.core",
    "apps.escalation",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "embed_chat"),
        "USER": os.environ.get("DB_USER", "postgres"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "postgres"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "tenants.Operator"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_TZ = True

# Redis
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Celery
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]

# OpenRouter
OPEN_ROUTER_API_KEY = os.environ.get("OPEN_ROUTER_API_KEY", "")
OPEN_ROUTER_DEFAULT_MODEL = os.environ.get("OPEN_ROUTER_DEFAULT_MODEL", "openrouter/owl-alpha")
OPEN_ROUTER_BASE_URL = os.environ.get("OPEN_ROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# Ollama (embedding)
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "bge-m3")
OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "60.0"))

# EmbedToken
EMBED_TOKEN_TTL_SECONDS = int(os.environ.get("EMBED_TOKEN_TTL_SECONDS", "300"))

# JWT signing key (derived from SECRET_KEY)
JWT_SIGNING_KEY = SECRET_KEY

# CORS
CORS_ALLOW_ALL_ORIGINS = True

# Media
MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"

# PaddleOCR
PADDLE_OCR_URL = os.environ.get("PADDLE_OCR_URL", "http://paddle-ocr:8080")
PADDLE_OCR_TIMEOUT = float(os.environ.get("PADDLE_OCR_TIMEOUT", "60.0"))
