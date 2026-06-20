# ADR-0016: Global Search 제거 (Community 요약 폐기) — 엔티티 해소는 잔존

## Status
Accepted (구현은 후속 — issues 120-121)

## Context
ADR-0007(GraphRAG)은 검색을 **Local**(엔티티 중심)과 **Global**(Community 요약 기반, 코퍼스 전체 sensemaking)으로 나눴다. Global Search의 품질을 측정한 결과 결함이 명백했다(HP모니터 그래프 모사 → 실제 커뮤니티 생성):

- **요약이 엔티티 *이름만*, 한 문장으로 생성**된다 — `community_builder`가 LLM에 멤버 이름 목록만 넘긴다. 8개 엔티티 → *"This community ... centers on HP monitors and their associated features, software, and physical components."* 한 줄. 구체 지식 0.
- **스펙 소실**: `지원 해상도`(description="1920×1080")가 멤버였는데도 요약에 `1920`·`해상도` 부재 → Global로 라우팅돼도 스펙을 못 답함.
- **단일 거대 커뮤니티**: 커뮤니티=연결요소(union-find)라 단일 제품 매뉴얼은 8엔티티 → 커뮤니티 1개로 degenerate. 의미 있는 하위 주제 분할 0.
- **dump-all**: `global_search_node`가 모든 요약을 통째로 주입(관련도 랭킹·map-reduce 없음) → 토큰 폭탄 + 노이즈.
- **언어 드리프트**: 한국어 코퍼스/봇인데 요약이 영어로 생성(프롬프트가 영어).

또한 지원 챗 질의는 대부분 *특정형*(local)이고, 방금 도입한 **원문 폴백(issue 119)** 이 스펙형 특정 Q&A를 이미 커버한다. 즉 Global은 *드물게 호출되며, 호출되면 공허한 요약을 비싸게 던지는* 경로다.

## Decision
**Global Search를 제거한다. 단, Local search가 의존하는 엔티티 해소(SAME_AS)는 잔존시킨다.**

- 챗에서 `route_search`(local/global 분류 LLM 호출 1회)·`global_search`·`search_scope`를 제거하고 **START → local_search 직결**한다. 분류 LLM 호출이 사라져 메시지당 토큰·지연이 준다.
- Community 서브시스템(탐지 연결요소 + 이름-only 요약 + 저장)을 제거한다: `global_search_node`, GraphStore의 `query_community_summaries`/`upsert_community`/`clear_communities`.
- **`rebuild_communities`는 "엔티티 해소 전용 잡"으로 축소**한다 — 임베딩 백필 + `resolve_equivalences` + `SAME_AS` upsert만 수행. `search_entities`(local)가 SAME_AS 클러스터로 dedup하므로 이 부분은 필수다.
- 어드민 "그래프 재구축" 엔드포인트와 Graph Freshness(stale/rebuilding/fresh)는 **유지**한다(이제 = 엔티티 해소 갱신).

## Considered Options
- **(A) Global을 정석 GraphRAG로 개선** (계층 Leiden 커뮤니티 + description·관계 기반 요약 + map-reduce 관련도 랭킹): 기각. 작업량이 크고, 측정상 품질 0 + 지원 봇에서 sensemaking 질의 빈도가 낮아 ROI가 안 맞는다.
- **요약 생성만 수정**(이름→description+관계, 한국어): 기각(부분책). 근본적으로 지원 봇에 Global이 거의 불필요하고, local+원문폴백으로 충분.
- **현행 유지**: 기각. 공허한 요약 + 불필요한 분류 LLM 호출이 토큰·품질을 함께 깎는다(측정).

## Consequences
- **챗 토폴로지 단순화**: route_search·global_search 노드 소멸, 메시지당 LLM 분류 호출 1회 절감.
- **엔티티 해소 테스트 재배선**: 기존 해소 특성화 테스트가 Community 개수로 클러스터를 검증했으므로, **SAME_AS 기준 단언으로 바꾼다**(해소 동작은 불변).
- **ADR-0007 부분 무효화**: GraphRAG의 Local/그래프 구조는 유지하되 Global만 제거. 향후 sensemaking 수요가 생기면 ADR-0007의 정석 Global을 재도입할 수 있다(현 이름-only 구현이 아니라).
- **sensemaking형 질의 미지원**: "전체 공통 주제" 같은 코퍼스 총괄 질의는 더 이상 전용 경로가 없다(특정형은 local+폴백으로 커버).
