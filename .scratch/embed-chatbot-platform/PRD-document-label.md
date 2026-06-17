Status: ready-for-agent

# PRD: Document Label

## Problem Statement

Tenant가 RAG Knowledge Base에 업로드하는 PDF나 이미지 문서는 본문 내용에 제품명·모델명이 등장하지 않는 경우가 많다. 파일명이나 Tenant가 알고 있는 컨텍스트에는 "FCB1010" 같은 식별자가 있지만, 문서 본문은 해당 장치의 사양만 나열되어 있다. 이 상태에서 Visitor가 "FCB1010 스위치 기능 알려줘"라고 질문하면 벡터 검색이 정확한 청크를 찾지 못해 RAG가 무용지물이 된다.

## Solution

Tenant가 문서마다 Document Label을 직접 지정하도록 한다. 업로드 시 파일명을 기본값으로 채우되, 업로드 전후 모두 편집 가능하다. Document Label은 DocumentChunk 임베딩 생성 시 `"<label>: <chunk_content>"` 형태로 prefix되어, 제품명 기반 쿼리가 본문에 제품명이 없는 문서의 청크와도 매칭되게 한다. Label 변경 시 자동으로 재임베딩을 트리거한다.

## User Stories

1. As a Tenant, I want to set a Document Label when uploading a file, so that I can associate the file with the product or model name it belongs to.
2. As a Tenant, I want the filename to be pre-filled as the Document Label, so that I don't have to type from scratch every time.
3. As a Tenant, I want to edit the Document Label of an already-uploaded document, so that I can correct or refine it after seeing how search results perform.
4. As a Tenant, I want label changes to automatically re-index the document, so that search immediately reflects the updated label without manual re-upload.
5. As a Tenant, I want to see the document status change to "processing" while re-indexing is in progress, so that I know the label change is being applied.
6. As a Tenant, I want re-indexing to complete without me re-uploading the file, so that I don't have to wait for OCR or file transfer again.
7. As a Visitor, I want to search by product name even when the document body doesn't mention the product name, so that I get accurate answers about a specific model.
8. As a Tenant, I want the LLM response to reflect which document a retrieved passage came from, so that I can verify the source during RAG test queries.

## Implementation Decisions

### Document Label = `Document.name`

`Document.name`을 "사용자 편집 가능한 레이블"로 승격한다. 업로드 시 파일명을 기본값으로 저장하며, 스키마 추가 없이 기존 `name` 필드를 그대로 사용한다.

### 임베딩 시 동적 prefix (ADR-0006)

`DocumentChunk.content`에는 추출 원문만 저장한다 (label prefix 미포함). 임베딩 생성 시에만 `"<Document.name>: <content>"` 형태로 prefix를 붙인다. LLM에 청크를 전달할 때도 동적으로 prefix를 붙여 어느 문서에서 온 정보인지 LLM이 알 수 있게 한다.

### 새 API 엔드포인트: PATCH `/rag/{document_id}`

요청 바디: `{ "name": "FCB1010" }` (비어 있으면 400)  
동작: `Document.name` 업데이트 → `re_embed_document` Celery 태스크 트리거 → 업데이트된 `DocumentOut` 반환  
Document 상태는 즉시 `pending`으로 리셋되고, 태스크 내에서 `processing` → `ready` (또는 `failed`)로 전환된다.

### 새 Celery 태스크: `re_embed_document`

기존 `DocumentChunk.content` 값을 읽어 현재 `Document.name`으로 prefix한 뒤 `get_embeddings()`를 호출해 `DocumentChunk.embedding`을 갱신한다. OCR 및 텍스트 재추출 없이 임베딩만 교체한다. 실패 시 기존 `ingest_document`와 동일하게 `status=failed` + `error_message` 저장.

### Retriever 수정

`retrieve_chunks()`와 `retrieve_chunks_with_scores()` 모두 반환 시 content에 `Document.name` prefix를 붙인다. `retrieve_chunks()`는 `select_related("document")`를 추가해 name을 조회한다. 반환 형태: `"<document_name>: <content>"`.

### Admin UI (Tenant)

- **업로드 모달**: 파일 선택 후 "Document Label" 입력 필드 표시, 파일명을 기본값으로 미리 채움.
- **문서 목록**: 각 Document 행에 "레이블 수정" 인라인 편집 또는 편집 버튼 제공. 저장 시 PATCH 호출 후 status가 `processing`으로 바뀌는 것을 목록에 즉시 반영.

## Testing Decisions

좋은 테스트란 내부 구현이 아닌 외동 동작을 검증한다. 임베딩 함수가 어떻게 호출되는지가 아니라, "label이 붙은 청크가 label 포함 쿼리에서 더 잘 검색되는가"를 검증하는 것이 목표다.

**테스트 대상 모듈:**

- **`DocumentIngester.ingest()`**: label prefix가 포함된 텍스트로 임베딩이 생성되는지 — `retrieve_chunks()`로 label 포함 쿼리를 날려 실제로 청크가 검색되는지로 검증. 기존 `test_ingest_png_creates_chunks` 패턴 참조.
- **`re_embed_document` Celery 태스크**: label 변경 후 동일 쿼리로 검색하면 새 label 기준으로 검색되는지 end-to-end로 검증.
- **`PATCH /rag/{document_id}` 엔드포인트**: 빈 name → 400, 정상 name → 200 + status 전환, 다른 Tenant 문서 접근 → 404.
- **Retriever**: 반환된 content에 document label prefix가 포함되어 있는지.

Prior art: `backend/tests/test_rag.py`의 `test_ingest_*` 및 `test_pdf_*` 테스트 시리즈.

## Out of Scope

- 동일 Label을 여러 문서에 공유하는 그룹핑 기능
- Label 자동 추출 (LLM이 파일명/본문에서 모델명을 추론)
- Label 변경 이력 추적

## Further Notes

재임베딩 태스크는 파일을 MEDIA_ROOT에서 다시 읽지 않으므로 파일이 삭제돼도 재임베딩은 가능하다. 다만 현재 파일은 ingestion 후에도 MEDIA_ROOT에 남아 있으므로 실질적 문제는 없다.
