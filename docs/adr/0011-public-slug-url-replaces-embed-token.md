# ADR-0011: 공개 Tenant Slug URL이 EmbedToken을 대체 — 계층형 Visitor 신원

## Status
Accepted (EmbedToken 기반 접근 모델을 supersede; A1에서 구현 예정)

## Context
현재 Visitor는 Tenant 서버가 `TENANT_KEY + VisitorId`로 발급한 단기 서명 토큰(EmbedToken, TTL 300s)을 iframe URL의 `?token=`으로 받아 연결한다. 이 토큰은 ① tenant 식별 ② 연결 인가(서명) ③ visitor_id·VisitorContext의 **신뢰**를 한꺼번에 담는다.

문제는 연동 마찰이다 — Tenant는 Visitor가 위젯을 열 때마다 자기 서버에서 토큰 발급 왕복을 해야 한다. "챗봇 URL만 주면 바로 위젯이 뜨는" 단순함을 원한다. 동시에 토큰을 그냥 없애면 세 가지 신뢰가 함께 붕괴한다: 누구나 `?visitor_id=`를 위조해 **남의 Visitor Memory·대화 이력을 열람**할 수 있고, VisitorContext도 위조된다.

## Decision
**EmbedToken(per-session 서명 토큰)을 폐지하고, 공개 Tenant Slug URL + 계층형 Visitor 신원으로 대체한다.**

- **공개 URL**: `/chatbot/{slug}/`. tenant는 URL 경로의 **Tenant Slug**(고유·URL-safe, 표시명과 분리)로 해석. 연결 인가 서명은 없다 — 공개가 의도다. Tenant는 발급 단계 없이 그냥 iframe만 박는다.
- **계층형 Visitor 신원** (마찰과 보안의 트레이드오프를 토글로 분리):
  - 익명: 위젯이 생성·localStorage 저장하는 **Anonymous Visitor ID**(지속) — 추측 불가, 같은 브라우저에서 이력·기억 축적.
  - 식별 기본: `?visitor_id=` 평문 — 마찰 0, best-effort.
  - 식별 보안(opt-in 토글 **Identity Verification**): `?visitor_id=` + `HMAC(tenant secret, visitor_id)` 해시. 토글 ON이면 서버가 무효/누락 해시를 거부.
- **무상태 HMAC**: 위조 방지를 per-session 토큰이 아니라 **안정·캐시 가능한 HMAC 해시**로 한다. visitor_id당 결정적이라 유저당 1회 계산해 무기한 캐시. 해시는 **Operator 백엔드의 HMAC API**(TENANT_KEY 인증)로 받거나 Tenant가 직접 계산.
- **VisitorContext 폐지**: 연결 시점 신뢰 채널을 제거. 첫 메시지 개인화는 상실하고 Visitor Memory로 대체. 비신뢰 입력 채널이 하나 줄어 프롬프트 인젝션 표면도 축소.
- **최소 남용 가드**: 공개 URL이므로 (tenant, visitor_id)당 + per-tenant Redis 레이트리밋을 둔다. 하드 비용 쿼터는 Tenant-부담 LLM(기능 C)에서 본격화.

## Considered Options
- **필수 HMAC**: 기각. 모든 식별 연동에 Tenant 백엔드 크립토를 강제해 마찰이 크다. opt-in 토글이 쉬운 기본과 안전한 선택지를 동시에 준다.
- **평문 visitor_id만(검증 옵션 없음)**: 기각. 익명엔 충분하나 식별 사용자의 Visitor Memory가 위조에 노출. 토글로 보안 경로를 남긴다.
- **EmbedToken 유지**: 기각. "URL만 주면 바로" 단순함과 세션마다의 발급 왕복이 상충.
- **VisitorContext를 HMAC 범위에 포함(신뢰 유지)**: 기각. context 변경 시마다 해시 갱신 마찰. 폐지가 더 단순하고 인젝션 표면도 줄인다.
- **dual-support 전환기**: 기각. 운영 트래픽/실 Tenant가 없어 clean cut이 더 단순.

## Consequences
- `create/verify_embed_token`, `/api/embed/token`, `EMBED_TOKEN_TTL_SECONDS`, 위젯 `?token=` 분기가 제거된다. `/api/chat/stream`은 `?token=` 대신 slug+visitor_id(+hash) 계약으로 바뀐다.
- `ChatSession.visitor_context` 필드와 프롬프트의 "## Visitor Context" 주입이 제거된다(컬럼 드롭 migration).
- TENANT_KEY는 유지되나 용도가 바뀐다: EmbedToken 발급 → **HMAC API 인증** + TenantAgent 생성.
- 공개 URL은 새 남용 표면을 연다. 최소 레이트리밋이 A1에 포함되며, 기능 C 이전에 반드시 존재해야 한다.
- 글로서리: EmbedToken·VisitorContext 항목은 구현 시 제거, Tenant Slug·Anonymous Visitor ID·Identity Verification으로 대체.
