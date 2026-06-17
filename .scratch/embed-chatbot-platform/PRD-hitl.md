---
title: HITL (Human-in-the-Loop) 상담 시스템
label: ready-for-agent
blocked-by: PRD-tenant-agent.md
---

## Prerequisites

이 PRD의 구현은 `PRD-tenant-agent.md` (TenantAgent 계정 시스템)가 완료된 이후에 진행한다. HITL `EscalationClaim.claimed_by`는 `TenantAgent.username`을 참조하며, 어드민 UI의 HITL 탭 인증은 TenantAgent JWT를 사용한다.

## Problem Statement

현재 챗봇은 AI 단독으로 모든 Visitor 질문에 응대한다. AI가 답변할 수 없는 복잡한 문의(환불 분쟁, 법적 질문, 감정적 응대가 필요한 상황)나 Visitor가 사람과 직접 대화하길 원하는 경우에도 AI가 계속 응답해 Visitor 신뢰를 훼손하고, Tenant 입장에서는 중요한 고객 응대를 AI에게만 맡겨야 하는 문제가 있다. 또한 에스컬레이션이 발생했을 때 Tenant 팀이 이를 실시간으로 인지하고 개입할 방법이 없다.

## Solution

LLM Structured Output으로 AI가 스스로 에스컬레이션이 필요한지 판단하고, Visitor가 상담원을 요청하는 키워드도 동일 메커니즘으로 감지한다. Escalation이 생성되면 Tenant 설정 웹훅(Slack·Discord·Generic)으로 즉시 알림이 발송된다. Tenant 상담원은 어드민 UI의 실시간 HITL 탭에서 세션을 수락(Claim)하고 Visitor와 직접 대화한다. 문제 해결 후 "AI에게 넘기기"를 누르면 AI 모드로 복귀한다. Visitor에게는 전환 시스템 메시지가 표시되어 사람이 응대하고 있음을 알 수 있다.

## User Stories

1. As a Visitor, I want the chatbot to automatically escalate to a human agent when the AI cannot confidently answer my question, so that I receive accurate help without having to repeat myself.
2. As a Visitor, I want to see a clear message when I'm connected to a human agent, so that I know who I'm talking to.
3. As a Visitor, I want to see the human agent's name or team name in the chat, so that the interaction feels personal and trustworthy.
4. As a Visitor, I want to continue sending messages while waiting for an agent to connect, so that I can provide additional context upfront.
5. As a Visitor, I want to know when my conversation is handed back to AI after the agent resolves my issue, so that I understand the transition.
6. As a Tenant, I want to receive an immediate notification on Slack when a Visitor session is escalated, so that my team can respond quickly.
7. As a Tenant, I want the notification to include the last few messages and visitor context, so that I can understand the situation without opening the admin UI.
8. As a Tenant, I want a direct link to the admin UI session in the notification, so that I can jump directly to the escalated conversation with one click.
9. As a Tenant, I want to claim an escalated session in the admin UI, so that my team doesn't accidentally respond to the same Visitor twice.
10. As a Tenant, I want to see the full conversation history when I open an escalated session, so that I have context before responding.
11. As a Tenant, I want to type and send messages to the Visitor in real time from the admin UI, so that the conversation feels natural.
12. As a Tenant, I want to hand the conversation back to AI when I've resolved the issue, so that the AI can handle follow-up questions.
13. As a Tenant, I want to configure my Slack webhook URL in the admin settings, so that notifications go to the right channel.
14. As a Tenant, I want to choose between Slack, Discord, and Generic webhook formats, so that the payload is correctly formatted for my notification platform.
15. As a Tenant, I want to set a display name for my agents (e.g., "ABC쇼핑 고객센터"), so that it appears correctly in the Visitor's chat widget.
16. As a Tenant, I want to see a real-time list of pending and claimed escalations in the admin UI, so that my team knows what needs attention.
17. As a Tenant, I want unclaimed escalations to be clearly highlighted, so that urgent sessions are not missed.
18. As a Tenant agent, I want to see which escalations are already claimed by another team member, so that I don't duplicate effort.
19. As a Tenant, I want the AI to remain silent during HITL mode, so that the Visitor is not confused by simultaneous AI and human responses.
20. As a Tenant, I want messages sent by the Visitor during HITL mode to be delivered to me in real time, so that the conversation flows naturally.
21. As an Operator, I want HITL events to be logged with trigger type and reason, so that I can audit escalation patterns across Tenants.

## Implementation Decisions

### 새 도메인 모델: Escalation, EscalationClaim

`Escalation` 모델: ChatSession과 1:1 대응(한 세션에 최대 하나의 활성 Escalation). 필드: `id` (UUID), `session` (FK → ChatSession), `trigger_type` (`ai` / `visitor`), `reason` (text, LLM이 반환하는 이유), `status` (`pending` → `claimed` → `resolved`), `created_at`, `resolved_at`.

`EscalationClaim` 모델: Escalation과 1:1. 필드: `escalation` (OneToOne, unique constraint), `claimed_by` (text, 클레이머 식별자), `claimed_at`. DB 레벨 unique constraint로 동시 클레임 방지.

ChatMessage에 `ROLE_HUMAN_AGENT = "human_agent"` role 추가. HumanTurn 메시지는 기존 ChatMessage 테이블에 이 role로 저장.

ChatSession에 `is_hitl` (BooleanField, default=False) 추가. Escalation 생성 시 True, resolved 시 False로 전환.

### LangGraph 그래프 변경

현재 그래프: `retrieve → assemble_prompt → call_llm → save_messages`

변경 후:
```
retrieve → assemble_prompt → call_llm_structured → check_hitl → (분기)
  ├─ needs_hitl=True  → create_escalation → END
  └─ needs_hitl=False → save_messages → END
```

`call_llm_structured` 노드: `.with_structured_output()`으로 LLM을 호출해 `{ response: str, needs_hitl: bool, hitl_reason: str }` 구조로 반환. Visitor 위젯의 스트리밍 UX를 유지하기 위해, `needs_hitl=False`인 경우에만 `response` 내용을 SSE token 이벤트로 emit. `needs_hitl=True`인 경우 response를 버리고 Escalation 생성 후 SSE `hitl_start` 이벤트만 emit.

> 트레이드오프: Structured Output은 스트리밍과 동시 적용이 어려우므로, LLM 호출이 완료된 후 response를 단일 SSE event로 전송하는 방식으로 변경된다. 이는 스트리밍 타이핑 효과를 포기하는 대신 HITL 감지 정확도를 확보한다.

### WebhookDispatcher 모듈

인터페이스: `dispatch(escalation, session, recent_messages)` — 단일 public 메서드.

내부적으로 `webhook_type`에 따라 Slack (`blocks` 포맷), Discord (`embeds` 포맷), Generic (raw JSON) 포맷터를 선택해 HTTP POST 전송. Celery task(`send_escalation_webhook.delay(escalation_id)`)로 비동기 실행.

알림 페이로드 포함 항목:
- 트리거 유형 및 이유
- 마지막 5개 메시지
- VisitorContext (있을 경우)
- 어드민 UI 딥링크 (`/admin-ui/?hitl={session_id}`)

### Escalation API (새 라우터)

인증: `tenant_key_auth` (기존 패턴 유지)

| 메서드 | 경로 | 동작 |
|--------|------|------|
| GET | `/api/tenant/escalations/` | 활성 Escalation 목록 (pending + claimed) |
| POST | `/api/tenant/escalations/{id}/claim` | 세션 클레임 (select_for_update + unique constraint) |
| POST | `/api/tenant/escalations/{id}/message` | HumanTurn 메시지 전송 |
| POST | `/api/tenant/escalations/{id}/resolve` | AI 모드 복귀 |
| GET | `/api/tenant/escalations/stream` | SSE — `hitl:{tenant_id}` Redis 채널 구독 |

### SSE 이벤트 확장

기존 `session:{session_id}` 채널에 신규 이벤트 타입 추가:
- `hitl_start`: Visitor 위젯에 HITL 전환 알림 (발신 채널: session)
- `hitl_message`: Visitor 위젯에 HumanTurn 메시지 전달 (발신 채널: session)
- `hitl_end`: Visitor 위젯에 AI 복귀 알림 (발신 채널: session)

신규 `hitl:{tenant_id}` 채널:
- `escalation_new`: 새 Escalation 생성 시 어드민 UI에 알림
- `escalation_claimed`: 클레임 시 어드민 UI에 동기화
- `escalation_message`: HumanTurn 메시지 어드민 실시간 동기화
- `escalation_resolved`: Escalation 종료 어드민 동기화

### TenantConfig 스키마 변경

기존 TenantConfig 모델에 필드 추가:
- `webhook_url`: URLField (blank=True)
- `webhook_type`: CharField (choices: `slack`/`discord`/`generic`, blank=True)
- `agent_display_name`: CharField (default: "상담원")

### Chat API 변경

`POST /api/chat/message`: 메시지 처리 전 `session.is_hitl` 확인. `True`이면 ChatMessage를 user role로 저장하되 LangGraph 호출 없이 SSE `hitl_message` 이벤트만 emit.

### 어드민 UI 변경 (embed-chat-admin)

- 새 "HITL 상담" 탭: `/api/tenant/escalations/stream` SSE 구독으로 실시간 목록 유지. 미수락(pending) 세션 하이라이트. Claim 버튼 → 메시지 입력 인터페이스 → "AI에게 넘기기" 버튼.
- 설정 탭: `webhook_url`, `webhook_type` 선택, `agent_display_name` 입력 필드 추가.

### 위젯 변경 (embed-chat-widget)

- `hitl_start` 이벤트: "잠시만 기다려 주세요. 상담원과 연결 중입니다." 시스템 메시지 표시. 입력창 대기 상태 (메시지는 보낼 수 있지만 AI 답변 없음).
- `hitl_message` 이벤트: `agent_display_name`으로 발신자 표시, AI 버블과 다른 스타일 적용.
- `hitl_end` 이벤트: "AI 상담으로 전환되었습니다." 시스템 메시지 표시.

## Testing Decisions

**좋은 테스트 기준**: 공개 인터페이스를 통해 동작을 검증. 내부 구현이 바뀌어도 테스트가 깨지지 않아야 함. "Escalation이 생성되면 웹훅이 전송된다"를 테스트하되, 포맷터 내부 구조는 테스트하지 않음.

**테스트할 모듈**:

- **WebhookDispatcher**: `dispatch()` 호출 시 올바른 URL로 HTTP POST가 나가는지, Slack/Discord/Generic 각각 올바른 포맷인지. HTTP 클라이언트를 mock해 외부 의존 없이 테스트 가능. 기존 `tests/` 패턴 참조.

- **EscalationClaim 동시성**: 같은 Escalation에 두 번 claim 시도 시 두 번째가 실패하는지. DB 트랜잭션 테스트.

- **LangGraph HITL 분기**: `call_llm_structured` 노드가 `needs_hitl=True`를 반환할 때 Escalation이 생성되고 SSE `hitl_start`가 emit되는지. LLM을 mock해 Structured Output 반환값 제어. 기존 `tests/test_agent.py` 패턴 참조.

- **Chat API HITL 모드 차단**: `session.is_hitl=True`인 세션에 `POST /chat/message` 시 LangGraph 미호출 확인. 기존 `tests/test_chat.py` 패턴 참조.

- **어드민 UI (embed-chat-admin)**: HITL 탭 Claim 버튼, 메시지 전송, Resolve 동작을 fetch mock으로 테스트. 기존 `src/test/OperatorDashboard.test.jsx`, `MemoryTab.test.jsx` 패턴 참조.

- **위젯 (embed-chat-widget)**: `hitl_start`, `hitl_message`, `hitl_end` SSE 이벤트 시 UI 상태 변화. MockEventSource 패턴 재사용. 기존 `src/test/ChatWidget.test.jsx` 패턴 참조.

## Out of Scope

- Escalation Claim timeout / 자동 재할당 (클레이머가 응답 없이 자리를 비운 경우)
- Tenant당 복수 웹훅 URL 등록
- HITL 통계·리포팅 대시보드
- Visitor가 HITL 대기 중 이탈했을 때의 재연결 처리
- Slack Bot / Discord Bot 양방향 응답 통합 (웹훅은 단방향 알림만)
- Escalation 만료 시간 (Pending 상태로 무한 대기 방지)

## Further Notes

- Structured Output은 모든 OpenRouter 모델이 지원하지 않을 수 있음. `model_id` 선택 시 function calling 지원 여부를 Tenant가 인지해야 함. 미지원 모델에서의 fallback 처리(graceful degradation)는 별도 이슈로 관리 권장.
- `select_for_update()`를 사용한 클레임 동시성 제어는 PostgreSQL 트랜잭션을 활용. 기존 DB 스택과 완전 호환.
- 웹훅 전송 실패 시 Celery의 `autoretry_for` + 지수 백오프로 재시도. 최대 3회 실패 시 로그 기록.
