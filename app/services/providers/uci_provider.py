"""UCI Machine Learning Repository provider."""
import logging
from typing import List

import httpx

from app.models.schemas import DatasetResult
from app.services.providers.base import DatasetProvider

logger = logging.getLogger(__name__)


class UCIProvider(DatasetProvider):
    """Search datasets from UCI ML Repository API."""

    BASE_URL = "https://archive.ics.uci.edu/api"

    @property
    def name(self) -> str:
        return "uci"

    async def search(self, query: str, max_results: int = 10) -> List[DatasetResult]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self.BASE_URL}/datasets",
                    params={"search": query, "limit": max_results, "skip": 0},
                )
                resp.raise_for_status()
                data = resp.json()

            results = []
            datasets = data if isinstance(data, list) else data.get("data", data.get("results", []))
            if isinstance(datasets, dict):
                datasets = datasets.get("datasets", [])

            for ds in datasets[:max_results]:
                ds_id = str(ds.get("id", ds.get("ID", "")))
                name = ds.get("name", ds.get("Name", "Untitled"))
                abstract = ds.get("abstract", ds.get("Abstract", ""))
                num_instances = ds.get("num_instances", ds.get("NumInstances", ""))

                results.append(DatasetResult(
                    source="uci",
                    dataset_id=ds_id,
                    name=name,
                    description=str(abstract)[:300] if abstract else "",
                    url=f"https://archive.ics.uci.edu/dataset/{ds_id}",
                    size=f"{num_instances} instances" if num_instances else "",
                    format="CSV",
                    tags=[],
                ))

            logger.info("UCI returned %d results for '%s'", len(results), query)
            return results

        except Exception as e:
            logger.warning("UCI search failed: %s", e)
            return []

    async def download_url(self, dataset_id: str) -> str:
        return f"https://archive.ics.uci.edu/static/public/{dataset_id}"
