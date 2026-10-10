"""Reciprocal Rank Fusion (RRF) for merging ranked candidate lists."""

from collections import defaultdict
from typing import Dict, List, Mapping, Sequence, Tuple


def reciprocal_rank_fusion(
    rankings: Mapping[str, Sequence[str]],
    k: int = 60,
) -> List[Tuple[str, float]]:
    """Merge several ranked lists of doc ids into one ranking.

    Each document scores sum(1 / (k + rank)) over the lists it appears in.
    Duplicates inside one list count once. Ties are broken by doc id so the
    output is deterministic.
    """
    scores: Dict[str, float] = defaultdict(float)
    for ids in rankings.values():
        seen = set()
        rank = 0
        for doc_id in ids:
            if doc_id in seen:
                continue
            seen.add(doc_id)
            rank += 1
            scores[doc_id] += 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))