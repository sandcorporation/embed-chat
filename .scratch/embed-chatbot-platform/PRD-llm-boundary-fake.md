Status: ready-for-agent

# PRD: LLM 호출 경계 격리 (단위 테스트 Fake)

## Problem Statement

단위/통합 테스트(`docker compose ... run test`)가 chat LLM을 로컬 ollama(`qwen2.5:3b`)로 실제 호출한다. 이 때문에:

- 3B 소형 모델의 구조화 출력(`needs_hitl` 판단)이 불안정해, 전체 백엔드 스위트에서 `test_hitl.py`/`test_webhook.py` 등이 **비결정적으로 실패**한다 (재실행마다 1~4개, 격리 실행 시 통과).
- chat LLM이 단일 8GB GPU에서 bge-m3·PaddleOCR와 VRAM을 경합한다.
- 테스트가 LLM의 "판단 품질"에 의존해, 정작 검증하려는 우리 코드(Escalation 생성·SSE 발행·웹훅·메시지 저장·Visitor Memory 추출)의 동작이 LLM 변덕에 가려진다.

## Solution

LLM 호출을 단일 경계(seam)로 캡슐화하고, 단위/통합 테스트에서는 그 경계를 **결정적 Fake**로 교체한다. 테스트는 더 이상 LLM 판단에 의존하지 않고, "LLM이 X를 반환했을 때 시스템이 Y를 한다"는 우리 코드의 동작만 결정적으로 검증한다. E2E는 변경 없이 실제 LLM(qwen)을 계속 사용한다(블랙박스 검증).

TDD 스킬 `mocking.md`에 따라 LLM(OpenRouter)은 mock 가능한 외부 API 경계이며, `CLAUDE.md`의 "내부 mock 금지" 규칙과 충돌하지 않는다.

## User Stories

1. As a developer, I want the backend test suite to pass deterministically, so that a red run reliably means a real regression.
2. As a developer, I want HITL/escalation tests to verify system behavior given a controlled LLM verdict, so that flaky model judgment can't break the build.
3. As a developer, I want the LLM call isolated behind one seam, so that swapping providers or stubbing in tests touches one place.
4. As a developer, I want unit tests to run without invoking qwen, so that GPU VRAM contention no longer makes tests flaky.
5. As a developer, I want the Fake to return `needs_hitl=true` when the visitor message contains the human-agent keyword(상담원), so that escalation-path tests stay meaningful without a real model.
6. As a developer, I want the Fake to return a normal assistant response with `needs_hitl=false` for ordinary messages, so that the non-escalation path is exercised deterministically.
7. As a developer, I want the Visitor Memory extraction LLM call to go through the same seam, so that memory-extraction tests are deterministic too.
8. As a developer, I want E2E tests to keep using the real LLM, so that end-to-end behavior with an actual model is still covered.
9. As a maintainer, I want production LLM behavior unchanged, so that this refactor carries no runtime risk.

## Implementation Decisions

### Deep module: LLM 경계 (`apps/agent/llm.py`, 신설)

LLM 호출을 좁은 인터페이스 뒤로 숨기는 deep module을 신설한다. 두 함수만 노출:

- `complete_structured(model_id, messages, schema)` → `schema` 인스턴스 반환. 내부적으로 `ChatOpenAI(...).with_structured_output(schema).invoke(messages)`. `HITLResponse` 구조화 출력에 사용.
- `complete_text(model_id, messages)` → 문자열(LLM 응답 본문) 반환. Visitor Memory 추출에 사용.

프로덕션 구현은 기존과 동일하게 `OPEN_ROUTER_*` 설정으로 `ChatOpenAI`를 만든다. 호출부의 모든 `ChatOpenAI` 직접 생성은 제거된다.

### 호출부 변경

- chat 그래프의 `call_llm_structured`는 `complete_structured(model_id, lc_messages, HITLResponse)`를 호출한다. 반환값으로 토큰 발행/상태 갱신하는 기존 로직은 유지.
- Visitor Memory 추출 태스크는 `complete_text(model_id, [prompt])`를 호출한다. 코드펜스 제거·JSON 파싱 로직은 유지.
- seam은 **모듈 속성으로 호출**한다(예: `from apps.agent import llm` 후 `llm.complete_structured(...)`)—테스트에서 `monkeypatch.setattr`로 교체 가능하도록.

### 테스트 Fake (autouse fixture)

`conftest.py`에 autouse fixture를 추가해 두 seam 함수를 결정적 Fake로 교체한다:

- `complete_structured`: 입력 메시지에 인간 상담원 키워드(`상담원`)가 포함되면 `HITLResponse(response="", needs_hitl=True, hitl_reason=...)`, 아니면 `HITLResponse(response=<카난 응답>, needs_hitl=False)`.
- `complete_text`: 결정적 facts JSON 문자열(예: `{}` 또는 고정 키/값)을 반환.

Fake는 langchain 메시지 객체에서 텍스트를 읽어 키워드를 판정한다. 별도 토글 없이 항상 적용되며, 테스트는 필요 시 fixture가 노출한 핸들로 Fake의 반환을 조정할 수 있다.

### 범위 밖 인프라

- `ollama-test-init`의 `qwen2.5:3b` pull은 **유지**한다(E2E가 실제 LLM을 사용). 임베딩(bge-m3)도 변경 없이 ollama 유지.
- 단위 테스트 실행 시 LLM 호출이 사라지므로 qwen이 VRAM에 로드되지 않아 경합이 해소된다.

## Testing Decisions

좋은 테스트는 LLM의 판단이 아니라 **우리 코드의 외부 동작**을 검증한다: 통제된 LLM 응답이 주어졌을 때 Escalation 생성·`is_hitl` 전환·`hitl_start`/`hitl_new` SSE 발행·웹훅 디스패치·ChatMessage 저장·Visitor Memory upsert가 일어나는가.

전환 대상 테스트(현재 실제 LLM 의존):

- `test_hitl.py` — escalation 생성, 비-escalation 메시지 저장, `hitl_start` SSE, resolved 후 AI 재개 (4건)
- `test_webhook.py` — agent가 생성한 escalation 시 웹훅 발송 경로 (`run_chat_agent` 사용 건)
- `test_chat_session.py` — `run_chat_agent` 후 Checkpoint 조회/누적 (3건)
- `test_memory.py` — `schedule_memory_extraction` 동작 (1건)

이 테스트들은 동작을 그대로 검증하되, Fake로 LLM 변덕을 제거해 결정적으로 만든다. NO-MOCK 원칙은 내부 협력자에 해당하며, LLM은 외부 API 경계이므로 Fake 교체가 허용된다.

Prior art: 기존 `test_hitl.py`/`test_webhook.py`/`test_memory.py`/`test_chat_session.py`의 통합 스타일 테스트.

## Out of Scope

- 프로덕션 LLM 제공자/모델 변경
- 임베딩(bge-m3) 경로 변경
- E2E 테스트의 LLM mock (E2E는 실제 qwen 유지)
- 토큰 스트리밍(SSE 토큰) 자체의 정합성 재설계

## Further Notes

Fake가 항상 적용되므로 conftest의 기존 system_prompt(상담원 지시문)는 더 이상 LLM 판정에 영향을 주지 않으나, 그대로 두어도 무해하다. seam을 모듈 속성으로 호출하는 점만 지키면 production 동작은 완전히 동일하다.
