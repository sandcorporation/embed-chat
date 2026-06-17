# 07 — RAG 검색 LangGraph 통합

Status: ready-for-agent

## What to build

LangGraph 그래프에 `retrieve` 노드를 추가하여, 메시지 수신 시 RAGRetriever가 pgvector에서 해당 Tenant의 관련 청크를 검색하고 프롬프트에 주입하도록 한다.

- `RAGRetriever`: `retrieve(tenant_id, query, top_k) -> List[Chunk]`
- 항상 `tenant_id`로 필터링하여 Tenant 간 격리 보장
- `top_k` 기본값 환경 변수로 설정 가능
- LangGraph `assemble_prompt` 노드에서 RAG 청크를 시스템 프롬프트에 삽입

## Acceptance criteria

- [ ] Tenant의 RAG Knowledge Base에 있는 내용을 질문하면 LLM이 해당 문서 내용을 인용해 답변
- [ ] Tenant A의 문서를 Tenant B의 ChatSession에서 검색되지 않음 (격리 검증)
- [ ] RAG 청크가 없을 때(빈 Knowledge Base)도 LLM 응답 정상 동작
- [ ] 통합 테스트: pgvector 실제 연결, `retrieve` 결과가 프롬프트에 포함되는지 확인
- [ ] 통합 테스트: Tenant 격리 — 타 Tenant 문서 미반환

## Blocked by

- `05-langgraph-openrouter-chat.md`
- `06-rag-document-ingester.md`
