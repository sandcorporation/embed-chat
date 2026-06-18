"""EntityResolver — Entity Mention 동치(Entity Equivalence) 판별 (ADR-0010).

임베딩(name+description)을 가진 Mention 집합에서 같은 referent를 가리키는 쌍을
**보수적으로** 찾아 SAME_AS 후보로 낸다. 정체성은 이름이 아니라 맥락이므로 신호는
설명이 반영된 임베딩 유사도다. 위험이 비대칭(과대병합 > 과소병합)이라 확신할 때만 묶는다.

순수·결정적 모듈 — 외부 I/O 없이 Mention(+embedding)만 받는다. 추이성(A~B~C)은
호출측(community union-find)이 처리하므로 여기서는 쌍만 낸다.
"""
import math

# 코사인 유사도가 이 값 이상일 때만 동치로 본다(보수적). fixture로 튜닝.
SIMILARITY_THRESHOLD = 0.95


def _cosine(a: list, b: list) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def resolve_equivalences(mentions: list) -> list:
    """동치인 Mention 쌍 [(mention_id, mention_id), ...]을 반환한다.

    mentions: [{"mention_id": str, "embedding": list[float]}, ...]
    """
    pairs = []
    for i in range(len(mentions)):
        for j in range(i + 1, len(mentions)):
            sim = _cosine(mentions[i]["embedding"], mentions[j]["embedding"])
            if sim >= SIMILARITY_THRESHOLD:
                pairs.append((mentions[i]["mention_id"], mentions[j]["mention_id"]))
    return pairs
