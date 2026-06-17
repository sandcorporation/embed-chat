import os
import uuid
from typing import List
from ninja import Router, Schema, File, Form, UploadedFile
from ninja.errors import HttpError
from django.conf import settings
from django.shortcuts import get_object_or_404
from apps.tenants.auth import tenant_agent_auth
from apps.rag.models import Document, DocumentChunk
from apps.rag.ingesters import MIME_TO_INGESTER

rag_router = Router(tags=["rag"], auth=tenant_agent_auth)


class DocumentOut(Schema):
    id: str
    name: str
    status: str
    error_message: str


@rag_router.post("/", response={201: DocumentOut})
def upload_document(request, file: UploadedFile = File(...), name: str = Form(None)):
    tenant = request.auth.tenant
    mime_type = file.content_type or "text/plain"

    if mime_type not in MIME_TO_INGESTER:
        raise HttpError(400, f"Unsupported file type: {mime_type}")

    label = (name or "").strip() or file.name
    doc = Document.objects.create(
        tenant_id=tenant.id,
        name=label,
        mime_type=mime_type,
    )

    os.makedirs(os.path.join(settings.MEDIA_ROOT, "documents"), exist_ok=True)
    file_path = os.path.join(settings.MEDIA_ROOT, "documents", str(doc.id))
    with open(file_path, "wb") as f:
        for chunk in file.chunks():
            f.write(chunk)

    from apps.rag.tasks import ingest_document
    ingest_document.delay(str(doc.id), str(tenant.id), mime_type)

    return 201, {
        "id": str(doc.id),
        "name": doc.name,
        "status": doc.status,
        "error_message": doc.error_message,
    }


@rag_router.get("/", response=List[DocumentOut])
def list_documents(request):
    tenant = request.auth.tenant
    docs = Document.objects.filter(tenant_id=tenant.id)
    return [
        {"id": str(d.id), "name": d.name, "status": d.status, "error_message": d.error_message}
        for d in docs
    ]


class QueryIn(Schema):
    query: str
    top_k: int = 5


@rag_router.post("/query", response=list)
def query_rag(request, body: QueryIn):
    from apps.rag.retriever import retrieve_chunks_with_scores

    tenant = request.auth.tenant
    return retrieve_chunks_with_scores(str(tenant.id), body.query, body.top_k)


class DocumentPatchIn(Schema):
    name: str


@rag_router.patch("/{document_id}", response=DocumentOut)
def update_document(request, document_id: str, body: DocumentPatchIn):
    tenant = request.auth.tenant
    doc = get_object_or_404(Document, id=document_id, tenant_id=tenant.id)

    name = body.name.strip()
    if not name:
        raise HttpError(400, "name must not be empty")

    doc.name = name
    doc.status = Document.STATUS_PENDING
    doc.error_message = ""
    doc.save()

    from apps.rag.tasks import reembed_document
    reembed_document.delay(str(doc.id))

    doc.refresh_from_db()
    return {
        "id": str(doc.id),
        "name": doc.name,
        "status": doc.status,
        "error_message": doc.error_message,
    }


@rag_router.delete("/{document_id}", response={204: None})
def delete_document(request, document_id: str):
    tenant = request.auth.tenant
    doc = get_object_or_404(Document, id=document_id, tenant_id=tenant.id)
    doc.chunks.all().delete()
    doc.delete()
    return 204, None


class ChunkOut(Schema):
    chunk_index: int
    content: str


@rag_router.get("/{document_id}/chunks", response=List[ChunkOut])
def list_chunks(request, document_id: str):
    tenant = request.auth.tenant
    get_object_or_404(Document, id=document_id, tenant_id=tenant.id)
    chunks = DocumentChunk.objects.filter(
        document_id=document_id, tenant_id=tenant.id
    ).order_by("chunk_index")
    return [{"chunk_index": c.chunk_index, "content": c.content} for c in chunks]
