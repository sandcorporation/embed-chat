"""공개 가입 IP 레이트리밋 (ADR-0025 후속) — deep module.

공개 Self-Signup 남용을 막는다: **IP당 윈도우(기본 1시간) 1회**. 실패(약한 비번·중복 이름)는 슬롯을
소비하지 않고 **성공한 가입만** 기록한다(typo로 1시간 잠기는 일 방지). nginx 뒤라 X-Forwarded-For의
최좌측을 원 클라이언트 IP로 본다. Redis 단일 키(SET EX)로 단순·결정적.
"""
from django.conf import settings

from apps.chat.sse import get_redis_client


def _window() -> int:
    return int(getattr(settings, "SIGNUP_RATE_LIMIT_WINDOW_SECONDS", 3600))


def client_ip(request) -> str:
    """프록시 체인을 고려한 원 클라이언트 IP. XFF 최좌측 우선, 없으면 REMOTE_ADDR."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or "unknown"


def _key(ip: str) -> str:
    return f"signup:rl:{ip}"


def signup_allowed(ip: str) -> bool:
    """이 IP가 윈도우 내에 이미 성공 가입했으면 False(차단)."""
    return not get_redis_client().exists(_key(ip))


def mark_signup(ip: str) -> None:
    """성공한 가입을 기록 — 윈도우 동안 같은 IP의 추가 가입을 차단한다."""
    get_redis_client().set(_key(ip), "1", ex=_window())
