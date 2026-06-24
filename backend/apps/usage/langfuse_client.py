"""Langfuse 연동 (가드형) — env 설정 시에만 langchain CallbackHandler를 제공한다.

LANGFUSE_PUBLIC_KEY/SECRET_KEY 미설정이면 None을 반환해 dev/test에선 완전 no-op이다(외부 경계라
테스트는 Langfuse를 치지 않는다). 본문 캡처는 LANGFUSE_CAPTURE_CONTENT(기본 on)로 끈다 — off면
입력/출력을 마스킹한다. import·생성 실패도 no-op으로 흡수한다(배포 환경 차이에 견고).
"""
import functools
import os


def langfuse_enabled() -> bool:
    return bool(os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"))


def _capture_content() -> bool:
    return os.environ.get("LANGFUSE_CAPTURE_CONTENT", "true").lower() == "true"


@functools.lru_cache(maxsize=1)
def get_langfuse_handler():
    """설정됐으면 Langfuse langchain CallbackHandler를, 아니면 None을 반환(캐시)."""
    if not langfuse_enabled():
        return None
    try:
        if not _capture_content():
            # 본문 캡처 off — 전역 클라이언트에 마스크를 걸어 입력/출력을 가린다(킬스위치).
            try:
                from langfuse import Langfuse
                Langfuse(mask=lambda data=None, **_: "[REDACTED]")
            except Exception:
                pass
        from langfuse.langchain import CallbackHandler
        return CallbackHandler()
    except Exception:
        return None
