# PRD: RAG Query, Checkpoint 조회, HITL 실시간 Visitor 메시지

Status: ready-for-agent

## Problem Statement

TenantAgent가 Knowledge Base와 LangGraph 실행 상태를 직접 검증할 수 없고,
HITL 상담 탭에서 Visitor가 보낸 메시지가 실시간으로 나타나지 않는다.

구체적으로:

1. **RAG 블랙박스**: 문서를 업로드한 후 "이 질문에 어떤 청크가 매칭되는가"를 확인할 방법이 없다.
   LLM이 엉뚱한 답변을 내도 RAG 검색 결과가 문제인지 프롬프트가 문제인지 구분할 수 없다.

2. **Checkpoint 불투명**: LangGraph가 실제로 LLM에 무엇을 전달했는지 (system prompt, RAG 주입, 누적 메시지)
   볼 수 없다. `Conversation Memory`가 올바르게 누적되고 있는지 확인할 수 없다.

3. **HITL 실시간 메시지 미표시**: 상담원이 HITL 탭을 열어도 Visitor가 새로 보낸 메시지가
   실시간으로 표시되지 않는다. 상담 중 Visitor 메시지를 보려면 페이지를 수동 새로고침해야 한다.
   또한 EscalationCard에 대화 히스토리 자체가 없어 맥락을 파악하기 어렵다.

## Solution

1. **RAG Query 엔드포인트**: TenantAgent가 임의의 쿼리를 입력하면, Knowledge Base에서 매칭되는
   DocumentChunk를 유사도 점수와 함께 반환한다.

2. **LangGraph Checkpoint 조회 엔드포인트**: ChatSession ID로 해당 세션의 LangGraph
   `channel_values`를 raw JSON으로 조회한다. Visitors 탭 세션 상세에서 접근한다.

3. **HITL EscalationCard 대화 히스토리 + 실시간 업데이트**: EscalationCard가 마운트될 때
   전체 대화 히스토리(HITL 이전 AI 대화 포함)를 로드하고, SSE를 통해 Visitor 메시지를 실시간으로 추가한다.

## User Stories

1. As a TenantAgent, I want to submit a test query against my Knowledge Base, so that I can verify which document chunks are returned for a given question.
2. As a TenantAgent, I want to see the similarity score for each returned chunk, so that I can judge whether the Knowledge Base is retrieving relevant content.
3. As a TenantAgent, I want to see which document each chunk came from, so that I can identify poorly performing documents and re-upload them.
4. As a TenantAgent, I want to control how many chunks are returned (top_k), so that I can explore more or fewer results as needed.
5. As a TenantAgent, I want to query RAG using the same authentication I use for other tenant APIs, so that there is no additional login step.
6. As a TenantAgent, I want to view the full LangGraph Checkpoint state for a ChatSession, so that I can see exactly what was sent to the LLM.
7. As a TenantAgent, I want to inspect the accumulated `messages` in the Checkpoint, so that I can verify Conversation Memory is building up correctly across turns.
8. As a TenantAgent, I want to inspect the `rag_chunks` in the Checkpoint, so that I can see which chunks were injected in the last LLM call.
9. As a TenantAgent, I want to inspect the `system_prompt` in the Checkpoint, so that I can confirm the correct prompt was used.
10. As a TenantAgent, I want to receive a 404 when I query a Checkpoint for a session that has had no LLM calls, so that I get a clear signal rather than an empty result.
11. As a TenantAgent, I want to access the Checkpoint viewer from the session detail in the Visitors tab, so that I can jump directly from a conversation to its debug state.
12. As a TenantAgent, I want to see the full conversation history inside an EscalationCard when I open the HITL tab, so that I understand the context before responding.
13. As a TenantAgent, I want to see AI messages that were sent before the escalation was triggered, so that I can understand what the AI already told the Visitor.
14. As a TenantAgent, I want Visitor messages to appear in real-time in the EscalationCard without refreshing, so that I can respond promptly.
15. As a TenantAgent, I want messages in the EscalationCard to be visually differentiated by role (Visitor / AI / 상담원), so that I can follow the conversation at a glance.
16. As a TenantAgent, I want the EscalationCard chat window to auto-scroll to the latest message when a new one arrives, so that I don't miss incoming messages.

## Implementation Decisions

### RAG Query 엔드포인트

- **엔드포인트**: `POST /api/tenant/documents/query`
- **인증**: TenantAgent JWT (기존 `tenant_agent_auth`)
- **요청 바디**: `{ query: string, top_k?: int }` — `top_k` 기본값 5
- **응답**: `[{ document_name, content, score }]` — `score`는 L2Distance 값 (낮을수록 유사)
- **retriever 수정**: 현재 `retrieve_chunks()`는 거리 값을 버리고 텍스트만 반환한다.
  점수 포함 버전인 `retrieve_chunks_with_scores()`를 retriever 모듈에 추가한다.
  기존 `retrieve_chunks()`는 그래프 노드에서 계속 사용하므로 그대로 유지한다.

### LangGraph Checkpoint 조회 엔드포인트

- **엔드포인트**: `GET /api/tenant/sessions/{session_id}/checkpoint`
- **인증**: TenantAgent JWT
- **응답**: LangGraph `PostgresSaver`가 저장한 `channel_values` raw JSON
- **Checkpoint 없음**: 404 반환
- **테넌트 격리**: `session_id`가 요청 Tenant 소속인지 `ChatSession` 조회로 검증 후 Checkpoint 접근
- **구현**: `_create_checkpointer()`(기존 graph 모듈)를 재사용하여 `saver.get()` 호출.
  connection은 조회 후 즉시 close.
- **직렬화**: `channel_values`의 LangChain 객체는 LangGraph가 JsonPlusSerializer로 저장하므로
  그 raw 값을 그대로 JSON 응답으로 반환한다.

### HITL EscalationCard 대화 히스토리 + 실시간 업데이트

- **초기 로드**: `EscalationCard` 마운트 시 `GET /api/tenant/escalations/{id}/messages` 호출.
  HITL 이전 AI 대화 포함 전체 메시지를 표시한다.
- **실시간 업데이트**:
  - `openEscalationStream()`에 `visitor_message` 이벤트 리스너 추가.
  - 이벤트 payload에 `session_id`가 포함되므로, `HitlTab`이 해당 session_id의 EscalationCard에 메시지를 라우팅한다.
- **UI**: EscalationCard 내부에 스크롤 가능한 채팅창을 메시지 입력창 위에 배치.
  role별 정렬: `user` → 왼쪽, `assistant`/`human_agent` → 오른쪽.
  새 메시지 수신 시 자동 스크롤.
- **`api.js`에 추가**: `queryRag(agentToken, query, topK)`, `getSessionCheckpoint(agentToken, sessionId)`, `getEscalationMessages(agentToken, escalationId)`

## Testing Decisions

좋은 테스트는 구현이 아닌 **외부에서 관찰 가능한 동작**을 검증한다.
내부 함수 호출 여부가 아니라, API 응답 바디와 상태 코드, DB 레코드를 기준으로 assertion한다.
Mock을 사용하지 않으며 실제 PostgreSQL, Redis, pgvector를 사용한다.

**테스트 대상 모듈:**

- **RAG Query 엔드포인트** (`test_rag.py` 확장)
  - `POST /api/tenant/documents/query`가 매칭된 청크, 문서명, score를 반환하는지
  - `top_k` 파라미터가 결과 수를 제한하는지
  - 다른 Tenant의 청크가 섞이지 않는지 (테넌트 격리)
  - prior art: `test_rag.py`의 기존 ingestion/retrieval 테스트

- **Checkpoint 조회 엔드포인트** (`test_chat_session.py` 확장)
  - `run_chat_agent()` 실행 후 `GET /api/tenant/sessions/{session_id}/checkpoint`가 200을 반환하는지
  - 응답에 `messages`, `rag_chunks` 등 state 키가 포함되는지
  - LLM 호출 전 세션에 대해 404를 반환하는지
  - 다른 Tenant의 session_id로 조회 시 404를 반환하는지
  - prior art: `test_langgraph_checkpoint_table_exists`, `test_multi_turn_creates_multiple_assistant_replies`

- **HITL 대화 히스토리 및 실시간 메시지** — 백엔드는 Issue 34/35에서 이미 테스트 완료.
  프론트엔드 동작(EscalationCard 렌더링, SSE 이벤트 라우팅)은 TDD 범위 밖.

## Out of Scope

- RAG Query UI (DocumentsTab에 쿼리 입력창 추가) — API만 구현, UI는 별도 이슈
- Checkpoint viewer UI (Visitors 탭 세션 상세에 "LangGraph 상태 보기" 버튼) — API만 구현, UI는 별도 이슈
- `retrieve_chunks_with_scores()`의 cosine similarity 전환 — 현재 L2Distance 유지
- Checkpoint 특정 필드 필터링 또는 마스킹
- 실시간 채팅 히스토리의 페이지네이션

## Further Notes

- `retrieve_chunks_with_scores()`는 `retrieve_chunks()`와 거의 동일한 쿼리이나
  pgvector의 `.annotate(score=L2Distance(...))` 패턴으로 점수를 함께 반환한다.
- Checkpoint `channel_values` 내 `lc_messages` 필드는 LangChain 직렬화 형식이므로
  프론트엔드에서 파싱 없이 그대로 표시해도 디버그 용도로 충분하다.
- HITL `visitor_message` SSE 이벤트는 Issue 35에서 이미 백엔드 구현 완료.
  이번 PRD의 프론트엔드 작업이 이를 소비하는 마지막 퍼즐 조각이다.
