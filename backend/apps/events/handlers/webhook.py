"""webhook 소비자 핸들러 (issue 146).

SessionEscalated 내구 이벤트를 소비해 Tenant webhook을 발사한다. 실패 시 raise → 소비자
런타임의 제한 재시도 + DLQ가 처리(best-effort였던 webhook을 at-least-once로 승격).
"""
from apps.events.consumer import register_handler
from apps.events.types import GROUP_WEBHOOK, SESSION_ESCALATED


def handle(envelope: dict) -> None:
    if envelope.get("type") != SESSION_ESCALATED:
        return  # webhook은 escalation 발생에만 반응
    from apps.escalation.webhook import send_webhook

    send_webhook(envelope["payload"]["escalation_id"])  # 실패 시 raise → 재시도/DLQ


register_handler(GROUP_WEBHOOK, handle)
