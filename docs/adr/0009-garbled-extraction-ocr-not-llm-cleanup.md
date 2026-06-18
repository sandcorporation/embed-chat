# ADR-0009: Garbled PDF 추출은 LLM 정제가 아니라 OCR 재추출로 복구한다

## Status
Accepted

## Context
일부 PDF는 텍스트 레이어의 폰트 인코딩(ToUnicode/CID 매핑)이 없어, `page.get_text()`가 글리프를 의미 없는 문자열(mojibake, 예: `-%&././ 2*$* . ./G/`)로 추출한다. 현재 `PDFIngester`의 OCR fallback 조건은 **단어 수**(`len(text.split()) < 50`)뿐이라, 깨진 텍스트는 토큰 수가 충분해 fallback을 빠져나가 그대로 임베딩·저장된다.

이 깨진 텍스트는 두 갈래로 흘러간다(`graph_ingester.ingest_to_graph`): (1) `extract_graph`의 LLM Entity/관계 추출 입력, (2) `chunk_text` → `upsert_text_unit`으로 Text Unit content·임베딩. 실제 사고: tenant `8282e641…`의 fcb1010 문서(`doc 0e59c3de`, Text Unit 7개 전부 깨짐)가 Local Search 근거 문맥으로 깨진 채 노출됨(checkpoint `rag_chunks`에서 발견). 같은 파이프라인의 HP 문서(`8457c037`)는 OCR 경로로 깨끗한 한글로 들어와, OCR이 복원 경로임이 입증됨.

## Decision
깨진 추출(Garbled Extraction)을 **추출 직후 문자 클래스 비율 휴리스틱으로 문서 단위 감지**하고, 감지되면 **OCR로 문서 전체를 재추출**한다. LLM 정제·복원은 쓰지 않는다. OCR 재추출 결과도 여전히 깨진 청크는 **저장하지 않고 드롭**한다.

- 감지: `PDFIngester.extract_text`의 단어 수 조건 옆에 `_looks_garbled(text)`를 OR로 추가. 임계값은 fixture로 튜닝.
- 복구: 기존 `_ocr_pdf`(문서 전체 페이지별 OCR) 재사용.
- 기존 손상 데이터: fcb1010 재처리는 코드 범위 밖 — 어드민에서 수동 재업로드로 처리(운영 조치).

## Considered Options
- **LLM이 깨진 텍스트를 정제/복원**(사용자 제안): 기각. 폰트 매핑이 소실된 텍스트 레이어에는 원문 정보가 0이라, LLM의 "정제"는 사실상 추측·창작이 된다. Entity는 출처 Text Unit으로 검증 가능한 '해석'이지만, Text Unit content는 그 검증의 '기준점(원문)'이다. 기준점마저 LLM 창작이면 Local Search citation의 검증 가능성이 무너진다. 추가로 전체 문서를 LLM에 넣어야 해(현 `text[:8000]` 컷 충돌) 비용·지연이 크고, LLM 경계를 Fake로 막는 테스트 원칙상 정제 품질을 회귀로 검증할 수도 없다.
- **단순 깨진문자(U+FFFD) 카운트**: 기각. fcb1010은 U+FFFD가 아니라 잘못된 ASCII/기호로 매핑돼 안 잡힌다.
- **PyMuPDF 폰트 메타(ToUnicode 부재/notdef 비율) 검사**: 보류. 근본 신호에 가깝지만 라이브러리 내부 API 의존·테스트 fixture 제작이 까다로워, 결정적·언어독립적인 문자 클래스 휴리스틱을 1차로 채택.
- **페이지 단위 폴백**: 보류. 정밀하나 구현 복잡. 관측된 사고가 문서 전체 깨짐이라 문서 단위로 충분(YAGNI).

## Consequences
- OCR fallback 트리거가 넓어져, 텍스트 레이어가 멀쩡한데도 오탐으로 OCR을 타는 문서가 생길 수 있다(느림·OCR 오인식 위험). 임계값을 보수적으로 잡아 통제한다.
- citation 원문성 원칙이 도메인 규약으로 확정됨: Text Unit은 추출 원문/OCR 재추출본만 담고 LLM 생성물을 담지 않는다(CONTEXT.md Text Unit·Garbled Extraction 항목).
- 새 문서는 자동 보호되나, 이미 저장된 깨진 Text Unit/Entity는 재업로드 전까지 남는다.
