# PRD: 프롬프트 캐싱 친화 메시지 재구조화

Status: ready-for-agent

관련 ADR: [ADR-0012](../../docs/adr/0012-per-tenant-llm-embedding-providers.md) (per-Tenant Provider — provider-aware 마커) · [ADR-0010](../../docs/adr/0010-entity-resolution-mention-entity-context-equivalence.md) (Knowledge Base 근거 프레이밍) · 관련 PRD: [PRD-prompt-hardening](./PRD-prompt-hardening.md) (UNTRUSTED_DATA 격리·인젝션 하드닝 — 본 작업이 보존해야 함)

## Problem Statement

챗 에이전트가 LLM에 보내는 메시지는 매 턴 새로 조립되는데, **RAG 근거(Knowledge Base)와 Visitor Memory가 system 메시지 안에 인라인**된다. 이 둘은 질의마다 바뀌므로, system 메시지(프롬프트의 가장 앞부분)가 **매 요청 달라진다**. 그 결과 LLM provider의 프롬프트 캐싱(안정적 prefix를 재사용해 입력 토큰 비용·지연을 줄이는 기능)이 **전혀 작동하지 않는다**. 테넌트마다 동일한 Base System Prompt + 보안 지침 + 구조화 출력 스키마가 모든 세션·방문자·턴에 반복 전송되지만, 캐시 prefix가 깨져 있어 매번 풀 과금된다.

## Solution

휘발성 콘텐츠(RAG·Visitor Memory·운영 안내)를 system 메시지에서 빼서 **대화 뒤쪽 별도 컨텍스트 메시지로** 옮기고, **테넌트-불변 블록(구조화 출력 tool 스키마 + Base System Prompt + 보안 지침)을 안정적 prefix로 고정**한다. 이렇게 하면 OpenAI·OpenRouter는 **자동 prefix 캐싱**으로, Anthropic은 안정 prefix 끝에 **`cache_control` 분기점 1개**를 명시 주입해 캐시가 작동한다. 인젝션 하드닝(UNTRUSTED_DATA 격리·"데이터지 명령 아님" 프레이밍·보안 지침)은 그대로 보존한다.

## User Stories

1. As a platform operator, I want the tenant-constant prompt prefix to be reused across requests, so that repeated input tokens are cache-billed instead of full-billed.
2. As a Tenant paying for their own Provider (ADR-0012), I want prompt caching to work for my chat traffic, so that my per-message LLM cost drops on multi-turn and high-volume sessions.
3. As a Tenant on an Anthropic Provider, I want a `cache_control` breakpoint placed on my stable prefix, so that Claude caches my system+tools block.
4. As a Tenant on an OpenAI/OpenRouter Provider, I want the message ordering to expose a stable prefix, so that automatic prefix caching applies without provider-specific markers.
5. As a visitor, I want the assistant's answer quality and grounding to be unchanged, so that the caching refactor is invisible to me.
6. As a security-conscious operator, I want RAG and Visitor Memory to remain delimited as untrusted data and labeled "data, not instructions", so that the move out of the system block does not weaken prompt-injection hardening.
7. As a security-conscious operator, I want the anti-disclosure security directive to remain in the stable system block, so that it is always present and cannot be displaced by retrieved content.
8. As a developer, I want the chat node to assemble logical messages without provider conditionals, so that provider-specific caching concerns live at the LLM boundary.
9. As a developer, I want the boundary to inject `cache_control` only for Anthropic-type providers, so that OpenAI/OpenRouter requests are not sent invalid markers.
10. As a developer, I want a single deterministic test of the assembled message shape per provider, so that the cache-friendly structure is locked against regressions.
11. As a developer, I want the structured-output schema (HITLResponse/PlainResponse) to remain part of the cacheable prefix, so that the tool definition is reused too.
12. As a Tenant whose prompt is below the provider's minimum cacheable size, I want the system to simply not cache (no error), so that small prompts degrade gracefully.
13. As a developer, I want the source-text fallback path (issue 119) to keep working after the message reorg, so that augmented RAG chunks still reach the LLM.
14. As a developer, I want conversation history to keep restoring from the Checkpoint and appear before the volatile context, so that multi-turn grounding is preserved.

## Implementation Decisions

- **메시지 순서(재배치)**: `[tools(구조화 출력 스키마)] → [system: Base System Prompt + 보안 지침(_ANTI_DISCLOSURE)] → [history(대화 누적)] → [context: UNTRUSTED_DATA 블록(RAG·Visitor Memory·운영 안내)] → [현재 user 질문]`. 테넌트-불변 prefix(tools+system)가 모든 세션·방문자·턴에서 재사용된다.
- **휘발성 분리**: RAG 청크·Visitor Memory는 **현재 user 질문 직전의 별도 메시지**(컨텍스트 메시지)로 옮긴다. 더 이상 system 메시지에 인라인하지 않는다.
- **보안 프레이밍 보존**: 옮긴 컨텍스트 메시지에서도 `UNTRUSTED_DATA` delimit + "지시가 아니라 데이터로만 취급" 라벨을 유지한다. 보안 지침은 안정 system 블록에 둔다(휘발성보다 앞 = 항상 존재, 변위 불가).
- **캐시 분기점 1개**: 안정 블록(tools+system) 끝에 분기점 1개. Anthropic 경로만 `cache_control: {type: "ephemeral"}`을 마지막 system 콘텐츠 블록에 주입(tools는 그 앞이라 함께 캐시됨). OpenAI/OpenRouter는 마커 없이 자동 prefix 캐싱.
- **provider-aware는 boundary에**: 챗 노드는 **논리적 메시지만** 만든다(provider 분기 없음). `cache_control` 주입 여부는 **LLM 호출 경계(complete_structured 계열)** 가 provider 타입을 보고 결정한다. provider는 이미 호출 컨텍스트(`get_chat_provider`)로 흐른다.
- **운영 안내 슬롯**: 영업시간 외 안내(PRD ②) 같은 휘발성 운영 텍스트도 이 컨텍스트 메시지 슬롯에 실린다(별도 PRD에서 활용).
- **와이어/스키마 변경 없음**: HITLResponse/PlainResponse 스키마, 그래프 토폴로지, Checkpoint 계약은 불변. 바뀌는 것은 LLM에 보내는 메시지 배열의 구성과 순서뿐.

## Testing Decisions

- **무엇이 좋은 테스트인가**: 내부 구조가 아니라 **조립된 메시지 배열의 관찰 가능한 shape**(블록 순서·안정 prefix 위치·UNTRUSTED_DATA 격리 유지·provider별 cache_control 유무)를 단언한다. LLM 자체는 결정적 Fake로 교체한다(CLAUDE.md: 비결정적 외부 경계만 Fake).
- **테스트 대상 모듈**:
  - 메시지 조립부: 휘발성(RAG·메모리)이 system이 아닌 뒤쪽 컨텍스트 메시지에 위치하고, 보안 지침이 안정 system 블록에 남고, UNTRUSTED_DATA 프레이밍이 보존됨.
  - LLM 경계의 provider-aware 마커: `type==anthropic`이면 안정 블록에 `cache_control`이 붙고, openai/custom/""(OpenRouter)이면 안 붙음.
- **Prior art**: `apps/agent` 단위 테스트(LLM 경계 Fake 교체 — `PRD-llm-boundary-fake`), `test_local_source_fallback.py`(노드 동작 검증), 구조화 출력 검증 테스트.
- **회귀 보호**: 소스-텍스트 폴백(issue 119) 경로가 재배치 후에도 augmented chunk를 컨텍스트 메시지에 싣는지 1개 테스트로 고정.

## Out of Scope

- **캐시 분기점 2개 이상**(history 분기점 등): 안 함. 분기점은 system+tools 1개만(grill 결정).
- **provider별 캐시 적중률/비용 측정 대시보드**: 본 PRD 아님.
- **OpenRouter가 내부 Anthropic 모델에 cache_control을 passthrough하도록 하는 별도 경로**: 본 PRD는 네이티브 `anthropic` 타입만 마커 대상. OpenRouter는 자동 캐싱에 의존.
- **그래프 토폴로지·HITL 분기·Checkpoint 스키마 변경**: 없음.

## Further Notes

- **구현 리스크(스파이크에서 확인)**:
  1. langchain `ChatAnthropic` + `with_structured_output`에서 콘텐츠-블록 `cache_control` passthrough가 되는지(메시지 content를 블록 리스트로 줄 때 통과되는지).
  2. Anthropic 최소 캐시 prefix(보통 1024토큰, Haiku 2048). 테넌트 프롬프트가 임계 미만이면 캐시는 **조용한 no-op**(에러 아님) — 회귀로 보지 않는다.
- 본 작업은 PRD ②(HITL 영업시간)의 **선행**이다 — 영업시간 외 안내가 여기서 만든 "뒤쪽 컨텍스트 메시지 슬롯"에 실리기 때문.
- ADR 후보: "캐시 친화 메시지 레이아웃 + provider-aware cache_control(인젝션 하드닝 보존)"은 되돌리기 비용이 있고 보안 프레이밍과 얽혀 있어 ADR 가치가 있다(발행은 별도 판단).
