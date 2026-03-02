# DS-PAL — Dataset Pre-processing, Analysis, and Learning

A dataset analysis platform with clustering, anomaly detection, interactive visualizations, and an AI assistant. Includes a CLI-based ticket manager for tracking fix-later items.

## Features

**Web Application**
- Search datasets from Kaggle, HuggingFace, data.gov, OpenML, Socrata, Zenodo, and AWS Open Data
- Upload datasets: CSV, JSON, Excel (.xlsx), Parquet
- Preview dataset structure with column classification and cardinality info
- Multi-sheet Excel support with join configuration
- Automatic categorical column encoding (one-hot for low cardinality, label encoding for high cardinality)
- Toggle categorical columns on/off with encoding method badges in the UI
- Run clustering analysis (K-Means, DBSCAN, Hierarchical) on numeric and categorical data
- Detect anomalies with Isolation Forest
- Interactive Plotly visualizations (2D/3D scatter, parallel coordinates, heatmaps)
- Transformation notices showing which columns were encoded and how
- Save and manage analysis results with encoding metadata
- Dark mode with automatic OS preference detection and manual toggle

**PAL Chat Assistant**
- AI-powered help and feedback collection widget
- Powered by HuggingFace Inference API
- Answers DS-PAL usage questions and general data science questions
- Built-in feedback collection mode — type "feedback" to share thoughts
- Conversation history with session persistence
- Debug-only feedback review page at `/feedback`

**CLI Ticket Manager**
- Track bugs and tasks with priorities and tags
- Filter by status, priority, or tag
- Mark tickets as solved with resolution notes
- View aggregate statistics

## Installation

```bash
# Clone the repo
git clone https://github.com/nifemim/DS-PAL.git
cd DS-PAL

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies and register CLI
pip install -r requirements.txt
pip install -e .

# Copy environment config
cp .env.example .env
# Edit .env with your API keys (optional, for Kaggle/HuggingFace access)
```

## Usage

### Web Application

```bash
python run.py
# Open http://localhost:8000
```

### CLI Ticket Manager

```bash
# Add tickets
tickets add "Fix the login bug" --priority high --tags "auth,urgent"
tickets add "Refactor search" -d "Extract common provider logic" -p low

# List and filter
tickets list
tickets list --status open --priority high --tag ui

# View details
tickets show 1

# Update and solve
tickets update 1 --priority critical --status in_progress
tickets solve 1 -r "Fixed in commit abc123"

# Delete and stats
tickets delete 1
tickets stats

# Clean up ticket formatting (reword titles/descriptions)
tickets cleanup 1              # single ticket
tickets cleanup 1 2 3          # multiple tickets
tickets cleanup --all          # all tickets
tickets cleanup --all --dry-run  # preview changes only
```

## Configuration

Environment variables (see `.env.example`):

| Variable | Description | Default |
|----------|-------------|---------|
| `KAGGLE_USERNAME` | Kaggle API username | - |
| `KAGGLE_KEY` | Kaggle API key | - |
| `HUGGINGFACE_TOKEN` | HuggingFace API token (also powers PAL chat) | - |
| `APP_HOST` | Server host | `0.0.0.0` |
| `APP_PORT` | Server port | `8000` |
| `APP_DEBUG` | Enable debug mode | `true` |
| `DATABASE_PATH` | SQLite database path | `ds_pal.db` |
| `MAX_DATASET_ROWS` | Max rows to load | `10000` |
| `MAX_FILE_SIZE_MB` | Max file size (MB) | `50` |

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test files
pytest tests/test_analysis.py -v
pytest tests/test_dataset_loader.py -v
pytest tests/test_ticket_service.py -v
```

## System Design

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser                              │
│  Pico CSS + HTMX 1.9 + Plotly.js + Jinja2 Templates        │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP (HTML partials, forms)
┌──────────────────────────▼──────────────────────────────────┐
│                     FastAPI App                              │
│                                                              │
│  Routers          Services            Providers              │
│  ───────          ────────            ─────────              │
│  pages.py         analysis_engine.py  datagov_provider.py    │
│  search.py        dataset_loader.py   huggingface_provider.py│
│  upload.py        dataset_search.py   kaggle_provider.py     │
│  analysis.py      search_ranker.py    openml_provider.py     │
│  saved.py         visualization.py    aws_opendata_provider.py│
│  chat.py          insights.py         socrata_provider.py    │
│                   storage.py          zenodo_provider.py     │
└─────┬──────────────────┬───────────────────┬────────────────┘
      │                  │                   │
      ▼                  ▼                   ▼
  SQLite (WAL)    File Cache (.cache/)   External APIs
  ─ analyses      ─ downloaded datasets  ─ HuggingFace
  ─ visualizations                       ─ data.gov (CKAN)
  ─ search_history                       ─ Kaggle
  ─ chat_messages                        ─ OpenML
  ─ tickets                              ─ AWS Open Data (S3)
                                         ─ Socrata
                                         ─ Zenodo
```

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Home page with search and upload |
| `GET` | `/saved` | Saved analyses list |
| `GET` | `/analysis/{id}` | Analysis detail page |
| `GET` | `/dataset/{source}/{id}` | Dataset preview + config page |
| `POST` | `/api/search` | Fan-out search across 7 providers |
| `GET` | `/api/search/suggest` | Autocomplete from search history |
| `POST` | `/api/dataset/upload` | Upload CSV/Excel/JSON/Parquet |
| `POST` | `/api/dataset/preview` | Download and preview a dataset |
| `POST` | `/api/analyze` | Run clustering + anomaly detection |
| `POST` | `/api/analysis/{id}/save` | Persist analysis to database |
| `DELETE` | `/api/saved/{id}` | Delete a saved analysis |
| `POST` | `/api/chat/message` | Chat with PAL assistant |

### Data Flow

**Search → Analyze → Save:**

1. User types a query. HTMX sends `POST /api/search` which fans out to 7 providers concurrently via `asyncio.gather()`. Results are ranked by fuzzy relevance (`rapidfuzz`) and returned as an HTML partial.
2. Clicking a result opens a modal preview (`POST /api/dataset/modal-preview`). The dataset is downloaded, cached locally, and loaded into a pandas DataFrame. Column types, cardinality, and encoding suggestions are computed.
3. User selects columns and algorithm, then submits `POST /api/analyze`. The analysis engine preprocesses data (handle missing values, encode categoricals, scale features), runs the chosen algorithm (K-Means, DBSCAN, or Hierarchical), and generates 9 Plotly visualizations.
4. Results are held in memory (`pending_analyses`, TTL 1 hour) until the user saves them to SQLite.

**Upload path:** File upload → validate size/type → cache to disk → redirect to `/dataset/upload/{id}`. Excel files with multiple sheets get a sheet selection step with optional join configuration.

### Dataset Providers

All providers implement the `DatasetProvider` abstract base class (`search()` + `download_url()`). Search is concurrent — all 7 providers are queried in parallel, failures are silently caught so one broken provider doesn't block results.

| Provider | API | Auth | Notes |
|----------|-----|------|-------|
| data.gov | CKAN REST API | None | Filters to CSV/JSON resources with download URLs |
| HuggingFace | `huggingface.co/api/datasets` | Optional token | Filters to tabular datasets |
| Kaggle | Kaggle Python library | Username + key | Requires credentials to function |
| OpenML | `openml.org/api/v1/json` | None | ML benchmark datasets, parquet downloads |
| AWS Open Data | S3 static NDJSON | None | Lazy-loaded on first search, searched locally |
| Socrata | Discovery API | None | Government portals, SODA CSV export for download |
| Zenodo | REST API | None | Academic datasets hosted by CERN |

### Database Schema

SQLite with WAL mode and foreign keys enabled. Five tables:

- **analyses** — saved analysis results (config, algorithm output, metadata)
- **visualizations** — Plotly chart JSON linked to analyses (cascade delete)
- **search_history** — logged queries for autocomplete suggestions
- **chat_messages** — PAL conversation history with feedback flag
- **tickets** — CLI-managed bug/task tracker

### ML Pipeline

The analysis engine (`analysis_engine.py`) runs this pipeline:

1. **Preprocessing** — drop ID-like columns, handle missing values (drop rows or impute median/mode)
2. **Encoding** — one-hot encode low-cardinality categoricals, label encode high-cardinality
3. **Scaling** — StandardScaler on all features
4. **Clustering** — K-Means (with silhouette scoring), DBSCAN (eps/min_samples), or Hierarchical (Ward linkage)
5. **Anomaly Detection** — Isolation Forest with configurable contamination
6. **Dimensionality Reduction** — PCA to 2D and 3D for visualization
7. **Profiling** — cluster centroids, feature importance, correlation matrix, column stats

### Frontend Stack

- **Pico CSS 2.0** — classless CSS framework with dark/light theme support
- **HTMX 1.9** — server-rendered HTML partials, no client-side framework
- **Plotly.js 2.27** — interactive charts (scatter, heatmap, parallel coordinates, etc.)
- **Custom CSS** — aurora gradient background, glassmorphism, Space Grotesk/Mono fonts
- **No build step** — static files served directly by FastAPI

## Project Structure

```
app/
├── cli/                  # CLI ticket manager
│   ├── __main__.py       # argparse entry point
│   ├── tickets.py        # subcommand handlers
│   ├── _cleanup.py       # ticket cleanup/reformat logic
│   └── _formatter.py     # output formatting
├── models/
│   └── schemas.py        # Pydantic models
├── routers/              # FastAPI routes (pages, search, analysis, saved, upload, chat)
├── services/
│   ├── analysis_engine.py  # Preprocessing, encoding, clustering
│   ├── dataset_loader.py   # Download, validate, and load datasets
│   ├── dataset_search.py   # Fan-out search orchestrator
│   ├── search_ranker.py    # Fuzzy relevance ranking + dedup
│   ├── insights.py         # LLM-generated cluster insights
│   ├── storage.py          # Analysis + search history CRUD
│   ├── visualization.py    # Plotly chart generation (9 types)
│   ├── ticket_service.py
│   └── providers/          # Dataset source providers (7)
│       ├── base.py         # Abstract base class
│       ├── datagov_provider.py
│       ├── huggingface_provider.py
│       ├── kaggle_provider.py
│       ├── openml_provider.py
│       ├── aws_opendata_provider.py
│       ├── socrata_provider.py
│       └── zenodo_provider.py
├── static/               # CSS, JS
├── templates/            # Jinja2 templates
├── database.py           # SQLite setup
└── main.py               # FastAPI app
docs/
├── brainstorms/          # Feature exploration documents
├── plans/                # Implementation plans
└── solutions/            # Documented solutions (searchable)
    ├── architecture-patterns/
    ├── integration-issues/
    ├── logic-errors/
    └── ui-bugs/
tests/
├── test_analysis.py
├── test_dataset_loader.py
├── test_search.py
├── test_storage.py
├── test_ticket_service.py
├── test_ticket_cli.py
└── test_visualization.py
```

## License

MIT
