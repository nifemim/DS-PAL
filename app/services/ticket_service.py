"""CRUD operations for fix-later tickets."""
import json
import logging
from datetime import datetime
from typing import List, Optional

from app.database import get_db
from app.models.schemas import (
    Ticket,
    TicketCreate,
    TicketStats,
    TicketStatus,
    TicketUpdate,
)

logger = logging.getLogger(__name__)

PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _row_to_ticket(row) -> Ticket:
    """Convert a database row to a Ticket model."""
    return Ticket(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        status=row["status"],
        priority=row["priority"],
        tags=json.loads(row["tags"]) if row["tags"] else [],
        resolution=row["resolution"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        solved_at=row["solved_at"],
    )


async def create_ticket(data: TicketCreate) -> Ticket:
    """Create a new ticket. Returns the created Ticket."""
    db = await get_db()
    try:
        tags_json = json.dumps(data.tags)
        cursor = await db.execute(
            """INSERT INTO tickets (title, description, priority, tags)
               VALUES (?, ?, ?, ?)""",
            (data.title, data.description, data.priority.value, tags_json),
        )
        await db.commit()
        ticket_id = cursor.lastrowid

        return await _get_ticket_by_id(db, ticket_id)
    finally:
        await db.close()


async def _get_ticket_by_id(db, ticket_id: int) -> Optional[Ticket]:
    """Internal helper to fetch a ticket using an existing connection."""
    cursor = await db.execute(
        "SELECT * FROM tickets WHERE id = ?", (ticket_id,)
    )
    row = await cursor.fetchone()
    if not row:
        return None
    return _row_to_ticket(row)


async def get_ticket(ticket_id: int) -> Optional[Ticket]:
    """Get a ticket by ID."""
    db = await get_db()
    try:
        return await _get_ticket_by_id(db, ticket_id)
    finally:
        await db.close()


async def list_tickets(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    tag: Optional[str] = None,
) -> List[Ticket]:
    """List tickets with optional filters. Sorted by priority then created_at."""
    db = await get_db()
    try:
        conditions = []
        params = []

        if status:
            conditions.append("status = ?")
            params.append(status)
        if priority:
            conditions.append("priority = ?")
            params.append(priority)
        if tag:
            conditions.append("tags LIKE ?")
            params.append(f'%"{tag}"%')

        where = ""
        if conditions:
            where = "WHERE " + " AND ".join(conditions)

        query = f"""
            SELECT * FROM tickets {where}
            ORDER BY
                CASE priority
                    WHEN 'critical' THEN 0
                    WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2
                    WHEN 'low' THEN 3
                END,
                created_at DESC
        """

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [_row_to_ticket(row) for row in rows]
    finally:
        await db.close()


async def update_ticket(ticket_id: int, data: TicketUpdate) -> Optional[Ticket]:
    """Update a ticket. Returns the updated Ticket or None if not found."""
    db = await get_db()
    try:
        existing = await _get_ticket_by_id(db, ticket_id)
        if not existing:
            return None

        fields = []
        params = []

        if data.title is not None:
            fields.append("title = ?")
            params.append(data.title)
        if data.description is not None:
            fields.append("description = ?")
            params.append(data.description)
        if data.status is not None:
            fields.append("status = ?")
            params.append(data.status.value)
            if data.status in (TicketStatus.SOLVED, TicketStatus.WONT_FIX):
                fields.append("solved_at = ?")
                params.append(datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
            elif existing.status in (TicketStatus.SOLVED, TicketStatus.WONT_FIX):
                # Reopening: clear solved_at
                fields.append("solved_at = NULL")
        if data.priority is not None:
            fields.append("priority = ?")
            params.append(data.priority.value)
        if data.tags is not None:
            fields.append("tags = ?")
            params.append(json.dumps(data.tags))
        if data.resolution is not None:
            fields.append("resolution = ?")
            params.append(data.resolution)

        if not fields:
            return existing

        fields.append("updated_at = datetime('now')")
        params.append(ticket_id)

        query = f"UPDATE tickets SET {', '.join(fields)} WHERE id = ?"
        await db.execute(query, params)
        await db.commit()

        return await _get_ticket_by_id(db, ticket_id)
    finally:
        await db.close()


async def solve_ticket(ticket_id: int, resolution: str = "") -> Optional[Ticket]:
    """Mark a ticket as solved with an optional resolution note."""
    return await update_ticket(
        ticket_id,
        TicketUpdate(
            status=TicketStatus.SOLVED,
            resolution=resolution,
        ),
    )


async def delete_ticket(ticket_id: int) -> bool:
    """Delete a ticket. Returns True if deleted."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "DELETE FROM tickets WHERE id = ?", (ticket_id,)
        )
        await db.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info("Deleted ticket #%d", ticket_id)
        return deleted
    finally:
        await db.close()


async def get_ticket_stats() -> TicketStats:
    """Get aggregate ticket statistics."""
    db = await get_db()
    try:
        # Total count
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM tickets")
        row = await cursor.fetchone()
        total = row["cnt"]

        # By status
        cursor = await db.execute(
            "SELECT status, COUNT(*) as cnt FROM tickets GROUP BY status"
        )
        by_status = {r["status"]: r["cnt"] for r in await cursor.fetchall()}

        # By priority
        cursor = await db.execute(
            "SELECT priority, COUNT(*) as cnt FROM tickets GROUP BY priority"
        )
        by_priority = {r["priority"]: r["cnt"] for r in await cursor.fetchall()}

        return TicketStats(
            total=total,
            by_status=by_status,
            by_priority=by_priority,
        )
    finally:
        await db.close()
