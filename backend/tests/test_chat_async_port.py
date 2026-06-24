"""토큰 포트 + 세션 락 async (issue 193) — 실제 async redis로 검증."""
import asyncio


async def test_session_lock_async_serializes():
    """aacquire는 세션당 하나만 허용하고, arelease 후 다시 획득된다."""
    from apps.chat.session_lock import aacquire, arelease

    sid = "lock-async-1"
    await arelease(sid)  # 선행 정리
    assert await aacquire(sid) is True
    assert await aacquire(sid) is False   # 이미 보유 → 실패
    await arelease(sid)
    assert await aacquire(sid) is True     # 해제 후 재획득
    await arelease(sid)


async def test_token_port_async_roundtrip():
    """apublish_token → asubscribe로 토큰 메시지를 수신한다(async pub/sub)."""
    from apps.chat.sse import apublish_token, asubscribe

    sid = "tok-async-1"
    received = []

    async def consume():
        async for msg in asubscribe(sid):
            received.append(msg)
            return

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.2)                # 구독 준비 대기
    await apublish_token(sid, "hi")
    await asyncio.wait_for(task, timeout=5)
    assert received[0] == {"type": "token", "content": "hi"}
