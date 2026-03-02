"""Score and deduplicate search results by query relevance."""
from __future__ import annotations

from rapidfuzz import fuzz

from app.models.schemas import DatasetResult

DEDUP_THRESHOLD = 85


def rank_results(query: str, results: list[DatasetResult]) -> list[DatasetResult]:
    """Score results by query relevance, deduplicate, return sorted."""
    if not results:
        return results

    q = query.lower()

    # Score each result
    scored: list[tuple[float, DatasetResult]] = []
    for r in results:
        title_score = fuzz.token_set_ratio(q, r.name.lower()) * 0.60
        desc_score = fuzz.partial_ratio(q, r.description[:200].lower()) * 0.25
        tag_score = max(
            (fuzz.token_set_ratio(q, t.lower()) for t in r.tags),
            default=0,
        ) * 0.15
        scored.append((title_score + desc_score + tag_score, r))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    # Deduplicate: keep first (highest-scored) when names are near-identical
    kept: list[tuple[float, DatasetResult]] = []
    for score, result in scored:
        if not any(
            fuzz.token_set_ratio(result.name.lower(), k.name.lower()) >= DEDUP_THRESHOLD
            for _, k in kept
        ):
            kept.append((score, result))

    return [r for _, r in kept]
