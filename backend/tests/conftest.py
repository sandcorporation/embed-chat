# pyright: reportAttributeAccessIssue=false
import json
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from django.test import Client

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")




# ── Celery eager execution ────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def celery_always_eager(settings):
    """Run all Celery tasks synchronously so tests don't need a running worker."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = False


@pytest.fixture(autouse=True)
def reset_usage_context():
    """토큰 사용량 귀속 ContextVar를 테스트마다 초기화(누수 시 비-django_db 테스트가 DB write 시도)."""
    from apps.usage.context import _current
    _current.set(None)
    yield


# ── Event pipeline test helpers (issues 142-151) ─────────────────────────────

@pytest.fixture(autouse=True)
def isolated_events_topic(settings):
    """각 테스트가 유니크한 내구 스트림을 쓰게 해 Redis Streams 상태 교차오염을 막는다."""
    import uuid as _uuid
    settings.EVENTS_TOPIC = f"test.events.{_uuid.uuid4().hex}"


@pytest.fixture
def drain_events(settings):
    """outbox를 드레인하고 내구 소비자(webhook·visitor-bridge·console-bridge)를 인프로세스로
    1회 처리한다 — 컷오버 parity 테스트가 전이→이벤트→relay→소비자→부수효과 전 구간을 검증하게."""
    def _drain():
        import apps.events.handlers  # noqa: F401 — 핸들러 등록
        from apps.events.bus import RedisStreamsBus
        from apps.events.relay import drain_once
        from apps.events.consumer import EventConsumer, get_handler

        bus = RedisStreamsBus()
        topic = settings.EVENTS_TOPIC
        groups = ("webhook", "visitor-bridge", "console-bridge")
        for g in groups:
            bus.ensure_group(topic, g)  # 발행 전에 group 생성(이후 메시지를 보게)
        drain_once(bus)
        for g in groups:
            EventConsumer(bus, topic, g, f"{g}-test", get_handler(g)).process_once(block_ms=100)
    return _drain


# ── LLM 경계 Fake ─────────────────────────────────────────────────────────────
# LLM(OpenRouter)은 외부 API 경계이므로 단위/통합 테스트에서 결정적 Fake로 교체한다
# (mocking.md: 외부 API는 mock 대상, 내부 협력자는 아님).

def _latest_human_message(messages) -> str:
    """langchain 메시지 중 가장 최근 사용자(human) 발화를 반환한다.

    - 시스템 프롬프트('상담원' 안내문 포함 가능)는 제외한다.
    - checkpoint로 복원된 과거 발화가 아니라 현재 의도(마지막 사용자 메시지)만 본다.
    """
    latest = ""
    for m in messages:
        msg_type = getattr(m, "type", None)
        if isinstance(m, dict):
            msg_type = m.get("role") or m.get("type")
            content = m.get("content", "")
        else:
            content = getattr(m, "content", "")
        if msg_type in ("human", "user"):
            latest = str(content or "")
    return latest


class _FakeChatLLM:
    """결정적 chat LLM Fake. 기본은 키워드('상담원') 기반 판정이며,
    테스트가 override를 지정하면 그 함수가 판정을 대신한다."""

    HUMAN_AGENT_KEYWORD = "상담원"

    def __init__(self):
        self.override = None  # callable(messages) -> schema instance
        self.extraction = None  # optional GraphExtraction override (GraphRAG 추출용)
        self.last_provider = None  # 마지막 호출에 전달된 LLMProvider(라우팅 검증용)

    def complete_structured(self, provider, messages, schema):
        self.last_provider = provider
        # GraphRAG Entity/관계 추출 스키마는 결정적 그래프를 반환
        if schema.__name__ == "GraphExtraction":
            if self.extraction is not None:
                return self.extraction
            return schema(
                entities=[
                    {"name": "FOOTSWITCH", "type": "feature", "description": "a footswitch"},
                    {"name": "EXPRESSION_PEDAL", "type": "feature", "description": "a pedal"},
                ],
                relations=[
                    {"source": "FOOTSWITCH", "target": "EXPRESSION_PEDAL", "description": "paired with"},
                ],
            )
        if self.override is not None:
            return self.override(messages)
        # HITL-OFF 경로(response-only 스키마)는 needs_hitl 필드가 없다
        if schema.__name__ == "PlainResponse":
            return schema(response="안녕하세요! 무엇을 도와드릴까요?")
        text = _latest_human_message(messages)
        if self.HUMAN_AGENT_KEYWORD in text:
            return schema(response="", needs_hitl=True, hitl_reason="상담원 요청")
        return schema(
            response="안녕하세요! 무엇을 도와드릴까요?",
            needs_hitl=False,
            hitl_reason="",
        )

    def stream_structured(self, provider, messages, schema):
        """complete_structured와 같은 판정을 '제어필드 먼저 → response 청크'로 결정적 yield한다
        (PRD-chat-token-streaming). 노드의 델타 publish·폴백 게이팅을 검증할 수 있게 한다."""
        result = self.complete_structured(provider, messages, schema)
        d = result.model_dump()
        cs = d.get("context_sufficient", True)
        resp = d.get("response", "") or ""
        yield {"context_sufficient": cs}                              # 제어 먼저
        if resp:
            mid = max(1, len(resp) // 2)
            yield {"context_sufficient": cs, "response": resp[:mid]}  # response 자라남
            yield {"context_sufficient": cs, "response": resp}
        yield d                                                       # 최종(모든 필드)


@pytest.fixture(autouse=True)
def fake_chat_llm(monkeypatch):
    """chat 그래프의 구조화 LLM 호출을 결정적 Fake로 교체하고 핸들을 반환한다.

    autouse: 단위/통합 테스트는 절대 실제 chat LLM을 호출하지 않는다 (E2E는 별도).
    """
    fake = _FakeChatLLM()
    monkeypatch.setattr("apps.agent.llm.complete_structured", fake.complete_structured)
    monkeypatch.setattr("apps.agent.llm.stream_structured", fake.stream_structured)
    return fake


class _FakeTextLLM:
    """결정적 text LLM Fake (Visitor Memory 추출용). 기본은 추출 없음('{}')."""

    def __init__(self):
        self.facts = {}

    def complete_text(self, model_id, messages):
        import json
        return json.dumps(self.facts)


@pytest.fixture(autouse=True)
def fake_text_llm(monkeypatch):
    """Visitor Memory 추출 LLM 호출을 결정적 Fake로 교체하고 핸들을 반환한다.

    autouse: chat 흐름이 save_messages_node에서 메모리 추출을 eager로 호출하므로,
    단위/통합 테스트가 실제 추출 LLM을 치지 않도록 한다.
    """
    fake = _FakeTextLLM()
    monkeypatch.setattr("apps.agent.llm.complete_text", fake.complete_text)
    return fake


# ── Webhook receiver fixtures ─────────────────────────────────────────────────

class _WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        self.server.received.append({"path": self.path, "data": json.loads(body)})
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def webhook_server():
    """Real HTTP server that captures incoming webhook POSTs."""
    server = HTTPServer(("127.0.0.1", 0), _WebhookHandler)
    server.received = []
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield {"url": f"http://127.0.0.1:{port}", "received": server.received}
    server.shutdown()


class _FailHandler(BaseHTTPRequestHandler):
    def handle(self):
        self.server.attempts.append(1)
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
        except OSError:
            pass

    def log_message(self, *args):
        pass


@pytest.fixture
def failing_webhook_server():
    """HTTP server that immediately closes every connection (simulates network failure)."""
    server = HTTPServer(("127.0.0.1", 0), _FailHandler)
    server.attempts = []
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield {"url": f"http://127.0.0.1:{port}", "attempts": server.attempts}
    server.shutdown()


# ── Django / auth fixtures ────────────────────────────────────────────────────

@pytest.fixture
def client():
    return Client()


@pytest.fixture
def operator_token(client, db):
    from apps.tenants.models import Operator
    from apps.tenants.auth import create_operator_token

    op = Operator.objects.create(username="admin", email="admin@example.com")
    op.set_password("password123")
    op.save()
    return create_operator_token(op)


@pytest.fixture
def tenant_with_key(db):
    import secrets
    from apps.tenants.models import Tenant, TenantConfig

    raw_key = secrets.token_urlsafe(32)
    tenant = Tenant.objects.create_with_key(name="Test Corp", raw_key=raw_key)

    config = TenantConfig.objects.get(tenant=tenant)
    config.model_id = os.environ.get("OPEN_ROUTER_DEFAULT_MODEL", "qwen2.5:3b")
    config.system_prompt = (
        "You are a helpful customer service AI assistant. "
        "When a user requests a human agent or uses the Korean word '상담원', "
        "you MUST set needs_hitl=true. For all other requests respond helpfully with needs_hitl=false."
    )
    config.save()

    return tenant, raw_key


@pytest.fixture
def tenant_agent_token(tenant_with_key):
    from apps.tenants.models import TenantAgent
    from apps.tenants.auth import create_tenant_agent_token

    tenant, _ = tenant_with_key
    agent = TenantAgent(tenant=tenant, username="agent")
    agent.set_password("agentpass")
    agent.save()
    return create_tenant_agent_token(agent)


@pytest.fixture
def auth_operator(client, operator_token):
    def _client():
        c = Client()
        c.defaults["HTTP_AUTHORIZATION"] = f"Bearer {operator_token}"
        return c

    return _client()


# ── Redis subscribe fixture ───────────────────────────────────────────────────

@pytest.fixture
def redis_subscribe():
    """Subscribe to a Redis channel before an action and return a pubsub handle."""
    import redis as redis_lib

    connections = []

    def subscribe(channel):
        r = redis_lib.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
        pubsub = r.pubsub()
        pubsub.subscribe(channel)
        for _ in range(10):
            msg = pubsub.get_message(timeout=0.3)
            if msg and msg["type"] == "subscribe":
                break
        connections.append((r, pubsub))
        return pubsub

    yield subscribe

    for r, ps in connections:
        try:
            ps.close()
        except Exception:
            pass
        try:
            r.close()
        except Exception:
            pass
