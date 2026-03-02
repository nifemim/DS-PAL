"""Dataset search orchestrator — fans out to all providers concurrently."""
import asyncio
import logging
from typing import List, Tuple

from app.models.schemas import DatasetResult
from app.services.providers.datagov_provider import DataGovProvider
from app.services.providers.kaggle_provider import KaggleProvider
from app.services.providers.huggingface_provider import HuggingFaceProvider
from app.services.providers.openml_provider import OpenMLProvider
from app.services.providers.aws_opendata_provider import AWSOpenDataProvider
from app.services.providers.socrata_provider import SocrataProvider
from app.services.providers.zenodo_provider import ZenodoProvider

logger = logging.getLogger(__name__)

PROVIDERS = [
    DataGovProvider(),
    KaggleProvider(),
    HuggingFaceProvider(),
    OpenMLProvider(),
    AWSOpenDataProvider(),
    SocrataProvider(),
    ZenodoProvider(),
]


async def search_all(
    query: str, max_per_provider: int = 5
) -> Tuple[List[DatasetResult], List[str]]:
    """Search all providers concurrently and merge results.

    Returns (results, active_provider_names) where active_provider_names
    lists which providers returned at least one result.
    """
    tasks = [
        provider.search(query, max_results=max_per_provider)
        for provider in PROVIDERS
    ]

    results_per_provider = await asyncio.gather(*tasks, return_exceptions=True)

    merged = []
    active_providers = []
    for provider, result in zip(PROVIDERS, results_per_provider):
        if isinstance(result, Exception):
            logger.warning("Provider %s failed: %s", provider.name, result)
            continue
        if result:
            active_providers.append(provider.name)
        merged.extend(result)

    logger.info(
        "Search for '%s' returned %d total results from %s",
        query, len(merged), ", ".join(active_providers) or "no providers",
    )
    return merged, active_providers
