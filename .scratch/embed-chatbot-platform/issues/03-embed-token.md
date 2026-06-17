# 03 — EmbedToken 발급 & 검증

Status: ready-for-agent

## What to build

Tenant 서버가 TENANT_KEY + VisitorId + VisitorContext를 POST하면 TTL이 있는 서명된 EmbedToken(JWT)을 반환하는 엔드포인트를 구현한다. EmbedToken 검증 로직도 함께 구현하여 이후 슬라이스에서 재사용 가능하도록 모듈화한다.

EmbedToken 페이로드: `tenant_id`, `visitor_id`, `visitor_context`(JSON), `exp`(TTL).  
TTL 기본값은 환경 변수로 설정 가능 (예: `EMBED_TOKEN_TTL_SECONDS=300`).

이 엔드포인트는 TENANT_KEY Bearer 인증으로 보호된다.

## Acceptance criteria

- [ ] `POST /api/embed/token` — Body: `{visitor_id, visitor_context}`, Header: `Authorization: Bearer {TENANT_KEY}` → 서명된 EmbedToken(JWT) 반환
- [ ] 잘못된 TENANT_KEY → 401
- [ ] 정지된 Tenant의 TENANT_KEY → 403
- [ ] 만료된 EmbedToken을 검증 함수에 전달 → 거부
- [ ] VisitorContext가 EmbedToken 페이로드에 포함됨
- [ ] 단위 테스트: 유효 토큰 발급, TTL 만료 거부, 잘못된 키 거부, 정지 Tenant 거부

## Blocked by

- `02-operator-auth-tenant-management.md`
