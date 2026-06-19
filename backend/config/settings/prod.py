from .base import *

DEBUG = False
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "").split(",")

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# prod(GPU 없는 Oracle A1)는 플랫폼 기본 Provider를 끈다 — Tenant가 자기 LLM·Embedding
# Provider를 설정해야 인제스션·챗·검색이 동작한다(ADR-0012, 온보딩 필수).
PLATFORM_DEFAULT_PROVIDERS_ENABLED = False
