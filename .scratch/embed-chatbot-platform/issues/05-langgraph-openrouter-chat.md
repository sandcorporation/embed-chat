# 05 — LangGraph + OpenRouter LLM 채팅 + VisitorContext 주입

Status: ready-for-agent

## What to build

에코를 실제 LLM 응답으로 교체한다. LangGraph 상태 그래프를 구현하여 VisitorContext와 TenantConfig의 system_prompt·model_id를 조합한 프롬프트로 OpenRouter를 호출하고, 스트리밍 토큰을 Redis publish한다.

LangGraph 노드 구성:
- `assemble_prompt` — system_prompt(TenantConfig) + VisitorContext(EmbedToken) + ConversationHistory 조합
- `call_llm` — OpenRouter 스트리밍 호출, 토큰마다 Redis publish
- (RAG·Memory 노드는 이후 슬라이스에서 추가)

ConversationHistory는 LangGraph state로 관리, ChatSession 종료 시 PostgreSQL 저장.

## Acceptance criteria

- [ ] 메시지 POST → LangGraph 그래프 실행 → OpenRouter 스트리밍 응답이 SSE로 전달됨
- [ ] TenantConfig의 `system_prompt`가 LLM 시스템 프롬프트에 포함됨
- [ ] VisitorContext(예: `{"name": "홍길동"}`)가 시스템 프롬프트에 주입됨
- [ ] TenantConfig의 `model_id`로 OpenRouter 모델이 선택됨
- [ ] 같은 ChatSession 내 이전 대화가 ConversationHistory로 전달됨 (다음 메시지에서 맥락 유지)
- [ ] 통합 테스트: OpenRouter mock → 프롬프트에 system_prompt·VisitorContext 포함 여부 확인, 토큰이 Redis에 publish되는지 확인

## Blocked by

- `04-chatsession-sse.md`
