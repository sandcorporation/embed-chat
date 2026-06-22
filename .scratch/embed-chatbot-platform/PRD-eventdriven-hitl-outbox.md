# PRD: HITL/세션 라이프사이클 Event-Driven 전환 (Transactional Outbox + EventBus)

Status: ready-for-agent

관련 ADR: [ADR-0001-sse-redis-pubsub](../../docs/adr/0001-sse-redis-pubsub.md) (현재 실시간 전송) · [ADR-0002-hitl-claim-model](../../docs/adr/0002-hitl-claim-model.md) (Escalation claim) · [ADR-0018](../../docs/adr/0018-business-hours-as-graph-selection.md) (영업시간) · 관련 PRD: [PRD-session-console-takeover-presence](./PRD-session-console-takeover-presence.md)

## Problem Statement

지금 HITL/세션 흐름은 **명령형 상태 변경 + 사이드이펙트 통지**다. `create_escalation_node`·claim·resolve·takeover가 `session.is_hitl` 등을 직접 mutate한 뒤 Redis pub/sub `publish_*`와 webhook `.delay`를 side-effect로 쏜다. 이 구조엔 세 가지 한계가 있다:

1. **디커플링 부재**: 새 소비자(분석·감사·알림)를 추가하려면 생산 지점(노드·엔드포인트) 코드를 건드려야 한다.
2. **감사·재생 불가**: pub/sub은 fire-and-forget이라 "무슨 전이가 언제 일어났나"의 영속 이력이 없다 — 재생·디버깅·감사가 안 된다.
3. **사이드이펙트 신뢰성 부재**: 상태 변경 커밋과 통지 발행이 한 트랜잭션이 아니라(`try/except pass`), 크래시 시 webhook/SSE 통지가 조용히 유실되거나 이중 발행될 수 있다(dual-write 문제).

## Solution

HITL/세션 라이프사이클을 **카논 도메인 이벤트**로 모델링하고, **Transactional Outbox**로 "상태 변경과 이벤트 기록을 한 트랜잭션"으로 묶어 dual-write를 없앤다. 이벤트는 **권위 DB는 그대로 두되**(완전 이벤트소싱 아님) 영속 `event_store`에 감사로 남고, **relay**가 **EventBus**(Redis Streams 어댑터, 추후 Kafka 교체 가능)로 발행하면, 디커플링된 소비자(webhook·방문자 SSE·콘솔·presence)가 각자 파생한다. 방문자 실시간 신호(`hitl_start`/`hitl_end`)와 콘솔 델타가 **단일 원천**(도메인 이벤트)에서 나오고, webhook은 at-least-once+DLQ로 승격된다.

## User Stories

1. As a platform engineer, I want every HITL state transition recorded as a domain event in the same transaction as the state change, so that no notification is lost or duplicated on crash (dual-write eliminated).
2. As a platform engineer, I want an append-only event_store of HITL lifecycle events, so that I can audit and replay "what happened when" for any session.
3. As a platform engineer, I want consumers decoupled from producers via an EventBus, so that I can add a new consumer (analytics, audit) without touching the escalation node or endpoints.
4. As a platform engineer, I want the EventBus behind a narrow port with a Redis Streams adapter now, so that we can swap to Kafka later by writing only a new adapter.
5. As a TenantAgent, I want webhook notifications on escalation to be at-least-once with retry and dead-letter, so that a transient Slack/Discord outage no longer silently drops the alert.
6. As a visitor, I want the "상담원 연결됨"(hitl_start) and "AI 복귀"(hitl_end) signals to arrive reliably from a single source, so that the handoff UX is consistent (sub-second latency acceptable).
7. As a TenantAgent, I want the session console live deltas (escalated/claimed/resolved/takenover) derived from the event stream, so that the console reflects reality without bespoke publish calls scattered in code.
8. As a TenantAgent, I want presence (visitor connected/disconnected) deltas unified onto the same EventBus transport, so that all session-console live updates flow through one pipeline.
9. As a platform engineer, I want a single relay (LISTEN/NOTIFY) that drains the outbox in order, so that events reach the bus in aggregate order with low latency.
10. As a platform engineer, I want the relay to catch up any unpublished outbox rows on (re)connect/boot, so that a NOTIFY missed while the relay was down is not lost.
11. As a platform engineer, I want consumers to be idempotent via a processed_events dedup table, so that at-least-once redelivery does not double-apply effects (e.g., double webhook).
12. As a platform engineer, I want a single global durable stream with session_id as the envelope key, so that v1 is simple while a future Kafka adapter can partition by that key.
13. As an operator, I want failed events to land in a dead-letter stream after bounded backoff with an alert, so that poison messages don't block the consumer or loop forever.
14. As an operator, I want a CLI to list and replay dead-lettered events, so that I can recover after fixing the cause.
15. As a platform engineer, I want the outbox pruned after publish while the event_store is retained, so that the delivery queue stays small and the audit log stays permanent.
16. As a platform engineer, I want each consumer to run as its own process (webhook, visitor-bridge, console-bridge, presence-bridge), so that one consumer's failure or load is isolated from the others.
17. As a developer, I want the consumer code to be a single parameterized loop (`--group=<name>`), so that adding/splitting consumers is a deployment change, not new code.
18. As a developer, I want a canonical event envelope (event_id, type, aggregate_id, tenant_id, occurred_at, schema_version, payload), so that all consumers parse a stable shape.
19. As a developer, I want the cut-over gated by parity tests proving each transition emits exactly one correct event and each consumer reproduces the prior webhook/SSE/console behavior, so that the big-bang migration is safe.
20. As a developer, I want LLM token streaming and live HITL chat messages to stay on the existing Redis pub/sub, so that high-frequency ephemeral traffic doesn't bloat the durable pipeline.
21. As a platform engineer, I want presence heartbeat (keepalive ZADD) to stay a direct Redis write (not an event), so that per-second TTL refresh doesn't flood the event bus.
22. As a TenantAgent, I want takeover/claim/resolve to behave identically after the migration, so that the console and visitor experience are unchanged.
23. As a platform engineer, I want the escalation event emitted from inside the LangGraph chat node's transaction, so that AI-triggered escalation is atomic with is_hitl and the Escalation row.

## Implementation Decisions

- **목표·깊이**: 디커플링 + 감사/재생 + 사이드이펙트 신뢰성. **이벤트 로그 + 권위 DB + 프로젝션**(rebuild-from-events 아님). ChatSession/Escalation 행이 권위 유지.
- **저장(큐/감사 분리)**: 상태 전이 트랜잭션에서 **`event_store`(영구 append-only 감사) + `outbox`(전송 큐, 자기완결 payload)** 둘 다 insert. relay가 outbox 드레인·발행 후 **outbox만 prune**, event_store는 영구. (outbox는 Kafka로 가도 dual-write 해결용으로 필요 — 브로커 무관.)
- **relay**: **Postgres LISTEN/NOTIFY 싱글톤**. outbox insert에 트리거 NOTIFY → 즉시 드레인. 부팅/재연결 시 미발행 outbox 행 **catch-up sweep**(NOTIFY 유실 안전망)은 필수. 단일 relay라 aggregate/global 순서 보존.
- **EventBus 포트(deep module)**: 좁은 인터페이스 — `publish(topic, key, payload)` + consumer-group `consume(group, consumer) -> handler` + `ack` + dead-letter. **Redis Streams 어댑터 v1**, Kafka 어댑터는 추후 드롭인. relay·소비자는 포트만 의존.
- **스트림/봉투**: 단일 글로벌 내구 스트림 + 봉투 `{event_id, type, aggregate_id=session_id, tenant_id, occurred_at, schema_version, payload}`. key=session_id는 v1 Redis에선 미사용(단일 스트림), Kafka 파티션키로 예약.
- **이벤트 경계**:
  - **내구(outbox→event_store→bus, DLQ)**: `SessionEscalated`·`EscalationClaimed`·`SessionTakenOver`·`EscalationResolved`.
  - **ephemeral(EventBus capped 스트림, outbox 미경유, best-effort)**: `VisitorConnected`·`VisitorDisconnected`.
  - **기존 pub/sub 유지(이벤트화 안 함)**: LLM 토큰, 라이브 HITL 메시지(hitl_message/visitor_message/typing), presence 하트비트 ZADD.
- **소비자(각 별도 프로세스, 코드는 단일 파라미터화 루프)**:
  - `webhook` ← `SessionEscalated` (at-least-once + 재시도 + DLQ).
  - `visitor-bridge` ← 내구 이벤트 → `session:{id}` 채널에 `hitl_start`(Escalated/TakenOver)·`hitl_end`(Resolved) 발행(단일 원천).
  - `console-bridge` ← 내구 이벤트 → `hitl:{tenant}` 델타.
  - `presence-bridge` ← ephemeral presence 이벤트 → presence sorted-set 갱신 + `hitl:{tenant}` 델타.
- **콘솔 읽기 모델**: **DB/Redis 스냅샷 + 이벤트 델타**. `GET /tenant/sessions/`·presence sorted-set은 그대로 권위 스냅샷, 라이브 델타만 이벤트 소비. 새 프로젝션 테이블 없음.
- **멱등성**: `processed_events(consumer_group, event_id)` dedup. DB 효과 있는 소비자는 같은 트랜잭션에 dedup insert로 사실상 exactly-once.
- **DLQ**: 소비자가 XPENDING/XCLAIM idle로 제한 백오프 재시도 → 소진 시 dead-letter 스트림 + 구조화 알림. 운영자용 **management command로 DLQ 조회·수동 리플레이**(자동 재처리 루프 없음).
- **런타임**: 신규 프로세스 — `relay`(싱글톤) + 소비자 4종 프로세스. dev/prod compose에 추가(worker-chat 패턴 재사용).
- **트랜잭션 경계**: AI escalation은 `create_escalation_node`(LangGraph, worker-chat) 안에서 `transaction.atomic`으로 `is_hitl 변경 + Escalation 생성 + event_store/outbox insert`. takeover/claim/resolve(웹 엔드포인트)도 동일하게 atomic.
- **마이그레이션 = 빅뱅**: 직접 `publish_*`/webhook `.delay`를 outbox 발행으로, presence `publish_*`를 EventBus ephemeral로 한 번에 교체, 전 소비자 동시 컷오버. parity 테스트가 머지 게이트.

## Testing Decisions

- **무엇이 좋은 테스트인가**: 외부 행위 — 전이마다 정확한 이벤트 1건이 event_store/outbox에 남고, relay가 순서대로 발행하고, 소비자가 기존과 동일한 webhook/SSE/콘솔 결과를 내는지. 내부 구조가 아니라 관찰 가능한 이벤트·사이드이펙트를 단언.
- **인프라는 실객체(CLAUDE.md)**: v1 테스트는 **Docker 실 Redis Streams·실 Postgres**로. EventBus Fake 포트는 설계 안정 후 도입(초기엔 실 Stream로 충실도 우선).
- **테스트 대상**:
  - Outbox/event_store: 전이 트랜잭션이 둘 다 1건 기록, 실패 시 롤백(이벤트도 안 남음).
  - relay: outbox 순서대로 발행·prune, catch-up sweep로 미발행 행 회수, event_store 불변.
  - EventBus(Redis Streams 어댑터): consumer-group at-least-once, ack, XCLAIM 재시도, dead-letter 이동.
  - 멱등: 같은 event_id 재전달이 효과를 두 번 내지 않음(webhook 1회, projection 1회).
  - 소비자 parity: SessionEscalated→webhook 발사·hitl_start 발행·콘솔 델타가 기존 동작과 동일.
  - 빅뱅 parity: takeover/claim/resolve/AI escalation 후 방문자 SSE·콘솔·webhook 관찰 결과 불변.
- **Prior art**: `test_escalation.py`(claim/message/resolve·SSE·redis_subscribe), `test_presence.py`(실 Redis), `test_session_console.py`, `test_webhook.py`(실 HTTP 수신 서버), `test_chat_agent_task.py`.

## Out of Scope

- **완전 이벤트소싱**(상태를 이벤트에서 rebuild/스냅샷): 안 함. DB 권위 유지.
- **ingest/rag/memory 이벤트화**: 범위 외(기존 Celery 유지). v1은 HITL/세션 라이프사이클만.
- **LLM 토큰·라이브 HITL 메시지·typing의 이벤트화**: 기존 pub/sub 유지.
- **Kafka 어댑터 구현**: 포트만 Kafka-ready로, 어댑터는 v1 미구현.
- **테넌트별/N-파티션 스트림**: 단일 글로벌 스트림. Kafka 전환 시 재검토.
- **별도 read-model 프로젝션 테이블(CQRS)**: 안 함(DB/Redis 스냅샷 + 델타).
- **DLQ 자동 재처리 루프**: 안 함(수동 리플레이 CLI).
- **strangler 병행 이중운영**: 안 함(빅뱅 + parity 테스트).

## Further Notes

- **ADR 후보**: "Transactional Outbox + 포트화 EventBus(Redis Streams now/Kafka later), 큐·감사 분리, 빅뱅 컷오버"는 되돌리기 비용·트레이드오프가 커 ADR 가치가 있다(발행은 별도).
- **위험·완화**: 빅뱅은 HITL 핵심 경로를 한 번에 바꾸므로, parity 테스트(단위+통합+e2e)를 머지 전 GREEN으로 강제하는 게 유일한 안전장치. relay 싱글톤은 SPOF이므로 재시작·catch-up sweep로 복원력 확보(향후 leader-election 여지).
- **봉투 schema_version**: v1=1. v2 이벤트 shape 등장 시 역직렬화에 upcaster 추가(현재는 스텁).
