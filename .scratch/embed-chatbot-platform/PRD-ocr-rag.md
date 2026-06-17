# PRD: OCR RAG 지원 + Document Chunk Inspector

Status: ready-for-agent
Labels: ready-for-agent

## Problem Statement

1. **스캔 PDF / 커스텀 폰트 PDF**: FCB1010_M_EN.pdf처럼 커스텀 Type1 폰트를 쓰는 PDF는 pymupdf가 `2*$*`, `?'$` 같은 쓰레기 printable ASCII를 반환한다. 제어문자 strip으로는 고칠 수 없다. 스캔본 PDF는 텍스트 레이어 자체가 없어서 extract_text()가 빈 문자열을 돌려준다.

2. **이미지 파일 미지원**: PNG/JPG 스크린샷이나 스캔 이미지를 RAG에 넣고 싶어도 현재 DocumentIngester가 이미지 MIME을 거부한다.

3. **청크 상태 불투명**: 문서를 업로드하면 `status=ready`가 뜨지만, 실제로 어떤 텍스트가 몇 개의 청크로 저장됐는지 Tenant Agent가 확인할 방법이 없다.

## Solution

1. PaddleOCR 서비스(pp-ocrv5, `ch` 언어)를 embed-chat Docker 스택에 포함시키고, 두 가지 경로로 연결한다:
   - **ImageIngester**: PNG/JPG/JPEG/WEBP 파일을 직접 OCR → 텍스트 → 청크 인제스션
   - **PDF OCR fallback**: pymupdf 추출 단어 수가 50 미만이면 PaddleOCR로 재시도

2. **Document Chunk Inspector**: Tenant 어드민 DocumentsTab에서 문서를 클릭하면 해당 문서의 청크 목록(인덱스, 내용 미리보기)을 볼 수 있는 뷰 추가.

## User Stories

1. As a Tenant Agent, I want to upload PNG/JPG/WEBP image files to the RAG Knowledge Base, so that scanned images and screenshots are searchable.
2. As a Tenant Agent, I want scanned PDFs and custom-font PDFs to be correctly ingested via OCR, so that garbled text no longer appears in RAG results.
3. As a Tenant Agent, I want to see how many chunks a document was split into and preview their content, so that I can verify ingestion quality.
4. As a Tenant Agent, I want to know the chunk index and text preview for each chunk, so that I can debug why certain queries don't return expected results.
5. As a Tenant Agent, I want the system to automatically decide whether to use OCR, so that I don't have to manually select an extraction mode.

## Implementation Decisions

- **PaddleOCR 서비스**: bt-editor의 `paddle_service/` 디렉토리를 embed-chat 루트로 복사. `lang="korean"` → `lang="ch"` (한/영 혼용). GPU 필수에서 CPU 폴백으로 변경 (Docker 환경에 GPU 없을 수 있음). `docker-compose.yml`과 `docker-compose.test.yml`에 `paddle-ocr` 서비스 추가.

- **PADDLE_OCR_URL**: `backend/config/settings/base.py`에 `PADDLE_OCR_URL = os.getenv("PADDLE_OCR_URL", "http://paddle-ocr:8080")` 추가. `.env.example`에 문서화.

- **ImageIngester**: `ingesters.py`에 추가. `extract_text(file_bytes)`가 base64 인코딩 후 `POST {PADDLE_OCR_URL}/ocr`을 호출, `{"text": "..."}` 응답에서 텍스트 반환. MIME: `image/png`, `image/jpeg`, `image/webp`.

- **PDF OCR fallback**: `PDFIngester.extract_text()`에서 pymupdf 추출 후 `len(text.split()) < 50`이면 `_ocr_pdf(file_bytes)` 호출. `_ocr_pdf`는 fitz로 각 페이지를 PNG 이미지로 렌더링 → paddle OCR 순차 호출 → 텍스트 합산.

- **Document Chunk Inspector API**: `GET /api/tenant/documents/{id}/chunks` — DocumentChunk 목록 반환. 각 항목: `{chunk_index, content}`. embedding 벡터는 제외.

- **Document Chunk Inspector UI**: DocumentsTab에서 각 문서 행에 "청크 보기" 버튼 추가. 클릭 시 동일 페이지 내 확장 패널(accordion)로 청크 목록 표시. 별도 페이지 이동 없음.

- **프론트 업로드 허용 타입**: `accept=".pdf,.txt,.png,.jpg,.jpeg,.webp"`. 백엔드 업로드 뷰도 image MIME 허용 검증 추가.

## Testing Decisions

- 좋은 테스트: 공개 API 계약(업로드 → status=ready → 청크 존재)만 검증. PaddleOCR 실제 호출은 test 환경에서 `httpx.MockTransport` 또는 실제 paddle-test 서비스로 처리.
- 테스트 대상:
  - `ImageIngester.extract_text()` — paddle 서비스 응답을 실제 HTTP로 검증 (test compose에 paddle-ocr 서비스 포함)
  - PDF OCR fallback — 단어 수 < 50인 최소 PDF 업로드 시 OCR 경로 진입 확인
  - `GET /api/tenant/documents/{id}/chunks` 엔드포인트
  - E2E: 이미지 업로드 → status=ready → 청크 조회 패널에서 내용 확인
- Prior art: `test_rag.py`의 `test_ingest_*` 패턴, `e2e/tests/rag-test-panel.spec.js` 패턴

## Out of Scope

- Tenant별 OCR 언어 설정 UI
- PDF 페이지별 OCR 결과 분리 저장 (페이지 단위 청킹)
- 청크 수동 편집·삭제
- DOCX, XLSX 등 Office 포맷
- OCR confidence score 표시

## Further Notes

- paddle-ocr 서비스가 cold start에 시간이 걸림 (모델 로드). healthcheck에 `/health` 엔드포인트 사용.
- test compose에서는 GPU 없이 CPU로 동작해야 하므로, paddle_service의 Dockerfile과 app.py에서 GPU 폴백 처리 확인 필요.
- PDF OCR fallback 임계값 50은 설정값이 아닌 코드 상수로 관리 (`PDF_OCR_FALLBACK_MIN_WORDS = 50`).
