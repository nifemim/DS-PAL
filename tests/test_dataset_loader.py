"""Tests for dataset loader content validation and download routing."""
import io
import zipfile

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

from app.services.dataset_loader import (
    _validate_content,
    _extract_zip,
    download_dataset,
    load_dataframe,
    MAX_FILE_BYTES,
)
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


class TestZenodoDownload:
    """Tests for _download_zenodo() handler."""

    @pytest.mark.asyncio
    async def test_routes_to_zenodo(self, tmp_path):
        with patch("app.services.dataset_loader._cache_path", return_value=tmp_path), \
             patch("app.services.dataset_loader._download_zenodo", new_callable=AsyncMock) as mock:
            mock.return_value = tmp_path / "data.csv"
            await download_dataset("zenodo", "12345", "https://zenodo.org/records/12345")
            mock.assert_called_once_with("12345", tmp_path)

    @pytest.mark.asyncio
    async def test_downloads_csv_file(self, tmp_path):
        from app.services.dataset_loader import _download_zenodo

        api_response = MagicMock()
        api_response.status_code = 200
        api_response.json.return_value = {
            "files": [
                {"key": "data.csv", "links": {"self": "https://zenodo.org/api/records/12345/files/data.csv/content"}}
            ]
        }
        api_response.raise_for_status = MagicMock()

        file_response = MagicMock()
        file_response.content = b"name,age\nAlice,30\n"
        file_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[api_response, file_response])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await _download_zenodo("12345", tmp_path)
        assert result.name == "data.csv"
        assert result.read_bytes() == b"name,age\nAlice,30\n"

    @pytest.mark.asyncio
    async def test_404_raises_clear_error(self, tmp_path):
        from app.services.dataset_loader import _download_zenodo

        api_response = MagicMock()
        api_response.status_code = 404

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=api_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(ValueError, match="not found"):
                await _download_zenodo("99999", tmp_path)

    @pytest.mark.asyncio
    async def test_no_data_files_raises_error(self, tmp_path):
        from app.services.dataset_loader import _download_zenodo

        api_response = MagicMock()
        api_response.status_code = 200
        api_response.json.return_value = {
            "files": [
                {"key": "readme.pdf", "links": {"self": "https://zenodo.org/api/records/12345/files/readme.pdf/content"}}
            ]
        }
        api_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=api_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(ValueError, match="no downloadable data files"):
                await _download_zenodo("12345", tmp_path)

    @pytest.mark.asyncio
    async def test_file_size_limit_enforced(self, tmp_path):
        from app.services.dataset_loader import _download_zenodo

        api_response = MagicMock()
        api_response.status_code = 200
        api_response.json.return_value = {
            "files": [
                {"key": "huge.csv", "links": {"self": "https://zenodo.org/api/records/12345/files/huge.csv/content"}}
            ]
        }
        api_response.raise_for_status = MagicMock()

        # Content just over the limit
        file_response = MagicMock()
        file_response.content = b"x" * 100
        file_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[api_response, file_response])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client), \
             patch("app.services.dataset_loader.MAX_FILE_BYTES", 50):
            with pytest.raises(ValueError, match="too large"):
                await _download_zenodo("12345", tmp_path)

    @pytest.mark.asyncio
    async def test_picks_first_data_file(self, tmp_path):
        from app.services.dataset_loader import _download_zenodo

        api_response = MagicMock()
        api_response.status_code = 200
        api_response.json.return_value = {
            "files": [
                {"key": "readme.txt", "links": {"self": "https://example.com/readme.txt"}},
                {"key": "results.csv", "links": {"self": "https://example.com/results.csv"}},
                {"key": "backup.json", "links": {"self": "https://example.com/backup.json"}},
            ]
        }
        api_response.raise_for_status = MagicMock()

        file_response = MagicMock()
        file_response.content = b"col1,col2\n1,2\n"
        file_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[api_response, file_response])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await _download_zenodo("12345", tmp_path)
        # Should pick results.csv (first data file), not readme.txt
        assert result.name == "results.csv"


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


def _make_zip(entries: dict[str, bytes]) -> bytes:
    """Helper to create a zip file in memory from {name: content} dict."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


class TestExtractZip:
    """Tests for _extract_zip() secure extraction."""

    def test_valid_zip_extracts_and_returns_largest(self, tmp_path):
        content = _make_zip({
            "small.csv": b"a,b\n1,2\n",
            "large.csv": b"a,b\n" + b"1,2\n" * 100,
        })
        result = _extract_zip(content, tmp_path)
        assert result.name == "large.csv"
        assert result.exists()

    def test_path_traversal_flattened_safely(self, tmp_path):
        content = _make_zip({"../../evil.csv": b"a,b\n1,2\n"})
        result = _extract_zip(content, tmp_path)
        # Should extract as "evil.csv" inside cache_dir, not traverse
        assert result.name == "evil.csv"
        assert result.parent.resolve() == tmp_path.resolve()

    def test_deeply_nested_traversal_flattened(self, tmp_path):
        content = _make_zip({"../../../etc/passwd.csv": b"a,b\n1,2\n"})
        result = _extract_zip(content, tmp_path)
        assert result.name == "passwd.csv"
        assert result.parent.resolve() == tmp_path.resolve()

    def test_oversized_entry_raises(self, tmp_path):
        content = _make_zip({"big.csv": b"x" * 200})
        with patch("app.services.dataset_loader.MAX_FILE_BYTES", 100):
            with pytest.raises(ValueError, match="exceeds"):
                _extract_zip(content, tmp_path)

    def test_oversized_entry_cleans_up(self, tmp_path):
        """Partial and previously extracted files should be cleaned up on error."""
        content = _make_zip({
            "first.csv": b"a,b\n1,2\n",
            "second.csv": b"x" * 200,
        })
        with patch("app.services.dataset_loader.MAX_FILE_BYTES", 100):
            with pytest.raises(ValueError, match="exceeds"):
                _extract_zip(content, tmp_path)
        # first.csv should have been cleaned up
        assert not (tmp_path / "first.csv").exists()

    def test_no_data_files_raises(self, tmp_path):
        content = _make_zip({"readme.txt": b"hello"})
        with pytest.raises(ValueError, match="No supported data files"):
            _extract_zip(content, tmp_path)

    def test_macosx_entries_skipped(self, tmp_path):
        content = _make_zip({
            "__MACOSX/._data.csv": b"resource fork junk",
            "data.csv": b"a,b\n1,2\n",
        })
        result = _extract_zip(content, tmp_path)
        assert result.name == "data.csv"
        assert not (tmp_path / "._data.csv").exists()

    def test_dot_files_skipped(self, tmp_path):
        content = _make_zip({
            ".hidden.csv": b"a,b\n1,2\n",
            "visible.csv": b"a,b\n1,2\n",
        })
        result = _extract_zip(content, tmp_path)
        assert result.name == "visible.csv"

    def test_case_insensitive_extension(self, tmp_path):
        content = _make_zip({"DATA.CSV": b"a,b\n1,2\n"})
        result = _extract_zip(content, tmp_path)
        assert result.name == "DATA.CSV"


class TestLoadDataframe:
    """Tests for load_dataframe() max_rows handling."""

    def test_json_max_rows_none_no_crash(self, tmp_path):
        import json
        data = [{"a": i, "b": i * 2} for i in range(10)]
        json_file = tmp_path / "data.json"
        json_file.write_text(json.dumps(data))
        df = load_dataframe(json_file, max_rows=None)
        assert len(df) == 10

    def test_parquet_max_rows_none_no_crash(self, tmp_path):
        import pandas as pd
        df_in = pd.DataFrame({"a": range(10), "b": range(10)})
        pq_file = tmp_path / "data.parquet"
        df_in.to_parquet(pq_file)
        df = load_dataframe(pq_file, max_rows=None)
        assert len(df) == 10

    def test_max_rows_zero_returns_empty(self, tmp_path):
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("a,b\n1,2\n3,4\n")
        df = load_dataframe(csv_file, max_rows=0)
        assert len(df) == 0

    def test_max_rows_truncates_parquet(self, tmp_path):
        import pandas as pd
        df_in = pd.DataFrame({"a": range(20), "b": range(20)})
        pq_file = tmp_path / "data.parquet"
        df_in.to_parquet(pq_file)
        df = load_dataframe(pq_file, max_rows=5)
        assert len(df) == 5

    def test_max_rows_truncates_json(self, tmp_path):
        import json
        data = [{"a": i} for i in range(20)]
        json_file = tmp_path / "data.json"
        json_file.write_text(json.dumps(data))
        df = load_dataframe(json_file, max_rows=5)
        assert len(df) == 5


class TestOpenMLArffRemoval:
    """Tests for _download_openml() ARFF fallback removal."""

    @pytest.mark.asyncio
    async def test_failed_parquet_raises_even_with_arff_url(self, tmp_path):
        """When parquet fails, should NOT fall back to ARFF URL."""
        from app.services.dataset_loader import _download_openml

        # Mock metadata response with an ARFF URL in ds_info
        meta_response = MagicMock()
        meta_response.status_code = 200
        meta_response.raise_for_status = MagicMock()
        meta_response.json.return_value = {
            "data_set_description": {
                "name": "iris",
                "url": "https://www.openml.org/data/download/61/iris.arff",
            }
        }

        # Mock parquet download failure (404)
        parquet_response = MagicMock()
        parquet_response.status_code = 404
        parquet_response.content = b""

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[parquet_response])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient") as mock_cls:
            # First client for metadata, second for parquet attempt
            meta_client = AsyncMock()
            meta_client.get = AsyncMock(return_value=meta_response)
            meta_client.__aenter__ = AsyncMock(return_value=meta_client)
            meta_client.__aexit__ = AsyncMock(return_value=False)

            mock_cls.side_effect = [meta_client, mock_client]

            with pytest.raises(ValueError, match="ARFF format"):
                await _download_openml("61", tmp_path)

    @pytest.mark.asyncio
    async def test_successful_parquet_still_works(self, tmp_path):
        """When parquet succeeds, should return the parquet file."""
        from app.services.dataset_loader import _download_openml

        meta_response = MagicMock()
        meta_response.status_code = 200
        meta_response.raise_for_status = MagicMock()
        meta_response.json.return_value = {
            "data_set_description": {"name": "iris"}
        }

        # Valid parquet-like content (just needs to pass _validate_content)
        parquet_response = MagicMock()
        parquet_response.status_code = 200
        parquet_response.content = b"PAR1" + b"\x00" * 100
        parquet_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_cls:
            meta_client = AsyncMock()
            meta_client.get = AsyncMock(return_value=meta_response)
            meta_client.__aenter__ = AsyncMock(return_value=meta_client)
            meta_client.__aexit__ = AsyncMock(return_value=False)

            parquet_client = AsyncMock()
            parquet_client.get = AsyncMock(return_value=parquet_response)
            parquet_client.__aenter__ = AsyncMock(return_value=parquet_client)
            parquet_client.__aexit__ = AsyncMock(return_value=False)

            mock_cls.side_effect = [meta_client, parquet_client]

            result = await _download_openml("61", tmp_path)
            assert result.name == "data.parquet"
            assert result.exists()
