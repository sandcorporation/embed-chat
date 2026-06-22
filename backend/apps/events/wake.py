"""relay wake 신호 (issue 144 개선).

outbox 행이 커밋되면 Redis pub/sub로 가벼운 wake를 쏘고, relay가 이를 구독해 즉시 드레인한다.
pg LISTEN/NOTIFY(psycopg3에서 Django 연결과 엮기 까다로움) 대신 이미 쓰는 Redis pub/sub로
저지연·크로스플랫폼 wake를 얻는다. wake는 best-effort 신호일 뿐 — 유실돼도 outbox는 DB에
남아 relay의 주기 sweep(backstop)이 회수하므로 정합성은 outbox가 보장한다.
"""
import redis
from django.conf import settings

OUTBOX_WAKE_CHANNEL = "outbox:wake"


def _redis():
    return redis.from_url(settings.REDIS_URL)


def notify_outbox() -> None:
    """relay를 깨운다. 반드시 트랜잭션 커밋 후에 호출돼야 한다(transaction.on_commit)."""
    _redis().publish(OUTBOX_WAKE_CHANNEL, "1")
