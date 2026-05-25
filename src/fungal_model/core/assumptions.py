"""Explicit modelling assumptions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Assumption:
    """A documented modelling assumption.

    Assumptions are separate from parameters so that a simulation can report
    what is known from data and what is a modelling choice.
    """

    name: str
    description: str
    justification: str
    known_limitations: str
    source: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "name": self.name,
            "description": self.description,
            "justification": self.justification,
            "known_limitations": self.known_limitations,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str | None]) -> "Assumption":
        return cls(
            name=str(data["name"]),
            description=str(data["description"]),
            justification=str(data["justification"]),
            known_limitations=str(data["known_limitations"]),
            source=data.get("source"),
        )


__all__ = ["Assumption"]

