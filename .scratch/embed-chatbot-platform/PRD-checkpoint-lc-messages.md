Status: ready-for-agent

# PRD: Checkpoint에서 lc_messages 중복 제거

## Problem Statement

Tenant 어드민에서 세션의 Checkpoint를 확인하면 같은 대화가 **두 번, 서로 다른 형식으로** 나타나고 순서가 시간순이 아닌 것처럼 보인다. 실제 데이터(운영 세션):

```
messages:     [{"role":"user","content":"..."}, {"role":"assistant","content":"..."}]   ← 시간순 정상
lc_messages:  [{"type":"human","content":"...","additional_kwargs":{},"example":false}, ...] ← System 먼저 + LangChain 객체 형태
```

LangGraph Checkpoint의 `channel_values`에는 대화가 `messages`(우리가 저장하는 dict)와 `lc_messages`(LLM 프롬프트 조립물, LangChain 메시지 객체) **두 채널에 중복** 저장돼 있다. Checkpoint 뷰는 `channel_values` 전체를 덤프하므로 둘 다 보여, "중복 + 뒤죽박죽"으로 읽힌다. `lc_messages`는 System 메시지가 맨 앞이고 마지막 user는 응답 없이 끝나므로 더더욱 시간순 대화처럼 보이지 않는다.

## Solution

`lc_messages`는 LLM 호출용 임시 프롬프트 조립물일 뿐 영속 대화 상태가 아니다. 이를 LangGraph 상태 채널에서 제거해 Checkpoint에 더 이상 저장되지 않게 한다. Checkpoint에는 시간순으로 정확한 `messages` 하나만 남아, 어드민에서 깔끔하게 보인다.

## User Stories

1. As a TenantAgent, I want the Checkpoint view to show each conversation message only once, so that I'm not confused by duplicate entries.
2. As a TenantAgent, I want the Checkpoint messages to read in chronological order, so that I can follow the conversation.
3. As a TenantAgent, I want the persisted Conversation Memory(Checkpoint) to contain the conversation(`messages`) and not the internal prompt-assembly artifact, so that the state is meaningful.
4. As a developer, I want `lc_messages` to be a local computation inside the LLM call, not a durable graph channel, so that checkpoints stay small and free of transient artifacts.
5. As a developer, I want the chat agent's externally observable behavior (assistant responses, HITL escalation, message persistence) to remain identical after the change, so that no functionality regresses.
6. As a developer, I want a regression test asserting the checkpoint contains `messages` but not `lc_messages` after a turn, so that this duplication cannot silently return.
7. As a returning Visitor, I want existing sessions to continue working after the change, so that the schema change doesn't break in-flight conversations.

## Implementation Decisions

### `lc_messages`를 그래프 채널에서 제거 (노드 병합)

현재 그래프: `retrieve → assemble_prompt → call_llm → (route) → create_escalation | save_messages`. `assemble_prompt_node`는 `lc_messages` 채널을 산출하고 `call_llm_structured`가 이를 읽어 LLM을 호출한다.

이 둘을 **하나의 노드로 병합**한다. 병합 노드가 system 프롬프트 + Visitor Context/Memory + RAG chunks + 과거 `messages` + 현재 `user_message`로 LangChain 메시지 리스트를 **로컬 변수**로 조립해 곧바로 `llm_boundary.complete_structured`를 호출한다. `lc_messages`는 어디에도 반환/저장되지 않는다.

`ChatState` TypedDict에서 `lc_messages` 필드를 제거한다. 그래프 엣지는 `retrieve → call_llm → (route) → ...`로 단순화된다. 토큰 발행(`publish_token`/`publish_done`), 반환 채널(`assistant_response`/`needs_hitl`/`hitl_reason`), HITL 라우팅, `save_messages`/`create_escalation` 동작은 모두 그대로 유지된다.

### 기존 세션 처리 (앞으로만 수정)

마이그레이션은 하지 않는다(LangGraph checkpoint 테이블 직접 조작은 위험 대비 가치 낮음). 새 턴/새 세션부터 checkpoint에 `lc_messages`가 없다. 기존 세션이 다음 턴에서 orphan `lc_messages`를 새 snapshot에 싣지 않고 정리되는지는 구현 중 실제로 확인하고, orphan이 남으면 그때 재검토한다. (별도 운영 작업으로 전체 데이터 truncate가 병행될 수 있어 기존 garbage는 사실상 사라진다.)

### Checkpoint 엔드포인트/뷰는 무변경

`/sessions/{id}/checkpoint`는 계속 `channel_values`를 반환하고, 프론트 `CheckpointView`는 그대로 둔다. 중복의 원천(`lc_messages` 채널)이 사라지므로 표시 변경이 불필요하다.

## Testing Decisions

좋은 테스트는 내부 노드 구조가 아니라 외부에서 관찰 가능한 동작을 검증한다: 한 턴 실행 후 Checkpoint의 `channel_values`에 무엇이 들어있는지, 그리고 응답/HITL/메시지 누적이 그대로인지.

- **회귀 테스트(핵심)**: run_chat_agent로 한 턴(또는 멀티턴) 실행 후 `saver.get(...)`의 `channel_values`에 `messages`는 존재하고 `lc_messages` 키는 **부재**함을 단언한다. 그리고 `messages`가 시간순([user, assistant, ...])임을 단언한다.
- **행동 보존 테스트**: 기존 HITL/checkpoint 테스트(test_hitl.py, test_chat_session.py)가 그대로 통과해야 한다 — escalation 생성, 비-escalation assistant 저장, checkpoint 누적, resolved 후 재개.
- 단위/통합 테스트는 chat LLM을 conftest Fake로 결정적으로 대체한다(기존 방침 유지).

Prior art: `test_chat_session.py`의 checkpoint 조회/누적 테스트, `test_hitl.py`.

## Out of Scope

- 기존 checkpoint 데이터 마이그레이션/정리 스크립트.
- Checkpoint 엔드포인트/프론트 뷰 표시 변경.
- 동시 메시지 전송 시 checkpoint 턴 손실(별개의 동시성 레이스 버그) — 별도 이슈로 다룬다.
- `user_message`/`assistant_response`/`rag_chunks` 등 노드가 실제 사용하는 채널 — 이들은 영속 채널로 유지(중복 원흉이 아님).
- 전체 데이터 truncate는 운영 작업으로 별도 수행.

## Further Notes

`lc_messages`가 `messages`와 중복되는 이유: `assemble_prompt_node`가 `messages`(dict)를 LangChain 객체로 변환해 별도 채널에 저장했기 때문. 병합 후에는 변환 결과가 노드 내부에만 존재한다. 동시성 손실 버그는 이번 범위 밖이며, 별도로 "세션당 agent 실행 직렬화 + done 발행 전 checkpoint 저장" 방향으로 다룰 것.
