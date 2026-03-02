---
title: "feat: Improve search result relevance with fuzzy scoring and deduplication"
type: feat
date: 2026-03-01
ticket: 61
---

# feat: Improve search result relevance

## Overview

Search results are currently concatenated in provider order (data.gov first, then Kaggle, HuggingFace, OpenML, AWS) with no relevance ranking. This feature adds fuzzy relevance scoring, cross-provider deduplication, and a client-side sort dropdown.

## Problem Statement

1. **Wrong order** — good results buried below irrelevant ones from earlier providers
2. **Junk results** — providers return datasets that barely match the query
3. **Duplicates** — same dataset appears from multiple providers with no grouping
4. **No user control** — no way to sort by relevance or name

## Proposed Solution

Add a single `rank_results()` function using `rapidfuzz` that scores and deduplicates results. Sort by relevance by default. Add a client-side sort dropdown (no server re-fetch for re-ordering).

## Technical Approach

### New file: `app/services/search_ranker.py`

One function that scores, deduplicates, and sorts in a single pass:

```python
from rapidfuzz import fuzz
from app.models.schemas import DatasetResult

DEDUP_THRESHOLD = 85

def rank_results(query: str, results: list[DatasetResult]) -> list[DatasetResult]:
    """Score results by query relevance, deduplicate, return sorted."""
    # Score each result
    scored = []
    for r in results:
        title_score = fuzz.token_set_ratio(query.lower(), r.name.lower()) * 0.60
        desc_score = fuzz.partial_ratio(query.lower(), r.description[:200].lower()) * 0.25
        tag_score = max(
            (fuzz.token_set_ratio(query.lower(), t.lower()) for t in r.tags),
            default=0,
        ) * 0.15
        scored.append((title_score + desc_score + tag_score, r))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    # Deduplicate: keep first (highest-scored) when names are near-identical
    kept: list[tuple[float, DatasetResult]] = []
    for score, result in scored:
        if not any(fuzz.token_set_ratio(result.name.lower(), k.name.lower()) >= DEDUP_THRESHOLD for _, k in kept):
            kept.append((score, result))

    return [r for _, r in kept]
```

### Integration: `app/routers/search.py`

`search_all()` stays untouched (pure orchestrator). Ranking happens in the router:

```python
from app.services.search_ranker import rank_results

@router.post("/search")
async def search_datasets(request: Request, query: str = Form(...)):
    results, providers = await search_all(query)
    results = rank_results(query, results)
    # ... rest unchanged, pass results to template ...
```

No schema change to `DatasetResult` — relevance score is a transient computation, not a model property.

### Template change: `app/templates/partials/search_results.html`

Add a client-side sort dropdown and `data-name` / `data-rank` attributes on each result for JS sorting:

```html
<div class="search-results-header">
    <h3>Results for "{{ query }}" ({{ results|length }} found)
        {% if providers %}<small>— from {{ providers|join(", ") }}</small>{% endif %}
    </h3>
    {% if results|length > 1 %}
    <select id="sort-select" onchange="sortResults(this.value)">
        <option value="relevance">Relevance</option>
        <option value="name">Name A-Z</option>
    </select>
    {% endif %}
</div>
```

Each `.dataset-item` gets data attributes:

```html
<div class="dataset-item" data-name="{{ ds.name|lower }}" data-rank="{{ loop.index }}">
```

### JS for client-side sort: `app/static/js/app.js`

~10 lines of vanilla JS:

```javascript
function sortResults(by) {
    var list = document.querySelector('.dataset-list');
    if (!list) return;
    var items = Array.from(list.querySelectorAll('.dataset-item'));
    items.sort(function(a, b) {
        if (by === 'name') return a.dataset.name.localeCompare(b.dataset.name);
        return parseInt(a.dataset.rank) - parseInt(b.dataset.rank);
    });
    items.forEach(function(el) { list.appendChild(el); });
}
```

No server round-trip for sorting. Instant feedback.

### Dependency: `requirements.txt`

Add `rapidfuzz`. `token_set_ratio` handles word order and partial matches far better than `difflib` for matching "air quality California" against "California Air Quality Monitoring Dataset."

## Acceptance Criteria

- [x] Results are scored by relevance to the query (title > description > tags)
- [x] Results are sorted by relevance score by default (highest first)
- [x] Duplicate datasets across providers are collapsed to a single result
- [x] Sort dropdown appears in results header with options: Relevance, Name A-Z
- [x] Changing sort reorders instantly (client-side, no server re-fetch)
- [x] Typos in queries still return reasonable results (fuzzy matching)
- [x] Empty results from a provider don't break scoring
- [x] All providers failing still returns empty state gracefully
- [x] `search_all()` unchanged — ranking is a separate layer
- [x] Existing search tests still pass
- [x] New tests cover: scoring, deduplication, edge cases

## Edge Cases

- **All results score 0:** Still show results in original provider order
- **Single result:** No dedup needed, scoring still applies
- **Provider timeout:** Score whatever comes back, existing graceful failure unchanged
- **Similar names, different datasets:** Only dedup at threshold 85 — distinct datasets survive
- **New search after sort:** Results arrive in relevance order (sort dropdown resets)

## Dependencies & Risks

- **New dependency:** `rapidfuzz` — C extensions, zero transitive deps, widely used
- **Performance:** Scoring + dedup on 25 results is sub-millisecond
- **Dedup threshold:** Start at 85, tune based on real queries

## Files to Change

1. `requirements.txt` — add `rapidfuzz`
2. `app/services/search_ranker.py` — new file, one function (~20 lines)
3. `app/routers/search.py` — add 2 lines (import + call `rank_results`)
4. `app/templates/partials/search_results.html` — add sort dropdown + data attributes
5. `app/static/js/app.js` — add `sortResults()` function (~10 lines)
6. `tests/test_search.py` — add tests for ranking and dedup

## References

- Brainstorm: `docs/brainstorms/2026-03-01-improve-search-relevance-brainstorm.md`
- Search orchestrator: `app/services/dataset_search.py`
- Search router: `app/routers/search.py:13-36`
- Results template: `app/templates/partials/search_results.html`
- Search tests: `tests/test_search.py`
- UX learning (keep list layout): `docs/solutions/ui-bugs/search-results-grid-hard-to-scan.md`
