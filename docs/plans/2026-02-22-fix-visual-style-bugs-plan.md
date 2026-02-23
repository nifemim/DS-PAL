---
title: "fix: Visual style bugs — aurora, fonts, navbar, upload UI"
type: fix
date: 2026-02-22
tickets: "#29, #30, #31, #32, #33"
---

# fix: Visual style bugs — aurora, fonts, navbar, upload UI

Five visual bugs found after the aurora + skeletal UI overhaul (PR #12). All are CSS/template fixes — no backend changes.

## Acceptance Criteria

### #29 — Aurora effect too subtle
- [ ] Aurora gradient colors clearly visible in both light and dark modes
- [ ] Effect feels vibrant, not frosty/washed out
- [ ] Text remains readable over the gradient
- [ ] Inner pages also show noticeable aurora tint

### #30 — Font missing in dark mode
- [ ] Space Grotesk renders on headings in dark mode
- [ ] Space Grotesk renders on headings in light mode (no regression)

### #31 — Body font pairing for all text
- [ ] Body text uses Inter (or compatible pairing) across the entire app
- [ ] Headings remain Space Grotesk
- [ ] Both fonts render in light and dark modes
- [ ] Google Fonts link updated with body font family

### #32 — Rectangular block artifact in navbar
- [ ] No visible opaque rectangle behind the navbar
- [ ] Navbar visually blends with the aurora background
- [ ] Nav remains sticky and functional
- [ ] Subtle separation (border-bottom) replaces opaque background

### #33 — Sleek upload button
- [ ] Native file input is hidden
- [ ] Single compact button triggers file picker
- [ ] Selected filename shown inline before upload
- [ ] Upload submits automatically or via a confirm action
- [ ] Existing upload JS logic (enable/disable, spinner) still works

## Fixes

### 1. #29 — Increase aurora opacity (`style.css:14-16, 30-32, 448`)

**Root cause:** Aurora color opacities are 0.15–0.3 (barely visible). Inner pages also apply extra `opacity: 0.4`.

```css
/* style.css — Light theme tokens */
--ds-aurora-color-1: rgba(167, 139, 250, 0.55);   /* was 0.3 */
--ds-aurora-color-2: rgba(249, 168, 212, 0.45);    /* was 0.25 */
--ds-aurora-color-3: rgba(196, 181, 253, 0.4);     /* was 0.2 */

/* style.css — Dark theme tokens */
--ds-aurora-color-1: rgba(167, 139, 250, 0.45);    /* was 0.25 */
--ds-aurora-color-2: rgba(99, 102, 241, 0.35);     /* was 0.2 */
--ds-aurora-color-3: rgba(6, 182, 212, 0.3);       /* was 0.15 */
```

Inner pages (`body:not([data-page="home"])::before`): remove `opacity: 0.4` or increase to `0.7`.

### 2. #30 — Add font var to dark theme (`style.css:22-34`)

**Root cause:** `--ds-font-heading` is defined only in the light theme block (line 19). Dark theme block is missing it, so `var(--ds-font-heading)` resolves to nothing in dark mode.

```css
/* style.css — Add to [data-theme="dark"] block */
--ds-font-heading: 'Space Grotesk', system-ui, -apple-system, sans-serif;
```

### 3. #31 — Add body font pairing (`style.css:5-38`, `base.html:22`)

Add Inter as body font. Both fonts are geometric sans-serifs — Inter is optimized for body text readability.

```css
/* style.css — Add to BOTH theme blocks */
--ds-font-body: 'Inter', system-ui, -apple-system, sans-serif;

/* style.css — Add rule after h1-h6 block */
body {
    font-family: var(--ds-font-body);
}
```

```html
<!-- base.html — Update Google Fonts link -->
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@500;700&display=swap">
```

### 4. #32 — Fix navbar rectangle (`style.css:459-475`)

**Root cause:** `color-mix(in srgb, var(--pico-background-color) 92%, transparent)` creates an opaque block. The frosted glass `--ds-glass-bg` at 0.7 opacity compounds the issue. `contain: layout style paint` adds containment boundary.

```css
/* style.css — Nav fallback */
nav {
    position: sticky;
    top: 0;
    z-index: 100;
    background: transparent;                          /* was color-mix(...92%) */
    border-bottom: 1px solid var(--pico-muted-border-color);
}

/* style.css — Reduce glass opacity */
:root:not([data-theme="dark"]),
[data-theme="light"] {
    --ds-glass-bg: rgba(255, 255, 255, 0.35);        /* was 0.7 */
}

[data-theme="dark"] {
    --ds-glass-bg: rgba(20, 20, 30, 0.35);           /* was 0.7 */
}
```

Remove `contain: layout style paint` from nav.

### 5. #33 — Sleek upload button (`index.html:28-45`, `app.js:71-86`)

Replace the bulky `fieldset role="group"` file input with a hidden input + styled button.

```html
<!-- index.html — New upload section -->
<section style="text-align: center;">
    <p style="color: var(--pico-muted-color);">&mdash; or &mdash;</p>
    <form id="upload-form" action="/api/dataset/upload" method="post" enctype="multipart/form-data">
        <input type="file" id="upload-file" name="file"
               accept=".csv,.json,.xlsx,.xls,.parquet"
               style="display: none;"
               aria-label="Upload a dataset file">
        <button type="button" id="upload-pick-btn" class="secondary"
                onclick="document.getElementById('upload-file').click()">
            Upload a file
        </button>
        <span id="upload-filename" style="margin-left: 0.5rem; color: var(--pico-muted-color); font-size: 0.85rem;"></span>
        <button type="submit" id="upload-btn" style="display: none;">Upload &amp; Analyze</button>
        <br>
        <small style="color: var(--pico-muted-color);">CSV, Excel, JSON, or Parquet &middot; max {{ max_file_size_mb }} MB</small>
    </form>
</section>
```

```javascript
// app.js — Update upload logic
// On file select: show filename, show submit button
// On submit: show spinner, disable button
```

## Files to Modify

| File | Changes |
|------|---------|
| `app/static/css/style.css` | #29: aurora opacity, #30: dark font var, #31: body font var+rule, #32: nav background |
| `app/templates/base.html` | #31: add Inter to Google Fonts link |
| `app/templates/index.html` | #33: upload UI redesign |
| `app/static/js/app.js` | #33: update upload button JS |

## Verification

1. `pytest` — all tests pass (no backend changes)
2. Visual check `http://localhost:8000`:
   - Aurora colors vivid in both themes
   - Space Grotesk headings + Inter body in both themes
   - No rectangular block in navbar
   - Upload is a compact button with filename display
3. `prefers-reduced-motion` — animations disabled, static aurora still visible

## References

- PR #12: Original aurora + skeletal UI implementation
- `docs/solutions/ui-bugs/pico-css-color-override-specificity.md`: Pico theme selector pattern
- Pico CSS v2.0.6: Theme variable specificity requires compound selector
