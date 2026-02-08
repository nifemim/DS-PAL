---
title: "feat: Replace Select Dataset button with clickable title in search results"
type: feat
date: 2026-02-08
ticket: 14
---

# Replace Select Dataset button with clickable title in search results

## Context

Each search result currently shows a "Select Dataset" button at the bottom of the item. This adds visual clutter and is an extra click target. The title (`<h4>`) is already styled in the primary color, making it look clickable — but it isn't. This change makes the title the click target and removes the button entirely.

## Solution

Move the HTMX attributes and `onclick` handler from the `<button>` to an `<a>` tag wrapping the title text, then remove the button.

### `app/templates/partials/search_results.html`

**Before:**
```html
<div class="dataset-item-header">
    <span class="source-badge">{{ ds.source }}</span>
    <h4>{{ ds.name }}</h4>
</div>
...
<button class="dataset-item-action"
        onclick="document.getElementById('preview-modal').showModal()"
        hx-post="/api/dataset/modal-preview"
        hx-target="#modal-content"
        hx-indicator="#modal-spinner"
        hx-vals='...'>
    Select Dataset
</button>
```

**After:**
```html
<div class="dataset-item-header">
    <span class="source-badge">{{ ds.source }}</span>
    <h4><a href="#"
           role="button"
           onclick="event.preventDefault(); document.getElementById('preview-modal').showModal()"
           hx-post="/api/dataset/modal-preview"
           hx-target="#modal-content"
           hx-indicator="#modal-spinner"
           hx-vals='{"source": "{{ ds.source }}", "dataset_id": "{{ ds.dataset_id }}", "name": "{{ ds.name|e }}", "url": "{{ ds.url|e }}"}'>
        {{ ds.name }}
    </a></h4>
</div>
```

- Remove the `<button class="dataset-item-action">` entirely
- Use `event.preventDefault()` to stop `#` navigation

### `app/static/css/style.css`

- [x] Add hover style for clickable title (underline on hover, cursor pointer)
- [x] Remove or keep `.dataset-item-action` class (remove since button is gone)

```css
.dataset-item-header h4 a {
    color: var(--pico-primary);
    text-decoration: none;
    cursor: pointer;
}

.dataset-item-header h4 a:hover {
    text-decoration: underline;
}
```

## Files to Modify

- `app/templates/partials/search_results.html` — move HTMX attrs to title, remove button
- `app/static/css/style.css` — add clickable title styles, remove `.dataset-item-action`

## Acceptance Criteria

- [x] "Select Dataset" button is gone from search results
- [x] Dataset title is clickable and opens the preview modal
- [x] Title shows underline on hover
- [x] Modal loads dataset preview correctly (same behavior as before)
- [x] Keyboard accessible (Enter key triggers the link)

## Verification

1. Run the web app and search for "iris"
2. Confirm no "Select Dataset" button appears
3. Click a dataset title — confirm the preview modal opens with correct data
4. Hover over title — confirm underline appears
5. Tab to a title and press Enter — confirm modal opens
