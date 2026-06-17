# PRD: Widget UX 개선 + TENANT_KEY 재발급

Status: ready-for-agent

## Problem Statement

Tenant가 ChatWidget을 방문자에게 제공할 때 세 가지 문제가 있다.

1. **환영 메시지 없음**: 위젯이 열리면 빈 화면만 보여 방문자가 대화를 시작해야 할지 망설인다. Tenant가 브랜드에 맞는 첫 인사말을 설정할 수 없다.

2. **응답 대기 피드백 없음**: 방문자가 메시지를 보낸 후 AI나 상담원이 응답 중인지 알 수 없다. 응답이 오기까지 수 초가 걸리는 경우 위젯이 멈춘 것처럼 보인다.

3. **TENANT_KEY 교체 불가**: TENANT_KEY가 유출되거나 주기적 교체가 필요할 때 Tenant가 어드민 UI에서 직접 재발급할 수 없고, Operator에게 별도 요청해야 한다.

## Solution

- **환영 메시지**: TenantConfig에 `welcome_message` 필드를 추가하고, SSE 연결 시 `connected` 이벤트 payload에 포함해 ChatWidget이 자동으로 assistant 버블로 표시한다.
- **타이핑 인디케이터**: AI 응답 대기 중에는 프론트엔드에서 "AI가 응답 중···"을, HITL 상담원이 입력 중일 때는 SSE `typing` 이벤트를 통해 "상담원이 입력 중···"을 표시한다.
- **TENANT_KEY 재발급**: 어드민 UI의 설정 탭에서 TenantAgent가 직접 재발급 요청을 할 수 있다. 새 키는 응답에 단 1회만 노출된다.

## User Stories

1. As a Tenant, I want to set a welcome message in the admin UI, so that visitors see a greeting when they open the ChatWidget.
2. As a Tenant, I want the welcome message to reflect my brand voice, so that the first impression is consistent with my product.
3. As a Visitor, I want to see a greeting message when the chat opens, so that I know the widget is ready and feel welcomed.
4. As a Visitor, I want to see "AI가 응답 중···" after I send a message, so that I know my message was received and a response is coming.
5. As a Visitor, I want the typing indicator to disappear as soon as the AI starts streaming text, so that the transition feels seamless.
6. As a Visitor, I want to see "상담원이 입력 중···" when a human agent is composing a reply, so that I know a real person is actively helping me.
7. As a Visitor, I want the agent typing indicator to disappear automatically if the agent stops typing, so that I'm not misled about agent activity.
8. As a Visitor, I want the agent typing indicator to disappear instantly when the agent's message arrives, so that there's no duplicate "typing + message" flash.
9. As a TenantAgent, I want my typing to automatically signal the visitor, so that I don't have to manually trigger any indicator.
10. As a TenantAgent, I want the typing signal to be debounced, so that every keystroke doesn't create unnecessary API calls.
11. As a TenantAgent, I want to regenerate the TENANT_KEY from the admin UI, so that I can rotate keys without contacting the Operator.
12. As a TenantAgent, I want to see the new TENANT_KEY exactly once after regeneration, so that I know to copy it immediately and the key isn't stored in plain text.
13. As a TenantAgent, I want a confirmation step before regenerating the key, so that I don't accidentally invalidate a working integration.
14. As a TenantAgent, I want to see a clear warning that existing integrations will break, so that I can prepare before rotating the key.
15. As a TenantAgent, I want to copy the new key with a single click, so that I don't accidentally introduce typos.
16. As a Tenant, I want the welcome message to be empty by default, so that existing widgets are unaffected by the feature rollout.

## Implementation Decisions

### 환영 메시지

- `TenantConfig`에 `welcome_message: TextField(blank=True, default="")` 추가. DB 마이그레이션 필요.
- SSE 연결 흐름: `stream` 뷰가 `tenant.config.welcome_message`를 읽어 `sse_event_stream`에 전달. 비어있으면 `connected` payload에서 키 자체를 생략.
- `connected` payload 형태 (프로토타입에서 확정):
  ```json
  { "session_id": "...", "welcome_message": "안녕하세요!" }
  ```
  `welcome_message` 키는 값이 있을 때만 포함됨.
- ChatWidget은 `connected` 이벤트에서 `welcome_message` 키가 있으면 `role: "assistant"` 메시지로 상태에 추가.
- TenantConfig PATCH API와 GET API에 `welcome_message` 필드 포함.
- 어드민 ConfigTab에 textarea 입력 필드 추가 (LLM 모델 선택 위에 배치).

### AI 타이핑 인디케이터

- 서버 이벤트 없이 순수 프론트엔드 처리.
- ChatWidget에서 `POST /api/chat/message` 202 응답 수신 후, HITL 모드가 아닐 때 `typingActor = 'ai'` 상태 설정.
- 첫 `token` SSE 이벤트 또는 `hitl_start` 이벤트 수신 시 `typingActor = null`로 초기화.
- `done` 이벤트 수신 시도 초기화.

### 상담원 타이핑 인디케이터

- 새 엔드포인트: `POST /api/tenant/escalations/{escalation_id}/typing` (TenantAgent 인증 필요).
- 요청 수신 시 Redis pubsub `session:{session_id}` 채널에 `{"type": "typing", "actor": "human_agent"}` 발행.
- ChatWidget SSE: `typing` 이벤트 수신 시 `typingActor = 'human_agent'` 설정, 3초 타이머 후 자동 초기화.
- `hitl_message` 이벤트 수신 시 타이머 취소 및 `typingActor = null` 즉시 초기화.
- 어드민 HitlTab `EscalationCard`: 메시지 입력 onChange마다 500ms 디바운스로 `/typing` 호출.

### TENANT_KEY 재발급

- `Tenant.reset_key()` 메서드는 이미 존재 — 새 키 생성, SHA-256 해시 저장 후 평문 반환.
- 새 엔드포인트: `POST /api/tenant/reset-key` (TenantAgent 인증). `{"new_tenant_key": "..."}` 반환.
- 응답은 1회성 — 이후 재조회 API 없음.
- 어드민 ConfigTab 하단 "API KEY 재발급" 섹션:
  - 1차 클릭: 버튼 텍스트가 경고 문구로 변경 (2단계 확인)
  - 2차 클릭: API 호출 → 새 키를 황색 경고 박스에 1회 표시 + 복사 버튼
  - "확인 완료" 클릭 시 박스 숨김

## Testing Decisions

좋은 테스트는 퍼블릭 인터페이스(HTTP API, SSE 이벤트, DB 상태)만 검증한다. 내부 함수 호출 여부나 구현 세부사항은 검증하지 않는다.

- **환영 메시지**: `welcome_message` 설정 후 SSE `connected` 이벤트 payload 검증. 비어있을 때 키가 없음을 검증. 선례: `test_stream_sends_connected_event_first`.
- **TENANT_KEY 재발급**: API 응답에 새 키 포함 확인, 기존 키로 인증 불가 확인, 새 키로 인증 가능 확인. 선례: `test_tenant_key_not_stored_in_plaintext`.
- **상담원 타이핑**: `/typing` POST 후 Redis에 `typing` 이벤트 발행 확인. 선례: `test_send_message_publishes_hitl_message_sse`.
- AI 타이핑 인디케이터는 순수 프론트엔드 로직이므로 백엔드 테스트 불필요. E2E(Playwright) 테스트 범위.

## Out of Scope

- Visitor가 타이핑 중임을 상담원 어드민에 표시하는 기능 (역방향 타이핑 인디케이터)
- 타이핑 인디케이터의 애니메이션 커스터마이징
- TENANT_KEY 재발급 이력 로깅
- Operator가 Tenant 대신 TENANT_KEY를 재발급하는 기능
- 환영 메시지에 Visitor 이름 등 동적 변수 삽입

## Further Notes

- 환영 메시지는 `ChatSession` 재연결(브라우저 탭 재열기) 시에도 매번 표시된다. 세션을 재사용하므로 중복 표시될 수 있는데, 이는 현재 허용 범위로 본다.
- TENANT_KEY 재발급 후 기존 embed_token은 만료(TTL 기반)될 때까지 계속 유효하다. 키 교체 즉시 모든 세션이 끊기지 않는다.
