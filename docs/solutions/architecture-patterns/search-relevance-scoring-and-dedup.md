---
title: "Search result relevance scoring, deduplication, and client-side sorting"
category: architecture-patterns
module: search
tags: [search, ranking, fuzzy-matching, rapidfuzz, deduplication, client-side-sort, htmx]
symptoms:
  - "Relevant results buried below irrelevant ones"
  - "Same dataset appears multiple times from different providers"
  - "Results show in provider order, not relevance order"
  - "No way to reorder search results without re-running the search"
date_solved: 2026-03-01
ticket: "#61"
---

# Search result relevance scoring, deduplication, and client-side sorting

## Problem

Search results were concatenated in provider order — data.gov first, then Kaggle, HuggingFace, OpenML, AWS, and so on — with no relevance ranking. The symptoms:

- A query for "air quality California" would surface data.gov's least-relevant results above Kaggle's exact match simply because data.gov was queried first
- The same dataset, indexed by multiple providers under slightly different names, appeared two or three times in the results list
- There was no sort control; users had no way to reorder results without re-submitting the search

The fix needed to be a self-contained layer that didn't touch `search_all()` or the provider implementations, and it needed a sort UI that didn't trigger a full server round-trip.

## Root Cause

`search_all()` in `app/services/dataset_search.py` gathered results from each provider sequentially and concatenated them in registration order. There was no scoring, no deduplication pass, and no sort mechanism — results were displayed in exactly the order they arrived.

The `DatasetResult` schema also had no relevance field, so there was no place to attach a score even transiently.

## Solution

### 1. Single `rank_results()` function — score, deduplicate, sort in one pass

New file `app/services/search_ranker.py`:

```python
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
```

Key scoring decisions:

| Signal | Algorithm | Weight | Rationale |
|--------|-----------|--------|-----------|
| Title | `token_set_ratio` | 60% | Word-order insensitive; "Air Quality California" matches "California Air Quality" |
| Description | `partial_ratio` | 25% | Substring match handles long descriptions; only first 200 chars to avoid noise |
| Tags | `token_set_ratio` (best tag) | 15% | Reward strong tag hits, ignore weak ones |

`token_set_ratio` is used for title and tags because it tokenises both strings and compares the sorted intersection — so word order does not affect the score. `partial_ratio` is used for description because we want to reward the query appearing anywhere in the text.

Deduplication uses a threshold of 85: names below that threshold are distinct enough to keep; above it they collapse to the highest-scored entry. A plain nested loop is correct here — the result set is capped at roughly 25 items.

The relevance score is kept transient (a local tuple), not added to the `DatasetResult` schema. The original insertion order is preserved in `data-rank` attributes on the DOM for the client-side sort reset.

### 2. Two-line integration in `app/routers/search.py`

```python
from app.services.search_ranker import rank_results   # added

# inside the search endpoint, after search_all():
results, providers = await search_all(query)
results = rank_results(query, results)                # added
await save_search_history(query, len(results))
```

`search_all()` was not modified. The ranking layer sits entirely between the search aggregator and the template.

### 3. Client-side sort dropdown — no server round-trip

Sort is handled entirely in the browser. The template attaches `data-rank` (relevance position) and `data-name` (lowercased title) to each result card, and a vanilla JS function reorders the DOM in place.

**`app/templates/partials/search_results.html`** — sort control and data attributes:

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

{% for ds in results %}
<div class="dataset-item" data-name="{{ ds.name|lower }}" data-rank="{{ loop.index }}">
    ...
</div>
{% endfor %}
```

**`app/static/js/app.js`** — `sortResults()`:

```js
function sortResults(by) {
    var list = document.querySelector(".dataset-list");
    if (!list) return;
    var items = Array.from(list.querySelectorAll(".dataset-item"));
    items.sort(function (a, b) {
        if (by === "name") return a.dataset.name.localeCompare(b.dataset.name);
        return parseInt(a.dataset.rank) - parseInt(b.dataset.rank);
    });
    items.forEach(function (el) { list.appendChild(el); });
}
```

`data-rank` stores the original relevance position (1-indexed from `loop.index`), so switching back to "Relevance" from "Name A-Z" restores the server-ranked order exactly.

### 4. Sort dropdown styles — Pico CSS fix

Pico CSS renders `<select>` elements at full width with a right-side arrow. Without explicit `padding-right`, the arrow overlaps the text in a narrow inline select. Fixed in `app/static/css/style.css`:

```css
/* Search results header with sort dropdown */
.search-results-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 1rem;
}
.search-results-header select {
    width: auto;
    margin-bottom: 0;
    padding: 0.25rem 2rem 0.25rem 0.5rem;  /* 2rem right clears the arrow */
    font-size: 0.85rem;
    cursor: pointer;
    border-color: var(--pico-muted-border-color);
    transition: border-color 0.2s, color 0.2s;
}
.search-results-header select:hover {
    border-color: var(--pico-primary);
    color: var(--pico-primary);
}
```

## Prevention

1. **Relevance is a separate layer** — keep scoring outside the provider/aggregator code. `search_all()` should return raw results; a dedicated ranker transforms them. This makes each piece independently testable.

2. **Client-side sort over server re-fetch** — for reordering already-loaded results, a JS DOM sort is always faster and simpler than re-running the full search. Use `data-*` attributes to carry the sort keys; avoid encoding logic in the sort function itself.

3. **Transient scores, not schema fields** — if a score is only needed to order results before the template renders, keep it in a local variable (e.g., a `list[tuple[float, T]]`). Adding it to the model leaks an implementation detail and forces every downstream consumer to ignore or handle the field.

4. **`token_set_ratio` for title/tag matching** — when user queries and dataset titles may share the same words in different orders, `token_set_ratio` handles this transparently. `partial_ratio` is better for long-text substring matches.

5. **Simple dedup beats fancy distance metrics** — for small result sets (~25 items), a nested loop with `token_set_ratio >= 85` is readable, debuggable, and fast enough. Avoid reaching for `scipy.cdist` or vectorised approaches until the dataset size justifies it.

6. **Pico CSS inline selects need explicit `padding-right: 2rem`** — the native dropdown arrow is rendered as a background image; it does not push text out of the way. Any `<select>` rendered inline (not at full column width) needs this padding set manually.

## Related

- **Files changed**:
  - `/Users/nifemimadarikan/Documents/ClaudeCode/DS-PAL/requirements.txt` — added `rapidfuzz>=3.0,<4.0`
  - `/Users/nifemimadarikan/Documents/ClaudeCode/DS-PAL/app/services/search_ranker.py` — new file, `rank_results()` function
  - `/Users/nifemimadarikan/Documents/ClaudeCode/DS-PAL/app/routers/search.py` — 2 lines added (import + call)
  - `/Users/nifemimadarikan/Documents/ClaudeCode/DS-PAL/app/templates/partials/search_results.html` — sort dropdown + `data-rank`/`data-name` attributes
  - `/Users/nifemimadarikan/Documents/ClaudeCode/DS-PAL/app/static/js/app.js` — `sortResults()` function
  - `/Users/nifemimadarikan/Documents/ClaudeCode/DS-PAL/app/static/css/style.css` — sort dropdown styles
  - `/Users/nifemimadarikan/Documents/ClaudeCode/DS-PAL/tests/test_search.py` — 9 new tests for `rank_results()`

- **See also**:
  - rapidfuzz `token_set_ratio` vs `partial_ratio` — [rapidfuzz docs](https://rapidfuzz.github.io/RapidFuzz/Usage/fuzz.html)
  - `app/services/dataset_search.py` — `search_all()` aggregator (untouched)
  - `app/models/schemas.py` — `DatasetResult` schema (unchanged)
