# Document Label을 임베딩 시점에 동적으로 prefix

DocumentChunk의 `content`에는 추출 원문만 저장하고, 임베딩 생성과 LLM 컨텍스트 구성 시점에 `"<Document Label>: <content>"` 형태로 prefix를 동적으로 붙인다.

## 배경

PDF 본문에 제품명(예: FCB1010)이 등장하지 않는 문서가 있다. Visitor가 "FCB1010 사양 알려줘"라고 질문했을 때, 제품명이 없는 청크는 쿼리 임베딩과의 거리가 멀어 검색에서 누락된다. Document Label(사용자 지정 문서 이름)을 임베딩에 반영해 이 문제를 해결한다.

## 고려한 대안

**prefix를 content에 포함해 저장**: `DocumentChunk.content = "FCB1010: 스위치 기능은..."` 형태로 저장하면 단순하지만, Document Label 변경 시 모든 청크의 content를 수정하고 재임베딩해야 한다. OCR이 느린 환경에서는 비용이 크다.

## 결정 이유

`content`를 순수 추출 텍스트로 유지하면 Label 변경 시 재임베딩만 하면 된다. 텍스트 재추출(OCR 포함) 없이 기존 `content`에 새 Label을 붙여 임베딩을 재생성하므로 훨씬 가볍다. Label 변경은 `Document.name` 수정 → Celery 재임베딩 태스크 자동 트리거로 처리된다.

## 결과

- `DocumentChunk.content`와 실제 임베딩 입력이 다르다. 코드 리뷰 시 의아하게 보일 수 있으나 이 ADR이 그 이유를 설명한다.
- LLM에 청크를 넘길 때도 `[Document Label] content` 형태로 동적으로 조합해야 한다.
