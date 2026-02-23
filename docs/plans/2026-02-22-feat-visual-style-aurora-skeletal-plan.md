---
title: "feat: Update visual style with aurora gradients and skeletal UI"
type: feat
date: 2026-02-22
deepened: 2026-02-22
reviewed: 2026-02-22
ticket: "#28"
brainstorm: docs/brainstorms/2026-02-22-visual-style-update-brainstorm.md
---

# feat: Update Visual Style with Aurora Gradients and Skeletal UI

## Overview

Evolve DS-PAL's visual style from "Pico CSS defaults + purple accent" to a modern design combining **Aurora / Blurred Light Gradients** (atmospheric backgrounds) with **Outline / Skeletal UI** (hollow, stroke-defined components). Includes a frosted-glass navbar and modal, skeleton loading placeholders, and Space Grotesk heading typography.

## Problem Statement

The current UI is functional but visually plain — flat backgrounds, solid-filled buttons, no visual depth. This update brings a distinctive, modern aesthetic while preserving the data-focused usability.

## Proposed Solution

A CSS-first approach that layers new visual effects onto the existing Pico CSS foundation. JavaScript changes are limited to Plotly theme expansion (~6 lines). No new JS files. No new CSS files. One Google Font added.

## Technical Approach

### Architecture

All changes go into existing files. No new CSS or JS files created (only one new HTML partial for skeleton loading).

```
app/static/
  css/
    style.css      # Add new sections: design tokens, aurora, skeletal, frosted glass, skeleton, reduced-motion
  js/
    app.js         # Expand getPlotlyThemeOverrides() (~6 lines)
app/templates/
  partials/
    skeleton.html  # New file: generic skeleton loading partial
```

**`base.html` head updates:**
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@2.0.6/css/pico.min.css">
<link rel="stylesheet" href="/static/css/style.css">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&display=swap">
```

> **Font loading:** The `&display=swap` parameter in the Google Fonts URL handles non-blocking rendering natively — no `media="print"` trick needed. `preconnect` to both Google Fonts domains eliminates ~100ms DNS latency.

### Design Specifications

#### Design Tokens (new section in `style.css`)

Use `--ds-` prefixed custom properties to avoid collision with Pico's `--pico-` namespace:

```css
/* === Design Tokens === */

:root:not([data-theme="dark"]),
[data-theme="light"] {
    /* Existing Pico overrides */
    --pico-primary: #a78bfa;
    --pico-primary-hover: #8b5cf6;
    /* ... other existing overrides ... */

    /* DS-PAL design tokens */
    --ds-aurora-color-1: rgba(167, 139, 250, 0.3);   /* purple */
    --ds-aurora-color-2: rgba(249, 168, 212, 0.25);  /* pink */
    --ds-aurora-color-3: rgba(196, 181, 253, 0.2);   /* lavender */
    --ds-glass-bg: rgba(255, 255, 255, 0.7);
    --ds-glass-blur: 8px;
    --ds-font-heading: 'Space Grotesk', system-ui, -apple-system, sans-serif;
}

[data-theme="dark"] {
    --ds-aurora-color-1: rgba(167, 139, 250, 0.25);  /* purple */
    --ds-aurora-color-2: rgba(99, 102, 241, 0.2);    /* indigo */
    --ds-aurora-color-3: rgba(6, 182, 212, 0.15);    /* cyan */
    --ds-glass-bg: rgba(20, 20, 30, 0.7);
}
```

> **Pico CSS specificity:** Must use `:root:not([data-theme="dark"]),[data-theme="light"]` and `[data-theme="dark"]` selectors to match Pico's compound specificity. Plain `:root` will NOT work.

#### Aurora Gradient

> **Critical performance rule:** NEVER animate gradient properties directly — they require CPU paint on every frame. Use a static gradient on an oversized pseudo-element and animate only `transform` (GPU-composited).

```css
/* === Aurora === */

body::before {
    content: "";
    position: fixed;
    top: -50%;
    left: -50%;
    width: 200%;
    height: 200%;
    z-index: -1;
    pointer-events: none;
    background:
        radial-gradient(ellipse at 30% 50%, var(--ds-aurora-color-1), transparent 50%),
        radial-gradient(ellipse at 70% 20%, var(--ds-aurora-color-2), transparent 45%),
        radial-gradient(ellipse at 50% 80%, var(--ds-aurora-color-3), transparent 50%);
    will-change: transform;
    contain: strict;
}

/* Home page: animated */
[data-page="home"]::before {
    animation: aurora-drift 20s ease-in-out infinite alternate;
}

/* Inner pages: static, subtle (single gradient, reduced opacity) */
body:not([data-page="home"])::before {
    width: 100%;
    height: 100%;
    top: 0;
    left: 0;
    background: radial-gradient(
        ellipse at 80% 10%,
        var(--ds-aurora-color-1),
        transparent 50%
    );
    opacity: 0.4;
}

@keyframes aurora-drift {
    0%   { transform: translate(0, 0) scale(1); }
    50%  { transform: translate(-5%, 3%) scale(1.05); }
    100% { transform: translate(3%, -2%) scale(1); }
}
```

**Why `body::before`:** Pure decoration with no semantic meaning. A pseudo-element keeps it out of the DOM, avoids HTMX swap conflicts, and requires no template changes.

> **Performance budget:** Apply `will-change: transform` ONLY to `body::before`. Each `will-change` promotes an element to its own GPU layer (~16MB VRAM per full-viewport layer at 2x DPI).

#### Frosted Glass

```css
/* === Frosted Glass === */

/* Navbar: solid fallback, then progressive enhancement */
nav {
    position: sticky;
    top: 0;
    z-index: 100;
    background: color-mix(in srgb, var(--pico-background-color) 92%, transparent);
    contain: layout style paint;
}

@supports (backdrop-filter: blur(1px)) {
    @media (min-width: 769px) {
        nav {
            background: var(--ds-glass-bg);
            backdrop-filter: blur(var(--ds-glass-blur));
            -webkit-backdrop-filter: blur(var(--ds-glass-blur));
        }
    }
}

/* Modal: transient, so backdrop-filter cost is acceptable */
#preview-modal[open] article {
    backdrop-filter: blur(var(--ds-glass-blur));
    -webkit-backdrop-filter: blur(var(--ds-glass-blur));
    background: var(--ds-glass-bg);
}
```

> Blur reduced from 12px to 8px. Gaussian blur cost grows quadratically — 8px is 54% cheaper than 12px for a nearly imperceptible visual difference. Desktop only via `@media (min-width: 769px)` to avoid mobile GPU cost.

#### Button Hierarchy (Skeletal)

| Variant | Style |
|---------|-------|
| Primary action (Search, Upload, Analyze) | Outlined with subtle tinted background (`rgba(167,139,250,0.1)`), purple border |
| Secondary action (Back, Cancel) | Fully hollow, muted border, transparent background |
| Destructive/utility (Delete, Regenerate) | Fully hollow, muted border (same as current `.outline.secondary`) |

> **Pico CSS integration:** Pico already has an `.outline` class for buttons. The skeletal conversion overrides the default filled button to become outlined. Primary buttons keep a subtle tint to preserve visual hierarchy.

#### Tab Switching

No changes. Keep the current `display: none` toggle — instant switching is better UX for a data analysis tool.

#### Skeleton Loading

Generic skeleton partial with pulsing outlined shapes replacing `aria-busy` spinners at all 5 loading locations.

> **Performance:** Use `opacity` pulse animation (GPU-composited), NOT `background-position` shimmer (triggers paint every frame).

```css
/* === Skeleton Loading === */

.skeleton-line {
    background: var(--pico-muted-border-color);
    border-radius: var(--pico-border-radius);
    animation: skeleton-pulse 1.5s ease-in-out infinite;
}

@keyframes skeleton-pulse {
    0%, 100% { opacity: 1; }
    50%      { opacity: 0.4; }
}

.sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
}
```

```html
<!-- partials/skeleton.html -->
<div aria-busy="true" role="status">
    <div class="skeleton-line" style="height:1.5rem; width:40%; margin-bottom:1rem;"></div>
    <div class="skeleton-line" style="height:1rem; width:100%; margin-bottom:0.75rem;"></div>
    <div class="skeleton-line" style="height:1rem; width:100%; margin-bottom:0.75rem;"></div>
    <div class="skeleton-line" style="height:1rem; width:60%;"></div>
    <span class="sr-only">Loading...</span>
</div>
```

**5 loading locations to update:**
1. `#search-spinner` in `index.html` — replaces "Searching datasets..."
2. `#modal-spinner` in `index.html` — replaces "Loading preview..."
3. `#analysis-spinner` in `analysis.html` — replaces "Loading analysis..."
4. `#saved-spinner` in `saved.html` — replaces "Loading saved analyses..."
5. `#cluster-insights` in `analysis_results.html` — replaces "Generating insights..."

**Accessibility:** Retains `aria-busy="true"` and `role="status"` on wrapper. Adds `.sr-only` text for screen reader announcement. Button-level `aria-busy` (upload button) stays as-is — skeleton is for section-level loading only.

#### Typography

```css
h1, h2, h3, h4, h5, h6 {
    font-family: var(--ds-font-heading);
}
```

#### Plotly Chart Alignment

Expand `getPlotlyThemeOverrides()` in `app.js` (~6 lines):

```javascript
function getPlotlyThemeOverrides() {
    var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    var gridColor = isDark ? 'rgba(167,139,250,0.15)' : 'rgba(167,139,250,0.12)';
    return {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: isDark ? '#e0e0e0' : '#333' },
        xaxis: { gridcolor: gridColor, linecolor: gridColor, zerolinecolor: gridColor },
        yaxis: { gridcolor: gridColor, linecolor: gridColor, zerolinecolor: gridColor }
    };
}
```

#### Tables

Keep Pico CSS default table styling. Tables serve a data purpose and do not need skeletal conversion.

#### Page Identification

Use `data-page` attribute on `<body>` (matches existing `data-theme` convention):

```html
<!-- base.html -->
<body {% block body_attrs %}{% endblock %}>

<!-- index.html -->
{% block body_attrs %}data-page="home"{% endblock %}
```

#### Accessibility — `prefers-reduced-motion`

```css
/* === Reduced Motion === */

@media (prefers-reduced-motion: reduce) {
    body::before,
    [data-page="home"]::before {
        animation: none;
    }

    .skeleton-line {
        animation: none;
    }

    nav {
        backdrop-filter: none;
        -webkit-backdrop-filter: none;
    }

    *, *::before, *::after {
        transition-duration: 0s !important;
    }
}
```

Disables aurora drift, skeleton pulse, backdrop-filter blur, and all hover transitions. Static aurora gradients and skeleton shapes remain visible.

### Implementation Plan

#### Phase 1: CSS — Tokens, Skeletal, Aurora, Frosted Glass, Skeleton, Accessibility

All CSS changes in `style.css`. All template updates for `data-page`, skeleton includes, and `.chart-plot` class extraction.

**Tasks:**
- [x] Add `/* === Design Tokens === */` section to `style.css` with `--ds-*` custom properties
- [x] Add `{% block body_attrs %}{% endblock %}` to `<body>` in `base.html`
- [x] Set `{% block body_attrs %}data-page="home"{% endblock %}` in `index.html`
- [x] Add `preconnect` links and Google Fonts `<link>` to `base.html` `<head>`
- [x] Add Space Grotesk `font-family` rule for `h1`–`h6`
- [x] Extract `.chart-plot` class from repeated inline styles (4 template files)
- [x] Override Pico button styles: primary gets tinted outline, default to transparent bg with border
- [x] Override Pico `<article>` background to transparent with border
- [x] Convert `.source-badge` from filled to outlined
- [x] Convert `.stat-card`, `.saved-card`, `.chart-container`, `.cluster-profile` to transparent bg
- [x] Update `.error-message` and `.success-message` to outlined style
- [x] Add `/* === Aurora === */` section: `body::before` pseudo-element, `@keyframes aurora-drift`
- [x] Scope animated aurora to `[data-page="home"]::before`, static hint to inner pages
- [x] Add `/* === Frosted Glass === */` section: sticky nav with `@supports` + `@media` guard, modal blur
- [x] Add hover glow transitions on cards: `transition: border-color 0.2s, box-shadow 0.2s`
- [x] Verify navbar doesn't overlap content (adjust `<main>` margin if needed)
- [x] Add `/* === Skeleton Loading === */` section: `.skeleton-line`, `@keyframes skeleton-pulse`, `.sr-only`
- [x] Create `app/templates/partials/skeleton.html`
- [x] Replace spinner content at all 5 loading locations with `{% include 'partials/skeleton.html' %}`
- [x] Keep `aria-busy="true"` and add `role="status"` on skeleton wrapper divs
- [x] Add `/* === Reduced Motion === */` section: `@media (prefers-reduced-motion: reduce)` block
- [x] Verify all conversions in both light and dark themes
- [x] Test readability of all text over aurora gradients in both themes

**Files:**
- `app/static/css/style.css` — add new sections (tokens, aurora, skeletal, frosted glass, skeleton, reduced-motion)
- `app/templates/base.html` — updated `<head>` (preconnect, Google Fonts, no CSS file changes), `body_attrs` block
- `app/templates/index.html` — set `data-page="home"`, replace 2 spinner locations
- `app/templates/partials/skeleton.html` — new file
- `app/templates/analysis.html` — replace spinner content
- `app/templates/saved.html` — replace spinner content
- `app/templates/partials/analysis_results.html` — replace insights spinner
- `app/templates/partials/cluster_charts.html` — `.chart-plot` class
- `app/templates/partials/section_eda.html` — `.chart-plot` class
- `app/templates/partials/section_segmentation.html` — `.chart-plot` class
- `app/templates/partials/analysis_detail.html` — `.chart-plot` class

#### Phase 2: JS — Plotly Theme

**Tasks:**
- [x] Expand `getPlotlyThemeOverrides()` in `app.js` with transparent backgrounds, gridline/axis colors (~6 lines)
- [x] Test with all chart types: scatter, bar, box, heatmap, parallel coordinates

**Files:**
- `app/static/js/app.js` — expand `getPlotlyThemeOverrides()`

---

## Acceptance Criteria

### Functional Requirements

- [ ] Home page displays aurora gradient background with animated drift (transform-based)
- [ ] Inner pages display subtle gradient hint (static, single glow)
- [ ] All buttons render as outlined/hollow with primary actions having tinted background
- [ ] All cards, badges, and containers render as outlined/transparent
- [ ] Navbar is sticky with frosted-glass blur effect (desktop only)
- [ ] Modal dialog has frosted-glass blur effect
- [ ] Loading states show skeleton placeholders (pulsing outlined shapes)
- [ ] Headings render in Space Grotesk font
- [ ] Plotly chart gridlines/borders match skeletal theme

### Non-Functional Requirements

- [ ] Both light and dark themes work correctly with all visual changes
- [ ] `prefers-reduced-motion` disables all animations and transitions (aurora, skeleton pulse, hover transitions, backdrop-filter)
- [ ] `backdrop-filter` fallback provides usable UI on unsupported browsers / mobile
- [ ] No WCAG contrast ratio regressions on text over gradient backgrounds
- [ ] `aria-busy` and `role="status"` semantics preserved on skeleton loading placeholders
- [ ] Plotly data colors remain unchanged (only chrome/borders updated)

### Quality Gates

- [ ] Tested in both light and dark modes
- [ ] Tested with `prefers-reduced-motion: reduce` enabled (macOS accessibility setting)
- [ ] Tested on mobile viewport (responsive grids collapse correctly)
- [ ] CSS sections clearly separated with comment headers
- [ ] No new event listener leaks introduced

## Dependencies & Prerequisites

- **Pico CSS v2.0.6** — no version change; overrides use existing custom property system
- **Google Fonts CDN** — Space Grotesk (`&display=swap` for non-blocking)
- **Browser support:** `backdrop-filter` (Chrome 76+, Firefox 103+, Safari 9+); `@supports` (all modern); `color-mix()` (Chrome 111+, Firefox 113+, Safari 16.2+)

## Risk Analysis & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Aurora GPU paint on every frame | High (if wrong) | High | Use `transform`-only animation on oversized static gradient; NEVER animate gradient properties |
| Pico CSS update breaks overrides | Low | High | Pin to v2.0.6 via CDN URL (already pinned) |
| Google Fonts blocked by firewall | Low | Low | `font-display: swap`; system font fallback in `--ds-font-heading` |
| `color-mix()` unsupported | Low | Low | Falls back to solid background |
| Outlined buttons reduce action clarity | Medium | Medium | Primary buttons retain subtle tinted background |
| `backdrop-filter` not supported | Low | Low | Solid `color-mix()` background fallback via `@supports` guard |

## What Was Cut (and Why)

| Cut | Reason |
|-----|--------|
| 3-file CSS split (`tokens.css`, `effects.css`) | 500-600 lines doesn't warrant multiple files. Comment section headers suffice. |
| Separate `animations.js` | No entrance animations = no new JS file needed |
| Entrance animations (Intersection Observer) | HTMX swaps entire lists at once — elements never individually scroll into view. The observer, safe arming, HTMX lifecycle hooks, and 3-class state machine added significant complexity for no user-visible benefit. |
| Scroll-pause mechanism | Aurora uses `transform`-only animation on a `contain: strict` pseudo-element — already GPU-composited, no repaint during scroll |
| Staggered Plotly chart rendering | Premature optimization without evidence of a problem |
| `media="print"` font loading trick | `&display=swap` handles non-blocking rendering natively |
| 4 implementation phases | Reduced to 2 — CSS styling doesn't warrant phase gates |

## Future Considerations (Deferred)

- **Entrance animations** — reconsider if the app adds infinite-scroll or lazy-loaded content where items genuinely scroll into view
- **CSS `@property`** — enables smooth gradient color interpolation; could replace transform-based aurora with color-cycling aurora
- **View Transitions API** — smooth page-to-page aurora transitions (limited browser support)

## References & Research

### Internal References

- Brainstorm: `docs/brainstorms/2026-02-22-visual-style-update-brainstorm.md`
- Current CSS: `app/static/css/style.css` (341 lines)
- Current JS: `app/static/js/app.js` (186 lines)
- Pico CSS specificity learning: `docs/solutions/ui-bugs/pico-css-color-override-specificity.md`
- Search results layout learning: `docs/solutions/ui-bugs/search-results-grid-hard-to-scan.md`

### External References

- [Modern Web Design Styles Guide](https://dev.to/homayounmmdy/modern-web-design-styles-every-frontend-developer-must-know-2025-guide-part-2-131d)
- [Space Grotesk on Google Fonts](https://fonts.google.com/specimen/Space+Grotesk)
- [Pico CSS v2 Documentation](https://picocss.com/docs)
- [CSS GPU Animation: Doing It Right — Smashing Magazine](https://www.smashingmagazine.com/2016/12/gpu-animation-doing-it-right/)
- [backdrop-filter Browser Support — Can I Use](https://caniuse.com/css-backdrop-filter)
