# 06 — RAG DocumentIngester + Celery 파이프라인 (PDF/TXT)

Status: ready-for-agent

## What to build

Tenant가 PDF 또는 TXT 파일을 업로드하면 Celery 워커가 비동기로 청킹 → 임베딩 → pgvector 저장까지 처리하는 파이프라인을 구현한다.

- `DocumentIngester` 인터페이스: `ingest(file_bytes, mime_type, tenant_id, document_id) -> None`
- 구현체: `PDFIngester`, `TXTIngester`
- 문서 상태: `pending → processing → ready / failed`
- Tenant API 엔드포인트 (`/api/tenant/documents/`) — TENANT_KEY Bearer 인증
- 업로드된 파일은 S3 호환 스토리지 또는 로컬 볼륨에 저장, pgvector에는 청크+벡터만 저장

## Acceptance criteria

- [ ] `POST /api/tenant/documents/` (multipart) → 문서 레코드 생성(`pending`), Celery 태스크 큐잉
- [ ] Celery 워커가 태스크 수행 → 청크 분할 → 임베딩 → pgvector upsert → 상태 `ready`
- [ ] 처리 실패 시 상태 `failed`, 오류 메시지 저장
- [ ] `GET /api/tenant/documents/` → 문서 목록 + 현재 상태 반환
- [ ] `DELETE /api/tenant/documents/{id}` → 문서 레코드 + pgvector 청크 삭제
- [ ] 타 Tenant 문서에 접근 시 404
- [ ] 단위 테스트: PDF/TXT 청킹 결과, 임베딩 호출 횟수, 실패 시 상태 `failed` 기록

## Blocked by

- `01-project-foundation.md`
