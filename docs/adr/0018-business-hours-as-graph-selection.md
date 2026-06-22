# ADR-0018: 상담 가능 시간(영업시간)을 별도 게이트가 아니라 그래프 선택으로 구현

## Status
Accepted (구현 완료 — issues 135-137)

## Context
Tenant가 "상담 가능 시간(예: 평일 9–18시)"을 지정해, 그 시간에만 사람 상담원으로의 전환(escalation)이 일어나게 하고 싶다. 시간 외에는 상담원이 부재이므로 AI가 escalation을 만들면 방문자가 응답 없는 대기에 갇히고 운영자는 빈 escalation을 본다.

핵심 관찰: 챗 에이전트 그래프는 이미 **`hitl_enabled` 불리언으로 두 개의 물리적으로 다른 토폴로지로 컴파일**된다(ADR-0001).
- `hitl_enabled=True`: `call_llm_structured`(HITLResponse, `needs_hitl` 필드 있음) + `create_escalation` 노드 존재.
- `hitl_enabled=False`: `call_llm_plain`(PlainResponse, `needs_hitl` 없음) — escalation 노드가 아예 없어 **전환 멘트 누수가 구조적으로 불가능**.

즉 "시간 외 = 사람 전환 없음"은 이미 존재하는 plain 그래프의 동작과 정확히 같다. 새 억제 로직을 추가할 필요가 없다.

서버는 UTC(`USE_TZ=True`)라 "9–18시"는 **테넌트 타임존** 해석이 필요하다.

## Decision
**영업시간을 새로운 억제 코드가 아니라, 실행 시점의 그래프 선택으로 구현한다.** 챗 1턴 실행 시:

```
effective_hitl = config.hitl_enabled AND business_hours.is_open(config, now_utc)
build_graph(hitl_enabled=effective_hitl)
```

- 시간 외(`is_open=False`) = `hitl_enabled=False` 그래프(plain) → AI가 계속 답하고 escalation 자체가 생기지 않는다.
- **`business_hours.is_open(config, now_utc) -> bool`** 은 순수 함수 deep module로, 타임존·요일별 시간창·휴일을 한 인터페이스로 캡슐화한다. 고정 `now_utc`를 주입해 결정적으로 테스트한다.
- 스케줄은 TenantConfig에 **타임존(IANA) + 요일별 시간창(월~일 각 on/off + start~end 1구간) + 휴일 예외 날짜 리스트**(요일 무관 강제 휴무)를 JSON으로 저장한다.
- **opt-in / 기본 24/7**: 타임존·스케줄 미설정이면 `is_open`은 항상 True → 기존 동작 보존(하위호환).
- 시간 외 운영 안내("현재 상담 운영시간이 아닙니다")는 system prefix가 아니라 **마지막 사용자 턴(trailing 컨텍스트)** 으로 주입해 프롬프트 캐시 prefix를 깨지 않는다(ADR-0019).
- **수동 takeover는 영업시간과 무관**하다(issue 140) — 시간 게이트는 *AI 자동 escalation*만 가른다. 자리에 있는 상담원은 언제든 임의 세션을 직접 잡을 수 있다.

## Considered Options
- **(A) 그래프는 그대로 두고 escalation 직전에 시간 가드를 추가**: 기각. `needs_hitl=True`가 이미 LLM 출력으로 떴는데 시간 외라 막으면, AI가 만든 전환 멘트("상담원에게 연결해 드릴게요")가 누수된다. plain 그래프는 이 멘트를 *구조적으로* 못 만든다 — 가드보다 안전.
- **(B) hitl_enabled를 시간에 따라 영구 토글**(크론으로 config 갱신): 기각. 분 단위 정확도·타임존·휴일 처리가 지저분하고, 설정 상태와 런타임 상태가 분리돼 혼란.
- **(C) escalation은 만들되 큐잉**(시간 외 pending 보관, 복귀 시 처리): 기각. 방문자가 무응답 대기에 갇히고, "곧 연락"을 지키는 백그라운드 처리·알림이 별도로 필요. 지원 봇의 기대와 안 맞음.
- **요일당 다중 시간창 / 자정 넘는 창**: 범위 외(요일당 1구간, start<end만). 필요 시 후속.

## Consequences
- **새 분기 코드 0**: 기존 두 토폴로지를 시간으로 고를 뿐이라, 전환 멘트 누수 차단 같은 불변식이 자동으로 상속된다.
- **테스트 분리**: `is_open`의 정확성(타임존·경계·휴일·미설정)은 순수 함수 단위 테스트로, "게이트 결과에 따른 그래프 선택"은 `is_open`을 monkeypatch해 시간 의존성 없이 검증한다.
- **수동 takeover와의 직교성**: 시간 게이트는 AI 자동 경로만 다룬다. 상담원 주도 takeover(ADR 없음, issue 140)는 항상 가능해 운영 유연성을 해치지 않는다.
- **관찰성**: 시간 외에는 escalation이 *생성되지 않으므로*, "왜 상담 전환이 안 됐나"는 escalation 부재 + 운영 안내 메시지로 설명된다(별도 거부 로그 없음).
