---
title: "feat: Expand search providers for better dataset coverage"
type: feat
date: 2026-03-01
ticket: "#57"
reviewed: true
---

# feat: Expand search providers for better dataset coverage

## Overview

Search returns empty for common queries because only 2 of 4 providers are active (data.gov, HuggingFace). Kaggle requires user credentials and UCI's API is broken. Add 2 new providers (OpenML, AWS Open Data), remove broken UCI, and show provider attribution in search results.

## Problem Statement

- 4 providers registered, only 2 functional
- UCI permanently broken (API returns HTML instead of JSON)
- Kaggle silently disabled (placeholder credentials)
- Provider failures are silently swallowed — users see empty results with no explanation
- Friend feedback: "search is returning empty for a lot of common things"

## Proposed Solution

Add 2 new providers (OpenML, AWS Open Data), remove broken UCI, and show provider attribution in search results.

**Dropped from original plan (per review):**
- ~~Awesome Public Datasets~~ — regex-parsing a README.rst is fragile, no download URLs
- ~~Google Dataset Search~~ — no public API
- ~~ARFF support~~ — use OpenML's parquet URLs instead
- ~~Cache TTL~~ — YAGNI, static data doesn't need daily refresh
- ~~Startup caching~~ — use lazy loading to avoid slowing Render cold starts

## Implementation

### Phase 1: Add OpenML Provider (live API, highest value)

**`app/services/providers/openml_provider.py`**

- REST API at `https://www.openml.org/api/v1/json/data/list/data_name/{query}/limit/{n}`
- No auth required for reads
- Response includes: `did`, `name`, `format`, `quality` (row/column counts), tags
- Download via parquet URLs (not ARFF)
- Map `quality` fields to `size` (e.g., "150 rows × 5 cols")
- Truncate description to 300 chars, cap tags at 5

### Phase 2: Add AWS Open Data Provider (lazy-loaded NDJSON)

**`app/services/providers/aws_opendata_provider.py`**

- Fetch `https://s3.amazonaws.com/registry.opendata.aws/roda/ndjson/index.ndjson` on first search (lazy load)
- Cache datasets in memory as a list of dicts
- Search locally against `Name`, `Description`, `Tags` fields
- No auth, no rate limits (S3 static file)
- No direct download URLs (datasets are S3 buckets) — use registry page URL instead
- `dataset_id` = `Slug` field

### Phase 3: Remove UCI Provider, Wire New Providers, Add Attribution

**`app/services/providers/uci_provider.py`** — delete file

**`app/services/dataset_search.py`** — remove UCI from `PROVIDERS` list, add new providers, return provider names with results

**`app/templates/partials/search_results.html`** — show which providers returned results:
```
Results for "iris" (12 found) — from OpenML, HuggingFace, data.gov
```

**`app/services/dataset_loader.py`** — remove `_download_uci` handler, add OpenML parquet download handler

## Files to Create/Modify

| Action | File |
|--------|------|
| Create | `app/services/providers/openml_provider.py` |
| Create | `app/services/providers/aws_opendata_provider.py` |
| Delete | `app/services/providers/uci_provider.py` |
| Modify | `app/services/dataset_search.py` (swap providers, add attribution) |
| Modify | `app/templates/partials/search_results.html` (attribution line) |
| Modify | `app/services/dataset_loader.py` (remove UCI handler, add OpenML) |

## Acceptance Criteria

- [ ] OpenML search returns results for common queries ("iris", "titanic", "housing")
- [ ] AWS Open Data lazy-loaded on first search, searchable locally
- [ ] UCI provider removed (including dead code in dataset_loader.py)
- [ ] Search results show which providers returned results
- [ ] All new providers follow existing patterns (base class, error handling, 15s timeout)
- [ ] Existing tests pass

## Technical Considerations

- **Lazy loading**: AWS data fetched on first search, not at startup (important for Render cold starts)
- **OpenML name search**: The API does exact substring matching on `data_name`, not fuzzy search
- **AWS non-downloadable**: Results link to registry page — show "View on Registry" instead of download

## Dependencies

- No new pip packages needed (httpx already available)
- No auth credentials needed for any new provider

## References

- [OpenML REST API docs](https://docs.openml.org/ecosystem/Rest/)
- [AWS Open Data Registry NDJSON](https://s3.amazonaws.com/registry.opendata.aws/roda/ndjson/index.ndjson)
- Existing provider pattern: `app/services/providers/datagov_provider.py`
- Provider base class: `app/services/providers/base.py`
