---
title: TenantAgent 계정 및 어드민 UI 인증 전환
label: ready-for-agent
---

## Problem Statement

현재 Tenant 팀원들은 서버사이드 시크릿인 `TENANT_KEY`를 브라우저에 직접 입력해 어드민 UI에 로그인한다. 이 방식은 두 가지 문제를 갖는다. 첫째, 서버 시크릿이 브라우저에 노출되어 보안상 취약하다. 둘째, 모든 팀원이 같은 키를 공유하므로 개인 정체성이 없어 "누가 무엇을 했는가"를 추적할 수 없다. 이는 HITL Claim 시스템(누가 세션을 수락했는가)의 선행 조건이기도 하다.

## Solution

`TenantAgent` 개인 계정 시스템을 도입한다. Operator가 Tenant를 생성할 때 초기 TenantAgent 계정(username + 임시 password)도 함께 만들어 1회 화면에 표시한다. 어드민 UI 로그인은 username/password → JWT 방식으로 전환된다. TENANT_KEY는 서버사이드 전용(EmbedToken 발급, TenantAgent 계정 생성 API)으로만 남는다. 어드민 UI 내 "팀원" 탭에서 로그인한 TenantAgent가 추가 팀원 계정을 직접 추가·비활성화할 수 있다.

## User Stories

1. As an Operator, I want the system to automatically create an initial TenantAgent account when I create a new Tenant, so that the Tenant can immediately log in without a separate setup step.
2. As an Operator, I want to see the initial TenantAgent username and temporary password displayed once after Tenant creation, so that I can share the credentials with the Tenant.
3. As an Operator, I want the initial credentials to be shown alongside the TENANT_KEY in one screen, so that I can hand over everything the Tenant needs in one step.
4. As a TenantAgent, I want to log in to the admin UI with my username and password, so that I have a personal identity separate from the shared TENANT_KEY.
5. As a TenantAgent, I want my login session to persist with a JWT token, so that I don't have to re-enter credentials on every page load.
6. As a TenantAgent, I want to log out of the admin UI, so that I can protect access on shared devices.
7. As a TenantAgent, I want to access all admin UI features (Documents, Memory, Config, HITL) with my personal account, so that I don't need the TENANT_KEY in my browser.
8. As a TenantAgent, I want to view a list of TenantAgent accounts in my organization from the "팀원" tab, so that I know who has access.
9. As a TenantAgent, I want to add a new TenantAgent account from the "팀원" tab, so that I can onboard new team members without involving the Operator.
10. As a TenantAgent, I want the new account's temporary password to be shown once upon creation, so that I can share it with the new team member.
11. As a TenantAgent, I want to deactivate a TenantAgent account from the "팀원" tab, so that I can revoke access for team members who no longer need it.
12. As a TenantAgent, I want deactivated accounts to be blocked from logging in, so that revoked access is immediately effective.
13. As a TenantAgent, I want to change my own password from the admin UI, so that I can replace the temporary password I received from the Operator.
14. As a Tenant (server-side), I want to create TenantAgent accounts programmatically via the TENANT_KEY-authenticated API, so that I can automate account provisioning from my backend.
15. As an Operator, I want the TENANT_KEY to remain valid for server-side API calls (EmbedToken issuance), so that existing Tenant integrations are not broken.
16. As a TenantAgent, I want to see my username displayed in the admin UI header, so that I know which account I'm logged in as.
17. As a TenantAgent, I want to see the active/inactive status of each team member account, so that I can tell who currently has access.

## Implementation Decisions

### 새 도메인 모델: TenantAgent

`TenantAgent` 모델 필드: `id` (UUID), `tenant` (FK → Tenant), `username` (CharField, unique_together with tenant), `password_hash` (CharField, Django의 `make_password`/`check_password` 사용), `is_active` (BooleanField, default=True), `created_at`.

`username`은 Tenant 내에서만 고유하면 된다 (`unique_together: [tenant, username]`). 동일 username이 다른 Tenant에 존재해도 무관.

### TenantAgent 인증 (백엔드)

`create_tenant_agent_token(agent)` 함수: Operator JWT와 동일한 패턴으로 `{ sub: agent.id, tenant_id: tenant.id, type: "tenant_agent", exp: 24h }` payload를 HS256으로 서명.

`TenantAgentAuth(HttpBearer)`: Bearer 토큰을 검증해 `TenantAgent` 인스턴스를 반환. `request.auth`에 `TenantAgent` 객체가 들어오며, `request.auth.tenant`로 소속 Tenant에 접근.

### API 변경

**신규 엔드포인트 (인증 없음):**
- `POST /api/tenant/agents/auth/login` — `{ username, tenant_id }` + password → `{ access_token }`

> `tenant_id`를 로그인 시 요구하는 이유: username이 Tenant 내에서만 고유하므로, 어느 Tenant의 계정인지 식별 필요.

**신규 엔드포인트 (TenantAgentAuth):**
- `GET /api/tenant/agents/` — 소속 Tenant의 TenantAgent 목록
- `POST /api/tenant/agents/` — 새 TenantAgent 생성. 임시 password를 시스템이 자동 생성해 response에 1회 반환
- `PATCH /api/tenant/agents/{id}/deactivate` — 비활성화
- `POST /api/tenant/agents/me/change-password` — 본인 비밀번호 변경

**신규 엔드포인트 (TenantKeyAuth, 서버사이드 용도):**
- `POST /api/tenant/agents/` — TENANT_KEY로도 동일한 TenantAgent 생성 엔드포인트 호출 가능 (이중 인증 허용: TenantAgentAuth OR TenantKeyAuth)

**기존 엔드포인트 인증 교체:**

아래 엔드포인트들의 `auth`를 `tenant_key_auth` → `tenant_agent_auth`로 전환:
- `GET/PATCH /api/tenant/config/`
- 모든 RAG 문서 엔드포인트 (`/api/tenant/rag/...`)
- 모든 Memory 엔드포인트 (`/api/memory/...`)
- 추후 HITL 엔드포인트 (`/api/tenant/escalations/...`)

**Operator API 변경:**

`POST /api/operator/tenants/` 응답 스키마 확장:
```
{
  "id": "...",
  "name": "...",
  "is_active": true,
  "tenant_key": "...",         ← 기존
  "agent_username": "admin",   ← 신규
  "agent_temp_password": "..." ← 신규 (1회만)
}
```
Tenant 생성 시 `username="admin"`, 임시 password를 자동 생성해 초기 TenantAgent를 함께 DB에 저장.

### 어드민 UI 변경 (embed-chat-admin)

**`TenantLogin.jsx` 교체:**
- 기존 TENANT_KEY 입력 필드 제거
- username, tenant_id(또는 선택 가능한 Tenant 식별자), password 입력 폼으로 교체
- 로그인 성공 시 JWT를 localStorage에 저장 (현재 tenantKey 저장 위치와 동일)

**API 레이어 (`api.js`) 업데이트:**
- 모든 Tenant API 호출에서 `Authorization: Bearer <tenantKey>` → `Authorization: Bearer <agentToken>` 으로 변경
- props/state 이름을 `tenantKey` → `agentToken`으로 일관 변경

**`TenantDashboard.jsx` 업데이트:**
- 헤더에 현재 로그인한 username 표시
- 탭 목록에 "팀원" 탭 추가

**`AgentsTab.jsx` 신규 컴포넌트:**
- TenantAgent 목록 표시 (username, 상태, 생성일)
- "팀원 추가" 폼 (username 입력 → 임시 password 1회 표시)
- 비활성화 버튼

**`OperatorDashboard.jsx` 업데이트:**
- Tenant 생성 완료 알림에 `agent_username`과 `agent_temp_password` 추가 표시
- 현재 TENANT_KEY 1회 표시 UI에 통합

### 보안 고려사항

- TenantAgent JWT는 `type: "tenant_agent"` 클레임으로 Operator JWT와 구분
- TENANT_KEY는 어드민 UI 로그인에서 완전히 제거. `POST /api/chat/embed-token`(EmbedToken 발급)과 TenantAgent 생성 API에만 허용
- TenantAgent password는 Django의 `make_password()`로 해시 저장. 평문은 어디에도 저장되지 않음
- 임시 password는 API 응답으로 1회 반환 후 복구 불가

## Testing Decisions

**좋은 테스트 기준**: 공개 API 인터페이스를 통해 동작 검증. 해시 알고리즘 내부나 JWT 페이로드 구조는 테스트하지 않는다. "올바른 credentials로 로그인하면 토큰을 받는다", "잘못된 credentials로 로그인하면 401이 반환된다"처럼 행동을 기술한다.

**테스트할 모듈:**

- **TenantAgent 로그인 API**: 올바른 username/password → 200 + access_token. 틀린 password → 401. 비활성 계정 → 401. 존재하지 않는 username → 401. 기존 `tests/test_tenants.py` 패턴 참조.

- **TenantAgent 보호 엔드포인트**: TenantAgent JWT 없이 `/api/tenant/config/` 호출 → 401. TenantAgent JWT로 호출 → 200. TENANT_KEY로 호출 → 401 (어드민 엔드포인트는 더 이상 TENANT_KEY 불허). 기존 `tests/test_tenants.py` 패턴 참조.

- **TenantAgent CRUD**: 팀원 생성 → 목록에 나타남. 비활성화 → 해당 계정으로 로그인 불가. 기존 `tests/test_tenants.py` 패턴 참조.

- **Operator Tenant 생성**: 응답에 `agent_username`과 `agent_temp_password` 포함. 해당 credentials로 TenantAgent 로그인 API 호출 시 성공. 기존 `tests/test_tenants.py` 패턴 참조.

- **어드민 UI `TenantLogin.jsx`**: username/password 폼 렌더링, 성공 시 `onLogin` 호출, 실패 시 에러 메시지. 기존 `src/test/` 패턴 참조.

- **어드민 UI `AgentsTab.jsx`**: 팀원 목록 렌더링, 팀원 추가 후 임시 password 표시, 비활성화 버튼 동작. fetch mock 사용.

## Out of Scope

- 비밀번호 재설정 이메일 플로우 (SMTP 인프라 필요)
- 첫 로그인 시 비밀번호 강제 변경
- TenantAgent 역할 구분 (admin vs agent)
- TenantAgent별 접근 가능한 탭/기능 제한
- 세션 무효화 (JWT revocation, token blacklist)
- 로그인 실패 횟수 제한 (rate limiting)
- TenantAgent 활동 로그

## Further Notes

- `tenant_id`를 로그인 폼에 어떻게 입력받을지 UX 결정 필요: 직접 UUID 입력은 불편하므로, Operator가 전달하는 초기 credentials 패키지에 `tenant_id`를 포함하거나, Tenant 이름으로 조회하는 엔드포인트를 추가하는 방향을 고려할 수 있다. 단, MVP에서는 UUID 직접 입력도 허용 범위.
- 기존 `/api/tenant/*` 엔드포인트에 접근하던 자동화 스크립트(TENANT_KEY 사용)가 있다면, 마이그레이션 기간 동안 해당 엔드포인트에 TenantKeyAuth를 임시로 병행 허용하는 방안을 검토할 수 있다. 이 PRD에서는 즉시 전환을 기본으로 한다.
