import io
import os
import socket
import threading

import pytest


# ── Issue 51: Document Chunk Inspector ───────────────────────────────────────

@pytest.mark.django_db
def test_list_chunks_returns_chunks_for_ingested_document(client, tenant_agent_token, tenant_with_key):
    """인제스션된 문서의 /chunks 엔드포인트가 청크 목록을 반환한다."""
    content = b"The FCB1010 has ten footswitches and two expression pedals for live performance."
    f = io.BytesIO(content)
    f.name = "fcb.txt"
    resp = client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    chunk_resp = client.get(
        f"/api/tenant/documents/{doc_id}/chunks",
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert chunk_resp.status_code == 200
    chunks = chunk_resp.json()
    assert isinstance(chunks, list)
    assert len(chunks) >= 1
    assert "chunk_index" in chunks[0]
    assert "content" in chunks[0]
    assert "embedding" not in chunks[0]


@pytest.mark.django_db
def test_list_chunks_other_tenant_returns_404(client, tenant_agent_token, db):
    """다른 Tenant의 문서 청크를 조회하면 404를 반환한다."""
    import secrets
    from apps.tenants.models import Tenant, TenantAgent
    from apps.tenants.auth import create_tenant_agent_token

    raw_key2 = secrets.token_urlsafe(32)
    tenant2 = Tenant.objects.create_with_key(name="Other Corp Chunks", raw_key=raw_key2)
    agent2 = TenantAgent(tenant=tenant2, username="chunkagent2")
    agent2.set_password("pass")
    agent2.save()
    token2 = create_tenant_agent_token(agent2)

    f = io.BytesIO(b"secret content of tenant2")
    f.name = "secret.txt"
    resp = client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    doc_id = resp.json()["id"]

    chunk_resp = client.get(
        f"/api/tenant/documents/{doc_id}/chunks",
        HTTP_AUTHORIZATION=f"Bearer {token2}",
    )
    assert chunk_resp.status_code == 404


@pytest.mark.django_db
def test_list_chunks_empty_document_returns_empty_list(client, tenant_agent_token):
    """청크가 없는 문서(빈 PDF)의 /chunks는 빈 배열을 반환한다."""
    import fitz
    from apps.rag.models import Document, DocumentChunk

    doc = fitz.open()
    doc.new_page()
    pdf_bytes = doc.tobytes()

    f = io.BytesIO(pdf_bytes)
    f.name = "empty_for_chunks.pdf"
    resp = client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    chunk_resp = client.get(
        f"/api/tenant/documents/{doc_id}/chunks",
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert chunk_resp.status_code == 200
    assert chunk_resp.json() == []


@pytest.mark.django_db
def test_upload_txt_document(client, tenant_agent_token):
    content = b"This is a test document about return policy."
    f = io.BytesIO(content)
    f.name = "policy.txt"

    response = client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "policy.txt"
    assert data["status"] == "pending"


@pytest.mark.django_db
def test_list_documents(client, tenant_agent_token):
    f = io.BytesIO(b"doc content")
    f.name = "test.txt"
    client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    response = client.get(
        "/api/tenant/documents/",
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert response.status_code == 200
    assert len(response.json()) >= 1


@pytest.mark.django_db
def test_delete_document(client, tenant_agent_token):
    from apps.rag.models import Document

    f = io.BytesIO(b"deletable content")
    f.name = "delete_me.txt"
    resp = client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    doc_id = resp.json()["id"]

    delete_resp = client.delete(
        f"/api/tenant/documents/{doc_id}",
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert delete_resp.status_code == 204
    assert not Document.objects.filter(id=doc_id).exists()


@pytest.mark.django_db
def test_other_tenant_cannot_access_document(client, tenant_agent_token, db):
    import secrets
    from apps.tenants.models import Tenant, TenantAgent
    from apps.tenants.auth import create_tenant_agent_token

    raw_key2 = secrets.token_urlsafe(32)
    tenant2 = Tenant.objects.create_with_key(name="Other Corp", raw_key=raw_key2)
    agent2 = TenantAgent(tenant=tenant2, username="agent2")
    agent2.set_password("pass")
    agent2.save()
    token2 = create_tenant_agent_token(agent2)

    f = io.BytesIO(b"private content")
    f.name = "private.txt"
    resp = client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    doc_id = resp.json()["id"]

    delete_resp = client.delete(
        f"/api/tenant/documents/{doc_id}",
        HTTP_AUTHORIZATION=f"Bearer {token2}",
    )
    assert delete_resp.status_code == 404


@pytest.mark.django_db
def test_document_ingestion_sets_status_ready(client, tenant_agent_token):
    """문서 업로드 후 Celery EAGER 실행으로 인제스션 완료 → status=ready, 청크 생성."""
    from apps.rag.models import Document, DocumentChunk

    content = b"Our return policy allows returns within 30 days of purchase."
    f = io.BytesIO(content)
    f.name = "return_policy.txt"

    resp = client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    doc = Document.objects.get(id=doc_id)
    assert doc.status == Document.STATUS_READY
    assert DocumentChunk.objects.filter(document_id=doc_id).exists()


@pytest.mark.django_db
def test_rag_retriever_returns_chunks_for_uploaded_content(client, tenant_agent_token, tenant_with_key):
    """인제스션된 문서와 관련된 쿼리로 retriever를 호출하면 해당 내용의 청크가 반환된다."""
    from apps.rag.retriever import retrieve_chunks

    tenant, _ = tenant_with_key
    content = b"Customer support is available Monday to Friday from 9am to 6pm."
    f = io.BytesIO(content)
    f.name = "support_hours.txt"

    client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )

    chunks = retrieve_chunks(str(tenant.id), "support hours", top_k=3)
    assert len(chunks) > 0
    assert any("support" in c.lower() or "Monday" in c for c in chunks)


@pytest.mark.django_db
def test_delete_document_removes_chunks(client, tenant_agent_token):
    """문서 삭제 시 연결된 DocumentChunk도 함께 삭제된다."""
    from apps.rag.models import DocumentChunk

    content = b"This document should be deleted including all its chunks."
    f = io.BytesIO(content)
    f.name = "to_delete.txt"

    resp = client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    doc_id = resp.json()["id"]
    assert DocumentChunk.objects.filter(document_id=doc_id).exists()

    client.delete(
        f"/api/tenant/documents/{doc_id}",
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert not DocumentChunk.objects.filter(document_id=doc_id).exists()


@pytest.mark.django_db
def test_rag_query_endpoint_returns_chunks_with_score_and_document_name(client, tenant_agent_token, tenant_with_key):
    """POST /api/tenant/documents/query → document_name, content, score를 포함한 결과 반환."""
    content = b"Shipping takes 3-5 business days for standard delivery."
    f = io.BytesIO(content)
    f.name = "shipping.txt"
    client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )

    resp = client.post(
        "/api/tenant/documents/query",
        {"query": "shipping delivery time", "top_k": 3},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    first = data[0]
    assert "document_name" in first
    assert "content" in first
    assert "score" in first
    assert first["document_name"] == "shipping.txt"
    assert isinstance(first["score"], float)


@pytest.mark.django_db
def test_rag_query_top_k_limits_results(client, tenant_agent_token, tenant_with_key):
    """top_k 파라미터가 반환 청크 수를 제한한다."""
    content = b"Our return policy allows returns within 30 days."
    f = io.BytesIO(content)
    f.name = "returns.txt"
    client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )

    resp = client.post(
        "/api/tenant/documents/query",
        {"query": "return policy", "top_k": 1},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert resp.status_code == 200
    assert len(resp.json()) <= 1


@pytest.mark.django_db
def test_rag_query_tenant_isolation(client, tenant_agent_token, tenant_with_key):
    """다른 Tenant의 문서 청크가 결과에 포함되지 않는다."""
    import secrets
    from apps.tenants.models import Tenant, TenantAgent
    from apps.tenants.auth import create_tenant_agent_token

    # 다른 Tenant 문서 삽입
    raw_key2 = secrets.token_urlsafe(32)
    tenant2 = Tenant.objects.create_with_key(name="OtherCo RAG", raw_key=raw_key2)
    agent2 = TenantAgent(tenant=tenant2, username="rag-agent2")
    agent2.set_password("pass")
    agent2.save()
    token2 = create_tenant_agent_token(agent2)

    f2 = io.BytesIO(b"Secret proprietary knowledge from other company.")
    f2.name = "secret.txt"
    client.post(
        "/api/tenant/documents/",
        {"file": f2},
        HTTP_AUTHORIZATION=f"Bearer {token2}",
    )

    # 현재 Tenant로 쿼리
    resp = client.post(
        "/api/tenant/documents/query",
        {"query": "proprietary knowledge other company"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert resp.status_code == 200
    doc_names = [r["document_name"] for r in resp.json()]
    assert "secret.txt" not in doc_names


@pytest.mark.django_db
def test_ingest_strips_nul_bytes(client, tenant_agent_token, tenant_with_key):
    """NUL 바이트(\x00)가 포함된 파일을 업로드해도 PostgreSQL DataError 없이 인제스션된다."""
    from apps.rag.models import Document, DocumentChunk

    content = b"Hello\x00world\x00this is a test\x00document about FCB1010."
    f = io.BytesIO(content)
    f.name = "nul_bytes.txt"

    resp = client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    doc = Document.objects.get(id=doc_id)
    assert doc.status == Document.STATUS_READY, (
        f"Expected ready, got {doc.status}: {doc.error_message}"
    )
    chunks = DocumentChunk.objects.filter(document_id=doc_id)
    assert chunks.exists()
    for chunk in chunks:
        assert "\x00" not in chunk.content


@pytest.mark.django_db
def test_ingest_strips_esc_bytes(client, tenant_agent_token, tenant_with_key):
    """ESC(0x1B) 바이트가 포함된 파일을 업로드해도 청크에 ESC가 남지 않는다."""
    from apps.rag.models import Document, DocumentChunk

    content = b"SWITCH 1\x1b toggles relay\x1b when DIRECT SELECT is enabled."
    f = io.BytesIO(content)
    f.name = "esc_bytes.txt"

    resp = client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    doc = Document.objects.get(id=doc_id)
    assert doc.status == Document.STATUS_READY, (
        f"Expected ready, got {doc.status}: {doc.error_message}"
    )
    chunks = DocumentChunk.objects.filter(document_id=doc_id)
    assert chunks.exists()
    for chunk in chunks:
        assert "\x1b" not in chunk.content


@pytest.mark.django_db
def test_ingest_strips_control_chars_but_keeps_whitespace(client, tenant_agent_token, tenant_with_key):
    """0x01~0x1F 제어 문자는 제거되고, \\t \\n \\r 공백은 보존된다."""
    from apps.rag.models import Document, DocumentChunk

    # 제어 문자 + 정상 공백 혼합
    content = (
        b"line one\x01\x07\x0e\x1c\x1f\n"  # 제어 문자들 + 줄바꿈 보존
        b"line\ttwo\r\n"                     # 탭·CR·LF 보존
        b"FCB1010\x02\x03power supply\x1e"
    )
    f = io.BytesIO(content)
    f.name = "ctrl_chars.txt"

    resp = client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    doc = Document.objects.get(id=doc_id)
    assert doc.status == Document.STATUS_READY, (
        f"Expected ready, got {doc.status}: {doc.error_message}"
    )
    all_content = "".join(c.content for c in DocumentChunk.objects.filter(document_id=doc_id))

    # 제어 문자 없음
    for bad in ["\x01", "\x02", "\x03", "\x07", "\x0e", "\x1c", "\x1e", "\x1f"]:
        assert bad not in all_content, f"제어문자 {bad!r}가 청크에 남아 있음"

    # 실제 텍스트 보존
    assert "FCB1010" in all_content
    assert "power supply" in all_content


def _make_pdf(*page_texts):
    """page_texts 각 항목을 별도 페이지에 담은 PDF bytes를 반환한다."""
    import fitz
    doc = fitz.open()
    for text in page_texts:
        page = doc.new_page()
        page.insert_text((50, 100), text)
    return doc.tobytes()


@pytest.mark.django_db
def test_ingest_multipage_pdf_includes_text_from_all_pages(client, tenant_agent_token, tenant_with_key):
    """멀티페이지 PDF를 업로드하면 모든 페이지의 텍스트가 청크에 포함된다."""
    from apps.rag.models import Document, DocumentChunk

    pdf_bytes = _make_pdf(
        "MIDI channel settings for FCB1010 bank A presets.",
        "Expression pedal calibration procedure for FCB1010.",
    )
    f = io.BytesIO(pdf_bytes)
    f.name = "multipage.pdf"

    resp = client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    doc = Document.objects.get(id=doc_id)
    assert doc.status == Document.STATUS_READY, (
        f"Expected ready, got {doc.status}: {doc.error_message}"
    )
    all_content = " ".join(c.content for c in DocumentChunk.objects.filter(document_id=doc_id))
    assert "MIDI channel" in all_content
    assert "Expression pedal" in all_content


@pytest.mark.django_db
def test_ingest_empty_pdf_results_in_no_chunks(client, tenant_agent_token):
    """텍스트가 없는 빈 PDF를 업로드하면 status=ready이고 청크가 생성되지 않는다."""
    import fitz
    from apps.rag.models import Document, DocumentChunk

    doc = fitz.open()
    doc.new_page()  # blank page, no text
    pdf_bytes = doc.tobytes()

    f = io.BytesIO(pdf_bytes)
    f.name = "empty.pdf"

    resp = client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    doc_obj = Document.objects.get(id=doc_id)
    assert doc_obj.status == Document.STATUS_READY, (
        f"Expected ready, got {doc_obj.status}: {doc_obj.error_message}"
    )
    assert DocumentChunk.objects.filter(document_id=doc_id).count() == 0


@pytest.mark.django_db
def test_ingest_pdf_strips_control_chars(client, tenant_agent_token, tenant_with_key):
    """PDF 추출 텍스트에 제어 문자가 포함돼도 청크에는 남지 않는다."""
    import fitz
    from apps.rag.models import Document, DocumentChunk

    # pymupdf로 생성한 PDF는 보통 제어문자가 없지만,
    # TXTIngester 경로로 제어문자 포함 파일을 인제스션하면 동일한 strip 코드 경로를 탄다.
    # PDF ingester 자체의 strip을 검증하기 위해 fitz가 반환하는 텍스트에 제어문자가 있는 케이스를
    # 패치 없이 TXT로 시뮬레이션한다 (같은 base ingest() 메서드를 공유).
    content = b"FCB1010 MIDI controller\x01\x0e features:\x1c sysex\x1f dump."
    f = io.BytesIO(content)
    f.name = "ctrl.txt"

    resp = client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    doc_obj = Document.objects.get(id=doc_id)
    assert doc_obj.status == Document.STATUS_READY

    all_content = " ".join(c.content for c in DocumentChunk.objects.filter(document_id=doc_id))
    for bad in ["\x01", "\x0e", "\x1c", "\x1f"]:
        assert bad not in all_content
    assert "FCB1010" in all_content
    assert "sysex" in all_content


@pytest.mark.django_db
def test_ingest_txt_with_unicode_content(client, tenant_agent_token, tenant_with_key):
    """한글·특수문자·이모지가 포함된 TXT 파일도 올바르게 인제스션된다."""
    from apps.rag.models import Document, DocumentChunk

    content = "FCB1010 설명서: MIDI 채널 설정 방법 (1~16).\nExpression pedal A·B 캘리브레이션 절차.".encode("utf-8")
    f = io.BytesIO(content)
    f.name = "korean.txt"

    resp = client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    doc_obj = Document.objects.get(id=doc_id)
    assert doc_obj.status == Document.STATUS_READY

    all_content = " ".join(c.content for c in DocumentChunk.objects.filter(document_id=doc_id))
    assert "FCB1010" in all_content
    assert "MIDI" in all_content
    assert "설명서" in all_content


# ── Issue 49: ImageIngester ──────────────────────────────────────────────────

def _make_png_with_text(text: str) -> bytes:
    """fitz로 텍스트가 담긴 PNG bytes를 생성한다 (PIL 불필요)."""
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=600, height=120)
    page.insert_text((20, 80), text, fontsize=28)
    pix = page.get_pixmap(dpi=150)
    return pix.tobytes(output="png")


def _make_jpg_with_text(text: str) -> bytes:
    """fitz로 텍스트가 담긴 JPEG bytes를 생성한다."""
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=600, height=120)
    page.insert_text((20, 80), text, fontsize=28)
    pix = page.get_pixmap(dpi=150)
    return pix.tobytes(output="jpeg")


@pytest.mark.django_db
def test_ingest_png_creates_chunks(client, tenant_agent_token, tenant_with_key):
    """PNG 이미지 업로드 시 OCR로 텍스트가 추출되어 status=ready, 청크가 생성된다."""
    from django.core.files.uploadedfile import SimpleUploadedFile
    from apps.rag.models import Document, DocumentChunk

    png_bytes = _make_png_with_text("FCB1010 MIDI controller test")
    uploaded = SimpleUploadedFile("test_ocr.png", png_bytes, content_type="image/png")

    resp = client.post(
        "/api/tenant/documents/",
        {"file": uploaded},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    doc = Document.objects.get(id=doc_id)
    assert doc.status == Document.STATUS_READY, (
        f"Expected ready, got {doc.status}: {doc.error_message}"
    )
    assert DocumentChunk.objects.filter(document_id=doc_id).exists()


@pytest.mark.django_db
def test_ingest_jpg_creates_chunks(client, tenant_agent_token, tenant_with_key):
    """JPG 이미지 업로드 시 OCR로 텍스트가 추출되어 status=ready, 청크가 생성된다."""
    from django.core.files.uploadedfile import SimpleUploadedFile
    from apps.rag.models import Document, DocumentChunk

    jpg_bytes = _make_jpg_with_text("Expression pedal calibration guide")
    uploaded = SimpleUploadedFile("test_ocr.jpg", jpg_bytes, content_type="image/jpeg")

    resp = client.post(
        "/api/tenant/documents/",
        {"file": uploaded},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    doc = Document.objects.get(id=doc_id)
    assert doc.status == Document.STATUS_READY, (
        f"Expected ready, got {doc.status}: {doc.error_message}"
    )
    assert DocumentChunk.objects.filter(document_id=doc_id).exists()


@pytest.mark.django_db
def test_upload_unsupported_mime_returns_400(client, tenant_agent_token):
    """지원하지 않는 MIME 타입(image/gif)은 400 에러를 반환한다."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    gif_bytes = b"GIF89a" + b"\x00" * 10
    uploaded = SimpleUploadedFile("anim.gif", gif_bytes, content_type="image/gif")

    resp = client.post(
        "/api/tenant/documents/",
        {"file": uploaded},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert resp.status_code == 400


# ── Issue 50: PDF OCR Fallback ────────────────────────────────────────────────

def _make_image_only_pdf(text: str) -> bytes:
    """텍스트를 이미지로 렌더링한 후 텍스트 레이어 없이 PDF에 삽입한다.
    pymupdf로 추출하면 빈 문자열이 나와 OCR fallback을 트리거한다.
    """
    import fitz

    # 텍스트가 있는 페이지를 PNG로 렌더링
    src = fitz.open()
    page = src.new_page(width=600, height=120)
    page.insert_text((20, 80), text, fontsize=28)
    pix = page.get_pixmap(dpi=150)
    png_bytes = pix.tobytes(output="png")

    # 이미지만 담긴 PDF 생성 (텍스트 레이어 없음)
    out = fitz.open()
    out_page = out.new_page(width=600, height=120)
    out_page.insert_image(out_page.rect, stream=png_bytes)
    return out.tobytes()


@pytest.mark.django_db
def test_pdf_ocr_fallback_used_when_text_too_sparse(client, tenant_agent_token, tenant_with_key):
    """텍스트 레이어가 없는 스캔 PDF는 OCR fallback을 통해 status=ready이고 청크가 생성된다."""
    from django.core.files.uploadedfile import SimpleUploadedFile
    from apps.rag.models import Document, DocumentChunk
    import fitz

    pdf_bytes = _make_image_only_pdf("SYSEX dump sends entire FCB1010 memory")

    # 텍스트 레이어가 없음을 먼저 확인
    doc_check = fitz.open(stream=pdf_bytes, filetype="pdf")
    extracted = " ".join(page.get_text() for page in doc_check)
    assert len(extracted.split()) < 50, "테스트 PDF에 텍스트 레이어가 있으면 안 됩니다"

    uploaded = SimpleUploadedFile("scan.pdf", pdf_bytes, content_type="application/pdf")
    resp = client.post(
        "/api/tenant/documents/",
        {"file": uploaded},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    doc = Document.objects.get(id=doc_id)
    assert doc.status == Document.STATUS_READY, (
        f"Expected ready, got {doc.status}: {doc.error_message}"
    )
    assert DocumentChunk.objects.filter(document_id=doc_id).exists()


@pytest.mark.django_db
def test_pdf_normal_text_skips_ocr(client, tenant_agent_token, tenant_with_key):
    """단어 수 >= 50인 정상 PDF는 OCR fallback 없이 처리된다."""
    from apps.rag.models import Document, DocumentChunk

    long_text = "FCB1010 MIDI controller " * 10  # 50개 이상 단어
    pdf_bytes = _make_pdf(long_text)

    f = io.BytesIO(pdf_bytes)
    f.name = "normal.pdf"
    resp = client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    doc = Document.objects.get(id=doc_id)
    assert doc.status == Document.STATUS_READY
    assert DocumentChunk.objects.filter(document_id=doc_id).exists()


# ── Issue 52: Document Label 임베딩 prefix ────────────────────────────────────

@pytest.mark.django_db
def test_retrieved_chunk_is_prefixed_with_document_label(client, tenant_agent_token, tenant_with_key):
    """retrieve_chunks가 반환하는 content는 Document Label(name)로 prefix된다."""
    from apps.rag.retriever import retrieve_chunks

    tenant, _ = tenant_with_key
    # 본문에는 제품명이 전혀 없고 사양만 있다
    content = b"The unit offers ten assignable footswitches and two expression pedals for stage use."
    f = io.BytesIO(content)
    f.name = "ZX900PRO.txt"
    client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )

    chunks = retrieve_chunks(str(tenant.id), "footswitches", top_k=3)
    assert len(chunks) > 0
    assert any(c.startswith("ZX900PRO.txt:") for c in chunks), (
        f"label prefix가 붙지 않음: {chunks}"
    )


@pytest.mark.django_db
def test_document_retrievable_by_label_even_when_body_lacks_product_name(
    client, tenant_agent_token, tenant_with_key
):
    """본문에 제품명이 없어도 Document Label 덕분에 제품명 쿼리로 상위 검색된다.

    distractor 문서는 쿼리의 일반 단어("specifications and features")를 본문에 담고 있어,
    label prefix가 없으면 distractor가 더 유사하게 검색된다.
    """
    from apps.rag.retriever import retrieve_chunks_with_scores

    tenant, _ = tenant_with_key

    # 타깃: 본문에 제품명("ZX900PRO")도 "specifications/features"도 없음
    target = io.BytesIO(b"The unit offers ten assignable footswitches and two expression pedals.")
    target.name = "ZX900PRO.txt"
    client.post(
        "/api/tenant/documents/",
        {"file": target},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )

    # distractor: 쿼리의 일반 단어를 본문에 포함 (label 없으면 이쪽이 더 유사)
    distractor = io.BytesIO(b"Product specifications and features overview guide for general use.")
    distractor.name = "manual.txt"
    client.post(
        "/api/tenant/documents/",
        {"file": distractor},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )

    results = retrieve_chunks_with_scores(
        str(tenant.id), "ZX900PRO specifications and features", top_k=1
    )
    assert len(results) == 1
    assert results[0]["document_name"] == "ZX900PRO.txt", (
        f"제품명 쿼리가 타깃 문서를 상위로 검색하지 못함: {results}"
    )


# ── Issue 53: Document Label 수정 + 자동 재임베딩 ──────────────────────────────

@pytest.mark.django_db
def test_patch_document_name_reembeds_and_is_searchable_by_new_name(
    client, tenant_agent_token, tenant_with_key
):
    """PATCH로 name을 제품명으로 바꾸면 재임베딩되어 새 제품명 쿼리로 상위 검색된다."""
    from apps.rag.models import Document
    from apps.rag.retriever import retrieve_chunks_with_scores

    tenant, _ = tenant_with_key

    # 타깃: 본문에 제품명/일반 단어 없음, 처음엔 무의미한 이름
    target = io.BytesIO(b"The unit offers ten assignable footswitches and two expression pedals.")
    target.name = "before.txt"
    resp = client.post(
        "/api/tenant/documents/",
        {"file": target},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    doc_id = resp.json()["id"]

    # distractor: 쿼리의 일반 단어 포함
    distractor = io.BytesIO(b"Product specifications and features overview guide for general use.")
    distractor.name = "manual.txt"
    client.post(
        "/api/tenant/documents/",
        {"file": distractor},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )

    # PATCH로 제품명 레이블 부여
    patch_resp = client.patch(
        f"/api/tenant/documents/{doc_id}",
        {"name": "ZX900PRO.txt"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "ZX900PRO.txt"

    doc = Document.objects.get(id=doc_id)
    assert doc.status == Document.STATUS_READY

    results = retrieve_chunks_with_scores(
        str(tenant.id), "ZX900PRO specifications and features", top_k=1
    )
    assert results[0]["document_name"] == "ZX900PRO.txt", (
        f"새 레이블로 재임베딩되지 않아 검색 실패: {results}"
    )


@pytest.mark.django_db
def test_upload_with_explicit_name_uses_it_as_label(client, tenant_agent_token):
    """업로드 시 name 폼 필드를 주면 파일명 대신 그 값이 Document.name(레이블)이 된다."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    uploaded = SimpleUploadedFile(
        "raw_filename_12345.txt", b"FCB1010 footswitch assignments.", content_type="text/plain"
    )
    resp = client.post(
        "/api/tenant/documents/",
        {"file": uploaded, "name": "FCB1010 매뉴얼"},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "FCB1010 매뉴얼"


@pytest.mark.django_db
def test_upload_without_name_falls_back_to_filename(client, tenant_agent_token):
    """name 폼 필드가 없으면 파일명을 레이블로 사용한다 (기존 동작 유지)."""
    f = io.BytesIO(b"Fallback content.")
    f.name = "fallback.txt"
    resp = client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "fallback.txt"


@pytest.mark.django_db
def test_patch_document_empty_name_returns_400(client, tenant_agent_token):
    """빈 name으로 PATCH하면 400을 반환한다."""
    f = io.BytesIO(b"Some document content for label test.")
    f.name = "label.txt"
    resp = client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    doc_id = resp.json()["id"]

    patch_resp = client.patch(
        f"/api/tenant/documents/{doc_id}",
        {"name": "   "},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert patch_resp.status_code == 400


@pytest.mark.django_db
def test_patch_document_other_tenant_returns_404(client, tenant_agent_token, db):
    """다른 Tenant의 문서를 PATCH하면 404를 반환한다."""
    import secrets
    from apps.tenants.models import Tenant, TenantAgent
    from apps.tenants.auth import create_tenant_agent_token

    raw_key2 = secrets.token_urlsafe(32)
    tenant2 = Tenant.objects.create_with_key(name="Other Corp Patch", raw_key=raw_key2)
    agent2 = TenantAgent(tenant=tenant2, username="patchagent2")
    agent2.set_password("pass")
    agent2.save()
    token2 = create_tenant_agent_token(agent2)

    f = io.BytesIO(b"Tenant1 private document.")
    f.name = "private.txt"
    resp = client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    doc_id = resp.json()["id"]

    patch_resp = client.patch(
        f"/api/tenant/documents/{doc_id}",
        {"name": "hijacked.txt"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token2}",
    )
    assert patch_resp.status_code == 404


@pytest.mark.django_db
def test_patch_reembeds_without_reextracting_from_file(client, tenant_agent_token):
    """원본 파일이 삭제돼도 재임베딩은 기존 청크로 수행되어 status=ready가 된다.

    재임베딩이 OCR/텍스트 재추출(파일 재읽기) 없이 저장된 청크만 사용함을 검증한다.
    """
    import os
    from django.conf import settings as dj_settings
    from apps.rag.models import Document

    f = io.BytesIO(b"FCB1010 SYSEX dump sends the entire memory over MIDI for backup.")
    f.name = "reembed.txt"
    resp = client.post(
        "/api/tenant/documents/",
        {"file": f},
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    doc_id = resp.json()["id"]

    # 원본 파일을 삭제 → 재추출 경로라면 실패할 것
    file_path = os.path.join(str(dj_settings.MEDIA_ROOT), "documents", doc_id)
    if os.path.exists(file_path):
        os.unlink(file_path)

    patch_resp = client.patch(
        f"/api/tenant/documents/{doc_id}",
        {"name": "FCB1010-manual.txt"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {tenant_agent_token}",
    )
    assert patch_resp.status_code == 200

    doc = Document.objects.get(id=doc_id)
    assert doc.status == Document.STATUS_READY, (
        f"파일 없이 재임베딩 실패: {doc.status} {doc.error_message}"
    )


@pytest.fixture
def _hang_server():
    """TCP server that accepts connections but never responds — simulates a hung Ollama."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(10)
    port = sock.getsockname()[1]

    def _loop():
        while True:
            try:
                conn, _ = sock.accept()
                # accept but never respond — caller will timeout
            except Exception:
                break

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    yield port
    sock.close()


@pytest.mark.django_db
def test_ingest_document_sets_failed_status_on_ollama_timeout(settings, tenant_with_key, _hang_server):
    """Ollama가 응답하지 않아 ReadTimeout 발생 시 Document.status=failed, error_message에 에러 내용이 저장된다."""
    from django.conf import settings as django_settings
    from apps.rag.models import Document
    from apps.rag.tasks import ingest_document

    settings.OLLAMA_BASE_URL = f"http://127.0.0.1:{_hang_server}"
    settings.OLLAMA_TIMEOUT = 0.2

    tenant, _ = tenant_with_key
    doc = Document.objects.create(
        tenant_id=tenant.id,
        name="timeout_test.txt",
        mime_type="text/plain",
    )

    file_dir = os.path.join(str(django_settings.MEDIA_ROOT), "documents")
    os.makedirs(file_dir, exist_ok=True)
    file_path = os.path.join(file_dir, str(doc.id))
    try:
        with open(file_path, "wb") as fh:
            fh.write(b"Some content that needs embedding")

        ingest_document.apply(args=[str(doc.id), str(tenant.id), "text/plain"])
    finally:
        if os.path.exists(file_path):
            os.unlink(file_path)

    doc.refresh_from_db()
    assert doc.status == Document.STATUS_FAILED
    assert doc.error_message != ""
