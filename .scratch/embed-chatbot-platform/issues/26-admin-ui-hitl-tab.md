---
title: "어드민 UI HITL 탭 (실시간 목록 · 클레임 · 응답 · 해제)"
label: done
---

## Parent

PRD: `.scratch/embed-chatbot-platform/PRD-hitl.md`

## What to build

어드민 UI에 "HITL 상담" 탭을 추가한다. `/api/tenant/escalations/stream` SSE로 실시간 Escalation 목록을 유지하고, 클레임·메시지 전송·해제 UI를 제공한다. Pending 세션은 강조 표시된다.

## Acceptance criteria

- [ ] "HITL 상담" 탭이 TenantDashboard에 추가된다
- [ ] 탭 진입 시 SSE 연결이 시작되고 실시간 Escalation 목록이 표시된다
- [ ] Pending 상태의 Escalation이 시각적으로 강조된다
- [ ] 클레임 버튼 클릭 시 세션이 Claimed 상태로 바뀐다
- [ ] 이미 다른 상담원이 클레임한 세션은 읽기 전용으로 표시된다
- [ ] 클레임 후 메시지 입력·전송 UI가 활성화된다
- [ ] "AI에게 넘기기" 버튼 클릭 시 Escalation이 Resolved 상태로 바뀐다
- [ ] Resolve 후 해당 세션이 목록에서 사라진다

## Blocked by

- issue-23: Escalation 관리 API + 어드민 SSE 스트림
