"""Process registry and mechanism matching."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, cast

from fungal_model.core.errors import InvalidMechanismError
from fungal_model.processes.base import Process
from fungal_model.processes.factories import (
    BuildDecision,
    ProcessBuildContext,
    ProcessFactory,
    default_foundation_factories,
)


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

        requested = cast(tuple[str, ...], tuple(getattr(context, "requested_processes", ()) or ()))
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
    """Public process library for process objects and process factories."""

    def __init__(
        self,
        processes: Iterable[Process] | None = None,
        factories: Iterable[ProcessFactory] | None = None,
    ) -> None:
        super().__init__(processes)
        self._factories: dict[str, ProcessFactory] = {}
        for factory in factories or ():
            self.register_factory(factory)

    @classmethod
    def default_foundation(cls) -> "ProcessLibrary":
        """Return the default foundation process library."""

        return cls(factories=default_foundation_factories())

    def register_process(self, process: Process) -> None:
        self.register(process)

    def register_factory(self, factory: ProcessFactory) -> None:
        if factory.process_type in self._factories:
            raise InvalidMechanismError(f"Duplicate process factory: {factory.process_type}")
        self._factories[factory.process_type] = factory

    @property
    def factories(self) -> tuple[ProcessFactory, ...]:
        return tuple(self._factories.values())

    def factory_types(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))

    def factory_for(self, process_type: str) -> ProcessFactory:
        try:
            return self._factories[process_type]
        except KeyError as exc:
            available = ", ".join(self.factory_types()) or "none"
            raise InvalidMechanismError(
                f"No process factory registered for {process_type!r}. "
                f"Registered factory types: {available}."
            ) from exc

    def build_decisions(
        self,
        context: ProcessBuildContext,
        process_configs: Iterable[Any],
    ) -> tuple[BuildDecision, ...]:
        decisions: list[BuildDecision] = []
        for process_config in process_configs:
            factory = self.factory_for(process_config.process_type)
            decisions.append(factory.can_build(context, process_config))
        return tuple(decisions)

    def build_processes(
        self,
        context: ProcessBuildContext,
        process_configs: Iterable[Any],
    ) -> tuple[Process, ...]:
        processes: list[Process] = []
        for process_config in process_configs:
            factory = self.factory_for(process_config.process_type)
            decision = factory.can_build(context, process_config)
            if not decision.can_build:
                raise InvalidMechanismError(
                    f"Process factory {decision.factory} cannot build "
                    f"{process_config.id!r}: {decision.to_dict()}"
                )
            processes.append(factory.build(context, process_config))
        return tuple(processes)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["factory_types"] = list(self.factory_types())
        return data


__all__ = ["MissingProcessIssue", "ProcessLibrary", "ProcessRegistry"]
