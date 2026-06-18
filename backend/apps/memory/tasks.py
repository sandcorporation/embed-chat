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
        from apps.agent.providers import chat_provider, LLMProvider
        try:
            config = TenantConfig.objects.get(tenant_id=tenant_id)
            provider = chat_provider(config)
        except TenantConfig.DoesNotExist:
            provider = LLMProvider(
                type="", model=settings.OPEN_ROUTER_DEFAULT_MODEL,
                base_url=settings.OPEN_ROUTER_BASE_URL, api_key=settings.OPEN_ROUTER_API_KEY,
            )

        prompt = f"""Extract key facts about the user from this conversation as JSON.
Return ONLY a JSON object with string keys and string values. Example: {{"preference": "prefers email", "name": "Alice"}}
If nothing notable, return {{}}.

Conversation:
{conversation}"""

        content = llm_boundary.complete_text(provider, [HumanMessage(content=prompt)])
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
