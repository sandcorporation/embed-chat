# PRD: admin HTTP 클라이언트 OpenAPI(orval) 코드젠 + admin 전체 TS 전환

Status: ready-for-agent

관련 ADR: [ADR-0014](../../docs/adr/0014-admin-orval-openapi-codegen.md) (의존: [ADR-0013](../../docs/adr/0013-admin-access-refresh-token-auth.md))

## Problem Statement

admin의 HTTP 호출은 손으로 쓴 `api.js`(fetch 기반 ~30개 CRUD 함수)다. 백엔드 django-ninja는 `Schema`로 응답을 정의하고 `/api/openapi.json`에 OpenAPI를 노출하지만, 프론트 함수는 이 스키마와 **수동으로 동기화**된다 — 백엔드 응답이 바뀌면 프론트가 조용히 어긋나고, 런타임에야 발견된다. admin은 순수 JS라 타입 안전도 전무하다. 개발자는 "백엔드를 단일 출처로 삼아 프론트 클라이언트가 자동으로 따라오고, 어긋나면 빌드/커밋 시점에 잡히는" 구조를 원한다.

## Solution

백엔드 OpenAPI를 단일 출처로 삼아 **orval로 admin HTTP 클라이언트를 자동 생성**하고, admin을 **전체 TypeScript**로 전환한다. 인증(ADR-0013의 쿠키·sessionStorage·refresh·SSE)은 생성 클라이언트가 거치는 **custom mutator**와 손작성 auth/SSE로 보존한다. 백엔드 응답 Schema를 전면 정비해(와이어 포맷 불변, 타입만 부여) 완전한 타입 커버리지를 얻고, 재생성 파이프라인을 docker 단일 명령 + pre-commit 드리프트 체크로 강제한다.

## User Stories

1. As an admin frontend developer, I want the HTTP client generated from the backend OpenAPI schema, so that I never hand-sync request/response shapes again.
2. As a developer, I want the generated client typed in TypeScript, so that a backend response change surfaces as a compile error, not a runtime surprise.
3. As a developer, I want every generated request to carry the correct access token automatically, so that I don't wire auth per-call.
4. As a developer, I want the generated client to pick operator vs agent auth by URL prefix, so that one mutator serves both subject areas.
5. As a developer, I want a 401 on a generated call to transparently refresh and retry, so that short-lived access tokens never surface errors to the UI (preserving ADR-0013).
6. As a developer, I want the refresh cookie sent on generated calls (credentials include), so that the httpOnly refresh flow keeps working.
7. As a developer, I want hand-written auth (login/refresh/logout) kept separate from generated code, so that token-storage side effects aren't lost to codegen.
8. As a developer, I want the escalation SSE stream kept hand-written, so that the un-modellable EventSource + re-open-on-refresh behavior survives.
9. As a developer, I want the admin components migrated to TSX, so that the whole app benefits from the generated types.
10. As a developer, I want backend endpoints that currently return `dict`/`list` to gain response Schemas, so that the generated client is fully typed.
11. As a developer, I want schema tightening to preserve the exact JSON wire format, so that existing tests and the widget do not break.
12. As a developer, I want the OpenAPI schema exported by a management command without a running server, so that codegen is deterministic and dockerizable.
13. As a developer, I want a single `scripts/gen-admin-api.sh` to export the schema and run orval, so that regeneration is one command.
14. As a developer, I want all codegen tooling to run in docker, so that it matches the project's "everything in docker" rule.
15. As a developer, I want the generated client committed, so that drift can be detected against the current schema.
16. As a developer, I want a pre-commit drift check that regenerates and fails on diff, so that a stale client cannot be committed.
17. As a developer, I want CLAUDE.md to instruct regeneration after backend schema/endpoint changes, so that humans and agents follow the workflow.
18. As a developer, I want the auth mutator unit-tested with a fake fetch, so that the bearer/credentials/401-refresh/kind-by-URL logic is verified.
19. As a developer, I want generated client functions NOT unit-tested, so that I trust orval and rely on the drift check instead.
20. As a developer, I want component tests to mock the generated module, so that UI behavior and request payloads are verified without real HTTP.
21. As an Operator using the admin dashboard, I want all existing screens to keep working after the migration, so that the codegen is invisible to me.
22. As a TenantAgent using the admin dashboard, I want config/documents/visitors/agents/HITL tabs to keep working, so that nothing regresses.
23. As a developer, I want generated calls to return parsed typed data (throwing on non-2xx after refresh), so that call sites stop juggling `Response`.
24. As a developer, I want the existing auth/SSE tests relocated (mutator + hand-written), so that ADR-0013 coverage is preserved under the new structure.

## Implementation Decisions

### Modules (deep modules extracted)

- **OpenAPI export command (backend, deep)** — django 관리 커맨드가 `config.api.api.get_openapi_schema()`를 호출해 `openapi.json`으로 덤프. 실행 중 서버 불필요. 작은 인터페이스(커맨드), 결정적 출력.
- **응답 Schema 정비 (backend)** — 현재 `dict`/`list`/무 response 엔드포인트(graph search·neighbors·status·rebuild, escalations 목록/메시지/claim/typing/resolve, memory 목록/수정, session checkpoint/messages 등)에 `Schema` 신설. **와이어 포맷 불변 제약**: 기존 JSON을 그대로 기술, 응답 모양 변경 금지.
- **Auth mutator (admin, deep module)** — orval custom instance. 인터페이스: `customInstance<T>(config) => Promise<T>`. 내부: URL 프리픽스로 kind(`/api/operator/*`→operator, 그 외→agent) 판정 → sessionStorage access bearer + `credentials:include` → 401 시 `refresh(kind)`→1회 재시도 → 파싱된 `T` 반환, 실패 시 throw. ADR-0013의 `getAccess/refresh/onAccessChange` 재사용.
- **손작성 auth + SSE (admin)** — `login/refresh/logout`(부수효과: setAccess·쿠키·notify) + `openEscalationStream`(SSE 재오픈). TS로 이관, 생성 코드와 분리.
- **생성 클라이언트 (admin)** — orval가 OpenAPI에서 뽑은 per-endpoint 함수 + 타입. 커밋됨. 평범한 함수 형태(react-query 미사용).
- **Codegen 파이프라인 (scripts)** — `scripts/gen-admin-api.sh`: ① 백엔드 docker로 openapi.json export → ② admin node docker로 orval. 모두 docker.

### Architectural decisions

- 범위 admin만(widget 제외). admin 전체 TS 전환(tsconfig, .tsx/.ts, vitest TS).
- 생성 함수는 `Response`가 아니라 데이터 반환·throw 계약 → 호출부 정리.
- 스키마 소스는 정적 export(라이브 서버 미사용).
- 드리프트 강제: 생성물 커밋 + pre-commit 훅이 재생성 후 `git diff --exit-code`. CLAUDE.md에 재생성 규칙 추가.

### Schema/계약

- `openapi.json`은 export 산출물로 리포에 커밋(orval 입력 + 드리프트 기준).
- 백엔드 응답 Schema는 기존 JSON 키/형태를 1:1로 기술(타입만 부여, 값/구조 불변).

## Testing Decisions

**좋은 테스트**: 외부 행위만 검증한다. mutator는 "401이면 refresh 후 새 토큰으로 재시도", "operator URL은 operator 토큰을 싣는다" 같은 관찰 가능한 결과를, 컴포넌트는 "저장 누르면 올바른 생성함수를 이 payload로 호출"을 검증한다. 생성 코드 내부 구조는 검증하지 않는다.

- **mutator (admin, vitest)**: fake fetch로 bearer 부착·credentials include·**401 refresh→재시도**·URL프리픽스 kind판정·throw. (ADR-0013 `auth.test.js`의 401-재시도 및 "bearer 싣는다" 어서션을 이관.)
- **손작성 auth/SSE (admin, vitest)**: login/refresh/logout 부수효과 + `openEscalationStream` 재오픈(`api.logout.test.js`/`api.stream.test.js` 유지·이관).
- **생성 클라이언트 함수**: 미테스트(orval 신뢰, 드리프트 체크가 스키마 일치 보증).
- **컴포넌트 (admin, vitest)**: 생성 모듈을 mock + UI·호출 payload 검증(`ConfigTab.test`를 생성 모듈 mock으로 전환).
- **백엔드 Schema 정비 (pytest, 실DB)**: 정비한 엔드포인트가 **기존과 동일한 JSON을 반환**함을 회귀로 검증(와이어 포맷 불변).
- **export 커맨드 (pytest)**: 커맨드가 유효한 OpenAPI(paths 포함)를 덤프함.
- **Prior art**: 프론트는 이번에 도입한 vitest 패턴(`auth.test.js`, `ConfigTab.test.jsx`). 백엔드는 `test_tenants.py`의 엔드포인트 응답 검증, 관리 커맨드는 `test_refresh_prune.py`의 `call_command` 패턴.

## Out of Scope

- widget의 codegen/TS 전환.
- react-query 등 데이터 패칭 패러다임 교체.
- 백엔드 응답 **형태** 변경(타입만 부여, 와이어 불변).
- SSE를 OpenAPI/codegen으로 끌어들이기(계속 손작성).
- CI 파이프라인 신설(드리프트 체크는 pre-commit; CI 통합은 추후).

## Further Notes

- django-ninja 1.3에 `api.get_openapi_schema()` 존재 확인됨(export 커맨드 근거).
- 본 작업은 ADR-0013 직후라, mutator가 그 auth(쿠키·sessionStorage·refresh·SSE)를 흡수·보존하는 것이 성공 기준.
- 규모가 큼(백엔드 스키마 정비 + admin 전체 TS + 도구체인). `/to-issues`에서 다수 수직 슬라이스로 분할.
