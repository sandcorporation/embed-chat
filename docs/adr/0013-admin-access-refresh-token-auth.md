# ADR-0013: 어드민 인증을 stateful Access/Refresh 토큰으로 전환

## Status
Accepted (구현은 후속)

## Context
현재 어드민 UI(Operator·TenantAgent) 인증은 **무상태 단일 JWT**다. 로그인 시 `type`(operator/tenant_agent)을 담은 HS256 JWT 1개를 발급하고(`ACCESS_TOKEN_EXPIRE_MINUTES = 60*24`, **24시간**), 프론트는 이를 **localStorage**(`op_token`/`agent_token`)에 넣어 모든 호출에 `Authorization: Bearer`로 보낸다. 갱신 메커니즘이 없어 만료되면 재로그인해야 하고, **무상태라 만료 전 강제 폐기가 불가능**하다(로그아웃·침해 시에도 토큰이 24시간 살아 있음). localStorage라 XSS가 토큰을 그대로 읽어갈 수 있다.

목표는 **토큰 탈취 시 피해 범위(blast-radius) 축소**다: 단순히 "더 오래 로그인 유지"가 아니라, 탈취된 자격증명이 짧게만 유효하고 서버가 즉시 무효화할 수 있어야 한다.

prod·dev 모두 admin(`/admin-ui/`)과 API(`/api/`)가 **동일 출처**로 서빙된다(prod: nginx 단일 server 블록, dev: vite 프록시). 따라서 쿠키 기반 자격증명이 CORS 없이 성립한다.

## Decision
**무상태 단일 JWT를 stateful Access/Refresh 토큰 쌍으로 교체한다. Operator·TenantAgent 양쪽에 적용하고, TENANT_KEY(위젯·HMAC용 서버사이드 키)는 범위 밖.**

- **Access Token**: 단수명(**30분**) Bearer JWT. 프론트 **sessionStorage**에만 보관. 기존 `create_operator_token`/`create_tenant_agent_token`을 30분 TTL의 access 생성기로 재사용.
- **Refresh Token**: 장수명, **httpOnly·Secure·SameSite=Strict 쿠키**로만 전달(JS가 못 읽음 → XSS가 장수명 토큰 탈취 불가). 쿠키 Path는 refresh 엔드포인트로 한정해 노출면 최소화. 원문은 쿠키에만, DB엔 **해시만** 저장(비밀번호 동일 원칙).
- **stateful 저장(`RefreshToken` 모델)**: nullable FK 2개(operator/tenant_agent, 정확히 하나만 set) + `family_id`(UUID) + `token_hash` + `family_expires_at` + `used`/`revoked`. 무상태 JWT와 달리 **서버가 만료 전 강제 폐기 가능** — 이게 refresh 도입의 실질 명분.
- **회전 + 재사용 감지**: refresh 사용 시 옛 토큰을 `used` 처리하고 같은 Family로 새 토큰 발급. 이미 `used`된 토큰이 다시 오면 **도난으로 간주해 Family 전체 폐기**(동시 사용 케이스 차단).
- **절대 수명 상한(슬라이딩 아님)**: Family는 최초 로그인 +14일 `family_expires_at`을 가지며 **회전이 이를 상속**(연장 안 함). 탈취자가 정상 사용자 휴면 중 무한 회전으로 세션을 영속화하는 케이스를 하드캡으로 차단.
- **다중기기 = 다중 Family**: 로그인 1회 = Family 1개. 한 주체가 여러 기기에서 동시 다수 Family 보유. 회전·감지·폐기가 전부 Family 스코프라 한 기기 침해가 타 기기로 번지지 않는다.
- **로그아웃 정책 3종**: (1) 이 기기 — 현재 Family만 폐기 + 쿠키 삭제, (2) 전체 기기 — 주체의 전 Family 폐기(어드민 UI 버튼), (3) **비밀번호 변경 시 자동 전체 폐기**.
- **SSE 단수명 화해**: 에스컬레이션 스트림은 access를 쿼리로 받으므로, 프론트가 silent refresh 시 EventSource를 **close→재오픈**해 새 access로 재연결(전용 장수명 스트림 토큰을 새로 만들지 않음).
- **프론트 무중단 갱신**: 부팅 시 silent refresh로 access 복구, 401 시 투명 refresh→원요청 재시도 인터셉터. F5 시 sessionStorage의 유효 access를 재사용해 불필요한 재발급·회전 churn 방지.
- **클린 컷오버**: 듀얼지원 셰임 없음. 구 24시간 localStorage 토큰은 무효화되고 사용자는 1회 재로그인.

## Considered Options
- **무상태 refresh JWT(취소 불가)**: 기각. 취소 불가면 토큰 하나를 둘로 나눈 것뿐 — blast-radius 축소(본 목적)를 못 얻고 복잡도만 증가.
- **localStorage에 refresh 보관**: 기각. 장수명 토큰이 XSS에 그대로 노출 → 본 목적 무력화.
- **슬라이딩 만료**: 기각. 휴면 사용자 케이스에서 탈취자가 회전으로 세션 영속화 가능.
- **subject_type/id 제네릭 주체**: 기각. 종류가 딱 2개라 nullable FK 2개가 무결성·cascade 면에서 더 깔끔.
- **access를 메모리에만 보관**: 기각. F5마다 silent refresh 왕복 발생. sessionStorage는 단수명 access만 담아 보안 등급 동일하면서 새로고침 부하 제거.
- **SSE 전용 장수명 스트림 토큰**: 기각. 토큰 종류·장수명 자격증명만 추가되는 과설계.

## Consequences
- **auth 모듈 확장**: `create_*_token`은 30분 access 생성기로, 신규 refresh 발급/검증/회전/폐기 deep module + `RefreshToken` 모델·마이그레이션 추가.
- **로그인 엔드포인트 변경**: 응답이 access(body) + refresh(Set-Cookie). 신규 `/auth/refresh`(쿠키→새 access + 회전 쿠키), `/auth/logout`(Family 폐기 + 쿠키 삭제), 전체 로그아웃, `change-password`에 전체 폐기 호출 추가.
- **프론트 재작성**: localStorage→sessionStorage(access) + 쿠키(refresh), fetch 래퍼(투명 refresh·재시도), 부팅 silent refresh, SSE 재오픈.
- **테스트**: 백엔드는 실제 DB·crypto로 회전·재사용감지·절대캡·다중기기 독립성·로그아웃 3종 검증, 프론트는 vitest로 부팅 refresh·401 재시도·로그아웃 폐기·SSE 재오픈 검증.
- 만료·폐기된 `RefreshToken` row는 주기적 정리 필요(동시 Family 수 상한은 두지 않음).
