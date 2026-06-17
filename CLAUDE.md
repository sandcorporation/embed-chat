# 작업의 순서
/grill-* /to-prd /to-issues /tdd 의 순서

# 테스트 작성시
- RED/GREEN/REFACTOR 사이클을 따르세요.
- 기본적으로 MOCK을 사용하지 마세요. 실제 객체를 사용하세요. (내부 협력자/우리 코드는 절대 mock하지 않음)
- 예외: 비결정적인 외부 경계(예: LLM/OpenRouter 호출)는 결정적 Fake/Mock으로 교체하세요. 테스트는 외부 모델의 판단 품질이 아니라 우리 코드의 동작을 검증해야 합니다. 단, 임베딩·DB·SSE·HTTP 수신부 등 결정적으로 만들 수 있는 것은 실제 객체를 사용하세요.
- 가능한한 모든 유저 스토리를 테스트하세요. (예: 로그인, 로그아웃, 회원가입 등)
- 테스트는 독립적이어야 합니다. 다른 테스트에 의존하지 마세요.

## Agent skills

### Issue tracker

이슈는 이 저장소의 `.scratch/<feature>/` 아래 로컬 마크다운 파일로 관리됩니다. `docs/agents/issue-tracker.md` 참조.

### Triage labels

표준 레이블 어휘 사용: needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. `docs/agents/triage-labels.md` 참조.

### Domain docs

단일 컨텍스트 구조 — 루트의 `CONTEXT.md` 하나 + `docs/adr/`. `docs/agents/domain.md` 참조.
