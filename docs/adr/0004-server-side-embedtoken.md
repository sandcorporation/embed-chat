# ADR-0004: Server-side EmbedToken signing flow

## Status
Accepted

## Context
Visitor가 Tenant 사이트를 방문할 때 챗봇 iframe을 안전하게 초기화해야 한다. TENANT_KEY를 브라우저에 노출하지 않아야 한다.

## Decision
EmbedToken 발급을 서버사이드 플로우로 강제한다.

1. Visitor가 Tenant 사이트 방문
2. Tenant 서버가 Operator API에 `TENANT_KEY + VisitorId + VisitorContext`로 EmbedToken 발급 요청
3. Operator가 TTL이 있는 서명된 EmbedToken 반환
4. Tenant 서버가 `<iframe src="...?token={EmbedToken}">` 형태로 응답

## Consequences
- TENANT_KEY가 절대 브라우저에 노출되지 않는다.
- EmbedToken은 TTL이 있어 탈취 시 피해가 제한된다.
- 최초 SSE 연결 후 ChatSession이 생성되고, 이후 세션은 session_id로 관리된다.
- Tenant가 서버사이드 통합을 구현해야 하므로 순수 정적 사이트에는 적용이 어렵다.
