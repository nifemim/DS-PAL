# Brainstorm: Change Accent Color to Purple

**Date:** 2026-02-08
**Ticket:** #19
**Status:** Ready for planning

## What We're Building

Override Pico CSS's default blue primary color with a soft/lavender purple (`#a78bfa`) across the entire app.

## Why This Approach

- Soft lavender purple gives the app a distinctive, modern feel
- Same shade for both light and dark mode keeps things simple and brand-consistent
- Pico CSS uses CSS custom properties for its primary color, so a single override applies everywhere

## Key Decisions

1. **Shade:** Soft/lavender purple — `#a78bfa` (Tailwind violet-400)
2. **Both modes:** Same shade for light and dark mode
3. **Method:** Override Pico CSS `--pico-primary` and related variables in `style.css`

## Open Questions

None — ready to plan.
