# 11 — AdminUI — Operator 뷰 (React)

Status: ready-for-agent

## What to build

별도 레포의 React 어드민 앱에서 Operator 전용 뷰를 구현한다. Operator가 로그인하여 Tenant 목록을 확인하고, 새 Tenant를 생성해 TENANT_KEY를 받고, Tenant를 정지·삭제할 수 있다.

- Operator 로그인 페이지 (JWT 발급)
- Tenant 목록 페이지: 이름, 활성 상태, 생성일, ChatSession 수 표시
- Tenant 생성 모달: 이름 입력 → 생성 후 TENANT_KEY 1회 표시 (복사 유도)
- Tenant 정지/삭제 액션
- prod Compose에서 빌드된 정적 파일을 Nginx 서빙

## Acceptance criteria

- [ ] Operator 로그인 → JWT 저장 → 인증 필요 페이지 접근 가능
- [ ] Tenant 목록이 표 형태로 표시됨
- [ ] Tenant 생성 → TENANT_KEY가 모달에 1회 표시됨 (이후 재조회 불가 안내 포함)
- [ ] Tenant 정지 → 목록에서 비활성 상태로 표시
- [ ] Tenant 삭제 → 목록에서 제거
- [ ] 비로그인 상태에서 페이지 접근 시 로그인 페이지로 리다이렉트

## Blocked by

- `02-operator-auth-tenant-management.md`
