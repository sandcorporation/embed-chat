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

    file_path = os.path.join(settings.MEDIA_ROOT, "documents", document_id)
    with open(file_path, "rb") as f:
        file_bytes = f.read()

    ingester = get_ingester(mime_type)
    ingester.ingest(file_bytes, tenant_id, document_id)


@app.task(
    bind=True,
    max_retries=3,
    autoretry_for=(httpx.ReadTimeout, httpx.ConnectError),
    default_retry_delay=60,
)
def reembed_document(self, document_id: str):
    from apps.rag.ingesters import reembed_document_chunks

    reembed_document_chunks(document_id)
