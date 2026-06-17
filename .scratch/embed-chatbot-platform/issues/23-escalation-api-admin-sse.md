---
title: "Escalation 관리 API + 어드민 SSE 스트림"
label: done
---

## Parent

PRD: `.scratch/embed-chatbot-platform/PRD-hitl.md`

## What to build

Tenant 상담원이 Escalation 세션을 수락·응답·해제할 수 있는 API와 실시간 SSE 스트림을 추가한다. 세션 해제 시 `session.is_hitl=False`로 전환되고 Visitor SSE에 `hitl_end` 이벤트가 전송된다.

API 엔드포인트 (모두 TenantAgentAuth):
- `GET /api/tenant/escalations/` — 활성 Escalation 목록
- `POST /api/tenant/escalations/{id}/claim` — 세션 수락 (DB unique constraint로 중복 방지)
- `POST /api/tenant/escalations/{id}/message` — HumanTurn 메시지 전송
- `POST /api/tenant/escalations/{id}/resolve` — 해제 후 AI 복귀
- `GET /api/tenant/escalations/stream` — SSE (`hitl:{tenant_id}` 채널 구독)

## Acceptance criteria

- [ ] `GET /api/tenant/escalations/`가 pending + claimed 상태의 Escalation 목록을 반환한다
- [ ] `POST .../claim`으로 Escalation을 수락하면 `EscalationClaim`이 생성되고 status가 `claimed`가 된다
- [ ] 같은 Escalation에 두 번 claim하면 두 번째는 실패(409)한다
- [ ] `POST .../message`로 HumanTurn 메시지를 보내면 `role=human_agent`로 ChatMessage가 저장되고 Visitor SSE에 `hitl_message` 이벤트가 전송된다
- [ ] `POST .../resolve`로 해제하면 `session.is_hitl=False`, Escalation status가 `resolved`가 되고 Visitor SSE에 `hitl_end` 이벤트가 전송된다
- [ ] `GET .../stream` SSE로 `escalation_new`, `escalation_claimed`, `escalation_resolved` 이벤트를 수신할 수 있다

## Blocked by

- issue-22: Chat API HITL 모드 차단
