"""ChatRateLimiter (deep module).

공개 챗봇 URL이 무방비로 노출되지 않도록 메시지 경로에 고정 윈도우 레이트리밋을 둔다.
(tenant, visitor)당 + per-tenant 상한으로 스팸·비용 고갈을 막는다(하드 예산 캡은 기능 C).
Redis INCR+expire 기반이라 실제 Redis로 결정적으로 테스트된다.
"""
from apps.chat.sse import get_redis_client

WINDOW_SECONDS = 60
PER_VISITOR_PER_MINUTE = 20
PER_TENANT_PER_MINUTE = 300


def _hit(r, key: str) -> int:
    count = r.incr(key)
    if count == 1:
        r.expire(key, WINDOW_SECONDS)
    return count


def allow_message(
    tenant_id: str,
    visitor_id: str,
    per_visitor: int = PER_VISITOR_PER_MINUTE,
    per_tenant: int = PER_TENANT_PER_MINUTE,
) -> bool:
    """이번 메시지를 허용하면 True, 한도 초과면 False."""
    r = get_redis_client()
    v = _hit(r, f"ratelimit:v:{tenant_id}:{visitor_id}")
    t = _hit(r, f"ratelimit:t:{tenant_id}")
    return v <= per_visitor and t <= per_tenant
