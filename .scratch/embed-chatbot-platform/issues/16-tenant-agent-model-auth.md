---
title: "TenantAgent 모델 + 로그인 API + TenantAgentAuth"
label: ready-for-agent
---

## Parent

PRD: `.scratch/embed-chatbot-platform/PRD-tenant-agent.md`

## What to build

`TenantAgent` 모델과 JWT 기반 인증 레이어를 추가한다. TenantAgent는 Tenant 소속 개별 상담원으로, username/password로 로그인해 JWT를 받는다. JWT는 어드민 UI 전반의 인증에 사용된다.

## Acceptance criteria

- [ ] `TenantAgent` 모델이 존재한다 (id, tenant FK, username, password_hash, is_active, created_at)
- [ ] `username`은 같은 Tenant 내에서만 고유하다 (`unique_together: [tenant, username]`)
- [ ] `POST /api/tenant/agents/auth/login`에 올바른 username/password/tenant_id를 보내면 200 + `access_token`을 반환한다
- [ ] 잘못된 password로 로그인하면 401을 반환한다
- [ ] 비활성 TenantAgent로 로그인하면 401을 반환한다
- [ ] 반환된 JWT로 `TenantAgentAuth` 보호 엔드포인트를 호출하면 `request.auth`에 TenantAgent 인스턴스가 주입된다

## Blocked by

None - 즉시 시작 가능
