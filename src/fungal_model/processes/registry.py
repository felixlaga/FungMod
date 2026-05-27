"""Process registry and mechanism matching."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from fungal_model.core.errors import InvalidMechanismError
from fungal_model.processes.base import Process


@dataclass(frozen=True)
class MissingProcessIssue:
    """A requested mechanism that no registered process can satisfy."""

    process_type: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "process_type": self.process_type,
            "message": self.message,
        }


class ProcessRegistry:
    """Container that matches available processes to an assembly context."""

    def __init__(self, processes: Iterable[Process] | None = None) -> None:
        self._processes: dict[str, Process] = {}
        for process in processes or ():
            self.register(process)

    @classmethod
    def default(cls) -> "ProcessRegistry":
        """Return the default registry for the current milestone.

        Milestone 1 intentionally ships an empty default registry. Later
        milestones can add generic processes here only after they are tested.
        """

        return cls()

    def register(self, process: Process) -> None:
        if process.name in self._processes:
            raise InvalidMechanismError(f"Duplicate process name: {process.name}")
        self._processes[process.name] = process

    @property
    def processes(self) -> tuple[Process, ...]:
        return tuple(self._processes.values())

    def process_types(self) -> tuple[str, ...]:
        return tuple(sorted({process.process_type for process in self._processes.values()}))

    def find_candidates(self, process_type: str, context: Any) -> tuple[Process, ...]:
        """Return registered processes that can satisfy one requested type."""

        return tuple(
            process
            for process in self._processes.values()
            if process.applies_to(context)
            and (process.process_type == process_type or process.name == process_type)
        )

    def match_required_processes(
        self,
        context: Any,
    ) -> tuple[tuple[Process, ...], tuple[MissingProcessIssue, ...]]:
        """Match requested process types and report absent mechanisms."""

        requested = tuple(getattr(context, "requested_processes", ()) or ())
        if not requested:
            return (
                tuple(process for process in self._processes.values() if process.applies_to(context)),
                (),
            )

        matched: list[Process] = []
        missing: list[MissingProcessIssue] = []
        seen_names: set[str] = set()
        for process_type in requested:
            candidates = self.find_candidates(process_type, context)
            if not candidates:
                missing.append(
                    MissingProcessIssue(
                        process_type=process_type,
                        message=(
                            "No registered process matched the requested mechanism. "
                            "Provide a process implementation or remove this mechanism "
                            "from the assembly request."
                        ),
                    )
                )
                continue
            for process in candidates:
                if process.name not in seen_names:
                    matched.append(process)
                    seen_names.add(process.name)
        return tuple(matched), tuple(missing)

    def to_dict(self) -> dict[str, Any]:
        return {
            "processes": [process.to_dict() for process in self.processes],
            "process_types": list(self.process_types()),
        }


class ProcessLibrary(ProcessRegistry):
    """Public process library for already-built foundation process objects."""

    @classmethod
    def default_foundation(cls) -> "ProcessLibrary":
        """Return the default foundation process library."""

        return cls()

    def register_process(self, process: Process) -> None:
        self.register(process)


__all__ = ["MissingProcessIssue", "ProcessLibrary", "ProcessRegistry"]
