"""Tests for analysis route redirect behavior and unified detail endpoint."""
import time
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from httpx import AsyncClient, ASGITransport

from app.main import app
from app.models.schemas import SavedAnalysis


@pytest.fixture(autouse=True)
def ensure_pending_analyses():
    """Ensure app.state.pending_analyses exists (lifespan doesn't run in test transport)."""
    if not hasattr(app.state, "pending_analyses"):
        app.state.pending_analyses = {}
    yield
    # Clean up any test entries
    app.state.pending_analyses.clear()


@pytest.fixture
def mock_analysis():
    """Create a mock AnalysisOutput with required attributes."""
    analysis = MagicMock()
    analysis.id = "test-analysis-123"
    analysis.dataset_description = ""
    return analysis


@pytest.fixture
def mock_charts():
    """Create mock chart data."""
    return [MagicMock()]


class TestRunAnalysisRedirect:
    """Tests for POST /api/analyze redirect behavior."""

    @pytest.mark.asyncio
    async def test_run_analysis_redirects_to_analysis_page(self, mock_analysis, mock_charts):
        """POST /api/analyze returns 303 redirect to /analysis/{id} on success."""
        with patch("app.routers.analysis.download_dataset", new_callable=AsyncMock) as mock_dl, \
             patch("app.routers.analysis.load_dataframe") as mock_load, \
             patch("app.routers.analysis.analysis_engine") as mock_engine, \
             patch("app.routers.analysis.generate_all") as mock_gen:
            mock_dl.return_value = "/tmp/fake.csv"
            mock_load.return_value = MagicMock()
            mock_engine.run.return_value = mock_analysis
            mock_gen.return_value = mock_charts

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/analyze",
                    data={
                        "source": "test",
                        "dataset_id": "iris",
                        "name": "Iris",
                        "url": "",
                        "algorithm": "kmeans",
                    },
                    follow_redirects=False,
                )

            assert resp.status_code == 303
            assert resp.headers["location"] == "/analysis/test-analysis-123"

    @pytest.mark.asyncio
    async def test_run_analysis_stores_in_pending(self, mock_analysis, mock_charts):
        """POST /api/analyze stores analysis in app.state.pending_analyses."""
        with patch("app.routers.analysis.download_dataset", new_callable=AsyncMock) as mock_dl, \
             patch("app.routers.analysis.load_dataframe") as mock_load, \
             patch("app.routers.analysis.analysis_engine") as mock_engine, \
             patch("app.routers.analysis.generate_all") as mock_gen:
            mock_dl.return_value = "/tmp/fake.csv"
            mock_load.return_value = MagicMock()
            mock_engine.run.return_value = mock_analysis
            mock_gen.return_value = mock_charts

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.post(
                    "/api/analyze",
                    data={
                        "source": "test",
                        "dataset_id": "iris",
                        "name": "Iris",
                        "url": "",
                        "algorithm": "kmeans",
                    },
                    follow_redirects=False,
                )

            assert "test-analysis-123" in app.state.pending_analyses
            entry = app.state.pending_analyses["test-analysis-123"]
            assert entry["analysis"] is mock_analysis
            assert entry["charts"] is mock_charts
            assert "created_at" in entry

    @pytest.mark.asyncio
    async def test_run_analysis_error_redirects_to_dataset(self):
        """POST /api/analyze redirects back to dataset page with ?error= on failure."""
        with patch("app.routers.analysis.download_dataset", new_callable=AsyncMock) as mock_dl:
            mock_dl.side_effect = Exception("File not found")

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/analyze",
                    data={
                        "source": "test",
                        "dataset_id": "iris",
                        "name": "Iris",
                        "url": "http://example.com/iris.csv",
                        "algorithm": "kmeans",
                    },
                    follow_redirects=False,
                )

            assert resp.status_code == 303
            location = resp.headers["location"]
            assert location.startswith("/dataset/test/iris")
            assert "error=" in location
            assert "File%20not%20found" in location


class TestUnifiedDetailEndpoint:
    """Tests for GET /api/analysis/{id}/detail."""

    @pytest.mark.asyncio
    async def test_detail_returns_pending(self, mock_analysis, mock_charts):
        """Unified detail endpoint returns analysis_results.html for pending analysis."""
        app.state.pending_analyses["pending-123"] = {
            "analysis": mock_analysis,
            "charts": mock_charts,
            "created_at": time.time(),
        }

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/analysis/pending-123/detail")

            assert resp.status_code == 200
        finally:
            del app.state.pending_analyses["pending-123"]

    @pytest.mark.asyncio
    async def test_detail_returns_saved(self):
        """Unified detail endpoint returns analysis_detail.html for saved analysis."""
        saved = SavedAnalysis(
            id="saved-456",
            title="Saved Test",
            dataset_source="test",
            dataset_id="iris",
            dataset_name="Iris",
        )

        with patch("app.routers.analysis.get_analysis", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = saved

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/analysis/saved-456/detail")

            assert resp.status_code == 200
            assert "Saved Test" in resp.text

    @pytest.mark.asyncio
    async def test_detail_returns_not_found(self):
        """Unified detail endpoint returns error partial for missing ID."""
        with patch("app.routers.analysis.get_analysis", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/analysis/nonexistent-789/detail")

            assert resp.status_code == 200
            assert "not found" in resp.text.lower()


class TestDatasetPageErrorBanner:
    """Tests for dataset page error query param."""

    @pytest.mark.asyncio
    async def test_dataset_page_shows_error_banner(self):
        """Dataset page shows error message when ?error= is provided."""
        with patch("app.routers.pages.download_dataset", new_callable=AsyncMock) as mock_dl, \
             patch("app.routers.pages.load_dataframe") as mock_load, \
             patch("app.routers.pages.build_preview") as mock_preview:
            mock_dl.return_value = MagicMock()
            mock_load.return_value = MagicMock()
            mock_preview.return_value = MagicMock(
                name="Test", source="test", dataset_id="iris",
                url="", num_rows=10, num_columns=3,
                numeric_columns=[], categorical_columns=[],
                columns=[], sample_rows=[],
            )

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(
                    "/dataset/test/iris?error=Something+went+wrong"
                )

            assert resp.status_code == 200
            assert "Something went wrong" in resp.text

    @pytest.mark.asyncio
    async def test_dataset_page_no_error_without_param(self):
        """Dataset page renders normally without error param."""
        with patch("app.routers.pages.download_dataset", new_callable=AsyncMock) as mock_dl, \
             patch("app.routers.pages.load_dataframe") as mock_load, \
             patch("app.routers.pages.build_preview") as mock_preview:
            mock_dl.return_value = MagicMock()
            mock_load.return_value = MagicMock()
            mock_preview.return_value = MagicMock(
                name="Test", source="test", dataset_id="iris",
                url="", num_rows=10, num_columns=3,
                numeric_columns=[], categorical_columns=[],
                columns=[], sample_rows=[],
            )

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/dataset/test/iris")

            assert resp.status_code == 200
            assert "error-message" not in resp.text
