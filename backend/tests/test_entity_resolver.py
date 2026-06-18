"""EntityResolver 단위 테스트 — 임베딩 보유 Mention → 보수적 동치 쌍.

순수·결정적 deep module이므로 DB·Neo4j 없이 검증한다(fixture 임베딩).
"""
from apps.rag.entity_resolver import resolve_equivalences


def _pairset(pairs):
    """쌍 방향을 정규화한 집합 (순서 무관 비교)."""
    return {frozenset(p) for p in pairs}


def test_high_similarity_mentions_are_equivalent():
    """임베딩이 거의 동일한 두 Mention은 동치 쌍으로 묶인다 (표기변이)."""
    mentions = [
        {"mention_id": "m1", "embedding": [1.0, 0.0, 0.0]},
        {"mention_id": "m2", "embedding": [0.99, 0.02, 0.0]},
    ]
    assert frozenset(("m1", "m2")) in _pairset(resolve_equivalences(mentions))


def test_dissimilar_mentions_are_not_equivalent():
    """맥락(임베딩)이 다른 두 Mention은 동치가 아니다 (동음이의: '다리'=대교 vs 신체)."""
    mentions = [
        {"mention_id": "bridge", "embedding": [1.0, 0.0, 0.0]},
        {"mention_id": "leg", "embedding": [0.0, 1.0, 0.0]},  # 직교 → 유사도 0
    ]
    assert resolve_equivalences(mentions) == []


def test_close_but_below_threshold_stays_separate():
    """맥락이 가까워도(유사도 임계 미만) 보수적으로 분리한다 (Pedal A vs Pedal B)."""
    import math
    mentions = [
        {"mention_id": "pedal_a", "embedding": [1.0, 0.0]},
        {"mention_id": "pedal_b", "embedding": [0.9, math.sqrt(1 - 0.81)]},  # cos≈0.9 < 0.95
    ]
    assert resolve_equivalences(mentions) == []


def test_resolution_is_idempotent():
    """같은 입력에 대해 같은 동치 집합을 낸다 (멱등)."""
    mentions = [
        {"mention_id": "m1", "embedding": [1.0, 0.0, 0.0]},
        {"mention_id": "m2", "embedding": [0.99, 0.02, 0.0]},
        {"mention_id": "m3", "embedding": [0.0, 0.0, 1.0]},
    ]
    assert _pairset(resolve_equivalences(mentions)) == _pairset(resolve_equivalences(mentions))
