# ADR-0024: chat=taskiq(async) / 배치=Celery(prefork) 공존

## Status
Accepted

## Context
ADR-0022로 chat을 async 워커로 옮긴다. Celery는 async def task를 task마다 이벤트루프로 감싸 진짜 asyncio
동시성(단일 루프 수백 task)을 깔끔히 못 낸다. 한편 인제스션·OCR·커뮤니티는 CPU 바운드(파싱·벡터 연산)라
prefork 격리가 적합하다 — 이걸 async로 옮기면 run_in_executor 의존만 늘 뿐 이득이 없다.

## Decision
**chat은 taskiq(asyncio-native task queue), 배치는 Celery(prefork)로 공존한다.** broker는 redis 공유.
taskiq가 graceful/warm shutdown·max-async-tasks(백프레셔)·task timeout·재시도를 기본 제공해 web-내 async
task의 graceful 난점을 피한다. 세션 직렬화만 앱이 async redis SETNX 락으로 처리(Celery 시절에도 앱 몫).

## Considered Options
- **web 내 async task(create_task)**: 기각. graceful shutdown(in-flight 보존)을 직접 구현해야 — taskiq가 공짜로 줌.
- **arq**: 검토. 더 오래됐지만 인터페이스가 빈약. "Celery 같은 broker·미들웨어·라우팅"엔 taskiq가 우월.
- **Celery로 chat async**: 기각. async task 동시성이 미성숙(task당 루프).
- **taskiq 단일 통일(배치도)**: 기각. CPU 배치를 async로 옮기면 run_in_executor만 늘고 prefork 격리를 잃음.

## Consequences
- 워커 종류 2종(Celery·taskiq) 공존 — 운영 표면이 늘지만 각자 최적 모델.
- **성숙도 리스크**: taskiq는 Celery만큼 전장 검증되진 않았다(신생). chat만 taskiq라 폭발 반경은 chat에 국한.
- chat dispatch를 어댑터 한 곳에 두어 추후 전송/큐 구현 교체가 국소적이다.
