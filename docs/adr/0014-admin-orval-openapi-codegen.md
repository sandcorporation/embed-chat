# ADR-0014: admin HTTP 클라이언트를 OpenAPI(orval) 코드젠으로 + admin 전체 TS 전환

## Status
Accepted (구현은 후속)

## Context
admin의 HTTP 호출은 손으로 쓴 `api.js`(fetch 기반, ADR-0013의 `authFetch` 위에 ~30개 CRUD 함수)다. 백엔드 django-ninja(1.3)는 `Schema` 클래스로 응답을 정의하고 `/api/openapi.json`에 OpenAPI를 노출하는데, 프론트 함수는 이 스키마와 **수동으로 동기화**된다 — 백엔드 응답이 바뀌면 프론트가 조용히 어긋난다. admin은 순수 JS라 타입 안전도 없다.

목표는 **백엔드 OpenAPI를 단일 출처로 삼아 admin HTTP 클라이언트를 자동 생성**하고, 스키마-프론트 드리프트를 제거하는 것.

## Decision
**orval로 admin 클라이언트를 OpenAPI에서 생성하고, admin을 전체 TypeScript로 전환한다.**

- **범위: admin만.** widget은 표면이 작고 SSE 위주라 제외.
- **전체 TS 전환**: 9개 `.jsx` 컴포넌트 + auth/api + vitest를 `.tsx`/`.ts`로. orval의 타입 이득을 전면 적용.
- **평범한 클라이언트 함수 생성**(orval `client: fetch` 계열 + custom mutator). react-query 훅은 채택 안 함(데이터 패칭 패러다임 교체는 별개 작업 — TS 전환과 겹치면 회귀 위험).
- **custom mutator = 인증 딥모듈**: 생성 함수가 모두 거치는 mutator가 `authFetch` 로직을 흡수한다.
  - **URL 프리픽스로 kind 판정**: `/api/operator/*` → operator, 그 외 → agent. (라우터 마운트와 일치)
  - kind로 sessionStorage access를 `Authorization`에 부착 + `credentials:include`(쿠키) + **401 시 `refresh(kind)`→재시도** + 파싱된 `T` 반환, 재시도 후 실패 시 **throw**.
  - `auth.js`의 `getAccess/refresh/onAccessChange`를 재사용.
- **손작성 유지**(orval이 대체 안 함): `login/refresh/logout`(setAccess·쿠키·notify 같은 부수효과가 있어 순수 HTTP 아님) + `openEscalationStream`(SSE는 OpenAPI 모델링 불가).
- **백엔드 Schema 전면 정비**: 현재 `dict`/`list`/무(無) response 엔드포인트(graph search·neighbors·status, escalations 목록/메시지, memory, checkpoint 등)에 `Schema`를 부여한다. **제약: 기존 JSON 와이어 포맷을 그대로 기술(응답 형태 불변), 타입만 추가** — API 변경이 아니라 타입 부여.
- **스키마 소스 = 정적 export**: django 관리 커맨드가 `api.get_openapi_schema()`를 `openapi.json`으로 덤프 → orval이 그 파일을 소비. 실행 중 서버 불필요 → 한 번의 docker 명령으로 결정적.
- **파이프라인**: `scripts/gen-admin-api.sh` 단일 진입점(① 백엔드 docker로 openapi.json export → ② admin node docker로 orval). 모든 도구는 docker에서 실행(CLAUDE.md 규칙과 정합).
- **드리프트 강제**: 생성물은 커밋되고, **pre-commit 훅**이 재생성 후 `git diff --exit-code`로 최신성 검증. CLAUDE.md에도 "백엔드 Schema/엔드포인트 변경 시 재생성·커밋" 규칙 추가.
- **테스트 전략**:
  - mutator(인증 딥모듈)를 fake fetch로 직접 단위테스트(기존 `authFetch`/"bearer 싣는다" 테스트를 이관).
  - 손작성 auth(login/refresh/logout) + SSE 재오픈 테스트 유지.
  - **생성 클라이언트 함수는 미테스트**(얇고 orval 신뢰, 드리프트 체크가 스키마 일치 보증).
  - 컴포넌트 테스트는 생성 모듈을 mock + UI·호출 payload 검증.

## Considered Options
- **손작성 클라이언트 유지**: 기각. 스키마-프론트 수동 동기화로 드리프트 지속, 타입 없음.
- **생성 레이어만 TS(allowJs), 나머지 JS 유지**: 기각(사용자 선택). 일관성을 위해 전체 TS로.
- **react-query 훅 생성**: 기각. TS 전환과 패칭 패러다임 교체를 동시 진행하면 회귀 추적이 어렵다.
- **per-tag 분리 클라이언트로 kind 구분**: 기각. URL 프리픽스 판정이 더 단순하고 라우터 구조와 일치.
- **라이브 서버에서 openapi.json fetch**: 기각. 서버 기동 의존 → 결정성·자동화 약화.
- **약한 타입(dict/list) 수용·점진 정비**: 기각(사용자 선택). 지금 Schema를 전면 정비해 완전한 타입 커버리지 확보.
- **백엔드 편집마다 Claude Code 훅으로 codegen**: 기각. 매 편집이 docker codegen으로 느려짐. pre-commit/CLAUDE.md가 비용 대비 실효 큼.

## Consequences
- **대규모 전환**: admin 전체가 TS화(.tsx/.ts, tsconfig 추가), 컴포넌트 import 경로가 생성 모듈로 이동, 호출부가 `Response` 대신 데이터 반환·throw 계약에 맞춰 정리.
- **백엔드**: ~다수 엔드포인트에 응답 Schema 신설(와이어 포맷 불변 제약). openapi export 관리 커맨드 추가.
- **새 도구 체인**: orval + orval.config, 생성물 커밋, `scripts/gen-admin-api.sh`, pre-commit 드리프트 훅, CLAUDE.md 규칙.
- **이득**: 백엔드 OpenAPI가 admin 클라이언트의 단일 출처가 되어, Schema를 채울수록 프론트 타입이 자동으로 좋아지고 드리프트가 구조적으로 차단됨.
- ADR-0013의 auth(쿠키·sessionStorage·refresh·SSE)는 mutator/손작성으로 보존된다.
