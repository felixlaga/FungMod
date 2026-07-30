"""Thermodynamic metadata interfaces.

Stage 7 records approximate Gibbs free energy estimates when available. The
framework does not yet enforce full thermodynamic flux analysis.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.provenance import ProvenanceError, UnknownParameterError, has_text
from fungal_model.core.units import Q_, Quantity, assert_compatible


@dataclass(frozen=True)
class GibbsFreeEnergyEstimate:
    """Approximate Gibbs free energy estimate with provenance."""

    reaction_name: str
    delta_gibbs: Parameter
    conditions: ParameterSet = field(default_factory=ParameterSet)
    source: str | None = None
    notes: str = ""

    def validate(
        self,
        *,
        allow_unsourced_for_testing: bool = False,
        require_value: bool = False,
    ) -> None:
        if not allow_unsourced_for_testing and not has_text(self.source):
            raise ProvenanceError(f"Gibbs free energy estimate for {self.reaction_name!r} is missing a source.")
        self.delta_gibbs.validate_provenance(allow_unsourced_for_testing=allow_unsourced_for_testing)
        if require_value:
            self.delta_gibbs.validate_value()
        if self.delta_gibbs.quantity is not None:
            assert_compatible(self.delta_gibbs.quantity, "joule / mole", name=self.delta_gibbs.symbol)
        self.conditions.validate(
            allow_unsourced_for_testing=allow_unsourced_for_testing,
            require_values=False,
        )

    def value(self) -> Quantity:
        quantity = self.delta_gibbs.quantity
        if quantity is None:
            raise UnknownParameterError(f"Delta G for {self.reaction_name} is unknown.")
        return assert_compatible(quantity, "joule / mole", name=self.delta_gibbs.symbol)

    def is_exergonic(self) -> bool | None:
        if self.delta_gibbs.quantity is None:
            return None
        value = self.value()
        return bool(np.all(np.asarray(value.magnitude, dtype=float) < 0.0))

    def to_dict(self) -> dict[str, Any]:
        return {
            "reaction_name": self.reaction_name,
            "delta_gibbs": self.delta_gibbs.to_dict(),
            "conditions": self.conditions.to_dict(),
            "source": self.source,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class DynamicActivityParticipant:
    """One explicitly bound trajectory state in a reaction quotient."""

    state_name: str
    species_id: str
    signed_coefficient: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_name": self.state_name,
            "species_id": self.species_id,
            "signed_coefficient": self.signed_coefficient,
            "role": "reactant" if self.signed_coefficient < 0.0 else "product",
        }


@dataclass(frozen=True)
class DynamicThermodynamicEvaluation:
    """One state-specific activity, quotient, and Gibbs evaluation."""

    constraint_id: str
    process_id: str
    reaction_id: str
    activities: Mapping[str, float]
    log_reaction_quotient: float
    reaction_quotient: float
    standard_delta_gibbs: float
    delta_gibbs: float
    temperature_kelvin: float
    absolute_tolerance: float
    favorable: bool
    rate_blocked: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "constraint_id": self.constraint_id,
            "process_id": self.process_id,
            "reaction_id": self.reaction_id,
            "activities": dict(self.activities),
            "log_reaction_quotient": self.log_reaction_quotient,
            "reaction_quotient": self.reaction_quotient,
            "standard_delta_gibbs": self.standard_delta_gibbs,
            "standard_delta_gibbs_units": "joule / mole",
            "delta_gibbs": self.delta_gibbs,
            "delta_gibbs_units": "joule / mole",
            "temperature_K": self.temperature_kelvin,
            "absolute_tolerance": self.absolute_tolerance,
            "absolute_tolerance_units": "joule / mole",
            "favorable": self.favorable,
            "rate_blocked": self.rate_blocked,
        }


@dataclass(frozen=True)
class DynamicThermodynamicConstraint:
    """Provenance-bound dynamic Gibbs constraint for one forward process rate."""

    constraint_id: str
    process_id: str
    reaction_id: str
    electron_balance_check_id: str
    participants: tuple[DynamicActivityParticipant, ...]
    standard_energy_method: str
    temperature: Parameter
    gas_constant: Parameter
    standard_concentration: Parameter
    minimum_activity: Parameter
    absolute_tolerance: Parameter
    provenance_refs: tuple[str, ...]
    standard_delta_gibbs: Parameter | None = None
    standard_redox_potential: Parameter | None = None
    electron_transfer_number: Parameter | None = None
    faraday_constant: Parameter | None = None
    enforcement_mode: str = "block_unfavorable_forward_rate"

    def validate(self) -> None:
        for field_name, value in (
            ("constraint_id", self.constraint_id),
            ("process_id", self.process_id),
            ("reaction_id", self.reaction_id),
            ("electron_balance_check_id", self.electron_balance_check_id),
        ):
            if not has_text(value):
                raise ValueError(f"Dynamic thermodynamic {field_name} must be nonblank.")
        if self.enforcement_mode != "block_unfavorable_forward_rate":
            raise ValueError(
                "Dynamic thermodynamic enforcement_mode must be "
                "'block_unfavorable_forward_rate'."
            )
        if not self.participants:
            raise ValueError("Dynamic thermodynamic constraint requires reaction participants.")
        state_names = [participant.state_name for participant in self.participants]
        species_ids = [participant.species_id for participant in self.participants]
        if len(set(state_names)) != len(state_names):
            raise ValueError(
                "Dynamic thermodynamic reaction participants must bind distinct state names."
            )
        if len(set(species_ids)) != len(species_ids):
            raise ValueError(
                "Dynamic thermodynamic reaction participants must bind distinct species ids."
            )
        if not any(participant.signed_coefficient < 0.0 for participant in self.participants):
            raise ValueError("Dynamic thermodynamic reaction requires at least one reactant.")
        if not any(participant.signed_coefficient > 0.0 for participant in self.participants):
            raise ValueError("Dynamic thermodynamic reaction requires at least one product.")
        for participant in self.participants:
            if (
                not has_text(participant.state_name)
                or not has_text(participant.species_id)
                or not np.isfinite(participant.signed_coefficient)
                or participant.signed_coefficient == 0.0
            ):
                raise ValueError(
                    "Dynamic thermodynamic participants require nonblank state/species "
                    "ids and finite nonzero signed coefficients."
                )
        if not self.provenance_refs or any(not has_text(value) for value in self.provenance_refs):
            raise ProvenanceError(
                "Dynamic thermodynamic constraint requires nonblank provenance_refs."
            )
        parameters = [
            self.temperature,
            self.gas_constant,
            self.standard_concentration,
            self.minimum_activity,
            self.absolute_tolerance,
        ]
        if self.standard_energy_method == "standard_delta_gibbs":
            if self.standard_delta_gibbs is None:
                raise ValueError(
                    "standard_delta_gibbs method requires standard_delta_gibbs."
                )
            if any(
                item is not None
                for item in (
                    self.standard_redox_potential,
                    self.electron_transfer_number,
                    self.faraday_constant,
                )
            ):
                raise ValueError(
                    "standard_delta_gibbs method cannot also declare redox energy inputs."
                )
            parameters.append(self.standard_delta_gibbs)
        elif self.standard_energy_method == "redox_potential":
            redox_parameters = (
                self.standard_redox_potential,
                self.electron_transfer_number,
                self.faraday_constant,
            )
            if any(parameter is None for parameter in redox_parameters):
                raise ValueError(
                    "redox_potential method requires standard_redox_potential, "
                    "electron_transfer_number, and faraday_constant."
                )
            if self.standard_delta_gibbs is not None:
                raise ValueError(
                    "redox_potential method cannot also declare standard_delta_gibbs."
                )
            parameters.extend(
                parameter
                for parameter in redox_parameters
                if parameter is not None
            )
        else:
            raise ValueError(
                "Dynamic thermodynamic standard_energy.method must be "
                "'standard_delta_gibbs' or 'redox_potential'."
            )
        for parameter in parameters:
            parameter.validate_provenance()
            parameter.validate_value()
            _finite_scalar(parameter)
        _positive_value(self.temperature, "kelvin")
        _positive_value(self.gas_constant, "joule / mole / kelvin")
        standard_concentration_quantity = self.standard_concentration.quantity
        assert standard_concentration_quantity is not None
        assert_compatible(
            standard_concentration_quantity,
            "mole / liter",
            name=self.standard_concentration.symbol,
        )
        _positive_value(self.standard_concentration, str(self.standard_concentration.units))
        minimum_activity = _positive_value(self.minimum_activity, "dimensionless")
        if minimum_activity > 1.0:
            raise ValueError("minimum_activity must be positive and no greater than 1.")
        tolerance = _nonnegative_value(self.absolute_tolerance, "joule / mole")
        if not np.isfinite(tolerance):
            raise ValueError("absolute_tolerance must be finite.")
        if self.standard_energy_method == "standard_delta_gibbs":
            assert self.standard_delta_gibbs is not None
            _finite_value(self.standard_delta_gibbs, "joule / mole")
        else:
            assert self.standard_redox_potential is not None
            assert self.electron_transfer_number is not None
            assert self.faraday_constant is not None
            _finite_value(self.standard_redox_potential, "volt")
            _positive_value(self.electron_transfer_number, "dimensionless")
            _positive_value(self.faraday_constant, "coulomb / mole")

    def standard_delta_gibbs_value(self) -> float:
        """Return configured or redox-derived standard Gibbs energy in J/mol."""

        self.validate()
        if self.standard_energy_method == "standard_delta_gibbs":
            assert self.standard_delta_gibbs is not None
            return _finite_value(self.standard_delta_gibbs, "joule / mole")
        assert self.standard_redox_potential is not None
        assert self.electron_transfer_number is not None
        assert self.faraday_constant is not None
        potential = assert_compatible(
            self.standard_redox_potential.quantity,
            "volt",
            name=self.standard_redox_potential.symbol,
        )
        transfer_number = assert_compatible(
            self.electron_transfer_number.quantity,
            "dimensionless",
            name=self.electron_transfer_number.symbol,
        )
        faraday = assert_compatible(
            self.faraday_constant.quantity,
            "coulomb / mole",
            name=self.faraday_constant.symbol,
        )
        delta_g = -(transfer_number * faraday * potential)
        return float(delta_g.to("joule / mole").magnitude)

    def evaluate(
        self,
        state: Mapping[str, Quantity],
        *,
        rate_blocked: bool = False,
    ) -> DynamicThermodynamicEvaluation:
        """Evaluate activities, Q, and delta G for one solver state."""

        self.validate()
        standard_concentration = self.standard_concentration.quantity
        minimum_activity = self.minimum_activity.quantity
        temperature = self.temperature.quantity
        gas_constant = self.gas_constant.quantity
        tolerance = self.absolute_tolerance.quantity
        assert standard_concentration is not None
        assert minimum_activity is not None
        assert temperature is not None
        assert gas_constant is not None
        assert tolerance is not None
        standard_value = float(standard_concentration.magnitude)
        floor_value = float(minimum_activity.to("dimensionless").magnitude)
        activities: dict[str, float] = {}
        log_quotient = 0.0
        for participant in self.participants:
            if participant.state_name not in state:
                raise ValueError(
                    f"Dynamic thermodynamic constraint {self.constraint_id!r} "
                    f"requires missing state {participant.state_name!r}."
                )
            concentration = assert_compatible(
                state[participant.state_name],
                str(standard_concentration.units),
                name=participant.state_name,
            )
            concentration_value = float(concentration.magnitude)
            if not np.isfinite(concentration_value) or concentration_value < 0.0:
                raise ValueError(
                    f"Dynamic thermodynamic state {participant.state_name!r} "
                    "must be a finite nonnegative concentration."
                )
            activity = max(concentration_value / standard_value, floor_value)
            activities[participant.state_name] = activity
            log_quotient += participant.signed_coefficient * float(np.log(activity))
        quotient = float(np.exp(log_quotient))
        if not np.isfinite(log_quotient) or not np.isfinite(quotient) or quotient <= 0.0:
            raise ValueError(
                f"Dynamic thermodynamic constraint {self.constraint_id!r} "
                "produced a non-finite or non-positive reaction quotient."
            )
        temperature_k = float(temperature.to("kelvin").magnitude)
        gas_constant_value = float(
            gas_constant.to("joule / mole / kelvin").magnitude
        )
        standard_delta_g = self.standard_delta_gibbs_value()
        delta_g = standard_delta_g + gas_constant_value * temperature_k * log_quotient
        tolerance_value = float(tolerance.to("joule / mole").magnitude)
        return DynamicThermodynamicEvaluation(
            constraint_id=self.constraint_id,
            process_id=self.process_id,
            reaction_id=self.reaction_id,
            activities=activities,
            log_reaction_quotient=log_quotient,
            reaction_quotient=quotient,
            standard_delta_gibbs=standard_delta_g,
            delta_gibbs=delta_g,
            temperature_kelvin=temperature_k,
            absolute_tolerance=tolerance_value,
            favorable=delta_g < -tolerance_value,
            rate_blocked=rate_blocked,
        )

    def enforce(
        self,
        rate: Quantity,
        state: Mapping[str, Quantity],
    ) -> tuple[Quantity, DynamicThermodynamicEvaluation]:
        """Block an unfavorable nonnegative forward rate."""

        rate_values = np.asarray(rate.magnitude, dtype=float)
        if rate_values.ndim != 0 or not np.isfinite(rate_values).all():
            raise ValueError(
                "Dynamic thermodynamic enforcement requires a finite scalar process rate."
            )
        if float(rate_values) < 0.0:
            raise ValueError(
                "Dynamic thermodynamic enforcement supports nonnegative forward rates only."
            )
        evaluation = self.evaluate(state)
        if evaluation.favorable:
            return rate, evaluation
        blocked = self.evaluate(state, rate_blocked=True)
        return Q_(0.0, rate.units), blocked

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.constraint_id,
            "process_id": self.process_id,
            "reaction_id": self.reaction_id,
            "electron_balance_check_id": self.electron_balance_check_id,
            "enforcement_mode": self.enforcement_mode,
            "participants": [participant.to_dict() for participant in self.participants],
            "standard_energy_method": self.standard_energy_method,
            "standard_delta_gibbs": (
                None
                if self.standard_delta_gibbs is None
                else self.standard_delta_gibbs.to_dict()
            ),
            "standard_redox_potential": (
                None
                if self.standard_redox_potential is None
                else self.standard_redox_potential.to_dict()
            ),
            "electron_transfer_number": (
                None
                if self.electron_transfer_number is None
                else self.electron_transfer_number.to_dict()
            ),
            "faraday_constant": (
                None if self.faraday_constant is None else self.faraday_constant.to_dict()
            ),
            "temperature": self.temperature.to_dict(),
            "gas_constant": self.gas_constant.to_dict(),
            "standard_concentration": self.standard_concentration.to_dict(),
            "minimum_activity": self.minimum_activity.to_dict(),
            "absolute_tolerance": self.absolute_tolerance.to_dict(),
            "provenance_refs": list(self.provenance_refs),
        }


def _finite_scalar(parameter: Parameter) -> float:
    quantity = parameter.quantity
    assert quantity is not None
    value = np.asarray(quantity.magnitude, dtype=float)
    if value.ndim != 0 or not np.isfinite(value).all():
        raise ValueError(f"Parameter {parameter.symbol!r} must be a finite scalar.")
    return float(value)


def _finite_value(parameter: Parameter, units: str) -> float:
    quantity = parameter.quantity
    assert quantity is not None
    value = float(
        assert_compatible(quantity, units, name=parameter.symbol).magnitude
    )
    if not np.isfinite(value):
        raise ValueError(f"Parameter {parameter.symbol!r} must be finite.")
    return value


def _positive_value(parameter: Parameter, units: str) -> float:
    value = _finite_value(parameter, units)
    if value <= 0.0:
        raise ValueError(f"Parameter {parameter.symbol!r} must be positive.")
    return value


def _nonnegative_value(parameter: Parameter, units: str) -> float:
    value = _finite_value(parameter, units)
    if value < 0.0:
        raise ValueError(f"Parameter {parameter.symbol!r} must be nonnegative.")
    return value


__all__ = [
    "DynamicActivityParticipant",
    "DynamicThermodynamicConstraint",
    "DynamicThermodynamicEvaluation",
    "GibbsFreeEnergyEstimate",
]
