Status: ready-for-agent

# PRD: Web URL · Excel 인제스션 (B)

## Problem Statement

Tenant는 PDF/TXT/이미지만 Knowledge Graph 생성용 문서로 올릴 수 있다. 하지만 많은 Tenant의 지식은 **웹 페이지(FAQ·문서 사이트)**나 **Excel 표(제품 카탈로그·사양표)**에 있다. 지금은 이를 그래프에 넣을 방법이 없어 일일이 PDF로 변환해야 한다.

## Solution

DocumentIngester를 두 소스로 확장한다. **Excel(xlsx·xls)**은 기존 파일 업로드 모델에 ExcelIngester로 추가하고, 시트를 헤더-키 행별 텍스트로 평탄화해 Entity 추출에 적합하게 만든다. **웹**은 Tenant가 명시한 URL(들)을 fetch해 메인 콘텐츠를 추출하며(재귀 크롤 아님), 각 URL이 하나의 Document가 된다. Document에 파일/URL **Document Source** 구분을 두고 인제스션 태스크가 분기한다.

## User Stories

1. Tenant로서, 제품 사양이 담긴 Excel(.xlsx)을 올려 Knowledge Graph에 넣고 싶다.
2. Tenant로서, 구형 .xls 파일도 동일하게 올릴 수 있길 바란다.
3. Tenant로서, Excel의 각 행이 의미 있는 레코드(예: 제품+속성)로 Entity 추출되길 바란다.
4. Tenant로서, 여러 시트가 있는 워크북에서 시트별로 맥락이 구분되어 추출되길 바란다.
5. Tenant로서, 수식 셀이 계산된 값으로 들어가길 바란다.
6. Tenant로서, 우리 FAQ 페이지 URL을 입력해 그 내용을 그래프에 넣고 싶다.
7. Tenant로서, 여러 문서 페이지 URL을 목록으로 한 번에 추가하고 싶다.
8. Tenant로서, 각 URL이 별도 Document로 잡혀 출처 표시·삭제 단위가 되길 바란다.
9. Tenant로서, 웹 페이지의 nav·footer 보일러플레이트가 제거되고 본문만 추출되길 바란다, 그래야 쓰레기 Entity가 안 생긴다.
10. Tenant로서, 웹 Document의 기본 이름(Document Label)이 페이지 제목 또는 URL로 채워지길 바란다.
11. Tenant로서, 웹 페이지 내용이 바뀌면 어드민에서 "다시 가져오기"로 갱신하고 싶다.
12. Tenant로서, 웹 Document를 다른 문서처럼 삭제할 수 있길 바란다.
13. Tenant로서, fetch 실패(404·타임아웃)한 URL은 Document status가 failed로 표시되길 바란다.
14. Tenant로서, Excel/웹 Document도 PDF처럼 Local/Global Search 근거로 쓰이길 바란다.
15. Operator로서, 인제스션 태스크가 파일 소스와 URL 소스를 깔끔히 분기하길 바란다.
16. Tenant로서, 지원하지 않는 형식·접근 불가 URL은 명확한 오류로 거부되길 바란다.

## Implementation Decisions

- **ExcelIngester deep module**: bytes → 텍스트. 첫 행을 헤더(키)로 보고 각 데이터 행을 `헤더: 값` 쌍으로 평탄화. 시트별 섹션(시트명 prefix). 수식은 계산값(openpyxl data_only), 빈 셀 skip. xlsx=openpyxl, xls=xlrd. 두 mime(`...spreadsheetml.sheet`, `application/vnd.ms-excel`) → ExcelIngester. `extract_text(file_bytes) -> str` 인터페이스 준수.
- **WebIngester deep module**: URL → fetch(HTML) → 메인 콘텐츠 추출(readability류, 보일러플레이트 제거) → 텍스트. HTML→텍스트 추출은 fixture HTML로 격리 테스트 가능하게 fetch와 추출을 분리.
- **Document Source**: `Document`에 소스 종류(파일/URL) + URL 저장 필드. 웹 소스는 mime `text/html`, Document Label 기본값 = 페이지 `<title>` 또는 URL.
- **인제스션 태스크 분기**: 기존 `ingest_document`가 소스 종류로 분기 — 파일이면 디스크 읽기, URL이면 fetch. 이후는 동일한 `ingest_to_graph` 경로(텍스트 → LLM 추출 → 그래프).
- **웹 Document 생성 API**: 파일 업로드와 별개로 URL(들)을 받아 각 URL당 Document 생성 + 인제스션 태스크 enqueue.
- **수동 재-fetch**: 웹 Document의 재-ingest(삭제+재구축) 트리거. 자동 스케줄 재크롤 없음.

## Testing Decisions

좋은 테스트는 외부 행위만 검증한다. 실제 객체(임베딩·Neo4j·OCR 실물), LLM 경계만 Fake. 최대 커버리지 — deep module + 업로드/인제스션 통합.

- **ExcelIngester** [순수·결정적 단위, DB 불필요]: 헤더+행 fixture → `헤더: 값` 텍스트 확인. 멀티시트 → 시트별 섹션. 수식 셀 → 계산값. 빈 셀 skip. xlsx·xls 둘 다.
- **WebIngester 추출** [fixture HTML 결정적]: 보일러플레이트(nav·footer) 포함 HTML → 본문만 추출, 노이즈 제거 확인. fetch는 로컬 HTTP fixture(conftest의 webhook_server류 패턴)로.
- **Excel 업로드 통합**: .xlsx 업로드 → status ready, Text Unit·Entity 생성, 행 기반 Entity가 검색됨.
- **웹 인제스션 통합**: 로컬 HTTP fixture URL 추가 → fetch·추출·그래프 기여 → 그 내용이 Local Search로 검색됨. 각 URL=Document.
- **실패 경로**: 접근 불가 URL → Document status=failed + error_message. 지원 안 하는 형식 → 400.
- **재-fetch**: 웹 Document 재-ingest 시 기존 기여분이 교체됨.
- Prior art: `tests/test_rag.py`(업로드→인제스션→그래프, OCR fallback fixture), `tests/conftest.py`(webhook_server = 로컬 HTTP fixture).

## Out of Scope

- 재귀 크롤(링크 추적·깊이·도메인 제한·robots.txt·루프 제거).
- JS 렌더링 페이지(헤드리스 브라우저).
- 자동 스케줄 재크롤·변경 감지.
- CSV(별도 후속). Google Sheets 등 외부 연동.

## Further Notes

- 웹 인제스션은 외부 콘텐츠를 그래프에 넣으므로 간접 프롬프트 인젝션 표면을 만든다 — 기능 D(프롬프트 하드닝)에서 RAG 내용을 비신뢰 데이터로 다룬다.
- Excel 행별 텍스트가 마크다운 표보다 행 단위 Entity 추출에 유리하다(grill 결정).
