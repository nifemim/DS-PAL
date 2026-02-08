---
title: "fix: Remove redundant Close button and Search nav link"
type: fix
date: 2026-02-08
tickets: [16, 9]
---

# fix: Remove redundant Close button and Search nav link

Two small UI cleanups to reduce clutter.

## Ticket #16: Remove Close button from preview modal

The modal footer has a "Close" button that duplicates the X button already in the modal header.

**File:** `app/templates/partials/modal_preview.html:74`

Remove the line:
```html
<button class="secondary" onclick="document.getElementById('preview-modal').close()">Close</button>
```

## Ticket #9: Remove Search nav link from header

The "Search" link in the navbar is redundant since the DS-PAL logo already links to `/` (the search page).

**File:** `app/templates/base.html:29`

Remove the line:
```html
<li><a href="/">Search</a></li>
```

## Acceptance Criteria

- [x] Preview modal footer only shows the "Analyze!" button (no Close button)
- [x] Modal can still be closed via the X button in the header
- [x] Navbar shows: DS-PAL logo | Saved Analyses | theme toggle (no Search link)
- [x] DS-PAL logo still links to home/search page
