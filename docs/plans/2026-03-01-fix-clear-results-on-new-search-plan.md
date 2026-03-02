---
title: "fix: Clear existing results when starting a new search"
type: fix
date: 2026-03-01
ticket: 59
---

# fix: Clear existing results when starting a new search

When a user submits a new search, old results remain visible until the server responds. They should disappear immediately, leaving only the existing skeleton loader visible.

## Acceptance Criteria

- [x] Old search results hide instantly when a new search is submitted
- [x] Skeleton loader (already shown by `hx-indicator`) is the only visible element during the request
- [x] Behavior only triggers on form submit, not on clearing the input field

## Implementation

### `app/static/css/style.css`

One CSS rule. HTMX adds `.htmx-request` to the form element when a request is in flight. Use a sibling selector to hide the results section:

```css
section:has(form.htmx-request) ~ #search-results {
    display: none;
}
```

**Why this works:** The search form is inside a `<section>`, and `#search-results` is a sibling of that section. `:has()` targets the parent section when its child form has the `.htmx-request` class. HTMX already shows `#search-spinner` (which contains `partials/skeleton.html`) via the `hx-indicator` mechanism. The only missing piece is hiding old results — this CSS rule does exactly that, with zero JS and zero markup duplication.

**No JS changes needed.** No skeleton markup duplication. The existing `hx-indicator` + `partials/skeleton.html` infrastructure handles the loading state.

## References

- Brainstorm: `docs/brainstorms/2026-03-01-clear-results-on-new-search-brainstorm.md`
- Search form: `app/templates/index.html:25-37`
- Results container: `app/templates/index.html:41-43`
- Skeleton indicator: `app/templates/index.html:45-47`
- Skeleton partial: `app/templates/partials/skeleton.html`
- Pico `aria-busy` gotcha: `docs/solutions/ui-bugs/pico-css-interactive-elements-polish.md`
