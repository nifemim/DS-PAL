---
title: "Lazy imports reduce cold start time on Render free tier"
category: performance-issues
module: app-startup
tags: [performance, cold-start, render, lazy-imports, pandas, sklearn, plotly]
symptoms:
  - "App takes long to load on Render free tier"
  - "Slow cold start times"
  - "1.85s app startup time"
date_solved: 2026-03-01
ticket: "#56"
---

# Lazy imports reduce cold start time on Render free tier

## Problem

DS-PAL was taking ~1.85s to start on Render free tier. Cold starts were noticeably slow because heavy Python dependencies (pandas, scikit-learn, numpy, plotly, pyarrow) were all imported at module level through the router → service import chain.

## Root Cause

The import chain was: `app/main.py` → routers → services → heavy deps at module level.

Three service modules were the culprits:

- `dataset_loader.py` — `import pandas as pd` at top level. This was the most critical because ALL routers (pages, search, upload, analysis) import from this module, meaning pandas was guaranteed to load on every cold start regardless of what the user was doing.
- `analysis_engine.py` — `import numpy as np`, `import pandas as pd`, and 5 sklearn imports at top level.
- `visualization.py` — `import numpy as np`, `import plotly.graph_objects as go`, `import plotly.express as px` at top level.

Combined, these heavy deps accounted for ~1.2s of the 1.85s startup time.

## Investigation

1. Measured full app import time: 1.85s
2. Measured individual import times: pandas 0.58s, scikit-learn 0.65s (the two largest offenders)
3. Traced the import chain from each router through to the services to find which modules pulled in heavy deps
4. Identified `dataset_loader.py` as the critical path — because every router imports from it, pandas was loading on every cold start even before any user interaction with datasets

## Solution

Moved all heavy imports from module level into the functions that actually use them (lazy imports). Python caches imported modules after the first import, so there is zero runtime cost after the first call — only the cold start benefits.

### `app/services/dataset_loader.py`

Removed the top-level `import pandas as pd`. Added `import pandas as pd` inside each function that uses it: `detect_sheets()`, `join_sheets()`, `load_dataframe()`, and `_classify_column()`. Removed `pd.DataFrame` type hints from function signatures (replaced with bare types or no annotation) since the type is no longer available at module load time.

### `app/services/analysis_engine.py`

Removed all top-level imports of numpy, pandas, and sklearn. Added lazy imports inside each function that needs them:

- `encode_categoricals()`: `import pandas as pd; from sklearn.preprocessing import LabelEncoder`
- `preprocess()`: `import pandas as pd; from sklearn.preprocessing import StandardScaler`
- `reduce_dimensions()`: `import numpy as np; from sklearn.decomposition import PCA`
- `find_optimal_k()`: `from sklearn.cluster import KMeans; from sklearn.metrics import silhouette_score`
- `_auto_eps()`: `import numpy as np; from sklearn.neighbors import NearestNeighbors`
- `cluster()`: `from sklearn.cluster import KMeans, DBSCAN, AgglomerativeClustering; from sklearn.metrics import silhouette_score`
- `detect_anomalies()`: `import numpy as np; from sklearn.ensemble import IsolationForest`

Changed dataclass type hints that referenced `pd.DataFrame` to `object`.

### `app/services/visualization.py`

Removed top-level numpy and plotly imports. Created a `_get_imports()` helper function that returns a `(np, go, px, make_subplots)` tuple. Every chart function calls `_get_imports()` at the start instead of relying on module-level names. The `COLORS` constant was moved inside the functions that use it.

## Result

App startup time dropped from 1.85s to 0.46s — a 75% reduction. All 184 tests continued to pass. Heavy dependencies now only load on the first user interaction that actually requires them (loading a dataset or running analysis).

## Key Lesson

On free-tier PaaS platforms (Render, Heroku), every second of cold start time matters for user experience. Data science libraries are exceptionally heavy — pandas alone takes ~0.58s to import, scikit-learn ~0.65s. Moving imports to function level costs nothing at runtime (Python's module cache means subsequent calls to the same import are instantaneous) but can dramatically cut cold start times. The trick is identifying the critical import path: the module imported by the most other modules is where a lazy import has the greatest leverage.
