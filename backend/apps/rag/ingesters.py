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
    @abstractmethod
    def extract_text(self, file_bytes: bytes) -> str:
        pass

    def ingest(self, file_bytes: bytes, tenant_id: str, document_id: str) -> None:
        from apps.rag.models import Document, DocumentChunk

        doc = Document.objects.get(id=document_id)
        doc.status = Document.STATUS_PROCESSING
        doc.save()

        try:
            text = self.extract_text(file_bytes)
            # Strip control characters: NUL (PostgreSQL rejects), ESC and other
            # non-printable bytes that PDF extractors leak from binary streams.
            # Preserve whitespace (\t \n \r) so chunking stays word-aware.
            import re
            text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
            chunks = chunk_text(text)
            # Document Label(name)을 임베딩 입력에 prefix해, 본문에 제품명이 없어도
            # 제품명 기반 쿼리로 검색되게 한다 (ADR-0006). content에는 raw만 저장.
            embed_inputs = [f"{doc.name}: {chunk}" for chunk in chunks]
            embeddings = get_embeddings(embed_inputs)

            DocumentChunk.objects.filter(document_id=document_id).delete()
            DocumentChunk.objects.bulk_create([
                DocumentChunk(
                    document_id=document_id,
                    tenant_id=tenant_id,
                    content=chunk,
                    embedding=list(emb),
                    chunk_index=i,
                )
                for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
            ])

            doc.status = Document.STATUS_READY
            doc.save()
        except Exception as e:
            doc.status = Document.STATUS_FAILED
            doc.error_message = str(e)
            doc.save()
            raise


def reembed_document_chunks(document_id: str) -> None:
    """기존 DocumentChunk content를 현재 Document.name으로 prefix해 임베딩만 교체한다.

    OCR·텍스트 재추출 없이 임베딩만 갱신하므로 Document Label 변경 비용이 가볍다 (ADR-0006).
    """
    from apps.rag.models import Document, DocumentChunk

    doc = Document.objects.get(id=document_id)
    doc.status = Document.STATUS_PROCESSING
    doc.save()

    try:
        chunks = list(
            DocumentChunk.objects.filter(document_id=document_id).order_by("chunk_index")
        )
        if chunks:
            embed_inputs = [f"{doc.name}: {c.content}" for c in chunks]
            embeddings = get_embeddings(embed_inputs)
            for chunk, emb in zip(chunks, embeddings):
                chunk.embedding = list(emb)
            DocumentChunk.objects.bulk_update(chunks, ["embedding"])

        doc.status = Document.STATUS_READY
        doc.save()
    except Exception as e:
        doc.status = Document.STATUS_FAILED
        doc.error_message = str(e)
        doc.save()
        raise


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

        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        if len(text.split()) < PDF_OCR_FALLBACK_MIN_WORDS:
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
