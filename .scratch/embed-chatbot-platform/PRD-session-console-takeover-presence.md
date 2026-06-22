# PRD: 세션 콘솔 — 전체 세션 가시화 + 임의 세션 takeover + presence

Status: ready-for-agent

관련 ADR: [ADR-0002-hitl-claim-model](../../docs/adr/0002-hitl-claim-model.md) (Escalation claim — takeover가 재사용) · [ADR-0001-sse-redis-pubsub](../../docs/adr/0001-sse-redis-pubsub.md) (SSE/Redis pub-sub — presence·이벤트의 토대) · [ADR-0017](../../docs/adr/0017-admin-stay-react-tailwind-shadcn-nested-routes.md) (admin 라우팅) · 관련 PRD: [PRD-hitl](./PRD-hitl.md), [PRD-conversation-visibility](./PRD-conversation-visibility.md)

## Problem Statement

상담원(TenantAgent)은 **AI가 escalation을 만든 세션에서만** 사람 상담을 할 수 있다. 그 외 세션 — 방문자가 지금 AI와 대화 중인 활성 세션이나 과거 세션 — 은 HITL 화면(HitlTab)에 보이지도 않고, 상담원이 먼저 끼어들 방법도 없다. 운영자는 (1) **모든 세션을 한 화면에서 보고**, (2) **지금 접속해 있는(SSE 연결된) 세션을 알아보고**, (3) **원하는 아무 세션이나 직접 상담을 시작(takeover)** 하고 싶다.

## Solution

HitlTab을 **세션 콘솔**로 진화시킨다. 콘솔은 테넌트의 세션을 **3계층으로 정렬**해 보여준다: **escalation(최상위) → 활성(SSE 연결됨) → 나머지(최근창, 페이지네이션)**. 활성 여부는 **Redis presence**(SSE keepalive가 갱신하는 TTL = 자가치유 진실원천) + **이벤트 push**(연결/해제 시 `hitl:{tenant}` 채널로 실시간 통지)로 판단한다. 상담원은 아무 세션이나 골라 **takeover** 할 수 있고, takeover는 자동-claimed `Escalation(trigger=agent)`을 만들어 기존 message/typing/resolve 기계를 그대로 재사용하며, 방문자에겐 "상담원 연결됨"을 알린다. resolve하면 AI로 복귀한다.

## User Stories

1. As a TenantAgent, I want to see all my tenant's sessions in one console, so that I'm not limited to AI-escalated ones.
2. As a TenantAgent, I want escalated sessions pinned at the top, so that the ones needing attention are first.
3. As a TenantAgent, I want pending (un-handled) escalations above claimed ones within the top tier, so that unaddressed handoffs surface first.
4. As a TenantAgent, I want currently-connected (SSE-active) sessions in the second tier, so that I can jump into live conversations.
5. As a TenantAgent, I want the remaining (idle/past) sessions below, ordered by recency and paginated, so that the list stays manageable as sessions accumulate.
6. As a TenantAgent, I want to take over any session — not just escalated ones, so that I can proactively help a visitor who's talking to the AI.
7. As a TenantAgent who takes over a session, I want the visitor to be told a human connected, so that the handoff is transparent.
8. As a TenantAgent, I want takeover to reuse the existing claim/message/typing/resolve flow, so that the chat console behaves consistently with AI escalations.
9. As a TenantAgent, I want to resolve a taken-over session back to the AI, so that the bot resumes after I'm done.
10. As a TenantAgent, I want takeover to work even outside business hours, so that being present lets me help regardless of the AI's auto-escalation schedule.
11. As a TenantAgent, I want to take over a session whose visitor is offline, so that my message persists and the visitor sees it when they return.
12. As a TenantAgent, I want the console to update live as visitors connect/disconnect, so that the active tier reflects reality without manual refresh.
13. As a TenantAgent, I want the console to show correct presence even after a server/worker crash, so that stale "active" entries self-heal.
14. As a visitor, I want my session to register as "active" while my widget is connected, so that a human can find and join my live chat.
15. As a TenantAgent, I want to open a specific session via a deep-linked URL, so that I can share or bookmark an in-progress consultation.
16. As a developer, I want presence implemented with Redis TTL refreshed on SSE keepalive, so that no new infrastructure is needed and disconnects expire automatically.
17. As a developer, I want connect/disconnect events published to the existing `hitl:{tenant}` channel, so that the admin SSE stream pushes live deltas without polling.
18. As a developer, I want a deep "presence" module (mark active / list active sessions) testable against real Redis, so that presence logic is locked in isolation.
19. As a TenantAgent, I want two agents racing to take over the same session to be resolved by the existing claim uniqueness (one wins, other gets a conflict), so that there's no double-takeover.
20. As a TenantAgent, I want the session list to show each session's visitor id, status (escalated/active/idle), and last activity, so that I can triage at a glance.

## Implementation Decisions

- **Presence (Redis, 자가치유)**: 테넌트별 sorted set(예 `presence:{tenant}` ZADD score=now, member=session_id). SSE 스트림 루프의 keepalive 지점에서 갱신(연결 살아있는 동안 score 신선). "활성"=score가 임계(예 15~30s) 이내. 연결 끊김→갱신 중단→임계 밖으로 밀려 자연 소멸(워커 비정상 종료에도 자가치유). 스트림에 tenant_id를 흘려 presence 갱신·이벤트 publish에 사용.
- **이벤트 push (실시간성)**: SSE 연결 시작/종료 전이에서 `session_connected`/`session_disconnected`를 **기존 `hitl:{tenant}` 채널**에 publish. 어드민 콘솔의 기존 escalation SSE 스트림이 이 채널을 이미 구독 → 새 인프라 없이 live delta 수신. 콘솔 최초 로드는 presence 집합(진실원천)을 조회해 초기 상태 구성, 이후 이벤트로 갱신.
- **전체 세션 엔드포인트**: `GET /tenant/sessions/`(tenant_agent_auth). 최근창(예 최근 N시간/일) + 페이지네이션. 각 행에 session_id·visitor_id·is_hitl·escalation 상태(있으면)·presence 활성 여부·last activity·created_at을 enrich. 3계층 정렬(escalation: pending→claimed → 활성 → 나머지 최근순)은 서버에서 수행하거나 플래그를 내려 클라이언트 정렬(구현 시 택1, 관찰 동작 동일).
- **takeover 엔드포인트**: `POST /tenant/sessions/{session_id}/takeover`(tenant_agent_auth). 동작: 자동-claimed `Escalation(trigger=agent, status=claimed, claimed_by=현재 agent)` 생성 + `session.is_hitl=True` + `publish_hitl_start`(방문자 알림) + `publish_hitl_new`(콘솔 갱신). 응답으로 escalation id 반환 → 콘솔이 채팅 열기. 이미 active escalation이 있으면 그걸 반환(중복 생성 방지).
- **Escalation 모델 확장**: `TRIGGER_AGENT`(수동 takeover) 추가. claim/message/typing/resolve API는 그대로 재사용. takeover는 claim 단계를 건너뛴 자동-claimed(생성자=claimed_by). 동시 takeover는 `EscalationClaim` OneToOne 유일성으로 한 명만 성공(409).
- **영업시간 무관**: takeover는 PRD 영업시간의 `is_open`과 독립 — 상담원이 직접 시작하므로 시간 게이트 적용 안 함.
- **오프라인 방문자 허용**: presence와 무관하게 takeover 허용. human 메시지는 ChatMessage로 영속되어 방문자 재접속(세션 복원) 시 노출.
- **콘솔 UI**: HitlTab을 세션 콘솔로 확장. 상단 escalation 카드(기존 claim/message/resolve) = 최상위 계층, 그 아래 활성/나머지 세션 목록. 세션 클릭 → takeover(미escalation 시) 또는 기존 채팅(escalation 존재 시). 딥링크 URL 보존(ADR-0017).
- **백엔드 Schema 변경** → orval 재생성(CLAUDE.md).

## Testing Decisions

- **무엇이 좋은 테스트인가**: 외부 행위 — (a) presence 모듈에 mark 후 list가 활성 세션을 돌려주고 TTL 경과 후 빠지는지, (b) takeover 엔드포인트가 자동-claimed escalation을 만들고 is_hitl을 켜고 방문자에 알림을 publish하는지, (c) 세션 목록이 3계층 순서로 나오는지, (d) 동시 takeover가 한 명만 성공(409)하는지 — 를 단언한다. Redis·DB·SSE 수신부는 **실제 객체**(CLAUDE.md: 결정적으로 만들 수 있는 인프라는 실 사용, Docker).
- **테스트 대상 모듈**:
  - `presence`(mark_active/active_sessions, TTL 만료): 실 Redis.
  - 세션 목록 enrich·정렬: escalation/활성/나머지 계층 순서, 최근창·페이지네이션.
  - takeover: escalation 생성·is_hitl·publish, 멱등(이미 active면 재사용), 동시성(409).
  - SSE 연결/해제 시 connect/disconnect 이벤트가 `hitl:{tenant}`에 실리는지.
- **Prior art**: `test_escalation.py`(claim/message/resolve·SSE), `test_chat_session.py`·`test_hitl.py`, `test_visitors.py`(세션 목록), HitlTab/VisitorsTab vitest, `test_chat_agent_task.py`.

## Out of Scope

- **방문자가 트리거한 escalation(TRIGGER_VISITOR) UI 노출**: 기존대로(본 PRD는 trigger=agent 추가만).
- **세션 종료(ended_at) 라이프사이클 도입**: 안 함. 활성/비활성은 presence(Redis)로 판단, ended_at은 건드리지 않음.
- **비-HITL 활성 세션의 실시간 메시지 내용 스트리밍**(콘솔 목록에서): 목록은 presence·상태만. 메시지 내용은 takeover 후 노출.
- **전체 세션 무한 조회**: 최근창+페이지네이션으로 제한(과거 전수는 VisitorsTab 경유).
- **상담원별 라우팅/배정 규칙**: 아무 agent나 아무 세션 takeover(테넌트 스코프만).

## Further Notes

- **병렬 가능**: 캐싱·영업시간 PRD와 독립. 메시지/그래프 파이프라인이 아니라 escalation·admin·presence를 건드린다.
- **presence 갱신 빈도**: keepalive(1s)마다 ZADD는 부담이 작지만, 필요 시 N번째 keepalive마다(예 5~10s) 갱신 + TTL 여유로 조정 가능(구현 튜닝).
- presence 임계·최근창 크기는 구현 시 합리적 기본값으로 두고 추후 조정.
