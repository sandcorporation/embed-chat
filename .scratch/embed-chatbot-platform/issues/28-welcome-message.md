# 28 — TenantConfig 환영 메시지

Status: ready-for-agent

## Parent

`.scratch/embed-chatbot-platform/PRD-widget-ux-improvements.md`

## What to build

TenantConfig에 `welcome_message` 필드를 추가하고, Visitor가 ChatWidget을 열면 자동으로 assistant 버블로 표시되도록 end-to-end 구현한다.

- DB: `TenantConfig.welcome_message` (TextField, blank=True, default="") 추가 + 마이그레이션
- API: TenantConfig GET/PATCH 응답에 `welcome_message` 포함
- SSE: `stream` 엔드포인트가 `tenant.config.welcome_message`를 읽어 `connected` 이벤트 payload에 포함 (값이 있을 때만 키 포함)
  ```json
  { "session_id": "...", "welcome_message": "안녕하세요!" }
  ```
- ChatWidget: `connected` 이벤트에서 `welcome_message` 가 있으면 `role: "assistant"` 메시지로 상태에 추가
- 어드민 ConfigTab: 환영 메시지 textarea 입력 필드 추가 (LLM 모델 선택 위에 배치)

## Acceptance criteria

- [ ] `PATCH /api/tenant/config/` 로 `welcome_message` 저장 가능
- [ ] `GET /api/tenant/config/` 응답에 `welcome_message` 포함
- [ ] `welcome_message` 가 설정된 Tenant의 위젯을 열면 SSE `connected` payload에 해당 값이 포함됨
- [ ] ChatWidget 초기 렌더링 시 환영 메시지가 assistant 버블로 표시됨
- [ ] `welcome_message` 가 빈 문자열이면 `connected` payload에 키가 없음
- [ ] 기존 Tenant(마이그레이션 전 생성)는 환영 메시지 없이 정상 동작
- [ ] 어드민 ConfigTab에서 환영 메시지를 입력·저장할 수 있음
- [ ] 테스트: `welcome_message` 설정 후 SSE connected payload 검증, 비어있을 때 키 없음 검증

## Blocked by

None — can start immediately
