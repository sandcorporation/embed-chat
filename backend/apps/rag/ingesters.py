from abc import ABC, abstractmethod
from typing import List


CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        if chunk:
            chunks.append(chunk)
        start = end - overlap
    return chunks


def get_embeddings(texts: List[str]) -> List[List[float]]:
    import httpx
    from django.conf import settings

    resp = httpx.post(
        f"{settings.OLLAMA_BASE_URL}/api/embed",
        json={"model": settings.OLLAMA_EMBED_MODEL, "input": texts},
        timeout=getattr(settings, "OLLAMA_TIMEOUT", 60.0),
    )
    resp.raise_for_status()
    return resp.json()["embeddings"]


class DocumentIngester(ABC):
    """문서에서 텍스트를 추출하는 인터페이스. (GraphRAG: 추출 텍스트는 GraphIngester가 그래프로 변환)"""

    @abstractmethod
    def extract_text(self, file_bytes: bytes) -> str:
        pass


def _call_ocr(image_bytes: bytes) -> str:
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


PDF_OCR_FALLBACK_MIN_WORDS = 50


def _ocr_pdf(file_bytes: bytes) -> str:
    import fitz
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    texts = []
    for page in doc:
        pix = page.get_pixmap(dpi=150)
        png_bytes = pix.tobytes(output="png")
        page_text = _call_ocr(png_bytes)
        if page_text:
            texts.append(page_text)
    return "\n".join(texts)


class PDFIngester(DocumentIngester):
    def extract_text(self, file_bytes: bytes) -> str:
        import fitz  # pymupdf
        from apps.rag.text_quality import is_garbled

        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        # 텍스트 레이어가 희소(스캔)하거나 폰트 인코딩이 깨져(mojibake) 추출되면 OCR로 재추출한다.
        if len(text.split()) < PDF_OCR_FALLBACK_MIN_WORDS or is_garbled(text):
            text = _ocr_pdf(file_bytes)
        return text


class TXTIngester(DocumentIngester):
    def extract_text(self, file_bytes: bytes) -> str:
        return file_bytes.decode("utf-8", errors="replace")


class ImageIngester(DocumentIngester):
    def extract_text(self, file_bytes: bytes) -> str:
        return _call_ocr(file_bytes)


MIME_TO_INGESTER = {
    "application/pdf": PDFIngester,
    "text/plain": TXTIngester,
    "image/png": ImageIngester,
    "image/jpeg": ImageIngester,
    "image/webp": ImageIngester,
}


def get_ingester(mime_type: str) -> DocumentIngester:
    cls = MIME_TO_INGESTER.get(mime_type)
    if not cls:
        raise ValueError(f"Unsupported mime type: {mime_type}")
    return cls()
