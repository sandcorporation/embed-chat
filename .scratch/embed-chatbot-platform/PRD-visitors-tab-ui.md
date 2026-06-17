# PRD: Visitors 탭 — 방문자/세션/Checkpoint 통합 뷰

Status: ready-for-agent

## Problem Statement

Tenant 대시보드의 "Memory" 탭은 Visitor ID를 직접 입력해야만 메모리를 조회할 수 있다.
방문자 목록을 탐색하거나 특정 방문자의 대화 세션을 열람하는 방법이 없다.

특히 다음 세 가지 작업이 현재 불가능하다:

1. **방문자 목록 탐색**: 어떤 방문자가 대화했는지 ID를 미리 알아야만 조회할 수 있다.
2. **세션 대화 내역 확인**: TenantAgent가 특정 대화의 흐름을 사후에 검토할 방법이 없다.
3. **LangGraph Checkpoint 조회**: 개발자/운영자가 LangGraph 내부 상태를 확인하는 뷰가 없다.

백엔드에는 이미 `GET /api/tenant/visitors/`, `GET /api/tenant/visitors/{id}/sessions/`,
`GET /api/tenant/sessions/{id}/messages/`, `GET /api/tenant/sessions/{id}/checkpoint`
엔드포인트가 모두 구현되어 있지만, 어드민 프론트엔드에서 연결되지 않았다.

## Solution

"Memory" 탭을 "Visitors" 탭으로 개편한다.
왼쪽 패널에 방문자 목록을 표시하고, 방문자를 선택하면 오른쪽에 세션 목록과 Memory 편집기를 보여준다.
세션을 선택하면 세션 상세 패널이 열려 대화 메시지와 Checkpoint 원시 상태를 확인할 수 있다.

## User Stories

1. As a TenantAgent, I want to browse a list of all visitors, so that I don't need to know a visitor's ID in advance.
2. As a TenantAgent, I want to search for visitors by ID keyword, so that I can quickly find a specific visitor.
3. As a TenantAgent, I want to see all chat sessions for a selected visitor, so that I can understand their conversation history.
4. As a TenantAgent, I want to know whether a session involved HITL, so that I can prioritize sessions that needed human intervention.
5. As a TenantAgent, I want to click on a session to read the full message history, so that I can review what was discussed.
6. As a TenantAgent, I want to see human_agent messages in the session detail, so that I can evaluate the quality of HITL conversations.
7. As a TenantAgent, I want to view the LangGraph Checkpoint raw state for a session, so that I can debug unexpected AI behavior.
8. As a TenantAgent, I want to see when a Checkpoint is unavailable (no AI calls made), so that I know the session had no LangGraph execution.
9. As a TenantAgent, I want to manage memory entries for a visitor (view/edit/delete), so that I can correct outdated or wrong information.
10. As a TenantAgent, I want to switch between a visitor's sessions and their memory entries, so that I can see both contexts in one place.
11. As a TenantAgent, I want the Visitors tab to load the visitor list automatically, so that I don't have to perform a manual search first.

## Implementation Decisions

### 탭 이름 변경

`TenantDashboard` 에서 `memory` 탭 라벨을 `🧠 Memory`에서 `👤 Visitors`로 변경한다.
`MemoryTab` 컴포넌트는 `VisitorsTab`으로 재작성하되 기존 memory CRUD 기능은 유지한다.

### 레이아웃: 2-패널 구조

**왼쪽 패널 (방문자 목록)**
- 검색 입력 + 방문자 목록
- 항목: `visitor_id` 표시
- 선택 시 오른쪽 패널 갱신

**오른쪽 패널 (방문자 상세)**
- 방문자 미선택 시: "방문자를 선택하세요" placeholder
- 방문자 선택 시: 두 개의 서브 섹션
  - **세션 목록**: created_at, HITL 뱃지 포함 카드 목록. 클릭 시 세션 상세 패널 열림
  - **Memory 편집기**: 기존 MemoryTab의 CRUD 기능 그대로

### 세션 상세 패널

세션 카드를 클릭하면 같은 오른쪽 영역에 세션 상세가 오버레이되거나 교체된다.
세션 상세는 두 개의 sub-tab으로 구성된다:

- **대화 내역**: 메시지를 역할(user / assistant / human_agent)별 말풍선으로 표시. `HitlTab`의 `ChatHistory` 컴포넌트와 동일한 스타일.
- **Checkpoint**: `GET /api/tenant/sessions/{id}/checkpoint` 결과를 JSON pretty-print로 표시. 404이면 "이 세션은 AI 호출 내역이 없습니다." 안내.

"← 뒤로" 버튼으로 세션 목록으로 복귀.

### `api.js` 추가 함수

- `listVisitors(agentToken, search?)` → `GET /api/tenant/visitors/?search=`
- `listVisitorSessions(agentToken, visitorId)` → `GET /api/tenant/visitors/{id}/sessions/`
- `getSessionMessages(agentToken, sessionId)` → `GET /api/tenant/sessions/{id}/messages/`
- `getSessionCheckpoint(agentToken, sessionId)` → `GET /api/tenant/sessions/{id}/checkpoint`

`getSessionCheckpoint`는 404를 에러로 던지지 않고 `null`을 반환한다 (checkpoint 없는 세션 정상 처리).

## Testing Decisions

백엔드 엔드포인트는 `test_visitors.py`, `test_chat_session.py` 등에서 이미 테스트됨.
이번 이슈의 테스트 범위는 `api.js` 함수들 — 즉 각 엔드포인트와의 HTTP 통신이 올바른 URL/파라미터/응답 처리를 하는지 확인하는 통합 테스트.

프론트엔드 컴포넌트 동작(클릭, 상태 전환)은 수동 검증으로 대체한다.

**Prior art**: 기존 `test_visitors.py`에 `GET /api/tenant/visitors/`, `GET /api/tenant/visitors/{id}/sessions/` 테스트가 있음.

## Out of Scope

- 세션 삭제 또는 강제 종료 — 별도 이슈
- Checkpoint를 시각화(그래프, 노드별 분리) — 원시 JSON 표시로 충분
- 페이지네이션 — 방문자/세션 수가 적은 초기 단계

## Further Notes

- `HitlTab`의 `ChatHistory` 컴포넌트는 `VisitorsTab`에서도 재사용 가능하도록 공용 컴포넌트로 추출하거나, 동일한 스타일을 복제하는 방식 중 하나를 선택한다. 추출이 바람직하지만 이 PRD 범위 내에서 결정한다.
- Checkpoint JSON은 `messages` 키에 LangGraph 내부 메시지 객체 배열이 포함되어 있어 크게 표시될 수 있다. `max-height + overflow: auto`로 스크롤 처리한다.
