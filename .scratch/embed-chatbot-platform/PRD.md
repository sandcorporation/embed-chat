# PRD: Embeddable Chatbot Platform

Status: ready-for-agent

---

## Problem Statement

B2B SaaS 기업들은 자사 웹사이트에 AI 챗봇을 삽입하고 싶지만, LLM 연동·세션 관리·RAG 구축·보안을 처음부터 개발하는 데 많은 시간과 비용이 든다. 특히 각 고객사마다 다른 응대 매뉴얼과 톤앤매너를 적용하고, 개별 방문자의 맥락을 기억하는 기능을 직접 구현하기 어렵다.

## Solution

Tenant(고객사)가 자사 서버에서 EmbedToken을 발급받아 `<iframe>`으로 챗봇을 삽입하면, Visitor(최종 사용자)는 즉시 맞춤형 AI 상담을 받을 수 있는 멀티테넌트 챗봇 플랫폼을 제공한다. Operator는 어드민 페이지에서 Tenant를 관리하고, Tenant는 자기 RAG 문서·시스템 프롬프트·LLM 모델을 직접 설정한다. Visitor의 대화 이력과 장기 기억은 자동으로 축적·관리된다.

## User Stories

### Visitor (최종 사용자)

1. As a Visitor, I want to see a chat widget appear on the Tenant's website without installing anything, so that I can start a conversation immediately.
2. As a Visitor, I want LLM responses to stream in word-by-word, so that I don't have to wait for the full answer before reading.
3. As a Visitor, I want my conversation history to persist when I return to the site later, so that I don't have to repeat context I already provided.
4. As a Visitor, I want the chatbot to respond in the language and tone appropriate for me, so that the experience feels personalized.
5. As a Visitor, I want the chatbot to know my account information (e.g. name, plan tier) without me having to type it, so that I get relevant answers faster.

### Tenant (고객사)

6. As a Tenant, I want to receive a TENANT_KEY from the Operator so that I can securely generate EmbedTokens from my server.
7. As a Tenant, I want to call an API endpoint with my TENANT_KEY + VisitorId + VisitorContext to receive a time-limited EmbedToken, so that I can render the chat iframe securely without exposing secrets to the browser.
8. As a Tenant, I want to embed the chatbot with a single `<iframe src="...?token={EmbedToken}">` line, so that integration into my site is minimal.
9. As a Tenant, I want to upload PDF and TXT documents as my RAG Knowledge Base, so that the chatbot answers questions based on my product manuals and policies.
10. As a Tenant, I want to write and edit a Base System Prompt, so that the chatbot's tone and persona match my brand.
11. As a Tenant, I want to select which OpenRouter LLM model powers my chatbot, so that I can balance cost and quality for my use case.
12. As a Tenant, I want to view and edit Visitor Memory entries, so that I can correct inaccurate long-term memories the LLM extracted.
13. As a Tenant, I want to delete a Visitor's Memory entries, so that I can honor data removal requests.
14. As a Tenant, I want to see the ingestion status of uploaded documents (pending / processing / ready / failed), so that I know when my RAG Knowledge Base is active.
15. As a Tenant, I want to delete individual documents from my RAG Knowledge Base, so that I can keep my knowledge base up to date.

### Operator (서비스 운영자)

16. As an Operator, I want to create Tenant accounts and issue TENANT_KEYs, so that I can onboard new customers.
17. As an Operator, I want to suspend or delete a Tenant account, so that I can manage contracts and abuse.
18. As an Operator, I want to view all active Tenants and their configuration, so that I can monitor the platform's usage.
19. As an Operator, I want to provide a default system prompt template that Tenants can customize, so that all new Tenants start with sensible defaults.
20. As an Operator, I want to view per-Tenant document and ChatSession counts, so that I can plan capacity.

## Implementation Decisions

### Module Architecture

**1. EmbedTokenService**
- EmbedToken은 서명된 JWT로 구현. 페이로드: `tenant_id`, `visitor_id`, `visitor_context`, `exp`(TTL).
- TENANT_KEY로 서명. 검증 시 Tenant가 활성 상태인지 DB 조회.
- 토큰 TTL은 환경 변수로 설정 가능 (기본값 5분).

**2. ChatSessionManager**
- EmbedToken 검증 성공 시 ChatSession 레코드 생성 (PostgreSQL).
- 동일 VisitorId에 대한 기존 미완료 세션 재사용 정책 필요.
- ChatSession은 `tenant_id`, `visitor_id`, `session_id`, `created_at`, `ended_at` 포함.

**3. SSEBridge**
- Visitor의 SSE 연결은 `session_id` 기준 Redis 채널 구독.
- LLM 토큰은 Celery worker → Redis publish → SSEBridge → Visitor 순으로 전달.
- Nginx `proxy_buffering off` + `X-Accel-Buffering: no` 헤더 필수.
- Django Ninja의 `StreamingHttpResponse`로 SSE 응답 구현.

**4. LangGraphChatAgent**
- LangGraph 상태 그래프. 노드 구성:
  - `retrieve` — RAGRetriever 호출
  - `assemble_prompt` — system_prompt + VisitorContext + VisitorMemory + RAG 결과 + ConversationHistory 조합
  - `call_llm` — OpenRouter 모델 스트리밍 호출, 토큰을 Redis publish
  - `extract_memory` — 세션 종료 후 Visitor Memory 추출 (비동기 Celery 태스크)
- Conversation Memory(ConversationHistory)는 LangGraph state로 관리, ChatSession 종료 시 PostgreSQL 저장.

**5. RAGRetriever**
- pgvector `cosine` 유사도 검색. 항상 `tenant_id`로 필터링하여 Tenant 간 격리 보장.
- 상위 K개 청크 반환 (기본값 환경 변수로 설정).

**6. DocumentIngester (인터페이스)**
- 인터페이스: `ingest(file_bytes, mime_type, tenant_id, document_id) -> None`
- 구현체: `PDFIngester`, `TXTIngester`
- 공통 파이프라인: 파일 → 청킹 → 임베딩(OpenRouter Embeddings 또는 별도 모델) → pgvector upsert
- Celery 태스크로 래핑. 문서 상태: `pending → processing → ready / failed`

**7. VisitorMemoryManager**
- `get(tenant_id, visitor_id)` → 현재 메모리 목록
- `upsert(tenant_id, visitor_id, key, value)` — LLM 자동 추출 및 어드민 수동 편집 공통 경로
- `delete(tenant_id, visitor_id, memory_id)`
- PostgreSQL 테이블로 영구 저장.

**8. TenantConfigService**
- Tenant별 설정: `model_id` (OpenRouter 모델 식별자), `system_prompt`, `tenant_key_hash`
- Operator만 Tenant 생성/삭제/정지 가능.
- Tenant는 자기 `model_id`, `system_prompt`만 수정 가능.

**9. AdminAPI (Django Ninja)**
- Operator 스코프 라우터: `/operator/tenants/`, `/operator/tenants/{id}/`
- Tenant 스코프 라우터: `/tenant/config/`, `/tenant/documents/`, `/tenant/visitors/{visitor_id}/memory/`
- 공통 라우터: `/embed/token/` (EmbedToken 발급), `/chat/stream/` (SSE), `/chat/message/` (메시지 POST)
- 인증: Operator는 세션/JWT, Tenant API는 TENANT_KEY Bearer, 위젯은 EmbedToken.

**10. EmbedWidget (React — 별도 레포)**
- iframe 안에서 렌더링되는 단일 React 앱.
- URL 파라미터에서 EmbedToken 추출 → SSE 연결 → 메시지 입력 POST.
- SSE 이벤트 타입: `token` (스트리밍 청크), `done` (완료), `error`.

**11. AdminUI (React — 별도 레포)**
- Operator 뷰: Tenant 목록·생성·정지.
- Tenant 뷰: 문서 업로드·목록·삭제, TenantConfig 편집, Visitor Memory 조회·편집·삭제.
- 별도 레포, Vite + React 스택.

### 인프라 (ADR-0005 기반)
- `docker-compose.yml` (base) + `docker-compose.dev.yml` + `docker-compose.prod.yml`
- 서비스: `api`, `worker` (Celery), `db` (PostgreSQL + pgvector), `redis`, `nginx`
- 프론트엔드: dev에서 네이티브 `npm run dev`, prod에서 빌드 정적 파일을 Nginx 서빙
- 시크릿: `.env` + `.env.example`

### 데이터 흐름 요약
```
Visitor 방문
→ Tenant 서버: POST /embed/token {tenant_key, visitor_id, visitor_context}
→ Operator API → EmbedToken(JWT, TTL 5분) 반환
→ Tenant 서버: <iframe src="/embed?token={EmbedToken}">
→ EmbedWidget: GET /chat/stream?token={EmbedToken} (SSE 연결)
→ ChatSessionManager: ChatSession 생성
→ SSEBridge: Redis 채널 구독
→ EmbedWidget: POST /chat/message {session_id, content}
→ LangGraphChatAgent: RAG 조회 → 프롬프트 조립 → OpenRouter 스트리밍
→ Redis publish → SSEBridge → Visitor SSE 스트림
→ 세션 종료: Celery 태스크 → VisitorMemory 추출 → PostgreSQL 저장
```

## Testing Decisions

**좋은 테스트의 기준**
- 구현 상세(함수 내부, ORM 쿼리 방식)가 아닌 외부 동작(입력 → 출력, 상태 변화)을 검증한다.
- 경계: 유효하지 않은 입력, 만료된 토큰, 존재하지 않는 Tenant 등 에지 케이스를 반드시 포함한다.
- OpenRouter 호출은 테스트에서 mock 처리한다. pgvector·Redis는 통합 테스트에서 실제 서비스를 사용한다.

**테스트 대상 모듈**

| 모듈 | 테스트 유형 | 핵심 검증 항목 |
|------|------------|---------------|
| `EmbedTokenService` | 단위 | 유효 토큰 발급, TTL 만료 거부, 잘못된 TENANT_KEY 거부, Tenant 정지 시 거부 |
| `ChatSessionManager` | 단위 | 유효 토큰으로 세션 생성, 만료 토큰 거부, 동일 VisitorId 세션 재사용 정책 |
| `RAGRetriever` | 통합 | Tenant 격리 검증 (타 Tenant 문서 미반환), 유사도 검색 결과 K개 제한 |
| `DocumentIngester` | 단위 | PDF/TXT 청킹 결과, 임베딩 호출 횟수, 실패 시 상태 `failed` 기록 |
| `VisitorMemoryManager` | 단위 | upsert → get → delete 순환, Tenant 간 격리 |
| `SSEBridge` | 통합 | Redis 메시지 발행 후 SSE 스트림 수신, 연결 해제 후 구독 정리 |
| `LangGraphChatAgent` | 통합 | RAG 결과·VisitorContext·VisitorMemory가 프롬프트에 포함되는지, OpenRouter mock 응답이 Redis에 publish되는지 |
| `AdminAPI` | 통합 | Operator 엔드포인트를 Tenant 토큰으로 호출 시 403, Tenant 엔드포인트 타 Tenant 데이터 접근 시 404 |

## Out of Scope

- CI/CD 파이프라인 (추후 결정, ADR-0005)
- 순수 정적 사이트(서버사이드 없는 Tenant)의 EmbedToken 발급 지원
- 실시간 Visitor 모니터링 (라이브 채팅 감시)
- Visitor 간 채팅 (1:1 Visitor-LLM만 지원)
- 결제·플랜·사용량 과금 시스템
- Docker Swarm / Kubernetes 기반 수평 확장
- `<script>` 태그 방식 위젯 (ADR-0003)
- WebSocket (ADR-0001)
- 전용 벡터 DB (ADR-0002)
- Tenant 셀프 가입

## Further Notes

- CONTEXT.md의 용어(Operator, Tenant, Visitor, EmbedToken, ChatSession, VisitorContext, RAG Knowledge Base, DocumentIngester, Visitor Memory, Conversation Memory, TenantConfig)를 모든 이슈·코드·커밋 메시지에서 일관되게 사용할 것.
- ADR-0001 ~ ADR-0005가 핵심 기술 결정을 담고 있으므로 구현 전 반드시 숙지.
- DocumentIngester 인터페이스를 확장할 때 기존 PDF/TXT 구현을 참고 패턴으로 사용할 것 (DOCX, URL 크롤링 등).
- Nginx SSE 설정 (`proxy_buffering off`)은 스트리밍이 동작하지 않을 때 첫 번째 점검 지점.
