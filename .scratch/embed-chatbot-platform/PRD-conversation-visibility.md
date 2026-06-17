# PRD: 대화 가시성 + LangGraph Checkpoint

Status: ready-for-agent

## Problem Statement

세 가지 운영 문제가 있다.

1. **HITL 상담원의 맥락 부재**: 상담원이 에스컬레이션을 수락해도 AI와 Visitor가 나눈 이전 대화를 볼 수 없다. 맥락 없이 상담을 시작해야 하고, Visitor가 HITL 모드에서 새 메시지를 보내도 상담원 화면에 실시간으로 나타나지 않아 상담원이 별도로 새로고침을 해야 한다.

2. **Visitor 대화 이력 조회 불가**: TenantAgent가 특정 Visitor의 전체 대화 이력을 볼 방법이 없다. Memory 탭은 Visitor ID를 직접 타이핑해야 하고, 어떤 Visitor가 존재하는지 목록조차 제공되지 않는다. 세션 히스토리와 Memory가 완전히 분리돼 있어 Visitor 전체 상황을 한눈에 파악할 수 없다.

3. **LangGraph state 비지속**: 매 LLM 호출마다 `ChatMessage`에서 전체 히스토리를 수동으로 로드해 그래프 초기 state로 주입한다. LangGraph Checkpoint가 없어 그래프 실행 중단 시 state가 유실되고, state 전체(RAG 청크, assembled prompt 포함)를 나중에 디버깅할 수 없다.

## Solution

- **HITL 히스토리 + 실시간**: EscalationCard에 이전 대화 히스토리를 표시하고, Visitor가 HITL 모드에서 보내는 메시지를 `hitl:{tenant_id}` 채널을 통해 상담원에게 실시간 전달한다.
- **Visitors 탭**: Memory 탭을 "Visitors" 탭으로 교체. Visitor 목록(검색 포함) → 세션 목록 → 대화 상세 + Memory 드릴다운 구조.
- **LangGraph Checkpoint**: `PostgresSaver`를 그래프에 연결해 `thread_id = session_id`로 state를 자동 저장·복원. 수동 히스토리 로드를 제거하고 LangGraph가 대화 연속성을 직접 관리.

## User Stories

1. As a TenantAgent, I want to see the full AI conversation history when I claim an escalation, so that I can understand the context without asking the Visitor to repeat themselves.
2. As a TenantAgent, I want to see the escalation history even before claiming it, so that I can decide whether I'm the right person to handle it.
3. As a TenantAgent, I want to see new Visitor messages appear in real-time in the escalation card, so that I don't have to refresh the page to follow the conversation.
4. As a TenantAgent, I want the conversation to feel continuous — AI messages, Visitor messages, and my own replies all in one thread, so that the handoff is seamless.
5. As a TenantAgent, I want to browse a list of all Visitors, so that I can look up any Visitor without knowing their ID in advance.
6. As a TenantAgent, I want to search Visitors by ID, so that I can quickly find a specific customer when I have their identifier.
7. As a TenantAgent, I want to see all ChatSessions for a Visitor in reverse chronological order, so that I can review how their usage has changed over time.
8. As a TenantAgent, I want to click into a session and see the full conversation, so that I can understand exactly what was discussed.
9. As a TenantAgent, I want to see a Visitor's Memory alongside their session history in one view, so that I can understand what the system knows about them and correct errors.
10. As a TenantAgent, I want to edit or delete a Visitor Memory entry from the Visitor detail view, so that I don't need a separate tab to manage memory.
11. As a Visitor, I want my messages to reach the human agent immediately when I'm in HITL mode, so that I don't feel like I'm talking into a void.
12. As a Developer, I want LangGraph to checkpoint conversation state automatically, so that a graph crash doesn't lose partial state and I can replay graph executions for debugging.
13. As a Developer, I want to remove the manual history-loading loop from `run_chat_agent`, so that the code is simpler and there's a single source of truth for conversation state.

## Implementation Decisions

### HITL 대화 히스토리 API

- 새 엔드포인트: `GET /api/tenant/escalations/{escalation_id}/messages`
  - TenantAgent 인증
  - 해당 Escalation의 `session_id`로 `ChatMessage`를 `created_at` 오름차순 조회
  - 반환: `[{role, content, created_at}]`
- EscalationCard가 마운트될 때(pending/claimed 무관) 이 엔드포인트를 호출해 히스토리를 로드
- 로드된 히스토리를 카드 내 스크롤 가능한 대화 뷰로 표시 (role별 말풍선 스타일)

### Visitor → Agent 실시간 메시지

- `send_message` 뷰에서 `session.is_hitl == True`일 때:
  ```
  hitl:{tenant_id} 채널에 발행:
  {"type": "visitor_message", "session_id": "...", "content": "..."}
  ```
- 상담원 SSE(`escalation_stream`)는 이미 `hitl:{tenant_id}` 채널을 구독 중
- 프론트: `visitor_message` 이벤트의 `session_id`가 일치하는 EscalationCard에 메시지를 append
- Agent가 메시지를 보낼 때도 EscalationCard의 로컬 state에 append (기존 `sendEscalationMessage` 응답 후)

### Visitors 탭 API

- Visitor 목록: `GET /api/tenant/visitors/`
  - 쿼리 파라미터: `search` (visitor_id contains)
  - `ChatSession`을 `visitor_id`로 group, 각 Visitor의 마지막 활동 시각과 세션 수 반환
  - 반환: `[{visitor_id, session_count, last_active_at}]`, `last_active_at` 내림차순
- Visitor 세션 목록: `GET /api/tenant/visitors/{visitor_id}/sessions/`
  - 기존 `memory_router` 경로(`/api/tenant/visitors/{visitor_id}/...`)와 동일 prefix 사용
  - 반환: `[{id, created_at, ended_at, is_hitl, message_count}]`, `created_at` 내림차순
- 세션 메시지: `GET /api/tenant/sessions/{session_id}/messages/`
  - 새 라우터 또는 기존 `chat_router`에 추가
  - 반환: `[{id, role, content, created_at}]`

### Visitors 탭 UI (Memory 탭 교체)

- 탭 이름: "Memory" → "Visitors"
- **드릴다운 A (순차 교체)**: `view` state로 관리
  - `list`: Visitor 목록 + 검색창, 최근 활동순
  - `visitor`: Visitor 상세 — 세션 목록(상단) + Memory(하단), "뒤로" 버튼
  - `session`: 세션 대화 상세, "뒤로" 버튼
- Memory 수정·삭제는 `visitor` 뷰에서 인라인으로 제공 (기존 로직 재사용)

### LangGraph Checkpoint

- 패키지: `langgraph-checkpoint-postgres`
- `PostgresSaver`를 `build_graph()`에 주입, `config={"configurable": {"thread_id": session_id}}`로 호출
- `run_chat_agent`에서 수동 히스토리 로드 코드 제거:
  ```python
  # 제거:
  history = [{"role": msg.role, "content": msg.content} for msg in session.messages.order_by("created_at")]
  # initial_state의 "messages": []로 변경 (Checkpoint가 복원)
  ```
- `ChatMessage` 저장(`save_messages_node`)은 유지 — Visitors 탭 API가 이를 쿼리함
- LangGraph Checkpoint 테이블(`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`)은 `PostgresSaver.setup()` 또는 마이그레이션으로 생성

### Memory 버그 수정

- `delete_memory_entry`: `response={204: None, 404: dict}` 로 스키마 수정
- `schedule_memory_extraction`: LLM 응답에서 코드 펜스(` ```json ... ``` `)를 strip한 뒤 `json.loads` 실행. strip 실패 시 Exception 대신 명시적 로깅.

## Testing Decisions

좋은 테스트는 HTTP API와 DB state만 검증한다. 내부 LangGraph state나 Redis pub/sub 구현은 직접 검증하지 않는다.

- **HITL 히스토리 API**: `GET /api/tenant/escalations/{id}/messages` 가 해당 세션의 ChatMessage를 반환하는지 검증. 선례: `test_list_escalations_returns_pending_and_claimed`.
- **Visitor → Agent 실시간**: Visitor가 HITL 메시지 전송 후 Redis `hitl:{tenant_id}` 채널에 `visitor_message` 이벤트가 발행됐는지 검증. 선례: `test_typing_indicator_publishes_sse_event`.
- **Visitors 탭 API**: `GET /api/tenant/visitors/` 검색, `GET /api/tenant/visitors/{id}/sessions/`, `GET /api/tenant/sessions/{id}/messages/` 응답 구조 검증. 선례: `test_list_escalations_returns_pending_and_claimed`.
- **LangGraph Checkpoint**: `run_chat_agent`를 두 번 호출한 후 두 번째 호출에서 첫 번째 대화 내용이 컨텍스트에 포함된 응답이 나오는지 검증 (히스토리 연속성). 선례: `test_multi_turn_creates_multiple_assistant_replies`.
- **Memory 버그**: DELETE 시 존재하지 않는 memory_id로 요청하면 404 반환 검증. 선례: `test_delete_document`.
- AI 타이핑 인디케이터, 어드민 UI 레이아웃은 백엔드 테스트 범위 외.

## Out of Scope

- Operator 대시보드 (대화 데이터 조회)
- LangGraph Studio 연동 UI
- Visitor 목록 페이지네이션 (검색으로 대체)
- Visitor가 상담원 타이핑 중임을 알리는 역방향 인디케이터
- 세션 대화 내보내기 (CSV, PDF 등)
- Visitor 간 비교 분석

## Further Notes

- LangGraph Checkpoint 도입 후 기존 `ChatMessage`에서 히스토리를 로드하던 방식이 제거되므로, 기존 세션(Checkpoint 없는 세션)에서 `run_chat_agent`를 호출하면 빈 state에서 시작한다. 이는 기존 세션에 대한 컨텍스트 손실이므로, 배포 전에 기존 `ChatMessage`를 Checkpoint로 마이그레이션하는 방안 또는 fallback 로직을 고려해야 한다.
- `schedule_memory_extraction` 태스크는 `session.tenant` FK가 없어 항상 `settings.OPEN_ROUTER_DEFAULT_MODEL`을 쓴다. Memory 버그 수정 시 함께 수정.
