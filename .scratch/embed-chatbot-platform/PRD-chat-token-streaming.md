# PRD — 챗 응답 실시간 토큰 스트리밍

Status: ready-for-agent

## Problem Statement

방문자가 챗봇에 물으면 AI 응답이 **전부 생성된 뒤 한 번에** 떠서 느리게 느껴진다. 원인: 챗
에이전트가 `complete_structured`(구조화 출력 단일 블로킹 호출)로 `{response, needs_hitl,
hitl_reason, context_sufficient}`를 한꺼번에 받아, 전체 LLM 생성(2~10초)이 끝나야 `publish_token`
한 번 → done이 나간다. 토큰 인프라(publish_token→Redis→SSE→위젯 누적 렌더)는 이미 있는데, 토큰을
여러 번 쏘지 않을 뿐이다.

## Solution

답변 텍스트를 **토큰별로 흘려** 첫 토큰이 ~1초에 뜨게 한다. 위젯은 이미 `setStreamingText(prev =>
prev + data.content)`로 누적 렌더하므로 **프론트는 무변경**이고, 백엔드 챗 노드만 단일 호출을
스트리밍으로 바꾼다. 구조화 출력의 라우팅 신호(`context_sufficient`로 원문 폴백 판정)와 충돌하지
않도록, **제어 필드를 먼저** 받아 "이 답을 흘려도 되는지"를 흘리기 전에 판정한다.

## User Stories

1. As a 방문자, I want AI 답변이 타이핑되듯 실시간으로 나타나기, so that 전체를 기다리지 않고 바로 읽기 시작한다.
2. As a 방문자, I want 첫 토큰이 빠르게 뜨기, so that 챗봇이 느리다는 느낌이 사라진다.
3. As a 운영자, I want 스트리밍이 실패하는 provider에서도 답변이 정상적으로(한 번에라도) 도착하기, so that 모델 호환성 때문에 응답이 깨지지 않는다.
4. As a 운영자, I want 필요 시 스트리밍을 전면 끌 수 있기, so that 문제가 생기면 안전하게 현행 동작으로 되돌린다.
5. As a 방문자, I want 원문 폴백(그래프 근거 부족)이 일어나도 답이 한 번만(중복 없이) 나타나기, so that 답이 두 번 출력되지 않는다.
6. As a 방문자, I want HITL 전환 멘트도 실시간으로 보기, so that 상담원 연결 안내가 자연스럽게 흐른다.
7. As a 테넌트, I want HITL on/off 두 경로 모두 스트리밍되기, so that 설정과 무관하게 빠른 응답을 얻는다.
8. As a 방문자, I want 스트리밍 중 에러가 나면 명확히 처리되기(멈춤 표시), so that 무한 대기에 빠지지 않는다.
9. As a developer, I want LLM 스트리밍을 결정적 Fake로 검증하기, so that 외부 모델 없이 노드 동작을 회귀 검증한다.
10. As a developer, I want 그래프 추출(extract_graph)은 비-스트리밍 그대로이기, so that 문서 인제스션은 영향받지 않는다.

## Implementation Decisions

- **핵심 방식(단일 호출, 제어필드 먼저)**: 챗 답변을 `with_structured_output(schema).stream()`로 받아 `response` 필드의 **델타만** `publish_token`한다. 스키마 필드 순서를 **`context_sufficient`를 `response`보다 먼저**로 둬, 스트림 앞부분에서 폴백 라우팅을 판정하고 흘릴지 결정한다. (needs_hitl/hitl_reason은 스트리밍을 게이팅하지 않으므로 response 뒤여도 됨 — 라우팅은 응답 완료 후.) 프로토타입이 확정한 필드 순서:
  - `HITLResponse`: `context_sufficient` → `response` → `needs_hitl` → `hitl_reason`
  - `PlainResponse`: `context_sufficient` → `response`
- **경계(deep module) — 부분 dict yield, 게이팅은 노드**: `stream_structured(provider, messages, schema)`가 **누적 dict**(아직 안 온 필드는 키 부재)를 점진 yield한다. Pydantic partial은 기본값으로 채워져 "부재"와 "기본값"을 구분 못 하므로 **dict 존재 여부**로 판단한다. 노드가: `'context_sufficient' in d`면 종단 판정(`_will_source_fallback`) → 종단이면 `d['response']` 델타를 publish, 폴백이면 억제. 끝에 dict를 schema로 검증해 라우팅 값 반환. `complete_structured`(비-스트리밍)는 그래프 추출용으로 유지.
- **우아한 자동 저하(provider 안전망)**: 노드는 "안전할 때만 흘리고, 아니면 끝에 한 번에"를 보장한다 — 제어필드가 response보다 늦게 오거나 부분 스트리밍이 없으면(최종 1청크만) 버퍼링했다가 **종단이면 전체를 한 번 publish**(=현행 one-shot), 폴백이면 억제. 즉 잘 맞는 provider(OpenAI 등)는 실시간, 안 맞으면 자동으로 현행 동작으로 저하(절대 후퇴·중복 없음).
- **킬스위치**: `CHAT_STREAMING_ENABLED`(기본 on). off면 `complete_structured` 경로(현행 one-shot)로.
- **두 경로 적용**: `call_llm_structured`(HITLResponse)·`call_llm_plain`(PlainResponse) 모두 스트리밍. 원문 폴백 억제(issue 119)·HITL 전환 멘트 스트리밍은 현 의미 보존.
- **에러**: 스트림 도중 예외 시 `publish_error` + done 처리(위젯이 멈춤/에러 표시). 부분 출력 후 에러도 graceful.
- **실행 위치**: worker-chat(Celery) 안 sync for-loop로 chunk마다 publish — 인프라(Redis pub/sub→SSE) 그대로, 위젯 무변경.

## Testing Decisions

- LLM은 비결정 외부 경계 → 결정적 Fake(CLAUDE.md). conftest의 autouse `fake_chat_llm`가 지금 `complete_structured`를 Fake하는데, 챗 노드가 `stream_structured`로 바뀌므로 **`stream_structured`도 Fake**해야 한다(안 그러면 실제 LLM 호출). Fake는 override/기본 판정을 받아 **"제어필드 dict → response 청크들"을 결정적으로 yield**한다.
- **노드 행동 테스트**: ① 종단 패스에서 `publish_token`이 **여러 번**(델타) 호출되고 누적이 응답과 일치, ② 폴백 패스(`context_sufficient=False`·미시도)에선 **스트리밍 억제**(중복 출력 0 — issue 119 회귀 보존), ③ 제어필드가 늦게 오는 Fake에선 **끝에 one-shot**으로 저하(깨짐·중복 없음), ④ HITL 전환 멘트 스트리밍 + 라우팅(needs_hitl) 정상, ⑤ 킬스위치 off면 현행 one-shot.
- prior art: 기존 `test_local_source_fallback.py`(폴백·중복 스트리밍 방지 `test_fallback_streams_answer_once`), `test_chat_*`(checkpoint·publish_done), conftest `_FakeChatLLM`.

## Out of Scope

- 실제 토큰 단위 생성은 provider 의존 — 미지원 모델은 설계상 one-shot으로 자동 저하(버그 아님).
- 마크다운 렌더링(별도 기능) — 본 스트리밍이 켜지면 "부분 마크다운" 처리가 다시 관건이 되므로, 마크다운 후속에서 점진/완료 렌더를 결정한다.
- 프론트(위젯/admin) 변경 — 위젯은 이미 토큰 누적 처리. admin 실시간 표시는 별도.
- 그래프 추출·메모리 추출 등 비-챗 LLM 경로.

## Further Notes

- 위젯은 무변경이라 백엔드만으로 체감 속도가 크게 좋아진다(첫 토큰 ~1초).
- 관련: ADR-0001(SSE/Redis pub/sub), 0010/issue119(조건부 원문 폴백 — 억제 의미 보존), ADR-0019(캐시 친화 메시지 — 스트리밍과 무관하게 유지).
