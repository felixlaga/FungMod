"""Generic first-order thermal inactivation of an active pool.

The process loses an active pool (an enzyme activity or concentration) at a
first-order rate whose constant follows the Arrhenius reference form in the
temperature of the static environment entity. The lost amount may be routed
to an explicit inactive pool so that a closure ledger can balance it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

import numpy as np

from fungal_model.core.kernels import KernelContext, RateKernel, conversion_factor
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Quantity, assert_compatible
from fungal_model.kinetics.inactivation import (
    arrhenius_inactivation_rate_constant,
    thermal_inactivation_assumption,
    thermal_inactivation_rate,
)
from fungal_model.processes.base import (
    ParameterRequirement,
    Process,
    StateVariableSpec,
    ValidityDomain,
)

THERMAL_INACTIVATION_PROCESS_TYPE = "thermal_inactivation"
#: Environment conditions the law reads at run time; each must have one exact value.
THERMAL_INACTIVATION_ENVIRONMENT_CONDITIONS = ("temperature",)


@dataclass(frozen=True, init=False)
class ThermalInactivationProcess(Process):
    """First-order loss of an active pool with an Arrhenius-scaled rate constant."""

    active_state: str
    inactive_state: str | None
    state_units: str
    rate_units: str
    reference_rate_constant_symbol: str
    inactivation_energy_symbol: str
    reference_temperature_symbol: str
    minimum_temperature_symbol: str | None
    maximum_temperature_symbol: str | None

    def __init__(
        self,
        *,
        name: str,
        active_state: str,
        state_units: str,
        reference_rate_constant_symbol: str,
        inactivation_energy_symbol: str,
        reference_temperature_symbol: str,
        inactive_state: str | None = None,
        rate_units: str | None = None,
        minimum_temperature_symbol: str | None = None,
        maximum_temperature_symbol: str | None = None,
        source: str = "Generic first-order thermal inactivation process.",
        notes: str = "",
    ) -> None:
        if inactive_state is not None and inactive_state == active_state:
            raise ValueError("active_state and inactive_state must be distinct.")
        if (minimum_temperature_symbol is None) != (maximum_temperature_symbol is None):
            raise ValueError(
                "minimum_temperature_symbol and maximum_temperature_symbol must be given together."
            )
        units = rate_units or f"{state_units} / second"
        changed = [StateVariableSpec(active_state, state_units, role="reactant")]
        if inactive_state is not None:
            changed.append(StateVariableSpec(inactive_state, state_units, role="product"))
        requirements = [
            ParameterRequirement(
                symbol=reference_rate_constant_symbol,
                units="1 / second",
                name="inactivation rate constant at the reference temperature",
            ),
            ParameterRequirement(
                symbol=inactivation_energy_symbol,
                units="joule / mole",
                name="apparent activation energy of inactivation",
            ),
            ParameterRequirement(
                symbol=reference_temperature_symbol,
                units="kelvin",
                name="reference temperature of the inactivation constant",
            ),
        ]
        if minimum_temperature_symbol is not None and maximum_temperature_symbol is not None:
            requirements.append(
                ParameterRequirement(symbol=minimum_temperature_symbol, units="kelvin", name="minimum measured temperature")
            )
            requirements.append(
                ParameterRequirement(symbol=maximum_temperature_symbol, units="kelvin", name="maximum measured temperature")
            )
        Process.__init__(
            self,
            name=name,
            process_type=THERMAL_INACTIVATION_PROCESS_TYPE,
            required_state_variables=(StateVariableSpec(active_state, state_units, role="reactant"),),
            changed_state_variables=tuple(changed),
            required_parameters=tuple(requirements),
            assumptions=(thermal_inactivation_assumption(),),
            validity=ValidityDomain(
                description="Well-mixed first-order inactivation of one active pool at a static temperature.",
                labels=("homogeneous", "thermal_inactivation", "temperature_response"),
                limitations=(
                    "Irreversible single-exponential loss only; no unfolding equilibrium, proteolysis, "
                    "or stabilizer effects.",
                    "The temperature is read once from the static environment; no temperature dynamics.",
                ),
            ),
            failure_modes=(
                "missing environment temperature",
                "negative active pool",
                "negative reference rate constant or inactivation energy",
            ),
            source=source,
            notes=notes,
        )
        object.__setattr__(self, "active_state", active_state)
        object.__setattr__(self, "inactive_state", inactive_state)
        object.__setattr__(self, "state_units", state_units)
        object.__setattr__(self, "rate_units", units)
        object.__setattr__(self, "reference_rate_constant_symbol", reference_rate_constant_symbol)
        object.__setattr__(self, "inactivation_energy_symbol", inactivation_energy_symbol)
        object.__setattr__(self, "reference_temperature_symbol", reference_temperature_symbol)
        object.__setattr__(self, "minimum_temperature_symbol", minimum_temperature_symbol)
        object.__setattr__(self, "maximum_temperature_symbol", maximum_temperature_symbol)

    def rate_constant(self, *, parameters: ParameterSet, environment: Any) -> Quantity:
        """Return ``k_d(T)`` for the static environment temperature."""

        temperature = _require_environment_temperature(environment, process_name=self.name)
        minimum = maximum = None
        if self.minimum_temperature_symbol is not None and self.maximum_temperature_symbol is not None:
            minimum = parameters.require_quantity(self.minimum_temperature_symbol, "kelvin")
            maximum = parameters.require_quantity(self.maximum_temperature_symbol, "kelvin")
        return arrhenius_inactivation_rate_constant(
            reference_rate_constant=parameters.require_quantity(self.reference_rate_constant_symbol, "1 / second"),
            inactivation_energy=parameters.require_quantity(self.inactivation_energy_symbol, "joule / mole"),
            temperature=temperature,
            reference_temperature=parameters.require_quantity(self.reference_temperature_symbol, "kelvin"),
            minimum_temperature=minimum,
            maximum_temperature=maximum,
            source=self.source or self.name,
        )

    def rate(
        self,
        state: Mapping[str, Quantity],
        time: Quantity,
        parameters: ParameterSet,
        environment: Any = None,
        geometry: Any = None,
    ) -> Quantity:
        del time, geometry
        active = assert_compatible(state[self.active_state], self.state_units, name=self.active_state)
        return thermal_inactivation_rate(
            active_pool=active,
            rate_constant=self.rate_constant(parameters=parameters, environment=environment),
            rate_units=self.rate_units,
        )

    def compile_rate(self, context: KernelContext) -> RateKernel | None:
        """Fold ``k_d(T)`` once; the environment is static during a run."""

        rate_constant = float(
            assert_compatible(
                self.rate_constant(parameters=context.parameters, environment=context.environment),
                "1 / second",
                name=self.reference_rate_constant_symbol,
            ).magnitude
        )
        index, to_state = context.state_slot(self.active_state, self.state_units)
        scale = conversion_factor(f"{self.state_units} / second", self.rate_units, name=f"{self.name} rate")
        active_name = self.active_state

        def kernel(time: float, state: np.ndarray) -> float:
            del time
            active = state[index] * to_state
            if active < 0:
                raise ValueError(f"{active_name} must be non-negative.")
            return (rate_constant * active) * scale

        return kernel

    def contributions(self, rate: Quantity) -> Mapping[str, Quantity]:
        value = assert_compatible(rate, self.rate_units, name=f"{self.name} rate")
        contributions: dict[str, Quantity] = {self.active_state: cast(Quantity, -value)}
        if self.inactive_state is not None:
            contributions[self.inactive_state] = value
        return contributions

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "active_state": self.active_state,
                "inactive_state": self.inactive_state,
                "state_units": self.state_units,
                "rate_units": self.rate_units,
                "reference_rate_constant_symbol": self.reference_rate_constant_symbol,
                "inactivation_energy_symbol": self.inactivation_energy_symbol,
                "reference_temperature_symbol": self.reference_temperature_symbol,
                "minimum_temperature_symbol": self.minimum_temperature_symbol,
                "maximum_temperature_symbol": self.maximum_temperature_symbol,
                "environment_conditions_read": list(THERMAL_INACTIVATION_ENVIRONMENT_CONDITIONS),
            }
        )
        return data


def _require_environment_temperature(environment: Any, *, process_name: str) -> Quantity:
    if environment is None:
        raise ValueError(f"Process {process_name!r} requires an environment entity with temperature.")
    require_temperature = getattr(environment, "require_temperature", None)
    if require_temperature is None:
        raise ValueError(
            f"Process {process_name!r} requires an environment entity exposing require_temperature()."
        )
    return cast(Quantity, require_temperature())


__all__ = [
    "THERMAL_INACTIVATION_PROCESS_TYPE",
    "ThermalInactivationProcess",
]
