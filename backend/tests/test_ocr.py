"""OCR 포트 — 엔진 주입 + 페이지 상한 (issue 157).

포트는 결정적 Fake 백엔드로 엔진-무관 행동을 검증한다(이미지/스캔PDF가 주입된 백엔드로 전사되는가,
상한이 호출 수를 통제하는가). 실제 Paddle 통합 흐름은 test_rag.py(이미지/스캔PDF 업로드)가 커버한다.
"""
import fitz


class _StubOCR:
    """주입된 OCR 백엔드가 호출되는지/몇 번 호출되는지 보는 결정적 스텁."""

    def __init__(self, text="STUB OCR TEXT"):
        self.text = text
        self.calls = 0

    def transcribe(self, image_bytes, mime_type="image/png"):
        self.calls += 1
        return self.text


def _png_bytes(text="scanned text") -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=600, height=120)
    page.insert_text((20, 80), text, fontsize=28)
    return page.get_pixmap(dpi=150).tobytes(output="png")


def _image_only_pdf(n_pages: int, text="scanned page content") -> bytes:
    png = _png_bytes(text)
    out = fitz.open()
    for _ in range(n_pages):
        p = out.new_page(width=600, height=120)
        p.insert_image(p.rect, stream=png)
    return out.tobytes()


def test_image_ingester_uses_injected_ocr_backend():
    """이미지 ingester는 주입된 OCR 백엔드로 전사한다(엔진 무관 포트)."""
    from apps.rag.ingesters import get_ingester

    stub = _StubOCR("HELLO FROM OCR")
    out = get_ingester("image/png").extract_text(_png_bytes(), stub)
    assert out == "HELLO FROM OCR"
    assert stub.calls == 1


def test_pdf_scanned_fallback_uses_injected_ocr_backend():
    """텍스트 레이어 없는 스캔 PDF는 주입된 OCR 백엔드로 페이지 폴백한다."""
    from apps.rag.ingesters import get_ingester

    stub = _StubOCR("PAGE TEXT")
    out = get_ingester("application/pdf").extract_text(_image_only_pdf(2), stub)
    assert "PAGE TEXT" in out
    assert stub.calls == 2  # 2 페이지 각각 OCR


def test_pdf_ocr_fallback_respects_page_cap(settings):
    """OCR_MAX_PAGES가 거대한 스캔 PDF의 OCR 호출 수를 상한한다(비용 통제)."""
    settings.OCR_MAX_PAGES = 2
    from apps.rag.ingesters import get_ingester

    stub = _StubOCR("PAGE")
    get_ingester("application/pdf").extract_text(_image_only_pdf(5), stub)
    assert stub.calls == 2  # 5페이지지만 상한 2까지만


def test_get_ocr_backend_defaults_to_paddle_in_dev():
    """157 시점: 팩토리는 dev/test에서 Paddle 백엔드를 돌려준다(vision 분기는 158)."""
    from apps.rag.ocr import get_ocr_backend, PaddleOCR

    assert isinstance(get_ocr_backend(None), PaddleOCR)
