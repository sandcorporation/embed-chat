# PRD: 주제범위 제어 (Topic Scope Enforcement / in_scope 가드)

Status: ready-for-agent
Labels: ready-for-agent

## Problem Statement

Tenant의 챗봇이 비즈니스(도메인) 밖 질문에도 그냥 답한다. 예: "파란색에 대해 다섯 문장으로
설명해줘" → 봇이 일반지식으로 답변. 운영자는 봇이 **자기 비즈니스 관련 문의만** 응대하길 원하는데,
현재는 기본 system_prompt이 "You are a helpful assistant"(도메인 한정 없음)이고, 보안 하드닝의
"응대 범위를 벗어난 요청은 정중히 거절하세요"는 *범위가 정의돼 있지 않아* 모델이 무엇이든
답해버린다(`context_sufficient`는 라우팅 신호일 뿐 답변을 막는 게이트가 아님). 이는 탈옥이 아니라
**주제범위(스코프) 이탈** 문제다.

## Solution

운영자가 admin에서 **"주제범위 제어"를 on/off로 켜고**, **봇의 응대 범위를 한 줄로 설명**하면,
봇이 그 범위 밖 질문은 자연스럽게 거절한다("저는 OO 관련 문의를 도와드려요"). 인사·잡담 같은
대화 턴은 그대로 받아주고, 도메인 안이지만 자료가 없는 질문은 "그 정보는 없네요"로 답한다. 토글이
꺼져 있으면 현행(개방) 그대로다. 거절은 **프롬프트 + 코드 백스톱**으로 강제돼, 모델이 지침을 무시해도
범위 밖 답이 새지 않는다.

## User Stories

1. As an operator, I want a toggle to restrict my bot to on-topic questions, so that it doesn't answer unrelated general-knowledge questions like "describe the color blue".
2. As an operator, I want to describe my bot's scope in one line, so that the bot knows what counts as in-scope.
3. As an operator, I want off-topic questions politely declined, so that visitors are redirected to what the bot can help with.
4. As an operator, I want the decline message to reference my scope ("I help with OO inquiries"), so that it stays on-brand and useful.
5. As an operator, I want to optionally write my own decline message, so that I control the exact wording.
6. As an operator, I want greetings and small-talk still answered when the toggle is on, so that the bot isn't robotic ("hello" must not be refused).
7. As an operator, I want meta questions ("what can you help with?") answered, so that visitors can learn the bot's scope.
8. As an operator, I want in-domain questions with no knowledge-base support answered as "I don't have that specific info" (not a hard scope refusal), so that the bot distinguishes "off-topic" from "on-topic but unknown".
9. As an operator, I want the toggle off by default, so that my existing bot behavior is unchanged until I opt in.
10. As an operator, I want the bot to refuse off-topic reliably even if the model tries to answer, so that scope is actually enforced (not just suggested).
11. As an operator, I want to set the toggle, scope description, and decline message on the admin config page, so that I can manage scope without code.
12. As an operator, I want admin to require a scope description before enabling the toggle, so that I don't enable a broken (no-anchor) state.
13. As an operator, I want scope enforcement to coexist with HITL, so that off-topic is declined rather than escalated to a human.
14. As an operator with the toggle off, I want full current behavior, so that nothing regresses.
15. As a visitor, I want a clear, friendly decline when I ask something off-topic, so that I know what to ask instead.
16. As a visitor, I want my greeting answered warmly even on a scoped bot, so that the conversation feels natural.
17. As an operator, I want scope enforcement to work whether HITL is on or off (both structured-output paths), so that behavior is consistent.
18. As an operator, I want the decline to stream/appear like any other answer, so that the UX is consistent.
19. As an operator, I want scope enforcement to not leak the system prompt or scope-judgment internals, so that hardening is preserved.
20. As a developer, I want a small testable "scope decision" module, so that the refuse/pass logic is verified without an LLM.
21. As a developer, I want the scope instruction injected only when the toggle is on, so that off-state callers pay nothing.
22. As an operator, I want a sensible standard decline when I leave the custom message blank, so that I don't have to write one.
23. As an operator, I want the admin client (orval-generated) updated for the new config fields, so that the admin UI can read/write them.
24. As an operator, I want an empty scope description with the toggle somehow on to behave as off (fail-open), so that the bot never refuses everything by accident.

## Implementation Decisions

- **신규 TenantConfig 필드 3종**:
  - `topic_scope_enabled` (bool, 기본 **False** — opt-in 마이그레이션, 기존 테넌트 무변경).
  - `scope_description` (text, 기본 "") — 봇의 응대 범위/도메인 한 줄 설명. in_scope 판정의 기준 anchor.
  - `scope_refusal_message` (text, 기본 "") — 비우면 표준 거절 템플릿, 채우면 그 문구 사용.
- **구조화 출력에 `in_scope` 제어필드 추가** (HITLResponse·PlainResponse 둘 다). 제어필드
  (`in_scope`·`context_sufficient`)는 **response보다 앞** 정의 — 스트리밍 시 먼저 도착해 노드가
  종단/거절을 선판정한다(streaming 수정으로 strict json_schema가 필드 순서를 보존). 기본 True(토글
  OFF나 미설정 시 거절 안 함).
- **3분기 판정**(토글 ON):
  - 인사·메타·소셜 → `in_scope=True` → 자연 응답.
  - 명백한 도메인 밖 → `in_scope=False` → 거절.
  - 도메인 안 → `in_scope=True`, KB 있으면 `context_sufficient=True`(답변)/없으면 `False`(원문 폴백 →
    "그 정보는 없네요").
- **프롬프트 주입(deep module)**: 토글 ON일 때 `scope_description` 기반 스코프 지침 블록을 system
  prompt에 주입(현 `_ANTI_DISCLOSURE` 옆 conditional). "범위 밖이면 in_scope=False로 정중히 거절,
  범위 안이면 KB 근거로". OFF면 주입 없음(off-state 무비용).
- **구조적 백스톱(scope 결정 deep module)**: 종단에서 `topic_scope_enabled and not in_scope`이면
  모델의 response를 **무시하고 결정적 거절 메시지**(custom `scope_refusal_message` 또는 표준 템플릿
  `"죄송해요, 저는 {scope_description} 관련 문의를 도와드려요…"`)를 assistant 응답으로 확정한다.
  모델이 지침을 무시해도 코드가 막아 누출 차단. 스트리밍은 in_scope=False면 억제(폴백 억제와 동일
  패턴) 후 거절을 발행.
- **fail-open 방어**: `topic_scope_enabled=True`인데 `scope_description`이 비면 anchor가 없으므로
  OFF처럼 취급(전부 거절하는 사고 방지).
- **admin API 검증**: 토글을 켜 저장하려면 `scope_description`이 비어 있지 않아야 한다(에러 안내).
- **admin config 엔드포인트**: GET/PATCH에 3개 필드 노출(기존 config 필드 목록에 추가).
- **orval 재생성**(ADR-0014): 백엔드 Ninja Schema 변경이므로 admin OpenAPI·생성 클라이언트 재생성
  + openapi.json·generated 함께 커밋.
- **admin UI**: 설정 화면에 토글 + 범위 설명 + (선택) 거절 문구 입력, 토글 ON 시 범위 설명 필수
  검증, 가이드/플레이스홀더 제공.
- **그래프 호환**: HITL-on/off 두 경로(call_llm_structured/plain) 모두 in_scope·백스톱 적용.

## Testing Decisions

- **좋은 테스트**: 외부 행동만 — "토글 ON + in_scope=False면 거절 메시지가 나가고 모델의 off-topic
  응답은 안 보인다", "토글 OFF면 무엇이든 답한다(현행)", "인사(in_scope=True)는 답한다", "범위 설명
  비면 OFF처럼". 모델 판단 품질이 아니라 **우리 게이트 동작**을 검증. LLM은 결정적 Fake(in_scope를
  Fake 구조화 출력에 실어 제어).
- **대상 모듈**:
  1. **scope 결정 deep module** — (enabled, scope_description, in_scope, model_response,
     refusal_message) → 최종 응답(pass-through vs 거절: custom/표준). 순수 함수 단위 테스트, LLM 불요.
  2. **scope 프롬프트 빌더** — enabled+scope → 블록에 scope_description 포함, disabled → 블록 없음.
  3. **노드 통합**(fake_chat_llm) — 토글 ON+in_scope=False → 거절 발행·모델 응답 미노출, in_scope=True
     → 정상, 인사 → 응답, 토글 OFF → off-topic도 응답(현행). HITL-on/off 두 경로.
  4. **admin config API** — 3개 필드 set/get + 토글 ON 시 scope_description 필수 검증.
- **선례**: `test_business_hours_gating`(토글 게이팅), `test_hitl`(config 기반 그래프 컴파일),
  `test_chat_streaming`(fake로 노드 스트리밍·억제), `test_provider_models`(검증), `test_tenants`(config API).

## Out of Scope

- 별도 분류기 모델/2차 LLM 호출로 in_scope 판정(모델의 구조화 출력 in_scope만 사용).
- 거절 메시지 다국어 자동 현지화(scope_description/refusal_message 언어를 따른다).
- 거절 통계·분석 대시보드.
- 과거 대화 소급 스코프 적용.
- KB 암묵 스코프(문서로 자동 도메인 추론) — 이번엔 명시적 scope_description만(추후 폴백 고려 가능).
- 토큰 스트리밍 수정(별건으로 이미 완료).

## Further Notes

- in_scope는 `context_sufficient`와 **다른 신호**다: context_sufficient="KB 근거로 답 가능?",
  in_scope="이 질문이 봇의 응대 범위 안?". off-도메인 거절과 "도메인이나 자료 없음"을 가른다.
- 토글 OFF가 기본이라 마이그레이션은 안전(기존 테넌트 무변경). 운영자는 admin에서 켜고 범위를 적는다.
- 백스톱이 모델 응답을 덮으므로, 프롬프트가 약하거나 모델이 "helpful"하게 새도 범위 밖 답은 안 나간다.
- 배경: 이 PRD는 "파란색 설명" 사고에서 출발했고, 탈옥(보안 경계)과 구분되는 스코프(주제) 이슈다.
