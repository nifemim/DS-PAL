"""Tests for dataset loader content validation and download routing."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

from app.services.dataset_loader import _validate_content, download_dataset
from app.services.providers.datagov_provider import _is_direct_download


class TestValidateContent:
    """Tests for _validate_content()."""

    def test_rejects_html_doctype(self):
        content = b"<!DOCTYPE html><html><body>Not a dataset</body></html>"
        with pytest.raises(ValueError, match="HTML page"):
            _validate_content(content, "http://example.com/data")

    def test_rejects_html_tag(self):
        content = b"<html><head><title>Error</title></head><body>404</body></html>"
        with pytest.raises(ValueError, match="HTML page"):
            _validate_content(content, "http://example.com/data")

    def test_rejects_xml(self):
        content = b'<?xml version="1.0"?><catalog><item>data</item></catalog>'
        with pytest.raises(ValueError, match="XML data"):
            _validate_content(content, "http://example.com/data.xml")

    def test_accepts_csv(self):
        content = b"name,age,city\nAlice,30,NYC\nBob,25,LA\n"
        _validate_content(content, "http://example.com/data.csv")

    def test_accepts_json(self):
        content = b'[{"name": "Alice", "age": 30}]'
        _validate_content(content, "http://example.com/data.json")

    def test_accepts_parquet_magic_bytes(self):
        # Parquet files start with PAR1 magic bytes
        content = b"PAR1" + b"\x00" * 100
        _validate_content(content, "http://example.com/data.parquet")

    def test_accepts_empty_content(self):
        # Empty content should pass validation (will fail at parse stage)
        _validate_content(b"", "http://example.com/data.csv")

    def test_case_insensitive_html_detection(self):
        content = b"<!doctype HTML><HTML><body>error</body></HTML>"
        with pytest.raises(ValueError, match="HTML page"):
            _validate_content(content, "http://example.com")

    def test_whitespace_before_html(self):
        content = b"   \n  <!DOCTYPE html><html></html>"
        with pytest.raises(ValueError, match="HTML page"):
            _validate_content(content, "http://example.com")


class TestDownloadRouting:
    """Tests for download_dataset() source routing."""

    @pytest.mark.asyncio
    async def test_routes_to_kaggle(self, tmp_path):
        with patch("app.services.dataset_loader._cache_path", return_value=tmp_path), \
             patch("app.services.dataset_loader._download_kaggle", new_callable=AsyncMock) as mock:
            mock.return_value = tmp_path / "data.csv"
            await download_dataset("kaggle", "owner/dataset", "http://example.com")
            mock.assert_called_once_with("owner/dataset", tmp_path)

    @pytest.mark.asyncio
    async def test_routes_to_huggingface(self, tmp_path):
        with patch("app.services.dataset_loader._cache_path", return_value=tmp_path), \
             patch("app.services.dataset_loader._download_huggingface", new_callable=AsyncMock) as mock:
            mock.return_value = tmp_path / "data.parquet"
            await download_dataset("huggingface", "org/dataset", "http://example.com")
            mock.assert_called_once_with("org/dataset", tmp_path)

    @pytest.mark.asyncio
    async def test_routes_to_openml(self, tmp_path):
        with patch("app.services.dataset_loader._cache_path", return_value=tmp_path), \
             patch("app.services.dataset_loader._download_openml", new_callable=AsyncMock) as mock:
            mock.return_value = tmp_path / "data.parquet"
            await download_dataset("openml", "61", "http://example.com")
            mock.assert_called_once_with("61", tmp_path)

    @pytest.mark.asyncio
    async def test_generic_download_validates_content(self, tmp_path):
        """Generic download path should reject HTML responses."""
        html_content = b"<!DOCTYPE html><html><body>Error page</body></html>"

        mock_response = MagicMock()
        mock_response.content = html_content
        mock_response.headers = {"content-type": "text/html"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.dataset_loader._cache_path", return_value=tmp_path), \
             patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(ValueError, match="HTML page"):
                await download_dataset("data.gov", "abc-123", "http://example.com/data.csv")

    @pytest.mark.asyncio
    async def test_uses_cache_when_available(self, tmp_path):
        """Should return cached file without downloading."""
        cached_file = tmp_path / "data.csv"
        cached_file.write_text("a,b\n1,2\n")

        with patch("app.services.dataset_loader._cache_path", return_value=tmp_path):
            result = await download_dataset("data.gov", "test", "http://example.com")
            assert result == cached_file

    @pytest.mark.asyncio
    async def test_cache_rejects_stale_html(self, tmp_path):
        """Cached HTML files should be rejected and re-downloaded."""
        cached_file = tmp_path / "data.csv"
        cached_file.write_text("<!DOCTYPE html><html><body>Not data</body></html>")

        mock_response = MagicMock()
        mock_response.content = b"a,b\n1,2\n"
        mock_response.headers = {"content-type": "text/csv"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.dataset_loader._cache_path", return_value=tmp_path), \
             patch("httpx.AsyncClient", return_value=mock_client):
            result = await download_dataset("data.gov", "test", "http://example.com/data.csv")
            # Old cached HTML file should have been removed
            assert not cached_file.exists() or cached_file.read_bytes() == b"a,b\n1,2\n"

    @pytest.mark.asyncio
    async def test_cache_rejects_stale_xml(self, tmp_path):
        """Cached XML files should be rejected and re-downloaded."""
        cached_file = tmp_path / "data.csv"
        cached_file.write_text('<?xml version="1.0"?><root></root>')

        mock_response = MagicMock()
        mock_response.content = b"x,y\n3,4\n"
        mock_response.headers = {"content-type": "text/csv"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.dataset_loader._cache_path", return_value=tmp_path), \
             patch("httpx.AsyncClient", return_value=mock_client):
            result = await download_dataset("data.gov", "test", "http://example.com/data.csv")
            assert not cached_file.exists() or cached_file.read_bytes() == b"x,y\n3,4\n"


class TestDirectDownloadFilter:
    """Tests for data.gov URL filtering."""

    def test_csv_url_is_direct(self):
        assert _is_direct_download("https://data.gov/files/dataset.csv") is True

    def test_json_url_is_direct(self):
        assert _is_direct_download("https://api.data.gov/data.json") is True

    def test_xlsx_url_is_direct(self):
        assert _is_direct_download("https://example.com/report.xlsx") is True

    def test_zip_url_is_direct(self):
        assert _is_direct_download("https://example.com/data.zip") is True

    def test_html_page_not_direct(self):
        assert _is_direct_download("https://geodata.bts.gov/datasets/military-bases/about") is False

    def test_api_endpoint_not_direct(self):
        assert _is_direct_download("https://api.example.com/v1/datasets/123") is False

    def test_empty_url_not_direct(self):
        assert _is_direct_download("") is False

    def test_arcgis_hub_not_direct(self):
        assert _is_direct_download("https://hub.arcgis.com/datasets/abc123") is False
