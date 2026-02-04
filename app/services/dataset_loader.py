"""Download and load datasets into pandas DataFrames."""
import asyncio
import io
import logging
import os
import re
import zipfile
from pathlib import Path
from typing import Optional, Tuple

import httpx
import pandas as pd

from app.config import settings
from app.models.schemas import DatasetPreview, ColumnInfo

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = settings.max_file_size_mb * 1024 * 1024


def _sanitize_id(dataset_id: str) -> str:
    """Sanitize dataset ID to prevent path traversal."""
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", dataset_id)


def _cache_path(source: str, dataset_id: str) -> Path:
    """Get cache path for a dataset."""
    safe_id = _sanitize_id(dataset_id)
    return Path(settings.cache_dir) / f"{source}_{safe_id}"


async def download_dataset(source: str, dataset_id: str, url: str) -> Path:
    """Download a dataset file to the cache directory. Returns path to the data file."""
    cache_dir = _cache_path(source, dataset_id)
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Check if we already have a cached CSV/file
    cached_files = list(cache_dir.glob("*.csv")) + list(cache_dir.glob("*.json")) + \
                   list(cache_dir.glob("*.parquet")) + list(cache_dir.glob("*.xlsx"))
    if cached_files:
        logger.info("Using cached file: %s", cached_files[0])
        return cached_files[0]

    if source == "kaggle":
        return await _download_kaggle(dataset_id, cache_dir)

    # Generic HTTP download
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(url, headers={"Accept": "text/csv,application/json,*/*"})
        resp.raise_for_status()

        content_length = len(resp.content)
        if content_length > MAX_FILE_BYTES:
            raise ValueError(
                f"Dataset too large ({content_length / 1024 / 1024:.1f}MB). "
                f"Maximum is {settings.max_file_size_mb}MB."
            )

        content_type = resp.headers.get("content-type", "")

        # Handle zip files
        if "zip" in content_type or url.endswith(".zip"):
            return _extract_zip(resp.content, cache_dir)

        # Determine file extension
        if "json" in content_type or url.endswith(".json"):
            ext = ".json"
        elif "parquet" in content_type or url.endswith(".parquet"):
            ext = ".parquet"
        elif "excel" in content_type or url.endswith(".xlsx"):
            ext = ".xlsx"
        else:
            ext = ".csv"

        file_path = cache_dir / f"data{ext}"
        file_path.write_bytes(resp.content)
        logger.info("Downloaded %s to %s (%d bytes)", url, file_path, content_length)
        return file_path


async def _download_kaggle(dataset_id: str, cache_dir: Path) -> Path:
    """Download from Kaggle using their API."""
    loop = asyncio.get_event_loop()

    def _download():
        os.environ["KAGGLE_USERNAME"] = settings.kaggle_username
        os.environ["KAGGLE_KEY"] = settings.kaggle_key
        from kaggle.api.kaggle_api_extended import KaggleApi
        api = KaggleApi()
        api.authenticate()
        api.dataset_download_files(dataset_id, path=str(cache_dir), unzip=True)

    await loop.run_in_executor(None, _download)

    # Find the downloaded CSV
    for ext in ["*.csv", "*.json", "*.parquet", "*.xlsx"]:
        files = list(cache_dir.glob(ext))
        if files:
            # Return the largest file (likely the main dataset)
            return max(files, key=lambda f: f.stat().st_size)

    raise FileNotFoundError(f"No supported data files found in Kaggle download for {dataset_id}")


def _extract_zip(content: bytes, cache_dir: Path) -> Path:
    """Extract a zip file and return path to the data file inside."""
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        # Find data files in the zip
        data_files = [
            f for f in zf.namelist()
            if f.endswith((".csv", ".json", ".parquet", ".xlsx"))
            and not f.startswith("__MACOSX")
        ]
        if not data_files:
            raise ValueError("No supported data files found in zip archive")

        # Extract all data files
        for f in data_files:
            zf.extract(f, cache_dir)

        # Return the largest
        extracted = [cache_dir / f for f in data_files]
        return max(extracted, key=lambda f: f.stat().st_size)


def load_dataframe(file_path: Path, max_rows: Optional[int] = None) -> pd.DataFrame:
    """Load a data file into a pandas DataFrame."""
    max_rows = max_rows or settings.max_dataset_rows
    suffix = file_path.suffix.lower()

    if suffix == ".csv":
        df = pd.read_csv(file_path, nrows=max_rows, on_bad_lines="skip")
    elif suffix == ".json":
        df = pd.read_json(file_path)
        if len(df) > max_rows:
            df = df.head(max_rows)
    elif suffix == ".parquet":
        df = pd.read_parquet(file_path)
        if len(df) > max_rows:
            df = df.head(max_rows)
    elif suffix in (".xlsx", ".xls"):
        df = pd.read_excel(file_path, nrows=max_rows)
    else:
        # Try CSV as fallback
        df = pd.read_csv(file_path, nrows=max_rows, on_bad_lines="skip")

    logger.info("Loaded %s: %d rows x %d columns", file_path.name, len(df), len(df.columns))
    return df


def build_preview(df: pd.DataFrame, source: str, dataset_id: str,
                  name: str, url: str = "") -> DatasetPreview:
    """Build a DatasetPreview from a DataFrame."""
    columns = []
    for col in df.columns:
        non_null = int(df[col].count())
        null_count = int(df[col].isna().sum())
        sample_vals = df[col].dropna().head(3).tolist()
        # Convert numpy types to Python native
        sample_vals = [
            v.item() if hasattr(v, "item") else v
            for v in sample_vals
        ]
        columns.append(ColumnInfo(
            name=str(col),
            dtype=str(df[col].dtype),
            non_null_count=non_null,
            null_count=null_count,
            sample_values=sample_vals,
        ))

    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()

    # Build sample rows (first 5)
    sample_df = df.head(5).fillna("")
    sample_rows = []
    for _, row in sample_df.iterrows():
        row_dict = {}
        for col in sample_df.columns:
            val = row[col]
            if hasattr(val, "item"):
                val = val.item()
            row_dict[str(col)] = val
        sample_rows.append(row_dict)

    return DatasetPreview(
        source=source,
        dataset_id=dataset_id,
        name=name,
        url=url,
        num_rows=len(df),
        num_columns=len(df.columns),
        columns=columns,
        numeric_columns=numeric_cols,
        sample_rows=sample_rows,
    )
