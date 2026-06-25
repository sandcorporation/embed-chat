# PRD: 프롬프트 캐싱 안정 prefix — 그래프-플로우 통합 테스트 (FakeLLM 캡처)

Status: ready-for-agent
Labels: ready-for-agent

## Problem Statement

프롬프트 캐싱(ADR-0019)의 핵심 불변식은 "안정 system prefix가 모든 세션·방문자·턴에서 byte-동일"이다.
현재 이 불변식은 `_assemble_lc_messages`를 **손으로 만든 state로 직접 부르는 단위 테스트**
(test_prompt_caching.py)로만 검증된다. 빌드된 그래프(`build_graph`/`run_chat_agent_async`)가 **여러
플로우**(HITL-on/off, 원문 폴백 2회 호출, 영업시간 외, 멀티턴, 주제범위 ON/OFF)를 거치며 LLM에
실제로 보내는 메시지가 안정 prefix를 지키는지는 **테스트 자물쇠가 없다**. 그래서 어떤 플로우가
실수로 휘발성 콘텐츠를 system prefix에 섞어 캐싱을 깨도 현재 테스트는 못 잡는다(예: 최근 추가된
주제범위 `scope_instruction` 주입은 단위로 ADR과 대조만 했을 뿐 통합 검증은 없다).

## Solution

**FakeLLM가 그래프로부터 받는 messages를 캡처**해, `run_chat_agent_async`를 플로우별로 구동하면서
"한 테넌트의 모든 턴·플로우에서 system prefix가 byte-동일하고, 휘발성(RAG·메모리·운영안내)은 trailing
사용자 턴에만 실린다"를 단언한다. 이로써 캐싱 친화 레이아웃이 그래프 종단까지 보존됨을 회귀 가드로
박제한다 — 미래의 어떤 노드/플로우 변경이 prefix를 깨도 즉시 빨간불이 켜진다.

## User Stories

1. As a developer, I want the built graph's LLM-bound messages captured via FakeLLM, so that I can assert what the graph actually sends (not just what the assembly helper produces in isolation).
2. As a developer, I want the system prefix asserted byte-identical across turns of one session, so that multi-turn caching is locked.
3. As a developer, I want the system prefix identical across HITL-on and HITL-off flows (different tool schema, same system), so that the prefix isn't accidentally coupled to schema.
4. As a developer, I want the system prefix identical on the source-fallback second call_llm (RAG grown), so that the fallback path doesn't leak volatile content into system.
5. As a developer, I want the system prefix identical on the off-hours flow (operational notice present), so that the business-hours notice stays in the trailing turn.
6. As a developer, I want the system prefix identical with topic-scope ON vs across its own turns, so that the scope instruction (tenant-invariant) stays in the stable prefix and doesn't break caching.
7. As a developer, I want volatile content (RAG, Visitor Memory, operational notice) asserted absent from the system message in every flow, so that no flow regresses the layout.
8. As a developer, I want volatile content asserted present in the trailing user turn (UNTRUSTED isolation preserved) across flows, so that hardening + caching coexist.
9. As a developer, I want the capture harness reusable (part of the FakeLLM), so that future caching/layout tests can inspect graph-bound messages cheaply.
10. As a developer, I want these tests deterministic (no real LLM), so that they run in CI without external dependencies.
11. As a developer, I want the tests to cover the conversation-history-grows case, so that an appended history keeps the prefix stable (incremental caching).
12. As a developer, I want a clear failure message when a flow breaks the prefix, so that the offending flow is obvious.

## Implementation Decisions

- **캡처형 FakeLLM**: 기존 conftest `_FakeChatLLM`을 확장해 호출별로 `(schema_name, messages)`를 기록하는
  리스트를 둔다. 구조화 호출 4종(complete/stream/acomplete/astream)이 같은 캡처에 적재한다. 기존 동작
  (결정적 응답·in_scope·context_sufficient)은 불변 — 캡처는 부수기록일 뿐이다.
- **검증은 그래프 종단**: `run_chat_agent_async`(빌드된 그래프 ainvoke)를 플로우별로 구동하고, 캡처된
  messages에서 `messages[0]`(system)과 `messages[-1]`(trailing 턴)을 단언한다. 노드/조립 내부가 아니라
  **그래프가 실제로 보낸 것**을 본다.
- **플로우 매트릭스**: ① HITL-on(HITLResponse) ② HITL-off(PlainResponse) ③ 원문 폴백(context_sufficient
  =False → source_search → 2번째 call_llm, rag_chunks 증가) ④ 영업시간 외(operational_notice) ⑤ 멀티턴
  (history 누적) ⑥ 주제범위 ON.
- **불변식**: 한 테넌트(고정 config) 안에서 캡처된 모든 call의 `system` 콘텐츠가 서로 byte-동일.
  휘발성(RAG·메모리·운영안내 텍스트)은 system에 부재, trailing 턴에 존재(+ UNTRUSTED 격리 유지).
- **provider 마커는 범위 밖**: `_mark_cache_breakpoint`(Anthropic cache_control)는 실 `astream_structured`
  안에서 적용되는데 fake가 그 함수를 대체하므로 통합 캡처엔 안 잡힌다. 마커는 이미 단위 테스트가
  커버하므로 이 통합은 **논리 레이아웃**(안정 prefix·휘발성 위치)에 집중한다.
- **production 코드 변경 없음**(테스트·하네스 한정). 캡처 추가만 conftest에.

## Testing Decisions

- **좋은 테스트**: 외부로 관측 가능한 "그래프가 LLM에 보낸 messages"만 검증한다 — 안정 prefix byte-동일,
  휘발성 trailing 위치. LLM 판단 품질·노드 내부 구현은 보지 않는다. LLM만 결정적 Fake(이미 autouse).
- **대상**: 빌드된 그래프(`run_chat_agent_async`)를 캡처형 FakeLLM로 구동한 통합 테스트. 캡처 하네스
  (conftest 확장)도 그 자체로 검증(호출 시 messages가 기록되는지).
- **선례**: `test_prompt_caching`(단위 — 안정 prefix·마커), `test_local_source_fallback`(그래프 + fake로
  폴백 2회 호출), `test_business_hours_gating`(영업시간 외 플로우), `test_chat_session`(멀티턴 체크포인트),
  `test_topic_scope`(scope on/off 그래프 구동).

## Out of Scope

- 실 provider의 캐시 적중(`cached_tokens`) 실측·계측 — 별건(usage 계측 확장).
- 캐싱 레이아웃 자체 변경 — production 코드는 안 건드린다(테스트만).
- Anthropic `cache_control` 마커의 통합 검증 — 단위 테스트가 이미 커버(fake가 boundary를 대체해 통합
  캡처 대상 아님).
- 최소 토큰 임계(작은 프롬프트 no-op)는 provider 행동이라 테스트 대상 아님.

## Further Notes

- 이 테스트는 최근 추가된 주제범위 `scope_instruction`(system 주입)이 캐싱을 안 깬다는 것도 박제한다 —
  단위로 ADR-0019와 대조해 확인했으나 통합 자물쇠가 없던 갭을 메운다.
- 캡처 하네스는 향후 "캐시 분기점 2개" 같은 레이아웃 변경(ADR-0019 Considered Options)을 시도할 때도
  재사용된다.
