import json


def open_stream(client, tenant, visitor_id="v-1", slug=None):
    """slug를 보장한 뒤 slug+visitor_id로 stream 연결 응답을 반환한다 (issue 85 흐름).

    EmbedToken 폐지 후 테스트의 표준 연결 경로. tenant에 slug가 없으면 부여한다.
    """
    if slug is None:
        slug = tenant.slug or f"t-{str(tenant.id).split('-')[0]}"
    if tenant.slug != slug:
        tenant.slug = slug
        tenant.save(update_fields=["slug"])
    return client.get(f"/api/chat/stream?slug={slug}&visitor_id={visitor_id}")


def get_redis_message(pubsub, timeout=2.0):
    """Read the next non-subscribe message from a pubsub handle."""
    msg = pubsub.get_message(ignore_subscribe_messages=True, timeout=timeout)
    if msg and msg["type"] == "message":
        return json.loads(msg["data"])
    return None
