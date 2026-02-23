"""Keyword definitions -- tooltip keywords that appear on cards and relics."""

from __future__ import annotations

from pydantic import BaseModel


class KeywordDefinition(BaseModel):
    """A custom keyword that can be referenced by cards, relics, and potions.

    Keywords appear as bold highlighted terms in card text.  Hovering over
    them shows the description as a tooltip.
    """

    id: str
    """Unique identifier used to reference this keyword (e.g. 'my_mod:Ignite')."""

    name: str
    """Display name shown as the bold keyword text."""

    description: str
    """Tooltip text explaining what the keyword means."""
