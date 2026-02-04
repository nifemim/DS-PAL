"""HuggingFace Datasets provider."""
import logging
from typing import List

import httpx

from app.config import settings
from app.models.schemas import DatasetResult
from app.services.providers.base import DatasetProvider

logger = logging.getLogger(__name__)


class HuggingFaceProvider(DatasetProvider):
    """Search datasets from HuggingFace Hub API."""

    BASE_URL = "https://huggingface.co/api"

    @property
    def name(self) -> str:
        return "huggingface"

    async def search(self, query: str, max_results: int = 10) -> List[DatasetResult]:
        try:
            headers = {}
            if settings.huggingface_token:
                headers["Authorization"] = f"Bearer {settings.huggingface_token}"

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self.BASE_URL}/datasets",
                    params={
                        "search": query,
                        "limit": max_results,
                        "sort": "downloads",
                        "direction": "-1",
                    },
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()

            results = []
            for ds in data[:max_results]:
                ds_id = ds.get("id", "")
                tags = ds.get("tags", [])
                # Filter to only show datasets that likely have tabular data
                description = ds.get("description", "") or ""
                card_data = ds.get("cardData", {}) or {}
                size_str = ""
                if card_data.get("dataset_size"):
                    size_str = str(card_data["dataset_size"])
                elif ds.get("downloads"):
                    size_str = f"{ds['downloads']} downloads"

                results.append(DatasetResult(
                    source="huggingface",
                    dataset_id=ds_id,
                    name=ds_id.split("/")[-1] if "/" in ds_id else ds_id,
                    description=description[:300],
                    url=f"https://huggingface.co/datasets/{ds_id}",
                    size=size_str,
                    format="parquet",
                    tags=tags[:5],
                ))

            logger.info("HuggingFace returned %d results for '%s'", len(results), query)
            return results

        except Exception as e:
            logger.warning("HuggingFace search failed: %s", e)
            return []

    async def download_url(self, dataset_id: str) -> str:
        return f"https://huggingface.co/datasets/{dataset_id}"
