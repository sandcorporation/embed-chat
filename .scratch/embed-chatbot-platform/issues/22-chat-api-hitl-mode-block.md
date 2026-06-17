---
title: "Chat API HITL 모드 차단"
label: done
---

## Parent

PRD: `.scratch/embed-chatbot-platform/PRD-hitl.md`

## What to build

`session.is_hitl=True`인 세션에 Visitor가 메시지를 보내면 LangGraph를 호출하지 않고 메시지를 저장만 한 뒤, 어드민 SSE 채널(`hitl:{tenant_id}`)로 `hitl_message` 이벤트를 emit한다. AI는 완전히 침묵한다.

## Acceptance criteria

- [ ] `is_hitl=True` 세션에 `POST /api/chat/message`를 보내면 LangGraph가 호출되지 않는다
- [ ] Visitor 메시지는 `role=user`로 ChatMessage에 저장된다
- [ ] `hitl:{tenant_id}` Redis 채널로 `hitl_message` 이벤트가 publish된다

## Blocked by

- issue-21: Escalation 모델 + LangGraph Structured Output + SSE hitl_start
