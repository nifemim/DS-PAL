---
title: "Search results grid layout hard to scan and compare"
category: ui-bugs
module: search
tags: [ui, layout, css, search-results, usability]
symptoms:
  - "Search results hard to scan quickly"
  - "Card grid layout wastes space"
  - "Difficult to compare datasets side by side"
date_solved: 2026-02-07
ticket: "#6"
pr: "#2"
---

## Problem

The search results page used a CSS grid card layout that made it difficult for users to quickly scan and compare multiple datasets. The grid layout with `repeat(auto-fill, minmax(300px, 1fr))` created visual boxes that:

1. Wasted horizontal space with cards of varying heights
2. Required eye movement across columns and rows, breaking reading flow
3. Made side-by-side comparison of dataset metadata difficult
4. Prioritized visual aesthetics over information density and scannability

Users needed to quickly evaluate multiple search results, but the card-based grid layout optimized for visual appeal rather than efficient information consumption.

## Root Cause

The original design used a card grid pattern common in image galleries and e-commerce, but inappropriate for text-heavy search results:

**HTML Structure (Before):**
```html
<div class="dataset-grid">
    <article class="dataset-card">
        <!-- Dataset info with borders and hover effects -->
    </article>
</div>
```

**CSS (Before):**
```css
.dataset-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 1.5rem;
}

.dataset-card {
    border: 1px solid var(--pico-muted-border-color);
    border-radius: var(--pico-border-radius);
    padding: 1rem;
    transition: border-color 0.2s;
}

.dataset-card:hover {
    border-color: var(--pico-primary);
}
```

This pattern forced each result into a fixed-width box, creating a 2D grid that:
- Interrupted natural top-to-bottom reading flow
- Added visual noise with borders and spacing around each card
- Made scanning require zigzag eye movement

## Solution

Replaced the grid layout with a Wikipedia-style vertical list that prioritizes scannability and clean typography. Search results now flow in a single column with clear visual hierarchy.

### Template Changes

**File:** `/Users/nifemimadarikan/Documents/ClaudeCode/DS-PAL/app/templates/partials/search_results.html`

Replaced grid markup with a semantic list structure:

```html
<div class="dataset-list">
    {% for ds in results %}
    <div class="dataset-item">
        <div class="dataset-item-header">
            <span class="source-badge">{{ ds.source }}</span>
            <h4>{{ ds.name }}</h4>
        </div>
        {% if ds.description %}
        <p class="dataset-item-description">
            {{ ds.description[:150] }}{% if ds.description|length > 150 %}...{% endif %}
        </p>
        {% endif %}
        <div class="dataset-item-meta">
            {% if ds.size %}<span>Size: {{ ds.size }}</span>{% endif %}
            <span>Format: {{ ds.format or "CSV" }}</span>
            {% if ds.tags %}<span>Tags: {{ ds.tags|join(", ") }}</span>{% endif %}
        </div>
        <button class="dataset-item-action">Select Dataset</button>
    </div>
    {% endfor %}
</div>
```

### CSS Changes

**File:** `/Users/nifemimadarikan/Documents/ClaudeCode/DS-PAL/app/static/css/style.css`

Replaced grid styles with list styles and vertical rhythm:

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
```

### Responsive Breakpoint

Updated mobile responsiveness to stack metadata vertically:

```css
@media (max-width: 768px) {
    .dataset-item-meta {
        flex-direction: column;
        gap: 0.25rem;
    }
}
```

### Key Improvements

1. **Vertical flow:** Single-column list allows natural top-to-bottom scanning
2. **Clear hierarchy:** Prominent titles, subtle metadata, clean separation with bottom borders
3. **Information density:** More results visible without scrolling, no wasted space
4. **Scannability:** Source badges, truncated descriptions (150 chars), and inline metadata
5. **Reduced visual noise:** No card borders or hover effects, focus on content

## Prevention

To avoid similar UX issues in future interface designs:

1. **Match pattern to content type:** Use card grids for visual content (images, products), lists for text-heavy data (search results, tables, feeds)
2. **Prioritize scannability:** For comparison tasks, favor vertical lists over 2D grids
3. **Test with realistic data:** Evaluate layouts with actual content volume, not lorem ipsum
4. **Follow established patterns:** Search results conventions exist for good reason (Google, Wikipedia, academic databases all use vertical lists)
5. **Mobile-first thinking:** Designs that work well on narrow screens often scale better to desktop

### Design Decision Framework

When choosing between grid and list layouts:
- **Grid:** Visual browsing, exploration, variety of content types
- **List:** Quick scanning, comparison, homogeneous text-heavy items

## Related

- Ticket #5: Dataset preview modal (complements improved search UX)
- PicoCSS framework: Provides the base styles and CSS variables used
- HTMX integration: Powers the interactive "Select Dataset" action buttons
