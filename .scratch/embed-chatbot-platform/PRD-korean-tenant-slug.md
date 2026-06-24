# PRD — 한글 Tenant Slug (공개 챗봇 URL)

Status: ready-for-agent

## Problem Statement

한국 사업자가 공개 챗봇 URL(`/chatbot/{slug}/`)에 자기 브랜드명을 한글로 쓰고 싶다. 그러나 현재
slug 검증(`apps/tenants/slug.py`)은 `[a-z0-9](-?[a-z0-9])*` — ASCII 소문자·숫자·하이픈만 허용해
`/chatbot/우리가게/` 같은 한글 slug를 만들 수 없다. 운영자가 한글 slug를 저장하려 하면 400(Invalid
slug format)이 난다.

## Solution

slug에 **완성형 한글**을 허용한다. URL path에 한글을 그대로 두되(`/chatbot/우리가게/`, 실제 HTTP는
percent-encoded), 안전을 위해 **NFC 정규화**(macOS 자모분리 NFD ↔ 완성형 NFC 불일치로 인한 조회 실패
방지)와 **대소문자 무시 조회/중복검사**(원형은 보존, 비교는 lower)를 함께 도입한다. 영한 혼합·대문자도
허용한다(`서울cafe`, `MyStore`). 자모 단독·한자·이모지·특수문자는 거부한다.

## User Stories

1. 테넌트 운영자로서 한글 brand slug(`우리가게`)를 등록하고 싶다, 공개 챗봇 URL이 한글로 보이도록.
2. 테넌트 운영자로서 영한 혼합 slug(`서울cafe`, `store-강남`)를 등록하고 싶다, 자유롭게 브랜딩하도록.
3. 테넌트 운영자로서 대문자를 포함한 slug(`MyStore`)를 입력하면 그 표기 그대로 저장·표시되길 원한다.
4. 방문자로서 `/chatbot/mystore/`로 접근해도 `MyStore`로 등록된 챗봇이 열리길 원한다(대소문자 무시).
5. macOS 운영자로서 자모분리(NFD)된 한글을 붙여넣어도 완성형(NFC)으로 저장되어 조회가 깨지지 않길 원한다.
6. 플랫폼 운영자로서 `Store`가 이미 있으면 `store` 중복 등록이 거부되길 원한다(대소문자 무시 유일성).
7. 플랫폼 운영자로서 예약어를 대문자로 우회한 `Admin`·`API`도 거부되길 원한다.
8. 방문자로서 한글 URL(`/chatbot/우리가게/`, percent-encoded)로 위젯 챗봇에 정상 접속하고 싶다.
9. 기존 테넌트로서 이미 쓰던 ASCII slug(`acme`)가 그대로 동작하길 원한다(하위호환).
10. 플랫폼 운영자로서 자모 단독(`ㄱㄴㄷ`)·한자(`商店`)·이모지(`가게😀`)·특수문자(`가@게`)·연속/선행/후행
    하이픈 slug가 거부되길 원한다.
11. 테넌트 운영자로서 admin 설정 화면에서 "한글도 가능"하다는 안내를 보고 싶다.
12. 테넌트 운영자로서 빈 slug나 63자 초과 slug가 거부되길 원한다.

## Implementation Decisions

- **`slug.py` deep module 확장** (순수 함수, 외부 의존 없음):
  - 검증 정규식을 완성형 한글 + 라틴 대소문자 + 숫자 + 하이픈으로: 대략
    `[가-힣A-Za-z0-9](-?[가-힣A-Za-z0-9])*` (선행/후행/연속 하이픈 금지 유지).
  - `normalize_slug(raw) -> str`: **NFC 정규화 + 앞뒤 공백 trim**. 대소문자는 보존(소문자화 안 함).
  - `slug_key(slug) -> str`: 비교용 키 = `casefold()`(또는 lower). 조회·중복·예약어 비교에 사용.
  - `is_valid_slug`는 normalize된 입력 기준으로 형식·길이(≤63)·예약어(slug_key 비교)를 검사.
  - `RESERVED_SLUGS`는 그대로 두되 비교는 slug_key로(대문자 우회 차단).
- **`update_slug` API**: 입력을 `normalize_slug`로 보정 → `is_valid_slug` 검증 → 중복검사를
  `slug__iexact`(또는 slug_key 동등)로 → **원형(NFC) 저장**.
- **`resolve_slug`(models)**: 입력 slug를 normalize 후 `slug__iexact`로 활성 Tenant 조회.
  (한글엔 대소문자가 없어 iexact는 라틴에만 작동 + NFC는 저장·조회 양쪽 정규화로 일치시킨다.)
- **위젯**(`widget/src/App.tsx`): `pathname`에서 추출한 slug를 `decodeURIComponent` + NFC(`normalize('NFC')`)
  처리해 API에 넘긴다. 추출 정규식 `[^/?#]+`는 한글/encoded 모두 매칭하므로 변경 불필요.
- **대소문자**: 원형 보존 저장(`MyStore`). 표시는 원형, 비교는 case-insensitive.
- **길이**: `max_length=63` 유지(한글 63자). DB·스키마 변경 없음.
- 동시 등록 race(같은 slug_key의 `Store`/`store`)는 드문 작업이라 애플리케이션 중복검사로 충분(전용
  정규화 컬럼/제약은 도입하지 않음 — Out of Scope).

## Testing Decisions

좋은 테스트 = 공개 인터페이스(순수 함수·API·위젯 라우팅)로 외부 동작을 검증하고 구현 세부에 결합하지
않는다. 내부 협력자는 mock하지 않고 실제 객체(DB·검증 함수)를 쓴다.

- **`slug.py` 단위 테스트**(기존 `tests/test_tenant_slug.py` 확장): 한글/영한혼합/대문자 허용,
  자모·한자·이모지·특수문자·하이픈규칙 거부, `normalize_slug`의 NFC+trim, `slug_key` lower,
  예약어 대문자 우회 거부, 길이 경계.
- **API 통합 테스트**(실제 DB): 한글 slug 등록 → `MyStore`를 `mystore`로 `resolve_slug` 조회 성공,
  `Store` 존재 시 `store` 중복 등록 400, NFD 입력이 NFC로 저장.
- **위젯 테스트**(vitest): percent-encoded 한글 pathname에서 slug를 decode+NFC로 추출.
- prior art: `tests/test_tenant_slug.py`, `tests/test_tenants.py`(slug 엔드포인트), `widget` App 테스트.

## Out of Scope

- 자모 단독(`ㄱ`), 한자, 일본어 가나, 이모지, 기타 유니코드 문자.
- punycode/IDN(도메인이 아니라 path라 불필요).
- 한글→로마자 자동 음역 slug 생성.
- 기존 slug 데이터 마이그레이션(하위호환 — 기존 ASCII slug는 그대로).
- 전용 정규화 컬럼 + DB 레벨 case-insensitive unique 제약(동시 등록 race 강제). 드문 작업이라 보류.

## Further Notes

- percent-encoded 한글 URL은 길어진다(한글 1자 ≈ `%XX%XX%XX`). 주소창엔 한글로 보이지만 공유·QR엔
  다소 길고 지저분 — path에 한글을 택한 데 따른 감수 사항.
- nginx의 `/chatbot/` → 위젯 SPA fallback 라우팅은 변경 없음(slug는 클라이언트가 pathname에서 파싱).
- 부모/선행: [PRD-public-slug-access.md](./PRD-public-slug-access.md).
