# ADR-0022: 전면 async 개편 (uvicorn ASGI + taskiq chat 워커)

## Status
Accepted

## Context
chat 1턴은 거의 전부 I/O(LLM 스트리밍·pgvector·임베딩 API·체크포인트)다. 예전엔 chat을 gunicorn
gevent web 워커의 greenlet으로 돌렸으나, gevent가 monkey-patch 못 하는 블로킹(psycopg C 확장·임베딩)에서
hub가 멈춰 같은 워커의 모든 SSE를 얼리는 "블로킹-허브 병"이 있었다(PRD-chat-agent-celery). 그래서 chat을
Celery prefork worker-chat으로 분리했는데, prefork는 프로세스당 1 task라 동시성이 concurrency(=4)로 캡되고
프로세스 메모리가 비효율적이다 — I/O 바운드인데 동시 처리량이 낮다.

## Decision
**런타임을 전면 async로 개편한다. web=uvicorn(ASGI), chat=taskiq async 워커.** async-native
(httpx async·redis async·AsyncPostgresSaver)라 블로킹-허브 병이 원천 소멸하고, 단일 이벤트루프가 LLM을
await하는 동안 yield하며 동시 수백 chat을 같은 메모리로 처리한다. gunicorn gevent·Celery worker-chat 폐기.

## Considered Options
- **gevent 유지**: 기각. 블로킹-허브 병이 본질(psycopg C·임베딩은 monkey-patch 불가).
- **prefork worker-chat 스케일(concurrency/replica↑)**: 기각(주 해법으로는). 프로세스당 1 task라
  I/O 바운드 작업에 메모리가 비효율 — async가 같은 자원으로 10×+ 동시성.
- **그대로 두기**: 기각. concurrency=4가 동시 처리량 상한.

## Consequences
- 단일 박스 동시 chat 처리량이 크게 오른다(I/O 대기 중 yield). 병목은 LLM rate limit·비용·state 메모리로 이동.
- **스택 전염**: LLM 경계(acomplete/astream)·SSE(async generator)·체크포인트(AsyncPostgresSaver)·테스트
  하네스가 전부 async로. 회귀 위험이 크므로 big bang(브랜치)으로 단계 빌드 후 머지.
- Celery가 공짜로 주던 안전장치(graceful·백프레셔·timeout)는 taskiq로 대체(ADR-0024).
- ORM은 진짜 async가 아니다(ADR-0023).
