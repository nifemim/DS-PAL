---
title: "HTMX does not add htmx-request class to requesting element in 1.x"
category: ui-bugs
module: search
tags: [htmx, htmx-1x, css, search, ux, loading-state]
symptoms:
  - "Old search results remain visible when a new search is submitted"
  - "CSS rule targeting htmx-request class on form has no effect"
  - "section:has(form.htmx-request) selector never matches"
date_solved: 2026-03-01
ticket: "#59"
---

# HTMX does not add htmx-request class to requesting element in 1.x

## Problem

When a user submitted a new search, the previous search results remained visible on the page until the new results finished loading. This was confusing because it looked like the old results still applied to the new query.

The expected behavior was: as soon as the user triggers a new search, the old results should be cleared immediately, replaced by a loading indicator, and then the new results should appear when ready.

## Root Cause

Three plan reviewers independently recommended a CSS-only fix using the `htmx-request` class that HTMX adds to the requesting element during an in-flight request:

```css
section:has(form.htmx-request) ~ #search-results {
  display: none;
}
```

This approach was implemented but had no effect. The root cause is a **version difference in HTMX behavior**:

- **HTMX 2.x**: Adds the `htmx-request` class to the element that triggered the request. The CSS approach works as expected.
- **HTMX 1.9.x**: Does NOT add `htmx-request` to the requesting element. The class is only applied to the `hx-indicator` element. The selector `form.htmx-request` never matches, so the CSS rule is never triggered.

The project uses **HTMX 1.9.10 via CDN**, making the CSS-only approach fundamentally incompatible with the runtime version.

## Solution

Use the `hx-on` attribute directly on the form element to clear the results container in the `htmx:beforeRequest` event. This fires immediately when the request begins, before any response is received.

**File:** `app/templates/index.html`

```html
<form hx-post="/api/search"
      hx-target="#search-results"
      hx-indicator="#search-spinner"
      hx-on="htmx:beforeRequest: document.getElementById('search-results').innerHTML = ''">
```

This is a single HTML attribute change with no JavaScript file additions. The `hx-on` attribute is supported in HTMX 1.9.x and executes inline JS for any HTMX lifecycle event. Setting `innerHTML = ''` on the results container instantly clears old results the moment the request fires, before the response arrives.

## Prevention

1. **Check the HTMX version before using version-specific features** — HTMX 1.x and 2.x have meaningful behavioral differences. The `htmx-request` class on the requesting element is 2.x only; do not rely on it in a 1.9.x project.
2. **Prefer `hx-on` for before-request side effects in HTMX 1.x** — When you need to perform an action at the start of a request (clear content, reset UI state), `hx-on="htmx:beforeRequest: ..."` is the correct 1.x pattern.
3. **Verify CSS selectors against the actual DOM** — When a CSS-only approach does not work, inspect the element in DevTools during the request to confirm whether the expected class is actually being applied.
4. **Lock the CDN version explicitly** — The project already pins `1.9.10` in the CDN URL. Keep it pinned. A silent upgrade to 2.x would change `hx-on` event name syntax and other behaviors.

**HTMX version compatibility quick reference:**

| Feature | HTMX 1.9.x | HTMX 2.x |
|---------|-----------|---------|
| `htmx-request` on requesting element | No | Yes |
| `htmx-request` on `hx-indicator` element | Yes | Yes |
| `hx-on="htmx:beforeRequest: ..."` | Yes | Yes (syntax unchanged) |

## Related

- **Files Changed**:
  - `/Users/nifemimadarikan/Documents/ClaudeCode/DS-PAL/app/templates/index.html` - Added `hx-on` attribute to search form

- **See Also**:
  - HTMX 1.9.x lifecycle event documentation
  - HTMX migration guide (1.x to 2.x) — covers `htmx-request` class behavior change
  - Pico CSS loading state patterns
