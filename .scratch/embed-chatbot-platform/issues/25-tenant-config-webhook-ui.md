---
title: "TenantConfig 웹훅 설정 UI (ConfigTab 업데이트)"
label: done
---

## Parent

PRD: `.scratch/embed-chatbot-platform/PRD-hitl.md`

## What to build

어드민 UI 설정 탭에 웹훅 URL, 웹훅 타입(Slack/Discord/Generic), 상담원 표시 이름(`agent_display_name`) 필드를 추가한다. 백엔드 `/api/tenant/config/` 엔드포인트에도 이 필드들을 포함한다.

## Acceptance criteria

- [ ] `GET /api/tenant/config/`에 `webhook_url`, `webhook_type`, `agent_display_name`이 포함된다
- [ ] `PATCH /api/tenant/config/`로 세 필드를 업데이트할 수 있다
- [ ] 어드민 UI 설정 탭에서 세 필드의 입력 UI가 표시된다
- [ ] `webhook_type` 필드는 slack/discord/generic 선택지를 제공한다
- [ ] 저장 버튼 클릭 시 변경사항이 서버에 반영된다

## Blocked by

- issue-21: Escalation 모델 (TenantConfig 스키마 변경 포함)
- issue-18: 어드민 UI 로그인 교체 (TenantAgent JWT 필요)
