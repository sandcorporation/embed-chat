import json


def get_redis_message(pubsub, timeout=2.0):
    """Read the next non-subscribe message from a pubsub handle."""
    msg = pubsub.get_message(ignore_subscribe_messages=True, timeout=timeout)
    if msg and msg["type"] == "message":
        return json.loads(msg["data"])
    return None
