# Brainstorm: Improve Relevance of LLM-Generated Cluster Labels

**Date:** 2026-02-09
**Ticket:** #24
**Status:** Ready for planning

## What We're Building

Make LLM-generated cluster labels domain-aware so they reflect the actual dataset being analyzed. Currently labels tend to be generic ("High-value group") rather than grounded in the dataset's domain ("Large-petaled flowers" for iris data, "Frequent weekend shoppers" for retail data).

Two changes: (1) improve the prompt to explicitly ground labels in the dataset's domain using existing metadata + few-shot examples, and (2) add an optional user-provided dataset description field that feeds into the prompt.

## Why This Approach

The current prompt gives the LLM the dataset name, column names, and feature statistics, but doesn't explicitly instruct it to infer the domain and use domain-specific vocabulary in labels. The LLM defaults to generic analytical language.

Combining stronger prompt instructions with an optional user description covers both cases: datasets with self-explanatory names/columns get better labels automatically, and datasets with opaque column names (e.g. "col_1", "V1") benefit from user-provided context.

## Key Decisions

1. **Domain grounding + few-shot examples in prompt** — Add explicit instructions telling the LLM to infer the dataset's domain from its name and column names, then ground cluster labels in that domain. Include a good/bad example showing what domain-specific labels look like vs generic ones.

2. **Optional user-provided dataset description** — Add a textarea where users can describe their dataset (e.g. "customer purchase data from an e-commerce store"). This feeds directly into the LLM user prompt as additional context. Not required — the prompt works without it.

3. **Description field in both places** — Set the description on the analysis config form (before running analysis), and allow editing it near the Regenerate button on the insights panel. Regenerating with updated context produces better labels.

4. **Store description in AnalysisOutput** — The dataset description needs to persist so it's available when regenerating insights. Add an optional `dataset_description` field to the analysis schema.

## UX Design

### Analysis Config Form

- **Position:** After column selection fieldsets, before the submit button
- **Element:** `<textarea>` with label "Dataset Description (optional)"
- **Placeholder:** "Describe your data to improve cluster labels (e.g. 'monthly sales by region')"
- **Behavior:** Optional — if empty, prompt relies on dataset name and column names only
- **Size:** 2-3 rows, full width, resizable

### Insights Panel (Regenerate)

- **Default state:** Shows current description as plain text (or "No description provided" in muted text)
- **Edit mode:** Click "Edit" link to expand into a textarea pre-filled with the existing description
- **Regenerate:** Picks up the updated description when re-fetching insights
- **Flow:** Text display → click Edit → textarea appears → edit → click Regenerate → insights refresh with new context

## Current Prompt Structure

The system prompt currently says:
- "Each entry has 'id' (integer), 'label' (2-4 word intuitive name like 'high-income urbanites')"

The user prompt includes:
- Dataset name, algorithm, cluster count
- Column names (via feature list)
- Per-cluster feature statistics with z-deviations

**What's missing:** No explicit instruction to infer domain. No example of domain-grounded vs generic labels. No user context field.

## Proposed Prompt Changes

Add to system prompt:
- "First, infer the domain of this dataset from its name and column names."
- "Labels MUST use domain-specific vocabulary — not generic analytical terms."
- A good/bad example: "For a flower dataset: GOOD: 'Large-petaled flowers'. BAD: 'High-value group'."

Add to user prompt:
- If user provided a description: "Dataset context: {description}"

## Open Questions

None — ready to plan.
