"""Tests for the file upload feature."""
import pytest
import pandas as pd
from unittest.mock import patch, AsyncMock
from pathlib import Path

from httpx import AsyncClient, ASGITransport

from app.main import app
from app.services.dataset_loader import (
    detect_sheets,
    download_dataset,
    join_sheets,
    save_joined_csv,
)


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


def _create_multi_sheet_excel(path: Path, sheets: dict[str, pd.DataFrame]) -> Path:
    """Helper: write a multi-sheet Excel file to the given path."""
    file_path = path / "data.xlsx"
    with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name, index=False)
    return file_path


class TestMultiSheetExcel:
    """Tests for multi-sheet Excel detection, selection, and joining."""

    def test_detect_sheets_returns_sheet_info(self, tmp_path):
        """detect_sheets returns name, row count, columns for each sheet."""
        orders = pd.DataFrame({"order_id": [1, 2], "customer_id": [10, 20], "amount": [100, 200]})
        customers = pd.DataFrame({"customer_id": [10, 20, 30], "name": ["Alice", "Bob", "Carol"]})
        file_path = _create_multi_sheet_excel(tmp_path, {"Orders": orders, "Customers": customers})

        sheets = detect_sheets(file_path)

        assert len(sheets) == 2
        assert sheets[0]["name"] == "Orders"
        assert sheets[0]["num_rows"] == 2
        assert sheets[0]["num_columns"] == 3
        assert "customer_id" in sheets[0]["columns"]
        assert sheets[1]["name"] == "Customers"
        assert sheets[1]["num_rows"] == 3

    @pytest.mark.asyncio
    async def test_single_sheet_skips_selection(self, tmp_path):
        """Uploading a single-sheet Excel redirects straight to dataset page."""
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
        file_path = tmp_path / "data.xlsx"
        df.to_excel(file_path, index=False)
        content = file_path.read_bytes()

        with patch("app.routers.upload.save_upload") as mock_save, \
             patch("app.routers.upload.load_dataframe"):
            mock_save.return_value = ("test-uuid", file_path)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/dataset/upload",
                    files={"file": ("single.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                    follow_redirects=False,
                )

            assert resp.status_code == 303
            assert "/dataset/upload/test-uuid?" in resp.headers["location"]
            assert "sheets" not in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_multi_sheet_redirects_to_selection(self, tmp_path):
        """Uploading a multi-sheet Excel redirects to /sheets."""
        orders = pd.DataFrame({"order_id": [1], "customer_id": [10]})
        customers = pd.DataFrame({"customer_id": [10], "name": ["Alice"]})
        file_path = _create_multi_sheet_excel(tmp_path, {"Orders": orders, "Customers": customers})
        content = file_path.read_bytes()

        with patch("app.routers.upload.save_upload") as mock_save, \
             patch("app.routers.upload.load_dataframe"):
            mock_save.return_value = ("test-uuid", file_path)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/dataset/upload",
                    files={"file": ("multi.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                    follow_redirects=False,
                )

            assert resp.status_code == 303
            assert "/sheets" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_select_one_sheet_redirects_with_param(self, tmp_path):
        """Selecting one sheet redirects to dataset page with ?sheet= param."""
        orders = pd.DataFrame({"order_id": [1], "customer_id": [10]})
        customers = pd.DataFrame({"customer_id": [10], "name": ["Alice"]})
        file_path = _create_multi_sheet_excel(tmp_path, {"Orders": orders, "Customers": customers})

        with patch("app.services.dataset_loader._cache_path", return_value=tmp_path):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/dataset/upload/test-uuid/sheets",
                    data={"name": "multi", "sheets": "Orders"},
                    follow_redirects=False,
                )

            assert resp.status_code == 303
            assert "sheet=Orders" in resp.headers["location"]

    def test_join_two_sheets_on_shared_column(self, tmp_path):
        """join_sheets merges two sheets on a shared column."""
        orders = pd.DataFrame({"order_id": [1, 2, 3], "customer_id": [10, 20, 10], "amount": [100, 200, 150]})
        customers = pd.DataFrame({"customer_id": [10, 20], "name": ["Alice", "Bob"]})
        file_path = _create_multi_sheet_excel(tmp_path, {"Orders": orders, "Customers": customers})

        configs = [
            {"name": "Orders"},
            {"name": "Customers", "join_key": "customer_id", "join_type": "inner"},
        ]
        result = join_sheets(file_path, configs)

        assert len(result) == 3
        assert "name" in result.columns
        assert "amount" in result.columns
        assert list(result["name"]) == ["Alice", "Bob", "Alice"]

    def test_join_preview_returns_correct_stats(self, tmp_path):
        """join_sheets returns correct row/column counts."""
        sheet_a = pd.DataFrame({"id": [1, 2], "val_a": ["x", "y"]})
        sheet_b = pd.DataFrame({"id": [1, 2, 3], "val_b": ["p", "q", "r"]})
        file_path = _create_multi_sheet_excel(tmp_path, {"A": sheet_a, "B": sheet_b})

        configs = [
            {"name": "A"},
            {"name": "B", "join_key": "id", "join_type": "inner"},
        ]
        result = join_sheets(file_path, configs)

        assert len(result) == 2  # inner join: only ids 1 and 2
        assert len(result.columns) == 3  # id, val_a, val_b

    def test_save_joined_csv(self, tmp_path):
        """save_joined_csv writes CSV to the cache directory."""
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})

        with patch("app.services.dataset_loader._cache_path", return_value=tmp_path):
            path = save_joined_csv(df, "test-uuid")

        assert path.exists()
        assert path.name == "joined.csv"
        loaded = pd.read_csv(path)
        assert len(loaded) == 2
        assert list(loaded.columns) == ["a", "b"]

    @pytest.mark.asyncio
    async def test_no_shared_columns_shows_error(self, tmp_path):
        """Selecting sheets with no shared columns shows error message."""
        sheet_a = pd.DataFrame({"col_a": [1, 2]})
        sheet_b = pd.DataFrame({"col_b": [3, 4]})
        file_path = _create_multi_sheet_excel(tmp_path, {"A": sheet_a, "B": sheet_b})

        with patch("app.services.dataset_loader._cache_path", return_value=tmp_path):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/dataset/upload/test-uuid/sheets",
                    data={"name": "test", "sheets": ["A", "B"]},
                    follow_redirects=False,
                )

            assert resp.status_code == 200
            assert "No shared columns" in resp.text
