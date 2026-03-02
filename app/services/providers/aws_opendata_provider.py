"""AWS Open Data Registry provider."""
import json
import logging
from typing import List

import httpx

from app.models.schemas import DatasetResult
from app.services.providers.base import DatasetProvider

logger = logging.getLogger(__name__)

REGISTRY_URL = "https://s3.amazonaws.com/registry.opendata.aws/roda/ndjson/index.ndjson"


class AWSOpenDataProvider(DatasetProvider):
    """Search datasets from the AWS Open Data Registry.

    Lazy-loads the full registry NDJSON on first search, then searches locally.
    """

    def __init__(self):
        self._datasets: list[dict] | None = None

    @property
    def name(self) -> str:
        return "aws"

    async def _ensure_loaded(self) -> list[dict]:
        """Fetch and cache the registry on first use."""
        if self._datasets is not None:
            return self._datasets

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(REGISTRY_URL)
                resp.raise_for_status()

            datasets = []
            for line in resp.text.strip().split("\n"):
                if line.strip():
                    datasets.append(json.loads(line))

            self._datasets = datasets
            logger.info("AWS Open Data: loaded %d datasets", len(datasets))
            return datasets

        except Exception as e:
            logger.warning("AWS Open Data registry fetch failed: %s", e)
            self._datasets = []
            return []

    async def search(self, query: str, max_results: int = 10) -> List[DatasetResult]:
        try:
            datasets = await self._ensure_loaded()
            if not datasets:
                return []

            query_lower = query.lower()
            matches = []

            for ds in datasets:
                name = ds.get("Name", "")
                description = ds.get("Description", "")
                tags = ds.get("Tags", [])
                tag_str = " ".join(tags) if isinstance(tags, list) else ""

                searchable = f"{name} {description} {tag_str}".lower()
                if query_lower in searchable:
                    slug = ds.get("Slug", name.replace(" ", "-").lower())
                    registry_url = f"https://registry.opendata.aws/roda/{slug}/"
                    tag_list = tags[:5] if isinstance(tags, list) else []

                    matches.append(DatasetResult(
                        source="aws",
                        dataset_id=slug,
                        name=name,
                        description=(description or "")[:300],
                        url=registry_url,
                        format="varies",
                        tags=tag_list,
                    ))

                    if len(matches) >= max_results:
                        break

            logger.info("AWS Open Data returned %d results for '%s'", len(matches), query)
            return matches

        except Exception as e:
            logger.warning("AWS Open Data search failed: %s", e)
            return []

    async def download_url(self, dataset_id: str) -> str:
        return f"https://registry.opendata.aws/roda/{dataset_id}/"
