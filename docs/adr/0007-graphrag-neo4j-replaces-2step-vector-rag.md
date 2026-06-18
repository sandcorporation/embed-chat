# ADR-0007: GraphRAG on Neo4j replaces 2-step vector RAG

## Status
Accepted (supersedes ADR-0002 for the RAG Knowledge Base storage)

## Context
기존 RAG는 2-step(쿼리 임베딩 → pgvector L2 최근접 청크 → LLM 생성)이었다. 이 방식은 (가) 엔티티/관계 기반 질의("이 제품의 사양은?"에서 본문에 제품명이 없을 때)와 (나) 멀티홉/글로벌·요약형 질의("매뉴얼들이 공통 권장하는 설정은?")를 제대로 답하지 못한다. 단순 벡터 최근접은 관계를 타거나 전체를 요약하지 못하기 때문이다.

ADR-0002는 운영 단순성을 위해 pgvector를 선택했으나, 위 질의 유형을 풀려면 그래프 구조가 필요하다.

## Decision
RAG Knowledge Base를 **Microsoft GraphRAG식 지식그래프**로 전환하고 **Neo4j**(Community 에디션)에 저장한다.

- **인제스션(자동 추출)**: 문서 텍스트 추출(PDF/OCR 단계는 유지) → LLM이 Entity/관계를 자동 추출(스키마 강제 없음, 선택적 entity-type 힌트) → Neo4j 그래프에 기여. 각 노드/관계는 출처 Document와 `tenant_id`를 보유.
- **멀티테넌시**: 단일 Neo4j 그래프 + 모든 노드/관계에 `tenant_id` 속성, 모든 접근을 tenant_id 주입 헬퍼로 강제(Enterprise 멀티 DB 미사용 — 라이선스/운영 비용 회피).
- **임베딩 통합**: 텍스트 조각(Text Unit)·엔티티 임베딩을 Neo4j 네이티브 벡터 인덱스에 저장(bge-m3 그대로 재사용). RAG 용도의 pgvector는 은퇴.
- **검색(LangGraph)**: chat 그래프의 단일 `retrieve_node`를 `route_search → (local_search | global_search) → call_llm`로 교체. 라우팅은 기존 구조화 출력(`complete_structured`)에 `search_scope` 필드를 끼워 저렴하게 분류. Local Search=엔티티 이웃, Global Search=Community 요약 map-reduce.
- **추출 모델**: 플랫폼 레벨 전용 추출 모델(Tenant chat `model_id`와 분리), 반드시 `apps/agent/llm` 경계 경유(테스트에서 결정적 Fake 교체 가능).

## Considered Options
- pgvector 유지 + 검색 개선(하이브리드/리랭킹): (가)/(나)의 관계·글로벌 질의를 구조적으로 풀지 못해 기각.
- Neo4j 벡터 + 경량 엔티티 그래프(커뮤니티 없음): (가)는 되나 (나) 글로벌 요약 불가로 기각.
- Tenant당 별도 Neo4j DB(Enterprise): 격리는 강하나 라이선스·운영 비용 과다로 기각(규제 요건 없음).

## Consequences
- 별도 인프라(Neo4j 컨테이너)가 도커 스택(dev/prod/test)에 추가된다 — ADR-0002가 피하려던 "단일 PostgreSQL"에서 후퇴. 운영 복잡도↑를 GraphRAG 질의 품질과 맞바꾼다.
- 인제스션이 LLM 추출로 무거워진다(고비용·비동기). 비용은 전용 추출 모델 선택으로 통제.
- `tenant_id` 속성 필터를 빠뜨리면 테넌트 누수 위험 → 단일 진입 헬퍼로 강제해야 한다.
- 옛 Document Label의 "청크 임베딩 prefix + 재임베딩" 메커니즘은 Entity 추출로 대체된다(제품명이 Entity로 잡힘). Label은 문서 식별명·대표 Entity로 남는다.
- pgvector 확장은 남을 수 있으나 RAG에는 더 이상 쓰이지 않는다.
