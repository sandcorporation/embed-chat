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


def _build_payload(esc, messages, wtype: str) -> dict:
    if wtype == "slack":
        return _build_slack_payload(esc, messages)
    if wtype == "discord":
        return _build_discord_payload(esc, messages)
    return _build_generic_payload(esc, messages)


def send_webhook(escalation_id: str) -> None:
    """webhook을 1회 전송한다. 실패(네트워크/비2xx) 시 예외를 올린다 — 재시도·DLQ는 소비자 런타임이
    담당한다(issue 146). webhook 미설정 Tenant는 no-op."""
    from apps.escalation.models import Escalation
    from apps.tenants.models import TenantConfig

    esc = Escalation.objects.select_related("session").get(id=escalation_id)
    config = TenantConfig.objects.get(tenant_id=esc.session.tenant_id)
    if not config.webhook_url or not config.webhook_type:
        return

    recent = list(esc.session.messages.order_by("-created_at")[:5])
    recent.reverse()
    messages = [{"role": m.role, "content": m.content} for m in recent]
    payload = _build_payload(esc, messages, config.webhook_type)

    resp = requests.post(config.webhook_url, json=payload, timeout=10)
    resp.raise_for_status()


def dispatch_webhook(escalation_id: str) -> None:
    """레거시 Celery 경로(best-effort, 실패 삼킴). 컷오버(151)에서 제거 예정."""
    for attempt in range(3):
        try:
            send_webhook(escalation_id)
            return
        except Exception:
            if attempt == 2:
                return
