---
title: "Pico CSS Interactive Elements Polish & Skeletal UI Overrides"
date: 2026-02-22
category: ui-bugs
tags:
  - pico-css
  - design-system
  - focus-states
  - dark-mode
  - plotly
  - skeleton-loading
  - border-radius
module:
  - app/static/css/style.css
  - app/templates/index.html
  - app/static/js/app.js
  - app/services/visualization.py
severity: medium
symptoms:
  - Plotly charts in segmentation tab unbounded height, excessive scrolling
  - Pico aria-busy spinner visible alongside custom skeleton UI
  - Rounded corners contradicting sharp design aesthetic
  - Search bar outline grey instead of theme-matched color
  - Search button border thickens when input is focused
  - Hyperlinks lack hover feedback
  - Theme toggle shows persistent focus border after click
  - Nav links display grey instead of primary color
  - Upload button misplaced in search bar with wrong icon
related:
  - docs/solutions/ui-bugs/pico-css-color-override-specificity.md
  - docs/brainstorms/2026-02-22-monochrome-ui-polish-brainstorm.md
  - docs/plans/2026-02-22-fix-monochrome-ui-polish-plan.md
tickets: "#37, #38, #39, #40, #41, #42, #43, #44, #45, #46"
commits:
  - "f782871: Cap chart heights, reposition upload button, remove Pico loading spinner"
  - "506541c: Remove all rounded edges, use sharp corners only"
  - "83c0aef: UI polish — upload link, search bar, hyperlink hover, nav colors"
---

# Pico CSS Interactive Elements Polish & Skeletal UI Overrides

## Problem

After implementing the Aurora visual style with skeletal UI, 10 visual issues remained across interactive elements, loading states, and chart sizing. All stemmed from Pico CSS defaults conflicting with the monochrome sharp-edged aesthetic.

## Root Causes

1. **Pico's `aria-busy` spinner**: Pico renders a loading spinner via `background-image` on any element with `aria-busy="true"`. Our skeleton UI partial used `aria-busy` for accessibility, triggering both spinners simultaneously.

2. **Pico's `border-radius`**: Pico sets `--pico-border-radius: 0.25rem` globally. Individual component overrides weren't enough — the variable itself needed zeroing.

3. **Pico's fieldset focus styles**: Pico adds box-shadow and border changes to buttons inside focused `fieldset[role="group"]`, causing the search button to appear thicker on input focus.

4. **Plotly default heights**: Charts without explicit `height` in their layout default to ~450px. Combined with `min-height: 400px` CSS and no max cap, charts grew unbounded.

5. **Pico's link colors**: Default link styling uses Pico's primary color with underline, not matching the monochrome button-like interaction pattern.

## Solutions

### 1. Suppress Pico's aria-busy spinner

```css
[aria-busy="true"]:not(button) {
    background-image: none !important;
}

[aria-busy="true"]:not(button)::before {
    display: none !important;
}
```

The `:not(button)` preserves spinner behavior on buttons (e.g., upload submit) while skeleton UI handles section-level loading.

### 2. Zero border-radius globally

Set the Pico variable in both theme blocks:

```css
:root:not([data-theme="dark"]),
[data-theme="light"] {
    --pico-border-radius: 0;
}

[data-theme="dark"] {
    --pico-border-radius: 0;
}
```

This cascades to all Pico components. Explicit `border-radius: 0` on custom components for defense.

### 3. Cap Plotly chart heights

Python side — explicit `height=400` on all charts:

```python
fig.update_layout(height=400)  # scatter_2d, scatter_3d, cluster_sizes, etc.
fig.update_layout(height=min(250 * rows, 900))  # feature_distributions
```

CSS side — container max-height:

```css
.chart-plot {
    width: 100%;
    min-height: 300px;
    max-height: 450px;
    overflow: hidden;
}
```

### 4. Lock search bar styles across focus states

```css
fieldset[role="group"] {
    border-color: var(--pico-primary);
    border-radius: 0;
}

fieldset[role="group"] > * {
    border-radius: 0 !important;
}

fieldset[role="group"] button {
    border: 1px solid var(--pico-primary) !important;
    box-shadow: none !important;
    outline: none !important;
}

fieldset[role="group"]:has(input[type="search"]:focus) {
    --pico-group-box-shadow-focus-with-button: 0 0 0 transparent;
    box-shadow: none;
    outline: none;
    border-color: var(--pico-primary);
}
```

### 5. Hyperlink solid fill on hover

```css
a {
    color: var(--pico-muted-color);
    text-decoration: none;
    transition: background 200ms, color 200ms;
    padding: 0.1em 0.3em;
}

a:hover,
a:active {
    background: var(--pico-primary);
    color: var(--pico-primary-inverse);
}
```

### 6. Theme toggle hover + focus reset

```css
.theme-toggle:hover {
    background: var(--pico-primary);
    color: var(--pico-primary-inverse);
}

.theme-toggle:focus,
.theme-toggle:focus-visible {
    outline: none !important;
    box-shadow: none !important;
    border: none !important;
}
```

### 7. Nav links use primary color

```css
nav a {
    color: var(--pico-primary);
}
```

### 8. Upload button replaced with text link

HTML: removed button from fieldset, added clickable text in hint line:

```html
<small>or <a href="#" id="upload-pick-btn" class="upload-link">upload</a> CSV, Excel, JSON, or Parquet</small>
```

JS: `e.preventDefault()` on click, "uploading..." feedback on file select.

## Prevention

- **Pico overrides**: Always check if Pico applies styles via CSS variables vs. direct selectors. Override the variable first, then add explicit fallbacks.
- **Chart heights**: Always set explicit `height` in Plotly `update_layout()`. Never rely on CSS `min-height` alone.
- **Focus states**: When using Pico's `fieldset[role="group"]`, test all focus combinations — Pico adds styles to sibling elements on focus, not just the focused element.
- **Interactive consistency**: Define hover/active behavior globally for `a` and `button` elements early, then override per-component as needed.

## Key Lesson

Pico CSS uses a layered specificity system: CSS variables > compound selectors > element defaults. To override cleanly:

1. Override the CSS variable (e.g., `--pico-border-radius: 0`)
2. Match Pico's selector specificity (e.g., `:root:not([data-theme="dark"])`)
3. Use `!important` sparingly, only for focus/shadow resets where Pico's specificity wins

See also: [Pico CSS Color Override Specificity](../ui-bugs/pico-css-color-override-specificity.md)
