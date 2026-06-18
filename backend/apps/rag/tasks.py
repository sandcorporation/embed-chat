import httpx

from config.celery import app


@app.task(
    bind=True,
    max_retries=3,
    autoretry_for=(httpx.ReadTimeout, httpx.ConnectError),
    default_retry_delay=60,
)
def ingest_document(self, document_id: str, tenant_id: str, mime_type: str):
    import os
    from django.conf import settings
    from apps.rag.ingesters import get_ingester
    from apps.rag.models import Document
    from apps.rag.graph_ingester import ingest_to_graph

    # GraphRAG 단일 인제스션: 텍스트 추출 → Knowledge Graph 구축 (벡터 청크 없음)
    doc = Document.objects.get(id=document_id)
    doc.status = Document.STATUS_PROCESSING
    doc.save()
    try:
        if doc.source_type == Document.SOURCE_URL:
            from apps.rag.web import fetch_html, extract_main_content, extract_title
            html = fetch_html(doc.source_url)
            text = extract_main_content(html)
            # Document Label 기본값: 페이지 title (없으면 URL 유지)
            if doc.name == doc.source_url:
                title = extract_title(html)
                if title:
                    doc.name = title
        else:
            file_path = os.path.join(settings.MEDIA_ROOT, "documents", document_id)
            with open(file_path, "rb") as f:
                file_bytes = f.read()
            text = get_ingester(mime_type).extract_text(file_bytes)
        ingest_to_graph(text, tenant_id, document_id, doc.name)
        doc.status = Document.STATUS_READY
        doc.save()
    except Exception as e:
        doc.status = Document.STATUS_FAILED
        doc.error_message = str(e)
        doc.save()
        raise


@app.task(
    bind=True,
    max_retries=3,
    autoretry_for=(httpx.ReadTimeout, httpx.ConnectError),
    default_retry_delay=60,
)
def rebuild_graph_communities(self, tenant_id: str):
    from apps.rag.community_builder import rebuild_communities

    rebuild_communities(tenant_id)
