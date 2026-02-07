---
title: "Refactor search results from grid to list layout"
type: refactor
date: 2026-02-06
ticket: 6
---

# ♻️ Refactor Search Results from Grid to List Layout

Replace the current grid-based search results with a vertical list layout inspired by Wikipedia search results. Each result shows a prominent clickable name, source badge, description snippet, and metadata — optimized for scanning and comparison.

## Acceptance Criteria

- [x] Search results display as a vertical list instead of a multi-column grid
- [x] Each result row shows: source badge, dataset name (prominent/clickable), truncated description, and metadata (size, format, tags)
- [x] Layout follows Wikipedia search results pattern: clean typographic hierarchy, no card borders, whitespace separation
- [x] "Select Dataset" button triggers the existing modal preview (HTMX behavior unchanged)
- [x] Responsive: rows adapt gracefully at mobile breakpoints (<=768px)
- [x] Empty state ("No datasets found") remains unchanged
- [x] Results with missing optional fields (description, size, tags) render cleanly without visual gaps

## Context

**Reference**: Wikipedia search results — each result is a vertical block with prominent title, metadata line, and description snippet. No card borders, just clean spacing between items.

**Current implementation**: CSS Grid (`repeat(auto-fill, minmax(300px, 1fr))`) rendering `<article class="dataset-card">` elements inside a `.dataset-grid` container.

**Files to modify** (only 2 files, no backend changes):

| File | Changes |
|------|---------|
| `app/templates/partials/search_results.html` | Replace grid markup with list layout |
| `app/static/css/style.css` | Replace `.dataset-grid`/`.dataset-card` styles (lines 20-56) with `.dataset-list`/`.dataset-item` styles; update responsive breakpoint (lines 223-225) |

**Data model** (`app/models/schemas.py:16-24`): All fields already available — `source`, `name`, `description`, `size`, `format`, `tags`, `dataset_id`, `url`.

## MVP

### app/templates/partials/search_results.html

```html
<h3>Results for "{{ query }}" ({{ results|length }} found)</h3>

{% if results %}
<div class="dataset-list">
    {% for ds in results %}
    <div class="dataset-item">
        <div class="dataset-item-header">
            <span class="source-badge">{{ ds.source }}</span>
            <h4>{{ ds.name }}</h4>
        </div>
        {% if ds.description %}
        <p class="dataset-item-description">{{ ds.description[:150] }}{% if ds.description|length > 150 %}...{% endif %}</p>
        {% endif %}
        <div class="dataset-item-meta">
            {% if ds.size %}<span>Size: {{ ds.size }}</span>{% endif %}
            <span>Format: {{ ds.format or "CSV" }}</span>
            {% if ds.tags %}<span>Tags: {{ ds.tags|join(", ") }}</span>{% endif %}
        </div>
        <button class="dataset-item-action"
                onclick="document.getElementById('preview-modal').showModal()"
                hx-post="/api/dataset/modal-preview"
                hx-target="#modal-content"
                hx-indicator="#modal-spinner"
                hx-vals='{"source": "{{ ds.source }}", "dataset_id": "{{ ds.dataset_id }}", "name": "{{ ds.name|e }}", "url": "{{ ds.url|e }}"}'>
            Select Dataset
        </button>
    </div>
    {% endfor %}
</div>
{% else %}
<div class="empty-state">
    <p>No datasets found. Try a different search term.</p>
</div>
{% endif %}
```

### app/static/css/style.css (replace lines 20-56)

```css
/* Dataset list (Wikipedia-style search results) */
.dataset-list {
    margin-top: 1rem;
}

.dataset-item {
    padding: 1rem 0;
    border-bottom: 1px solid var(--pico-muted-border-color);
}

.dataset-item:last-child {
    border-bottom: none;
}

.dataset-item-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.25rem;
}

.dataset-item-header h4 {
    margin: 0;
    color: var(--pico-primary);
}

.dataset-item-description {
    margin: 0.25rem 0;
    font-size: 0.9rem;
    color: var(--pico-muted-color);
}

.dataset-item-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    font-size: 0.8rem;
    color: var(--pico-muted-color);
    margin: 0.25rem 0;
}

.dataset-item-action {
    margin-top: 0.5rem;
    padding: 0.25rem 0.75rem;
    font-size: 0.85rem;
    width: auto;
}

/* Responsive: stack metadata on small screens */
@media (max-width: 768px) {
    .dataset-item-meta {
        flex-direction: column;
        gap: 0.25rem;
    }
}
```

## References

- Ticket: #6
- Wikipedia search results design: [Improving search on Wikipedia](https://design.wikimedia.org/blog/2023/03/17/improving-search-wikipedia.html)
- Current grid styles: `app/static/css/style.css:20-56`
- Current template: `app/templates/partials/search_results.html`
- Data model: `app/models/schemas.py:16-24`
- Search route: `app/routers/search.py:13-36`
