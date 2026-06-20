# PRD: admin 리디자인 — 사이드바 셸 + 중첩 URL 라우트 + Tailwind/shadcn

Status: ready-for-agent

관련 ADR: [ADR-0017](../../docs/adr/0017-admin-stay-react-tailwind-shadcn-nested-routes.md) (본 결정) · [ADR-0013](../../docs/adr/0013-admin-access-refresh-token-auth.md) (auth 보존) · [ADR-0014](../../docs/adr/0014-admin-orval-openapi-codegen.md) (orval 클라이언트 보존)

## Problem Statement
admin은 기능은 다 있지만 룩이 투박하다 — 수평 탭 버튼 + 인라인 스타일이고, **섹션이 URL이 아니라 상태 기반**이라 새로고침하면 항상 첫 탭으로 돌아가고 특정 방문자/세션/상담을 **북마크·공유할 수 없다**. 운영자는 OpenAI/Claude developer platform 같은 **좌측 사이드바 + 깔끔한 디자인 시스템 + 자원별 URL**을 원한다.

## Solution
프레임워크는 React+Vite로 두고(ADR-0017), 룩과 라우팅만 바꾼다: **공유 사이드바 셸**(Operator/Tenant 공통) + **react-router 중첩 URL 라우트**(자원까지 주소화) + **Tailwind/shadcn 디자인 시스템**(라이트 기본 + 다크 토글). **점진적**으로 — 셸+라우팅을 먼저 깔고, 섹션을 하나씩 shadcn으로 리스타일한다(로직·동작 보존). auth(ADR-0013)와 orval 클라이언트(ADR-0014)는 건드리지 않는다.

## User Stories
1. As an operator, I want a persistent left sidebar to navigate sections, so that I always see where I am and switch quickly.
2. As an operator, I want each section to have its own URL, so that I can bookmark and deep-link to it.
3. As an operator, I want a specific visitor/session/escalation to be a shareable URL, so that I can send a teammate a direct link.
4. As an operator, I want refreshing the page to keep me on the current section (not reset to the first tab), so that my place isn't lost.
5. As an operator, I want browser back/forward to move between sections and detail views, so that navigation feels native.
6. As an operator, I want a clean, consistent design system (typography, spacing, cards, buttons), so that the admin looks like a modern dev platform.
7. As an operator, I want a light theme by default with an optional dark mode, so that I can work comfortably.
8. As an operator, I want forms (config, create tenant/agent) to use consistent inputs/selects/buttons, so that interactions are predictable.
9. As an operator, I want tables (tenants, visitors, memory) to be consistently styled with clear status badges, so that scanning is easy.
10. As an operator, I want dialogs/confirmations (delete, reset key) to be accessible (keyboard, focus), so that destructive actions are safe.
11. As an operator on the Tenant dashboard, I want sections (Documents, KnowledgeGraph, Visitors, Config, Agents, HITL) as sidebar items with URLs, so that each is addressable.
12. As an operator viewing Visitors, I want selecting a visitor to update the URL, so that I can refresh/share that visitor's view.
13. As an operator, I want a session's conversation detail to be its own URL, so that I can deep-link to a transcript.
14. As an operator handling HITL, I want an escalation conversation to be addressable, so that I can return to it directly.
15. As an operator on the Operator dashboard, I want the same sidebar shell (minimal nav: Tenants), so that the two dashboards feel consistent.
16. As an operator, I want the knowledge graph view to keep working inside the new layout, so that the redesign doesn't regress that feature.
17. As an operator, I want all existing behaviors (login/logout/logout-all, config save with provider validation, model fetch, document upload, HITL claim/resolve, memory edit) unchanged, so that the redesign is non-regressive.
18. As a developer, I want the redesign done as incremental, deployable slices, so that each ships safely and review stays small.
19. As a developer, I want auth (access/refresh, mutator) and the orval client untouched, so that the redesign stays in the presentation/routing layer.
20. As a developer, I want component tests to keep asserting behavior through roles/labels, so that restyling doesn't churn the test suite.
21. As a developer, I want e2e specs updated to the new sidebar/URL navigation, so that the e2e suite stays green.

## Implementation Decisions
- **프레임워크 유지(ADR-0017)**: React+Vite+react-router. Next.js 기각.
- **디자인 시스템**: Tailwind + shadcn/ui(Radix). 셋업 = Tailwind config/postcss + shadcn `components.json` + `cn` util + CSS 변수(light/dark 두 벌) + ThemeProvider/토글. 컴포넌트는 복붙·소유. 인라인 `styles.ts`는 섹션 마이그레이션마다 점진 제거.
- **셸 모듈(deep)**: `DashboardLayout` — 사이드바(브랜드 + 라우트 매핑 내비 + active 하이라이트) + 상단 바(계정/로그아웃/로그아웃-올) + `<Outlet/>`. **nav 항목 설정을 prop으로 받아** Operator/Tenant가 같은 셸을 공유한다.
- **라우팅 재구성**: 상태 탭 → 중첩 라우트. 기본 리다이렉트(`/tenant`→`/tenant/documents`, `/operator`→`/operator/tenants`). **자원 라우트**: `/tenant/visitors/:visitorId`, `/tenant/sessions/:sessionId`, `/tenant/hitl/:escalationId`. 지식그래프 노드는 `?entity=` 쿼리. Visitors/HITL의 상태 드릴다운을 `useParams`/`useNavigate`로 옮긴다.
- **딥링크 안전성**: nginx `try_files … /index.html` 폴백이 이미 존재(추가 작업 없음).
- **테마**: 라이트 기본 + 다크 토글(CSS 변수). 지금은 라이트를 다듬고 다크 토큰만 잡아둬도 됨.
- **보존**: auth(ADR-0013 mutator/auth.ts), orval 생성 클라이언트(ADR-0014), `react-force-graph-2d` 그래프 뷰(카드로 감싸기만), docker `vite build`·nginx 서빙.
- **점진 슬라이스**: ① 셸+라우팅+디자인시스템 셋업 → ② Config → ③ Documents → ④ Visitors/Session(자원 라우트) → ⑤ HITL(escalation 라우트) → ⑥ KnowledgeGraph → ⑦ Operator → ⑧ Agents → ⑨ e2e/테스트 정리. 과도기 혼합 룩 허용.

## Testing Decisions
- **무엇이 좋은 테스트인가**: 외부 행위(role/label로 쿼리, 호출 payload, 라우팅 결과)를 본다. 스타일/클래스가 아니라 **동작**을 단언 — 리스타일에도 생존한다.
- **라우팅 테스트**: 딥링크(`/tenant/config`가 Config를 렌더, `/tenant/visitors/:id`가 그 방문자를, `/tenant/sessions/:id`가 그 세션을), 리다이렉트(`/tenant`→documents), 사이드바 active 상태. `MemoryRouter`/라우터 래퍼로 결정적으로.
- **기존 컴포넌트 테스트 보존**: ConfigTab 등은 role/label 기반이라 대부분 그대로. router 훅을 쓰게 되면 테스트에 라우터 래퍼만 추가.
- **e2e 갱신**: 탭 버튼 클릭 → 사이드바 링크/URL 네비게이션으로 셀렉터 갱신(슬라이스별).
- **Prior art**: `ConfigTab.test.tsx`(vitest + 생성 모듈 mock), 기존 admin vitest, `e2e/` Playwright 스펙.

## Out of Scope
- **백엔드/API 변경**: 없음. orval 스키마 불변 → 재생성 불필요.
- **auth 로직 변경**(ADR-0013): 없음 — 표현/라우팅만.
- **지식그래프 캔버스 재작성**: 안 함(레이아웃에만 통합).
- **기능 추가**: 새 admin 기능 없음. 순수 리디자인 + URL 라우팅.
- **Next.js / SSR**: 기각(ADR-0017).

## Further Notes
- 동기: 섹션이 상태 기반이라 새로고침 시 첫 탭으로 리셋되고 자원 공유가 불가(VisitorsTab의 `selectedVisitor`/`selectedSession` 상태 드릴다운이 대표 사례).
- 과도기엔 새 셸 + 일부 옛 스타일 섹션이 섞인다(내부 admin이라 허용). 슬라이스가 진행될수록 옛 `styles.ts` 의존이 줄어든다.
