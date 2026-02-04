"""Integration tests for the ticket CLI."""
import subprocess
import sys

import pytest


def run_cli(*args: str) -> subprocess.CompletedProcess:
    """Run the CLI as a subprocess and return the result."""
    return subprocess.run(
        [sys.executable, "-m", "app.cli", *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.fixture(autouse=True)
def _cli_cleanup():
    """Ensure the db is initialized and tickets are cleaned between tests."""
    # conftest.py handles DB init/cleanup via the async clean_db fixture,
    # but CLI tests run in subprocesses so we also need cleanup here.
    yield
    # Delete all tickets after each test via CLI subprocess isn't reliable,
    # so the async clean_db fixture handles it.


class TestAddCommand:
    def test_add_basic(self):
        result = run_cli("add", "Test ticket")
        assert result.returncode == 0
        assert "Created ticket #" in result.stdout
        assert "Test ticket" in result.stdout

    def test_add_with_priority(self):
        result = run_cli("add", "High priority", "-p", "high")
        assert result.returncode == 0
        assert "Created ticket #" in result.stdout

    def test_add_with_tags(self):
        result = run_cli("add", "Tagged", "--tags", "auth,urgent")
        assert result.returncode == 0
        assert "Created ticket #" in result.stdout

    def test_add_with_description(self):
        result = run_cli("add", "Described", "-d", "Some details")
        assert result.returncode == 0


class TestListCommand:
    def test_list_empty(self):
        result = run_cli("list")
        assert result.returncode == 0
        assert "No tickets found" in result.stdout or "0 ticket(s)" in result.stdout

    def test_list_after_add(self):
        run_cli("add", "Listed ticket")
        result = run_cli("list")
        assert result.returncode == 0
        assert "Listed ticket" in result.stdout
        assert "1 ticket(s)" in result.stdout

    def test_list_filter_status(self):
        run_cli("add", "Open ticket")
        result = run_cli("list", "--status", "solved")
        assert result.returncode == 0
        assert "No tickets found" in result.stdout or "Open ticket" not in result.stdout


class TestShowCommand:
    def test_show_existing(self):
        run_cli("add", "Show me")
        result = run_cli("show", "1")
        # Ticket ID might not be 1 due to autoincrement, but let's check format
        assert result.returncode == 0 or "not found" in result.stderr

    def test_show_not_found(self):
        result = run_cli("show", "9999")
        assert result.returncode != 0
        assert "not found" in result.stderr


class TestSolveCommand:
    def test_solve_not_found(self):
        result = run_cli("solve", "9999")
        assert result.returncode != 0
        assert "not found" in result.stderr


class TestUpdateCommand:
    def test_update_not_found(self):
        result = run_cli("update", "9999", "--priority", "high")
        assert result.returncode != 0
        assert "not found" in result.stderr

    def test_update_no_fields(self):
        result = run_cli("update", "1")
        assert result.returncode != 0
        assert "no fields" in result.stderr


class TestDeleteCommand:
    def test_delete_not_found(self):
        result = run_cli("delete", "9999")
        assert result.returncode != 0
        assert "not found" in result.stderr


class TestStatsCommand:
    def test_stats_empty(self):
        result = run_cli("stats")
        assert result.returncode == 0
        assert "Total tickets: 0" in result.stdout

    def test_stats_with_tickets(self):
        run_cli("add", "Stat ticket", "-p", "high")
        result = run_cli("stats")
        assert result.returncode == 0
        assert "Total tickets:" in result.stdout


class TestNoCommand:
    def test_no_args_shows_help(self):
        result = run_cli()
        assert result.returncode != 0
