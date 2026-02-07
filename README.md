# DS-PAL

A dataset analysis platform with clustering, anomaly detection, and interactive visualizations. Includes a CLI-based ticket manager for tracking fix-later items.

## Features

**Web Application**
- Search datasets from Kaggle, HuggingFace, UCI ML Repository, and Data.gov
- Preview dataset structure and sample data
- Run clustering analysis (K-Means, DBSCAN, Hierarchical)
- Detect anomalies with Isolation Forest
- Interactive Plotly visualizations (2D/3D scatter, parallel coordinates, heatmaps)
- Save and manage analysis results

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
pytest tests/test_ticket_service.py -v
pytest tests/test_ticket_cli.py -v
```

## Project Structure

```
app/
├── cli/                  # CLI ticket manager
│   ├── __main__.py       # argparse entry point
│   ├── tickets.py        # subcommand handlers
│   └── _formatter.py     # output formatting
├── models/
│   └── schemas.py        # Pydantic models
├── routers/              # FastAPI routes
├── services/
│   ├── analysis_engine.py
│   ├── dataset_loader.py
│   ├── dataset_search.py
│   ├── storage.py
│   ├── ticket_service.py
│   ├── visualization.py
│   └── providers/        # Dataset source providers
├── static/               # CSS, JS
├── templates/            # Jinja2 templates
├── database.py           # SQLite setup
└── main.py               # FastAPI app
tests/
├── test_analysis.py
├── test_search.py
├── test_storage.py
├── test_ticket_service.py
├── test_ticket_cli.py
└── test_visualization.py
```

## License

MIT
