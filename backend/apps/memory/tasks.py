from config.celery import app


@app.task
def schedule_memory_extraction(tenant_id: str, visitor_id: str, session_id: str):
    from apps.chat.models import ChatMessage, ChatSession
    from apps.memory.manager import upsert_memory
    from django.conf import settings
    from langchain_core.messages import HumanMessage
    from apps.agent import llm as llm_boundary

    try:
        session = ChatSession.objects.get(id=session_id)
        messages = list(session.messages.order_by("created_at"))
        if not messages:
            return

        conversation = "\n".join(
            f"{m.role.upper()}: {m.content}" for m in messages
        )

        from apps.tenants.models import TenantConfig
        try:
            config = TenantConfig.objects.get(tenant_id=tenant_id)
            model_id = config.model_id
        except TenantConfig.DoesNotExist:
            model_id = settings.OPEN_ROUTER_DEFAULT_MODEL

        prompt = f"""Extract key facts about the user from this conversation as JSON.
Return ONLY a JSON object with string keys and string values. Example: {{"preference": "prefers email", "name": "Alice"}}
If nothing notable, return {{}}.

Conversation:
{conversation}"""

        content = llm_boundary.complete_text(model_id, [HumanMessage(content=prompt)])
        import json, re
        raw = content.strip()
        # strip code fences: ```json ... ``` or ``` ... ```
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        facts = json.loads(raw)
        if isinstance(facts, dict):
            for key, value in facts.items():
                upsert_memory(tenant_id, visitor_id, key, str(value))
    except Exception:
        pass
