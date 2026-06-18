Status: ready-for-agent

# PRD: Chat 에이전트 실행을 gevent 스레드 → Celery 태스크로 이관

## Problem Statement

방문자가 메시지를 보내면 `POST /chat/message`가 그 자리에서 `threading.Thread`로 `run_chat_agent`를 띄운다. 그런데 web 서버는 `gunicorn --worker-class=gevent`로 동작하므로 gevent가 stdlib을 monkey-patch한다 — 즉 이 "스레드"는 OS 스레드가 아니라 **SSE를 서빙하는 바로 그 워커 프로세스의 greenlet**이다.

에이전트 greenlet이 monkey-patch되지 않은 **블로킹 호출**(psycopg 체크포인터, Neo4j bolt 드라이버, 임베딩 연산)을 하는 순간 gevent hub 전체가 멈춘다. 그러면 그 워커가 처리하던 **다른 방문자의 SSE 스트림과 keepalive까지 전부 정지**한다. 한 명의 무거운 질의가 같은 워커에 동거한 모든 세션을 얼리는 구조다.

추가로 daemon greenlet 모델은: 배포(SIGTERM) 시 실행 중인 에이전트가 즉사해 응답이 유실되고, 동시성 상한이 없어(무한 greenlet) 백프레셔가 없으며, 운영 관측·수명주기 제어가 없다.

## Solution

에이전트 실행을 이미 운영 중인 Celery로 이관한다. 토큰 전달은 이미 Redis pub/sub로 디커플링되어 있으므로(`apps/chat/sse.py`), Celery 워커가 스레드와 **동일하게** `publish_token`하면 브라우저 SSE 경로는 그대로 동작한다.

이관이 사는 것은 명확히 셋이다: ① **프로세스 격리** — 블로킹 호출이 별도 prefork 풀에 갇혀 web 워커의 hub를 더 이상 얼리지 않는다, ② **바운드된 동시성/백프레셔** — 무한 greenlet 대신 큐, ③ **graceful shutdown** — Celery는 SIGTERM 시 실행 중 태스크를 끝까지 기다린 뒤 종료(warm shutdown)하므로 배포 안전성이 오른다.

스트리밍은 본질적으로 비멱등(이미 나간 토큰은 회수 불가)이므로, "끊긴 chat 자동 재개"는 **의도적으로 추구하지 않는다**. 실행 모델은 **at-most-once**다.

## User Stories

1. 방문자로서, 다른 방문자의 무거운 질의가 진행 중이어도 내 SSE 스트림이 끊기지 않기를 바란다, 그래야 응답이 매끄럽게 흐른다.
2. 방문자로서, 메시지를 보내면 에이전트가 동작해 답이 스트리밍되기를 바란다, 그래야 챗봇이 쓸모 있다.
3. 방문자로서, 에이전트가 실패하면 조용한 무응답 대신 오류 안내를 받아 재전송할 수 있기를 바란다.
4. 방문자로서, 조급해서 메시지를 빠르게 두 번 보내도 응답·히스토리가 뒤섞이지 않고 순서대로 처리되기를 바란다.
5. 플랫폼 운영자로서, 한 테넌트가 문서 수십 개를 한꺼번에 올려 인제스션이 밀려도 chat 응답이 그 배치에 인질로 잡히지 않기를 바란다.
6. 플랫폼 운영자로서, 배포로 워커를 재시작할 때 진행 중이던 chat이 즉사하지 않고 정상 종료되기를 바란다.
7. 플랫폼 운영자로서, chat 실행이 무한정 매달리지 않고 상한 시간 후 정리되기를 바란다, 그래야 워커 프로세스가 영구 점유되지 않는다.
8. 플랫폼 운영자로서, chat 동시 처리량을 워커 replica 수로 조절할 수 있기를 바란다.
9. 개발자로서, 에이전트 실행 경로가 단일 Celery 태스크 하나로 표현되기를 바란다, 그래야 LangGraph 오케스트레이션과 싸우지 않는다.
10. 개발자로서, 테스트가 `CELERY_TASK_ALWAYS_EAGER`로 태스크를 인라인 실행해 추가 인프라 없이 결정적으로 돌기를 바란다.
11. HITL 상태(`is_hitl=True`) 세션의 방문자로서, 내 메시지가 에이전트를 깨우지 않고 상담원에게 곧장 전달되는 기존 동작이 유지되기를 바란다.

## Implementation Decisions

- **단일 태스크 경계 (그릴 Q2).** `run_chat_agent_task(session_id: str, user_message: str)` 하나가 기존 `run_chat_agent`(LangGraph `graph.invoke` 전체)를 통째로 감싼다. 노드 분해(route/search/llm를 각각 태스크로)는 채택하지 않는다 — LangGraph가 이미 PostgresSaver로 노드를 오케스트레이션하므로 이중 오케스트레이션이 되고 노드마다 브로커 홉이 곱해진다.
- **id 기반 시그니처.** `CELERY_TASK_SERIALIZER="json"`이라 Django 모델을 직렬화할 수 없다. 태스크는 `session_id`(str)만 받아 내부에서 `ChatSession`을 재조회한다(현재 thread는 ORM 객체를 직접 넘김).
- **chat 전용 큐 + 전용 워커 (그릴 Q3).** `CELERY_TASK_ROUTES`로 `run_chat_agent_task`를 `chat` 큐로 라우팅하고, 그 큐만 소비하는 `worker-chat` 서비스를 분리한다. 기존 워커는 배치(`ingest`, `community`, `webhook`, `memory`) 전담. 단일 워커가 `-Q celery,chat` 둘 다 청취하는 안은 격리가 안 되어 비채택.
- **prefork + 튜닝 (그릴 Q3-b).** chat 워커는 prefork(프로세스 격리가 이관의 본질). gevent 워커는 블로킹-허브 병이 재발하므로 비채택. 동시 진행 chat 수 = concurrency로 캡되며 부하는 워커 replica로 수평 확장. `worker_prefetch_multiplier=1`(긴 태스크의 head-of-line 블로킹 방지). `task_soft_time_limit≈90s`(SoftTimeLimitExceeded로 잡아 정리) + `task_time_limit≈120s`(하드 kill) — LLM 경계에 앱 타임아웃이 없으므로 hang 백스톱.
- **세션 단위 직렬화 (그릴 Q4).** 같은 `thread_id`(=session_id) 동시 `graph.invoke`는 PostgresSaver lost update·토큰 인터리빙을 부른다(지금도 잠복, prefork에서 악화). 태스크 시작 시 Redis 락 `SETNX chat:lock:{session_id}`(TTL = 하드 타임리밋) 획득, 실패면 프로세스를 점유하지 말고 `apply_async(countdown=...)`로 재-enqueue, 종료 시 `try/finally`로 해제.
- **at-most-once (그릴 Q5).** 스트리밍 비멱등성 때문에 자동 재시도 없음(`max_retries=0`, `autoretry_for` 미설정), `acks_late=False`(크래시 시 재배달 안 함). 예외 시 `publish_error`로 사용자에게 알리고 재전송 유도(현재 `_run_agent`의 except 동작과 동일).
- **범위 경계 (그릴 Q6).** `is_hitl` 분기는 뷰에 그대로(에이전트 경로만 태스크화). 옛 `threading.Thread`는 토글 플래그 없이 완전 제거. 체크포인터의 매-호출 `PostgresSaver.setup()` 낭비는 이 이관 범위 밖(별도 후속 이슈) — 이관은 "어디서 도느냐"를 바꾸는 것이지 그래프 내부 최적화가 아니다.

### 모듈 스케치

- **`run_chat_agent_task` (신규, Celery 태스크).** 얇은 래퍼 — id로 세션 재조회 → 세션 락 획득(또는 재-enqueue) → `run_chat_agent` 호출 → finally 락 해제 → 예외 시 `publish_error`. `run_chat_agent`(deep module, 불변)는 그대로 재사용.
- **세션 락 (신규, deep module).** `acquire(session_id) -> bool` / `release(session_id)`를 Redis SETNX+TTL 위에 캡슐화. 외부 I/O는 Redis 하나뿐이라 결정적 단위 테스트 가능.
- **`POST /chat/message` 뷰 (수정).** non-hitl 분기에서 `threading.Thread(...)`를 `run_chat_agent_task.delay(session_id, content)`로 교체. is_hitl 분기 불변.

## Testing Decisions

좋은 테스트는 외부 행위만 검증한다(구현 세부 아님). CLAUDE.md 원칙: 실제 객체 사용, 비결정적 LLM 경계(`apps/agent/llm`)만 `fake_chat_llm`으로 교체, 테스트 독립. 실제 Redis·DB·Neo4j·SSE는 결정적이므로 실물 사용.

- **T1 — 뷰→태스크→에이전트 배선.** non-hitl `POST /api/chat/message` → `CELERY_TASK_ALWAYS_EAGER`(conftest에 이미 있음)로 태스크 인라인 실행 → assistant `ChatMessage` 저장 확인. 지금 thread 경로가 암묵적으로만 커버하던 "메시지 전송이 에이전트를 깨운다"를 명시적으로 잠근다.
- **T2 — 세션 락 deep module.** 같은 세션 2회 acquire → 두 번째 False, release 후 재acquire True, TTL 만료. 결정적 단위 테스트(실제 Redis).
- **T3 — 실패 경로.** Fake LLM이 예외를 던지게 → `publish_error`가 Redis에 발행되고 락이 풀려(다음 메시지 안 막힘) 확인.
- 진짜 병렬 동시-세션 레이스는 비결정적이라 테스트하지 않고, T2(락 모듈)로 직렬화 메커니즘을 결정적으로 잠근다.
- **기존 테스트 불변.** `run_chat_agent`를 직접 호출하는 hitl/graph 테스트(`test_hitl.py`, `test_graph_search.py` 등)는 그래프 동작 테스트라 그대로 유효. `test_hitl_mode_session_does_not_invoke_agent`는 is_hitl 경로 불변을 계속 보장.
- Prior art: `tests/test_hitl.py`(run_chat_agent 직접 호출 + Redis 구독), `tests/conftest.py`의 `celery_always_eager`·`fake_chat_llm`·`redis_subscribe`.

## Out of Scope

- 체크포인터 매-호출 `PostgresSaver.setup()` 최적화(별도 후속 이슈).
- LangGraph 노드 내부 로직·그래프 토폴로지 변경.
- LLM 경계 자체에 `request_timeout` 추가(defense-in-depth로 가치 있으나 별도) — 이번엔 Celery `task_time_limit`이 hang 백스톱.
- "끊긴 chat 자동 재개"(스트리밍 비멱등성으로 의도적 비채택).
- 멀티 노드/분산 워커 배치, 오토스케일링 정책.

## Further Notes

- 토큰 전달이 Redis pub/sub로 디커플링되어 있다는 점이 이 이관을 깔끔하게 만든다 — SSE 서빙 gunicorn 워커는 누가 토큰을 생산하든 신경 쓰지 않는다.
- 시작 `--concurrency` 값은 보수적으로(예 4) 잡고 운영 중 조정. chat 처리량은 워커 replica로 확장.
- 그릴 합의: Q1 지연 감수 → Q2 단일 태스크 → Q3/Q3-b 큐·워커 격리 → Q4 세션 직렬화 → Q5 at-most-once → Q6 범위 경계 → Q7 테스트 seam.
