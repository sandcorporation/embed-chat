import requests


def _build_slack_payload(esc, messages) -> dict:
    msg_text = "\n".join(f"*{m['role']}*: {m['content']}" for m in messages)
    return {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":rotating_light: *상담 에스컬레이션*\n*원인*: {esc.reason}\n*트리거*: {esc.trigger_type}",
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*최근 대화*\n{msg_text}"},
            },
        ]
    }


def _build_discord_payload(esc, messages) -> dict:
    msg_text = "\n".join(f"**{m['role']}**: {m['content']}" for m in messages)
    return {
        "embeds": [
            {
                "title": "상담 에스컬레이션",
                "description": f"**원인**: {esc.reason}\n**트리거**: {esc.trigger_type}",
                "fields": [{"name": "최근 대화", "value": msg_text or "-"}],
                "color": 16711680,
            }
        ]
    }


def _build_generic_payload(esc, messages) -> dict:
    return {
        "trigger_type": esc.trigger_type,
        "reason": esc.reason,
        "session_id": str(esc.session_id),
        "messages": messages,
    }


def dispatch_webhook(escalation_id: str) -> None:
    from apps.escalation.models import Escalation
    from apps.tenants.models import TenantConfig

    esc = Escalation.objects.select_related("session").get(id=escalation_id)
    config = TenantConfig.objects.get(tenant_id=esc.session.tenant_id)

    if not config.webhook_url or not config.webhook_type:
        return

    recent = list(
        esc.session.messages.order_by("-created_at")[:5]
    )
    recent.reverse()
    messages = [{"role": m.role, "content": m.content} for m in recent]

    wtype = config.webhook_type
    if wtype == "slack":
        payload = _build_slack_payload(esc, messages)
    elif wtype == "discord":
        payload = _build_discord_payload(esc, messages)
    else:
        payload = _build_generic_payload(esc, messages)

    for attempt in range(3):
        try:
            requests.post(config.webhook_url, json=payload, timeout=10)
            return
        except Exception:
            if attempt == 2:
                return
