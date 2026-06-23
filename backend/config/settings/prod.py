from .base import *

DEBUG = False
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "").split(",")

# NPM(Nginx Proxy Manager)이 TLS를 종단하고 http로 우리 nginx→api에 포워딩한다. 원 요청이
# https였음을 X-Forwarded-Proto로 신뢰해야 한다 — 없으면 SECURE_SSL_REDIRECT가 (api는 http로
# 보여) 무한 리다이렉트 루프를 만든다. nginx.oracle.conf가 NPM의 X-Forwarded-Proto를 전달한다.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# JWT API라 CSRF는 비필수지만, 프록시 도메인 출처를 명시(있으면 env로 주입; 예: https://chat.example.com).
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o]

# prod(GPU 없는 Oracle A1)는 플랫폼 기본 Provider를 끈다 — Tenant가 자기 LLM·Embedding
# Provider를 설정해야 인제스션·챗·검색이 동작한다(ADR-0012, 온보딩 필수).
PLATFORM_DEFAULT_PROVIDERS_ENABLED = False
