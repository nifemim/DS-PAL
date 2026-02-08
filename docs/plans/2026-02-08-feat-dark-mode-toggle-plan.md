---
title: "feat: Add dark mode with OS auto-detect and manual toggle"
type: feat
date: 2026-02-08
ticket: 17
brainstorm: docs/brainstorms/2026-02-08-dark-mode-brainstorm.md
---

# feat: Add dark mode with OS auto-detect and manual toggle

## Overview

Add automatic dark mode that follows the user's OS preference, with a moon/sun toggle button in the navbar for manual override. Preference persists in localStorage. Pico CSS handles all theming — minimal custom code needed.

## Context

- Pico CSS v2.0.6 supports dark mode via `data-theme` attribute on `<html>`
- All custom CSS already uses Pico CSS variables — zero hardcoded colors
- Currently hardcoded to `data-theme="light"` in `base.html`
- Plotly charts need explicit theme-aware layout config (they don't read CSS variables)

## Approach

### 1. FOUC prevention — inline `<script>` in `<head>`

Add a blocking inline script in `<head>` (before CSS loads) that:
- Reads `localStorage.getItem('ds-pal-theme')`
- Falls back to `window.matchMedia('(prefers-color-scheme: dark)').matches`
- Sets `document.documentElement.setAttribute('data-theme', theme)` immediately

Remove the hardcoded `data-theme="light"` from `<html>`.

**File:** `app/templates/base.html`

```html
<html lang="en">
<head>
    <script>
        (function() {
            try {
                var t = localStorage.getItem('ds-pal-theme');
            } catch(e) {}
            if (!t) t = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', t);
        })();
    </script>
    <!-- rest of head -->
```

### 2. Toggle button in navbar

Add a `<button>` as the last item in the right-side `<ul>` of the navbar. Moon icon (`☾`) in light mode, sun icon (`☀`) in dark mode. Use Unicode characters for simplicity — no SVG or icon fonts needed.

**File:** `app/templates/base.html`

```html
<ul>
    <li><a href="/">Search</a></li>
    <li><a href="/saved">Saved Analyses</a></li>
    <li><button id="theme-toggle" aria-label="Toggle dark mode" class="theme-toggle">☾</button></li>
</ul>
```

### 3. Toggle logic in `app.js`

Add to `app/static/js/app.js`:

- `applyTheme(theme)` — sets `data-theme`, updates button icon/aria-label, saves to localStorage
- Click handler on `#theme-toggle` — toggles between light/dark
- On load: set correct icon based on current `data-theme`
- Listen for `storage` event for cross-tab sync
- Wrap all localStorage access in try-catch

### 4. Plotly chart theme integration

Modify the existing `htmx:afterSwap` Plotly re-render code in `app.js` to merge theme-aware layout:

```javascript
function getPlotlyThemeOverrides() {
    var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    return isDark
        ? { paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)', font: { color: '#e0e0e0' } }
        : { paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)', font: { color: '#333' } };
}
```

On theme toggle, re-render all visible Plotly charts with `Plotly.relayout()`.

### 5. Toggle button styling

Add minimal CSS for the toggle button so it looks like a navbar icon, not a form button.

**File:** `app/static/css/style.css`

```css
.theme-toggle {
    background: none;
    border: none;
    font-size: 1.25rem;
    cursor: pointer;
    padding: 0.25rem;
}
```

## Files to Modify

| File | Change |
|------|--------|
| `app/templates/base.html` | Remove `data-theme="light"`, add inline FOUC script, add toggle button |
| `app/static/js/app.js` | Add theme toggle logic, Plotly theme integration, cross-tab sync |
| `app/static/css/style.css` | Add `.theme-toggle` button styles |

## Edge Cases Handled

- **FOUC prevention**: Inline script in `<head>` runs before first paint
- **localStorage unavailable** (private browsing): try-catch fallback, theme works for session
- **Cross-tab sync**: `storage` event listener updates other tabs
- **OS theme change mid-session**: Only auto-follow if no manual preference stored
- **HTMX content swaps**: Inherit theme from `<html>` element — no special handling needed
- **Plotly charts**: Theme-aware layout overrides + re-render on toggle

## Out of Scope

- Server-side theme preference (no cookies/session)
- Transition animations
- Custom color overrides beyond Pico CSS defaults
- Analytics tracking

## Acceptance Criteria

- [x] First-time visitor sees theme matching their OS preference
- [x] Moon icon visible in navbar when in light mode, sun icon in dark mode
- [x] Clicking toggle switches theme instantly
- [x] Theme persists across page reloads and sessions
- [x] No flash of wrong theme on page load (FOUC prevented)
- [x] Plotly charts render with appropriate colors for current theme
- [x] Toggle works in private/incognito mode (no crash, just no persistence)
- [x] Other open tabs sync when theme is toggled
- [x] Toggle button is keyboard-accessible with appropriate aria-label
