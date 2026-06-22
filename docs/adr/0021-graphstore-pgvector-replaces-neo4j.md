# ADR-0021: GraphStore를 Neo4j에서 Postgres+pgvector로 이전

## Status
Accepted

## Context
prod(Oracle Ampere A1, 4코어/24GB, CPU 전용)에 backend·frontend·Postgres·Redis가 이미 떠 있는데,
Neo4j(JVM)까지 올리기엔 박스가 북적인다 — Neo4j는 고정 힙(ADR 직전 4G로 제한)을 잡는 가장 무거운
입주자다. 게다가 Postgres를 향후 OCI Database with PostgreSQL(관리형)로 옮길 계획이라, 그래프/벡터가
Postgres에 통합돼 있으면 이전이 단순해진다.

다행히 그래프 사용이 얕다 — 1-hop 이웃 + RELATED/SAME_AS 엣지 + 벡터검색 + 어휘 검색뿐이고, 엔티티
해소(SAME_AS)는 이미 Python(임베딩 유사도 + union-find)이며 그래프 알고리즘(GDS/APOC) 의존이 0이다
(Community/Global Search는 ADR-0016에서 제거). 모든 그래프 접근은 단일 deep module GraphStore를 지난다.

## Decision
**GraphStore의 내부 구현만 Neo4j → Postgres+pgvector로 교체한다(공개 인터페이스 불변). 벡터는
메타데이터(차원 무관)와 임베딩(차원별 vec 테이블)을 분리해 둔다.**

- **메타/임베딩 분리**: content·name 등 메타데이터는 정적 공유 테이블(`kg_text_unit`·`kg_mention`)에,
  임베딩은 차원별 `kg_*_vec_d{dim}`(HNSW)에 둔다. 임베딩 차원이 바뀌어도(reembed) 메타데이터는 보존되고
  임베딩만 새 차원으로 재기록된다. vec 테이블은 임베딩 길이로 라우팅하고, 테넌트의 현 차원은 데이터에
  기록한다(`kg_graph_meta.embed_dim` — config가 아니라 데이터가 진실, Neo4j의 명시 차원 동작과 동일).
- **테넌트 스코프 검색**: `WHERE tenant_id=$t ORDER BY embedding <=> $q` + HNSW + pgvector 0.8 iterative
  scan. 모든 쿼리에 tenant_id를 강제 주입(현 격리 보존).
- **OCI 관리형 이식 가드**: `halfvec`(0.7+)·`iterative scan`(0.8+)에 정합성을 의존하지 않게 설계 —
  미지원 버전이면 full `vector` HNSW + `tenant_id` 파티셔닝(파티션별 HNSW)으로 폴백(GraphStore 내부에
  훅만 열어둠, 인터페이스 불변). 이전 전 OCI 콘솔에서 pgvector `extversion`·PG 메이저 버전 확인 필수.
- **빅뱅 전환(단일 구현)**: 개발 중엔 `GRAPH_BACKEND` 플래그로 게이팅하며 전 메서드를 pg에서 검증한 뒤,
  prod 미배포라 이전할 데이터가 없으므로 Neo4j 백엔드·플래그를 통째로 제거했다. GraphStore는 pg 단일
  구현이며 신규 배포는 처음부터 pg로 인제스션한다(데이터 이전 단계 불필요).

## Considered Options
- **Oracle Autonomous DB(네이티브 VECTOR + SQL/PGQ)**: 기각. 저장을 박스 밖 관리형으로 빼는 이점은 있으나,
  쿼리마다 네트워크 왕복 + wallet/드라이버 + 무거운 Oracle 테스트 컨테이너. "Postgres를 관리형으로" 계획엔
  pgvector가 이식성(어떤 Postgres로도 lift-and-shift)에서 우월.
- **per-Tenant 테이블 + HNSW**: 기각. 테넌트 데이터 크기는 확장되나 테넌트 **수**가 늘면 테이블 2×N개로
  카탈로그 bloat. 차원별 공유 테이블 + 테넌트 필터가 테이블 수를 차원 종류로 고정.
- **Exact KNN(인덱스 없음)**: 기각(실서비스). 인덱스 메모리는 0이나 테넌트당 수만+ 벡터에서 O(n)으로 무너짐.
- **결합 테이블(content+embedding 한 테이블)**: 기각. 차원 변경 시 데이터가 옛 차원 테이블에 갇힘 →
  메타/임베딩 분리로 해결.

## Consequences
- prod에서 Neo4j(JVM) 컨테이너가 사라진다(메모리·CPU 경합 순감). 그래프/벡터는 이미 떠 있는 Postgres에 흡수.
- 기존 GraphStore 행동 테스트가 pg 백엔드에서 그대로 통과(355 passed) — 충실한 drop-in 검증.
- 테스트는 실 Postgres+pgvector(db-test=`pgvector/pg16`)로, neo4j-test 제거. 테스트 인프라 가벼워짐.
- **Neo4j 완전 제거**: prod가 아직 배포된 적 없어 이전할 그래프 데이터가 없으므로, `neo4j` 파이썬 드라이버·
  `_Neo4jGraphStore`·데이터 이전 명령(`migrate_graph_to_pg`)·`GRAPH_BACKEND` 플래그·`NEO4J_*` 설정을 모두
  삭제했다. GraphStore는 단일 pg 구현이다(백엔드 선택 분기 없음). 신규 배포는 처음부터 pg로 인제스션한다.
