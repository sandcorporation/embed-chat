# ADR 0001: HITL 감지를 LLM Structured Output으로 처리

## Status
Accepted

## Context
HITL(Human-in-the-Loop) 트리거를 AI가 판단하는 방법으로 세 가지 대안이 있었다:
- **A) Structured Output**: LLM이 `{ response, needs_hitl, hitl_reason }` 형식으로 한 번에 반환
- **B) 별도 분류 LLM 호출**: 메인 LLM 이후 경량 LLM을 추가 호출해 판단
- **C) 키워드/규칙 기반**: System Prompt에 `[HITL]` 태그 규칙을 넣고 파싱

또한 Visitor가 "상담원 연결"을 명시 요청하는 경우(버튼 방식 vs 키워드 감지)에서도 키워드 감지를 Structured Output에 통합하기로 결정했다.

## Decision
LLM 호출 시 `.with_structured_output()`으로 `{ response, needs_hitl, hitl_reason }` 구조를 강제한다. `needs_hitl` 판단은 AI 불확실 상황과 Visitor의 상담원 요청 키워드 감지를 모두 포함한다.

## Consequences
- **장점**: API 호출 1회로 응답과 HITL 판단을 동시에 얻음. 키워드 규칙보다 신뢰성 높음.
- **단점**: LLM이 structured output을 지원해야 함(OpenRouter 모델 선택 시 제약). 일부 구형 모델은 function calling 미지원.
- **트레이드오프**: B 대비 비용 절감(호출 1회 감소), C 대비 정확도 향상.
