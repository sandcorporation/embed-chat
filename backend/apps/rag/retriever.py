from typing import List


def retrieve_chunks(tenant_id: str, query: str, top_k: int = 5) -> List[str]:
    from apps.rag.models import DocumentChunk
    from apps.rag.ingesters import get_embeddings
    from pgvector.django import L2Distance

    query_embedding = get_embeddings([query])[0]

    chunks = (
        DocumentChunk.objects.select_related("document")
        .filter(tenant_id=tenant_id)
        .order_by(L2Distance("embedding", query_embedding))[:top_k]
    )
    return [f"{chunk.document.name}: {chunk.content}" for chunk in chunks]


def retrieve_chunks_with_scores(tenant_id: str, query: str, top_k: int = 5) -> List[dict]:
    from apps.rag.models import DocumentChunk
    from apps.rag.ingesters import get_embeddings
    from pgvector.django import L2Distance

    query_embedding = get_embeddings([query])[0]

    chunks = (
        DocumentChunk.objects.select_related("document")
        .filter(tenant_id=tenant_id)
        .annotate(score=L2Distance("embedding", query_embedding))
        .order_by("score")[:top_k]
    )
    return [
        {
            "document_name": chunk.document.name,
            "content": chunk.content,
            "score": float(chunk.score),
        }
        for chunk in chunks
    ]
