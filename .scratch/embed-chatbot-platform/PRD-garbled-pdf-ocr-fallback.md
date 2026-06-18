Status: ready-for-agent

# PRD: 깨진 PDF 추출(Garbled Extraction) 감지 → OCR 재추출

## Problem Statement

일부 PDF는 텍스트 레이어의 폰트 인코딩(ToUnicode/CID 매핑)이 없어 추출 시 의미 없는 문자열(mojibake, 예: `-%&././ 2*$* . ./G/ … PRG CHG 1`)이 나온다. 현재 `PDFIngester`의 OCR fallback은 **단어 수**(`len(text.split()) < 50`)만 본다. 깨진 텍스트는 토큰 수가 충분해 fallback을 빠져나가 그대로 임베딩·저장된다.

그 결과 깨진 텍스트가 Knowledge Graph로 흘러간다: (1) Entity/관계 추출 입력이 부실해지고, (2) Text Unit content가 깨진 채 저장되어 **Local Search의 근거 문맥(citation)이 오염**된다. 실제 사고로 tenant `8282e641…`의 fcb1010 문서(`doc 0e59c3de`, Text Unit 7개 전부 깨짐)가 Local Search 결과로 깨진 채 노출되었다(visitor-211f8f00 checkpoint의 `rag_chunks`에서 발견). 같은 파이프라인의 HP 문서(`doc 8457c037`)는 OCR 경로로 깨끗한 한글로 들어와, OCR이 복원 경로임이 입증됐다.

## Solution

추출 직후 **깨진 추출(Garbled Extraction)을 문자 클래스 비율 휴리스틱으로 문서 단위 감지**하고, 감지되면 기존 `_ocr_pdf`로 **문서 전체를 OCR 재추출**한다. OCR은 이미지 픽셀에서 글자를 다시 읽으므로 폰트 인코딩 깨짐과 무관하게 진짜 텍스트를 되찾는다. OCR 재추출 이후에도 여전히 깨진 청크는 Text Unit으로 **저장하지 않고 드롭**한다.

LLM 정제·복원은 쓰지 않는다 — Text Unit은 검증의 기준점(원문)이고, 폰트 매핑이 소실된 텍스트에서 LLM "정제"는 추측·창작이 되어 citation을 환각으로 오염시키기 때문이다(ADR-0009). Tenant 입장에서는 깨진 문서를 올려도 검색 근거가 정상 텍스트로 나온다.

## User Stories

1. As a Tenant, I want a PDF whose text layer is garbled to be re-extracted via OCR, so that its real content lands in the Knowledge Base.
2. As a Visitor, I want Local Search citations to be readable real text rather than mojibake, so that I can trust the answer's evidence.
3. As a Visitor, I want answers grounded in OCR-recovered text instead of corrupted glyphs, so that the bot doesn't quote garbage.
4. As a Tenant, I want a normal PDF with a valid text layer to skip OCR, so that ingestion stays fast and isn't needlessly degraded by OCR misreads.
5. As a Tenant, I want a scanned (text-layer-sparse) PDF to still trigger OCR as before, so that the existing fallback keeps working.
6. As a Tenant, I want a partially-recoverable document where OCR still yields some garbled chunks to drop those chunks, so that no garbage is stored as a Text Unit.
7. As a TenantAgent, I want "청크 보기" to show only readable Text Units after ingestion, so that the inspector reflects usable knowledge.
8. As a developer, I want garble detection as an isolated, deterministic module, so that I can unit-test its thresholds with fixtures.
9. As a developer, I want the garbled-fixture (text layer = mojibake, pixels = real text) to prove both detection and OCR recovery in one integration test, so that the regression is locked.
10. As a developer, I want the garble heuristic shared between the PDF fallback decision and the chunk-drop step, so that one definition of "garbled" governs both.
11. As a Tenant, I want an English document with legitimate symbol-heavy content (code/tables) not to be falsely flagged as garbled, so that real documents aren't wrongly OCR'd.
12. As a developer, I want garble detection to leave non-PDF paths (TXT/이미지) unchanged, so that scope stays contained.
13. As an Operator/Tenant, I want existing already-garbled documents (fcb1010) to be fixable by re-uploading from the admin UI, so that historical corruption can be cleared without a migration.
14. As a developer, I want Document status (pending/processing/ready/failed) to remain correct through the garble→OCR path, so that progress stays visible.

## Implementation Decisions

### 모듈 1 — 깨짐 감지 (신규 deep module)

`apps/rag/`에 독립 모듈로 `is_garbled(text: str) -> bool` 순수 함수를 둔다. 외부 의존이 없고 문자 클래스 비율 휴리스틱을 캡슐화한다 — 전체 비공백 문자 대비 의미 있는 letter(한글 음절 + 라틴 letter) 비율이 낮고, 기호·단일문자 토큰 비율이 높으면 깨짐으로 판정. 임계값은 모듈 내부 상수로 두고 fixture로 튜닝한다. `PDFIngester`(문서 전체)와 chunk 드롭(청크 단위) **양쪽이 같은 함수를 공유**한다.

- 신호 선택: 문자 클래스 비율 휴리스틱(결정적·언어독립). U+FFFD 카운트는 배제(fcb1010은 잘못된 ASCII로 매핑되어 안 잡힘). PyMuPDF 폰트 메타 검사는 보류(라이브러리 내부 의존·fixture 난이도).

### 모듈 2 — PDFIngester.extract_text 폴백 확장

기존 단어 수 조건 옆에 OR로 깨짐 감지를 추가: 추출 텍스트가 `단어 수 부족` **또는** `is_garbled`이면 `_ocr_pdf`로 문서 전체 재추출. 폴백 단위는 문서 전체(관측된 사고가 문서 전체 깨짐, 기존 `_ocr_pdf` 구조와 동일, YAGNI). 페이지 단위 폴백은 채택하지 않는다.

### 모듈 3 — ingest_to_graph 청크 드롭

`chunk_text` 산출 청크 중 `is_garbled(chunk)`인 청크는 `upsert_text_unit` 대상에서 제외한다(OCR 재추출 후에도 남은 잔여 깨짐의 최종 방어선). 드롭은 Text Unit 저장에만 적용하며, Entity 추출(`extract_graph`) 입력은 OCR 재추출본 전체를 그대로 사용한다.

### 도메인 문서

- CONTEXT.md: `DocumentIngester` 폴백 조건 갱신, 신규 용어 **Garbled Extraction** 추가, `Text Unit`에 citation 원문성(추출 원문/OCR 재추출본만, LLM 생성물 금지) 명시 — 이미 반영됨.
- ADR-0009: LLM 정제 거부 · OCR 재추출 · citation 원문성 결정 기록 — 이미 작성됨.

### 기존 손상 데이터

fcb1010(`doc 0e59c3de`) 등 이미 저장된 깨진 Text Unit/Entity의 정리는 **코드 범위 밖**이다. 어드민 UI에서 문서 삭제 후 재업로드(수정된 파이프라인을 다시 탐)하는 운영 조치로 처리한다. 일회성 management command나 데이터 마이그레이션은 만들지 않는다.

## Testing Decisions

좋은 테스트는 내부 휴리스틱 구현이 아니라 외부 동작을 검증한다: 깨진 텍스트 레이어 PDF를 올리면 검색 근거가 정상 텍스트로 나오는가, 정상 PDF는 OCR을 건너뛰는가, OCR 후에도 깨진 청크는 저장되지 않는가.

- **모듈 1 (단위)**: `is_garbled`를 fcb1010 실제 발췌(`-%&././ 2*$* …`)와 정상 한글/영어/기호 많은 정상 텍스트(코드·표) 샘플로 직접 검증. 깨짐→True, 정상→False, 오탐 경계 케이스 포함. 순수 함수라 DB 불필요.
- **모듈 2·3 (통합)**: `apps/agent/llm` 경계만 Fake(Entity 추출 LLM), 그 외 임베딩·Neo4j·OCR(paddle)은 실제 객체. 깨짐 fixture는 `_make_image_only_pdf` 패턴을 확장해 **텍스트 레이어=mojibake(invisible), 이미지 픽셀=정상 텍스트**인 PDF를 합성 → 업로드 후 `get_text()`가 깨짐 감지를 트리거하고 OCR이 정상 텍스트를 복원함을 Text Unit 내용으로 검증. 정상 PDF는 OCR 건너뜀, 잔여 깨짐 청크 드롭도 검증.
- 회귀: 기존 `test_pdf_ocr_fallback_used_when_text_too_sparse`(단어 수 경로), `test_pdf_normal_text_skips_ocr`가 깨지지 않아야 한다.
- Prior art: `tests/test_rag.py`의 "Issue 50: PDF OCR Fallback" 섹션(`_make_image_only_pdf`, 실제 OCR 통합), `tests/test_graph_store.py`.

## Out of Scope

- 이미 저장된 깨진 데이터의 자동 정리(어드민 재업로드로 처리, 별도 작업 없음).
- 페이지 단위 부분 OCR 폴백(문서 단위로 충분).
- LLM 기반 텍스트 정제/복원(ADR-0009로 명시적 기각).
- PyMuPDF 폰트 메타 기반 감지(보류, 휴리스틱 우선).
- TXT/이미지 인제스션 경로 변경(이미지는 항상 OCR, 변화 없음).
- OCR 엔진 품질 개선(paddle 자체 튜닝).

## Further Notes

ADR-0009의 구현이다. 핵심 통찰: 같은 추출 텍스트가 Entity 추출과 Text Unit 저장 두 갈래로 흐르므로, 입력을 OCR로 한 번 고치면 두 갈래가 동시에 정상화된다 — LLM 정제는 Text Unit 갈래(citation)를 고치지 못하거나 환각으로 오염시킨다. 구현 순서 의존성: 모듈 1(감지)을 먼저 만들어 단위 테스트로 임계값을 확정한 뒤, 모듈 2(폴백)·모듈 3(드롭)이 그것을 소비한다.
