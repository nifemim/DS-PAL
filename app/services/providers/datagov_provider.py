"""data.gov dataset provider."""
import logging
from typing import List
from urllib.parse import urlparse

import httpx

from app.models.schemas import DatasetResult
from app.services.providers.base import DatasetProvider

logger = logging.getLogger(__name__)

# File extensions that indicate a direct download
_DATA_EXTENSIONS = {".csv", ".json", ".xlsx", ".xls", ".parquet", ".zip", ".tsv"}


def _is_direct_download(url: str) -> bool:
    """Check if a URL looks like a direct file download (not a landing page)."""
    if not url:
        return False
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in _DATA_EXTENSIONS)


class DataGovProvider(DatasetProvider):
    """Search datasets from data.gov CKAN API."""

    BASE_URL = "https://catalog.data.gov/api/3/action"

    @property
    def name(self) -> str:
        return "data.gov"

    async def search(self, query: str, max_results: int = 10) -> List[DatasetResult]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self.BASE_URL}/package_search",
                    params={
                        "q": query,
                        "rows": max_results,
                        "fq": "res_format:CSV OR res_format:JSON",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            results = []
            for pkg in data.get("result", {}).get("results", []):
                # Find best downloadable resource:
                # 1st priority: CSV with direct download URL
                # 2nd priority: JSON with direct download URL
                # 3rd priority: any resource with direct download URL
                # Skip packages with no direct download URLs
                best_url = ""
                fmt = ""
                for resource in pkg.get("resources", []):
                    res_fmt = (resource.get("format") or "").upper()
                    res_url = resource.get("url", "")
                    if not _is_direct_download(res_url):
                        continue
                    if res_fmt == "CSV" and not best_url:
                        best_url = res_url
                        fmt = "CSV"
                        break  # CSV direct download is the best option
                    elif res_fmt == "JSON" and not best_url:
                        best_url = res_url
                        fmt = "JSON"
                    elif not best_url:
                        best_url = res_url
                        fmt = res_fmt

                if not best_url:
                    continue  # Skip packages without direct download URLs

                dataset_id = pkg.get("id", "")
                results.append(DatasetResult(
                    source="data.gov",
                    dataset_id=dataset_id,
                    name=pkg.get("title", "Untitled"),
                    description=(pkg.get("notes") or "")[:300],
                    url=best_url,
                    format=fmt or "CSV",
                    tags=[t["name"] for t in pkg.get("tags", [])[:5]],
                ))

            logger.info("data.gov returned %d results for '%s'", len(results), query)
            return results

        except Exception as e:
            logger.warning("data.gov search failed: %s", e)
            return []

    async def download_url(self, dataset_id: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self.BASE_URL}/package_show",
                    params={"id": dataset_id},
                )
                resp.raise_for_status()
                data = resp.json()

            # Prefer CSV with direct download URL
            for resource in data.get("result", {}).get("resources", []):
                fmt = (resource.get("format") or "").upper()
                res_url = resource.get("url", "")
                if fmt == "CSV" and _is_direct_download(res_url):
                    return res_url

            # Fallback to any direct download URL
            for resource in data.get("result", {}).get("resources", []):
                res_url = resource.get("url", "")
                if _is_direct_download(res_url):
                    return res_url

            return ""
        except Exception as e:
            logger.warning("data.gov download_url failed: %s", e)
            return ""
