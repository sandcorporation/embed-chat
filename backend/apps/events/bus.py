"""EventBus 포트 + Redis Streams 어댑터 (issue 142).

브로커-중립 인터페이스(publish/consume/ack/claim/dead-letter)로 이벤트 전송을 추상화한다.
relay와 소비자는 이 포트만 의존하므로, 추후 Kafka 어댑터를 드롭인할 수 있다(PRD: Kafka-later).
key는 봉투에 보존된다 — Redis 단일 스트림에선 순서에 미사용, Kafka 파티션키로 예약.
"""
import json
from dataclasses import dataclass

import redis
from django.conf import settings


@dataclass
class ConsumedMessage:
    """소비된 메시지 — broker 메시지 id(ack/claim용)와 파싱된 이벤트 봉투."""
    msg_id: str
    payload: dict


def _dlq_topic(topic: str) -> str:
    return f"{topic}.dlq"


class RedisStreamsBus:
    """EventBus 포트의 Redis Streams 구현."""

    def __init__(self, client=None):
        self._r = client or redis.from_url(settings.REDIS_URL)

    def publish(self, topic: str, key: str, payload: dict, maxlen: "int | None" = None) -> None:
        """maxlen 지정 시 capped 스트림(근사 트림) — ephemeral presence 등 휘발성 신호용."""
        kwargs = {"maxlen": maxlen, "approximate": True} if maxlen else {}
        self._r.xadd(topic, {"data": json.dumps(payload), "key": key or ""}, **kwargs)

    def ensure_group(self, topic: str, group: str) -> None:
        """consumer group을 멱등 생성한다(없으면 스트림도 MKSTREAM). 이미 있으면 무시."""
        try:
            self._r.xgroup_create(topic, group, id="$", mkstream=True)
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    def consume(self, topic: str, group: str, consumer: str, count: int = 10, block_ms: int = 1000):
        """group의 새 메시지(>)를 읽는다. ack 전엔 PEL(pending)에 남는다."""
        resp = self._r.xreadgroup(group, consumer, {topic: ">"}, count=count, block=block_ms)
        return self._parse_streams(resp)

    def ack(self, topic: str, group: str, msg_id: str) -> None:
        self._r.xack(topic, group, msg_id)

    def claim_stale(self, topic: str, group: str, consumer: str, min_idle_ms: int, count: int = 10):
        """min_idle_ms 넘게 ack 안 된 pending 메시지를 consumer로 재청구(XAUTOCLAIM)."""
        res = self._r.xautoclaim(topic, group, consumer, min_idle_time=min_idle_ms, start_id="0-0", count=count)
        entries = res[1] if isinstance(res, (list, tuple)) and len(res) >= 2 else []
        return self._parse_entries(entries)

    def to_dead_letter(self, topic: str, group: str, msg: ConsumedMessage, reason: str) -> None:
        """메시지를 dead-letter 스트림으로 옮기고 원 PEL에서 ack(더 이상 재전달 안 됨)."""
        payload = dict(msg.payload)
        payload["_dlq_reason"] = reason
        self._r.xadd(_dlq_topic(topic), {"data": json.dumps(payload)})
        self._r.xack(topic, group, msg.msg_id)

    def dead_letter_items(self, topic: str, count: int = 100):
        return self._parse_entries(self._r.xrange(_dlq_topic(topic), count=count))

    def remove_dead_letter(self, topic: str, msg_ids) -> None:
        """리플레이 후 dead-letter 스트림에서 항목을 제거(중복 리플레이 방지)."""
        if msg_ids:
            self._r.xdel(_dlq_topic(topic), *msg_ids)

    # ── 파싱 ──────────────────────────────────────────────────────────────────
    def _parse_streams(self, resp):
        out = []
        for _stream, entries in (resp or []):
            out.extend(self._parse_entries(entries))
        return out

    def _parse_entries(self, entries):
        out = []
        for msg_id, fields in (entries or []):
            mid = msg_id.decode() if isinstance(msg_id, bytes) else msg_id
            data = fields.get(b"data") if b"data" in fields else fields.get("data")
            if isinstance(data, bytes):
                data = data.decode()
            out.append(ConsumedMessage(msg_id=mid, payload=json.loads(data)))
        return out
