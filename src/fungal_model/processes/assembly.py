"""Model assembly skeleton for process-centered FungMod models."""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Sequence

from fungal_model.core.assumptions import Assumption
from fungal_model.core.errors import (
    IncompatibleUnitsError,
    InvalidMechanismError,
    MissingParameterError,
    MissingProcessError,
)
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.provenance import ProvenanceError, UnknownParameterError
from fungal_model.core.simulation import SolverSettings
from fungal_model.core.units import Quantity, UnitError, assert_compatible
from fungal_model.processes.base import Process, StateVariableSpec
from fungal_model.processes.registry import MissingProcessIssue, ProcessRegistry

if TYPE_CHECKING:
    from fungal_model.chemistry.thermodynamics import DynamicThermodynamicConstraint
    from fungal_model.results import SimulationResult


@dataclass(frozen=True)
class ModelAssemblyContext:
    """Inputs used to decide which processes can assemble a model."""

    fungus: Any | None = None
    substrates: tuple[Any, ...] = ()
    enzymes: tuple[Any, ...] = ()
    environment: Any | None = None
    geometry: Any | None = None
    requested_processes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "fungus": _entity_name(self.fungus),
            "substrates": [_entity_name(substrate) for substrate in self.substrates],
            "enzymes": [_entity_name(enzyme) for enzyme in self.enzymes],
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
class CompatibilityIssue:
    """A biological or mechanism compatibility problem discovered during assembly."""

    process_name: str
    substrate: str
    reason: str
    message: str
    enzyme: str | None = None
    fungus: str | None = None
    bond_type: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "process_name": self.process_name,
            "substrate": self.substrate,
            "enzyme": self.enzyme,
            "fungus": self.fungus,
            "bond_type": self.bond_type,
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
    incompatible_mechanisms: tuple[CompatibilityIssue, ...] = ()
    static_balance_checks: tuple[Mapping[str, Any], ...] = ()
    dynamic_thermodynamic_constraints: tuple[Mapping[str, Any], ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def success(self) -> bool:
        return (
            not self.missing_processes
            and not self.missing_parameters
            and not self.incompatible_units
            and not self.incompatible_mechanisms
        )

    def to_dict(self) -> dict[str, Any]:
        data = {
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
            "incompatible_mechanisms": [
                issue.to_dict() for issue in self.incompatible_mechanisms
            ],
            "static_balance_checks": [
                dict(check) for check in self.static_balance_checks
            ],
            "warnings": list(self.warnings),
        }
        if self.dynamic_thermodynamic_constraints:
            data["dynamic_thermodynamic_constraints"] = [
                dict(constraint)
                for constraint in self.dynamic_thermodynamic_constraints
            ]
        return data

    def human_readable(self) -> str:
        lines = ["Assembly report:"]
        lines.extend(_section("matched processes", _format_matches(self.matched_processes)))
        lines.extend(_section("missing processes", _format_missing_processes(self.missing_processes)))
        lines.extend(_section("missing parameters", _format_parameter_issues(self.missing_parameters)))
        lines.extend(_section("incompatible units", _format_parameter_issues(self.incompatible_units)))
        lines.extend(_section("incompatible mechanisms", _format_compatibility_issues(self.incompatible_mechanisms)))
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
    thermodynamic_constraints: tuple[DynamicThermodynamicConstraint, ...] = ()

    def run(
        self,
        *,
        initial_state: Mapping[str, Quantity],
        t_span: tuple[Quantity, Quantity],
        t_eval: Quantity | None = None,
        validators: Sequence[Any] = (),
        label: str = "toy",
        name: str = "assembled_model",
    ) -> "SimulationResult":
        """Run this assembled model through the process ODE solver."""

        from fungal_model.solvers import ProcessODESolver, RunRequest

        return ProcessODESolver(self).run(
            RunRequest(
                initial_state=initial_state,
                t_span=t_span,
                t_eval=t_eval,
                validators=tuple(validators),
                label=label,
                name=name,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        data = {
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
        if self.thermodynamic_constraints:
            data["thermodynamic_constraints"] = [
                constraint.to_dict()
                for constraint in self.thermodynamic_constraints
            ]
        return data


@dataclass(frozen=True)
class ModelBuilder:
    """Assemble a model from entities, requested processes, and parameters."""

    fungus: Any | None = None
    substrates: Sequence[Any] = ()
    enzymes: Sequence[Any] = ()
    environment: Any | None = None
    geometry: Any | None = None
    process_library: ProcessRegistry | None = None
    parameters: ParameterSet = field(default_factory=ParameterSet)
    requested_processes: Sequence[str] = ()
    state_variables: Sequence[StateVariableSpec] = ()
    validators: Sequence[Any] = ()
    static_balance_checks: Sequence[Mapping[str, Any]] = ()
    thermodynamic_constraints: Sequence[DynamicThermodynamicConstraint] = ()
    solver_settings: SolverSettings = field(default_factory=SolverSettings)
    allow_unsourced_for_testing: bool = False

    def assemble(self) -> AssembledModel:
        registry = self.process_library or ProcessRegistry.default()
        context = ModelAssemblyContext(
            fungus=self.fungus,
            substrates=tuple(self.substrates),
            enzymes=tuple(self.enzymes),
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
        incompatible_mechanisms = _compatibility_issues(processes, context)
        report = AssemblyReport(
            context=context,
            matched_processes=tuple(ProcessMatch.from_process(process) for process in processes),
            missing_processes=missing_processes,
            missing_parameters=missing_parameters,
            incompatible_units=incompatible_units,
            incompatible_mechanisms=incompatible_mechanisms,
            static_balance_checks=tuple(dict(check) for check in self.static_balance_checks),
            dynamic_thermodynamic_constraints=tuple(
                constraint.to_dict()
                for constraint in self.thermodynamic_constraints
            ),
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
        if incompatible_mechanisms:
            raise InvalidMechanismError(
                "Model assembly failed: incompatible mechanism.",
                report=report,
            )

        return AssembledModel(
            processes=processes,
            parameters=self.parameters,
            context=context,
            state_variables=_collect_state_variables(processes, self.state_variables),
            assumptions=_collect_assumptions(processes),
            validators=tuple(self.validators),
            thermodynamic_constraints=tuple(self.thermodynamic_constraints),
            solver_settings=self.solver_settings,
            assembly_report=report,
        )


def _entity_name(entity: Any | None) -> str | None:
    if entity is None:
        return None
    return str(getattr(entity, "name", getattr(entity, "species_name", entity.__class__.__name__)))


def _compatibility_issues(
    processes: Sequence[Process],
    context: ModelAssemblyContext,
) -> tuple[CompatibilityIssue, ...]:
    issues: list[CompatibilityIssue] = []
    for process in processes:
        site_pool = getattr(process, "accessible_site_pool", None)
        if site_pool is None:
            continue
        bond_type = getattr(site_pool, "bond_type", None)
        for substrate in context.substrates:
            compatible_enzymes = tuple(
                enzyme
                for enzyme in context.enzymes
                if _enzyme_compatible(enzyme, substrate, bond_type=bond_type)
            )
            if context.enzymes and not compatible_enzymes:
                issues.append(
                    CompatibilityIssue(
                        process_name=process.name,
                        substrate=_entity_name(substrate) or "unknown",
                        enzyme=", ".join(_entity_name(enzyme) or "unknown" for enzyme in context.enzymes),
                        bond_type=bond_type,
                        reason="enzyme_substrate_mismatch",
                        message=(
                            "No supplied enzyme matches the substrate metadata, "
                            "required enzyme class, and target bond type."
                        ),
                    )
                )
            if context.fungus is not None and not _fungus_compatible(
                context.fungus,
                substrate,
                bond_type=bond_type,
                compatible_enzymes=compatible_enzymes,
            ):
                issues.append(
                    CompatibilityIssue(
                        process_name=process.name,
                        substrate=_entity_name(substrate) or "unknown",
                        fungus=_entity_name(context.fungus),
                        bond_type=bond_type,
                        reason="fungus_lacks_capability",
                        message=(
                            "The supplied fungus does not declare a compatible "
                            "enzyme capability for the substrate and bond type."
                        ),
                    )
                )
            if not context.enzymes and context.fungus is None:
                issues.append(
                    CompatibilityIssue(
                        process_name=process.name,
                        substrate=_entity_name(substrate) or "unknown",
                        bond_type=bond_type,
                        reason="missing_catalyst_entity",
                        message=(
                            "Surface catalysis assembly requires either an "
                            "explicit enzyme entity or a fungus with a matching capability."
                        ),
                    )
                )
    return tuple(issues)


def _enzyme_compatible(enzyme: Any, substrate: Any, *, bond_type: str | None) -> bool:
    if hasattr(enzyme, "compatible_with_substrate"):
        return bool(enzyme.compatible_with_substrate(substrate, bond_type=bond_type))
    return False


def _fungus_compatible(
    fungus: Any,
    substrate: Any,
    *,
    bond_type: str | None,
    compatible_enzymes: Sequence[Any],
) -> bool:
    substrate_name = str(getattr(substrate, "name", ""))
    if bond_type is None:
        bonds = tuple(getattr(substrate, "accessible_bonds", ()) or getattr(substrate, "bond_types", ()))
    else:
        bonds = (bond_type,)
    enzyme_classes = (
        tuple(getattr(enzyme, "enzyme_class", "") for enzyme in compatible_enzymes)
        or tuple(getattr(substrate, "required_enzyme_classes", ()))
    )
    profile = getattr(fungus, "enzyme_profile", None)
    if profile is None:
        return False
    for bond in bonds:
        for enzyme_class in enzyme_classes:
            if profile.compatible_capabilities(
                substrate_name=substrate_name,
                bond_type=str(bond),
                enzyme_class=str(enzyme_class) if enzyme_class else None,
            ):
                return True
    return False


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


def _format_compatibility_issues(issues: Sequence[CompatibilityIssue]) -> list[str]:
    return [
        (
            f"{issue.process_name} on {issue.substrate}: {issue.reason}"
            + ("" if issue.bond_type is None else f" for bond {issue.bond_type}")
        )
        for issue in issues
    ]


__all__ = [
    "AssembledModel",
    "AssemblyReport",
    "ModelAssemblyContext",
    "ModelBuilder",
    "ParameterIssue",
    "CompatibilityIssue",
    "ProcessMatch",
]
