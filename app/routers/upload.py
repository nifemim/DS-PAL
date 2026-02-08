"""Upload API route."""
import logging
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import RedirectResponse

from app.config import settings
from app.main import templates
from app.services.dataset_loader import (
    MAX_FILE_BYTES,
    _validate_content,
    load_dataframe,
    save_upload,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["upload"])

ALLOWED_EXTENSIONS = {".csv", ".json", ".parquet", ".xlsx", ".xls"}


@router.post("/dataset/upload")
async def upload_dataset(request: Request, file: UploadFile):
    """Upload a dataset file. Saves to cache, redirects to dataset page."""
    try:
        # 1. Validate extension
        original_name = file.filename or "dataset"
        ext = Path(original_name).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(
                "Unsupported format. Please upload CSV, Excel, JSON, or Parquet."
            )

        # 2. Read file content, reject empty and oversized files
        content = await file.read()
        if len(content) == 0:
            raise ValueError("The uploaded file is empty.")
        if len(content) > MAX_FILE_BYTES:
            raise ValueError(
                f"File exceeds {settings.max_file_size_mb} MB limit."
            )

        # 3. Validate content is not HTML/XML
        try:
            _validate_content(content)
        except ValueError:
            raise ValueError(
                "The uploaded file appears to be an HTML or XML page, not a dataset."
            )

        # 4. Save to cache
        upload_id, file_path = save_upload(content, ext)

        # 5. Verify file is loadable
        load_dataframe(file_path)

        # 6. Redirect to dataset page
        display_name = Path(original_name).stem
        return RedirectResponse(
            url=f"/dataset/upload/{upload_id}?name={quote(display_name)}",
            status_code=303,
        )

    except ValueError as e:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "max_file_size_mb": settings.max_file_size_mb,
                "upload_error": str(e),
            },
        )
    except Exception as e:
        logger.error("Upload failed: %s", e, exc_info=True)
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "max_file_size_mb": settings.max_file_size_mb,
                "upload_error": f"Could not read file: {str(e)}",
            },
        )
