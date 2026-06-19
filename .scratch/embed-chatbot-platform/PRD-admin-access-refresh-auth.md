# PRD: 어드민 인증 Access/Refresh 토큰 전환

Status: ready-for-agent

관련 ADR: [ADR-0013](../../docs/adr/0013-admin-access-refresh-token-auth.md)
관련 용어: CONTEXT.md — Access Token / Refresh Token / Session Family

## Problem Statement

어드민 UI(Operator·TenantAgent) 로그인은 지금 **무상태 단일 JWT 1개(24시간)** 를 발급해 **localStorage**에 저장한다. 이 방식은 세 가지가 아프다:

- **취소 불가**: 무상태라 로그아웃하거나 토큰이 탈취돼도 만료 전까지 24시간 그대로 유효하다. 서버가 강제로 무효화할 방법이 없다.
- **긴 탈취 수명**: 토큰 하나가 새면 24시간 동안 전권으로 쓸 수 있다.
- **XSS 노출**: localStorage라 사이트에 주입된 스크립트가 토큰을 그대로 읽어 빼낼 수 있다.

운영자는 "토큰이 새도 짧게만 유효하고, 침해를 알아챘을 때 즉시 끊을 수 있는" 인증을 원한다.

## Solution

무상태 단일 JWT를 **단수명 Access Token + 장수명·취소가능 Refresh Token** 쌍으로 교체한다.

- 일상 API 호출은 **30분짜리 Access Token**으로 한다(탈취돼도 30분만 유효). 프론트는 이를 sessionStorage에만 둔다.
- Access가 만료되면 **Refresh Token**(httpOnly 쿠키, JS가 못 읽음)으로 자동·무중단 재발급한다. 사용자는 끊김을 못 느낀다.
- Refresh는 서버 DB에 보관돼 **언제든 강제 폐기**할 수 있다. 로그아웃·비밀번호 변경·침해 의심 시 즉시 끊긴다.
- 여러 기기에서 동시에 로그인해도 서로 독립적이며, 한 기기에서 로그아웃하거나 한 기기의 토큰이 탈취돼도 다른 기기는 멀쩡하다.

## User Stories

1. As a TenantAgent, I want my login to issue a short-lived access token, so that a stolen token is only usable for 30 minutes.
2. As a TenantAgent, I want my session to refresh automatically in the background, so that I am not forced to re-login every 30 minutes.
3. As a TenantAgent, I want the refresh credential kept in an httpOnly cookie, so that a script injected into the page cannot read or exfiltrate my long-lived session.
4. As an Operator, I want the same access/refresh scheme on my dashboard login, so that the platform's highest-privilege account has the same blast-radius protection.
5. As a TenantAgent, I want a page reload to reuse my still-valid access token, so that hammering refresh does not spam the server with re-issuance.
6. As a TenantAgent, I want to stay logged in across reloads within a tab, so that refreshing the page does not log me out.
7. As an Operator, I want my access token cleared when I close the tab, so that a shared machine does not leave a usable token behind.
8. As a TenantAgent, I want to log out of just this device, so that my other devices remain logged in.
9. As a TenantAgent, I want a "log out of all devices" action, so that I can kill every session at once if I suspect compromise.
10. As an Operator, I want a "log out of all devices" action, so that I can revoke all my sessions centrally.
11. As a TenantAgent, I want changing my password to log out all my existing sessions, so that a leaked old credential cannot keep a session alive.
12. As a security-conscious operator, I want a refresh token to rotate on every use, so that an old copy of a refresh token becomes useless after one renewal.
13. As a security-conscious operator, I want a reused (already-rotated) refresh token to revoke the whole session family, so that concurrent use by a thief is detected and shut down.
14. As a security-conscious operator, I want each login session to have a hard 14-day absolute expiry that rotation cannot extend, so that a thief who silently rotates a stolen token while I am dormant still gets force-logged-out at the cap.
15. As a TenantAgent logging in from a second device, I want an independent session, so that revoking the first device does not disturb the second.
16. As a TenantAgent, I want the live escalation stream to keep working past 30 minutes, so that my background refresh does not silently break my HITL notifications.
17. As a TenantAgent, I want a failed (401) API call to transparently refresh and retry, so that an access token expiring mid-action does not surface an error to me.
18. As a TenantAgent, I want to be returned to the login screen when my refresh has been revoked or expired, so that I get a clear re-auth prompt instead of broken silent failures.
19. As an Operator, I want my refresh cookie scoped to the refresh endpoint path only, so that it is not sent on every unrelated API request.
20. As a returning TenantAgent, I want the app to silently restore my access token on boot from my refresh cookie, so that I do not have to re-enter credentials after a reload even though access lives only in sessionStorage.
21. As an operator running the platform, I want expired and revoked refresh tokens cleaned up, so that the table does not grow unbounded.
22. As a TenantAgent, I want logging out to revoke the refresh on the server (not just clear the browser), so that the cookie copy cannot be replayed.
23. As a developer, I want the old single-JWT localStorage path removed in a clean cutover, so that there is no dual-token ambiguity (existing users re-login once).
24. As an Operator, I want my session family scoped per device just like agents, so that multi-device behavior is consistent across both subject types.
25. As a TenantAgent, I want a refresh attempt with no cookie / garbage cookie to be cleanly rejected, so that unauthenticated states are unambiguous.

## Implementation Decisions

### Modules (deep modules extracted for isolation)

- **Refresh Token Service (backend, deep module)** — the core. Small interface, deep logic (hashing, family tracking, rotation, reuse detection, absolute cap, revocation). Conceptual interface:
  - `issue_session(subject) -> raw_refresh` — 새 Session Family 시작(최초 로그인). `family_expires_at = now + 14d`.
  - `rotate(raw_refresh) -> raw_refresh` — 회전. 재사용/만료/폐기 시 예외. 같은 family, `family_expires_at` 상속.
  - `revoke_family(family_id)` / `revoke_all(subject)` — 폐기.
  - subject는 Operator | TenantAgent (정확히 하나).
- **Access Token Generator (backend)** — 기존 `create_operator_token`/`create_tenant_agent_token`을 **TTL 30분** access 생성기로 재사용(`ACCESS_TOKEN_EXPIRE_MINUTES`를 30으로). 검증 경로(`OperatorAuth`/`TenantAgentAuth`)는 그대로.
- **Refresh Cookie Helper (backend)** — Set-Cookie 표준화: `HttpOnly; Secure; SameSite=Strict; Path=<refresh endpoint>`. subject별 쿠키 이름·경로 분리. 폐기 시 만료 쿠키로 삭제.
- **Frontend Auth Client (deep module)** — `authFetch` 단일 진입점: sessionStorage access 부착, **401 시 1회 투명 refresh→원요청 재시도**, 부팅 silent refresh, login/logout. 모든 어드민 API 호출이 이걸 경유.
- **Frontend App Session State** — localStorage→sessionStorage(access). 부팅 시 silent refresh로 복구, 로그아웃 시 서버 폐기 호출.
- **Escalation Stream Client** — silent refresh 콜백에서 EventSource close→재오픈(새 access 쿼리).

### Schema

- **`RefreshToken` 모델 신설**: nullable FK `operator`/`tenant_agent`(정확히 하나만 set, CHECK 제약), `family_id`(UUID, indexed), `token_hash`(unique, indexed — 원문 미저장), `family_expires_at`, `used`(bool), `revoked`(bool), `created_at`. 회전 조회는 `token_hash` 단건 lookup.

### API contracts

- `POST /api/operator/auth/login` / `POST /api/tenant/agents/auth/login`: 성공 시 body `{access_token}` + **Set-Cookie**(refresh). Family 신규 생성.
- `POST /api/operator/auth/refresh` / `POST /api/tenant/agents/auth/refresh`: **쿠키의 refresh를 읽어** 회전 → body `{access_token}` + 새 refresh Set-Cookie. 재사용/만료/폐기/쿠키없음 → 401(+ 재사용 시 family 폐기).
- `POST .../auth/logout`: 현재 family 폐기 + 쿠키 삭제.
- `POST .../auth/logout-all`: subject 전 family 폐기 + 쿠키 삭제.
- `change-password`(기존): 성공 시 `revoke_all(subject)` 호출 추가.

### Cross-cutting decisions (from ADR-0013)

- access 30분 / refresh 절대캡 14일(슬라이딩 없음) / 회전+재사용감지.
- access는 sessionStorage, refresh는 httpOnly 쿠키. localStorage 미사용.
- 다중기기 = 다중 Family, 폐기·감지 모두 Family 스코프.
- SSE는 silent refresh 시 재오픈(전용 스트림 토큰 신설 안 함).
- 클린 컷오버(듀얼지원 없음). TENANT_KEY·위젯/Visitor 인증은 범위 밖.

## Testing Decisions

**좋은 테스트**: 공개 인터페이스/외부 행위만 검증한다. RefreshToken row의 내부 컬럼을 들여다보는 대신, "회전 후 옛 토큰으로 refresh하면 401 + 같은 family의 다른 토큰도 죽는다" 같은 **관찰 가능한 결과**를 검증한다. CLAUDE.md TDD 원칙대로 실제 DB·실제 crypto를 쓰고, 외부 비결정 경계(없음 — 전부 결정적)만 예외.

**백엔드(실제 DB·실제 crypto, mock 없음):**
- Refresh Token Service deep module — 회전 성공, **재사용 감지 → family 일괄 폐기**, **절대 14일 캡 거부**, **다중기기 독립성**(F1 폐기해도 F2 생존), `revoke_all`로 전체 폐기.
- 엔드포인트 — 로그인이 access(body)+refresh(Set-Cookie) 반환 / refresh가 회전(새 access, 새 쿠키) / 쿠키 없음·만료·폐기·재사용 거부 / 로그아웃 3종(기기별·전체·비번변경) 폐기.
- Operator·TenantAgent 양쪽 모두 커버.

**프론트(vitest, jsdom — 네트워크 경계만 mock):**
- 부팅 silent refresh로 access 복구.
- 401 시 투명 refresh→원요청 1회 재시도(인터셉터).
- 로그아웃이 서버 폐기 호출 + sessionStorage 정리.
- access 갱신 시 EscalationStream EventSource 재오픈.

**Prior art**: 백엔드 인증 테스트는 기존 `backend/tests`의 로그인/auth 테스트 패턴(실제 Ninja 엔드포인트 호출, 실제 DB). 프론트는 이번 세션에 도입한 `admin/src/components/ConfigTab.test.jsx`의 vitest + `vi.mock('../api')` 네트워크 경계 패턴.

## Out of Scope

- TENANT_KEY(위젯·Identity Verification HMAC용 서버사이드 키) — 사람 로그인 세션이 아니므로 그대로.
- Visitor/위젯 인증(`/chat/stream`의 tenant_key) — 범위 밖.
- 기존 24시간 토큰과의 듀얼지원/마이그레이션 셰임 — 클린 컷오버.
- 동시 Family 수 상한, 디바이스 목록 UI(어떤 기기들이 로그인 중인지 보여주기) — 추후.
- CSRF 토큰 별도 발급 — SameSite=Strict로 충분(refresh 엔드포인트 한정), 추가 토큰 없음.

## Further Notes

- prod·dev 모두 admin과 API가 동일 출처(nginx 단일 server / vite 프록시)라 쿠키가 CORS 없이 성립함을 확인함.
- 만료·폐기 row 정리는 단순 주기 작업(관리 커맨드 또는 Celery beat)으로 충분 — 별도 슬라이스로 분리 가능.
- 본 전환은 인증 스킴·DB 스키마·쿠키 모델을 동시에 바꾸므로 되돌리기 비용이 큼 → ADR-0013에 근거 기록.
