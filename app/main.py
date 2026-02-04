"""FastAPI application factory."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.database import init_db

logger = logging.getLogger(__name__)

APP_DIR = Path(__file__).parent

# Templates - importable by routers
templates = Jinja2Templates(directory=APP_DIR / "templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup, clean up on shutdown."""
    logging.basicConfig(
        level=logging.DEBUG if settings.app_debug else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger.info("Starting DS-PAL...")

    # Initialize database
    await init_db()

    # Create cache directory
    Path(settings.cache_dir).mkdir(parents=True, exist_ok=True)

    # Pending analyses store (in-memory, keyed by UUID)
    app.state.pending_analyses = {}

    yield

    logger.info("Shutting down DS-PAL...")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="DS-PAL", lifespan=lifespan)

    # Mount static files
    app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")

    # Register routers
    from app.routers import pages, search, analysis, saved

    app.include_router(pages.router)
    app.include_router(search.router, prefix="/api")
    app.include_router(analysis.router, prefix="/api")
    app.include_router(saved.router, prefix="/api")

    return app


app = create_app()
