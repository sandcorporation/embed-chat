"""세션 presence(활성=SSE 연결됨) 추적 — deep module (issue 138).

테넌트별 Redis sorted set(member=session_id, score=마지막 갱신 epoch초)로 "지금 누가
연결돼 있는지"를 자가치유 방식으로 둔다. SSE 스트림이 keepalive마다 mark_active로 score를
갱신하고, 연결이 끊겨 갱신이 멈추면 TTL(임계)을 넘겨 active_sessions에서 자연 소멸한다
(워커 비정상 종료에도 stale 활성이 남지 않는다). 진실의 원천이며 콘솔이 이를 조회한다.
"""
import time
from typing import cast

PRESENCE_TTL_SECONDS = 20  # 이 시간 동안 갱신이 없으면 비활성으로 본다(keepalive 1s 대비 여유)


def _key(tenant_id: str) -> str:
    return f"presence:{tenant_id}"


def _conns_key(tenant_id: str, session_id: str) -> str:
    """세션의 살아있는 SSE 연결 id 집합 키(참조 계수). 새로고침 race를 막는다."""
    return f"presence:conns:{tenant_id}:{session_id}"


def _redis():
    from apps.chat.sse import get_redis_client
    return get_redis_client()


def mark_active(tenant_id: str, session_id: str, now: float | None = None) -> None:
    """세션을 지금 활성으로 표시(또는 갱신)한다."""
    now = time.time() if now is None else now
    _redis().zadd(_key(tenant_id), {str(session_id): now})


# ── 연결 참조 계수 (새로고침 race 방지) ───────────────────────────────────────
# 세션 active의 진실원천은 sorted-set(TTL)이지만, 콘솔의 즉시 연결/해제 델타는 '연결 단위'가
# 아니라 '세션 단위' 전이여야 한다. 새로고침은 (옛 연결 종료 + 새 연결 시작)이 겹쳐 일어나는데,
# 옛 연결의 늦은 종료가 disconnect 델타를 내면 콘솔이 유휴로 뒤집힌다. 그래서 연결 id 집합으로
# 참조 계수해 0→1(첫 연결)·1→0(마지막 종료) 전이에서만 이벤트를 내보낸다.

def register_connection(tenant_id: str, session_id: str, conn_id: str, now: float | None = None) -> bool:
    """이 SSE 연결을 등록하고 세션을 활성으로 표시한다. 세션의 '첫' 연결이면 True(0→1)."""
    now = time.time() if now is None else now
    r = _redis()
    key = _conns_key(tenant_id, session_id)
    pipe = r.pipeline()
    pipe.scard(key)               # 추가 전 연결 수
    pipe.sadd(key, conn_id)
    pipe.expire(key, PRESENCE_TTL_SECONDS)  # 비정상 종료 시 집합 자연 소멸(self-healing)
    before = pipe.execute()[0]
    mark_active(tenant_id, session_id, now)
    return before == 0


def touch_connection(tenant_id: str, session_id: str, conn_id: str, now: float | None = None) -> None:
    """keepalive: 하트비트(score) + 연결 집합 TTL을 갱신한다(만료로 인한 소멸 방지·복구)."""
    now = time.time() if now is None else now
    r = _redis()
    key = _conns_key(tenant_id, session_id)
    r.sadd(key, conn_id)  # TTL 만료로 사라졌었다면 복구
    r.expire(key, PRESENCE_TTL_SECONDS)
    mark_active(tenant_id, session_id, now)


def unregister_connection(tenant_id: str, session_id: str, conn_id: str) -> bool:
    """이 SSE 연결을 해제한다. 세션의 '마지막' 연결이었으면 True(1→0)."""
    r = _redis()
    key = _conns_key(tenant_id, session_id)
    pipe = r.pipeline()
    pipe.srem(key, conn_id)
    pipe.scard(key)
    after = pipe.execute()[1]
    return after == 0


def active_sessions(tenant_id: str, now: float | None = None) -> set[str]:
    """임계(TTL) 이내로 갱신된 활성 세션 id 집합. 조회 시 오래된 항목을 정리한다(자가치유)."""
    now = time.time() if now is None else now
    r = _redis()
    key = _key(tenant_id)
    r.zremrangebyscore(key, "-inf", now - PRESENCE_TTL_SECONDS)  # 임계 밖(stale) 제거
    members = cast(list, r.zrange(key, 0, -1))  # 동기 클라이언트지만 redis-py 타입은 Awaitable|... 유니온
    return {m.decode() if isinstance(m, bytes) else m for m in members}
