# Visual Style Update — Outline/Skeletal UI + Aurora Gradients

**Date:** 2026-02-22
**Ticket:** #28
**Status:** Brainstormed

## What We're Building

A visual style evolution of DS-PAL that combines two modern design languages:

1. **Aurora / Blurred Light Gradients** on the home page background — luminous, atmospheric radial gradients with soft motion, evoking northern-lights energy. Inner pages get a very subtle aurora hint (faint glow in one corner) for cohesion.
2. **Outline / Skeletal UI** for all components site-wide — hollow buttons, outlined cards, minimal fills, stroke-defined elements with deliberate negative space.

Additional polish:
- Frosted-glass navbar (semi-transparent with backdrop-blur)
- Frosted-glass modal dialogs
- Entrance animations (elements fade/slide in on page load and scroll)
- Subtle hover transitions on interactive elements
- Skeleton loading placeholders (pulsing outlined shapes) replacing the current spinner
- Space Grotesk display font for headings (system fonts for body text)
- `prefers-reduced-motion` respected — static fallbacks for all animations

## Why This Approach

**Aurora backgrounds + skeletal components** is the best blend because:
- Aurora sets an atmospheric mood without overwhelming the data-focused content
- Skeletal components keep the UI lightweight and modern, complementing the luminous backgrounds
- Limiting full aurora to the home page provides visual impact at the entry point while keeping inner pages clean and functional

**CSS-only implementation** chosen because:
- Zero new dependencies (aside from one Google Font) — everything lives in `style.css`
- Full control over dark/light mode via existing Pico CSS custom properties
- Easier to maintain long-term than canvas or animation libraries
- No risk of conflicts with HTMX partial page updates

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Style blend | Aurora backgrounds + skeletal components | Best of both — mood + clarity |
| Aurora scope | Full on home page, subtle hint on inner pages | Impact at entry point, cohesion throughout |
| Skeletal depth | Full conversion | All buttons, cards, badges, containers become outlined/hollow |
| Animations | Entrance animations + hover transitions | CSS `@keyframes`, fade/slide-in on load/scroll, smooth hovers |
| Color palette | Extend from existing purple (#a78bfa) | Add blue and pink gradient ranges; maintain brand identity |
| Dark mode gradients | Similar intensity, different tones | Warmer purples in light mode, cooler blues in dark mode |
| Navbar | Frosted glass (backdrop-blur) | Elegant, lets aurora show through on home page |
| Modal | Frosted glass (backdrop-blur) | Consistent with navbar treatment |
| Loading states | Skeleton placeholders | Pulsing outlined shapes replace the aria-busy spinner |
| Typography | Space Grotesk for headings | Geometric, techy feel that pairs with skeletal UI; system fonts for body |
| Chart colors | Subtle alignment only | Keep functional data colors; update chart backgrounds, gridlines, borders to match skeletal theme |
| Accessibility | Respect `prefers-reduced-motion` | Static gradients and no entrance animations for users who prefer reduced motion |
| Implementation | CSS-only (Approach A) | Zero dependencies, one file, dark-mode compatible |

## Scope of Changes

### Files to Modify

1. **`app/static/css/style.css`** — Primary target. Aurora gradients (pseudo-elements), skeletal component overrides, animations, frosted navbar/modal, skeleton loading, entrance keyframes.
2. **`app/templates/base.html`** — Add Google Fonts link for Space Grotesk. Add wrapper div or class for aurora background targeting. Add body class mechanism to identify the home page.
3. **`app/static/js/app.js`** — Intersection Observer for scroll-triggered entrance animations.
4. **`app/services/visualization.py`** — Update chart template/gridline styling to match skeletal theme (keep data colors as-is).
5. **Template partials** — Add CSS classes replacing any inline styles; no structural changes needed.

### Component Transformation Inventory

| Component | Current | Skeletal Target |
|-----------|---------|-----------------|
| Primary buttons | Filled purple background | Outlined, purple border, transparent fill |
| Secondary buttons | Filled grey | Outlined, grey border |
| Stat cards | 1px border, white/dark background | Outlined, transparent/semi-transparent background |
| Chart containers | 1px border, padded | Outlined, subtle glow on hover |
| Saved analysis cards | 1px border, filled background | Outlined, transparent |
| Source badge | Filled purple pill | Outlined purple pill, transparent fill |
| Cluster profiles | 4px left border, filled background | Outlined, transparent |
| Search result items | Bottom border separators | Keep as-is (already minimal) |
| Tabs | Bottom border active indicator | Keep pattern, add transition animation |
| Modal dialog | Filled solid background | Frosted glass effect (backdrop-blur) |
| Loading indicator | aria-busy spinner | Skeleton placeholders (pulsing outlined shapes) |
| Headings | System font | Space Grotesk (geometric, techy) |

### Aurora Effect Design

- CSS pseudo-element (`::before`) on the home page body/container
- Multiple `radial-gradient()` layers: purple center, blue edges, pink accents
- Subtle `@keyframes` animation for slow gradient movement (15-20s cycle)
- Reduced opacity (~0.3-0.4) so content remains readable
- **Light mode:** Warmer purple tones (purple → soft pink → lavender)
- **Dark mode:** Cooler blue tones (deep purple → blue → teal-tinged)
- Inner pages: single faint radial gradient in one corner, no animation

### Animation Plan

- **Entrance:** Elements use `opacity: 0; transform: translateY(20px)` initially, animate to visible on load/scroll via Intersection Observer
- **Hover transitions:** `transition: border-color 0.2s, box-shadow 0.2s` on cards and buttons
- **Tab switching:** Smooth opacity transition on tab panel content
- **Aurora motion:** Slow gradient position animation via `@keyframes`
- **Skeleton loading:** Pulsing opacity animation on placeholder shapes
- **Reduced motion:** All animations disabled via `@media (prefers-reduced-motion: reduce)` — static gradients, instant transitions, no entrance effects

## Open Questions

None — all major decisions resolved.

## Reference

- [Modern Web Design Styles Guide (2025)](https://dev.to/homayounmmdy/modern-web-design-styles-every-frontend-developer-must-know-2025-guide-part-2-131d)
- [Existing accent color brainstorm](./2026-02-08-accent-color-purple-brainstorm.md)
