# Brainstorm: Dark Mode Support

**Date:** 2026-02-08
**Ticket:** #17
**Status:** Ready for planning

## What We're Building

Automatic dark mode that follows the user's OS preference, plus a manual toggle button (moon/sun icon) in the navbar. The user's choice is persisted in localStorage across sessions.

## Why This Approach

The codebase is already perfectly set up for this:
- **Pico CSS** handles all dark mode styling automatically via `data-theme` attribute
- **All custom CSS** uses Pico CSS variables (`--pico-primary`, `--pico-muted-color`, etc.) — zero hardcoded colors
- Only change needed: remove the hardcoded `data-theme="light"` and add a small JS toggle

Auto-detect + manual toggle gives users the best of both worlds with minimal code.

## Key Decisions

1. **Auto-detect OS preference** using `prefers-color-scheme` media query as the default
2. **Moon/sun toggle button** in the navbar — moon icon in light mode, sun icon in dark mode (icon shows what you'll switch to)
3. **Persist choice in localStorage** so it survives across sessions
4. **Pico CSS handles all theming** — no custom dark mode CSS needed

## Scope

### In Scope
- Remove hardcoded `data-theme="light"` from `<html>`
- Add theme detection JS (check localStorage, fall back to OS preference)
- Add moon/sun toggle button to navbar in `base.html`
- Toggle JS logic in `app.js`

### Out of Scope
- Server-side theme preference (no user accounts)
- Transition animations
- Custom color overrides for dark mode

## Open Questions

None — ready to plan.
