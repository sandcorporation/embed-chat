# PRD — 전면 async 개편 (uvicorn ASGI + taskiq chat 워커)

Status: ready-for-agent

## Problem Statement

chat 1턴은 거의 전부 I/O(LLM 스트리밍·pgvector·임베딩 API·체크포인트)인데, 현재 실행 모델은 둘 다
동시성이 낮다. 예전엔 chat을 gunicorn **gevent** web 워커의 greenlet으로 돌렸으나, gevent가
monkey-patch 못 하는 블로킹(psycopg C 확장·임베딩 연산)에서 hub가 멈춰 같은 워커의 **모든 SSE
스트림을 얼리는** 병이 있었다(블로킹-허브 병). 그래서 chat을 Celery **prefork** worker-chat으로
분리했는데, prefork는 **프로세스당 1 task**라 동시성이 `concurrency`(=4)로 캡되고 프로세스 메모리가
비효율적이다 — I/O 바운드 작업인데 동시 처리량이 낮다.

## Solution

런타임을 **전면 async**로 개편한다. web을 **uvicorn(ASGI)** 로, chat을 **taskiq async 워커**로 옮겨,
단일 이벤트루프가 LLM을 `await`하는 동안 yield하며 **동시 수백 chat**을 같은 메모리로 처리한다.
async-native(httpx async·redis async·`AsyncPostgresSaver`)라 gevent의 블로킹-허브 병은 *원천적으로*
사라지고, prefork의 자원·동시성 한계도 없앤다. graceful shutdown·백프레셔·timeout 같은 안전장치는
taskiq가 기본 제공한다. CPU 바운드 배치(인제스션·OCR·커뮤니티)는 prefork가 적합하므로 **Celery를
유지**하고 taskiq와 공존시킨다(broker는 redis 공유).

## User Stories

1. 방문자로서, 동시 접속이 많아도 내 chat 응답이 지연 없이 스트리밍되기를 바란다, 그래야 챗봇이 붐벼도 쓸 만하다.
2. 방문자로서, 다른 방문자의 무거운 질의가 진행 중이어도 내 SSE 스트림이 안 얼기를 바란다(async non-blocking).
3. 플랫폼 운영자로서, 단일 A1 박스에서 더 많은 동시 chat을 같은 메모리로 처리하기를 바란다, 그래야 자원이 효율적이다.
4. 플랫폼 운영자로서, 배포(SIGTERM) 시 진행 중 chat이 즉사하지 않고 graceful하게 끝나기를 바란다(taskiq warm shutdown).
5. 플랫폼 운영자로서, chat 동시 처리량을 워커 설정·replica로 조절하기를 바란다(taskiq `max-async-tasks`).
6. 플랫폼 운영자로서, chat이 무한정 매달리지 않고 상한 시간 후 정리되기를 바란다(taskiq timeout).
7. 방문자로서, 같은 세션에 연속으로 메시지를 보내도 응답·히스토리가 뒤섞이지 않기를 바란다(세션 락).
8. 방문자로서, chat이 실패하면 조용한 무응답 대신 오류 안내를 받아 재전송하기를 바란다(at-most-once).
9. 개발자로서, chat 실행이 호출 위치와 무관한 순수 async 함수이기를 바란다, 그래야 taskiq든 인라인이든 같은 코드를 쓴다.
10. 개발자로서, 토큰 전달이 포트 뒤에 있어 전송 구현(redis pub/sub)을 갈아끼울 수 있기를 바란다.
11. 개발자로서, 인제스션·OCR 같은 CPU 배치는 prefork(Celery)에서 격리되어 돌기를 바란다, 그래야 이벤트루프를 안 막는다.
12. 개발자로서, 테스트가 추가 인프라 없이 인라인(taskiq `InMemoryBroker`)으로 결정적으로 돌기를 바란다.
13. HITL(`is_hitl=True`) 세션의 방문자로서, 내 메시지가 에이전트를 깨우지 않고 상담원에게 곧장 전달되는 기존 동작이 유지되기를 바란다.
14. 운영자로서, 전환 배포가 무중단(docker rollout)으로 이뤄지기를 바란다, 그래야 전면 개편에도 다운타임이 없다.
15. 개발자로서, LLM 경계가 async(`acomplete`/`astream`)로 통일되어 호출부가 일관되기를 바란다.
16. 개발자로서, LangGraph 체크포인트가 async(`AsyncPostgresSaver`)로 동작해 이벤트루프를 막지 않기를 바란다.
17. 개발자로서, Django ORM 호출이 `await` 가능(`aget`/`asave`)하되 그 실행이 스레드풀임을 명확히 알고 executor를 튜닝하기를 바란다.
18. 방문자로서, 첫 토큰까지의 지연이 enqueue 홉으로 체감 악화되지 않기를 바란다(LLM 대비 무시 수준).
19. 운영자로서, taskiq 도입의 성숙도 리스크가 문서화되어 추적되기를 바란다.

## Implementation Decisions

- **web = uvicorn ASGI.** gunicorn gevent 폐기. Django ASGI 애플리케이션 + async ninja view. SSE는
  ASGI async generator로 스트리밍(현재 gevent + redis 구독을 async redis 구독으로).
- **chat = taskiq async 워커.** Celery worker-chat 폐기. `chat_task.kiq(session_id, message)`로 enqueue,
  taskiq async 워커가 단일 이벤트루프에서 `astream` 실행. 토큰은 **redis pub/sub**로 web SSE에 중계
  (전송은 포트 뒤에 둬 추후 교체 가능). broker = redis.
- **배치 = Celery prefork 유지(공존).** 인제스션·OCR·커뮤니티·webhook은 Celery 그대로(CPU 바운드).
  relay·bridge(consume_events)도 그대로. broker는 redis 공유. 워커 종류 2종(Celery, taskiq) 공존.
- **LLM 경계 async.** `llm.py`를 `acomplete`/`astream`(+ async 콜백)으로. 비결정 외부 경계라 테스트는
  fake async LLM으로 교체.
- **체크포인트 = AsyncPostgresSaver.** LangGraph가 제공하는 async 체크포인터(자체 async psycopg3 커넥션).
- **ORM = async 메서드(스레드풀 위임).** `aget`/`asave`/`afilter`는 `await` 가능하나 Django는 아직
  네이티브 async DB가 아니라 `sync_to_async`로 스레드풀에 위임한다 — 이벤트루프는 안 막지만 진짜 async
  I/O가 아니다. 따라서 **스레드풀 크기가 새 DB 동시성 한계**이며, 전용 executor + `thread_sensitive=False`로
  튜닝한다. 진짜 async I/O 이득은 LLM·redis·SSE·체크포인트에서 나온다. (※ ADR 기록 대상.)
- **안전장치 = taskiq 기본 + 세션 락.** graceful/warm shutdown·`max-async-tasks`(백프레셔)·task timeout은
  taskiq가 제공. **세션 직렬화**만 앱이 async redis `SETNX chat:lock:{session_id}`(TTL=하드 timeout)로
  처리(Celery 시절에도 앱 몫이었음). 락 실패 시 재-enqueue.
- **at-most-once.** 스트리밍은 비멱등이라 자동 재시도 없음(taskiq 재시도 미들웨어 끔). 예외 시 `publish_error`로
  사용자에게 알리고 재전송 유도.
- **이음새(전환 보험).** ① `run_chat_agent_async`를 호출 위치와 무관한 **순수 async deep module**로,
  ② chat dispatch를 어댑터 한 곳으로, ③ 토큰 전달을 포트로 — 덕분에 인라인/taskiq/전송 구현 교체가 국소적.
- **전략 = big bang, 단계 커밋.** 별도 worktree 브랜치에서 단계별로(각 단계 테스트 그린 유지) 작업하고
  마지막에 한 번 머지. 중간 prod 배포는 없음.
- **ADR 3건 발행:** (a) 전면 async 채택(I/O 바운드 근거·gevent 병 해소), (b) Django ORM 스레드풀 위임
  현실, (c) chat=taskiq / 배치=Celery 공존 + taskiq 성숙도 리스크.

### 모듈 스케치 (deep modules — 작은 인터페이스, 격리 테스트 가능)

- **`run_chat_agent_async(session_id, message)`** — chat 1턴 전체(LangGraph `astream`)를 감싼 순수 async
  함수. 호출 위치(인라인/taskiq) 무관. 기존 `run_chat_agent`의 async 대응.
- **토큰 포트** — `publish_token(session_id, token)` / `subscribe(session_id)`. redis pub/sub 구현.
  SSE 핸들러는 이 포트로만 구독.
- **세션 락(async)** — `acquire(session_id) -> bool` / `release(session_id)`를 async redis SETNX+TTL 위에.
  외부 I/O가 redis 하나라 결정적 단위 테스트 가능.
- **chat dispatch** — `dispatch_chat(session_id, message)` 어댑터. 내부에서 `chat_task.kiq(...)`. 호출부
  (뷰)는 이 함수만 안다.
- **LLM 경계(async)** — `acomplete`/`astream`. provider 해석은 기존 그대로, 호출만 async.

## Testing Decisions

좋은 테스트는 외부 행위만 검증한다(구현 세부 아님). CLAUDE.md 원칙: 내부 협력자는 실제 객체, 비결정
외부 경계(LLM)만 fake로 교체, 테스트 독립. async 전환으로 테스트 하네스가 대거 바뀐다.

- **하네스**: `pytest-asyncio`(async 테스트), **async test client**(ASGI), taskiq **`InMemoryBroker`**로
  태스크 인라인 실행(기존 `celery_always_eager` 역할). conftest 픽스처(`celery_always_eager`·sync client·
  `fake_chat_llm`) 대거 async 재작성 — 회귀 위험의 핵심 축.
- **대상 모듈**: `run_chat_agent_async`(메시지 전송→에이전트 깨움→assistant 저장), 세션 락(2회 acquire→
  두 번째 False, release 후 재획득, TTL 만료), SSE 스트리밍(토큰 포트 publish→SSE 수신), dispatch 배선
  (뷰→taskiq→에이전트), 실패 경로(fake LLM 예외→`publish_error`+락 해제).
- **불변 보장**: HITL 분기(`is_hitl` 세션은 에이전트 미기동), 그래프 동작 테스트는 의미 유지(호출만 async).
- prior art: `tests/test_hitl.py`(run_chat_agent 직접 호출 + redis 구독), `tests/conftest.py`의
  `fake_chat_llm`·`redis_subscribe`, PRD-chat-agent-celery의 테스트 구조.

## Out of Scope

- **진짜 async DB(asyncpg raw)** — ORM 스레드풀 위임으로 시작. 스레드풀이 실제 병목으로 측정되면 그때
  chat hot path만 raw async로 내린다.
- **배치(인제스션·OCR)의 async 전환** — Celery prefork 유지(CPU 바운드).
- **taskiq 단일 통일** — Celery와 공존. 인제스션을 taskiq로 옮기지 않는다.
- **메모리 직접 토큰 전달** — redis pub/sub 유지(전환 보험). 측정 후에만 고려.
- **끊긴 chat 자동 재개** — 스트리밍 비멱등성 때문에 추구하지 않음(at-most-once).

## Further Notes

- **무중단 배포 검증 필요**: gevent→uvicorn + Celery worker-chat→taskiq 동시 교체. docker rollout
  (start-first)으로 가능하나 command·compose 서비스 구성 변경이 커서 스모크로 검증한다(HITL).
- **성숙도 리스크**: taskiq는 Celery만큼 전장 검증되진 않았다(arq가 더 오래됨). "Celery 같은 인터페이스
  (broker·미들웨어·라우팅)"가 필요해 taskiq를 택했고, ADR에 리스크를 기록한다.
- 선행 맥락: [PRD-chat-agent-celery.md](./PRD-chat-agent-celery.md)(chat을 prefork로 뺀 원래 결정),
  [PRD-chat-token-streaming.md](./PRD-chat-token-streaming.md).
