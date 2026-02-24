"""Test fixtures."""
import os

# Use a test database
os.environ["DATABASE_PATH"] = "test_ds_pal.db"

import pytest
import pytest_asyncio


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    """Initialize a fresh test database for each test."""
    from app.database import init_db, get_db

    await init_db()
    yield
    # Clean up after test
    db = await get_db()
    try:
        await db.execute("DELETE FROM chat_messages")
        await db.execute("DELETE FROM tickets")
        await db.execute("DELETE FROM visualizations")
        await db.execute("DELETE FROM analyses")
        await db.execute("DELETE FROM search_history")
        await db.commit()
    finally:
        await db.close()
