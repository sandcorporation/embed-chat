# ADR-0002: pgvector over dedicated vector DB

## Status
Superseded by ADR-0007 (RAG Knowledge Base가 Neo4j 기반 GraphRAG로 전환됨). 아래 내용은 전환 이전 상태의 기록이다.

## Context
Tenant별 RAG Knowledge Base를 위해 문서를 벡터로 인덱싱·검색해야 한다. 전용 벡터 DB(Qdrant, Weaviate 등) 또는 PostgreSQL 확장(pgvector) 중 선택해야 한다.

## Decision
pgvector를 사용한다. 별도 인프라 없이 기존 PostgreSQL에 확장만 추가한다.

## Consequences
- Tenant 수십 개, 문서 수만 건 규모에서는 pgvector 성능으로 충분하다.
- 인프라를 PostgreSQL 단일 인스턴스로 유지하여 운영 복잡도를 낮춘다.
- 향후 대용량 검색 병목이 발생하면 Qdrant 등으로 마이그레이션을 검토한다.
