"""Plain-text formatting for CLI ticket output."""
from __future__ import annotations

from typing import List

from app.models.schemas import Ticket, TicketStats

STATUS_ICONS = {
    "open": "[ ]",
    "in_progress": "[~]",
    "solved": "[x]",
    "wont_fix": "[-]",
}

PRIORITY_LABELS = {
    "low": "LOW",
    "medium": "MED",
    "high": "HIGH",
    "critical": "CRIT",
}


def _truncate(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    return text[: width - 3] + "..."


def format_ticket_table(tickets: List[Ticket]) -> str:
    """Format a list of tickets as an ASCII table."""
    if not tickets:
        return "No tickets found."

    header = (
        f"{'ID':>4}  {'St':<4}  {'Pri':<4}  {'Title':<40}  {'Tags':<20}  {'Created':<16}"
    )
    separator = "-" * len(header)
    lines = [header, separator]

    for t in tickets:
        tags_str = ", ".join(t.tags) if t.tags else ""
        created = t.created_at[:16] if t.created_at else ""
        line = (
            f"{t.id:>4}  "
            f"{STATUS_ICONS.get(t.status.value, '[ ]'):<4}  "
            f"{PRIORITY_LABELS.get(t.priority.value, 'MED'):<4}  "
            f"{_truncate(t.title, 40):<40}  "
            f"{_truncate(tags_str, 20):<20}  "
            f"{created:<16}"
        )
        lines.append(line)

    lines.append(f"\n{len(tickets)} ticket(s)")
    return "\n".join(lines)


def format_ticket_detail(ticket: Ticket) -> str:
    """Format a single ticket for detailed view."""
    tags_str = ", ".join(ticket.tags) if ticket.tags else "(none)"
    lines = [
        f"Ticket #{ticket.id}",
        f"  Title:       {ticket.title}",
        f"  Status:      {ticket.status.value}",
        f"  Priority:    {ticket.priority.value}",
        f"  Tags:        {tags_str}",
    ]
    if ticket.description:
        lines.append(f"  Description: {ticket.description}")
    if ticket.resolution:
        lines.append(f"  Resolution:  {ticket.resolution}")
    lines.append(f"  Created:     {ticket.created_at}")
    lines.append(f"  Updated:     {ticket.updated_at}")
    if ticket.solved_at:
        lines.append(f"  Solved:      {ticket.solved_at}")
    return "\n".join(lines)


def format_ticket_stats(stats: TicketStats) -> str:
    """Format ticket statistics."""
    lines = [
        f"Total tickets: {stats.total}",
        "",
        "By status:",
    ]
    for status in ("open", "in_progress", "solved", "wont_fix"):
        count = stats.by_status.get(status, 0)
        if count:
            lines.append(f"  {status:<12} {count}")

    lines.append("")
    lines.append("By priority:")
    for priority in ("critical", "high", "medium", "low"):
        count = stats.by_priority.get(priority, 0)
        if count:
            lines.append(f"  {priority:<12} {count}")

    return "\n".join(lines)
