---
title: "어드민 UI 로그인 교체 + Tenant 엔드포인트 인증 전환"
label: ready-for-agent
---

## Parent

PRD: `.scratch/embed-chatbot-platform/PRD-tenant-agent.md`

## What to build

어드민 UI의 Tenant 로그인 화면을 TENANT_KEY 입력에서 username/password 폼으로 교체한다. 동시에 `/api/tenant/config/`, RAG, Memory 엔드포인트의 인증을 `tenant_key_auth`에서 `tenant_agent_auth`(TenantAgent JWT)로 전환한다. 두 변경은 원자적으로 진행해야 UI가 깨지지 않는다.

## Acceptance criteria

- [ ] TenantLogin 화면이 username, tenant_id, password 세 필드를 가진 폼을 렌더링한다
- [ ] 올바른 credentials로 로그인하면 JWT가 저장되고 TenantDashboard로 이동한다
- [ ] 잘못된 credentials로 로그인하면 에러 메시지가 표시된다
- [ ] 로그아웃 버튼 클릭 시 JWT가 삭제되고 로그인 화면으로 돌아간다
- [ ] 헤더에 현재 로그인한 username이 표시된다
- [ ] TENANT_KEY Bearer 토큰으로 `/api/tenant/config/`를 호출하면 401이 반환된다
- [ ] TenantAgent JWT로 `/api/tenant/config/`를 호출하면 200이 반환된다

## Blocked by

- issue-16: TenantAgent 모델 + 로그인 API + TenantAgentAuth
- issue-17: Operator Tenant 생성 시 초기 TenantAgent 자동 생성
