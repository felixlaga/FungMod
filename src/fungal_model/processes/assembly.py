"""Model assembly skeleton for process-centered FungMod models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from fungal_model.core.assumptions import Assumption
from fungal_model.core.errors import (
    IncompatibleUnitsError,
    MissingParameterError,
    MissingProcessError,
)
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.provenance import ProvenanceError, UnknownParameterError
from fungal_model.core.simulation import SolverSettings
from fungal_model.core.units import UnitError, assert_compatible
from fungal_model.processes.base import Process, StateVariableSpec
from fungal_model.processes.registry import MissingProcessIssue, ProcessRegistry


@dataclass(frozen=True)
class ModelAssemblyContext:
    """Inputs used to decide which processes can assemble a model."""

    fungus: Any | None = None
    substrates: tuple[Any, ...] = ()
    environment: Any | None = None
    geometry: Any | None = None
    requested_processes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "fungus": _entity_name(self.fungus),
            "substrates": [_entity_name(substrate) for substrate in self.substrates],
            "environment": _entity_name(self.environment),
            "geometry": _entity_name(self.geometry),
            "requested_processes": list(self.requested_processes),
        }


@dataclass(frozen=True)
class ProcessMatch:
    """A process selected during assembly."""

    name: str
    process_type: str

    @classmethod
    def from_process(cls, process: Process) -> "ProcessMatch":
        return cls(name=process.name, process_type=process.process_type)

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "process_type": self.process_type,
        }


@dataclass(frozen=True)
class ParameterIssue:
    """A required parameter problem discovered during assembly."""

    symbol: str
    process_name: str
    expected_units: str
    reason: str
    message: str
    supplied_units: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "symbol": self.symbol,
            "process_name": self.process_name,
            "expected_units": self.expected_units,
            "supplied_units": self.supplied_units,
            "reason": self.reason,
            "message": self.message,
        }


@dataclass(frozen=True)
class AssemblyReport:
    """Machine- and human-readable model assembly report."""

    context: ModelAssemblyContext
    matched_processes: tuple[ProcessMatch, ...] = ()
    missing_processes: tuple[MissingProcessIssue, ...] = ()
    missing_parameters: tuple[ParameterIssue, ...] = ()
    incompatible_units: tuple[ParameterIssue, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def success(self) -> bool:
        return (
            not self.missing_processes
            and not self.missing_parameters
            and not self.incompatible_units
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "context": self.context.to_dict(),
            "matched_processes": [
                match.to_dict() for match in self.matched_processes
            ],
            "missing_processes": [
                issue.to_dict() for issue in self.missing_processes
            ],
            "missing_parameters": [
                issue.to_dict() for issue in self.missing_parameters
            ],
            "incompatible_units": [
                issue.to_dict() for issue in self.incompatible_units
            ],
            "warnings": list(self.warnings),
        }

    def human_readable(self) -> str:
        lines = ["Assembly report:"]
        lines.extend(_section("matched processes", _format_matches(self.matched_processes)))
        lines.extend(_section("missing processes", _format_missing_processes(self.missing_processes)))
        lines.extend(_section("missing parameters", _format_parameter_issues(self.missing_parameters)))
        lines.extend(_section("incompatible units", _format_parameter_issues(self.incompatible_units)))
        lines.extend(_section("warnings", list(self.warnings)))
        return "\n".join(lines)


@dataclass(frozen=True)
class AssembledModel:
    """A process-centered model that has passed Milestone 1 assembly checks."""

    processes: tuple[Process, ...]
    parameters: ParameterSet
    context: ModelAssemblyContext
    state_variables: tuple[StateVariableSpec, ...]
    assumptions: tuple[Assumption, ...]
    validators: tuple[Any, ...]
    solver_settings: SolverSettings
    assembly_report: AssemblyReport

    def run(self, *args: Any, **kwargs: Any) -> Any:
        """Placeholder until solver-backed process execution is implemented."""

        del args, kwargs
        raise NotImplementedError(
            "Process-centered solver execution is scheduled after Milestone 1. "
            "Use the existing SimulationEngine or ReactionDiffusionEngine1D for "
            "current runnable models."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "processes": [process.to_dict() for process in self.processes],
            "parameters": self.parameters.to_dict(),
            "context": self.context.to_dict(),
            "state_variables": [
                variable.to_dict() for variable in self.state_variables
            ],
            "assumptions": [assumption.to_dict() for assumption in self.assumptions],
            "validators": [str(validator) for validator in self.validators],
            "solver_settings": self.solver_settings.to_dict(),
            "assembly_report": self.assembly_report.to_dict(),
        }


@dataclass(frozen=True)
class ModelBuilder:
    """Assemble a model from entities, requested processes, and parameters."""

    fungus: Any | None = None
    substrates: Sequence[Any] = ()
    environment: Any | None = None
    geometry: Any | None = None
    process_library: ProcessRegistry | None = None
    parameters: ParameterSet = field(default_factory=ParameterSet)
    requested_processes: Sequence[str] = ()
    state_variables: Sequence[StateVariableSpec] = ()
    validators: Sequence[Any] = ()
    solver_settings: SolverSettings = field(default_factory=SolverSettings)
    allow_unsourced_for_testing: bool = False

    def assemble(self) -> AssembledModel:
        registry = self.process_library or ProcessRegistry.default()
        context = ModelAssemblyContext(
            fungus=self.fungus,
            substrates=tuple(self.substrates),
            environment=self.environment,
            geometry=self.geometry,
            requested_processes=tuple(self.requested_processes),
        )
        processes, missing_processes = registry.match_required_processes(context)
        missing_parameters, incompatible_units = _parameter_issues(
            processes,
            self.parameters,
            allow_unsourced_for_testing=self.allow_unsourced_for_testing,
        )
        report = AssemblyReport(
            context=context,
            matched_processes=tuple(ProcessMatch.from_process(process) for process in processes),
            missing_processes=missing_processes,
            missing_parameters=missing_parameters,
            incompatible_units=incompatible_units,
        )
        if missing_processes:
            raise MissingProcessError("Model assembly failed: missing process.", report=report)
        if incompatible_units:
            raise IncompatibleUnitsError(
                "Model assembly failed: incompatible parameter units.",
                report=report,
            )
        if missing_parameters:
            raise MissingParameterError("Model assembly failed: missing parameter.", report=report)

        return AssembledModel(
            processes=processes,
            parameters=self.parameters,
            context=context,
            state_variables=_collect_state_variables(processes, self.state_variables),
            assumptions=_collect_assumptions(processes),
            validators=tuple(self.validators),
            solver_settings=self.solver_settings,
            assembly_report=report,
        )


def _entity_name(entity: Any | None) -> str | None:
    if entity is None:
        return None
    return str(getattr(entity, "name", entity.__class__.__name__))


def _parameter_issues(
    processes: Sequence[Process],
    parameters: ParameterSet,
    *,
    allow_unsourced_for_testing: bool,
) -> tuple[tuple[ParameterIssue, ...], tuple[ParameterIssue, ...]]:
    missing: list[ParameterIssue] = []
    incompatible: list[ParameterIssue] = []
    for process in processes:
        for requirement in process.required_parameters:
            if not requirement.required:
                continue
            try:
                parameter = parameters.get(requirement.symbol)
            except KeyError:
                missing.append(
                    ParameterIssue(
                        symbol=requirement.symbol,
                        process_name=process.name,
                        expected_units=requirement.units,
                        reason="absent",
                        message="Required parameter is absent from the supplied ParameterSet.",
                    )
                )
                continue
            try:
                parameter.validate_provenance(
                    allow_unsourced_for_testing=allow_unsourced_for_testing
                )
                parameter.validate_value()
                assert_compatible(parameter.quantity, requirement.units, name=requirement.symbol)
            except ProvenanceError:
                missing.append(
                    ParameterIssue(
                        symbol=requirement.symbol,
                        process_name=process.name,
                        expected_units=requirement.units,
                        supplied_units=parameter.units,
                        reason="missing_source",
                        message=(
                            "Required parameter is present but lacks provenance. "
                            "Use allow_unsourced_for_testing only for explicit tests."
                        ),
                    )
                )
            except UnknownParameterError:
                missing.append(
                    ParameterIssue(
                        symbol=requirement.symbol,
                        process_name=process.name,
                        expected_units=requirement.units,
                        supplied_units=parameter.units,
                        reason="unknown_value",
                        message="Required parameter is explicitly unknown.",
                    )
                )
            except UnitError as exc:
                incompatible.append(
                    ParameterIssue(
                        symbol=requirement.symbol,
                        process_name=process.name,
                        expected_units=requirement.units,
                        supplied_units=parameter.units,
                        reason="incompatible_units",
                        message=str(exc),
                    )
                )
    return tuple(missing), tuple(incompatible)


def _collect_state_variables(
    processes: Sequence[Process],
    provided: Sequence[StateVariableSpec],
) -> tuple[StateVariableSpec, ...]:
    variables: list[StateVariableSpec] = []
    seen: set[str] = set()
    for spec in tuple(provided) + tuple(
        variable for process in processes for variable in process.state_variables
    ):
        if spec.name not in seen:
            variables.append(spec)
            seen.add(spec.name)
    return tuple(variables)


def _collect_assumptions(processes: Sequence[Process]) -> tuple[Assumption, ...]:
    assumptions: list[Assumption] = []
    seen: set[str] = set()
    for process in processes:
        for assumption in process.assumptions:
            if assumption.name not in seen:
                assumptions.append(assumption)
                seen.add(assumption.name)
    return tuple(assumptions)


def _section(title: str, items: list[str]) -> list[str]:
    lines = [f"    {title}:"]
    if not items:
        lines.append("        - none")
        return lines
    lines.extend(f"        - {item}" for item in items)
    return lines


def _format_matches(matches: Sequence[ProcessMatch]) -> list[str]:
    return [f"{match.name} ({match.process_type})" for match in matches]


def _format_missing_processes(issues: Sequence[MissingProcessIssue]) -> list[str]:
    return [f"{issue.process_type}: {issue.message}" for issue in issues]


def _format_parameter_issues(issues: Sequence[ParameterIssue]) -> list[str]:
    return [
        (
            f"{issue.symbol} for {issue.process_name}: {issue.reason}; "
            f"expected {issue.expected_units}"
            + ("" if issue.supplied_units is None else f", supplied {issue.supplied_units}")
        )
        for issue in issues
    ]


__all__ = [
    "AssembledModel",
    "AssemblyReport",
    "ModelAssemblyContext",
    "ModelBuilder",
    "ParameterIssue",
    "ProcessMatch",
]
