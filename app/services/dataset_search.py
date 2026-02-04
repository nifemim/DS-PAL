"""Dataset search orchestrator — fans out to all providers concurrently."""
import asyncio
import logging
from typing import List

from app.models.schemas import DatasetResult
from app.services.providers.datagov_provider import DataGovProvider
from app.services.providers.kaggle_provider import KaggleProvider
from app.services.providers.uci_provider import UCIProvider
from app.services.providers.huggingface_provider import HuggingFaceProvider

logger = logging.getLogger(__name__)

PROVIDERS = [
    DataGovProvider(),
    KaggleProvider(),
    UCIProvider(),
    HuggingFaceProvider(),
]


async def search_all(query: str, max_per_provider: int = 5) -> List[DatasetResult]:
    """Search all providers concurrently and merge results."""
    tasks = [
        provider.search(query, max_results=max_per_provider)
        for provider in PROVIDERS
    ]

    results_per_provider = await asyncio.gather(*tasks, return_exceptions=True)

    merged = []
    for provider, result in zip(PROVIDERS, results_per_provider):
        if isinstance(result, Exception):
            logger.warning("Provider %s failed: %s", provider.name, result)
            continue
        merged.extend(result)

    logger.info(
        "Search for '%s' returned %d total results from %d providers",
        query, len(merged), len(PROVIDERS),
    )
    return merged
