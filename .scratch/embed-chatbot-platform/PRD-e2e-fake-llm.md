Status: ready-for-agent

# PRD: E2E 결정적 Fake LLM 서비스

## Problem Statement

E2E 테스트(`hitl.spec.js`, `widget.spec.js`)가 실제 qwen2.5:3b를 통해 chat LLM을 호출하는데, 이 소형 모델의 `needs_hitl` 구조화 판정이 **양방향으로 비결정적**이다:

- "상담원 연결해 주세요"를 약 17% 놓침(false negative) → HITL escalation이 안 생김.
- 평범한 인사 "안녕하세요"를 가끔 escalation함(false positive) → `widget.spec.js`의 "AI 응답" 테스트가 깨짐.

같은 위젯 세션 내 재시도는 모델이 누적 대화 속 자기 응답을 보고 굳어져 효과가 없고, 매 시도 새 세션으로 재시도하는 우회책(`hitl.spec.js`)은 동작하나 느리고 부분적이다. 그 결과 CI에서 E2E HITL/chat 단언이 신뢰할 수 없다.

## Solution

E2E 스택에서 chat LLM을 **결정적 Fake LLM 서비스**(OpenAI 호환 HTTP 서비스)로 교체한다. `api-e2e`/`worker-e2e`의 `OPEN_ROUTER_BASE_URL`을 이 Fake로 돌리면, 위젯·어드민·SSE·DB·임베딩 등 나머지 전 구간은 실제 그대로 두면서 LLM 판정만 결정적이 된다. CLAUDE.md 정책("비결정적 외부 경계는 결정적 Fake/Mock으로 교체")의 E2E판이다.

결과적으로 E2E HITL/chat 테스트는 재시도 없이 결정적으로 통과하고, qwen이 E2E 경로에서 빠져 GPU VRAM 경합과 init 시간도 준다.

## User Stories

1. As a developer, I want E2E HITL tests to pass deterministically, so that a red E2E run means a real regression, not model variance.
2. As a developer, I want the widget "AI 응답" E2E test to reliably get a normal assistant reply for a greeting, so that it isn't broken by false escalations.
3. As a developer, I want the admin claim E2E test to reliably find a pending escalation when the visitor says "상담원", so that the HITL claim flow is exercised every run.
4. As a developer, I want the Fake LLM to live in its own container wired via compose, so that swapping it in/out is a config change, not a code change.
5. As a developer, I want everything except the LLM (widget, admin, SSE, Redis, Postgres, embeddings) to stay real in E2E, so that integration coverage is preserved.
6. As a developer, I want the Fake to decide `needs_hitl` from the latest user message keyword(상담원), so that both escalation and non-escalation paths are exercised deterministically.
7. As a developer, I want the Fake to also serve plain text completions(메모리 추출 등), so that non-structured LLM calls in the E2E path don't fail.
8. As a maintainer, I want production LLM behavior and unit-test fakes unchanged, so that this only affects the E2E stack.
9. As a developer, I want qwen no longer pulled for E2E, so that test init is faster and GPU memory is freed (embeddings bge-m3는 유지).
10. As a developer, I want the `hitl.spec.js` fresh-session retry workaround removed once the Fake is in, so that the spec is simple and fast.

## Implementation Decisions

### Deep module: Fake LLM 서비스 (신설 컨테이너)

OpenAI Chat Completions 호환 HTTP 서비스를 신설한다. 좁은 인터페이스(`POST /v1/chat/completions`, 필요 시 `GET /v1/models`)만 노출하며, 내부적으로 요청을 보고 결정적으로 응답한다.

- **구조화 출력 요청 구분**: 요청에 `tools`/`tool_choice`가 있으면(langchain `with_structured_output`의 function_calling 방식) → `choices[0].message.tool_calls[0].function.arguments`에 스키마 JSON을 담아 반환하고 `finish_reason="tool_calls"`. 없으면(일반 `.invoke()`) → `choices[0].message.content`에 텍스트 반환.
- **판정 규칙(결정적)**: 메시지 중 마지막 사용자(role=user) 발화에 인간 상담원 키워드(`상담원`)가 있으면 `needs_hitl=true`(빈 response, 사유 포함), 없으면 `needs_hitl=false` + 카난 한국어 응답. system 프롬프트는 판정에서 제외(상담원 안내문 포함 가능).
- **일반 completion**: 카난 텍스트(예: 빈 facts `{}` 또는 고정 응답)를 반환. 정확한 응답 스키마(tool_call vs content)는 구현 중 langchain-openai 0.2.x가 보내는 실제 요청을 로깅해 확정한다.
- 모델명·`api_key`·`extra_body`는 무시한다.

### Compose 배선 (docker-compose.test.yml)

- 신설 서비스(예: `fake-llm`)를 추가하고 healthcheck를 둔다.
- `api-e2e`, `worker-e2e`의 `OPEN_ROUTER_BASE_URL`을 Fake LLM(`http://fake-llm:<port>/v1`)으로 변경. `OPEN_ROUTER_API_KEY`는 더미 유지.
- 임베딩 경로(`OLLAMA_BASE_URL`, bge-m3)는 변경하지 않는다.
- `ollama-test-init`에서 `qwen2.5:3b` pull 제거(bge-m3만 유지). 단위 `test` 서비스와 E2E 모두 더 이상 qwen을 호출하지 않으므로 안전.

### E2E 스펙 정리

- `hitl.spec.js`: 매 시도 새 세션 재시도 우회책 제거, 단일 escalation → 단언으로 단순화. test 독립성은 유지(각 테스트가 자체 세션 생성).
- `widget.spec.js`: "AI 응답" 테스트가 인사말 → `needs_hitl=false` → assistant 응답을 결정적으로 받도록 그대로 동작(이제 Fake가 보장).

## Testing Decisions

좋은 테스트는 외부 모델의 판단이 아니라 우리 시스템의 동작을 검증한다. Fake LLM로 LLM 변덕을 제거하면 E2E는 "방문자가 상담원을 요청하면 escalation·SSE·어드민 claim이 동작한다", "인사하면 AI 응답이 표시된다" 같은 우리 코드 동작을 결정적으로 검증한다.

- 검증 대상: `hitl.spec.js`(위젯 escalation, 어드민 claim/resolve), `widget.spec.js`(AI 응답, 기타 위젯 플로우).
- Fake LLM 서비스 자체의 정합성은 이 E2E 스펙들이 통과하는 것으로 검증한다(별도 단위 테스트는 선택).
- 단위/통합 레이어의 결정적 HITL 커버리지는 이미 conftest Fake로 존재(issues 55/56) — 중복 구현하지 않는다.
- Prior art: 기존 `e2e/tests/*.spec.js`, 특히 `hitl.spec.js`/`widget.spec.js`.

## Out of Scope

- 프로덕션 LLM 제공자/모델 변경.
- 단위/통합 테스트의 LLM mock(이미 conftest Fake로 완료).
- 임베딩(bge-m3) 경로 변경.
- Fake LLM에 실제 추론/지능 부여(순수 규칙 기반 결정적 응답만).

## Further Notes

langchain-openai 0.2.x의 `with_structured_output`는 기본적으로 function_calling(tools) 방식을 사용한다. Fake 구현 시 실제 요청을 1회 로깅해 tool_call 응답 형식을 정확히 맞추는 것이 핵심 리스크 포인트다. Fake는 의도적으로 "멍청하게" 규칙 기반이어야 하며, 절대 외부 호출을 하지 않는다.
