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
        # UCI JSON API at /api/datasets no longer returns JSON (returns HTML).
        # Search is disabled until a working API endpoint is available.
        logger.info("UCI search disabled: API endpoint no longer returns JSON")
        return []

    async def download_url(self, dataset_id: str) -> str:
        return f"https://archive.ics.uci.edu/static/public/{dataset_id}"
