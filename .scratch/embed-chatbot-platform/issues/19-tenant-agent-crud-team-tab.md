---
title: "TenantAgent CRUD API + 어드민 UI 팀원 탭"
label: ready-for-agent
---

## Parent

PRD: `.scratch/embed-chatbot-platform/PRD-tenant-agent.md`

## What to build

로그인한 TenantAgent가 같은 Tenant의 팀원 계정을 추가·비활성화할 수 있는 API와 어드민 UI "팀원" 탭을 추가한다. 새 계정 생성 시 임시 password가 1회 반환된다. TENANT_KEY로도 팀원 계정을 생성할 수 있다(서버사이드 프로비저닝).

## Acceptance criteria

- [ ] `GET /api/tenant/agents/`가 소속 Tenant의 TenantAgent 목록을 반환한다
- [ ] `POST /api/tenant/agents/`로 새 TenantAgent를 생성하면 임시 password가 응답에 1회 포함된다
- [ ] 생성된 계정으로 로그인 API 호출 시 성공한다
- [ ] `PATCH /api/tenant/agents/{id}/deactivate`로 비활성화 후 해당 계정으로 로그인하면 401이 반환된다
- [ ] TENANT_KEY Bearer 토큰으로도 `POST /api/tenant/agents/`를 호출할 수 있다
- [ ] 어드민 UI "팀원" 탭에서 팀원 목록이 표시된다
- [ ] "팀원" 탭에서 팀원을 추가하면 임시 password가 화면에 1회 표시된다
- [ ] "팀원" 탭에서 비활성화 버튼 클릭 시 해당 행이 비활성 상태로 바뀐다

## Blocked by

- issue-18: 어드민 UI 로그인 교체 + Tenant 엔드포인트 인증 전환
