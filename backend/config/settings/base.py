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
    "apps.events",
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

# 이벤트 파이프라인(relay·consumer/bridge) 흐름을 docker logs에서 보려면 INFO를 stdout으로
# 내보내야 한다(Django 기본은 WARNING+만). 관리 명령(relay/consume_events)이 별도 프로세스로
# 도므로 stream 핸들러로 표준출력에 찍는다.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "events": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "events"},
    },
    # propagate=True여도 apps.events에 핸들러가 있어 lastResort가 비활성 → 이중 출력 없음.
    # root엔 핸들러가 없어 prod는 한 줄만, 테스트는 pytest caplog(root)가 캡처한다.
    "loggers": {
        "apps.events": {"handlers": ["console"], "level": "INFO", "propagate": True},
    },
}

AUTH_USER_MODEL = "tenants.Operator"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_TZ = True

# Redis
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Chat 레이트리밋 (공개 /chatbot/{slug}/ 남용·비용 고갈 가드)
CHAT_RATE_LIMIT_PER_VISITOR = int(os.environ.get("CHAT_RATE_LIMIT_PER_VISITOR", "20"))
CHAT_RATE_LIMIT_PER_TENANT = int(os.environ.get("CHAT_RATE_LIMIT_PER_TENANT", "300"))

# Event pipeline (Transactional Outbox + EventBus). 단일 글로벌 내구 스트림(테스트는 격리).
EVENTS_TOPIC = os.environ.get("EVENTS_TOPIC", "events.session")

# Celery
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
# 인터랙티브 chat을 무거운 배치(ingest/community)와 분리된 전용 큐로 보낸다.
# worker-chat이 'chat' 큐만 소비하므로 배치가 밀려도 chat 슬롯이 굶지 않는다.
CELERY_TASK_ROUTES = {
    "apps.chat.tasks.run_chat_agent_task": {"queue": "chat"},
}

# OpenRouter
OPEN_ROUTER_API_KEY = os.environ.get("OPEN_ROUTER_API_KEY", "")
OPEN_ROUTER_DEFAULT_MODEL = os.environ.get("OPEN_ROUTER_DEFAULT_MODEL", "openrouter/owl-alpha")
OPEN_ROUTER_BASE_URL = os.environ.get("OPEN_ROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# 플랫폼 기본 Provider 폴백(OpenRouter LLM + ollama 임베딩)을 켤지 여부.
# dev에서만 True(개발 편의), prod(GPU 없는 Oracle A1)는 False로 두어 Tenant가 자기
# LLM·Embedding Provider를 설정하지 않으면 거부한다(ADR-0012). dev.py/prod.py에서 명시.
# base 기본은 안전하게 False(미설정 환경에서 실수로 플랫폼 비용을 떠안지 않도록).
PLATFORM_DEFAULT_PROVIDERS_ENABLED = False

# Ollama (embedding)
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "bge-m3")
OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "60.0"))

# Neo4j (GraphRAG Knowledge Graph)
# GraphStore 백엔드 선택(neo4j|pg). pg = Postgres+pgvector 흡수(PRD-pgvector-graphstore).
# 개발 중엔 neo4j 기본, 전 메서드 검증 후 컷오버(167)에서 pg로 전환·Neo4j 제거.
GRAPH_BACKEND = os.environ.get("GRAPH_BACKEND", "neo4j")
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "neo4j-test-password")
# GraphRAG entity/relation extraction model (platform-level, separate from tenant chat model)
GRAPH_EXTRACTION_MODEL = os.environ.get("GRAPH_EXTRACTION_MODEL", OPEN_ROUTER_DEFAULT_MODEL)

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
# 스캔 PDF의 vision OCR 비용 통제 — 한 문서에서 OCR할 최대 페이지 수(초과분은 생략).
OCR_MAX_PAGES = int(os.environ.get("OCR_MAX_PAGES", "30"))
