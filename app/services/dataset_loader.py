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


def _validate_content(content: bytes, url: str) -> None:
    """Check that downloaded content is actual data, not HTML/XML error pages."""
    head = content[:500].strip().lower()
    if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
        raise ValueError(
            "The URL returned an HTML page instead of a data file. "
            "This dataset may not have a direct download link."
        )
    if head.startswith(b"<?xml"):
        raise ValueError(
            "The URL returned XML data which is not a supported format. "
            "This dataset may require a different format."
        )


async def download_dataset(source: str, dataset_id: str, url: str) -> Path:
    """Download a dataset file to the cache directory. Returns path to the data file."""
    cache_dir = _cache_path(source, dataset_id)
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Check if we already have a cached file (validate it's real data, not stale HTML/XML)
    cached_files = list(cache_dir.glob("*.csv")) + list(cache_dir.glob("*.json")) + \
                   list(cache_dir.glob("*.parquet")) + list(cache_dir.glob("*.xlsx"))
    if cached_files:
        cached = cached_files[0]
        try:
            _validate_content(cached.read_bytes(), str(cached))
            logger.info("Using cached file: %s", cached)
            return cached
        except ValueError:
            logger.warning("Cached file %s contains invalid data, re-downloading", cached)
            cached.unlink()  # Remove bad cached file

    if source == "kaggle":
        return await _download_kaggle(dataset_id, cache_dir)
    elif source == "huggingface":
        return await _download_huggingface(dataset_id, cache_dir)
    elif source == "uci":
        return await _download_uci(dataset_id, cache_dir)

    # Generic HTTP download (data.gov and others)
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(url, headers={"Accept": "text/csv,application/json,*/*"})
        resp.raise_for_status()

        content_length = len(resp.content)
        if content_length > MAX_FILE_BYTES:
            raise ValueError(
                f"Dataset too large ({content_length / 1024 / 1024:.1f}MB). "
                f"Maximum is {settings.max_file_size_mb}MB."
            )

        # Validate content is actual data, not an error page
        _validate_content(resp.content, url)

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


async def _download_huggingface(dataset_id: str, cache_dir: Path) -> Path:
    """Download from HuggingFace via the datasets-server parquet API."""
    api_url = f"https://datasets-server.huggingface.co/parquet?dataset={dataset_id}"
    headers = {}
    if settings.huggingface_token:
        headers["Authorization"] = f"Bearer {settings.huggingface_token}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(api_url, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    parquet_files = data.get("parquet_files", [])
    if not parquet_files:
        raise ValueError(
            f"No parquet files available for HuggingFace dataset '{dataset_id}'. "
            "The dataset may not be converted to parquet yet."
        )

    # Prefer "train" split, fall back to first available
    target = next((f for f in parquet_files if f["split"] == "train"), parquet_files[0])
    file_url = target["url"]
    file_size = target.get("size", 0)

    if file_size > MAX_FILE_BYTES:
        raise ValueError(
            f"Dataset too large ({file_size / 1024 / 1024:.1f}MB). "
            f"Maximum is {settings.max_file_size_mb}MB."
        )

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.get(file_url, headers=headers)
        resp.raise_for_status()

    file_path = cache_dir / "data.parquet"
    file_path.write_bytes(resp.content)
    logger.info("Downloaded HuggingFace %s to %s (%d bytes)", dataset_id, file_path, len(resp.content))
    return file_path


async def _download_uci(dataset_id: str, cache_dir: Path) -> Path:
    """Download from UCI ML Repository via static zip URL."""
    base_url = f"https://archive.ics.uci.edu/static/public/{dataset_id}"

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        # Try the base path with .zip suffix and without
        for url in [f"{base_url}.zip", base_url]:
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    continue
                content_type = resp.headers.get("content-type", "")
                # Accept zip or octet-stream responses
                if "zip" in content_type or "octet-stream" in content_type:
                    if len(resp.content) > MAX_FILE_BYTES:
                        raise ValueError(
                            f"Dataset too large ({len(resp.content) / 1024 / 1024:.1f}MB). "
                            f"Maximum is {settings.max_file_size_mb}MB."
                        )
                    return _extract_zip(resp.content, cache_dir)
            except ValueError:
                raise
            except Exception as e:
                logger.debug("UCI download attempt %s failed: %s", url, e)
                continue

    raise ValueError(
        f"Could not download UCI dataset '{dataset_id}'. "
        "The UCI repository may not have a direct download available for this dataset."
    )


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


def _classify_column(series: pd.Series) -> dict:
    """Classify a column and return encoding metadata.

    Returns dict with keys: cardinality, suggested_encoding, is_id_like.
    """
    dtype = series.dtype
    name = series.name
    n_rows = len(series)
    non_null = series.dropna()

    # Numeric columns: no encoding needed
    if pd.api.types.is_numeric_dtype(dtype):
        return {"cardinality": None, "suggested_encoding": None, "is_id_like": False}

    # Datetime columns: excluded
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return {"cardinality": None, "suggested_encoding": None, "is_id_like": False}

    # Boolean columns
    if dtype == bool or (dtype == object and set(non_null.unique()) <= {True, False}):
        return {"cardinality": 2, "suggested_encoding": "boolean", "is_id_like": False}

    # Object/category columns
    nunique = int(non_null.nunique())
    cardinality_ratio = nunique / n_rows if n_rows > 0 else 0

    # Single-value: exclude
    if nunique <= 1:
        return {"cardinality": nunique, "suggested_encoding": None, "is_id_like": False}

    # ID-like: cardinality ratio > 0.9
    if cardinality_ratio > 0.9:
        return {"cardinality": nunique, "suggested_encoding": None, "is_id_like": True}

    # Numeric-as-string: >80% values coerce to numeric
    if dtype == object:
        coerced = pd.to_numeric(non_null, errors="coerce")
        numeric_ratio = coerced.notna().sum() / len(non_null) if len(non_null) > 0 else 0
        if numeric_ratio > 0.8:
            return {"cardinality": nunique, "suggested_encoding": "numeric-coerce", "is_id_like": False}

    # Categorical: choose encoding by cardinality
    if nunique <= 10:
        return {"cardinality": nunique, "suggested_encoding": "one-hot", "is_id_like": False}
    else:
        return {"cardinality": nunique, "suggested_encoding": "label", "is_id_like": False}


def build_preview(df: pd.DataFrame, source: str, dataset_id: str,
                  name: str, url: str = "") -> DatasetPreview:
    """Build a DatasetPreview from a DataFrame."""
    columns = []
    categorical_cols = []

    for col in df.columns:
        non_null = int(df[col].count())
        null_count = int(df[col].isna().sum())
        sample_vals = df[col].dropna().head(3).tolist()
        # Convert numpy types to Python native
        sample_vals = [
            v.item() if hasattr(v, "item") else v
            for v in sample_vals
        ]

        classification = _classify_column(df[col])

        col_info = ColumnInfo(
            name=str(col),
            dtype=str(df[col].dtype),
            non_null_count=non_null,
            null_count=null_count,
            sample_values=sample_vals,
            cardinality=classification["cardinality"],
            suggested_encoding=classification["suggested_encoding"],
            is_id_like=classification["is_id_like"],
        )
        columns.append(col_info)

        # Encodable categorical: has a suggested encoding and is not ID-like
        if classification["suggested_encoding"] in ("one-hot", "label", "boolean", "numeric-coerce"):
            categorical_cols.append(str(col))

    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()

    # Build sample rows (first 5)
    sample_df = df.head(5).fillna("")
    sample_rows = []
    for _, row in sample_df.iterrows():
        row_dict = {}
        for col_name in sample_df.columns:
            val = row[col_name]
            if hasattr(val, "item"):
                val = val.item()
            row_dict[str(col_name)] = val
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
        categorical_columns=categorical_cols,
        sample_rows=sample_rows,
    )
