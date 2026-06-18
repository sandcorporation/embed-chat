Status: ready-for-agent

# PRD: GraphRAG (Neo4j) — 2-step 벡터 RAG 대체

## Problem Statement

Tenant의 RAG Knowledge Base가 현재 2-step 벡터 RAG(쿼리 임베딩 → pgvector 최근접 청크 → LLM)로 동작하는데, 두 종류의 질의를 제대로 답하지 못한다:

- **엔티티/관계 질의**: "이 제품의 전원 사양은?" — 답에 필요한 사양 청크가 제품명을 본문에 안 담고 있으면 검색에서 누락된다.
- **멀티홉/글로벌·요약 질의**: "이 매뉴얼들이 공통으로 권장하는 설정은?" — 여러 문서를 연결하거나 전체를 요약해야 답이 되는데, 단일 벡터 최근접으로는 불가능하다.

## Solution

RAG Knowledge Base를 Microsoft GraphRAG식 지식그래프(Neo4j)로 전환한다. 문서 인제스션이 텍스트 추출 후 LLM으로 Entity·관계를 뽑아 Tenant별 Knowledge Graph를 만들고, Community 요약을 생성한다. chat 그래프(LangGraph)는 질의를 분류해 Local Search(엔티티 이웃) 또는 Global Search(Community 요약)로 라우팅한다. Tenant는 프론트 업로드 흐름 변화 없이 같은 방식으로 문서를 올리되, 백엔드가 그래프를 구축한다. (ADR-0007, ADR-0008)

## User Stories

1. As a Visitor, I want answers about a specific product even when the document body omits the product name, so that entity-centric questions work.
2. As a Visitor, I want answers that combine facts across multiple documents, so that multi-hop questions are answerable.
3. As a Visitor, I want summary/global answers ("공통 권장 설정은?"), so that I can ask about the whole knowledge base.
4. As a Visitor, I want the AI to still escalate to HITL when uncertain or asked, so that HITL behavior is unchanged.
5. As a TenantAgent, I want to upload documents the same way as before (PDF/TXT/이미지), so that adoption requires no new skills.
6. As a TenantAgent, I want a document to become searchable (Local Search) right after upload, so that I don't wait for a full graph rebuild.
7. As a TenantAgent, I want to see when the graph's global summaries are stale and trigger a rebuild, so that I control global-answer freshness.
8. As a TenantAgent, I want deleting a document to remove only its unique contributions and keep entities shared with other documents, so that the graph stays consistent.
9. As a TenantAgent, I want my Knowledge Graph isolated from other Tenants, so that no cross-tenant leakage occurs.
10. As an Operator, I want extraction to use a platform-configured model independent of each Tenant's chat model, so that graph quality and cost are consistent.
11. As a developer, I want all graph access to go through a single tenant-scoped boundary, so that tenant_id can never be omitted.
12. As a developer, I want LLM extraction/summary to go through the existing LLM boundary, so that tests stay deterministic via the Fake.
13. As a TenantAgent, I want the RAG test panel to still let me query the knowledge base, so that I can verify retrieval.
14. As a TenantAgent, I want documents to report extraction status (pending/processing/ready/failed), so that I see per-document progress.
15. As an Operator/developer, I want Neo4j to run in the dev/prod/test docker stacks, so that the system is reproducible.

## Implementation Decisions

### 모듈 (deep modules 우선)

- **GraphStore (Neo4j 경계, deep module)**: Neo4j 접근을 좁은 인터페이스 뒤로 캡슐화. 모든 메서드가 `tenant_id`를 강제로 받아 주입한다. 책임: Entity/관계/Text Unit upsert(출처 Document 기록), 벡터 인덱스 검색, Local Search 1차 primitive(엔티티 이웃), Community 읽기, 출처-기반 삭제(고아 prune), Community 쓰기. 외부 인터페이스는 단순하고 잘 안 바뀌도록 설계.
- **GraphIngester**: 기존 텍스트 추출(PDF/OCR/이미지 단계 재사용) → LLM Entity/관계 추출(LLM 경계 경유) → GraphStore 기여. 기존 `DocumentIngester`(벡터 청크)를 대체.
- **CommunityBuilder**: Tenant 그래프에 대해 Community 탐지 + LLM 요약 생성. 배치/트리거(디바운스 자동 + 어드민 수동)로 실행, Graph Freshness 갱신.
- **Retrieval(LangGraph)**: `retrieve_node`를 `route_search → (local_search | global_search) → call_llm`로 교체. 라우팅은 `complete_structured`에 `search_scope`(local/global) 필드로 분류.
- **추출 모델 설정**: 플랫폼 env(예: `GRAPH_EXTRACTION_MODEL`), Tenant `model_id`와 분리, `apps/agent/llm` 경계 경유.

### 데이터 모델

- Knowledge Graph는 Neo4j 단일 그래프, 모든 노드/관계에 `tenant_id` 속성. 노드 종류: Entity, Text Unit, Community(요약 보유). 관계는 Entity-Entity, Text Unit-Entity, Text Unit-Document 출처 등.
- 노드/관계는 출처 Document 집합을 보유(삭제 시 참조 카운트 prune).
- 임베딩(bge-m3 1024차원)은 Neo4j 네이티브 벡터 인덱스에 저장. RAG용 pgvector(DocumentChunk)는 은퇴.
- `Document`(Postgres)는 유지: `status`(pending→processing→ready→failed, 추출 기준). Tenant 레벨 **Graph Freshness**(`fresh`/`stale`/`rebuilding`) 상태 추가.

### 인제스션·갱신 흐름

- 업로드 → 텍스트 추출 → LLM 추출 → GraphStore 기여 → Document `ready`. Local Search 즉시 가능.
- 업로드/삭제 시 그래프 `stale` 표시 → 디바운스 자동 재구축 + 어드민 수동 버튼이 동일 CommunityBuilder 경로 실행.
- 삭제: 출처에서 문서 제거 → 고아 노드/관계 prune → 그래프 stale.

### 멀티테넌시·보안

- 단일 그래프 + `tenant_id` 속성 필터. GraphStore가 유일 진입점으로 tenant_id를 항상 주입(누락 불가).

### 인프라

- docker-compose(dev/prod/test)에 Neo4j(Community) 컨테이너 추가(ADR-0005 스택 확장). 테스트 스택은 결정적이도록 실제 Neo4j 테스트 인스턴스 사용.

## Testing Decisions

좋은 테스트는 내부 그래프 표현이 아니라 외부 동작을 검증한다: "문서를 인제스트하면 그 Tenant로 엔티티를 검색할 수 있다", "본문에 제품명 없어도 제품명 질의로 답 근거가 잡힌다", "글로벌 질의가 Community 요약을 사용한다", "문서 삭제 시 공유 Entity는 남는다", "다른 Tenant 데이터가 안 섞인다", "Graph Freshness가 stale→rebuilding→fresh로 전이한다".

- **실제 객체 사용(NO MOCK 원칙)**: Neo4j는 결정적이므로 테스트 스택의 **실제 Neo4j 인스턴스**를 쓴다(임베딩 bge-m3도 실제). 
- **비결정적 외부 경계만 Fake**: LLM Entity/관계 추출·Community 요약·search_scope 분류는 `apps/agent/llm` 경계를 통해 **결정적 Fake**로 교체(기존 conftest Fake 인프라 확장 — 추출 트리플/요약/scope를 결정적으로 반환). E2E는 fake-llm 서비스 확장.
- 테스트 대상: GraphStore(인제스트·검색·삭제·테넌트 격리), GraphIngester(텍스트→그래프 기여), Retrieval 라우팅(local/global 분기 + escalation 보존), CommunityBuilder(freshness 전이).
- Prior art: `tests/test_rag.py`(인제스션/검색/테넌트 격리/삭제), `tests/test_hitl.py`/`test_chat_session.py`(그래프 라우팅·HITL 보존), conftest의 `fake_chat_llm`/`fake_text_llm`.

## Out of Scope

- 프론트 업로드 UI 변경(동일 유지) 및 엔티티 검토/온톨로지 편집기.
- 기존 pgvector 데이터 마이그레이션 — clean slate(운영 데이터 truncate)로 전환.
- Document Label의 "청크 임베딩 prefix + 재임베딩" 메커니즘(이슈 52–53) — Entity 추출로 대체되어 제거 대상이나, Label 자체(문서 식별명)는 유지.
- 동시 메시지 전송 checkpoint 손실(별개 동시성 버그) — 새 파이프라인 기준으로 별도 재평가.
- Neo4j Enterprise 멀티 DB 격리(규제 요건 없어 미채택).
- 엔티티 정규화 고도화(동의어/별칭 병합)는 추출 시 기본 처리만, 정교한 entity resolution은 후속.

## Further Notes

이 전환은 ADR-0007(GraphRAG/Neo4j가 2-step 벡터 RAG 대체, ADR-0002 supersede)와 ADR-0008(증분 인제스션 + 배치 Community 재구축)에 근거한다. 추출/요약이 LLM 경계를 타야 단위/E2E 테스트가 결정적으로 유지된다(앞서 구축한 LLM Fake 인프라 재사용). 인제스션이 무거워지므로 비용은 플랫폼 전용 추출 모델로 통제한다.
