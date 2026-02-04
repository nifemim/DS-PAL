"""data.gov dataset provider."""
import logging
from typing import List

import httpx

from app.models.schemas import DatasetResult
from app.services.providers.base import DatasetProvider

logger = logging.getLogger(__name__)


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
                # Find best downloadable resource (prefer CSV)
                csv_url = ""
                any_url = ""
                fmt = ""
                for resource in pkg.get("resources", []):
                    res_fmt = (resource.get("format") or "").upper()
                    res_url = resource.get("url", "")
                    if res_fmt == "CSV" and not csv_url:
                        csv_url = res_url
                        fmt = "CSV"
                    elif not any_url:
                        any_url = res_url
                        fmt = res_fmt

                download_url = csv_url or any_url
                dataset_id = pkg.get("id", "")
                results.append(DatasetResult(
                    source="data.gov",
                    dataset_id=dataset_id,
                    name=pkg.get("title", "Untitled"),
                    description=(pkg.get("notes") or "")[:300],
                    url=download_url,
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

            for resource in data.get("result", {}).get("resources", []):
                fmt = (resource.get("format") or "").upper()
                if fmt == "CSV":
                    return resource.get("url", "")

            # Fallback to first resource
            resources = data.get("result", {}).get("resources", [])
            if resources:
                return resources[0].get("url", "")
            return ""
        except Exception as e:
            logger.warning("data.gov download_url failed: %s", e)
            return ""
