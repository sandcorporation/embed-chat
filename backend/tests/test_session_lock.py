import time


# ── Issue 83: 세션 단위 직렬화 — Redis 락 deep module ──────────────────────────

def test_acquire_blocks_second_holder_until_release():
    """같은 세션은 한 번에 하나만 락을 쥔다 — 두 번째 acquire는 실패, release 후 재획득."""
    from apps.chat.session_lock import acquire, release

    sid = "lock-serialize-1"
    try:
        assert acquire(sid) is True, "처음엔 락을 획득해야 한다"
        assert acquire(sid) is False, "이미 쥔 락은 다시 획득되면 안 된다"
        release(sid)
        assert acquire(sid) is True, "release 후엔 다시 획득되어야 한다"
    finally:
        release(sid)


def test_lock_has_ttl_self_heals_without_release():
    """release를 못 해도 TTL 만료 후 락이 풀려 세션이 영구 데드락되지 않는다."""
    from apps.chat.session_lock import acquire, release

    sid = "lock-ttl-1"
    try:
        assert acquire(sid, ttl=1) is True
        assert acquire(sid, ttl=1) is False, "TTL 안에는 여전히 잠겨 있어야 한다"
        time.sleep(1.2)
        assert acquire(sid, ttl=1) is True, "TTL 만료 후엔 자가치유되어 재획득되어야 한다"
    finally:
        release(sid)
