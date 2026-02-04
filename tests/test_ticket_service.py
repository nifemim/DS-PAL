"""Tests for the ticket service layer."""
import pytest

from app.models.schemas import (
    TicketCreate,
    TicketPriority,
    TicketStatus,
    TicketUpdate,
)
from app.services import ticket_service


@pytest.mark.asyncio
async def test_create_ticket():
    data = TicketCreate(title="Test bug", priority=TicketPriority.HIGH, tags=["auth"])
    ticket = await ticket_service.create_ticket(data)

    assert ticket.id is not None
    assert ticket.title == "Test bug"
    assert ticket.priority == TicketPriority.HIGH
    assert ticket.status == TicketStatus.OPEN
    assert ticket.tags == ["auth"]
    assert ticket.created_at


@pytest.mark.asyncio
async def test_create_ticket_defaults():
    data = TicketCreate(title="Simple ticket")
    ticket = await ticket_service.create_ticket(data)

    assert ticket.priority == TicketPriority.MEDIUM
    assert ticket.status == TicketStatus.OPEN
    assert ticket.tags == []
    assert ticket.description == ""


@pytest.mark.asyncio
async def test_get_ticket():
    data = TicketCreate(title="Fetch me")
    created = await ticket_service.create_ticket(data)

    ticket = await ticket_service.get_ticket(created.id)
    assert ticket is not None
    assert ticket.title == "Fetch me"


@pytest.mark.asyncio
async def test_get_ticket_not_found():
    ticket = await ticket_service.get_ticket(9999)
    assert ticket is None


@pytest.mark.asyncio
async def test_list_tickets_empty():
    tickets = await ticket_service.list_tickets()
    assert tickets == []


@pytest.mark.asyncio
async def test_list_tickets_returns_all():
    await ticket_service.create_ticket(TicketCreate(title="A"))
    await ticket_service.create_ticket(TicketCreate(title="B"))

    tickets = await ticket_service.list_tickets()
    assert len(tickets) == 2


@pytest.mark.asyncio
async def test_list_tickets_filter_by_status():
    t = await ticket_service.create_ticket(TicketCreate(title="Open one"))
    await ticket_service.create_ticket(TicketCreate(title="Another"))
    await ticket_service.solve_ticket(t.id, "done")

    open_tickets = await ticket_service.list_tickets(status="open")
    assert len(open_tickets) == 1
    assert open_tickets[0].title == "Another"


@pytest.mark.asyncio
async def test_list_tickets_filter_by_priority():
    await ticket_service.create_ticket(
        TicketCreate(title="Low", priority=TicketPriority.LOW)
    )
    await ticket_service.create_ticket(
        TicketCreate(title="High", priority=TicketPriority.HIGH)
    )

    high = await ticket_service.list_tickets(priority="high")
    assert len(high) == 1
    assert high[0].title == "High"


@pytest.mark.asyncio
async def test_list_tickets_filter_by_tag():
    await ticket_service.create_ticket(
        TicketCreate(title="Tagged", tags=["ui", "bug"])
    )
    await ticket_service.create_ticket(TicketCreate(title="No tags"))

    tagged = await ticket_service.list_tickets(tag="ui")
    assert len(tagged) == 1
    assert tagged[0].title == "Tagged"


@pytest.mark.asyncio
async def test_list_tickets_sorted_by_priority():
    await ticket_service.create_ticket(
        TicketCreate(title="Low", priority=TicketPriority.LOW)
    )
    await ticket_service.create_ticket(
        TicketCreate(title="Critical", priority=TicketPriority.CRITICAL)
    )
    await ticket_service.create_ticket(
        TicketCreate(title="High", priority=TicketPriority.HIGH)
    )

    tickets = await ticket_service.list_tickets()
    priorities = [t.priority.value for t in tickets]
    assert priorities == ["critical", "high", "low"]


@pytest.mark.asyncio
async def test_update_ticket():
    t = await ticket_service.create_ticket(TicketCreate(title="Original"))
    updated = await ticket_service.update_ticket(
        t.id,
        TicketUpdate(title="Changed", priority=TicketPriority.CRITICAL),
    )

    assert updated is not None
    assert updated.title == "Changed"
    assert updated.priority == TicketPriority.CRITICAL


@pytest.mark.asyncio
async def test_update_ticket_not_found():
    result = await ticket_service.update_ticket(
        9999, TicketUpdate(title="Nope")
    )
    assert result is None


@pytest.mark.asyncio
async def test_update_ticket_sets_solved_at():
    t = await ticket_service.create_ticket(TicketCreate(title="To solve"))
    updated = await ticket_service.update_ticket(
        t.id, TicketUpdate(status=TicketStatus.SOLVED)
    )

    assert updated is not None
    assert updated.status == TicketStatus.SOLVED
    assert updated.solved_at is not None


@pytest.mark.asyncio
async def test_solve_ticket():
    t = await ticket_service.create_ticket(TicketCreate(title="Bug"))
    solved = await ticket_service.solve_ticket(t.id, "Fixed in v2")

    assert solved is not None
    assert solved.status == TicketStatus.SOLVED
    assert solved.resolution == "Fixed in v2"
    assert solved.solved_at is not None


@pytest.mark.asyncio
async def test_solve_ticket_not_found():
    result = await ticket_service.solve_ticket(9999)
    assert result is None


@pytest.mark.asyncio
async def test_delete_ticket():
    t = await ticket_service.create_ticket(TicketCreate(title="Delete me"))
    assert await ticket_service.delete_ticket(t.id) is True
    assert await ticket_service.get_ticket(t.id) is None


@pytest.mark.asyncio
async def test_delete_ticket_not_found():
    assert await ticket_service.delete_ticket(9999) is False


@pytest.mark.asyncio
async def test_get_ticket_stats_empty():
    stats = await ticket_service.get_ticket_stats()
    assert stats.total == 0
    assert stats.by_status == {}
    assert stats.by_priority == {}


@pytest.mark.asyncio
async def test_get_ticket_stats():
    await ticket_service.create_ticket(
        TicketCreate(title="A", priority=TicketPriority.HIGH)
    )
    await ticket_service.create_ticket(
        TicketCreate(title="B", priority=TicketPriority.HIGH)
    )
    t = await ticket_service.create_ticket(
        TicketCreate(title="C", priority=TicketPriority.LOW)
    )
    await ticket_service.solve_ticket(t.id, "done")

    stats = await ticket_service.get_ticket_stats()
    assert stats.total == 3
    assert stats.by_status["open"] == 2
    assert stats.by_status["solved"] == 1
    assert stats.by_priority["high"] == 2
    assert stats.by_priority["low"] == 1
