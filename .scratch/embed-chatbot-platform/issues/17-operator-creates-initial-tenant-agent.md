---
title: "Operator Tenant 생성 시 초기 TenantAgent 자동 생성"
label: ready-for-agent
---

## Parent

PRD: `.scratch/embed-chatbot-platform/PRD-tenant-agent.md`

## What to build

Operator가 Tenant를 생성하면 `username="admin"`인 초기 TenantAgent 계정도 함께 만들어진다. 임시 password는 시스템이 자동 생성하며, `POST /api/operator/tenants/` 응답에 1회만 포함된다. Operator 대시보드에서 TENANT_KEY와 함께 표시된다.

## Acceptance criteria

- [ ] `POST /api/operator/tenants/` 응답에 `agent_username`과 `agent_temp_password` 필드가 추가된다
- [ ] 응답의 `agent_username`은 `"admin"`이다
- [ ] 반환된 `agent_temp_password`로 `/api/tenant/agents/auth/login`에 로그인하면 성공한다
- [ ] Operator 대시보드에서 Tenant 생성 완료 시 `agent_username`과 `agent_temp_password`가 1회 표시된다

## Blocked by

- issue-16: TenantAgent 모델 + 로그인 API + TenantAgentAuth
