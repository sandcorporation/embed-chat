# 02 — Operator 인증 + Tenant 관리 (CRUD + TENANT_KEY 발급)

Status: ready-for-agent

## What to build

Operator가 로그인하여 Tenant 계정을 생성·조회·정지·삭제하고, Tenant별 TENANT_KEY를 발급하는 기능을 end-to-end로 구현한다.

- Operator 인증: JWT 기반 (로그인 → access token 발급)
- Tenant 모델: `id`, `name`, `tenant_key_hash`, `is_active`, `created_at`
- TENANT_KEY는 생성 시 한 번만 평문 반환, 이후 해시만 저장
- Django Ninja Operator 스코프 라우터 (`/api/operator/`) — Operator JWT로만 접근 가능
- TenantConfig 레코드(기본값)도 Tenant 생성 시 함께 생성

## Acceptance criteria

- [ ] `POST /api/operator/auth/login` → Operator JWT 반환
- [ ] `POST /api/operator/tenants/` → Tenant 생성 + TENANT_KEY 평문 1회 반환
- [ ] `GET /api/operator/tenants/` → 전체 Tenant 목록 반환
- [ ] `PATCH /api/operator/tenants/{id}/suspend` → Tenant 비활성화
- [ ] `DELETE /api/operator/tenants/{id}` → Tenant 삭제
- [ ] 비Operator JWT로 Operator 엔드포인트 호출 시 403 반환
- [ ] TENANT_KEY는 DB에 해시로만 저장됨 (평문 미저장 확인)
- [ ] 단위 테스트: 토큰 없음 → 403, 정지된 Tenant의 TENANT_KEY 검증 → 실패

## Blocked by

- `01-project-foundation.md`
