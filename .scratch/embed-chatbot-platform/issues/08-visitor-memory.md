# 08 — Visitor Memory 자동 추출 + CRUD API

Status: ready-for-agent

## What to build

ChatSession 종료 후 Celery 태스크로 LLM이 대화에서 Visitor Memory를 자동 추출해 저장하고, Tenant 어드민 API를 통해 조회·수정·삭제할 수 있도록 한다. 추출된 Visitor Memory는 이후 LangGraph `assemble_prompt` 노드에서 프롬프트에 주입된다.

- `VisitorMemoryManager`: `get`, `upsert`, `delete` (tenant_id + visitor_id 기준)
- ChatSession 종료 이벤트 → Celery 태스크 → LLM으로 메모리 추출 → `upsert`
- LangGraph `assemble_prompt`에서 `get`으로 현재 Visitor Memory 조회 후 주입

## Acceptance criteria

- [ ] ChatSession 종료 후 Celery 태스크가 실행되어 Visitor Memory가 DB에 저장됨
- [ ] 이후 같은 Visitor의 새 ChatSession에서 이전 Memory가 LLM 프롬프트에 포함됨
- [ ] `GET /api/tenant/visitors/{visitor_id}/memory/` → Visitor Memory 목록 반환
- [ ] `PATCH /api/tenant/visitors/{visitor_id}/memory/{memory_id}` → Memory 수정
- [ ] `DELETE /api/tenant/visitors/{visitor_id}/memory/{memory_id}` → Memory 삭제
- [ ] 타 Tenant의 Visitor Memory 접근 시 404
- [ ] 단위 테스트: upsert → get → delete 순환, Tenant 간 격리

## Blocked by

- `05-langgraph-openrouter-chat.md`
