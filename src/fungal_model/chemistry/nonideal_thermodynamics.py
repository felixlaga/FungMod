"""Explicit constant-activity-coefficient thermodynamics and reversible local flux."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any

import numpy as np

from fungal_model.chemistry.thermodynamics import DynamicActivityParticipant
from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.provenance import ProvenanceError, has_text
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity


NONIDEAL_REVERSIBLE_MATURITY = "explicit_constant_activity_coefficients_software_tested"
IUPAC_ACTIVITY_COEFFICIENT_SOURCE = "https://doi.org/10.1351/goldbook.A00116"
DETAILED_BALANCE_RATE_RATIO_SOURCE = "https://doi.org/10.1039/F29868201305"

ForwardRateLaw = Callable[[Mapping[str, Quantity], Quantity, ParameterSet], Quantity]


@dataclass(frozen=True)
class ExplicitActivityCoefficient:
    """One explicit, constant, dimensionless activity coefficient."""

    state_name: str
    coefficient: Parameter

    def validate(self) -> None:
        if not has_text(self.state_name):
            raise ValueError("Activity-coefficient state_name must be nonblank.")
        self.coefficient.validate_provenance()
        self.coefficient.validate_value()
        value = _finite_value(self.coefficient, "dimensionless")
        if value <= 0.0:
            raise ValueError("Activity coefficients must be finite and positive.")

    def value(self) -> float:
        self.validate()
        return _finite_value(self.coefficient, "dimensionless")

    def to_dict(self) -> dict[str, Any]:
        return {"state_name": self.state_name, "coefficient": self.coefficient.to_dict()}


@dataclass(frozen=True)
class NonidealReversibleEvaluation:
    """State-specific nonideal Gibbs and local-detailed-balance evaluation."""

    activities: Mapping[str, float]
    reduced_concentrations: Mapping[str, float]
    activity_coefficients: Mapping[str, float]
    log_reaction_quotient: float
    reaction_quotient: float
    equilibrium_constant: float
    standard_delta_gibbs: float
    delta_gibbs: float
    affinity: float
    temperature_kelvin: float
    reverse_to_forward_ratio: float
    direction: str
    forward_rate: float | None = None
    reverse_rate: float | None = None
    net_rate: float | None = None
    rate_units: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "activity_model": "explicit_constant_activity_coefficients",
            "activities": dict(self.activities),
            "reduced_concentrations": dict(self.reduced_concentrations),
            "activity_coefficients": dict(self.activity_coefficients),
            "log_reaction_quotient": self.log_reaction_quotient,
            "reaction_quotient": self.reaction_quotient,
            "equilibrium_constant": self.equilibrium_constant,
            "standard_delta_gibbs": self.standard_delta_gibbs,
            "delta_gibbs": self.delta_gibbs,
            "affinity": self.affinity,
            "energy_units": "joule / mole",
            "temperature_kelvin": self.temperature_kelvin,
            "reverse_to_forward_ratio": self.reverse_to_forward_ratio,
            "direction": self.direction,
            "forward_rate": self.forward_rate,
            "reverse_rate": self.reverse_rate,
            "net_rate": self.net_rate,
            "rate_units": self.rate_units,
        }


@dataclass(frozen=True)
class NonidealReversibleThermodynamics:
    """Nonideal reaction Gibbs energy and reversible rate from explicit inputs.

    Activity coefficients are constant caller-supplied values. The local
    detailed-balance relation is ``r_reverse/r_forward = exp(delta_g/RT)``;
    therefore ``r_net = r_forward - r_reverse``. The class does not infer
    activity coefficients or activation kinetics.
    """

    participants: tuple[DynamicActivityParticipant, ...]
    activity_coefficients: tuple[ExplicitActivityCoefficient, ...]
    standard_delta_gibbs: Parameter
    temperature: Parameter
    gas_constant: Parameter
    standard_concentration: Parameter
    minimum_activity: Parameter
    equilibrium_tolerance: Parameter
    source: str
    maturity: str = NONIDEAL_REVERSIBLE_MATURITY

    def validate(self) -> None:
        if not has_text(self.source):
            raise ProvenanceError("Nonideal reversible thermodynamics requires a source.")
        if self.maturity != NONIDEAL_REVERSIBLE_MATURITY:
            raise ValueError(
                f"Nonideal reversible maturity must be {NONIDEAL_REVERSIBLE_MATURITY!r}."
            )
        if not self.participants:
            raise ValueError("Nonideal reversible thermodynamics requires participants.")
        states = [participant.state_name for participant in self.participants]
        if len(set(states)) != len(states):
            raise ValueError("Thermodynamic participants must bind distinct state names.")
        if not any(item.signed_coefficient < 0.0 for item in self.participants):
            raise ValueError("Thermodynamic participants require at least one reactant.")
        if not any(item.signed_coefficient > 0.0 for item in self.participants):
            raise ValueError("Thermodynamic participants require at least one product.")
        for participant in self.participants:
            if (
                not has_text(participant.state_name)
                or not has_text(participant.species_id)
                or not np.isfinite(participant.signed_coefficient)
                or participant.signed_coefficient == 0.0
            ):
                raise ValueError("Thermodynamic participants require finite nonzero stoichiometry.")
        coefficients = {item.state_name: item for item in self.activity_coefficients}
        if len(coefficients) != len(self.activity_coefficients):
            raise ValueError("Activity coefficients must bind distinct state names.")
        if set(coefficients) != set(states):
            raise ValueError("Activity coefficients must exactly cover thermodynamic participant states.")
        for coefficient in self.activity_coefficients:
            coefficient.validate()
        for parameter in (
            self.standard_delta_gibbs,
            self.temperature,
            self.gas_constant,
            self.standard_concentration,
            self.minimum_activity,
            self.equilibrium_tolerance,
        ):
            parameter.validate_provenance()
            parameter.validate_value()
        _finite_value(self.standard_delta_gibbs, "joule / mole")
        if _finite_value(self.temperature, "kelvin") <= 0.0:
            raise ValueError("Temperature must be finite and positive.")
        if _finite_value(self.gas_constant, "joule / mole / kelvin") <= 0.0:
            raise ValueError("Gas constant must be finite and positive.")
        concentration_units = str(self.standard_concentration.units)
        assert_compatible(Q_(1.0, concentration_units), "mole / liter", name="standard concentration")
        if _finite_value(self.standard_concentration, concentration_units) <= 0.0:
            raise ValueError("Standard concentration must be finite and positive.")
        floor = _finite_value(self.minimum_activity, "dimensionless")
        if not 0.0 < floor <= 1.0:
            raise ValueError("minimum_activity must be positive and no greater than one.")
        if _finite_value(self.equilibrium_tolerance, "joule / mole") < 0.0:
            raise ValueError("equilibrium_tolerance must be finite and nonnegative.")

    @property
    def assumptions(self) -> tuple[Assumption, ...]:
        return (
            Assumption(
                name="explicit constant activity coefficients",
                description=(
                    "Each participant activity is gamma_i times its molar concentration "
                    "relative to an explicit standard concentration and activity floor."
                ),
                justification="Allows caller-supplied nonideal activities without inferring an electrolyte model.",
                known_limitations=(
                    "Activity coefficients are constant; ionic strength, composition, "
                    "temperature, pressure, electrostatics, and phase behavior are not modelled."
                ),
                source=IUPAC_ACTIVITY_COEFFICIENT_SOURCE,
            ),
            Assumption(
                name="local detailed balance reversible flux",
                description=(
                    "Reverse-to-forward flux ratio is exp(delta_g/RT), so the signed net "
                    "rate reverses direction when delta_g changes sign."
                ),
                justification="Enforces equilibrium and thermodynamic direction for an explicit one-way rate scale.",
                known_limitations=(
                    "Does not derive activation barriers or prove that a composite empirical "
                    "forward law is an elementary microscopic rate."
                ),
                source=DETAILED_BALANCE_RATE_RATIO_SOURCE,
            ),
        )

    def evaluate(self, state: Mapping[str, Quantity]) -> NonidealReversibleEvaluation:
        """Evaluate explicit nonideal activities, Q, equilibrium, and Gibbs energy."""

        self.validate()
        standard_units = str(self.standard_concentration.units)
        standard_value = _finite_value(self.standard_concentration, standard_units)
        floor = _finite_value(self.minimum_activity, "dimensionless")
        coefficient_by_state = {
            item.state_name: item.value() for item in self.activity_coefficients
        }
        reduced: dict[str, float] = {}
        activities: dict[str, float] = {}
        log_q = 0.0
        for participant in self.participants:
            if participant.state_name not in state:
                raise ValueError(f"Missing thermodynamic state {participant.state_name!r}.")
            concentration = assert_compatible(
                require_quantity(state[participant.state_name], name=participant.state_name),
                standard_units,
                name=participant.state_name,
            )
            value = float(np.asarray(concentration.magnitude))
            if not np.isfinite(value) or value < 0.0:
                raise ValueError("Thermodynamic concentrations must be finite and nonnegative scalars.")
            reduced_value = max(value / standard_value, floor)
            activity = coefficient_by_state[participant.state_name] * reduced_value
            reduced[participant.state_name] = reduced_value
            activities[participant.state_name] = activity
            log_q += participant.signed_coefficient * float(np.log(activity))
        reaction_quotient = float(np.exp(log_q))
        temperature = _finite_value(self.temperature, "kelvin")
        gas_constant = _finite_value(self.gas_constant, "joule / mole / kelvin")
        standard_delta_g = _finite_value(self.standard_delta_gibbs, "joule / mole")
        rt = gas_constant * temperature
        delta_g = standard_delta_g + rt * log_q
        equilibrium_constant = float(np.exp(-standard_delta_g / rt))
        ratio = float(np.exp(delta_g / rt))
        if not all(np.isfinite(value) and value > 0.0 for value in (reaction_quotient, equilibrium_constant, ratio)):
            raise ValueError("Thermodynamic quotient, equilibrium constant, and rate ratio must be finite and positive.")
        tolerance = _finite_value(self.equilibrium_tolerance, "joule / mole")
        if delta_g < -tolerance:
            direction = "forward"
        elif delta_g > tolerance:
            direction = "reverse"
        else:
            direction = "near_equilibrium"
        return NonidealReversibleEvaluation(
            activities=activities,
            reduced_concentrations=reduced,
            activity_coefficients=coefficient_by_state,
            log_reaction_quotient=log_q,
            reaction_quotient=reaction_quotient,
            equilibrium_constant=equilibrium_constant,
            standard_delta_gibbs=standard_delta_g,
            delta_gibbs=delta_g,
            affinity=-delta_g,
            temperature_kelvin=temperature,
            reverse_to_forward_ratio=ratio,
            direction=direction,
        )

    def net_rate(
        self,
        forward_rate: Quantity,
        state: Mapping[str, Quantity],
    ) -> tuple[Quantity, NonidealReversibleEvaluation]:
        """Return signed net flux and complete local-detailed-balance diagnostics."""

        rate = require_quantity(forward_rate, name="forward_rate")
        values = np.asarray(rate.magnitude, dtype=float)
        if values.ndim != 0 or not np.isfinite(values).all() or float(values) < 0.0:
            raise ValueError("forward_rate must be a finite nonnegative scalar quantity.")
        evaluation = self.evaluate(state)
        reverse = rate * evaluation.reverse_to_forward_ratio
        net = rate - reverse
        return net, replace(
            evaluation,
            forward_rate=float(rate.magnitude),
            reverse_rate=float(reverse.magnitude),
            net_rate=float(net.magnitude),
            rate_units=str(rate.units),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "maturity": self.maturity,
            "participants": [participant.to_dict() for participant in self.participants],
            "activity_coefficients": [item.to_dict() for item in self.activity_coefficients],
            "standard_delta_gibbs": self.standard_delta_gibbs.to_dict(),
            "temperature": self.temperature.to_dict(),
            "gas_constant": self.gas_constant.to_dict(),
            "standard_concentration": self.standard_concentration.to_dict(),
            "minimum_activity": self.minimum_activity.to_dict(),
            "equilibrium_tolerance": self.equilibrium_tolerance.to_dict(),
            "source": self.source,
            "limitations": (
                "Constant explicit activity coefficients and one reaction only; no inferred "
                "electrolyte model, activation barrier, coupled-network optimization, or validation."
            ),
        }


@dataclass(frozen=True)
class ReversibleThermodynamicRateLaw:
    """Wrap a nonnegative one-way rate law with signed reversible thermodynamics."""

    forward_rate_law: ForwardRateLaw
    thermodynamics: NonidealReversibleThermodynamics

    @property
    def assumptions(self) -> tuple[Assumption, ...]:
        return self.thermodynamics.assumptions

    def __call__(
        self,
        state: Mapping[str, Quantity],
        time: Quantity,
        parameters: ParameterSet,
    ) -> Quantity:
        forward = self.forward_rate_law(state, time, parameters)
        net, _ = self.thermodynamics.net_rate(forward, state)
        return net


def _finite_value(parameter: Parameter, units: str) -> float:
    quantity = parameter.quantity
    if quantity is None:
        raise ValueError(f"Parameter {parameter.symbol!r} requires a value.")
    value = float(assert_compatible(quantity, units, name=parameter.symbol).magnitude)
    if not np.isfinite(value):
        raise ValueError(f"Parameter {parameter.symbol!r} must be finite.")
    return value


__all__ = [
    "DETAILED_BALANCE_RATE_RATIO_SOURCE",
    "ExplicitActivityCoefficient",
    "ForwardRateLaw",
    "IUPAC_ACTIVITY_COEFFICIENT_SOURCE",
    "NONIDEAL_REVERSIBLE_MATURITY",
    "NonidealReversibleEvaluation",
    "NonidealReversibleThermodynamics",
    "ReversibleThermodynamicRateLaw",
]
