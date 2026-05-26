"""Generic process interfaces for model assembly.

The classes in this module describe mechanisms without naming a specific
substrate or fungus. Concrete process implementations can later reuse these
contracts to expose required state variables, parameters, assumptions, and
known validity limits.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from fungal_model.core.assumptions import Assumption
from fungal_model.core.errors import InvalidMechanismError
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Q_, Quantity


def _validate_identifier(value: str, *, field_name: str) -> None:
    if str(value).strip() == "":
        raise InvalidMechanismError(f"{field_name} must be provided.")


@dataclass(frozen=True)
class StateVariableSpec:
    """A state variable required or changed by a process."""

    name: str
    units: str
    description: str = ""
    role: str = "state"

    def __post_init__(self) -> None:
        _validate_identifier(self.name, field_name="StateVariableSpec.name")
        _validate_identifier(self.units, field_name=f"StateVariableSpec({self.name}).units")
        Q_(1, self.units)

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "units": self.units,
            "description": self.description,
            "role": self.role,
        }


@dataclass(frozen=True)
class ParameterRequirement:
    """A parameter that a process needs before scientific assembly can run."""

    symbol: str
    units: str
    name: str = ""
    description: str = ""
    required: bool = True

    def __post_init__(self) -> None:
        _validate_identifier(self.symbol, field_name="ParameterRequirement.symbol")
        _validate_identifier(self.units, field_name=f"ParameterRequirement({self.symbol}).units")
        Q_(1, self.units)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "units": self.units,
            "name": self.name,
            "description": self.description,
            "required": self.required,
        }


@dataclass(frozen=True)
class ValidityDomain:
    """Documented limits for using a process."""

    description: str = "Validity domain is not yet specialized for this process."
    labels: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "labels": list(self.labels),
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class Process:
    """Base description for a physical, chemical, or biological process."""

    name: str
    process_type: str
    required_state_variables: tuple[StateVariableSpec, ...] = ()
    changed_state_variables: tuple[StateVariableSpec, ...] = ()
    required_parameters: tuple[ParameterRequirement, ...] = ()
    assumptions: tuple[Assumption, ...] = ()
    validity: ValidityDomain = field(default_factory=ValidityDomain)
    failure_modes: tuple[str, ...] = ()
    source: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        _validate_identifier(self.name, field_name="Process.name")
        _validate_identifier(self.process_type, field_name=f"Process({self.name}).process_type")
        self._validate_state_specs_compatible(
            self.required_state_variables + self.changed_state_variables
        )
        self._validate_unique_specs(
            self.required_parameters,
            attribute="symbol",
            collection_name="parameter requirement",
        )

    @staticmethod
    def _validate_state_specs_compatible(specs: tuple[StateVariableSpec, ...]) -> None:
        units_by_name: dict[str, str] = {}
        for spec in specs:
            previous_units = units_by_name.get(spec.name)
            if previous_units is not None and previous_units != spec.units:
                raise InvalidMechanismError(
                    f"State variable {spec.name} has conflicting units: "
                    f"{previous_units} and {spec.units}."
                )
            units_by_name[spec.name] = spec.units

    @staticmethod
    def _validate_unique_specs(
        specs: tuple[Any, ...],
        *,
        attribute: str,
        collection_name: str,
    ) -> None:
        seen: set[str] = set()
        for spec in specs:
            key = str(getattr(spec, attribute))
            if key in seen:
                raise InvalidMechanismError(f"Duplicate {collection_name}: {key}")
            seen.add(key)

    @property
    def state_variables(self) -> tuple[StateVariableSpec, ...]:
        """Return required and changed variables without duplicates."""

        variables: list[StateVariableSpec] = []
        seen: set[str] = set()
        for spec in self.required_state_variables + self.changed_state_variables:
            if spec.name not in seen:
                variables.append(spec)
                seen.add(spec.name)
        return tuple(variables)

    def applies_to(self, context: Any) -> bool:
        """Return whether this process can satisfy the requested context.

        The Milestone 1 default is deliberately conservative: a process matches
        when its ``process_type`` or exact ``name`` is requested. Later entity
        compatibility layers can override this method without changing the
        registry contract.
        """

        requested = tuple(getattr(context, "requested_processes", ()) or ())
        if not requested:
            return True
        return self.process_type in requested or self.name in requested

    def rate(
        self,
        state: Mapping[str, Quantity],
        time: Quantity,
        parameters: ParameterSet,
        environment: Any = None,
        geometry: Any = None,
    ) -> Quantity:
        """Compute a process rate.

        Milestone 1 only defines the interface. Concrete processes must
        implement this method before being used by a solver.
        """

        del state, time, parameters, environment, geometry
        raise NotImplementedError(f"Process {self.name!r} has no rate implementation.")

    def contributions(self, rate: Quantity) -> Mapping[str, Quantity]:
        """Return state-variable contributions for a computed rate."""

        del rate
        raise NotImplementedError(f"Process {self.name!r} has no contribution implementation.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "process_type": self.process_type,
            "required_state_variables": [
                variable.to_dict() for variable in self.required_state_variables
            ],
            "changed_state_variables": [
                variable.to_dict() for variable in self.changed_state_variables
            ],
            "required_parameters": [
                requirement.to_dict() for requirement in self.required_parameters
            ],
            "assumptions": [assumption.to_dict() for assumption in self.assumptions],
            "validity": self.validity.to_dict(),
            "failure_modes": list(self.failure_modes),
            "source": self.source,
            "notes": self.notes,
        }


__all__ = [
    "ParameterRequirement",
    "Process",
    "StateVariableSpec",
    "ValidityDomain",
]
