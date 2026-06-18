Status: ready-for-agent

# PRD: 위젯 브랜드 텍스트 + Tenant HITL 토글 (A2 + A3)

## Problem Statement

(A2) Tenant는 위젯 상단에 자기 브랜드를 보여주고 싶지만 헤더에는 "AI 상담"이라는 고정 텍스트만 있다. (A3) HITL(사람 상담원 전환)은 항상 켜져 있어, 상담원을 둘 수 없는 Tenant도 AI가 escalation을 시도해 Visitor가 응대 없는 "상담원 연결 중"에 갇힐 수 있다. Tenant가 HITL 사용 여부를 직접 고르지 못한다.

## Solution

(A2) `TenantConfig`에 `brand_name` **텍스트** 필드를 추가해 위젯 헤더 상단에 표시한다(이미지 로고 아님). AI/사람 상태는 보조 텍스트+점으로 강등한다. (A3) `TenantConfig`에 `hitl_enabled` 토글을 추가하고, 불리언에 따라 **에이전트 그래프 토폴로지를 다르게 컴파일**한다 — HITL-OFF 그래프는 escalation 분기 자체가 없어 AI가 절대 사람에게 넘기지 않는다.

## User Stories

1. Tenant로서, 위젯 헤더에 내 브랜드 텍스트(예: "ABC쇼핑 고객센터")가 뜨길 바란다.
2. Tenant로서, 브랜드 텍스트를 어드민에서 입력·수정하고 싶다.
3. Visitor로서, 브랜드 텍스트가 있어도 지금 AI인지 사람인지(상태)를 여전히 알 수 있길 바란다.
4. Tenant로서, 브랜드 텍스트를 비워두면 기존처럼 상태 텍스트만 보이길 바란다.
5. Visitor로서, 브랜드 텍스트가 위젯 연결 시 바로 표시되길(connected 이벤트) 바란다.
6. Tenant로서, 상담원을 운영하지 않으므로 HITL을 끄고 AI 전용으로 운영하고 싶다.
7. Tenant로서, HITL을 켜면 기존처럼 AI가 불확실하거나 "상담원" 요청 시 escalation 되길 바란다(기본 켜짐).
8. HITL을 끈 Tenant의 Visitor로서, "상담원"이라고 입력해도 AI가 그냥 답하고 응대 없는 대기에 갇히지 않길 바란다.
9. HITL을 끈 Tenant로서, AI가 "연결해드리겠습니다" 같은 지키지 못할 전환 멘트를 만들지 않길 바란다.
10. HITL을 켠 Tenant로서, escalation·웹훅·HumanTurn 흐름이 그대로 동작하길 바란다.
11. Operator로서, HITL 토글이 그래프를 다르게 로드하는 방식이라 죽은 분기 없이 깔끔하길 바란다.
12. Tenant로서, HITL을 껐다 켜면 다음 대화부터 반영되길 바란다.

## Implementation Decisions

- **`TenantConfig.brand_name`**: 텍스트 필드(이미지 아님). 위젯 헤더 메인 타이틀. SSE `connected` 이벤트 payload에 포함되어 위젯에 전달. 비면 상태 텍스트만.
- **위젯 헤더 렌더**: `brand_name`을 메인 타이틀로, AI/사람 상태("AI 상담"/"상담원 연결 중")를 보조 텍스트+색 점으로 강등.
- **`TenantConfig.hitl_enabled`**: 불리언, 기본 True(현재 동작·기존 테스트 보존).
- **`build_graph(hitl_enabled)` 분기**: 불리언으로 그래프 토폴로지 + call_llm 스키마를 분기.
  - HITL-ON: call_llm이 `HITLResponse`(response·needs_hitl·hitl_reason) → `_route_hitl` → escalation | save.
  - HITL-OFF: call_llm이 **response-only 스키마**(needs_hitl 필드 없음) → 곧장 save_messages. escalation 노드 없음. needs_hitl을 구조적으로 표현할 수 없어 전환 멘트 누수가 불가능.
- **선택 그래프 로드**: `run_chat_agent`가 이미 로드하는 `config.hitl_enabled`로 `build_graph` 분기.
- **프롬프트 보조 억제(belt-and-suspenders)**: HITL-OFF 시 시스템 프롬프트에 "사람 상담원 연결 불가"를 명시(키워드 케이스 대비).

## Testing Decisions

좋은 테스트는 외부 행위만 검증한다. 실제 객체, LLM 경계만 Fake, 독립. 최대 커버리지.

- **`build_graph(hitl_enabled)` 분기** [그래프 동작]: HITL-OFF에서 Fake가 needs_hitl=True를 강제해도 **escalation이 생성되지 않고** assistant 메시지가 저장된다. HITL-ON에서는 기존대로 escalation 생성(회귀). "상담원" 키워드 입력 시 OFF→답변/ON→escalation.
- **HITL-OFF 스키마**: response-only 경로에서 전환 멘트 없이 응답이 저장된다.
- **brand_name 전달**: `connected` 이벤트 payload에 `brand_name` 포함, 비면 미포함(또는 빈 값) — Redis 구독으로 검증.
- **기본값 회귀**: `hitl_enabled` 기본 True라 기존 HITL 테스트(`tests/test_hitl.py`) 전부 통과.
- Prior art: `tests/test_hitl.py`(run_chat_agent + escalation), `tests/test_chat_session.py`(connected 이벤트 payload), `tests/conftest.py`(fake_chat_llm.override).

## Out of Scope

- 이미지 로고 업로드/URL(텍스트 brand_name만).
- 위젯 헤더의 추가 스타일링·테마.
- HITL-OFF에서 "상담원 없음" 안내문 커스터마이즈(단순히 AI가 답변).

## Further Notes

- A1과 같은 위젯/TenantConfig/connected-이벤트 표면을 공유하므로 함께 구현하면 효율적이다.
- HITL-OFF에서 스키마까지 가르는 이유: 라우팅 가드만으로는 LLM이 만든 전환 멘트가 누수될 수 있어, 스키마에 needs_hitl 필드를 없애 구조적으로 차단한다.
