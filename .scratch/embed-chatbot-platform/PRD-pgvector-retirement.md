Status: ready-for-agent

# PRD: pgvector/DocumentChunk 완전 제거 (GraphRAG 컷오버 마무리)

## Problem Statement

GraphRAG 전환(issues 60–66) 후 검색 표면은 그래프로 컷오버됐지만, 전환기 안정성을 위해 인제스션이 여전히 **벡터 청크(DocumentChunk)와 그래프를 dual-write**한다. 그 결과 (1) 쓰이지 않는 pgvector 청크가 계속 쌓이고, (2) Document Label의 "청크 임베딩 prefix + 재임베딩" 등 죽은 코드가 남아 있으며, (3) 청크 인스펙터가 여전히 옛 DocumentChunk를 본다. 코드/스토리지가 이중 진실을 갖는 혼란 상태다.

## Solution

벡터 청크 경로를 완전히 제거하고 그래프를 단일 진실로 만든다. 청크 인스펙터는 그래프의 Text Unit을 보여주고, 인제스션은 그래프만 구축하며, DocumentChunk 모델·옛 retriever·재임베딩 코드는 삭제한다. Tenant 입장에서 동작은 동일하되(업로드/검색/청크 보기/레이블 수정), 내부는 그래프 하나로 단순해진다.

## User Stories

1. As a TenantAgent, I want "청크 보기" to show the graph's Text Units for a document, so that the inspector reflects the actual knowledge source.
2. As a TenantAgent, I want uploading to build only the Knowledge Graph (no redundant vector chunks), so that storage isn't duplicated.
3. As a TenantAgent, I want editing a Document Label to rename it and refresh its graph entity (no re-embedding), so that renames stay cheap and consistent with GraphRAG.
4. As a TenantAgent, I want document status (pending/processing/ready/failed) to still reflect graph ingestion, so that progress is visible.
5. As a developer, I want DocumentChunk, the old pgvector retriever, and re-embedding code removed, so that there is one retrieval path.
6. As a developer, I want the unused pgvector dependency/usage removed, so that the stack reflects the Neo4j decision (ADR-0007).
7. As a developer, I want the vector-era tests rewritten on the graph basis (or removed if obsolete), so that the suite tests real behavior.
8. As a Visitor, I want chat answers to remain correct after the cleanup, so that retrieval behavior is unchanged.

## Implementation Decisions

### 청크 인스펙터 → Text Unit (issue 67)

`/documents/{id}/chunks` 엔드포인트를 GraphStore의 Text Unit 조회로 전환한다. GraphStore에 `query_text_units(document_id)`(tenant 스코프)를 추가. 반환은 기존 인스펙터 UI 계약(`chunk_index`/`content` 유사) 유지 — DocumentsTab "청크 보기" UI는 그대로 동작. 빈 문서는 빈 배열.

### 그래프 단일 인제스션 (issue 68)

`ingest_document`가 벡터 청크를 만들지 않고 그래프만 구축하도록 전환. 텍스트 추출(PDF/OCR/이미지)은 유지하되, 추출 후 곧장 `ingest_to_graph`로 가고 `Document.status`(processing→ready/failed)는 그래프 인제스션 경로가 소유한다. `DocumentIngester`는 텍스트 추출 책임만 남기고 청크 생성/임베딩 로직 제거.

Document Label 수정(PATCH name): 청크 재임베딩 대신 **이름 변경 + 대표 Entity 재시드 + Graph Freshness stale**. `reembed_document` 태스크와 청크 재임베딩 함수 제거.

### 제거 (issue 69)

- `DocumentChunk` 모델 + `document_chunks` 테이블(마이그레이션으로 삭제).
- 옛 `retriever`(retrieve_chunks/retrieve_chunks_with_scores) 제거.
- 재임베딩 잔여 코드 제거.
- RAG 용도로 더 이상 쓰이지 않는 pgvector 의존성/`VectorField` 사용 제거(임베딩은 Neo4j 벡터 인덱스). DB 이미지(pgvector/pgvector:pg16)는 그대로 둬도 무방하나 RAG에서 미사용.

### 테스트 마이그레이션 (issue 69)

벡터 시대 테스트(청크 생성/조회, retriever, 재임베딩, Document Label prefix 검색)를 그래프 기준으로 재작성하거나 폐기. 인제스션은 "업로드 → 그래프 Entity/Text Unit 생성 + status ready"로, 검색은 그래프 기준으로 검증.

## Testing Decisions

좋은 테스트는 내부 저장 방식이 아니라 외부 동작을 검증한다: 업로드 후 청크 보기가 Text Unit을 보여주는가, 검색이 그래프로 동작하는가, 레이블 수정이 이름/엔티티를 갱신하고 stale로 만드는가, status가 올바른가.

- Neo4j·임베딩은 실제 객체(결정적), LLM(추출/요약/scope)은 `apps/agent/llm` 경계 Fake(CI). bring-up 필요 시 실제 OpenRouter.
- 검증 대상: 청크 인스펙터(그래프 Text Unit), 그래프 단일 인제스션 status, 레이블 수정 동작, 제거 후 회귀(chat/검색/인스펙터).
- Prior art: `tests/test_graph_store.py`, `tests/test_graph_search.py`, `tests/test_graph_community.py`, 그리고 폐기/이전 대상인 `tests/test_rag.py`.

## Out of Scope

- GraphRAG 검색 품질 고도화(엔티티 정규화/리랭킹).
- DB 이미지 교체(pgvector/pgvector:pg16 유지 가능, RAG 미사용).
- 동시 메시지 checkpoint 손실(별개 이슈).

## Further Notes

ADR-0007(GraphRAG/Neo4j) 컷오버의 마지막 단계다. dual-write 제거로 그래프가 RAG의 단일 진실이 된다. 제거 순서 의존성: 청크 인스펙터를 Text Unit으로 옮긴 뒤(67) 인제스션을 그래프 단일화(68)하고, 마지막에 DocumentChunk/retriever/pgvector를 삭제(69)해야 중간 단계에서도 스위트가 green을 유지한다.
