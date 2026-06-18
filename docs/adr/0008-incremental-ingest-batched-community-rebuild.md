# ADR-0008: Incremental entity ingest + batched community rebuild

## Status
Accepted

## Context
GraphRAG(ADR-0007)에서 Entity/관계 추출은 문서 단위로 국소적이지만, Community 탐지와 Community 요약은 Tenant 그래프 **전체**에 대한 전역 연산이다. 문서 하나를 올릴 때마다 전체 커뮤니티+요약을 다시 만들면 매우 비싸다(커뮤니티마다 LLM 요약 호출). 한편 Tenant는 문서를 올리면 곧바로 검색이 되길 기대한다.

## Decision
인제스션을 **증분**으로, Community 재구축을 **배치/트리거**로 분리한다.

- 업로드 시 그 문서의 Entity/관계를 즉시 그래프에 반영한다 → **Local Search는 업로드 직후 동작**.
- Community 탐지 + 요약은 업로드마다 돌리지 않고, **업로드 후 디바운스 자동 재구축 + 어드민 수동 "재구축" 버튼**으로 갱신한다.
- Tenant 그래프에 **Graph Freshness** 상태(`fresh` / `stale` / `rebuilding`)를 둔다. 문서 추가·삭제로 stale이 되며, 재구축 후 fresh로 돌아간다. 문서별 `Document.status`(해당 문서 추출 완료=local 준비)와는 별개다.
- stale 상태에서도 직전 Community 요약으로 **Global Search는 계속 동작**한다(약간 outdated 허용).
- 문서 삭제는 노드/관계의 출처 집합에서 해당 문서를 제거하고, 출처가 빈 노드/관계만 prune한 뒤 그래프를 stale로 표시한다(공유 Entity 보존).

## Consequences
- Global Search 결과가 재구축 전까지 최신 문서를 반영하지 못할 수 있다(의도된 trade-off: 비용 ↔ 신선도). 어드민이 Graph Freshness로 이를 인지하고 수동 재구축할 수 있다.
- "문서는 ready인데 Global 요약은 stale"이라는 두 단계 상태가 존재 — 미래 독자가 의아할 수 있어 본 ADR로 근거를 남긴다.
- 디바운스/수동 트리거 양쪽이 동일한 재구축 경로를 타도록 단일화해야 한다.
