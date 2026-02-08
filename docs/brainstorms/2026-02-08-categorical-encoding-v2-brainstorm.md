# Brainstorm: Categorical Encoding v2

**Date:** 2026-02-08
**Ticket:** #12
**Status:** Ready for planning

## What We're Building

Five improvements to categorical encoding and related analysis features:

1. **Per-column encoding override** — Dropdown per categorical column (auto / one-hot / label) so users can override the suggested encoding
2. **Reverse-mapped centroids** — Map label-encoded centroid values back to the closest original category name (e.g. `4.73` → `Sedan`)
3. **Correlation heatmap cleanup** — Suppress within-group correlations for one-hot encoded columns (replace sibling correlations with blank/dash)
4. **Adaptive DBSCAN eps** — Replace hardcoded `eps=0.5` with automatic k-distance graph method (always auto, no manual override)
5. **Label encoding ordinal warning** — Prominent warning when label encoding is applied to nominal data

## Key Decisions

1. **Encoding override UI:** Small `<select>` dropdown next to each categorical column checkbox with options: auto (default), one-hot, label
2. **Centroid display:** Map centroid float back to nearest original category label
3. **Heatmap:** Suppress (blank out) correlations between one-hot siblings from the same source column
4. **DBSCAN eps:** Always auto-select via k-distance knee detection — no user input
5. **Ordinal warning:** Show a visual warning badge/tooltip when label encoding is used on nominal data

## Current Architecture

- Encoding logic: `app/services/analysis_engine.py:encode_categoricals()`
- Cardinality threshold: 10 (one-hot ≤ 10, label > 10)
- Feature cap: 100 total features
- UI: `app/templates/partials/dataset_preview.html` (checkboxes + encoding badges)
- Cluster profiles: `analysis_engine.py:profile_clusters()` — top 5 features by z-deviation
- Correlation heatmap: `app/services/visualization.py:correlation_heatmap()`
- DBSCAN: `analysis_engine.py` line 268 — `eps=0.5`, `min_samples=max(5, N//100)`

## Open Questions

None — ready to plan.
