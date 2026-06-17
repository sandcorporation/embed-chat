# 29 — AI 타이핑 인디케이터 (프론트엔드 전용)

Status: ready-for-agent

## Parent

`.scratch/embed-chatbot-platform/PRD-widget-ux-improvements.md`

## What to build

Visitor가 메시지를 보낸 후 AI 응답이 도착하기 전까지 ChatWidget에 "AI가 응답 중···" 인디케이터를 표시한다. 백엔드 변경 없이 순수 프론트엔드 상태로 처리한다.

- `POST /api/chat/message` 202 응답 수신 후, HITL 모드가 아닐 때 `typingActor = 'ai'` 상태 설정
- 첫 `token` SSE 이벤트 수신 시 즉시 `typingActor = null` (스트리밍 텍스트로 교체)
- `done`, `hitl_start`, `error` 이벤트 수신 시 `typingActor = null`
- 인디케이터는 메시지 목록 하단에 assistant 버블 스타일로 표시

## Acceptance criteria

- [ ] 메시지 전송 후 첫 token 이벤트 도착 전까지 "AI가 응답 중···" 인디케이터 표시
- [ ] 첫 token 이벤트 도착 시 인디케이터가 스트리밍 텍스트로 즉시 교체됨 (깜빡임 없음)
- [ ] `done` 수신 시 인디케이터가 남아있지 않음
- [ ] HITL 모드(`is_hitl=true`)에서는 메시지 전송 후 AI 인디케이터가 표시되지 않음
- [ ] 백엔드 API 변경 없음

## Blocked by

None — can start immediately
