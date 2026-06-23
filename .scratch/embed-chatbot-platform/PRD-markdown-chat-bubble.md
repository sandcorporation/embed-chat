# PRD — 마크다운 챗버블 렌더링

Status: ready-for-agent

## Problem Statement

AI가 가끔 마크다운으로 답한다(굵게·리스트·코드블록·표·링크). 그런데 위젯·admin의 챗버블은
지금 평문(`{content}` + `whitespace-pre-wrap`)으로 렌더해, `**굵게**`·`- 항목`·```` ``` ````가
그대로 raw 기호로 보인다. 방문자·상담원이 서식 없는 날 마크다운을 읽게 된다.

## Solution

AI(assistant) 메시지를 **마크다운으로 렌더**한다. 위젯의 스트리밍 버블도 토큰 델타마다 라이브로
마크다운 렌더해(닫히는 순간 서식으로 스냅) ChatGPT/Claude식 UX를 준다. 방문자 입력(`user`)·상담원
(`human_agent`)·시스템 안내는 평문 그대로 둔다(인젝션·혼란 방지). 위젯·admin 모두 react-markdown을
쓰되 패키지별 스타일 시스템(위젯 CSS-in-JS / admin Tailwind)에 맞춘 얇은 래퍼로 감싼다.

## User Stories

1. As a 방문자, I want AI의 굵게·기울임이 서식으로 보이기, so that 강조를 raw `**` 없이 읽는다.
2. As a 방문자, I want AI의 글머리·번호 리스트가 들여쓰기되어 보이기, so that 단계·항목을 또렷이 구분한다.
3. As a 방문자, I want AI의 코드블록이 monospace 배경 박스로 보이기, so that 명령어·설정을 그대로 복사·구분한다.
4. As a 방문자, I want AI가 준 링크가 클릭 가능하기, so that 안내 URL로 바로 이동한다.
5. As a 방문자, I want 링크가 새 탭에서 안전하게 열리기, so that 현재 챗 세션을 잃지 않고 보안 위험도 없다.
6. As a 방문자, I want AI의 비교 표가 깨지지 않고 보이기(좁으면 가로 스크롤), so that 좁은 버블에서도 표를 읽는다.
7. As a 방문자, I want 스트리밍 중에도 서식이 라이브로 입혀지기, so that 완성될 때까지 raw 기호를 안 본다.
8. As a 방문자, I want 내가 친 메시지는 평문 그대로이기, so that 내 `**`·URL이 임의로 서식·링크로 둔갑하지 않는다.
9. As a 상담원, I want admin 세션 콘솔의 AI 메시지도 서식으로 보이기, so that 방문자가 본 것과 같게 본다.
10. As a 운영자, I want AI 출력의 raw HTML·스크립트가 실행되지 않기, so that 프롬프트 인젝션이 위젯에서 XSS로 번지지 않는다.
11. As a 운영자, I want 이미지 마크다운이 렌더되지 않기, so that 외부 이미지 로드·트래킹·레이아웃 깨짐을 막는다.
12. As a 운영자, I want `javascript:`·`data:` 링크가 차단되기, so that 악성 링크 클릭 위험을 없앤다.
13. As a 방문자, I want 헤딩(`##`)이 버블에 맞게 적당한 크기로 보이기, so that h1이 버블을 뒤덮지 않는다.
14. As a 방문자, I want 인라인 코드(`` `code` ``)가 강조되어 보이기, so that 본문 속 식별자를 구분한다.
15. As a 방문자, I want 인용(`>`)·취소선(`~~`)·맨URL 자동링크가 자연스럽게 보이기, so that AI 출력을 충실히 읽는다.
16. As a developer, I want 위젯·admin이 같은 마크다운 설정(gfm·이미지off·링크정책)을 쓰기, so that 두 화면의 렌더가 일관된다.

## Implementation Decisions

- **라이브 렌더(스트리밍 복귀 반영)**: 위젯의 스트리밍 버블·커밋 메시지 모두 **같은 마크다운 렌더러**로 렌더. 토큰 델타마다 react-markdown 재렌더 — 미완성 구문(`**굵게`, 열린 코드펜스, 반쪽 링크)은 리터럴로 보이다 닫히면 서식으로 스냅(react-markdown은 부분 입력에 안 깨짐). done에 모드 전환하는 플래시 방식은 안 씀.
- **렌더러 = react-markdown 양쪽(위젯+admin)**: `dangerouslySetInnerHTML` 없이 raw HTML을 기본 차단해, 3자 사이트 iframe에서 AI 출력을 렌더하는 위젯의 안전성을 확보. 위젯 번들 ~+40KB gzip 감수.
- **GFM 켬 + 테이블 스크롤**: remark-gfm(취소선·태스크리스트·자동링크·테이블). 테이블은 좁은 버블에서 깨지지 않게 `overflow-x:auto` 컨테이너로 감싼다.
- **적용 대상 = `role === 'assistant'`만**: AI 응답 + tenant welcome_message(assistant). `user`(방문자)·`human_agent`(상담원)·시스템 안내는 평문 유지.
- **안전 정책(공통 설정)**:
  - raw HTML off(react-markdown 기본 — `rehype-raw` 안 씀).
  - 이미지 비활성: `img` 요소를 렌더하지 않음(컴포넌트 매핑에서 제거/무시).
  - 링크: `target="_blank"` + `rel="noopener noreferrer nofollow"`, 허용 프로토콜 **http/https/mailto만**(`javascript:`·`data:` 차단 — urlTransform/필터).
  - 인라인·블록 코드 허용.
- **패키지별 얇은 래퍼(공유 npm 패키지 없음)**: 위젯(JSX/vite)·admin(TSX/Tailwind)은 빌드·스타일 시스템이 달라 각자 `Markdown`(또는 `MessageContent`) 컴포넌트를 둔다. react-markdown **공통 설정**(gfm·이미지off·링크정책·urlTransform)만 동일하게 맞춘다.
  - **위젯 스타일**: `components` prop으로 각 요소를 **인라인 `style`** 컴포넌트에 매핑(현 CSS-in-JS와 일관, 추가 의존 0). 버블용 컴팩트 마진(첫/막 자식 margin 0)·헤딩 크기 캡·코드블록 monospace+배경+`overflow-x`·테이블 스크롤·링크 색·리스트 들여쓰기.
  - **admin 스타일**: `components`를 **Tailwind 유틸 클래스**에 매핑(`@tailwindcss/typography` 플러그인 도입 없이 themed·컴팩트 버블 정밀 제어). assistant 버블에만 적용, `user`는 기존 평문.

## Testing Decisions

- 좋은 테스트는 **외부 동작**(렌더 결과)을 본다 — DOM에 굵게·리스트·링크가 났는지, 링크에 `target`/`rel`이 붙었는지, `img`가 없는지, 스크립트가 실행 안 되는지. react-markdown 내부 구현은 보지 않는다.
- 프론트 테스트는 Docker node 컨테이너의 vitest(jsdom)로 — 백엔드 인프라 불필요(`--no-deps`).
- **위젯(vitest)**: ① `Markdown` 컴포넌트가 `**굵게**`→`<strong>`, `- a`→`<li>`, ```` ```code``` ````→`<pre><code>`, `[t](https://x)`→`<a target=_blank rel=...>` 렌더. ② `![](url)` 이미지 미렌더, `javascript:` 링크 차단, raw `<script>` 미실행. ③ 테이블이 스크롤 컨테이너로 감싸짐. ④ ChatWidget: assistant 버블은 마크다운, `user` 버블은 평문(`**`가 그대로). ⑤ 스트리밍: 부분 마크다운 토큰 누적 시 라이브 렌더(닫히면 서식).
- **admin(vitest)**: ChatHistory가 assistant 메시지를 마크다운으로, `user`를 평문으로 렌더 + 링크 정책 동일.
- prior art: 위젯 `ChatWidget.test.jsx`(토큰/done 핸들링), admin 컴포넌트 vitest, jsdom+fetch mock 패턴.

## Out of Scope

- 백엔드 변경 없음 — AI는 이미 마크다운을 낼 수 있고, 저장/전송은 그대로(원문 마크다운 텍스트).
- 마크다운 **작성** UI(상담원 입력 툴바 등) — 렌더만, 입력은 평문.
- `user`·`human_agent`·시스템 메시지 마크다운 — 필요해지면 후속(현재 평문).
- 수식(KaTeX)·다이어그램(mermaid)·syntax highlighting — 코드블록은 monospace 박스까지만(하이라이트 없음).
- 이미지 렌더(보안상 비활성) — 후속에서 허용리스트 도메인만 켜는 식 검토 가능.

## Further Notes

- 스트리밍(PRD-chat-token-streaming)이 켜진 뒤 부분 마크다운이 관건이 됐고, 라이브 렌더(A)로 해소.
- 위젯 번들이 늘므로(+react-markdown/remark-gfm) 빌드 크기 회귀를 한 번 확인.
- 관련: ADR-0001(SSE 스트리밍), 위젯 `role` 모델(assistant/user/human_agent + hitl 안내).
