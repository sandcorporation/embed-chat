# ADR-0017: admin은 React+Vite 유지, Tailwind+shadcn/ui + 중첩 URL 라우트로 리디자인 (Next.js 기각)

## Status
Accepted (구현은 후속 — issues 122~)

## Context
admin을 OpenAI/Claude developer platform 같은 룩(좌측 사이드바 + 깔끔한 콘텐츠 + 자원별 URL)으로 리디자인하려 한다. 초기 제안은 **프레임워크를 Next.js로 교체**하는 것이었다.

현 admin은 **Vite + React 18 + react-router-dom 6**다(ADR-0014로 전체 TS). 최상위는 이미 URL 라우팅(`/operator`·`/tenant`)이지만 **섹션(탭)은 상태 기반**(`useState`)이라 북마크·딥링크가 안 된다. 정적 dist를 `admin-init`→volume→nginx가 서빙하고, HTTP는 orval 생성 클라이언트 + access/refresh auth(ADR-0013/0014), 위젯엔 SSE 스트림이 있다.

## Decision
**프레임워크는 React+Vite로 유지하고, 리디자인은 (1) Tailwind+shadcn/ui 디자인 시스템, (2) react-router 중첩 URL 라우트, (3) 공유 사이드바 셸로 한다.**

- **프레임워크 유지(Next.js 기각)**: "OpenAI/Claude 룩"은 프레임워크가 아니라 레이아웃+디자인 시스템 문제다. 이 admin은 Django 백엔드와 통신하는 **인증 게이트된 내부 대시보드 + SSE**라 Next의 간판 기능(SSR/RSC/API routes/이미지 최적화)이 불필요하다.
- **URL 라우팅 = react-router 중첩 라우트**: 상태 탭을 중첩 라우트로 교체한다. **자원까지 주소화**한다(`/tenant/visitors/:visitorId`, `/tenant/sessions/:sessionId`, `/tenant/hitl/:escalationId`; 지식그래프 노드는 `?entity=` 쿼리). nginx의 `try_files … /index.html` 폴백이 이미 있어 딥링크 새로고침이 안전하다.
- **디자인 시스템 = Tailwind + shadcn/ui(Radix)**: dev-platform 룩을 가장 적은 노력으로. 컴포넌트를 복붙·소유(lock-in 없음), Radix로 접근성 확보. 인라인 `styles.ts`를 점진 대체.
- **공유 셸**: `DashboardLayout`(사이드바 + 상단바 + `<Outlet/>`)을 Operator/Tenant 공통으로. 사이드바 항목이 중첩 라우트에 매핑된다.
- **테마**: 라이트 기본 + 다크 토글(CSS 변수 light/dark 두 벌).
- **점진적 마이그레이션**: 셸+라우팅 슬라이스 먼저, 섹션을 하나씩 shadcn화(로직·동작 보존). 과도기엔 새 셸 + 일부 옛 스타일 섹션 혼합을 허용한다.

## Considered Options
- **Next.js로 교체**: 기각. 이득(SSR/RSC/파일라우팅) 0 — 정적 서빙·orval·auth·SSE 모델과 상충하며 ADR-0013/0014·docker·nginx·e2e를 전부 재작업해야 한다. `next export` 정적화는 Next 이점 대부분을 잃으면서 비용만 남긴다.
- **react-router 없이 상태 탭 유지**: 기각. "URL 라우팅"(북마크·딥링크·자원 공유)이 핵심 요구.
- **인라인 styles.ts 확장(디자인 시스템 없이)**: 기각. 폴리시된 dev-platform 룩을 손으로 만드는 건 노동집약적·비일관적.
- **Tailwind만(shadcn 없이)**: 채택 가능하나 기각. 메뉴/다이얼로그/접근성을 직접 챙겨야 함; shadcn이 그 룩에 더 빨리 도달.
- **big-bang 리라이트**: 기각. 거대 PR·고위험·리뷰 난망. 점진 슬라이스가 이 레포 워크플로우와 정합.

## Consequences
- **새 도구체인**: Tailwind(config/postcss) + shadcn(components.json, `cn` util, CSS 변수, ThemeProvider/토글). docker admin 빌드(`vite build`)는 그대로 동작.
- **라우팅 재구성**: `App.tsx` 중첩 라우트 + `DashboardLayout` + 섹션 라우트. 상태 탭 드릴다운(Visitors→Session, HITL→대화)이 param 라우트로 이동.
- **테스트 영향**: 라우터 훅(useParams/useNavigate)을 쓰는 컴포넌트 테스트에 `MemoryRouter` 래퍼 필요(동작 단언은 role/label 기반이라 대부분 생존). **e2e 셀렉터를 탭 버튼 → 사이드바 링크/URL로 갱신.**
- **ADR-0013/0014 보존**: auth(mutator/auth.ts)·orval 생성 클라이언트는 그대로. 리디자인은 프레젠테이션/라우팅 계층만 건드린다.
- **과도기 혼합 룩**: 마이그레이션 동안 새 셸 + 일부 옛 스타일 섹션 공존(내부 admin이라 허용).
