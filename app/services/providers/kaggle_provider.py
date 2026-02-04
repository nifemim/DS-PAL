"""Kaggle dataset provider."""
import asyncio
import logging
import os
from functools import partial
from typing import List

from app.config import settings
from app.models.schemas import DatasetResult
from app.services.providers.base import DatasetProvider

logger = logging.getLogger(__name__)


class KaggleProvider(DatasetProvider):
    """Search datasets from Kaggle API."""

    @property
    def name(self) -> str:
        return "kaggle"

    def _is_configured(self) -> bool:
        return bool(settings.kaggle_username and settings.kaggle_key)

    async def search(self, query: str, max_results: int = 10) -> List[DatasetResult]:
        if not self._is_configured():
            logger.debug("Kaggle credentials not configured, skipping")
            return []

        try:
            # Set env vars for kaggle API
            os.environ["KAGGLE_USERNAME"] = settings.kaggle_username
            os.environ["KAGGLE_KEY"] = settings.kaggle_key

            loop = asyncio.get_event_loop()
            datasets = await loop.run_in_executor(
                None,
                partial(self._search_sync, query, max_results),
            )
            logger.info("Kaggle returned %d results for '%s'", len(datasets), query)
            return datasets
        except Exception as e:
            logger.warning("Kaggle search failed: %s", e)
            return []

    def _search_sync(self, query: str, max_results: int) -> List[DatasetResult]:
        from kaggle.api.kaggle_api_extended import KaggleApi

        api = KaggleApi()
        api.authenticate()
        datasets = api.dataset_list(search=query, page_size=max_results, file_type="csv")

        results = []
        for ds in datasets:
            ref = str(ds)  # e.g. "owner/dataset-name"
            results.append(DatasetResult(
                source="kaggle",
                dataset_id=ref,
                name=getattr(ds, "title", ref),
                description=getattr(ds, "subtitle", "")[:300] if hasattr(ds, "subtitle") else "",
                url=f"https://www.kaggle.com/datasets/{ref}",
                size=str(getattr(ds, "size", "")),
                format="CSV",
                tags=[],
            ))
        return results

    async def download_url(self, dataset_id: str) -> str:
        return f"https://www.kaggle.com/datasets/{dataset_id}"
