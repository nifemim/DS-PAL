"""Abstract base class for dataset providers."""
from abc import ABC, abstractmethod
from typing import List
from app.models.schemas import DatasetResult


class DatasetProvider(ABC):
    """Base class for dataset search providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for display."""
        ...

    @abstractmethod
    async def search(self, query: str, max_results: int = 10) -> List[DatasetResult]:
        """Search for datasets matching the query."""
        ...

    @abstractmethod
    async def download_url(self, dataset_id: str) -> str:
        """Get the download URL for a dataset."""
        ...
