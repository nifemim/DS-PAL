"""OpenML dataset provider."""
import logging
from typing import List

import httpx

from app.models.schemas import DatasetResult
from app.services.providers.base import DatasetProvider

logger = logging.getLogger(__name__)


class OpenMLProvider(DatasetProvider):
    """Search datasets from OpenML REST API."""

    BASE_URL = "https://www.openml.org/api/v1/json"

    @property
    def name(self) -> str:
        return "openml"

    async def search(self, query: str, max_results: int = 10) -> List[DatasetResult]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self.BASE_URL}/data/list/data_name/{query}/limit/{max_results}",
                )
                resp.raise_for_status()
                data = resp.json()

            datasets = data.get("data", {}).get("dataset", [])
            results = []
            for ds in datasets[:max_results]:
                did = str(ds.get("did", ""))
                ds_name = ds.get("name", "Untitled")

                # Extract row/column counts from quality metrics
                qualities = {q["name"]: q["value"] for q in ds.get("quality", [])}
                rows = qualities.get("NumberOfInstances", "")
                cols = qualities.get("NumberOfFeatures", "")
                size = ""
                if rows and cols:
                    size = f"{int(float(rows))} rows × {int(float(cols))} cols"

                results.append(DatasetResult(
                    source="openml",
                    dataset_id=did,
                    name=ds_name,
                    description=f"OpenML dataset #{did}",
                    url=f"https://www.openml.org/d/{did}",
                    size=size,
                    format="parquet",
                    tags=[],
                ))

            logger.info("OpenML returned %d results for '%s'", len(results), query)
            return results

        except httpx.HTTPStatusError as e:
            # OpenML returns 412 when no datasets match the query
            if e.response.status_code == 412:
                logger.info("OpenML: no results for '%s'", query)
                return []
            logger.warning("OpenML search failed: %s", e)
            return []
        except Exception as e:
            logger.warning("OpenML search failed: %s", e)
            return []

    async def download_url(self, dataset_id: str) -> str:
        return f"https://www.openml.org/data/v1/download/{dataset_id}"
