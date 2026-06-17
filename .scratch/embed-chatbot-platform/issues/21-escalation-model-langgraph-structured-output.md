---
title: "Escalation 모델 + LangGraph Structured Output + SSE hitl_start"
label: done
---

## Parent

PRD: `.scratch/embed-chatbot-platform/PRD-hitl.md`

## What to build

HITL의 핵심 백엔드 파이프라인을 구축한다. LLM이 `{ response, needs_hitl, hitl_reason }` 구조로 응답하도록 LangGraph 그래프를 변경하고, `needs_hitl=True`이면 `Escalation`을 생성하고 ChatSession을 HITL 모드로 전환한다. Visitor 위젯 SSE로 `hitl_start` 이벤트를 전송한다.

상태 전이:
```
pending → claimed → resolved
```

## Acceptance criteria

- [ ] `Escalation` 모델이 존재한다 (id UUID, session FK, trigger_type, reason, status, created_at, resolved_at)
- [ ] `EscalationClaim` 모델이 존재한다 (escalation OneToOne, claimed_by, claimed_at)
- [ ] `ChatSession.is_hitl` 필드가 존재한다 (BooleanField, default=False)
- [ ] `TenantConfig`에 `agent_display_name`, `webhook_url`, `webhook_type` 필드가 추가된다
- [ ] LLM이 `needs_hitl=True`를 반환하면 Escalation이 생성되고 `session.is_hitl=True`가 된다
- [ ] Escalation 생성 시 Visitor 세션 SSE에 `hitl_start` 이벤트가 전송된다
- [ ] LLM이 `needs_hitl=False`를 반환하면 기존과 동일하게 응답이 저장된다

## Blocked by

- issue-16 ~ issue-20: TenantAgent 시스템 완료 후 진행
