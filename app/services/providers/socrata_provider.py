"""Socrata Open Data provider (powers thousands of government data portals)."""
import logging
from typing import List

import httpx

from app.models.schemas import DatasetResult
from app.services.providers.base import DatasetProvider

logger = logging.getLogger(__name__)


class SocrataProvider(DatasetProvider):
    """Search datasets from Socrata's Discovery API.

    Covers data.cityofchicago.org, data.ny.gov, data.seattle.gov,
    and thousands of other government open data portals.
    """

    API_URL = "https://api.us.socrata.com/api/catalog/v1"

    @property
    def name(self) -> str:
        return "socrata"

    async def search(self, query: str, max_results: int = 10) -> List[DatasetResult]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    self.API_URL,
                    params={
                        "q": query,
                        "limit": max_results,
                        "only": "datasets",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            results = []
            for item in data.get("results", [])[:max_results]:
                resource = item.get("resource", {})
                ds_id = resource.get("id", "")
                name = resource.get("name", "Untitled")
                description = resource.get("description", "") or ""
                domain = item.get("metadata", {}).get("domain", "")

                # Use the SODA CSV export URL — this returns actual data, not an HTML page
                csv_url = f"https://{domain}/resource/{ds_id}.csv?$limit=50000" if domain else ""

                tags = resource.get("columns_field_name", [])[:5]
                categories = item.get("classification", {}).get("categories", [])
                if categories:
                    tags = categories[:5]

                results.append(DatasetResult(
                    source="socrata",
                    dataset_id=ds_id,
                    name=name,
                    description=description[:300],
                    url=csv_url,
                    format="CSV",
                    tags=tags,
                ))

            logger.info("Socrata returned %d results for '%s'", len(results), query)
            return results

        except Exception as e:
            logger.warning("Socrata search failed: %s", e)
            return []

    async def download_url(self, dataset_id: str) -> str:
        return f"https://data.cityofchicago.org/resource/{dataset_id}.csv"
