"""Subcommand handlers for ticket CLI."""
from __future__ import annotations

import asyncio
import sys
from argparse import Namespace

from app.database import init_db
from app.models.schemas import TicketCreate, TicketPriority, TicketStatus, TicketUpdate
from app.services import ticket_service

from ._formatter import format_ticket_detail, format_ticket_stats, format_ticket_table


def _run(coro):
    """Run an async coroutine from sync context."""
    return asyncio.run(coro)


def _ensure_db():
    """Initialize the database (creates tables if needed)."""
    _run(init_db())


def handle_add(args: Namespace) -> None:
    _ensure_db()
    tags = []
    if args.tags:
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    try:
        priority = TicketPriority(args.priority)
    except ValueError:
        print(f"Error: invalid priority '{args.priority}'", file=sys.stderr)
        sys.exit(1)

    data = TicketCreate(
        title=args.title,
        description=args.description or "",
        priority=priority,
        tags=tags,
    )
    ticket = _run(ticket_service.create_ticket(data))
    print(f"Created ticket #{ticket.id}: {ticket.title}")


def handle_list(args: Namespace) -> None:
    _ensure_db()
    tickets = _run(
        ticket_service.list_tickets(
            status=args.status,
            priority=args.priority,
            tag=args.tag,
        )
    )
    print(format_ticket_table(tickets))


def handle_show(args: Namespace) -> None:
    _ensure_db()
    ticket = _run(ticket_service.get_ticket(args.id))
    if not ticket:
        print(f"Error: ticket #{args.id} not found", file=sys.stderr)
        sys.exit(1)
    print(format_ticket_detail(ticket))


def handle_solve(args: Namespace) -> None:
    _ensure_db()
    ticket = _run(
        ticket_service.solve_ticket(args.id, resolution=args.resolution or "")
    )
    if not ticket:
        print(f"Error: ticket #{args.id} not found", file=sys.stderr)
        sys.exit(1)
    print(f"Ticket #{ticket.id} marked as solved.")


def handle_update(args: Namespace) -> None:
    _ensure_db()

    update_data = {}
    if args.title is not None:
        update_data["title"] = args.title
    if args.description is not None:
        update_data["description"] = args.description
    if args.status is not None:
        try:
            update_data["status"] = TicketStatus(args.status)
        except ValueError:
            print(f"Error: invalid status '{args.status}'", file=sys.stderr)
            sys.exit(1)
    if args.priority is not None:
        try:
            update_data["priority"] = TicketPriority(args.priority)
        except ValueError:
            print(f"Error: invalid priority '{args.priority}'", file=sys.stderr)
            sys.exit(1)
    if args.tags is not None:
        update_data["tags"] = [t.strip() for t in args.tags.split(",") if t.strip()]
    if args.resolution is not None:
        update_data["resolution"] = args.resolution

    if not update_data:
        print("Error: no fields to update", file=sys.stderr)
        sys.exit(1)

    data = TicketUpdate(**update_data)
    ticket = _run(ticket_service.update_ticket(args.id, data))
    if not ticket:
        print(f"Error: ticket #{args.id} not found", file=sys.stderr)
        sys.exit(1)
    print(f"Updated ticket #{ticket.id}.")


def handle_delete(args: Namespace) -> None:
    _ensure_db()
    deleted = _run(ticket_service.delete_ticket(args.id))
    if not deleted:
        print(f"Error: ticket #{args.id} not found", file=sys.stderr)
        sys.exit(1)
    print(f"Deleted ticket #{args.id}.")


def handle_stats(args: Namespace) -> None:
    _ensure_db()
    stats = _run(ticket_service.get_ticket_stats())
    print(format_ticket_stats(stats))
