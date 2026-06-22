# ADR-0019: 캐시 친화 메시지 레이아웃 + provider-aware cache_control (인젝션 하드닝 보존)

## Status
Accepted (구현 완료 — issues 133-134)

## Context
챗 에이전트가 LLM에 보내는 메시지는 매 턴 새로 조립된다. 기존 조립(`_assemble_lc_messages`)은 **RAG 근거(Knowledge Base)와 Visitor Memory를 system 메시지 안에 인라인**했다. 이 둘은 질의마다 바뀌므로, 프롬프트의 가장 앞부분인 system 메시지가 **매 요청 달라진다**.

그 결과 LLM provider의 프롬프트 캐싱(안정적 prefix를 재사용해 입력 토큰 비용·지연을 줄이는 기능)이 **전혀 작동하지 않는다**. 테넌트마다 동일한 Base System Prompt + 보안 지침 + 구조화 출력 tool 스키마가 모든 세션·방문자·턴에 반복 전송되지만, 캐시 prefix가 깨져 매번 풀 과금된다.

제약: 비신뢰 입력(RAG·메모리)은 `UNTRUSTED_DATA` 구역으로 격리하고 "데이터지 명령 아님"으로 라벨링하며, anti-disclosure 보안 지침을 항상 주입한다(인젝션 하드닝, PRD-prompt-hardening). 캐싱을 위해 메시지를 재배치하더라도 이 속성은 보존해야 한다.

캐싱 메커니즘은 provider마다 다르다:
- OpenAI·OpenRouter(`ChatOpenAI`): **자동 prefix 캐싱**(마커 불필요, 안정 prefix만 있으면 됨).
- Anthropic(`ChatAnthropic`): **명시적 `cache_control` 마커** 필요(+ 최소 토큰 임계).

## Decision
**휘발성 콘텐츠를 안정 system prefix에서 빼 마지막 사용자 턴으로 옮기고, Anthropic에는 boundary에서 cache_control 분기점 1개를 provider-aware로 주입한다.**

메시지 레이아웃:
```
[tools]    구조화 출력 스키마(HITLResponse/PlainResponse) — 테넌트 불변
[system]   Base System Prompt + 보안 지침(_ANTI_DISCLOSURE) — 테넌트 불변   ← 캐시 분기점
[messages] 대화 history (세션 내 누적)
[user 턴]  (운영 안내) + UNTRUSTED_DATA(RAG·Visitor Memory) + 현재 질문
```

- **안정 prefix = tools + system**(테넌트 불변)이라 모든 세션·방문자·턴에서 재사용된다. 이게 캐시 최대 이득.
- 휘발성(RAG·메모리·운영 안내)은 system이 아니라 **마지막 사용자 턴**에 싣는다. role 교대(system → history → user)가 유효해 Anthropic의 연속 role 제약도 안 깨진다.
- **UNTRUSTED_DATA 격리·라벨링은 옮긴 자리에서도 유지**하고, 보안 지침은 안정 system 블록(휘발성보다 앞)에 둬 인젝션 하드닝을 보존한다.
- **캐시 분기점 1개**(system+tools 끝). Anthropic 경로만 마지막 system 블록을 langchain 블록 형식(`[{"type":"text","text":...,"cache_control":{"type":"ephemeral"}}]`)으로 바꿔 분기점을 주입한다. OpenAI/custom/플랫폼기본은 마커 없이 자동 prefix 캐싱.
- **provider-aware 로직은 LLM 호출 boundary**(`complete_structured`)에 둔다 — 챗 노드는 논리적 메시지만 만들고 provider 분기를 모른다.

## Considered Options
- **분기점 2개 이상**(history 꼬리까지 캐시): 기각(현재). 멀티턴 이득은 있으나 각 분기점이 최소 토큰 임계·복잡도를 더한다. system+tools 1개가 80/20(모든 세션·방문자 교차 재사용).
- **재배치만(provider-agnostic), Anthropic 마커 생략**: 기각. OpenAI/OpenRouter는 이득을 보지만 Anthropic 네이티브는 마커 없이는 캐시가 안 걸린다. 둘 다 지원하는 비용이 작아 둘 다 한다.
- **휘발성을 system 끝에 두고 분기점을 그 앞에**: 기각. system이 매 턴 달라지면(끝에 RAG가 붙어) prefix 동일성이 의도와 어긋나 추론이 흐려진다. 휘발성을 메시지 영역으로 완전히 빼는 편이 명확하고 role 교대도 자연스럽다.
- **노드에서 provider별 메시지 생성**: 기각. 캐싱은 provider 관심사라 boundary에 격리해야 노드가 단순·테스트 가능하게 남는다.

## Consequences
- **캐시 적중**: 테넌트-불변 prefix가 재사용돼 멀티턴·고볼륨 세션의 입력 토큰 비용·지연이 준다(provider가 지원할 때).
- **조용한 no-op 한계**: ① 프롬프트 캐싱은 *적용된 적 없던* 신규 동작이라 캐싱 미설정 시 회귀가 아니다. ② Anthropic 최소 캐시 prefix(보통 1024토큰, Haiku 2048) 미만이면 캐시는 조용한 no-op(에러 아님) — 작은 테넌트 프롬프트는 캐시가 안 걸릴 수 있다.
- **하드닝 테스트 재배선**: UNTRUSTED 격리가 system이 아니라 trailing 턴으로 이동했으므로, 위치를 검증하던 테스트를 새 위치로 갱신했다(보안 속성은 불변).
- **영업시간 안내의 의존**: 시간 외 운영 안내(ADR-0018)가 이 trailing 슬롯을 재사용한다 — system prefix를 안 깨고 휘발성 운영 텍스트를 실을 자리가 생겼다.
- **langchain 의존**: Anthropic 콘텐츠-블록 `cache_control` passthrough는 langchain_anthropic의 문서화된 형식에 의존한다(`with_structured_output`의 tool 정의는 분기점 앞이라 함께 캐시됨).
