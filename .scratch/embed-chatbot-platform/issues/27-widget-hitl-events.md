---
title: "위젯 HITL 이벤트 처리 (hitl_start · hitl_message · hitl_end)"
label: done
---

## Parent

PRD: `.scratch/embed-chatbot-platform/PRD-hitl.md`

## What to build

Visitor 위젯이 세 가지 HITL SSE 이벤트를 처리하도록 업데이트한다. `hitl_start`: 상담원 연결 중 시스템 메시지 표시. `hitl_message`: `agent_display_name`으로 발신자 표시 + 별도 스타일의 말풍선 렌더링. `hitl_end`: AI 복귀 시스템 메시지 표시.

## Acceptance criteria

- [ ] `hitl_start` 이벤트 수신 시 "잠시만 기다려 주세요. 상담원과 연결 중입니다." 시스템 메시지가 표시된다
- [ ] `hitl_message` 이벤트 수신 시 `agent_display_name`이 발신자로 표시된 메시지가 렌더링된다
- [ ] HumanTurn 메시지 말풍선은 AI 메시지와 다른 스타일(예: 다른 색상)을 갖는다
- [ ] `hitl_end` 이벤트 수신 시 "AI 상담으로 전환되었습니다." 시스템 메시지가 표시된다
- [ ] HITL 모드 중에도 Visitor는 메시지를 전송할 수 있다 (입력창 비활성화 없음)
- [ ] 기존 AI 응답 렌더링은 그대로 동작한다 (회귀 없음)

## Blocked by

- issue-23: Escalation 관리 API + 어드민 SSE 스트림
