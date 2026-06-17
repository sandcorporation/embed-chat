# 04 — ChatSession 생성 + SSE 스트리밍 기반

Status: ready-for-agent

## What to build

EmbedToken으로 SSE 연결을 열면 ChatSession이 생성되고, Redis pub/sub을 통해 이벤트를 스트리밍하는 기반 레이어를 구현한다. 이 슬라이스에서 LLM은 연결하지 않고, 에코 메시지(입력을 그대로 되돌려주는)로 스트리밍 파이프라인 전체가 동작함을 검증한다.

- `GET /api/chat/stream?token={EmbedToken}` → SSE 연결, ChatSession 생성
- `POST /api/chat/message` — Body: `{session_id, content}` → Redis publish → SSE 스트림으로 에코 반환
- SSEBridge: Django `StreamingHttpResponse`, ChatSession ID 기준 Redis 채널 구독
- Nginx: `proxy_buffering off`, `X-Accel-Buffering: no` 헤더 설정
- 여러 `api` 인스턴스가 떠 있어도 Redis pub/sub 덕분에 올바른 연결로 에코가 전달됨

## Acceptance criteria

- [ ] `GET /api/chat/stream?token={EmbedToken}` → SSE 연결 수립, DB에 ChatSession 레코드 생성
- [ ] 만료된 EmbedToken으로 스트림 요청 → 401
- [ ] `POST /api/chat/message {session_id, content}` → SSE 스트림으로 에코 메시지 수신
- [ ] SSE 이벤트 타입: `token`(청크), `done`(완료), `error`
- [ ] `api` 컨테이너 2개 실행 시, 연결이 맺어진 인스턴스와 다른 인스턴스에 POST해도 SSE 수신 정상
- [ ] 통합 테스트: Redis pub/sub 실제 연결, SSE 스트림 수신 확인

## Blocked by

- `03-embed-token.md`
