"""Zenodo dataset provider (academic/research datasets)."""
import logging
from typing import List

import httpx

from app.models.schemas import DatasetResult
from app.services.providers.base import DatasetProvider

logger = logging.getLogger(__name__)


class ZenodoProvider(DatasetProvider):
    """Search datasets from Zenodo's REST API.

    Zenodo is a general-purpose open repository hosted by CERN,
    widely used for research data sharing.
    """

    API_URL = "https://zenodo.org/api/records"

    @property
    def name(self) -> str:
        return "zenodo"

    async def search(self, query: str, max_results: int = 10) -> List[DatasetResult]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    self.API_URL,
                    params={
                        "q": f"{query} dataset",
                        "size": max_results,
                        "type": "dataset",
                        "access_right": "open",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            results = []
            for hit in data.get("hits", {}).get("hits", [])[:max_results]:
                meta = hit.get("metadata", {})
                record_id = str(hit.get("id", ""))
                title = meta.get("title", "Untitled")
                description = meta.get("description", "") or ""
                # Strip HTML tags from description
                import re
                description = re.sub(r"<[^>]+>", "", description)

                keywords = meta.get("keywords", [])[:5]
                doi = hit.get("doi", "")
                url = f"https://zenodo.org/records/{record_id}"

                # Get file info for size
                files = hit.get("files", [])
                size = ""
                if files:
                    total_bytes = sum(f.get("size", 0) for f in files)
                    if total_bytes > 1024 * 1024:
                        size = f"{total_bytes / 1024 / 1024:.1f} MB"
                    elif total_bytes > 1024:
                        size = f"{total_bytes / 1024:.0f} KB"

                # Determine format from filenames
                fmt = ""
                if files:
                    exts = {f.get("key", "").rsplit(".", 1)[-1].upper() for f in files if "." in f.get("key", "")}
                    data_exts = exts & {"CSV", "JSON", "PARQUET", "XLSX", "TSV", "ZIP"}
                    if data_exts:
                        fmt = ", ".join(sorted(data_exts))

                results.append(DatasetResult(
                    source="zenodo",
                    dataset_id=record_id,
                    name=title,
                    description=description[:300],
                    url=url,
                    size=size,
                    format=fmt or "varies",
                    tags=keywords,
                ))

            logger.info("Zenodo returned %d results for '%s'", len(results), query)
            return results

        except Exception as e:
            logger.warning("Zenodo search failed: %s", e)
            return []

    async def download_url(self, dataset_id: str) -> str:
        return f"https://zenodo.org/records/{dataset_id}"
