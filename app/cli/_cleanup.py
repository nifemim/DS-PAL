"""Ticket cleanup utilities for improving title and description quality."""
from __future__ import annotations

import re
from typing import Tuple

# Common action verbs for ticket titles
ACTION_VERBS = [
    "Add", "Fix", "Remove", "Update", "Implement", "Refactor", "Create",
    "Delete", "Move", "Rename", "Extract", "Merge", "Split", "Optimize",
    "Improve", "Enable", "Disable", "Configure", "Set up", "Clean up",
    "Migrate", "Convert", "Replace", "Integrate", "Support", "Handle",
    "Validate", "Test", "Document", "Deploy", "Build", "Install", "Show",
    "Hide", "Display", "Prevent", "Allow", "Ensure", "Make", "Use",
    "Change", "Modify", "Adjust", "Apply", "Load", "Save", "Export",
    "Import", "Fetch", "Send", "Parse", "Format", "Render", "Generate",
]

# Words that suggest a specific action verb
VERB_SUGGESTIONS = {
    "bug": "Fix",
    "error": "Fix",
    "broken": "Fix",
    "crash": "Fix",
    "issue": "Fix",
    "problem": "Fix",
    "wrong": "Fix",
    "new": "Add",
    "feature": "Add",
    "missing": "Add",
    "need": "Add",
    "want": "Add",
    "get rid": "Remove",
    "delete": "Remove",
    "superfluous": "Remove",
    "unnecessary": "Remove",
    "redundant": "Remove",
    "unused": "Remove",
    "change": "Update",
    "modify": "Update",
    "edit": "Update",
    "clean": "Refactor",
    "cleanup": "Refactor",
    "restructure": "Refactor",
    "reorganize": "Refactor",
    "slow": "Optimize",
    "performance": "Optimize",
    "fast": "Optimize",
    "speed": "Optimize",
}


def _starts_with_action_verb(title: str) -> bool:
    """Check if title starts with an action verb."""
    title_lower = title.lower()
    for verb in ACTION_VERBS:
        if title_lower.startswith(verb.lower()):
            return True
    return False


def _suggest_action_verb(title: str, description: str) -> str:
    """Suggest an action verb based on title and description content."""
    combined = (title + " " + description).lower()

    for keyword, verb in VERB_SUGGESTIONS.items():
        if keyword in combined:
            return verb

    return "Implement"  # Default fallback


def _capitalize_first(text: str) -> str:
    """Capitalize first letter of text."""
    if not text:
        return text
    return text[0].upper() + text[1:]


def _ensure_period(text: str) -> str:
    """Ensure text ends with proper punctuation."""
    text = text.rstrip()
    if text and text[-1] not in ".!?":
        text += "."
    return text


def _clean_whitespace(text: str) -> str:
    """Normalize whitespace in text."""
    # Replace multiple spaces with single space
    text = re.sub(r" +", " ", text)
    # Remove space before punctuation
    text = re.sub(r" ([.,!?;:])", r"\1", text)
    # Add space after punctuation if missing
    text = re.sub(r"([.,!?;:])([A-Za-z])", r"\1 \2", text)
    return text.strip()


def _format_description(description: str) -> str:
    """Format description for clarity."""
    if not description:
        return description

    # Clean whitespace
    description = _clean_whitespace(description)

    # Capitalize first letter
    description = _capitalize_first(description)

    # Ensure ends with period
    description = _ensure_period(description)

    return description


def _format_title(title: str, description: str) -> str:
    """Format title to be actionable and clear."""
    title = _clean_whitespace(title)

    # If title doesn't start with action verb, add one
    if not _starts_with_action_verb(title):
        verb = _suggest_action_verb(title, description)
        # Remove common non-action starting words
        title = re.sub(r"^(the|a|an|we need to|we should|should|need to|must)\s+", "", title, flags=re.IGNORECASE)
        title = _capitalize_first(title)
        title = f"{verb} {title[0].lower()}{title[1:]}" if title else verb

    # Capitalize first letter
    title = _capitalize_first(title)

    # Remove trailing period from title (titles shouldn't end with period)
    title = title.rstrip(".")

    return title


def cleanup_ticket(title: str, description: str) -> Tuple[str, str]:
    """
    Clean up a ticket's title and description.

    Returns:
        Tuple of (cleaned_title, cleaned_description)
    """
    cleaned_title = _format_title(title, description)
    cleaned_description = _format_description(description)

    return cleaned_title, cleaned_description


def preview_cleanup(title: str, description: str) -> str:
    """
    Generate a preview of cleanup changes.

    Returns:
        A formatted string showing before/after changes.
    """
    new_title, new_description = cleanup_ticket(title, description)

    lines = []

    if new_title != title:
        lines.append("Title:")
        lines.append(f"  - {title}")
        lines.append(f"  + {new_title}")

    if new_description != description:
        if lines:
            lines.append("")
        lines.append("Description:")
        # Truncate long descriptions for preview
        old_preview = description[:100] + "..." if len(description) > 100 else description
        new_preview = new_description[:100] + "..." if len(new_description) > 100 else new_description
        lines.append(f"  - {old_preview}")
        lines.append(f"  + {new_preview}")

    if not lines:
        return "(no changes needed)"

    return "\n".join(lines)
