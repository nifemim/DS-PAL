---
title: "fix: Monochrome UI polish — remove purple, refine controls"
type: fix
date: 2026-02-22
tickets: "#34, #35, #36, #38, #39"
brainstorm: "docs/brainstorms/2026-02-22-monochrome-ui-polish-brainstorm.md"
deepened: 2026-02-22
---

# fix: Monochrome UI polish — remove purple, refine controls

Remove all purple accents from foreground UI. All interactive elements adapt to the active theme — black in light mode, white in dark mode. Aurora gradient stays as sole color expression.

## Enhancement Summary

**Deepened on:** 2026-02-22
**Research agents used:** pattern-recognition-specialist, code-simplicity-reviewer, julik-frontend-races-reviewer, Pico CSS cascade analysis, WCAG accessibility research

### Key Improvements from Research
1. **Use #1a1a1a instead of #000** — softened black reduces eye strain while maintaining WCAG AAA (19:1+ contrast)
2. **Defer upload icon integration (#37)** — all 3 reviewers flagged it as over-engineered with race conditions; current upload section works well
3. **Reduced from 15 fixes to 8** — many original "fixes" were just confirmations that tokens cascade correctly
4. **Added disabled button styling** — missing from original plan, needed for monochrome
5. **Consolidated duplicate card hover styles** — single multi-selector rule
6. **Increased focus ring opacity** — `rgba(0,0,0,0.25)` may not meet WCAG 2.4.13; bumped to 0.4
7. **Remove redundant theme-toggle color rules** — after token change, they're unnecessary

### Deferred
- **#37 (Upload icon in search bar)**: Deferred based on review feedback. Integrating upload into the search fieldset introduces semantic confusion (3 buttons in one group), Enter-key ambiguity between search/upload forms, double-submission race conditions, and worse mobile UX. The current separate upload section is clean and robust. Revisit if user demand arises.

## Acceptance Criteria

### #34 — Font colors
- [ ] All text is near-black (#1a1a1a) in light mode
- [ ] All text is white (#fff) in dark mode
- [ ] No purple text anywhere in the UI

### #35 — Button borders
- [ ] Button borders are near-black in light mode, white in dark mode
- [ ] Button hover inverts: solid fill with contrasting text
- [ ] No purple borders anywhere
- [ ] Disabled buttons have reduced opacity (0.4) with muted border

### #36 — Navbar opaque block
- [ ] No visible opaque rectangle behind the navbar in either theme
- [ ] Nav remains sticky and functional
- [ ] Subtle border-bottom for separation

### #38 — Transparent search bar
- [ ] Search input has transparent background
- [ ] Border remains visible for affordance

### #39 — Solid Search button
- [ ] Search button is solid near-black with white text in light mode
- [ ] Search button is solid white with near-black text in dark mode

### Additional (from brainstorm)
- [ ] Active tabs: solid fill (invert pattern)
- [ ] Card hover: border highlight (no purple glow)
- [ ] Focus rings: monochrome, 0.4 opacity for WCAG compliance
- [ ] Plotly chart grid lines: neutral gray instead of purple
- [ ] Theme toggle color rules cleaned up (use token cascade)

## Technical Approach

### Critical: Pico CSS Specificity

Per `docs/solutions/ui-bugs/pico-css-color-override-specificity.md`, Pico v2.0.6 uses compound selectors. We **must** match their pattern:

```css
:root:not([data-theme="dark"]),
[data-theme="light"] {
    /* light theme overrides */
}

[data-theme="dark"] {
    /* dark theme overrides */
}
```

### Strategy: Update `--pico-primary` tokens

Change the root token values — this cascades to all Pico-styled elements automatically (buttons, links, focus rings, badges, stat values, cluster profile accents, source badges).

- Light mode: `--pico-primary: #1a1a1a` (softened black — WCAG AAA, easier on eyes than pure #000)
- Dark mode: `--pico-primary: #fff` (white)

**What cascades automatically (no manual CSS needed):**
- Button text and border colors
- Link colors
- Focus rings
- Source badge colors and borders
- Stat card value colors
- Cluster profile left border accent

**What needs manual CSS:**
- Hardcoded `rgba(167,139,250,...)` values (5 locations in CSS, 1 in JS)
- Button hover invert behavior (new interaction pattern)
- Tab active solid fill (new interaction pattern)
- Nav glass removal
- Search bar transparency

### Research Insight: Why #1a1a1a not #000

Pure black (#000) on white (#FFF) achieves maximum 21:1 contrast but causes eye strain for extended reading. #1a1a1a maintains WCAG AAA compliance (19:1+) while being significantly easier on the eyes. This is an industry best practice from UX accessibility research.

## Fixes

### 1. Update Pico primary tokens (`style.css:5-37`)

```css
/* Light theme */
:root:not([data-theme="dark"]),
[data-theme="light"] {
    --pico-primary: #1a1a1a;
    --pico-primary-hover: #000;
    --pico-primary-focus: rgba(0, 0, 0, 0.4);
    --pico-primary-background: #1a1a1a;
    --pico-primary-hover-background: #000;
    --pico-primary-inverse: #fff;
    --pico-primary-border: var(--pico-primary-background);
    --pico-primary-underline: rgba(0, 0, 0, 0.5);
    --pico-text-selection-color: rgba(0, 0, 0, 0.15);

    /* Aurora stays unchanged */
    --ds-aurora-color-1: rgba(167, 139, 250, 0.55);
    --ds-aurora-color-2: rgba(249, 168, 212, 0.45);
    --ds-aurora-color-3: rgba(196, 181, 253, 0.4);
    --ds-glass-bg: rgba(255, 255, 255, 0.35);
    --ds-glass-blur: 8px;
    --ds-font-heading: 'Space Grotesk', system-ui, -apple-system, sans-serif;
    --ds-font-body: 'Inter', system-ui, -apple-system, sans-serif;
}

/* Dark theme */
[data-theme="dark"] {
    --pico-primary: #fff;
    --pico-primary-hover: #ccc;
    --pico-primary-focus: rgba(255, 255, 255, 0.4);
    --pico-primary-background: #fff;
    --pico-primary-hover-background: #ccc;
    --pico-primary-inverse: #1a1a1a;
    --pico-primary-border: var(--pico-primary-background);
    --pico-primary-underline: rgba(255, 255, 255, 0.5);
    --pico-text-selection-color: rgba(255, 255, 255, 0.15);

    /* Aurora stays unchanged */
    --ds-aurora-color-1: rgba(167, 139, 250, 0.45);
    --ds-aurora-color-2: rgba(99, 102, 241, 0.35);
    --ds-aurora-color-3: rgba(6, 182, 212, 0.3);
    --ds-glass-bg: rgba(20, 20, 30, 0.35);
    --ds-font-heading: 'Space Grotesk', system-ui, -apple-system, sans-serif;
    --ds-font-body: 'Inter', system-ui, -apple-system, sans-serif;
}
```

**Research insights:**
- Focus ring opacity bumped to 0.4 (from 0.25) to meet WCAG 2.4.13 requirement of 3:1 contrast for focus indicators
- Added `--pico-primary-border`, `--pico-primary-underline`, and `--pico-text-selection-color` — Pico uses these internally for link underlines, form borders, and text selection highlighting. Without overriding them, they'd remain the default blue.

### 2. Button styles: full interaction state system (`style.css:49-86`)

Replace current button styles with monochrome invert pattern covering all states:

```css
/* Default: outlined */
button:not(.theme-toggle):not(.tab-btn):not([aria-label="Close"]),
[role="button"] {
    background: transparent;
    border: 1px solid var(--pico-primary);
    color: var(--pico-primary);
    cursor: pointer;
    transition: background-color 200ms ease-out,
                border-color 200ms ease-out,
                color 200ms ease-out,
                transform 100ms ease-out;
    -webkit-tap-highlight-color: transparent;
}

/* Hover: invert (fill solid) */
button:not(.theme-toggle):not(.tab-btn):not([aria-label="Close"]):not(:disabled):hover,
[role="button"]:not(:disabled):hover {
    background: var(--pico-primary);
    border-color: var(--pico-primary);
    color: var(--pico-primary-inverse);
}

/* Active/pressed: tactile feedback */
button:not(.theme-toggle):not(.tab-btn):not([aria-label="Close"]):not(:disabled):active,
[role="button"]:not(:disabled):active {
    transform: scale(0.98);
}

/* Focus-visible: keyboard navigation only (no outline on mouse click) */
button:not(.theme-toggle):not(.tab-btn):not([aria-label="Close"]):focus-visible,
[role="button"]:focus-visible {
    outline: 2px solid var(--pico-primary);
    outline-offset: 2px;
}

button:not(.theme-toggle):not(.tab-btn):not([aria-label="Close"]):focus:not(:focus-visible),
[role="button"]:focus:not(:focus-visible) {
    outline: none;
}

/* Primary buttons (submit): solid fill by default */
button[type="submit"],
button.primary {
    background: var(--pico-primary);
    color: var(--pico-primary-inverse);
}

/* Secondary/outline buttons: muted border */
button.secondary,
button.outline,
[role="button"].outline,
[role="button"].secondary {
    border-color: var(--pico-muted-border-color);
    color: var(--pico-color);
}

button.secondary:not(:disabled):hover,
button.outline:not(:disabled):hover,
[role="button"].outline:not(:disabled):hover,
[role="button"].secondary:not(:disabled):hover {
    border-color: var(--pico-primary);
    color: var(--pico-primary-inverse);
    background: var(--pico-primary);
}

/* Disabled buttons */
button:disabled,
[role="button"][aria-disabled="true"] {
    opacity: 0.4;
    cursor: not-allowed;
    pointer-events: none;
}
```

**Research insights:**
- **200ms ease-out** for color transitions, **100ms** for transform — industry standard for responsive feel
- **:focus-visible** prevents "sticky" outlines after mouse clicks while keeping keyboard navigation accessible (WCAG 2.4.7)
- **:active scale(0.98)** provides subtle pressed feedback without being distracting
- **-webkit-tap-highlight-color: transparent** removes default mobile blue flash; our :active state provides feedback instead
- **:not(:disabled)** guards on hover/active prevent visual state changes on disabled buttons
- WCAG exempts disabled elements from contrast — opacity 0.4 is sufficient

### 3. Card hover: consolidated (`style.css:265-268, 305-308, 337-339`)

Replace 3 duplicate purple glow rules with one consolidated rule:

```css
.chart-container:hover,
.stat-card:hover,
.saved-card:hover {
    border-color: var(--pico-primary);
}
```

**Research insight:** Shadow removed entirely — simpler, and border-color change provides sufficient hover feedback. Purple `rgba(167,139,250,0.15)` box-shadow was a hardcoded value that wouldn't cascade.

### 4. Tab active state: solid fill (`style.css:239-248`)

```css
.tab-btn {
    background: none;
    border: none;
    border-bottom: 3px solid transparent;
    padding: 0.75rem 1.25rem;
    cursor: pointer;
    font-size: 0.95rem;
    color: var(--pico-muted-color);
    margin-bottom: -2px;
}

.tab-btn:hover {
    color: var(--pico-color);
}

.tab-btn.active {
    color: var(--pico-primary-inverse);
    background: var(--pico-primary);
    border-bottom-color: var(--pico-primary);
    font-weight: 600;
    border-radius: 0.25rem 0.25rem 0 0;
}
```

### 5. Remove navbar glass effect (`style.css:466-482`)

Remove the entire `@supports (backdrop-filter)` block. The glass background (even at 0.35 opacity) creates a visible opaque rectangle.

```css
nav {
    position: sticky;
    top: 0;
    z-index: 100;
    background: transparent;
    border-bottom: 1px solid var(--pico-muted-border-color);
}

/* DELETE: the @supports (backdrop-filter: blur(1px)) block */
/* DELETE: the nav rules inside it */
```

Also delete `--ds-glass-bg` and `--ds-glass-blur` tokens from both theme blocks (only used by nav and modal; modal can use hardcoded values).

### 6. Search bar: transparent fill (`style.css`)

```css
/* Transparent search input */
fieldset[role="group"] input[type="search"] {
    background: transparent;
}
```

The Search button already gets solid fill from Fix #2 (`button[type="submit"]` rule).

### 7. Plotly chart grid colors (`app.js:5-15`)

Replace hardcoded purple grid colors:

```javascript
function getPlotlyThemeOverrides() {
    var isDark = document.documentElement.getAttribute("data-theme") === "dark";
    var gridColor = isDark ? "rgba(255,255,255,0.12)" : "rgba(0,0,0,0.08)";
    return {
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { color: isDark ? "#e0e0e0" : "#333" },
        xaxis: { gridcolor: gridColor, linecolor: gridColor, zerolinecolor: gridColor },
        yaxis: { gridcolor: gridColor, linecolor: gridColor, zerolinecolor: gridColor }
    };
}
```

### 8. Clean up redundant theme-toggle color rules (`style.css:134-140`)

After the token change, `var(--pico-primary)` resolves to black/white per theme. The hardcoded theme-toggle rules become redundant:

```css
/* REPLACE these two theme-specific rules: */
/* [data-theme="light"] .theme-toggle { color: #000; } */
/* [data-theme="dark"] .theme-toggle { color: #fff; } */

/* WITH a single rule: */
.theme-toggle {
    color: var(--pico-primary);
}
```

## Files to Modify

| File | Changes |
|------|---------|
| `app/static/css/style.css` | Pico tokens → monochrome, button hover invert + disabled state, tab active fill, remove nav glass, transparent search, consolidated card hover, theme-toggle cleanup |
| `app/static/js/app.js` | Plotly grid colors |

**No changes to:** `index.html` (upload section stays as-is), `base.html`

## Verification

1. `pytest` — all tests pass (no backend changes)
2. Visual check `http://localhost:8000`:
   - No purple anywhere in foreground UI
   - Buttons: near-black outlined (light) / white outlined (dark), invert on hover
   - Search: transparent input, solid Search button
   - Upload: current section unchanged, functional
   - Tabs: solid fill on active
   - Cards: border highlight on hover (no glow)
   - Aurora gradient visible and unchanged
3. Toggle light/dark mode — all elements adapt correctly
4. Keyboard navigation — focus rings visible in monochrome (0.4 opacity)
5. Disabled buttons — reduced opacity, no pointer events
6. Check `prefers-reduced-motion` — transitions disabled

## References

- Brainstorm: `docs/brainstorms/2026-02-22-monochrome-ui-polish-brainstorm.md`
- Pico specificity pattern: `docs/solutions/ui-bugs/pico-css-color-override-specificity.md`
- PR #12: Original aurora + skeletal UI implementation
- WCAG 2.1 Contrast: https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html
- WCAG 2.4.13 Focus Appearance: https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance.html
- UX Movement on pure black readability: https://uxmovement.com/content/why-you-should-never-use-pure-black-for-text-or-backgrounds/
