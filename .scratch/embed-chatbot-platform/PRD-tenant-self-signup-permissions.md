# PRD — Tenant Self-Signup + 권한 비트(Admin/Member) 인가 모델

Labels: ready-for-agent

기반 결정: [ADR-0025](../../docs/adr/0025-tenant-self-signup-permission-bits.md) · 용어: [CONTEXT.md](../../CONTEXT.md)

## Problem Statement

오늘 Tenant 계정은 **Operator가 만들어 자격증명을 전달**해야 생긴다. 신규 고객이 스스로 시작할 수 없어
온보딩이 Operator 병목에 묶인다. 또한 한 Tenant 안의 TenantAgent는 **역할 구분이 전혀 없어** 모든 상담원이
팀원 생성·키 회전·Slug 변경 같은 조직 단위 행위까지 동등하게 할 수 있다 — 실수·남용에 무방비고, 단일
관리자 계정을 비활성화하면 조직이 통째로 lockout된다.

## Solution

Tenant가 **직접 가입**해 조직과 첫 관리자가 된다. 가입은 `조직 이름 + username + password`만 받아 Tenant와
그 조직의 **첫 Tenant Admin**을 만든다(Operator 개입 없음). 조직 안에서 권한은 **Tenant Admin / Tenant
Member** 두 역할로 나뉜다 — Member는 일상 운영을 다 하되 *되돌리기 어렵거나 라이브를 끊는* 세 가지(팀원
관리·TENANT_KEY 회전·Slug 변경)만 못 한다. 한 조직은 항상 최소 1명의 활성 Admin을 유지하며(lockout 방지),
사고 시 TENANT_KEY가 break-glass 복구 채널이 된다. Operator의 수동 프로비저닝도 그대로 공존한다.

## User Stories

1. As a prospective tenant, I want to sign up with an organization name, username, and password, so that I can start using the platform without waiting for an Operator.
2. As a prospective tenant, I want to be told immediately if my organization name is already taken, so that I can pick a different one.
3. As a prospective tenant, I want "Acme" and "acme" to be treated as the same name, so that near-duplicate orgs don't collide or confuse login.
4. As a newly signed-up tenant, I want to automatically become the first Tenant Admin of my organization, so that I can manage everything from the start.
5. As a newly signed-up tenant, I want to log in right after signup with my organization name + username + password, so that I can access the admin UI immediately.
6. As a Tenant Admin, I want to create team member accounts, so that my colleagues can help operate the chatbot.
7. As a Tenant Admin, I want to choose each new member's role (Admin or Member), so that I grant only the access they need.
8. As a Tenant Admin, I want to promote a Member to Admin or demote an Admin to Member, so that responsibilities can change over time.
9. As a Tenant Admin, I want to deactivate a team member, so that departed colleagues lose access.
10. As a Tenant Admin, I want to rotate the TENANT_KEY, so that I can respond to a leaked secret.
11. As a Tenant Admin, I want to change the public chatbot Slug, so that I can control the embed URL.
12. As a Tenant Admin, I want to edit all configuration (providers, prompt, scope, HITL, business hours), so that I can fully tune the bot.
13. As a Tenant Member, I want to operate HITL (claim/message/resolve escalations, take over sessions), so that I can do my counselor job.
14. As a Tenant Member, I want to view sessions, checkpoints, retrievals, visitors, and memories, so that I can support customers with context.
15. As a Tenant Member, I want to manage documents (upload, edit, delete, refetch, rebuild graph), so that I keep the knowledge base current.
16. As a Tenant Member, I want to edit non-sensitive configuration (prompt, scope, HITL settings, provider keys), so that I can run day-to-day operations.
17. As a Tenant Member, I must NOT be able to manage team members, so that org membership stays under Admin control.
18. As a Tenant Member, I must NOT be able to rotate the TENANT_KEY, so that I can't sever the live widget/Identity-HMAC integration.
19. As a Tenant Member, I must NOT be able to change the Slug, so that I can't break the embedded chatbot URL.
20. As a Tenant Member, when I attempt an Admin-only action, I want a clear "permission denied" (403), so that I understand why it failed.
21. As a Tenant Member, I want Admin-only controls hidden or disabled in the admin UI, so that I'm not tempted by actions I can't perform.
22. As a Tenant Admin, I want the system to prevent deactivating or demoting the last active Admin, so that my organization can never be locked out.
23. As a locked-out organization (zero active Admins by accident), I want to recover using the TENANT_KEY, so that I can mint a new Admin without Operator intervention.
24. As any TenantAgent, I want my role reflected in my session/token, so that the admin UI gates features correctly without an extra round-trip.
25. As a Tenant Admin, I want to see each team member's role in the team list, so that I know who can do what.
26. As an Operator, I want to keep provisioning tenants manually, so that enterprise/assisted onboarding still works alongside self-signup.
27. As an Operator, I want to suspend or delete abusive self-signed-up tenants, so that I can control spam without an email gate.
28. As an existing TenantAgent (pre-migration), I want to keep all my current abilities, so that the role rollout doesn't strip my access (existing agents become Admin).
29. As a programmatic integrator using the TENANT_KEY, I want it treated as Admin-equivalent, so that automated agent provisioning keeps working.
30. As a prospective tenant, I want signup abuse to be limited (light IP rate limiting), so that the open endpoint isn't trivially floodable.
31. As a Tenant Member whose password I forgot, I want my Admin to reset it (issue a new temporary password), so that I can regain access without email.

## Implementation Decisions

- **`permissions` 인가 모듈 (deep module, 신규)** — Permission 비트 카탈로그(`agents.manage`,
  `tenant_key.rotate`, `slug.change`)와 `ROLE_PERMISSIONS`(admin=전체 / member=전체−3종). `has_permission(subject,
  perm)`: subject가 **TenantAgent면 그 role**, **Tenant(=TENANT_KEY 인증)면 Admin 등가(전체 True)**. ninja
  가드 `require_permission(perm)`로 엔드포인트에 부착. 인가 판단은 전부 이 한 모듈을 통한다.
- **권한은 역할이 아니라 비트로 가드.** 엔드포인트는 필요한 Permission을 선언하고, Role은 비트 묶음의
  프리셋일 뿐. 추후 per-agent 세분화를 도입해도 가드 지점은 불변(ADR-0025 C).
- **`register_tenant(name, username, password)` 가입 모듈 (신규)** — 이름 정규화(대소문자·공백 무시)로 중복
  검사, 중복이면 거부(409/400). 통과 시 Tenant(+TENANT_KEY) + 첫 **Admin** TenantAgent를 한 트랜잭션에 생성하고
  (tenant, agent)를 반환. 공개 `POST /auth/signup`(auth=None)이 감싼다. 응답은 가입 직후 바로 로그인 가능한
  형태(또는 토큰 발급)로 한다.
- **last-admin 가드 (순수 함수/서비스)** — `agents.manage` 경로(비활성화·역할 변경)에서, 대상 변경이 "활성
  Admin 0명"을 만들면 거부(409/400). 비활성화·강등 양쪽 모두.
- **스키마 변경** — `TenantAgent.role`(choices: admin/member; 마이그레이션으로 기존 활성 전원 admin 백필).
  `Tenant.name`에 unique 제약(정규화 일관성 유지). 실 사용자 없음 → 데이터 충돌 없음.
- **로그인** — 기존 `tenant_name + username + password` 유지하되 name unique로 결정적. 가입·로그인 모두
  동일 정규화를 거친다(슬러그 정규화와 같은 결의 헬퍼 재사용 가능).
- **API 계약**
  - `POST /agent/auth/signup` (공개): {tenant_name, username, password} → 201 {tenant, 토큰 또는 로그인 지시}.
    중복 이름 409. 가벼운 IP 레이트리밋.
  - `POST /agents/` (생성): 선택 `role`(기본 member), `agents.manage` 가드.
  - `PATCH /agents/{id}/role` (신규): `agents.manage` 가드 + last-admin 가드.
  - `PATCH /agents/{id}/deactivate`: `agents.manage` 가드 + last-admin 가드.
  - `POST /reset-key`: `tenant_key.rotate` 가드.
  - `PATCH /slug/`: `slug.change` 가드.
  - `GET /agents/`: 응답에 `role` 포함.
  - 토큰(`create_tenant_agent_token`)에 `role` 클레임 추가(또는 `/me`로 노출) — UI 게이팅용.
  - Provider 키 편집(config PATCH)·문서·HITL·조회는 Member 허용(가드 없음/누구나).
- **TENANT_KEY = Admin 등가** — `_dual_auth`의 Tenant(키) 주체는 `has_permission`에서 전체 True. break-glass
  복구 + 프로그램적 프로비저닝 유지.
- **Operator create_tenant 공존** — 기존 엔드포인트 유지. (Operator 생성 시에도 첫 agent는 Admin role.)
- **Admin UI** — 공개 가입 페이지(라우트); 팀원 탭에 role 표시·역할 선택·승격/강등 + 마지막 Admin 보호 UX;
  Member에게는 reset-key·Slug 변경 등 Admin 전용 컨트롤 숨김/비활성(토큰의 role로 게이팅); 가입/로그인 폼은
  `조직 이름 + username + password`.

## Testing Decisions

- **좋은 테스트**: 공개 인터페이스(엔드포인트·모듈 함수)의 외부 행위만 검증. 내부 협력자/DB는 실제 객체로
  (CLAUDE.md). 외부 비결정 경계가 없으므로 mock 없음. 전부 Docker 풀스택에서.
- **테스트할 모듈**
  - `permissions` (deep): role→비트 매핑, `has_permission`(admin 전체 True / member 3종 False·나머지 True /
    Tenant주체 전체 True). 순수 단위.
  - `register_tenant` (deep): 정상 가입 시 Tenant+첫 Admin 생성, 중복 이름(대소문자·공백 변형 포함) 거부.
  - last-admin 가드: 마지막 활성 Admin 비활성화·강등 거부, Admin 2명일 땐 허용.
  - **게이트된 엔드포인트 행위**: Member 토큰으로 `agents.manage`/`reset-key`/`slug` 호출 시 403; Admin은 200/201.
    `POST /auth/signup` → 201 + 그 자격으로 로그인 성공. 중복 이름 가입 409.
  - 토큰/`list_agents`에 role이 실려 나오는지.
- **Prior art**: `tests/test_provider_models.py`·`tests/test_tenants.py`(엔드포인트 + 인증), `tests/test_chat_session.py`
  (테넌트 스코프 403/404), 마이그레이션·모델 테스트. 어드민 vitest는 `ConfigTab.test.tsx`·`HitlTab.test.tsx`
  패턴(가입 폼·role 변경·게이팅).

## Out of Scope

- **이메일 인프라** — 이메일 가입·검증·비밀번호 재설정 메일. 인프라가 생기면 별도 작업으로 보강(ADR-0025).
- **Owner 계층 / per-agent 커스텀 권한** — 비트 설계로 여지만 남기고 지금은 도입 안 함.
- **결제·구독·소유권 이전.**
- **강한 남용 방지**(CAPTCHA·이메일 검증·승인 큐) — v1은 공개 즉시 가입 + Operator 정지로 대응.
- **Provider 키 편집을 Admin 전용으로 막기** — 필드 단위 authz 필요. 추후.

## Further Notes

- `Tenant.name`이 전역 unique가 되면서 표시명=로그인 식별자다(스쿼팅은 알려진 trade-off, 소규모 단계 수용).
- Member lockout 복구: Admin이 임시 비밀번호 재발급(기존 create/agent 흐름과 동일). Admin 전체 lockout 복구:
  TENANT_KEY로 새 Admin 생성.
- 정규화 헬퍼는 Slug 정규화(NFC·iexact)와 같은 결로 두어 이름 충돌 판정을 일관되게.
