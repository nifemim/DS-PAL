# DS-PAL — Dataset Pre-processing, Analysis, and Learning

A dataset analysis platform with clustering, anomaly detection, and interactive visualizations. Includes a CLI-based ticket manager for tracking fix-later items.

## Features

**Web Application**
- Search datasets from Kaggle, HuggingFace, and Data.gov
- Preview dataset structure with column classification and cardinality info
- Automatic categorical column encoding (one-hot for low cardinality, label encoding for high cardinality)
- Toggle categorical columns on/off with encoding method badges in the UI
- Run clustering analysis (K-Means, DBSCAN, Hierarchical) on numeric and categorical data
- Detect anomalies with Isolation Forest
- Interactive Plotly visualizations (2D/3D scatter, parallel coordinates, heatmaps)
- Transformation notices showing which columns were encoded and how
- Save and manage analysis results with encoding metadata
- Dark mode with automatic OS preference detection and manual toggle

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
| `HUGGINGFACE_TOKEN` | HuggingFace API token | - |
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
├── routers/              # FastAPI routes
├── services/
│   ├── analysis_engine.py  # Preprocessing, encoding, clustering
│   ├── dataset_loader.py   # Download, validate, and load datasets
│   ├── dataset_search.py   # Fan-out search orchestrator
│   ├── storage.py
│   ├── ticket_service.py
│   ├── visualization.py
│   └── providers/         # Dataset source providers
│       ├── base.py        # Abstract base class
│       ├── datagov_provider.py
│       ├── huggingface_provider.py
│       ├── kaggle_provider.py
│       └── uci_provider.py
├── static/               # CSS, JS
├── templates/            # Jinja2 templates
├── database.py           # SQLite setup
└── main.py               # FastAPI app
docs/
├── plans/                # Implementation plans
└── solutions/            # Documented solutions (searchable)
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
