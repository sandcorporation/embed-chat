---
title: "WebhookDispatcher (Slack / Discord / Generic)"
label: done
---

## Parent

PRD: `.scratch/embed-chatbot-platform/PRD-hitl.md`

## What to build

Escalation 생성 시 Tenant 설정 웹훅으로 알림을 비동기 전송하는 `WebhookDispatcher`를 구현한다. Slack, Discord, Generic 세 가지 포맷을 지원하며 Celery 태스크로 실행된다.

Slack 페이로드: `blocks` 포맷. Discord: `embeds`. Generic: raw JSON.
모두 트리거 유형·이유·최근 5개 메시지·어드민 딥링크 포함.

## Acceptance criteria

- [ ] `webhook_type=slack`이면 Slack `blocks` 포맷으로 HTTP POST가 전송된다
- [ ] `webhook_type=discord`이면 Discord `embeds` 포맷으로 전송된다
- [ ] `webhook_type=generic`이면 raw JSON 포맷으로 전송된다
- [ ] 페이로드에 trigger_type, reason, 최근 메시지 5개, 어드민 딥링크가 포함된다
- [ ] HTTP 전송 실패 시 최대 3회 재시도한다
- [ ] `webhook_url`이 비어 있으면 전송하지 않는다 (에러 없이 skip)
- [ ] Escalation 생성 시 Celery 태스크가 자동으로 예약된다

## Blocked by

- issue-21: Escalation 모델 + LangGraph Structured Output (Escalation 모델 필요)
