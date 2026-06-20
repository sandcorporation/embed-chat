# PRD: Global Search 제거 — Community 요약 폐기, 엔티티 해소 잔존

Status: ready-for-agent

관련 ADR: [ADR-0016](../../docs/adr/0016-remove-global-search-keep-entity-resolution.md) (본 결정) · [ADR-0007](../../docs/adr/0007-graphrag-neo4j-replaces-2step-vector-rag.md) (Global 도입을 부분 무효화) · [ADR-0010](../../docs/adr/0010-entity-resolution-mention-entity-context-equivalence.md) (엔티티 해소는 유지)

## Problem Statement
Global Search(Community 요약 기반)는 측정 결과 품질이 거의 0이다 — 요약이 엔티티 *이름만*으로 한 문장 생성돼 공허하고(스펙·숫자 소실, 영어 드리프트), 커뮤니티가 연결요소라 단일 거대 덩어리로 degenerate하며, 모든 요약을 통째로 주입(랭킹·map-reduce 없음)해 토큰만 쓴다. 게다가 지원 봇 질의는 대부분 *특정형*이라 Global이 드물게 호출되고, 호출돼도 쓸모가 없다. 그런데도 매 메시지마다 local/global 분류를 위해 **LLM 호출이 한 번 더** 든다.

## Solution
Global Search를 **제거**한다. 챗은 항상 Local Search로 가고(분류 LLM 호출 제거), 스펙형 특정 질의는 이미 도입된 **원문 폴백(issue 119)** 이 커버한다. Community 탐지·요약·저장 코드를 들어낸다. **단, Local Search가 의존하는 엔티티 해소(SAME_AS)는 남긴다** — 그래프 재구축 잡을 "엔티티 해소 전용"으로 축소한다. 어드민 재구축 버튼과 Graph Freshness는 유지된다(이제 엔티티 해소 갱신 의미).

## User Stories
1. As a Visitor, I want specific questions answered via Local Search + source fallback, so that removing Global Search doesn't reduce the answers I actually ask for.
2. As a Visitor, I want responses to stay grounded in my tenant's documents, so that quality is unaffected by the removal.
3. As a TenantAgent, I want the bot to stop spending an extra classification LLM call per message, so that latency and cost drop.
4. As a TenantAgent, I want entity resolution (merging synonym mentions, separating homonyms) to keep working, so that Local Search dedup/quality is unchanged.
5. As a TenantAgent, I want the "그래프 재구축" button and graph freshness to keep working, so that I can still refresh entity resolution after uploads.
6. As a TenantAgent, I want no vacuous community-summary path, so that the bot never feeds an empty one-line summary as evidence.
7. As a developer, I want route_search / global_search / search_scope removed from the chat graph, so that the topology is START → local_search → call_llm (+ source fallback).
8. As a developer, I want the community subsystem (detection, name-only summary, storage) removed, so that there is no dead code behind a removed feature.
9. As a developer, I want the graph rebuild job reduced to entity resolution only, so that Local Search's SAME_AS dependency is preserved without community machinery.
10. As a developer, I want the entity-resolution characterization tests rewired to assert on SAME_AS clusters (not community counts), so that the preserved behavior stays locked down after communities are gone.
11. As a developer, I want existing Local Search, HITL, and source-fallback behavior unchanged, so that the removal is non-regressive.

## Implementation Decisions
- **챗 그래프 단순화**: `route_search_node`·`SearchRoute`·`global_search_node`·`search_scope` 채널·`_route_scope` 제거. 토폴로지는 `START → local_search → call_llm → [context_sufficient=False면 source_search→call_llm(119)] → (hitl?) → save_messages`.
- **Fake 정리**: 테스트용 `_FakeChatLLM`의 `SearchRoute` 분기 제거(분류 호출이 더는 없음).
- **Community 제거**: `global_search_node`, GraphStore `query_community_summaries`/`upsert_community`/`clear_communities`, `community_builder`의 연결요소 탐지 + 이름-only 요약 루프.
- **엔티티 해소 잔존(필수)**: 그래프 재구축 잡을 *임베딩 백필 + `resolve_equivalences` + `SAME_AS` upsert*로 축소한다. `search_entities`가 `query_mention_same_as` 클러스터로 dedup하므로 이 경로는 보존한다. 잡/엔드포인트 이름과 Graph Freshness(stale/rebuilding/fresh)는 유지(이제 '엔티티 해소 갱신' 의미).
- **어드민**: "그래프 재구축" 엔드포인트·상태 표시는 그대로 동작(트리거 대상이 community→entity-resolution으로 바뀔 뿐, 와이어 계약 불변 → orval 영향 없음).

## Testing Decisions
- **무엇이 좋은 테스트인가**: 외부 행위 — 챗이 Global 없이도 정상 응답하고(특정/일반 질의 모두 local로 처리), 엔티티 해소(동의어 병합·동음이의 분리)가 여전히 동작함을 본다. 토폴로지 내부 구조가 아니라 결과를 검증.
- **재배선**: 엔티티 해소 특성화 테스트(현재 `query_community_summaries()` 개수로 검증)를 **`query_mention_same_as()` 단언**으로 바꾼다 — 동의어는 SAME_AS 쌍 생성, 무관/동음이의는 미생성. 해소 동작 불변을 잠근다.
- **제거**: Global Search 전용 테스트(`global_search_node` 반환, 커뮤니티 생성, route 분류)는 삭제. 재구축/freshness 엔드포인트 테스트는 유지(community 단언만 제거).
- **회귀 가드(풀스택)**: 기존 챗 흐름(local 응답, HITL escalation, 119 원문 폴백)이 그대로 GREEN.
- **Prior art**: `test_graph_community.py`(해소 특성화 — 재배선 대상), `test_entity_resolver.py`/`test_entity_semantic_search.py`(해소 단위 — 유지), `test_local_source_fallback.py`(폴백 — 유지).

## Out of Scope
- **정석 Global 재구현**(Leiden 계층 + description 요약 + map-reduce): 안 한다(ADR-0016 기각). 향후 sensemaking 수요 시 별도.
- **엔티티 해소 알고리즘 변경**: 그대로 유지(이번엔 호출 경로만 축소).
- **Local Search·원문 폴백(118-119) 변경**: 없음.
- **어드민 UI 재작성**: 와이어 계약 불변이라 재생성 불필요.

## Further Notes
- 측정 근거: HP모니터 그래프 모사 → 8엔티티가 커뮤니티 1개로 붕괴, 요약은 영어 한 줄, `1920`/`해상도` 소실(ADR-0016 Context).
- `rebuild_communities`라는 이름은 더는 community를 만들지 않으므로 의미상 `rebuild_graph_entities`류로 바꾸는 게 적절하나, 와이어/태스크 호환을 위해 구현 슬라이스에서 결정한다.
