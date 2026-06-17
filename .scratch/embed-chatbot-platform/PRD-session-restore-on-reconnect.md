# PRD: 페이지 새로고침 시 ChatSession 상태 복원

Status: ready-for-agent

## Problem Statement

Visitor가 채팅 도중 페이지를 새로 고침하면 대화 내역과 HITL 상태가 모두 사라진다.
특히 HITL 상담 중 새로고침하면 위젯이 "AI 상담" 모드로 초기화되어, Visitor가 상담원과
연결 중이라는 사실을 잃어버리고 AI에게 메시지를 보내려 한다.

구체적으로 세 가지 증상이 발생한다:

1. **대화 내역 소실**: 새로고침 후 `messages` 상태가 빈 배열로 초기화된다.
   이전에 나눈 대화 내용이 전혀 표시되지 않는다.

2. **HITL 상태 미복원**: `isHitl` 상태가 항상 `false`로 초기화된다.
   세션이 HITL 모드였어도 위젯은 AI 모드로 동작한다.

3. **환영 메시지 중복 표시**: 재연결 시에도 `welcome_message`가 있으면 다시 표시된다.
   Visitor 입장에서 이미 대화한 상대가 다시 인사하는 이상한 상황이 발생한다.

## Solution

`GET /api/chat/stream` 연결 시 서버가 내려주는 `connected` 이벤트 payload를 확장한다.
**기존 세션**(이전 ChatMessage 존재)에 재연결하는 경우:
- `history`: 이전 대화 메시지 목록
- `is_hitl`: 현재 세션의 HITL 상태
- `welcome_message` 생략 (중복 방지)

**신규 세션**(ChatMessage 없음)에 최초 연결하는 경우:
- 기존과 동일하게 `welcome_message` 포함
- `history`, `is_hitl` 포함하지 않음 (빈 세션이므로 불필요)

위젯은 `connected` 이벤트를 받아 `history`와 `is_hitl`로 상태를 복원한다.

## User Stories

1. As a Visitor, I want my previous messages to still be visible after refreshing the page, so that I don't lose the context of my conversation.
2. As a Visitor, I want the chat widget to show that I am connected to a human agent after refreshing, so that I don't accidentally think I'm talking to the AI.
3. As a Visitor, I want the human agent's messages to still be visible after refreshing, so that I can continue reading the conversation.
4. As a Visitor, I want the system message ("상담원 연결 중") to not reappear if I refresh the page during HITL, so that I don't see duplicate system messages.
5. As a Visitor, I want the welcome message to not appear again when I refresh the page, so that I don't see a redundant greeting in the middle of an ongoing conversation.
6. As a Visitor, I want to be able to continue sending messages immediately after refreshing, without needing to re-identify myself.
7. As a Visitor in HITL mode, I want the input field to remain enabled after refreshing, so that I can continue messaging the human agent.
8. As a TenantAgent, I want to know that a Visitor refreshing the page during HITL doesn't disrupt the ongoing session, so that I can continue my support conversation seamlessly.

## Implementation Decisions

### `connected` 이벤트 payload 확장

`GET /api/chat/stream` 연결 후 첫 번째 SSE 이벤트인 `connected`의 payload를 두 가지 형태로 분기한다.

**신규 세션 (ChatMessage 없음):**
```json
{
  "session_id": "...",
  "welcome_message": "안녕하세요!"
}
```

**기존 세션 (ChatMessage 존재):**
```json
{
  "session_id": "...",
  "is_hitl": true,
  "history": [
    { "role": "user", "content": "안녕하세요" },
    { "role": "assistant", "content": "안녕하세요! 무엇을 도와드릴까요?" },
    { "role": "human_agent", "content": "상담원입니다. 말씀해 주세요." }
  ]
}
```

`history`에는 `role`과 `content`만 포함한다. `id`, `created_at` 등 위젯이 사용하지 않는 필드는 제외한다.

### 백엔드 수정: `stream` 엔드포인트

`GET /api/chat/stream` 뷰에서 세션의 ChatMessage를 조회하여 신규/기존 세션 여부를 판단한다.
- 기존 세션: `sse_event_stream()`에 `history`와 `is_hitl`을 전달
- 신규 세션: 기존대로 `welcome_message`를 전달

### 백엔드 수정: `sse_event_stream()`

`sse_event_stream(session_id, welcome_message, history, is_hitl)` 시그니처로 확장한다.
`connected` 이벤트의 payload를 인자에 따라 구성한다.

### 프론트엔드 수정: `ChatWidget`

`connected` 이벤트 핸들러에서:
- `data.history`가 있으면 `setMessages(data.history)` 로 상태 복원
- `data.is_hitl`이 있으면 `setIsHitl(true)` 로 상태 복원
- `data.welcome_message`가 있을 때만 환영 메시지를 messages에 추가 (기존 동작 유지)

## Testing Decisions

좋은 테스트는 구현이 아닌 **외부에서 관찰 가능한 동작**을 검증한다.
내부 함수 호출 여부가 아니라, SSE 이벤트 payload와 API 응답을 기준으로 assertion한다.
Mock 없이 실제 ChatMessage, ChatSession 레코드를 사용한다.

**테스트 대상:**

- **`stream` 엔드포인트 — 기존 세션** (`test_chat_session.py` 확장)
  - ChatMessage가 있는 세션에 재연결 시 `connected` 이벤트에 `history` 포함 여부
  - `is_hitl=True` 세션에 재연결 시 `connected` 이벤트에 `is_hitl: true` 포함 여부
  - 기존 세션에서 `welcome_message` 미포함 여부
  - prior art: `test_stream_sends_connected_event_first`, `test_stream_reconnect_reuses_same_session`

- **`stream` 엔드포인트 — 신규 세션**
  - 신규 세션에서 `welcome_message` 포함 여부 (기존 테스트 회귀 방지)
  - prior art: `test_welcome_message_included_in_connected_event`

프론트엔드(`ChatWidget`) 동작은 TDD 범위 밖이며 수동 검증으로 대체한다.

## Out of Scope

- EmbedToken TTL 만료 시 재발급 흐름 — 별도 이슈
- `streamingText` (partial AI response) 복원 — 새로고침 시점에 이미 완료된 응답만 복원하므로 불필요
- 페이지를 닫았다가 수일 후 재방문하는 경우 — 현재 세션은 `ended_at=None` 조건으로 관리되며, 세션 만료 정책은 별도 이슈

## Further Notes

- `get_or_create`의 `(tenant_id, visitor_id, ended_at=None)` 조합이 재연결 시 같은 세션을 재사용하므로, 세션 ID 자체는 이미 유지된다. 이번 PRD는 세션 ID 유지가 아닌 **UI 상태 복원** 문제를 다룬다.
- `history`에 포함되는 ChatMessage는 `created_at` 오름차순으로 정렬한다.
- `human_agent` role 메시지도 `history`에 포함되어야 HITL 대화 맥락이 복원된다.
