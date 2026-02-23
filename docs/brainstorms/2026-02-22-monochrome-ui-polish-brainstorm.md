---
title: "Monochrome UI polish"
type: brainstorm
date: 2026-02-22
tickets: "#34, #35, #36, #37, #38, #39"
---

# Monochrome UI Polish

## What We're Building

A visual refinement pass that shifts the DS-PAL UI from purple-accented skeletal to a clean **black/white monochrome** aesthetic. All interactive elements (buttons, text, borders) adapt to the active theme — black in light mode, white in dark mode. The aurora gradient background stays as ambient color; purple is removed from all foreground UI.

The upload UI is consolidated into a small icon inside the search bar, and the search bar itself becomes transparent with a solid-fill Search button.

## Why This Approach

The purple accent created visual noise — buttons, borders, text, links, hover states all competing with the aurora background. A monochrome foreground lets the aurora be the sole color expression while making the UI feel cleaner and more intentional.

## Tickets & Key Decisions

### #34 — Font colors: white (dark) / black (light) everywhere
- Replace all `color: var(--pico-primary)` with theme-aware text colors
- Use `--pico-color` (Pico's built-in theme-aware text color) or explicit black/white tokens
- Applies to: body text, button text, link text, badges, stat cards

### #35 — Button borders: black/white instead of purple
- Replace `border: 1px solid var(--pico-primary)` with `var(--pico-color)` or explicit tokens
- Hover states also shift to black/white (no purple on hover)
- Applies to: all outlined buttons, secondary buttons, article borders

### #36 — Opaque block at top of page (navbar)
- The `@supports (backdrop-filter)` block still applies `--ds-glass-bg` on desktop, creating a visible rectangle
- Fix: remove the glass background entirely, keep `background: transparent` + `border-bottom`
- Or reduce glass opacity further / remove the `@supports` block

### #37 — Upload symbol inside search bar
- Small upload icon (arrow ↑ or paperclip) positioned inside the search input on the right
- Clicking it opens the native file picker
- After file selection: show filename inline + submit button (or auto-submit)
- Hidden `<input type="file">` triggered by the icon
- Remove the separate upload `<section>` entirely

### #38 — Transparent search bar fill
- Override Pico's default opaque input background
- `fieldset[role="group"] input[type="search"] { background: transparent; }`
- Border stays visible for affordance

### #39 — Solid Search button
- Black fill + white text in light mode
- White fill + black text in dark mode
- High contrast CTA that anchors the search bar

### Aurora — No changes
- Aurora gradient stays purple/pink/cyan as ambient background
- It provides the sole color expression in the UI

## Styling Decisions

### Links
- **Slightly muted by default** — use `var(--pico-muted-color)` (gray tone)
- **Darken + underline on hover** — shift to full `var(--pico-color)` (black/white) with underline
- Applies to: dataset titles, nav links, "Saved Analyses", any anchor text

### Badges & Stat Values
- **Monochrome with borders** — black/white text with a thin border, same treatment as buttons
- Replace `color: var(--pico-primary)` and `border: 1px solid var(--pico-primary)` on `.source-badge` and `.stat-card .value`

### Tabs & Active States
- **Analysis tabs: solid fill** — active tab gets a solid black/white background with contrasting text (same invert pattern as button hovers). Inactive tabs stay muted text, no border.
- **Nav active link: underline** — the current page's nav link gets a subtle underline. Other links stay plain.

### Hover & Focus States
- **Button hover: invert** — on hover, outlined buttons fill solid (black in light mode, white in dark mode) with contrasting text. Same visual as the Search button's resting state.
- **Link hover**: darken from muted gray to full black/white + underline (see Links section above)
- **Focus rings: monochrome** — focus outline matches theme color (black/white), no purple or blue accent. Keeps accessibility clear while staying on-brand.
- **Card hover** (chart containers, stat cards, saved cards): currently uses purple glow (`box-shadow: 0 0 12px rgba(167,139,250,0.15)`). Replace with a subtle black/white border highlight or a neutral shadow.

## Open Questions

1. After a file is selected via the search bar icon, should it auto-navigate to upload, or show a confirmation?
2. Should the upload icon disappear while search results are loading?

## Scope

| File | Changes |
|------|---------|
| `app/static/css/style.css` | Theme tokens, button styles, nav, search bar, remove purple |
| `app/templates/index.html` | Merge upload into search bar, remove upload section |
| `app/templates/base.html` | Possibly minor nav adjustments |
| `app/static/js/app.js` | Update upload trigger logic for in-search-bar icon |
