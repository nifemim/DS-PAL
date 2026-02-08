---
title: "Custom accent color override ignored in Pico CSS light mode"
category: ui-bugs
module: theming
tags: [css, pico-css, specificity, theming, custom-properties, dark-mode]
symptoms:
  - "Custom primary color only works in dark mode"
  - "Light mode ignores CSS variable overrides"
  - "Pico CSS accent color won't change"
  - "CSS custom properties not applying"
date_solved: 2026-02-08
ticket: "#19"
---

## Problem

After switching the app's accent color from Pico CSS default blue to a custom purple (`#a78bfa`), the override only applied in dark mode. Light mode continued showing the default blue accent color despite CSS custom properties being set.

## Root Cause

**CSS selector specificity mismatch.** Pico CSS v2.0.6 does not define its light-mode color variables on a plain `:root` selector. Instead, it uses a compound selector with higher specificity:

```css
/* Pico CSS internal selector for light mode variables */
:root:not([data-theme=dark]),
[data-theme=light] {
    --pico-primary: #1095c1;
    /* ... other variables ... */
}
```

This selector (`:root:not([data-theme=dark])`) is **more specific** than a plain `:root` because it includes a `:not()` pseudo-class with an attribute selector inside.

### What failed

**Attempt 1** — plain `:root`:

```css
/* DOES NOT WORK — lower specificity than Pico's selector */
:root {
    --pico-primary: #a78bfa;
}
```

**Attempt 2** — `[data-theme="light"]` only:

```css
/* DOES NOT WORK — doesn't match when no data-theme is set */
[data-theme="light"] {
    --pico-primary: #a78bfa;
}
```

This fails because on first load before JS sets the attribute, `<html>` has no `data-theme` attribute at all. Pico's `:root:not([data-theme=dark])` still matches (since it's `:root` that is NOT dark-themed), but `[data-theme="light"]` does not.

## Solution

Match Pico's exact selector pattern to achieve equal specificity (last-defined wins):

```css
/* app/static/css/style.css */
:root:not([data-theme="dark"]),
[data-theme="light"] {
    --pico-primary: #a78bfa;
    --pico-primary-hover: #8b5cf6;
    --pico-primary-focus: rgba(167, 139, 250, 0.5);
    --pico-primary-background: #a78bfa;
    --pico-primary-hover-background: #8b5cf6;
    --pico-primary-inverse: #fff;
}

[data-theme="dark"] {
    --pico-primary: #a78bfa;
    --pico-primary-hover: #8b5cf6;
    --pico-primary-focus: rgba(167, 139, 250, 0.375);
    --pico-primary-background: #a78bfa;
    --pico-primary-hover-background: #8b5cf6;
    --pico-primary-inverse: #fff;
}
```

**Why this works:** By using the same compound selector `:root:not([data-theme="dark"])`, our rule has identical specificity to Pico's. Since our stylesheet loads after Pico's CDN CSS, the cascade rule "last defined wins" applies and our values take effect.

### Key Variables to Override

When changing the primary accent color in Pico CSS, override all six related variables:

| Variable | Purpose |
|----------|---------|
| `--pico-primary` | Text links, form focus borders |
| `--pico-primary-hover` | Link/button hover state |
| `--pico-primary-focus` | Focus ring (use rgba for transparency) |
| `--pico-primary-background` | Filled buttons, badges |
| `--pico-primary-hover-background` | Filled button hover |
| `--pico-primary-inverse` | Text on primary background |

## Prevention

1. **Always inspect the framework's actual CSS selectors** before writing overrides. Minified CSS can hide compound selectors that affect specificity.
2. **Match the framework's selector pattern** rather than guessing a simpler one. Equal specificity + later source order is the cleanest override strategy.
3. **Test both themes** (and no-theme initial state) when overriding themed variables.
4. **Avoid `!important`** — matching specificity is cleaner and more maintainable.

### Quick Reference: Pico CSS v2 Theme Selectors

| Mode | Selector |
|------|----------|
| Light (default) | `:root:not([data-theme="dark"]),[data-theme="light"]` |
| Dark | `[data-theme="dark"]` |

## Related

- Pico CSS v2.0.6 color system
- Dark mode implementation (ticket #17)
- `app/static/css/style.css` — all custom style overrides
