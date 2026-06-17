# 31 — TENANT_KEY 재발급

Status: ready-for-agent

## Parent

`.scratch/embed-chatbot-platform/PRD-widget-ux-improvements.md`

## What to build

TenantAgent가 어드민 UI에서 TENANT_KEY를 직접 재발급할 수 있도록 한다. 새 키는 응답에 단 1회만 노출되며, 기존 키는 즉시 무효화된다.

- **API**: `POST /api/tenant/reset-key` (TenantAgent JWT 인증). 기존 `Tenant.reset_key()` 메서드를 호출하고 `{"new_tenant_key": "..."}` 반환. 이후 재조회 API 없음
- **어드민 ConfigTab 하단 "API KEY 재발급" 섹션**:
  - 1차 클릭: 버튼 텍스트가 경고 문구로 변경 (2단계 확인 패턴)
  - 2차 클릭: API 호출 → 황색 경고 박스에 새 키 1회 표시 + 클립보드 복사 버튼
  - "확인 완료" 클릭 시 박스 숨김, 취소 버튼으로 1단계로 복귀 가능

## Acceptance criteria

- [ ] `POST /api/tenant/reset-key` 가 `new_tenant_key` 를 포함한 200 응답 반환
- [ ] 재발급 후 기존 raw key로 `Tenant.verify_key()` 하면 `None` 반환
- [ ] 재발급 후 새 key로 `Tenant.verify_key()` 하면 Tenant 반환
- [ ] 어드민 UI에서 재발급 버튼 클릭 시 2단계 확인 flow가 작동
- [ ] 새 키가 UI에 1회 표시되며 복사 버튼으로 클립보드에 복사 가능
- [ ] "확인 완료" 후 키가 UI에서 사라짐
- [ ] 테스트: API 응답에 새 키 포함 확인, 기존 키 무효화 확인, 새 키 유효성 확인

## Blocked by

None — can start immediately
