"""카논 도메인 이벤트 타입 상수 (PRD: HITL/세션 라이프사이클).

내구(outbox→event_store→bus): escalation 애그리거트 전이.
ephemeral(EventBus capped, outbox 미경유): presence 전이.
"""
# ── 내구 도메인 이벤트 ─────────────────────────────────────────────────────────
SESSION_ESCALATED = "SessionEscalated"
ESCALATION_CLAIMED = "EscalationClaimed"
SESSION_TAKEN_OVER = "SessionTakenOver"
ESCALATION_RESOLVED = "EscalationResolved"

# ── ephemeral presence 신호 ────────────────────────────────────────────────────
VISITOR_CONNECTED = "VisitorConnected"
VISITOR_DISCONNECTED = "VisitorDisconnected"

# 소비자 group 이름.
GROUP_WEBHOOK = "webhook"
GROUP_VISITOR_BRIDGE = "visitor-bridge"
GROUP_CONSOLE_BRIDGE = "console-bridge"
GROUP_PRESENCE_BRIDGE = "presence-bridge"

# ephemeral presence 전송용 별도 스트림(outbox 미경유, capped).
PRESENCE_TOPIC = "signals.presence"
