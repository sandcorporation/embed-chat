Status: ready-for-agent

# PRD: Entity Resolution — 정체성을 이름에서 맥락으로 (Mention/Entity 분리 + 비파괴 동치)

## Problem Statement

Knowledge Graph의 Entity가 **이름 정확일치**(`MERGE {tenant_id, name}`)로만 식별된다. 이름을 정체성으로 삼은 탓에 양방향으로 샌다(특성화 테스트 `test_graph_community.py`로 확인됨):

- **과소병합**: 같은 대상의 다른 표기(`FCB1010` vs `FCB-1010`, `메뉴` vs `OSD Menu`)가 별도 노드 → 서로 다른 Community로 파편화. "이 제품 전체를 요약해줘" 같은 질의에서 같은 대상의 근거가 흩어진다.
- **과대병합**: 다른 대상의 같은 이름(동음이의 — 한강 "다리" vs 신체 "다리", 흔한 일반명 `User Manual`)이 한 노드로 뭉개진다. 이건 인제스션 시점에 이미 발생하며 설명 임베딩마저 덮어써진다. 무관한 두 문서가 한 Community로 잘못 통합된다.

세 케이스(`FCB1010/FCB-1010`=같음, `다리/다리`=다름, `Pedal A/Pedal B`=다름)에서 **이름은 세 번 다 오답**을 준다. 일치하는 신호는 맥락뿐이다.

## Solution

Entity의 정체성을 이름이 아니라 **맥락(설명·이웃 관계·출처)**으로 정의한다(ADR-0010). 추출된 개별 언급을 **Entity Mention**으로 두고(이름이 같아도 맥락이 다르면 별개 Mention), 배치 시점에 같은 referent를 가리키는 Mention들을 **Entity Equivalence(SAME_AS)** 로 묶어 하나의 Entity로 본다.

동치는 **비파괴 SAME_AS 엣지**로 표현해(노드·표기·출처 보존, 되돌림 가능), Community 재구축이 이를 연결로 소비한다. 신호는 임베딩(name+description) 유사도이며, 위험이 비대칭(과대병합이 과소병합보다 해롭다)이므로 **확신할 때만 동치**로 묶는다(보수적). Tenant·Visitor 입장에서는 같은 대상이 표기가 달라도 하나로 검색·요약되고, 같은 이름의 다른 대상은 섞이지 않는다.

## User Stories

1. As a Visitor, I want the same product referred to by different spellings (`FCB1010`/`FCB-1010`) to be treated as one, so that a summary answer doesn't miss half its evidence.
2. As a Visitor, I want a homonym ("다리" as a bridge vs. a body part) to stay distinct, so that the answer isn't contaminated by an unrelated meaning.
3. As a Visitor, I want a cross-lingual synonym (`메뉴`/`OSD Menu`) to resolve to one Entity, so that Korean and English queries hit the same knowledge.
4. As a Visitor, I want Global Search summaries to cover a product once and completely, so that fragmented duplicates don't split or double-count the evidence.
5. As a TenantAgent, I want the graph inspector to show a resolved Entity with its equivalent mentions, so that I can see "these spellings are the same thing".
6. As a TenantAgent, I want unrelated documents that happen to share a generic name (`User Manual`) to remain in separate communities, so that the inspector reflects real topical structure.
7. As a TenantAgent, I want entity search to return one resolved Entity instead of duplicate near-identical nodes, so that results are clean.
8. As a TenantAgent, I want a wrong equivalence to be reversible (an edge removed, not a node destroyed), so that resolution mistakes don't lose data.
9. As a developer, I want a deterministic EntityResolver deep module (mentions+embeddings → conservative SAME_AS pairs), so that resolution logic is unit-testable in isolation.
10. As a developer, I want resolution to run in the batch Community rebuild, so that it reuses the existing Graph Freshness lifecycle (ADR-0008).
11. As a developer, I want connected-component community detection to union over `RELATED` and `SAME_AS`, so that equivalent mentions land in the same Community.
12. As a developer, I want extraction to create Entity Mentions (not name-MERGE), so that homonyms are preserved as distinct nodes.
13. As a developer, I want resolution to be conservative (merge only on strong context match), so that over-merge (the harmful direction) is avoided and missed equivalences can be added later.
14. As a developer, I want the existing characterization tests (synonym→2, overmerge→1) to flip to the corrected expectation, so that they become the acceptance criteria.
15. As a TenantAgent, I want Local Search citations to still come from Text Units unchanged, so that resolution doesn't disturb the evidence text.
16. As a developer, I want `search_entities`/`neighbors`/`graph_search` to operate on resolved Entities, so that the API surface reflects identity, not raw mentions.
17. As a Tenant, I want resolution to respect tenant scoping, so that mentions never resolve across tenants.
18. As a developer, I want resolution to be idempotent across rebuilds, so that re-running produces the same SAME_AS set for the same graph.
19. As a developer, I want ambiguous near-duplicates (`Pedal A`/`Pedal B`) left separate, so that the conservative policy holds and search still finds both via embeddings.

## Implementation Decisions

(전부 ADR-0010을 따른다.)

### 모듈 1 — EntityResolver (신규 deep module)
임베딩을 가진 Mention 집합을 입력받아 **보수적 동치 쌍(SAME_AS 후보)**을 산출하는 순수·결정적 로직. 인터페이스는 "mentions(+embeddings) → equivalence pairs/clusters" 형태로, 외부 I/O 없이 격리 단위 테스트가 가능하다. 임계·정책(확신할 때만)을 내부에 캡슐화하고 tenant 스코프 입력만 받는다. LLM은 쓰지 않는다(향후 최종 판정 보강 후보).

### 모듈 2 — GraphStore (수정)
- Mention 노드를 `mention_id`(name이 아님)로 식별·upsert. 같은 표기·다른 맥락은 별개 Mention.
- `SAME_AS` 동치 엣지 upsert(비파괴) 및 조회.
- Entity(동치 클러스터) 단위 조회 — SAME_AS로 묶인 Mention 집합을 하나의 Entity로 본다.
- 기존 name-MERGE(`upsert_entity {name}`)는 제거/대체.

### 모듈 3 — graph_ingester (수정)
`upsert_entity` → `upsert_mention`. 추출된 언급을 Mention으로 저장(동음이의 보존). 문서 레이블·관계도 Mention 기준으로 시드. Text Unit 경로는 변경 없음.

### 모듈 4 — community_builder (수정)
rebuild에서 EntityResolver를 호출해 SAME_AS를 upsert한 뒤, `_connected_components`가 `RELATED` ∪ `SAME_AS`를 union하도록 한다. Community 멤버십은 Entity(동치 클러스터) 단위로 의미를 가진다. Graph Freshness 흐름(stale→rebuilding→fresh)은 유지.

### 모듈 5 — graph API / search (수정)
`search_entities`·`neighbors`·`graph_search` 인스펙터를 Entity(동치) 단위로. 중복 근접 노드 대신 resolved Entity와 그 동치 mention들을 반환.

### 슬라이스(트레이서 불릿) 순서
중간중간 스위트가 green을 유지하도록 4개로 쪼갠다:
1. EntityResolver deep module(단위) — 보수적 동치 클러스터링 로직.
2. Mention 노드 분리 — ingest가 Mention 생성, 동음이의 별도 노드.
3. 배치 SAME_AS + Community 소비 — rebuild가 resolution→SAME_AS→동치가 같은 Community. 특성화 테스트 전환.
4. search/neighbors/인스펙터를 Entity 단위로.

## Testing Decisions

좋은 테스트는 내부 클러스터링 구현이 아니라 외부 동작을 검증한다: 표기변이는 한 Entity로, 동음이의·근접 다른 대상은 분리로, 동치 Mention은 같은 Community로 들어가는가.

- **EntityResolver (단위)**: fixture 임베딩으로 결정적 검증 — 표기변이 쌍→동치, 동음이의("다리: 대교" vs "다리: 신체") 설명 임베딩 차이→분리, `Pedal A`/`Pedal B`→보수적 분리, tenant 격리, 멱등성. DB 불필요.
- **모듈 2~5 (통합)**: 임베딩·Neo4j는 실제 객체, LLM(추출/요약)은 `apps/agent/llm` 경계 Fake. 동음이의 Mention 분리, 표기변이가 rebuild 후 1 Community, 무관 일반명이 과대병합되지 않음, search/neighbors가 Entity 단위 반환.
- **특성화 테스트 전환**: `test_graph_community.py`의 `synonym→2`, `overmerge→1`이 resolution 도입 후 **`synonym→1`, `homonym/overmerge→2`로 뒤집힌다** — 이게 수용 기준이다.
- Prior art: `tests/test_graph_community.py`(특성화/community), `tests/test_entity_semantic_search.py`, `tests/test_graph_store.py`, `tests/test_graph_search.py`.

## Out of Scope

- LLM 기반 최종 동치 판정(ADR-0010에서 향후 보강 후보로 보류 — 1차는 보수적 임베딩).
- 어휘 정규화 신호(하이픈/대소문자) — 임베딩이 표기변이를 커버하므로 별도 도입 안 함.
- `search_entities`의 어휘∪벡터 하이브리드 검색 로직 자체 변경(Entity 단위 집계만 조정).
- 기존 그래프의 일괄 재-resolution 마이그레이션(다음 rebuild에서 자연 반영; 필요 시 어드민 rebuild 트리거).
- Text Unit/Local Search citation 경로(변경 없음).
- 계층적(다단계) Community — "더 넓은 범위"는 SAME_AS 통합으로 충족, Leiden 레벨은 별도.

## Further Notes

ADR-0010의 구현이다. 핵심 통찰: 정체성은 이름이 아니라 맥락이므로, name-MERGE를 폐기하고 Mention/Entity를 분리해야 동음이의 분리와 표기변이 병합이 **동시에** 가능하다. 위험 비대칭(과대병합 > 과소병합) 때문에 보수적으로 가고, 비파괴 SAME_AS라 놓친 동치는 추후 보강한다. 이는 ADR-0007의 "name이 식별키" 전제를 바꾸는 큰 재설계이므로 슬라이스를 작게 유지해 각 단계에서 스위트가 green을 유지하도록 한다.
