# PRD: 설정 탭을 세부 탭으로 분류 + 비개발자용 친절 설명

Status: ready-for-agent

관련 ADR: [ADR-0017](../../docs/adr/0017-admin-stay-react-tailwind-shadcn-nested-routes.md) (admin 리디자인 — 본 작업은 그 안의 Config 섹션 개선) · [ADR-0012](../../docs/adr/0012-per-tenant-llm-embedding-providers.md) (Provider 설정)

## Problem Statement
어드민 **설정 섹션**(`/tenant/config`)은 Slug·환영 메시지·시스템 프롬프트·HITL·신원검증·LLM Provider·Embedding Provider·API KEY 재발급이 **하나의 긴 폼**으로 쭉 나열돼 있다. 비개발자 테넌트에겐 (1) 스크롤이 길고 어디에 뭐가 있는지 찾기 어렵고, (2) "Provider", "Embedding", "시스템 프롬프트", "API Key" 같은 **기술 용어에 설명이 거의 없어** 무엇을 입력해야 할지 막막하다.

## Solution
설정을 **세부 탭 4개**(일반 · AI 모델 · 상담 전환(HITL) · 공개 URL·보안)로 그룹핑하고, **각 항목에 평이한 한국어 설명**(무엇인지 + 모르면 어떻게 하는지)을 붙인다. 설정은 통째로 저장돼야 하므로 **단일 폼 + 항상 보이는 "저장" 버튼으로 atomic 저장**을 유지하고(탭을 오가도 입력값 보존), 활성 세부 탭을 `?section=` 쿼리로 동기화해 북마크·딥링크를 지원한다(ADR-0017 일관). 백엔드·저장 계약은 불변.

## User Stories
1. As a non-technical TenantAgent, I want the settings split into clearly named sub-tabs, so that I can find a setting without scrolling a long form.
2. As a non-technical TenantAgent, I want a one-line plain-language description for each technical field, so that I understand what to enter without asking a developer.
3. As a TenantAgent, I want the "AI 모델" sub-tab to explain Provider/API Key/Embedding in plain terms, so that the most technical settings are the most guided.
4. As a TenantAgent, I want a single "저장" button that saves everything across sub-tabs, so that I don't have to save each tab separately or lose unsaved changes when switching tabs.
5. As a TenantAgent, I want my edits preserved when I switch sub-tabs before saving, so that organizing into tabs doesn't lose work.
6. As a TenantAgent, I want the active sub-tab reflected in the URL (`?section=`), so that I can bookmark/share a specific settings sub-tab and a refresh keeps my place.
7. As a TenantAgent, I want a short intro line per sub-tab, so that I know what that group is for.
8. As a TenantAgent, I want the "일반" sub-tab to hold brand text, welcome message, system prompt, agent display name, so that the bot's voice/appearance is in one place.
9. As a TenantAgent, I want the "상담 전환(HITL)" sub-tab to hold the HITL toggle and webhook, so that human-handoff settings are grouped.
10. As a TenantAgent, I want the "공개 URL·보안" sub-tab to hold Tenant Slug, identity verification, and API KEY reset, so that access/security settings are grouped.
11. As a TenantAgent, I want all existing behaviors (provider validation on save, model fetch, base_url custom-only, advanced extraction model, slug save, key reset) unchanged, so that the reorganization is non-regressive.
12. As a developer, I want the sub-tabs implemented inside the single ConfigTab form (not separate routes), so that the atomic save and shared form state are preserved.
13. As a developer, I want the existing ConfigTab tests updated to navigate to the right sub-tab before interacting, so that behavior coverage survives the reorganization.

## Implementation Decisions
- **세부 탭 구성(4)**:
  - **일반** — 브랜드 텍스트, 환영 메시지, Base System Prompt, 상담원 표시 이름.
  - **AI 모델** — LLM Provider(타입·Base URL(custom)·API Key·모델 불러오기·AI 모델·고급 설정/자료 정리 모델) + Embedding Provider(타입·Base URL(custom)·API Key·모델·차원).
  - **상담 전환(HITL)** — HITL 사용 토글, 웹훅 유형·URL.
  - **공개 URL · 보안** — Tenant Slug(+Slug 저장), visitor_id 신원검증, API KEY 재발급.
- **단일 폼 + atomic 저장**: ConfigTab은 그대로 하나의 stateful 컴포넌트(`config` 상태 + `updateTenantConfig` 저장)다. 세부 탭은 **컴포넌트 내부 탭 상태**로 활성 탭의 필드만 렌더한다. **"저장" 버튼은 탭과 무관하게 항상 보이며 전체 config를 한 번에 저장**한다(Slug 저장·API KEY 재발급은 각자 별도 액션 유지).
- **`?section=` 동기화**: `useSearchParams`로 활성 세부 탭을 `?section=general|ai|handoff|security`에 반영. 진입 시 쿼리로 초기 탭 결정(없으면 일반). 라우트 분리(nested route)는 하지 않는다 — atomic 폼 보존이 우선.
- **친절 설명**: 각 기술 항목에 1줄 helper text("무엇인지 + 모르면 어떻게"). 예: API Key="AI 서비스에서 발급받은 비밀 키…담당 개발자에게 'OpenAI API 키' 요청", Embedding="문서를 검색 가능한 '숫자 지문'으로 바꾸는 엔진", 시스템 프롬프트="봇의 성격·말투·역할 지시문". 각 세부 탭 상단에 1줄 인트로.
- **보존**: 모든 aria-label·data-testid·저장/조회 동작·provider 검증·base_url custom 게이팅·고급 설정. 백엔드/orval 변경 0.

## Testing Decisions
- **무엇이 좋은 테스트인가**: 외부 행위(필드 조작 → 저장 payload, 세부 탭 전환으로 필드 노출, `?section=` 딥링크)를 본다. 스타일이 아니라 동작·노출을 단언.
- **기존 테스트 갱신**: `ConfigTab.test.tsx`의 각 케이스가 대상 필드를 만지기 전에 **해당 세부 탭으로 이동**(탭 버튼 클릭 또는 `?section=`)하도록 갱신. aria-label은 보존되므로 단언 자체는 유지.
- **신규 테스트**: 기본 탭=일반, 탭 전환 시 해당 필드 노출/비노출, `?section=ai` 진입 시 AI 모델 탭 렌더, 한 탭에서 입력 후 다른 탭으로 갔다가 **저장 시 양쪽 값이 payload에 포함**(atomic·상태 보존), 친절 설명 텍스트 표시.
- **Prior art**: `ConfigTab.test.tsx`(vitest + 생성 모듈 mock), `DashboardLayout.test.tsx`·`VisitorsRouting.test.tsx`(MemoryRouter 라우팅 테스트).

## Out of Scope
- **백엔드/스키마/저장 계약 변경**: 없음. orval 재생성 불필요.
- **세부 탭을 nested route로 분리**: 안 함(atomic 폼 보존 위해 `?section=` 쿼리만).
- **다른 섹션**(Documents·Visitors·HITL·Graph 등) 변경: 없음.
- **Provider/모델 동작 로직 변경**: 없음(배치만 재구성).

## Further Notes
- 동기: 123 슬라이스에서 ConfigTab을 shadcn으로 옮겼지만 여전히 긴 단일 폼이라 비개발자 진입장벽이 남음.
- 친절 설명의 톤은 "기술 용어를 모르는 운영자도 행동할 수 있게"(무엇 + 모르면 누구에게/어떻게).
