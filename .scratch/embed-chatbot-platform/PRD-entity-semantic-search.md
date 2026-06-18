Status: ready-for-agent

# PRD: 엔티티 의미 검색 (다국어 하이브리드)

## Problem Statement

Knowledge Graph 인스펙터에서 엔티티 검색이 어휘 부분일치(substring)뿐이라, 언어/표기 간극을 못 넘는다. 예: 엔티티 `"OSD Menu"`가 있는데 `"메뉴"`로 검색하면 글자가 안 겹쳐 0건이다. Tenant가 자기 도메인 용어(한글)로 영문 추출 엔티티를 찾지 못한다.

## Solution

엔티티(이름+설명)를 다국어 임베딩(bge-m3)으로 인덱싱하고, 검색을 **하이브리드**(어휘 부분일치 ∪ 의미 벡터)로 바꾼다. `"메뉴"` 같은 한↔영·동의어 질의가 `"OSD Menu"`를 의미적으로 찾고, 정확/문서레이블 검색은 어휘로 그대로 신뢰성 있게 동작한다. 검색 결과는 기존처럼 매칭 엔티티 + 1홉 서브그래프로 렌더된다.

## User Stories

1. As a TenantAgent, I want to search entities in my own language (Korean) and find English-named entities, so that "메뉴" finds "OSD Menu".
2. As a TenantAgent, I want synonyms/near-terms to match entities semantically, so that I don't need the exact wording.
3. As a TenantAgent, I want exact and document-label searches to still work reliably, so that semantic ranking doesn't hide precise matches.
4. As a TenantAgent, I want the search result to render the matched entities and their 1-hop neighbors as before, so that the inspector behavior is unchanged except better recall.
5. As a developer, I want entity embeddings computed once per ingestion in a batch, so that ingestion stays efficient.
6. As a developer, I want an entity embedding refreshed when its description changes on re-ingestion, so that search reflects the latest description.
7. As a TenantAgent, I want existing entities (created before this feature) to become semantically searchable after a graph rebuild, so that I don't have to re-upload everything.
8. As a TenantAgent, I want graph search scoped to my tenant, so that no cross-tenant entity leaks.
9. As a developer, I want all of this through the GraphStore boundary and the existing embedding model (bge-m3), so that it's consistent with the current GraphRAG stack (ADR-0007).

## Implementation Decisions

### 임베딩 대상 & 모델
- 엔티티당 `name + description`을 하나의 텍스트로 임베딩(bge-m3, 다국어, 1024차원). type은 제외.
- 임베딩 모델/경로는 기존 `get_embeddings`(ollama bge-m3) 재사용.

### 계산 위치 (배치)
- `graph_ingester`가 추출된 엔티티(+문서 레이블 엔티티)의 `name+description`을 모아 `get_embeddings` **1회 배치 호출** → `upsert_entity(embedding=...)`로 전달. Text Unit 처리와 동일 패턴.
- 같은 엔티티가 새 문서에서 다시 추출되면(MERGE) description과 함께 임베딩을 **재계산**(최신값 반영).

### GraphStore 변경 (deep module)
- `upsert_entity`에 `embedding` 인자 추가 → 노드에 저장.
- `ensure_entity_vector_index()`: `Entity.embedding`에 대한 Neo4j 벡터 인덱스(1024 cosine, Text Unit 인덱스와 별도). 인제스션 시 보장.
- `search_entities(term)`를 **하이브리드**로: (1) 기존 어휘 부분일치(name/description CONTAINS), (2) 쿼리 임베딩으로 Entity 벡터 인덱스 top-k(기본 10) — 두 결과를 **이름 키로 dedup**해 합친다. 둘 다 tenant 스코프. 벡터 인덱스가 아직 없거나 임베딩 없는 엔티티는 어휘 경로로 처리(무중단).

### 기존 엔티티 백필
- CommunityBuilder 재구축(rebuild) 시 **임베딩이 없는 엔티티를 백필**(name+description 배치 임베딩). truncate 없이 기존 그래프도 의미 검색 가능. 백필 전에도 어휘 검색은 동작.

### 검색 표면 (무변경에 가까움)
- `/rag/graph/search`는 계약 동일(매칭 엔티티 + 1홉 `{nodes, edges}`). 내부적으로 `search_entities`가 하이브리드라 recall만 개선. 프론트 인스펙터(KnowledgeGraphTab) 변경 없음.
- 관계(relation)는 임베딩하지 않는다(엔티티에서 이웃 확장으로 도달).

## Testing Decisions

좋은 테스트는 저장 방식이 아니라 검색 동작을 검증한다: 다국어/동의어 질의가 의미적으로 맞는 엔티티를 반환하는가, 정확/부분 일치가 여전히 동작하는가, tenant 격리, 백필로 기존 엔티티가 검색되는가.

- **실제 Neo4j + 실제 bge-m3(결정적)**: `"메뉴"` 질의가 `"OSD Menu"` 엔티티를 반환(핵심 회귀); 정확/부분 일치 유지; tenant 격리; 임베딩 없는(기존) 엔티티는 어휘로 잡히고, 재구축 백필 후 의미 검색으로도 잡힘.
- LLM(추출)은 기존 `apps/agent/llm` 경계 Fake로 결정적. 임베딩은 실제 bge-m3(다국어 의미 매칭이 검증 대상이므로 실제 사용).
- 검증 대상: GraphStore(`upsert_entity` 임베딩 저장, `search_entities` 하이브리드, `ensure_entity_vector_index`), graph_ingester(배치 임베딩), community_builder(백필), `/rag/graph/search` 엔드포인트.
- Prior art: `tests/test_graph_search.py`, `tests/test_graph_store.py`, `tests/test_graph_community.py`.

## Out of Scope

- 관계(relation) 임베딩/의미 검색.
- 본문(Text Unit)→엔티티 매핑 검색(별도 엣지 필요, 별건).
- 엔티티 정규화/동의어 병합(별칭을 같은 노드로 합치는 entity resolution) — 의미 "검색"과 별개.
- 프론트 인스펙터 UI 변경(검색 입력/렌더는 그대로).

## Further Notes

ADR-0007("임베딩은 Neo4j 벡터 인덱스로 통합")의 자연스러운 확장이므로 신규 ADR은 만들지 않는다. bge-m3가 다국어라 한↔영 간극을 임베딩 공간이 메꾸는 것이 핵심 enabler다. 하이브리드로 두는 이유는 순수 벡터가 정확/레이블 일치를 의미 순위에 묻을 수 있어서다.
