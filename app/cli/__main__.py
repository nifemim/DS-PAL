"""CLI entry point: python3 -m app.cli <command>."""
from __future__ import annotations

import argparse
import sys

from .tickets import (
    handle_add,
    handle_cleanup,
    handle_delete,
    handle_list,
    handle_show,
    handle_solve,
    handle_stats,
    handle_update,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m app.cli",
        description="DS-PAL fix-later ticket manager",
    )
    sub = parser.add_subparsers(dest="command")

    # add
    p_add = sub.add_parser("add", help="Create a new ticket")
    p_add.add_argument("title", help="Ticket title")
    p_add.add_argument("-d", "--description", default="", help="Ticket description")
    p_add.add_argument(
        "-p", "--priority", default="medium",
        choices=["low", "medium", "high", "critical"],
        help="Priority level (default: medium)",
    )
    p_add.add_argument("--tags", default="", help="Comma-separated tags")
    p_add.set_defaults(func=handle_add)

    # list
    p_list = sub.add_parser("list", help="List tickets")
    p_list.add_argument("--status", default=None, help="Filter by status")
    p_list.add_argument("--priority", default=None, help="Filter by priority")
    p_list.add_argument("--tag", default=None, help="Filter by tag")
    p_list.set_defaults(func=handle_list)

    # show
    p_show = sub.add_parser("show", help="Show ticket details")
    p_show.add_argument("id", type=int, help="Ticket ID")
    p_show.set_defaults(func=handle_show)

    # solve
    p_solve = sub.add_parser("solve", help="Mark a ticket as solved")
    p_solve.add_argument("id", type=int, help="Ticket ID")
    p_solve.add_argument("-r", "--resolution", default="", help="Resolution note")
    p_solve.set_defaults(func=handle_solve)

    # update
    p_update = sub.add_parser("update", help="Update a ticket")
    p_update.add_argument("id", type=int, help="Ticket ID")
    p_update.add_argument("--title", default=None, help="New title")
    p_update.add_argument("-d", "--description", default=None, help="New description")
    p_update.add_argument(
        "--status", default=None,
        choices=["open", "in_progress", "solved", "wont_fix"],
        help="New status",
    )
    p_update.add_argument(
        "--priority", default=None,
        choices=["low", "medium", "high", "critical"],
        help="New priority",
    )
    p_update.add_argument("--tags", default=None, help="New comma-separated tags")
    p_update.add_argument("-r", "--resolution", default=None, help="Resolution note")
    p_update.set_defaults(func=handle_update)

    # delete
    p_delete = sub.add_parser("delete", help="Delete a ticket")
    p_delete.add_argument("id", type=int, help="Ticket ID")
    p_delete.set_defaults(func=handle_delete)

    # stats
    p_stats = sub.add_parser("stats", help="Show ticket statistics")
    p_stats.set_defaults(func=handle_stats)

    # cleanup
    p_cleanup = sub.add_parser("cleanup", help="Clean up ticket titles and descriptions")
    p_cleanup.add_argument("ids", type=int, nargs="*", help="Ticket IDs to clean up")
    p_cleanup.add_argument("--all", action="store_true", help="Clean up all tickets")
    p_cleanup.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    p_cleanup.add_argument("-q", "--quiet", action="store_true", help="Suppress detailed output")
    p_cleanup.set_defaults(func=handle_cleanup)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
