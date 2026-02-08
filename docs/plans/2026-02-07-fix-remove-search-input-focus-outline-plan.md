---
title: "Fix: Remove focus outline from search input box"
type: fix
date: 2026-02-07
ticket: 8
---

# Fix: Remove focus outline from search input box

## Context

The search input on the home page displays a visible blue outline ring (via Pico CSS `box-shadow`) when focused. Ticket #8 requests removing or restyling this to match the app's design while maintaining accessibility.

## Problem

Pico CSS v2.0.6 applies a `box-shadow` on input focus:
```css
input:not(...):focus {
  box-shadow: 0 0 0 var(--pico-outline-width) var(--pico-form-element-focus-color);
}
```

This is the only focus indicator — there is no `outline` property involved.

## Solution

Add a CSS override in `app/static/css/style.css` that targets the search input inside the fieldset group to:
1. Remove the `box-shadow` focus ring
2. Apply a subtle `border-color` change on focus for accessibility

```css
/* Search input — subtle focus style */
fieldset[role="group"] input[type="search"]:focus {
  box-shadow: none;
  border-color: var(--pico-primary);
}
```

## Files to Modify

- `app/static/css/style.css` — add the focus override (~3 lines)

## Verification

1. Run the web app (`python run.py`)
2. Click into the search input — confirm the blue outline ring is gone
3. Confirm a subtle border color change appears on focus (accessibility)
4. Tab through the page — confirm the search input is still visibly distinguishable when focused via keyboard
