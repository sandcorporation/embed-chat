---
title: "TenantAgent 본인 비밀번호 변경 (API + UI)"
label: ready-for-agent
---

## Parent

PRD: `.scratch/embed-chatbot-platform/PRD-tenant-agent.md`

## What to build

로그인한 TenantAgent가 자신의 비밀번호를 변경할 수 있는 API 엔드포인트와 어드민 UI 폼을 추가한다. 기존 password 확인 후 새 password로 교체한다.

## Acceptance criteria

- [ ] `POST /api/tenant/agents/me/change-password`에 `{ current_password, new_password }`를 보내면 비밀번호가 변경된다
- [ ] 변경 후 새 password로 로그인 API 호출이 성공한다
- [ ] 잘못된 current_password를 입력하면 400이 반환된다
- [ ] 어드민 UI "팀원" 탭 또는 설정 영역에서 비밀번호 변경 폼이 제공된다

## Blocked by

- issue-19: TenantAgent CRUD API + 어드민 UI 팀원 탭
