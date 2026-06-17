# 12 — AdminUI — Tenant 뷰 (문서·Memory·Config)

Status: ready-for-agent

## What to build

AdminUI의 Tenant 전용 뷰를 구현한다. Tenant가 TENANT_KEY로 로그인하여 RAG 문서 관리, Visitor Memory 조회·편집·삭제, TenantConfig(system_prompt·model_id) 수정을 한 화면에서 수행할 수 있다.

**문서 관리 탭**
- 파일 업로드(PDF/TXT 드래그앤드롭), 문서 목록(이름·상태·업로드일), 삭제

**Visitor Memory 탭**
- VisitorId 검색, Memory 항목 목록, 항목 수정·삭제

**설정 탭**
- `system_prompt` 텍스트 편집기
- `model_id` 드롭다운 (OpenRouter 주요 모델 목록)
- 저장 버튼

## Acceptance criteria

- [ ] TENANT_KEY로 로그인 → Tenant 뷰 접근 가능
- [ ] 문서 업로드 → 목록에 `pending` 상태로 즉시 표시, polling으로 `ready`/`failed` 갱신
- [ ] 문서 삭제 → 목록에서 제거
- [ ] VisitorId 검색 → 해당 Visitor의 Memory 목록 표시
- [ ] Memory 항목 수정 저장 → 변경 내용 즉시 반영
- [ ] Memory 항목 삭제 → 목록에서 제거
- [ ] system_prompt 수정 저장 → 이후 ChatSession에 반영
- [ ] model_id 변경 저장 → 이후 ChatSession에 반영

## Blocked by

- `06-rag-document-ingester.md`
- `08-visitor-memory.md`
- `09-tenant-config-self-service.md`
- `11-admin-ui-operator.md`
