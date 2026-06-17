# 10 — EmbedWidget (React)

Status: ready-for-agent

## What to build

별도 레포의 React 앱으로, Tenant 사이트의 `<iframe>` 안에서 렌더링되는 챗봇 위젯을 구현한다. URL 파라미터에서 EmbedToken을 추출해 SSE 연결을 맺고, 메시지를 입력하면 POST 후 SSE 스트림으로 LLM 응답을 실시간으로 표시한다.

- URL 파라미터: `?token={EmbedToken}`
- SSE 연결: `GET /api/chat/stream?token={EmbedToken}`
- 메시지 전송: `POST /api/chat/message {session_id, content}`
- SSE 이벤트 처리: `token`(텍스트 누적), `done`(입력 활성화), `error`(오류 표시)
- 대화 이력을 UI에 표시 (사용자 메시지 + LLM 응답)
- prod Compose에서는 빌드된 정적 파일을 Nginx가 서빙

## Acceptance criteria

- [ ] iframe URL에 유효한 EmbedToken이 있으면 위젯이 렌더링되고 SSE 연결이 맺어짐
- [ ] 만료된 EmbedToken → 오류 메시지 표시
- [ ] 메시지 입력 후 전송 → LLM 응답이 단어 단위로 스트리밍되어 UI에 표시됨
- [ ] `done` 이벤트 수신 후 입력창 활성화
- [ ] `error` 이벤트 수신 시 사용자에게 오류 안내 표시
- [ ] `npm run build` → Nginx 서빙 가능한 정적 파일 생성

## Blocked by

- `04-chatsession-sse.md`
