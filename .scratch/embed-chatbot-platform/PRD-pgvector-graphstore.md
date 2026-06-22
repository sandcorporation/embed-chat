# PRD — GraphStore를 Neo4j에서 Postgres+pgvector로 이전

Status: ready-for-agent

## Problem Statement

prod(Oracle Ampere A1, 4코어/24GB, CPU 전용)에 backend·frontend·**Postgres**·Redis가 이미 떠 있는데,
여기에 **Neo4j(JVM)**까지 올리기엔 박스가 너무 북적인다. Neo4j는 고정 힙(우리가 4G로 묶은 그놈)을
잡는 가장 무거운 입주자다. 게다가 향후 Postgres를 **OCI Database with PostgreSQL(관리형)**로 옮길
계획이라, 그래프/벡터 저장이 Postgres로 통합돼 있으면 이전이 단순해진다.

다행히 그래프 사용은 얕다 — 1-hop 이웃 + RELATED/SAME_AS 엣지 + 벡터검색 + 어휘 CONTAINS뿐이고,
엔티티 해소(SAME_AS)는 이미 Python(임베딩 유사도 + union-find)이며 그래프 알고리즘(GDS/APOC)
의존이 0이다(Community/Global Search는 ADR-0016에서 제거). 모든 그래프 접근은 단일 deep module
`GraphStore`를 지난다.

## Solution

`GraphStore`의 **내부 구현만** Neo4j → Postgres+pgvector로 교체한다. 공개 인터페이스(메서드 시그니처)는
그대로라 호출부(graph_ingester·agent nodes·rag api·reembed·community_builder)는 무변경이다. Neo4j
컨테이너·JVM이 박스에서 사라지고, 그래프/벡터는 이미 떠 있는 Postgres(pgvector)에 흡수된다.

벡터는 **차원별 테이블 + 테넌트 스코프 HNSW**로 둔다. 운영(실서비스) 규모를 위해 인덱스를 쓰되,
JVM 고정 힙이 아니라 pgvector(OS page cache 탄력적)라 박스 메모리는 순감한다. 향후 OCI 관리형
이전을 위해 버전-특화 기능(halfvec·iterative scan)에 정합성을 의존하지 않게 설계한다.

## User Stories

1. As a 운영자, I want Neo4j 컨테이너를 prod에서 제거, so that 4코어/24GB A1 박스의 메모리·CPU 경합이 준다.
2. As a 운영자, I want 그래프/벡터가 기존 Postgres에 통합되기, so that 관리할 데이터 스토어가 하나 줄어든다.
3. As a 운영자, I want 향후 OCI Database with PostgreSQL로 무리 없이 이전, so that 관리형으로 옮길 때 그래프/벡터가 같이 따라간다(Postgres→Postgres).
4. As a 테넌트, I want 문서 인제스션이 그대로 동작(Entity/관계 추출 → 저장), so that 마이그레이션이 기능을 깨지 않는다.
5. As a 방문자, I want 챗 응답의 GraphRAG 근거(Local Search)가 동일 품질로 동작, so that 답변 품질이 유지된다.
6. As a 테넌트, I want per-Tenant 임베딩 차원(예: 768·1024·1536)이 그대로 지원되기, so that 내 임베딩 모델을 계속 쓸 수 있다(ADR-0012).
7. As a 테넌트, I want 테넌트 간 벡터가 섞여 검색되지 않기, so that 다른 테넌트의 근거가 절대 노출되지 않는다(격리).
8. As a 테넌트, I want 원문 폴백(TextUnit 벡터검색)이 동일하게 동작, so that 그래프에 없는 스펙·수치도 답할 수 있다(ADR-0010 보강).
9. As a 테넌트, I want 엔티티 해소(SAME_AS) 재구축이 동일 결과를 내기, so that 표기변이가 하나의 Entity로 묶인다.
10. As a 테넌트, I want 동음이의 Mention이 분리 유지, so that 맥락이 다른 같은 표기가 섞이지 않는다.
11. As a 테넌트, I want Knowledge Graph 인스펙터(검색·이웃·청크 보기)가 동일하게 동작, so that 어드민에서 그래프를 계속 확인한다.
12. As a 테넌트, I want 문서 삭제/레이블 변경이 그래프에 동일 반영, so that 그래프가 문서 상태와 일치한다.
13. As a 테넌트, I want 임베딩 Provider 변경 시 재임베딩 재구축이 동작, so that 벡터 공간 변경이 무중단 swap된다(issue 95).
14. As a 개발자, I want 기존 GraphStore 행동 테스트가 새 구현에서 그대로 통과, so that 마이그레이션이 회귀 없음을 증명한다.
15. As a 개발자, I want 테스트가 실 Postgres+pgvector로 검증, so that 결정적 인프라를 실제 객체로 쓴다(CLAUDE.md).
16. As a 운영자, I want 기존 테넌트 그래프 데이터가 임베딩 재계산 없이 이전, so that 마이그레이션 비용(LLM·임베딩 호출)이 0이고 데이터가 충실하다.
17. As a 운영자, I want 이전 전 OCI의 pgvector 버전·PG 메이저 버전을 확인하는 선행 점검, so that halfvec 채택·덤프 전략을 사실로 정한다.
18. As a 운영자, I want Neo4j 관련 설정·compose 서비스가 깨끗이 제거, so that 운영 표면이 줄고 혼선이 없다.

## Implementation Decisions

- **GraphStore deep module 내부 재구현(인터페이스 불변)**: 현 공개 메서드(`ensure_vector_index`·`upsert_text_unit`·`vector_search`·`upsert_mention`·`upsert_mention_relation`·`upsert_mention_same_as`·`query_mention_*`·`search_entities`·`neighbors`·`delete_document`·`reseed_document_label`·`set/get_freshness`·재임베딩용 메서드 등)를 Postgres+pgvector로 백킹. 호출부 무변경.
- **데이터 접근**: Django DB 연결(psycopg)로 **raw SQL**. GraphStore가 그래프 접근 경계라 Django ORM 모델 그래프에 그래프 테이블을 끌어들이지 않는다(현 Cypher 경계와 동일 철학). 모든 쿼리는 생성자 `tenant_id`를 강제 주입(테넌트 누수 구조적 차단 — 현 동작 보존).
- **벡터 모델 (C: 차원별 테이블 + 테넌트 스코프 HNSW)**:
  - TextUnit·Mention은 **임베딩 차원별 테이블**(예: `kg_text_unit_d{dim}`, `kg_mention_d{dim}`)에 `tenant_id` 컬럼 + `embedding vector(dim)` + content/metadata. 테넌트의 `embed_dim`으로 테이블을 라우팅(현 per-Tenant 인덱스 이름의 자연 치환).
  - 각 차원 테이블에 **HNSW 인덱스** + `tenant_id` B-tree. 검색은 `WHERE tenant_id=$t ORDER BY embedding <=> $q LIMIT k`로 **테넌트 스코프**. self-hosted pgvector 0.8.2의 **iterative scan**으로 필터 recall을 보장.
  - 비-벡터(차원 무관): RELATED 엣지·SAME_AS 엣지·GraphMeta는 **정적 공유 테이블**(`tenant_id` 인덱스). 엣지는 `mention_id` 문자열 참조라 차원 비의존.
  - 1-hop `neighbors`/관계 나열 = 엣지 테이블 self-join + 테넌트 dim-테이블의 Mention 조인. 가변길이 경로 없음.
- **DDL 생성**: `CREATE EXTENSION IF NOT EXISTS vector` + 정적 공유 테이블(엣지·메타)은 **Django 마이그레이션(RunSQL)**으로. 차원별 텍스트유닛/멘션 테이블·HNSW는 **런타임 `CREATE … IF NOT EXISTS`**(첫 인제스션 시, 현 `ensure_vector_index` 동적 패턴 그대로).
- **OCI 관리형 이식 가드(버전 무관 설계)**:
  - `halfvec`(인덱스 메모리 ~50%↓, pgvector 0.7+)와 `iterative scan`(0.8+)은 **선택적 최적화**로 — 미지원 버전이면 full `vector` HNSW + `ef_search` 상향으로 폴백.
  - 더 강한 격리/recall이 필요하면 차원 테이블을 `tenant_id` 파티셔닝(파티션별 HNSW)으로 승격하는 길을 GraphStore 내부에 열어둠(인터페이스 불변, 점진적).
  - **선행 점검(코드 외, 운영)**: OCI 콘솔에서 ① pgvector `extversion`, ② PG 메이저 버전(현 self-hosted=pg16 vs OCI=14/15 가능) 확정. 이전은 Postgres→Postgres `pg_dump/restore` + extension·인덱스 재생성.
- **엔티티 해소 불변**: `community_builder.rebuild_communities`와 `entity_resolver.resolve_equivalences`(Python union-find)는 그대로. GraphStore의 `mention_embeddings`/`upsert_mention_same_as`만 새 백엔드를 탄다.
- **데이터 이전(임베딩 보존)**: 일회성 management command가 테넌트별로 Neo4j에서 노드·엣지·**임베딩**을 읽어 새 pg 스토어에 기록(재임베딩 0). 재인제스션은 폴백(원문 바이트가 MEDIA에 있음).
- **컷오버(빅뱅)**: GraphStore 구현 교체는 deep module이라 코드 레벨에서 원자적(듀얼라이트 불필요). 데이터 이전을 배포 전/시점에 1회 수행. 그래프 **쓰기**는 인제스션·재구축 같은 비동기 배치라 사용자 요청 경로가 아니므로, 롤링 배포 중 짧은 인제스션 동결로 신·구 발산을 피한다(읽기=챗 경로는 pg로 바로 전환).
- **Neo4j 제거**: `NEO4J_URI/USER/PASSWORD` 설정 제거, 모든 compose(base·dev·test·prod)에서 neo4j·neo4j-test 서비스와 `depends_on` 제거, `neo4j` 파이썬 드라이버 의존 제거.

## Testing Decisions

- 좋은 테스트는 **외부 행동**만 검증한다(저장 엔진 세부 아님) — 그래서 기존 GraphStore 행동 테스트가 **새 구현에서도 그대로 통과**하는 것이 마이그레이션의 1차 회귀 증거다.
- **실 Postgres+pgvector로 검증**: 결정적 인프라는 실제 객체(CLAUDE.md). 테스트 DB는 **이미 `pgvector/pgvector:pg16`**라 변경 불필요. neo4j-test 서비스만 제거.
- **재사용(prior art)**: `test_graph_store.py`·`test_graph_search.py`·`test_entity_mention.py`·`test_entity_semantic_search.py`·`test_graph_delete.py`·`test_local_source_fallback.py`·`test_rag.py`(OCR/인제스션). 이들이 검색·이웃·dedup·삭제·원문폴백을 인터페이스로 검증하므로 엔진 교체에 둔감해야 한다(둔감하지 않으면 그 테스트가 구현 결합—수정 대상).
- **신규 테스트(새 행동)**: ① per-Tenant 차원 라우팅(서로 다른 dim 테넌트가 각자 테이블에서 검색되고 섞이지 않음), ② 테넌트 격리(한 테넌트 검색이 다른 테넌트 벡터를 절대 반환 안 함), ③ 동적 DDL 멱등성(첫 인제스션이 테이블·인덱스를 IF NOT EXISTS로 생성).
- **데이터 이전 command**: import 측을 합성 입력(노드·엣지·임베딩)으로 검증(왕복은 Neo4j 의존이라 별도/수동).

## Out of Scope

- OCI Database with PostgreSQL로의 실제 이전 실행(이 PRD는 self-hosted pg 흡수까지 — 이전은 그 위에서 `pg_dump/restore`).
- 그래프 알고리즘(커뮤니티 탐지·PageRank 등) 재도입 — ADR-0016에서 제거됨, 복원 안 함.
- 차원 테이블의 `tenant_id` 파티셔닝(설계 훅만 열어두고, 실제 채택은 초대형 테넌트/구버전 pgvector 만났을 때 후속).
- `halfvec` 전면 채택(선행 점검 후 옵션).
- GraphStore 공개 인터페이스 변경.

## Further Notes

- pgvector는 OCI Database with PostgreSQL에서 지원 확인됨(2024-11 Extension Manager로 활성화). 정확한 버전·PG 메이저 버전은 문서 미공개라 콘솔 확인 필요 — 그래서 본 설계는 버전-특화 기능에 의존하지 않게 잡았다.
- 박스 메모리: Neo4j JVM(고정 힙 1.5G + page cache 1G + overhead)을 들어내고 pgvector(탄력적)로 가면 순감. halfvec 적용 시 인덱스 메모리 추가 절감.
- 관련 ADR: 0007(GraphRAG/Neo4j 채택 — 저장 엔진만 교체, 그래프 모델 보존), 0010(Entity Mention·resolution), 0012(per-Tenant 차원), 0016(Global/Community 제거). 본 전환은 새 ADR 후보(저장 엔진 결정 + OCI 이식 가드).
