# Speed Up Analysis Pipeline and Cluster Description Generation

**Date:** 2026-03-09
**Ticket:** #79
**Status:** Brainstormed

## What We're Building

Optimize the analysis pipeline to reduce wait time on the loading page, and add progress step indicators so users know what's happening. Focused on small-medium datasets (<1000 rows) which are the most common use case.

## Why This Approach

**Approach A: Algorithm Tuning + Progress Steps** was chosen over full parallelization or lazy chart generation because:

- The biggest bottlenecks are algorithmic, not architectural (silhouette sweep going to k=70, double PCA, KMeans n_init=10)
- Small-medium datasets don't benefit much from parallelization — the overhead can exceed the savings
- Progress steps are simple to implement and dramatically improve perceived speed
- Avoids the complexity of lazy chart generation which would require significant refactoring

## Key Decisions

1. **Run PCA once (3D) and slice for 2D** — eliminates redundant PCA fit, ~50% reduction in PCA time
2. **Cap silhouette sweep at max_k=10** — currently `int(sqrt(n))` which is 70 for 5000 rows; most datasets don't need more than 10 clusters
3. **Lower KMeans n_init from 10 to 5** — halves KMeans cost with minimal quality impact on small datasets
4. **Add progress step tracking** — update `pending_analyses[id]` with current step name so the loading page can show "Preprocessing...", "Clustering...", "Generating charts..."
5. **Update loading template** — show the current pipeline step instead of a generic spinner

## Open Questions

- Should we add a "fast mode" toggle on the analysis form that uses even more aggressive settings (n_init=3, skip anomaly detection)?
- Should progress steps show estimated time remaining, or just the step name?

## Bottleneck Summary

| Component | Current | After Optimization |
|-----------|---------|-------------------|
| PCA (2D+3D) | 50-150ms (2 fits) | 25-75ms (1 fit) |
| Silhouette sweep | 200-800ms (up to k=70) | 50-200ms (max k=10) |
| KMeans clustering | 100-300ms (n_init=10) | 50-150ms (n_init=5) |
| Chart generation | 170-500ms | Same (not changed) |
| **Total pipeline** | **650ms-4.5s** | **~300ms-1.5s** |

## Next Steps

Run `/workflows:plan` to create implementation plan.
