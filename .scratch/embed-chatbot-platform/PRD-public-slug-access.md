Status: ready-for-agent

# PRD: 공개 Tenant Slug URL이 EmbedToken을 대체 (A1)

ADR: `docs/adr/0011-public-slug-url-replaces-embed-token.md`

## Problem Statement

Tenant가 챗봇을 자기 사이트에 붙이려면, Visitor가 위젯을 열 때마다 자기 서버에서 `TENANT_KEY`로 단기 EmbedToken을 발급하는 왕복을 해야 한다. "챗봇 URL만 주면 바로 위젯이 뜨는" 단순함을 원하는데, 토큰 발급 단계가 그 단순함을 막는다. 동시에 토큰을 그냥 없애면 누구나 `?visitor_id=`를 위조해 남의 Visitor Memory·대화 이력을 열람하는 신뢰 붕괴가 일어난다.

## Solution

EmbedToken(per-session 서명 토큰)을 폐지하고 **공개 Tenant Slug URL**(`/chatbot/{slug}/`)로 대체한다. Tenant는 발급 단계 없이 iframe만 박으면 된다. Visitor 신원은 계층화한다: 익명은 위젯이 생성·저장하는 **Anonymous Visitor ID**, 식별은 평문 `?visitor_id=`(마찰 0), 보안이 필요하면 Tenant별 **Identity Verification**(opt-in HMAC) 토글로 위조를 막는다. 공개 URL의 남용은 최소 레이트리밋으로 가드한다.

## User Stories

1. Tenant로서, 토큰 발급 서버 코드 없이 `/chatbot/{slug}/` URL을 iframe에 넣기만 하면 챗봇이 뜨길 바란다, 그래야 연동이 단순하다.
2. Tenant로서, 내 챗봇 URL에 쓸 짧고 고유한 이름(Tenant Slug)을 어드민에서 직접 정하고 싶다.
3. Tenant로서, slug가 이미 쓰이는 이름이면 거부되어 전역 고유성이 보장되길 바란다.
4. Tenant로서, slug를 나중에 바꿀 때 "기존 임베드 URL이 끊긴다"는 경고를 받고 싶다.
5. Tenant로서, 표시명(name)은 한글·공백으로 자유롭게 두고 slug만 URL-safe로 분리하고 싶다.
6. Visitor로서, 익명으로 챗봇을 열어도 같은 브라우저에서 다시 오면 이전 대화·맥락이 이어지길 바란다.
7. Visitor로서, 위젯이 내 익명 식별자를 localStorage에 저장해 세션을 넘어 지속하길 바란다.
8. Tenant로서, 내 유저시스템의 로그인 사용자를 `?visitor_id=`로 그냥 넘겨 식별 대화를 붙이고 싶다(마찰 0).
9. Tenant로서, 보안이 필요한 경우 어드민에서 "신원검증 요구"를 켜서 visitor_id 위조를 막고 싶다.
10. Tenant 백엔드로서, Operator의 HMAC API를 TENANT_KEY로 호출해 visitor_id의 검증 해시를 받고 싶다, 그래야 크립토를 직접 구현하지 않는다.
11. Tenant 백엔드로서, 받은 해시가 visitor_id당 안정값이라 유저당 1회 계산해 캐시하고 싶다.
12. 악의적 Visitor로서, 신원검증이 켜진 Tenant에서 해시 없이 `?visitor_id=남의id`로 접속하면 거부되길(시스템 관점) 기대한다.
13. Visitor로서, 신원검증이 꺼진 Tenant에선 평문 visitor_id로 즉시 대화가 시작되길 바란다.
14. Operator로서, EmbedToken 발급 엔드포인트·TTL·검증 코드가 깔끔히 제거되어 유지보수 표면이 줄길 바란다.
15. Operator로서, TENANT_KEY가 폐지되지 않고 HMAC API 인증 + TenantAgent 생성 용도로 유지되길 바란다.
16. Visitor로서, 챗봇이 더 이상 VisitorContext에 의존하지 않아도 정상 동작하길 바란다.
17. Operator로서, 공개 URL을 악용해 한 Tenant의 LLM 비용을 고갈시키려는 스팸이 레이트리밋으로 차단되길 바란다.
18. Tenant로서, 동일 Visitor가 분당 과도한 메시지를 보내면 제한되길 바란다.
19. Operator로서, `admin`·`api`·`chatbot` 같은 예약어가 slug로 등록되어 라우트와 충돌하는 일이 없길 바란다.
20. Visitor로서, 위젯이 slug를 URL 경로에서 읽어 올바른 Tenant에 연결되길 바란다.
21. Tenant로서, 기존 `?token=` 방식이 완전히 사라지고 혼동 없이 단일 방식만 남길 바란다.
22. Operator로서, `ChatSession.visitor_context` 컬럼과 프롬프트의 "## Visitor Context" 주입이 제거되길 바란다.

## Implementation Decisions

- **Tenant Slug**: `Tenant`에 표시명과 분리된 고유·URL-safe slug 필드 추가. 형식 제약(소문자 영숫자+하이픈), 전역 unique, 예약어 차단. Tenant가 어드민에서 설정·변경(변경 시 경고). slug→Tenant 해석은 `/chatbot/{slug}/` 라우트와 stream/message 경로에서 사용.
- **IdentityVerification deep module**: `HMAC(tenant secret, visitor_id)` 계산·검증을 순수 함수로 캡슐화. tenant secret은 TENANT_KEY 파생. Operator 백엔드가 이 모듈로 해시를 발급하는 API(TENANT_KEY 인증)와 stream 연결 시 검증을 둘 다 제공. 해시는 무상태·무기한.
- **Identity Verification 토글**: `TenantConfig`에 신원검증 요구 불리언. ON이면 stream 연결 시 유효 hash 없는 visitor_id를 거부(또는 익명 격리). OFF가 기본.
- **Visitor 연결 리졸버**: stream 연결이 `slug`(경로) + `visitor_id`(+`hash`)를 받아 Tenant 조회 → (토글 시 hash 검증) → `get_or_create ChatSession(tenant, visitor_id)`. visitor_id 미제공 시 위젯이 생성한 Anonymous Visitor ID 사용. 출처(Tenant 제공/위젯 생성) 무관하게 동일 처리.
- **ChatRateLimiter deep module**: Redis 기반 (tenant, visitor_id)당 + per-tenant 롤링 레이트리밋. 초과 시 메시지 처리 거부. 공개 URL 남용·비용 고갈 가드(하드 예산 캡은 C 범위).
- **EmbedToken clean cut**: `create/verify_embed_token`, 발급 엔드포인트, TTL 설정, 위젯 `?token=` 분기 전부 제거. dual-support 없음(운영 트래픽 없음).
- **VisitorContext 폐지**: `ChatSession.visitor_context` 컬럼 드롭 migration + 프롬프트 조립의 "## Visitor Context" 블록 제거 + 토큰 payload 제거.
- **위젯 변경**: slug를 URL 경로에서 읽음. `?visitor_id=`/`hash` 쿼리 파싱. visitor_id 없으면 localStorage에서 Anonymous Visitor ID를 읽거나 생성·저장. stream/message 호출을 새 계약으로.
- **stream/message 계약**: `/api/chat/stream`이 `?token=` 대신 slug+visitor_id(+hash). message POST는 기존대로 session_id.
- **TENANT_KEY 유지**: 용도가 EmbedToken 발급 → HMAC API 인증으로 변경(+ TenantAgent 생성 유지).

## Testing Decisions

좋은 테스트는 공개 인터페이스로 외부 행위만 검증한다. CLAUDE.md 원칙: 실제 객체(Redis·DB·SSE 실물), LLM 경계만 Fake, 테스트 독립. 최대 커버리지 — deep module + 연결 경로 통합 테스트.

- **IdentityVerification** [순수·결정적 단위]: 같은 (secret, visitor_id) → 동일 해시(멱등), 위조 해시 거부, 다른 tenant secret → 다른 해시.
- **Tenant Slug 검증** [순수·결정적 단위]: 형식 위반 거부, 예약어 거부, 전역 unique 충돌 거부, 표시명과 독립.
- **ChatRateLimiter** [Redis 실물 결정적]: 한도 내 허용 → 초과 거부 → 윈도우 경과 후 재허용, (tenant,visitor) 격리, per-tenant 상한.
- **연결 리졸버 통합**: slug+visitor_id로 stream 연결 → 올바른 Tenant의 ChatSession 생성. 신원검증 ON에서 유효 hash → 허용, 무효/누락 → 거부. 익명(visitor_id 없음) → Anonymous Visitor ID로 세션, 재연결 시 동일 세션.
- **HMAC API 통합**: TENANT_KEY 인증으로 해시 요청 → 그 해시가 stream 검증을 통과.
- **clean cut 회귀**: EmbedToken 엔드포인트·`?token=` 경로 제거 확인. is_hitl 차단 등 기존 chat 동작 회귀 유지.
- **VisitorContext 제거 회귀**: 프롬프트 조립에 Visitor Context 블록이 없고, visitor_context 없이 chat이 정상 동작.
- Prior art: `tests/test_chat_session.py`(embed token→stream→message), `tests/test_session_lock.py`(Redis deep module), `tests/conftest.py`(redis_subscribe, fake_chat_llm).

## Out of Scope

- 하드 비용 쿼터/예산 캡(기능 C).
- 플로팅 버블 `<script>` 로더(raw iframe만; 별도 enhancement).
- 식별 사용자에 대한 추가 인증(SSO 등) — HMAC 신원검증까지만.
- 기존 토큰 URL의 점진 마이그레이션(운영 트래픽 없어 clean cut).

## Further Notes

- VisitorContext 폐지는 비신뢰 입력 채널을 줄여 프롬프트 인젝션 표면(기능 D)도 축소한다.
- 첫 메시지 개인화 상실은 Visitor Memory(대화 중 축적)로 대체된다.
- 레이트리밋은 C(Tenant 부담 LLM)에서 Tenant 키를 공개 URL 남용으로부터 보호하는 역할로 이어진다.
