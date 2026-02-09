# Brainstorm: Multi-Sheet Excel Support

**Date:** 2026-02-08
**Ticket:** TBD
**Status:** Ready for planning

## What We're Building

When a user uploads an Excel file with multiple worksheets, show a sheet selection page where they can either:
1. **Pick one sheet** to analyze directly (same flow as today)
2. **Select multiple sheets** and join them on auto-detected shared columns before analysis

Single-sheet Excel files skip the selection page entirely — same behavior as today.

## Why This Approach

The current upload flow reads only the first sheet (`pd.read_excel(file_path)` with no `sheet_name` param). Users with multi-sheet workbooks lose access to all but the first sheet. Rather than forcing users to convert to CSV first, we detect multi-sheet files at upload time and insert a lightweight selection step before the existing preview/analysis pipeline.

The join feature addresses a common pattern: related data split across sheets (e.g., "Orders" + "Customers" joined on `customer_id`). Auto-detecting shared column names keeps it simple while covering the majority of real-world cases.

## Key Decisions

1. **Sheet selection page:** Redirect-based (matches existing upload flow). Only appears for multi-sheet files. Shows sheet names, row counts, and column names for each sheet.
2. **Single vs. multiple selection:** User can pick one sheet (radio button → straight to preview) or check multiple sheets (checkboxes → join flow).
3. **Join key detection:** Auto-detect columns with matching names across selected sheets. Suggest them as join key candidates. User confirms which column to join on.
4. **Join type:** Three options — inner, left, outer. Default to inner.
5. **Sequential pairwise join:** When 3+ sheets selected, join A+B first, then result+C, etc. User picks one join key per pair.
6. **Join preview:** After joining, show a preview (row count, column count, sample rows) before committing to analysis. User can go back and adjust.
7. **Single-sheet files:** Skip selection, redirect straight to dataset preview (no behavior change).
8. **Storage:** The joined DataFrame is saved as a new CSV in the cache (alongside the original .xlsx). The analysis pipeline loads the joined CSV, not the original Excel file.

## User Flow

```
Upload .xlsx
    ↓
Detect sheets (pd.ExcelFile)
    ↓
┌── 1 sheet ──→ Skip, redirect to /dataset/upload/{id} (today's flow)
│
└── 2+ sheets ──→ Redirect to /dataset/upload/{id}/sheets
                      ↓
                  Sheet Selection Page
                  ┌─────────────────────────────────┐
                  │ Your file has 3 sheets:          │
                  │                                  │
                  │ ○ Orders (1,240 rows, 8 cols)    │
                  │ ○ Customers (350 rows, 5 cols)   │
                  │ ○ Products (89 rows, 4 cols)     │
                  │                                  │
                  │ [Use Selected Sheet]              │
                  │                                  │
                  │ ☐ Select multiple to join         │
                  │ [Join & Preview]                  │
                  └─────────────────────────────────┘
                      ↓
              ┌── 1 selected ──→ load that sheet, redirect to preview
              │
              └── 2+ selected ──→ Join Configuration
                                  ┌───────────────────────────┐
                                  │ Join: Orders + Customers   │
                                  │ Shared columns detected:   │
                                  │   • customer_id ✓          │
                                  │ Join type: [inner ▾]       │
                                  │                            │
                                  │ [Preview Join Result]      │
                                  └───────────────────────────┘
                                      ↓
                                  Join Preview
                                  ┌───────────────────────────┐
                                  │ Joined result:             │
                                  │ 1,180 rows × 12 columns   │
                                  │ (table preview)            │
                                  │                            │
                                  │ [Proceed to Analysis]      │
                                  │ [Back — Adjust Join]       │
                                  └───────────────────────────┘
                                      ↓
                                  Save joined CSV to cache
                                  Redirect to /dataset/upload/{id}
```

## Current Architecture

- Upload saves to: `.cache/datasets/upload_{uuid}/data.xlsx`
- Excel loading: `pd.read_excel(file_path, nrows=max_rows)` — first sheet only
- Preview pipeline: `load_dataframe()` → `build_preview()` → template
- Upload endpoint: `POST /api/dataset/upload` → validate → save → 303 redirect
- Dataset page: `GET /dataset/{source}/{dataset_id}` → download_dataset → load → preview

## Edge Cases

- **No shared columns between selected sheets:** Show clear error — "No matching column names found. Sheets cannot be joined automatically."
- **Multiple shared columns:** Let user pick which one to use as the join key
- **Duplicate column names after join:** pandas handles this with `_x`/`_y` suffixes by default — acceptable
- **Very large joins:** The existing `max_dataset_rows` (10,000) limit applies to the joined result
- **Sheets with incompatible join key types:** Coerce both to string before joining, with a warning

## Open Questions

None — ready to plan.
