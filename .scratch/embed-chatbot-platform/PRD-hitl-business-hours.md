# PRD: HITL 영업시간(상담 가능 시간) 지정

Status: ready-for-agent

관련 ADR: [ADR-0001-hitl-structured-output](../../docs/adr/0001-hitl-structured-output.md) (hitl_enabled로 그래프 토폴로지 분기 — 본 작업이 시간으로 그 분기를 가름) · 관련 PRD: [PRD-hitl](./PRD-hitl.md), [PRD-widget-brand-hitl-toggle](./PRD-widget-brand-hitl-toggle.md)

## Problem Statement

테넌트의 HITL(사람 상담원 전환)은 켜져 있으면 **24시간 언제든** AI가 사람에게 escalation을 만든다. 상담원이 자리에 없는 새벽·주말에도 방문자가 "사람 바꿔줘"라고 하면 escalation이 쌓이지만 아무도 받지 못해, 방문자는 응답 없는 대기에 갇히고 운영자는 빈 escalation을 본다. 운영자는 **"상담 가능 시간(예: 평일 9:00~18:00)"을 지정**해, 그 시간에만 사람 전환이 일어나게 하고 싶다.

## Solution

테넌트가 **타임존 + 요일별 상담 시간창 + 휴일(예외 날짜)** 로 상담 가능 시간을 설정한다. 챗 에이전트는 매 실행마다 "지금이 상담 시간인가"를 계산해, **상담 시간 내에만 HITL 그래프(escalation 가능)** 로, **시간 외에는 plain 그래프(escalation 노드 없음 → 전환 멘트 구조적 차단)** 로 실행한다. 즉 새로운 억제 로직이 아니라 이미 존재하는 두 그래프(ADR-0001)를 **시간으로 선택**한다. 시간 외에 방문자가 상담원을 요구하면, 대화 뒤쪽 **운영 안내 메시지**로 "현재 상담 운영시간이 아니다"를 알려 AI가 자연스럽게 안내한다(프롬프트 캐시 prefix를 깨지 않음 — PRD 캐싱 재구조화에 의존).

## User Stories

1. As a TenantAgent, I want to set my HITL hours (timezone + per-weekday windows), so that human handoff only happens when staff are available.
2. As a TenantAgent, I want to mark specific weekdays as closed (e.g., weekends), so that no escalations are created when nobody is working.
3. As a TenantAgent, I want a holiday calendar of exception dates that force "closed" regardless of weekday, so that public holidays are covered.
4. As a TenantAgent, I want my hours interpreted in my own timezone, so that "9–18시" means my local time even though the server runs in UTC.
5. As a visitor chatting outside business hours, I want the AI to keep answering instead of silently queuing me for a human, so that I still get help.
6. As a visitor who asks for a human outside business hours, I want the AI to tell me the support hours, so that I know when to come back.
7. As a visitor chatting inside business hours, I want human handoff to work exactly as before, so that nothing regresses during open hours.
8. As an operator, I want a tenant that has not configured any hours to remain available 24/7, so that the feature is opt-in and backward compatible.
9. As a TenantAgent, I want the hours settings grouped under the "상담 전환(HITL)" settings sub-tab, so that handoff configuration lives in one place.
10. As a developer, I want a pure, deterministic "is_open(config, now)" decision function, so that the time/timezone/holiday logic is unit-testable without a live clock.
11. As a developer, I want the graph selection to combine `hitl_enabled AND is_open(now)`, so that off-hours uses the existing plain graph with no escalation node.
12. As a TenantAgent who staffs manually, I want off-hours to never create AI escalations, but I still want to manually take over sessions anytime (see Session Console PRD), so that hours gate only AI auto-escalation.
13. As a developer, I want the off-hours notice injected as a trailing context message (not in the system prefix), so that prompt caching is preserved.
14. As a TenantAgent with HITL disabled entirely, I want hours to have no effect, so that the existing plain-graph behavior is unchanged.

## Implementation Decisions

- **그래프 선택으로 게이팅**: 챗 에이전트 실행 시 `hitl_enabled = config.hitl_enabled AND business_hours.is_open(config, now_utc)`로 그래프를 컴파일한다. 시간 외 = `hitl_enabled=False` 그래프(plain, escalation 노드 없음). 새 분기/억제 코드 없이 ADR-0001의 기존 두 토폴로지를 재사용한다.
- **스케줄 표현**: TenantConfig에 (a) **타임존**(IANA 문자열, 예 `Asia/Seoul`), (b) **요일별 시간창**(월~일 각 on/off + start~end, 1구간), (c) **휴일 예외 날짜 리스트**(요일 무관 강제 휴무). 저장은 구조화 JSON 필드로(요일 7키 + 휴일 배열) — 관계형 모델까지는 가지 않음.
- **opt-in / 기본 24/7**: 스케줄 미설정(타임존·시간창 비어 있음)이면 `is_open`은 항상 True → 현재 동작 보존(하위호환).
- **is_open 판정**: `now_utc`를 테넌트 타임존으로 변환 → 그 날짜가 휴일이면 closed → 아니면 해당 요일의 on/off와 시간창으로 판정. 자정 넘는 창(예 22:00~02:00)은 본 PRD 범위에서 단순 start<end만 지원(범위 외는 Out of Scope).
- **시간 외 안내 주입**: `is_open=False`일 때 PRD 캐싱 재구조화가 만든 **뒤쪽 컨텍스트 메시지 슬롯**에 운영 안내 텍스트("현재 상담 운영시간(…)이 아니라 상담원 연결이 어렵습니다")를 싣는다. system prefix는 불변 → 캐시 유지.
- **Deep module**: `business_hours.is_open(config, now_utc) -> bool` (순수 함수). 타임존·요일·휴일 해석을 한 인터페이스로 캡슐화.
- **설정 UI**: ConfigTab의 **handoff(상담 전환) 서브탭**에 타임존·요일별 시간창·휴일을 추가. 백엔드 Schema 변경 → orval 재생성 필요(CLAUDE.md).

## Testing Decisions

- **무엇이 좋은 테스트인가**: `is_open`의 **관찰 가능한 판정**(주어진 config·시각 → open/closed)을 결정적으로 단언한다. 실제 시계 대신 고정 `now_utc`를 주입한다(순수 함수라 자연스러움).
- **테스트 대상 모듈**:
  - `business_hours.is_open`: 타임존 변환(UTC↔KST 경계), 요일 on/off, 시간창 경계(start/end 포함·제외), 휴일이 요일을 덮어쓰는지, 미설정 시 24/7.
  - 그래프 선택: `hitl_enabled=True`라도 시간 외면 plain 그래프(escalation 노드 부재 → needs_hitl 표현 불가)로 실행되는지(실 그래프 빌드 검증). LLM은 결정적 Fake.
  - 시간 외 안내가 컨텍스트 메시지로 주입되고 system prefix는 불변인지.
- **Prior art**: `apps/agent` 그래프/노드 테스트, `test_hitl.py`(HITL 분기), 설정 라운드트립 테스트, ConfigTab vitest.

## Out of Scope

- **요일당 다중 시간창**(점심 휴게 분리 등): 안 함(요일당 1구간).
- **자정 넘는 시간창**(overnight, end<start): 본 PRD 미지원.
- **상담원 개인별 근무표**: 테넌트 단위 한 스케줄만.
- **위젯에 영업시간 배지 상시 표시**: 본 PRD 아님(안내는 AI 응답으로만).
- **escalation 큐잉/시간 내 자동 처리**: 시간 외엔 escalation을 아예 안 만든다(큐 없음).

## Further Notes

- **선행 의존**: PRD 프롬프트 캐싱 재구조화 — 시간 외 안내가 그쪽의 "뒤쪽 컨텍스트 메시지 슬롯"에 실리므로 캐싱 PRD가 먼저.
- **수동 takeover와의 관계**: 영업시간은 *AI 자동 escalation*만 가른다. 자리에 있는 상담원의 수동 takeover(세션 콘솔 PRD)는 시간과 무관하게 항상 가능.
- ADR 후보: "영업시간을 별도 게이트가 아니라 그래프 선택(hitl_enabled AND is_open)으로 구현"은 surprising-without-context라 ADR 가치가 있다.
