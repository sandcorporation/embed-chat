# ADR-0023: Django ORM은 async 메서드여도 스레드풀 위임 — 그 한계를 수용

## Status
Accepted

## Context
ADR-0022로 전면 async로 가지만, Django ORM의 async 메서드(aget/asave/afilter/acreate)는 await 가능할 뿐
내부적으로 sync_to_async로 **스레드풀에 위임**한다 — Django는 아직 네이티브 async DB 드라이버를 안 쓴다
(5.x까지). 즉 "async ORM"은 이벤트루프를 막지 않을 뿐 진짜 async I/O가 아니다.

## Decision
**ORM은 async 메서드(스레드풀 위임)로 쓰고, 진짜 async는 LLM·redis·SSE·체크포인트에서만 얻는다.**
스레드풀 크기가 DB 동시성의 새 한계임을 인지하고 전용 executor + thread_sensitive=False로 튜닝한다.
체크포인트는 LangGraph AsyncPostgresSaver(자체 async psycopg3)로 진짜 async를 쓴다.

## Considered Options
- **asyncpg raw로 전체 DB를 진짜 async**: 기각(지금은). Django 모델·ORM을 포기해야 해 비현실적.
- **ORM을 sync_to_async로 명시 래핑**: 동일(async 메서드가 이미 그것). 가독성만 나쁨.
- **chat hot path만 asyncpg raw**: 보류(Out of Scope). 스레드풀이 실측 병목일 때만.

## Consequences
- chat의 무거운 I/O(LLM)는 진짜 async라 동시성 이득 대부분을 얻는다. DB는 짧은 쿼리라 스레드풀로 충분.
- "왜 async인데 ORM이 스레드냐"는 혼란을 이 ADR이 차단한다.
- 동시 수백 chat이 동시에 DB를 치면 스레드풀이 병목 가능 → executor 크기를 부하에 맞춰 조정.
