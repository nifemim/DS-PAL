"""Tests for the file upload feature."""
import pytest
from unittest.mock import patch, AsyncMock
from pathlib import Path

from httpx import AsyncClient, ASGITransport

from app.main import app
from app.services.dataset_loader import download_dataset


class TestUploadDataset:
    """Tests for the upload endpoint."""

    @pytest.mark.asyncio
    async def test_upload_csv_saves_and_redirects(self, tmp_path):
        """Valid CSV upload saves file to cache and returns 303 redirect."""
        csv_content = b"name,age,city\nAlice,30,NYC\nBob,25,LA\n"

        with patch("app.routers.upload.save_upload") as mock_save, \
             patch("app.routers.upload.load_dataframe"):
            mock_save.return_value = ("test-uuid", tmp_path / "data.csv")
            (tmp_path / "data.csv").write_bytes(csv_content)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/dataset/upload",
                    files={"file": ("sales.csv", csv_content, "text/csv")},
                    follow_redirects=False,
                )

            assert resp.status_code == 303
            assert "/dataset/upload/test-uuid" in resp.headers["location"]
            assert "name=sales" in resp.headers["location"]
            mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_rejects_unsupported_extension(self):
        """Files with unsupported extensions return index.html with upload_error."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/dataset/upload",
                files={"file": ("readme.txt", b"hello world", "text/plain")},
            )

        assert resp.status_code == 200
        assert "Unsupported format" in resp.text

    @pytest.mark.asyncio
    async def test_upload_rejects_empty_file(self):
        """Empty files (0 bytes) are rejected with clear error."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/dataset/upload",
                files={"file": ("empty.csv", b"", "text/csv")},
            )

        assert resp.status_code == 200
        assert "empty" in resp.text.lower()

    @pytest.mark.asyncio
    async def test_upload_rejects_unparseable_file(self, tmp_path):
        """Files that can't be loaded as DataFrame return index.html with upload_error."""
        bad_content = b"not,a,valid\x00\x01\x02csv"

        with patch("app.routers.upload.save_upload") as mock_save, \
             patch("app.routers.upload.load_dataframe", side_effect=Exception("parse error")):
            mock_save.return_value = ("test-uuid", tmp_path / "data.csv")

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/dataset/upload",
                    files={"file": ("bad.csv", bad_content, "text/csv")},
                )

            assert resp.status_code == 200
            assert "Could not read file" in resp.text


class TestDownloadDatasetUploadSource:
    """Tests for download_dataset with source='upload'."""

    @pytest.mark.asyncio
    async def test_resolves_cached_upload(self, tmp_path):
        """download_dataset('upload', id, '') finds and returns cached upload file."""
        cached_file = tmp_path / "data.csv"
        cached_file.write_text("a,b\n1,2\n")

        with patch("app.services.dataset_loader._cache_path", return_value=tmp_path):
            result = await download_dataset("upload", "some-uuid", "")
            assert result == cached_file

    @pytest.mark.asyncio
    async def test_missing_upload_raises(self, tmp_path):
        """download_dataset('upload', bad_id, '') raises ValueError."""
        # Empty directory — no cached files
        with patch("app.services.dataset_loader._cache_path", return_value=tmp_path):
            with pytest.raises(ValueError, match="re-upload"):
                await download_dataset("upload", "nonexistent-uuid", "")
