"""OCR 포트(deep module) — 이미지/스캔 PDF에서 텍스트를 전사한다.

엔진(어댑터)을 단일 인터페이스 `transcribe(image_bytes, mime_type) -> str` 뒤로 숨긴다:
- PaddleOCR — 자체호스팅 PaddleOCR HTTP 서비스. dev/test 폴백(결정적 로컬 OCR — CLAUDE.md).
- VisionOCR — per-Tenant vision 모델(issue 158, prod 경로).

팩토리 `get_ocr_backend(config)`가 tenant config로 엔진을 고른다(embedding_provider와 동일한 폴백 패턴).
"""
from typing import Protocol


class OCRBackend(Protocol):
    """엔진-무관 OCR 포트. 이미지 바이트를 받아 보이는 텍스트를 전사해 돌려준다."""

    def transcribe(self, image_bytes: bytes, mime_type: str = "image/png") -> str: ...


class PaddleOCR:
    """자체호스팅 PaddleOCR HTTP 서비스 어댑터. dev/test의 결정적 OCR 폴백."""

    def transcribe(self, image_bytes: bytes, mime_type: str = "image/png") -> str:
        import base64
        import httpx
        from django.conf import settings

        b64 = base64.b64encode(image_bytes).decode()
        resp = httpx.post(
            f"{settings.PADDLE_OCR_URL}/ocr",
            json={"image_b64": b64},
            timeout=getattr(settings, "PADDLE_OCR_TIMEOUT", 60.0),
        )
        resp.raise_for_status()
        return resp.json().get("text", "")


class VisionOCR:
    """per-Tenant vision 모델 어댑터. transcribe_image 경계로 이미지를 전사한다(prod 경로)."""

    def __init__(self, provider):
        self.provider = provider

    def transcribe(self, image_bytes: bytes, mime_type: str = "image/png") -> str:
        from apps.agent import llm

        return llm.transcribe_image(self.provider, image_bytes, mime_type)


def get_ocr_backend(config=None) -> OCRBackend:
    """tenant config로 OCR 백엔드를 고른다(embedding_provider와 동일한 폴백 패턴).

    OCR Provider 설정됨 → VisionOCR / dev·test 미설정 → Paddle 폴백 / prod 미설정 → ValueError.
    """
    if config is not None and getattr(config, "ocr_provider_type", ""):
        from apps.agent.providers import ocr_provider

        return VisionOCR(ocr_provider(config))

    from django.conf import settings

    if getattr(settings, "PLATFORM_DEFAULT_PROVIDERS_ENABLED", False):
        return PaddleOCR()
    raise ValueError("OCR Provider가 설정되지 않았습니다 (프로덕션은 Tenant 설정 필수)")
