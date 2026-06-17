# 30 — 상담원 타이핑 인디케이터

Status: ready-for-agent

## Parent

`.scratch/embed-chatbot-platform/PRD-widget-ux-improvements.md`

## What to build

HITL 상담원이 메시지를 입력 중일 때 Visitor의 ChatWidget에 "상담원이 입력 중···" 인디케이터를 표시한다. 어드민 UI의 키 입력 → API → Redis → SSE → 위젯 전 레이어를 관통하는 수직 슬라이스.

- **API**: `POST /api/tenant/escalations/{escalation_id}/typing` (TenantAgent 인증). Redis pubsub `session:{session_id}` 채널에 `{"type": "typing", "actor": "human_agent"}` 발행
- **ChatWidget**: SSE `typing` 이벤트 수신 시 `typingActor = 'human_agent'` 설정 → 3초 타이머 후 자동 해제. `hitl_message` 이벤트 수신 시 타이머 취소 + 즉시 해제
- **어드민 HitlTab**: 메시지 입력창 onChange마다 500ms 디바운스로 `/typing` API 호출

## Acceptance criteria

- [ ] `POST /api/tenant/escalations/{id}/typing` 가 200을 반환하고 Redis에 `typing` 이벤트 발행
- [ ] 존재하지 않는 escalation_id로 요청 시 404 반환
- [ ] ChatWidget SSE에서 `typing` 이벤트 수신 시 "상담원이 입력 중···" 인디케이터 표시
- [ ] 인디케이터가 3초 후 자동으로 사라짐
- [ ] `hitl_message` SSE 이벤트 도착 시 타이머 관계없이 즉시 인디케이터 해제
- [ ] 어드민 UI 입력창에서 타이핑 시 debounce(500ms) 후 `/typing` 호출
- [ ] 테스트: `/typing` POST 후 Redis `typing` 이벤트 발행 검증

## Blocked by

None — can start immediately
