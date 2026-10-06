"""The field-process contract of the spatial mycelium core.

A :class:`FieldProcess` is the spatial counterpart of
:class:`fungal_model.processes.base.Process`: it names the fields it reads and
changes, the parameters it needs, its assumptions, validity and failure modes,
and it compiles once into numpy kernels that act on whole field arrays. No
kernel performs a unit conversion at run time; every factor is resolved in
:meth:`FieldProcess.compile_tendency` from a :class:`FieldKernelContext`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fungal_model.core.assumptions import Assumption
from fungal_model.core.errors import InvalidMechanismError
from fungal_model.mycelium.fields import FieldKernelContext, FieldSpec, RateFieldKernel, TendencyKernel
from fungal_model.processes.base import ParameterRequirement, ValidityDomain

KERNEL_VECTORISED = "vectorised_numpy"


@dataclass(frozen=True)
class FieldProcess:
    """A mechanism acting on spatial fields, compiled to vectorised numpy kernels."""

    name: str
    process_type: str
    required_fields: tuple[FieldSpec, ...] = ()
    changed_fields: tuple[FieldSpec, ...] = ()
    required_parameters: tuple[ParameterRequirement, ...] = ()
    assumptions: tuple[Assumption, ...] = ()
    validity: ValidityDomain = field(default_factory=ValidityDomain)
    failure_modes: tuple[str, ...] = ()
    source: str | None = None
    notes: str = ""
    rate_units: str = "dimensionless"

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise InvalidMechanismError("FieldProcess.name must be provided.")
        if not str(self.process_type).strip():
            raise InvalidMechanismError(f"FieldProcess({self.name}).process_type must be provided.")
        units_by_name: dict[str, str] = {}
        for spec in self.required_fields + self.changed_fields:
            previous = units_by_name.get(spec.name)
            if previous is not None and previous != spec.units:
                raise InvalidMechanismError(f"Field {spec.name} has conflicting units: {previous} and {spec.units}.")
            units_by_name[spec.name] = spec.units
        symbols = [requirement.symbol for requirement in self.required_parameters]
        if len(symbols) != len(set(symbols)):
            raise InvalidMechanismError(f"FieldProcess({self.name}) declares a parameter requirement twice.")

    @property
    def fields(self) -> tuple[FieldSpec, ...]:
        seen: set[str] = set()
        result: list[FieldSpec] = []
        for spec in self.required_fields + self.changed_fields:
            if spec.name not in seen:
                seen.add(spec.name)
                result.append(spec)
        return tuple(result)

    @property
    def kernel_kind(self) -> str:
        return KERNEL_VECTORISED

    def compile_tendency(self, context: FieldKernelContext) -> TendencyKernel:
        """Kernel returning every field's tendency for the projected field array."""

        del context
        raise NotImplementedError(f"FieldProcess {self.name!r} has no tendency kernel.")

    def compile_rate(self, context: FieldKernelContext) -> RateFieldKernel | None:
        """Kernel returning the per-cell rate the process reports in ``rate_units``, or ``None``."""

        del context
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "process_type": self.process_type,
            "required_fields": [spec.to_dict() for spec in self.required_fields],
            "changed_fields": [spec.to_dict() for spec in self.changed_fields],
            "required_parameters": [requirement.to_dict() for requirement in self.required_parameters],
            "assumptions": [assumption.to_dict() for assumption in self.assumptions],
            "validity": self.validity.to_dict(),
            "failure_modes": list(self.failure_modes),
            "source": self.source,
            "notes": self.notes,
            "rate_units": self.rate_units,
            "kernel_kind": self.kernel_kind,
        }


__all__ = ["KERNEL_VECTORISED", "FieldProcess"]
