Status: ready-for-agent

# PRD: Knowledge Graph 인스펙터 (RAG 테스트 패널 폐기)

## Problem Statement

GraphRAG 전환 후에도 어드민의 "RAG 테스트" 패널은 옛 청크 검색과 똑같아 보여, Tenant가 자기 Knowledge Graph(엔티티·관계)를 실제로 볼 수 없다. 패널은 Text Unit 검색 결과만 나열할 뿐 그래프 구조를 드러내지 않는다.

## Solution

"RAG 테스트" 패널을 폐기하고, 어드민에 **Knowledge Graph 인스펙터** 탭을 새로 만든다. Tenant가 엔티티를 검색하면 매칭 엔티티와 그 이웃을 **노드-엣지 그래프로 시각화**하고, 노드를 클릭하면 이웃을 점진적으로 확장하며, 선택한 노드의 기본 정보를 디테일 패널에 보여준다.

## User Stories

1. As a TenantAgent, I want a dedicated "지식그래프" tab, so that I can explore my Knowledge Graph visually.
2. As a TenantAgent, I want to search entities by name/description, so that I can find a starting point in the graph.
3. As a TenantAgent, I want the search to render the matched entities and their direct relations as a node-edge graph, so that I see structure, not just a list.
4. As a TenantAgent, I want to click a node to expand its neighbors, so that I can traverse the graph progressively.
5. As a TenantAgent, I want a detail panel showing the selected node's name, type, description, and source documents, so that I understand each entity.
6. As a TenantAgent, I want the graph scoped to my tenant, so that I never see other tenants' graphs.
7. As a TenantAgent, I want the inspector to start empty with a prompt, so that a huge graph isn't loaded all at once.
8. As a developer, I want the old "RAG 테스트" panel, `/query` endpoint, and its api client removed, so that there is one clear way to inspect the knowledge base.
9. As a developer, I want chat retrieval (local/global search) unaffected, so that removing the RAG test panel doesn't change answering.

## Implementation Decisions

### 백엔드 (GraphStore + API)

- GraphStore deep module에 추가(둘 다 tenant 스코프):
  - `search_entities(term)`: 이름/설명에 term이 포함된 엔티티 목록(name/type/description/source_document_ids).
  - `neighbors(name)`: 해당 엔티티 + 1홉 이웃과 그 사이 관계를 `{nodes, edges}`로 반환.
- API(`rag_router`):
  - `GET /rag/graph/search?q=<term>` → 매칭 엔티티 + 각 1홉 이웃을 합친 `{nodes, edges}`.
  - `GET /rag/graph/neighbors?entity=<name>` → 그 엔티티의 1홉 `{nodes, edges}`.
  - `nodes`: `{name, type, description, source_document_ids}`. `edges`: `{source, target, description}`.
- 폐기: `POST /rag/query` 엔드포인트 제거. (`vector_search`는 chat local_search가 쓰므로 유지.)

### 프론트 (admin)

- TenantDashboard에 새 탭 **"🕸️ 지식그래프"**(KnowledgeGraphTab).
- 검색 전 빈 상태 + "엔티티를 검색하세요" 안내.
- 검색 입력 → `/graph/search` → 노드-엣지 그래프 렌더(**react-force-graph** 의존성 추가).
- 노드 클릭 → `/graph/neighbors` 호출 → 기존 뷰에 병합(점진 확장) + 선택 노드 디테일 패널(name/type/description/source docs).
- DocumentsTab에서 "RAG 테스트" 패널 제거. api.js의 `queryDocuments` 제거, `searchGraph`/`graphNeighbors` 추가.
- "청크 보기" / 그래프 신선도 / 재구축은 유지.

### 범위 밖

- 본문(Text Unit) 의미 검색 — Text Unit↔Entity 엣지가 없어 v1 제외(후속).
- Community 브라우징/색상 — v1 디테일 패널은 기본 정보만.
- 전체 그래프 일괄 렌더.

## Testing Decisions

좋은 테스트는 캔버스 픽셀이 아니라 외부 동작(데이터·DOM)을 검증한다.

- **백엔드(실제 Neo4j, 결정적)**: `search_entities`가 이름/설명 매칭 엔티티를 반환하고 tenant 격리됨; `neighbors`가 엔티티+1홉 `{nodes,edges}`를 반환; `/graph/search`·`/graph/neighbors` 엔드포인트 계약; `/query` 제거 후에도 chat 검색(local/global) 무영향.
- **프론트(e2e)**: 캔버스 렌더 픽셀은 단언하지 않는다. 대신 "지식그래프 탭 진입 → 빈 안내 → 검색 → 결과(노드 수/디테일 패널 DOM via data-testid)"를 단언. 그래프 노드는 data-testid나 사이드 패널로 검증.
- Prior art: `tests/test_graph_store.py`, `tests/test_graph_search.py`; e2e는 `rag-test-panel.spec.js`(폐기 후 대체), `chunk-inspector.spec.js`.

## Out of Scope

- 의미(content) 검색, Community 시각화, 전체 그래프 렌더, 노드-엣지 편집(읽기 전용 인스펙터).

## Further Notes

데이터 계층 대부분은 GraphStore에 이미 존재(query_entities/relations). 신규는 `search_entities`/`neighbors`와 2개 엔드포인트, 그리고 프론트 시각화 탭. react-force-graph 의존성 추가가 admin의 첫 그래프 viz 라이브러리다.
