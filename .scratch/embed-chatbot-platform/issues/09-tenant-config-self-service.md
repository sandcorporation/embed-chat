# 09 — TenantConfig 셀프서비스 (model_id + system_prompt)

Status: ready-for-agent

## What to build

Tenant가 자신의 TENANT_KEY로 어드민 API에 인증하고, `model_id`(OpenRouter 모델)와 `system_prompt`(Base System Prompt)를 직접 수정할 수 있도록 한다. 변경된 설정은 이후 ChatSession의 LangGraph 그래프에 즉시 반영된다.

- Tenant API 인증: `Authorization: Bearer {TENANT_KEY}`
- `GET /api/tenant/config/` → 현재 TenantConfig 반환
- `PATCH /api/tenant/config/` → `model_id` 또는 `system_prompt` 수정
- Operator가 제공하는 기본 system_prompt 템플릿을 TenantConfig 생성 시 기본값으로 설정

## Acceptance criteria

- [ ] `GET /api/tenant/config/` → 현재 `model_id`, `system_prompt` 반환
- [ ] `PATCH /api/tenant/config/ {model_id: "openai/gpt-4o"}` → 이후 ChatSession에서 해당 모델 사용
- [ ] `PATCH /api/tenant/config/ {system_prompt: "..."}` → 이후 ChatSession LLM 프롬프트에 반영
- [ ] 타 Tenant의 config에 접근·수정 불가 (403/404)
- [ ] 잘못된 TENANT_KEY로 접근 시 401

## Blocked by

- `02-operator-auth-tenant-management.md`
- `05-langgraph-openrouter-chat.md`
