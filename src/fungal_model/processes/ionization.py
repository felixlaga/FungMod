"""Generic pH-dependent (diprotic ionization) Michaelis-Menten process.

The process reads the pH of the static environment entity once, scales the
limiting turnover and Michaelis constant with the two-pKa ionization factors
of :mod:`fungal_model.kinetics.ionization`, and otherwise behaves like the
enzyme-explicit homogeneous Michaelis-Menten process. Nothing in it names an
enzyme, organism or substrate; the constants arrive as parameter symbols.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

import numpy as np

from fungal_model.core.kernels import KernelContext, RateKernel
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity
from fungal_model.kinetics.ionization import (
    diprotic_ionization_factor,
    ph_dependent_michaelis_constant,
    ph_dependent_turnover,
    ph_ionization_michaelis_menten_assumption,
    ph_ionization_michaelis_menten_rate,
)
from fungal_model.kinetics.ph import warn_if_ph_outside_range
from fungal_model.processes.base import (
    ParameterRequirement,
    Process,
    StateVariableSpec,
    ValidityDomain,
)
from fungal_model.processes.homogeneous import homogeneous_process_assumption

PH_IONIZATION_MICHAELIS_MENTEN_PROCESS_TYPE = "ph_ionization_michaelis_menten"
#: Environment conditions the law reads at run time; each must have one exact value.
PH_IONIZATION_MICHAELIS_MENTEN_ENVIRONMENT_CONDITIONS = ("ph",)


@dataclass(frozen=True, init=False)
class PHIonizationMichaelisMentenProcess(Process):
    """Enzyme-explicit Michaelis-Menten process with diprotic pH-dependent constants."""

    substrate_state: str
    product_state: str | None
    enzyme_state: str
    substrate_units: str
    enzyme_units: str
    rate_units: str
    turnover_symbol: str
    michaelis_constant_symbol: str
    free_enzyme_lower_pk_symbol: str
    free_enzyme_upper_pk_symbol: str
    complex_lower_pk_symbol: str
    complex_upper_pk_symbol: str
    minimum_ph_symbol: str | None
    maximum_ph_symbol: str | None
    product_coefficients: dict[str, float]

    def __init__(
        self,
        *,
        name: str,
        substrate_state: str,
        enzyme_state: str,
        substrate_units: str,
        enzyme_units: str,
        rate_units: str,
        turnover_symbol: str,
        michaelis_constant_symbol: str,
        free_enzyme_lower_pk_symbol: str,
        free_enzyme_upper_pk_symbol: str,
        complex_lower_pk_symbol: str,
        complex_upper_pk_symbol: str,
        product_state: str | None = None,
        product_coefficients: Mapping[str, float] | None = None,
        minimum_ph_symbol: str | None = None,
        maximum_ph_symbol: str | None = None,
        source: str = "Generic pH-dependent Michaelis-Menten process.",
        notes: str = "",
    ) -> None:
        if substrate_state == enzyme_state:
            raise ValueError("substrate_state and enzyme_state must be distinct.")
        if (minimum_ph_symbol is None) != (maximum_ph_symbol is None):
            raise ValueError("minimum_ph_symbol and maximum_ph_symbol must be given together.")
        coefficients = _product_coefficients(product_state=product_state, product_coefficients=product_coefficients)
        if substrate_state in coefficients or enzyme_state in coefficients:
            raise ValueError("Product states must be distinct from the substrate and enzyme states.")
        turnover_units = f"{rate_units} / ({enzyme_units})"
        requirements = [
            ParameterRequirement(symbol=turnover_symbol, units=turnover_units, name="limiting turnover k0"),
            ParameterRequirement(
                symbol=michaelis_constant_symbol, units=substrate_units, name="limiting Michaelis constant Km0"
            ),
            ParameterRequirement(symbol=free_enzyme_lower_pk_symbol, units="dimensionless", name="free-enzyme lower pKa"),
            ParameterRequirement(symbol=free_enzyme_upper_pk_symbol, units="dimensionless", name="free-enzyme upper pKa"),
            ParameterRequirement(symbol=complex_lower_pk_symbol, units="dimensionless", name="complex lower pKa"),
            ParameterRequirement(symbol=complex_upper_pk_symbol, units="dimensionless", name="complex upper pKa"),
        ]
        if minimum_ph_symbol is not None and maximum_ph_symbol is not None:
            requirements.append(
                ParameterRequirement(symbol=minimum_ph_symbol, units="dimensionless", name="minimum measured pH")
            )
            requirements.append(
                ParameterRequirement(symbol=maximum_ph_symbol, units="dimensionless", name="maximum measured pH")
            )
        changed = [
            StateVariableSpec(substrate_state, substrate_units, role="reactant"),
            *(StateVariableSpec(state_name, substrate_units, role="product") for state_name in coefficients),
            StateVariableSpec(enzyme_state, enzyme_units, role="enzyme"),
        ]
        Process.__init__(
            self,
            name=name,
            process_type=PH_IONIZATION_MICHAELIS_MENTEN_PROCESS_TYPE,
            required_state_variables=(
                StateVariableSpec(substrate_state, substrate_units, role="substrate"),
                StateVariableSpec(enzyme_state, enzyme_units, role="enzyme"),
            ),
            changed_state_variables=tuple(changed),
            required_parameters=tuple(requirements),
            assumptions=(homogeneous_process_assumption(), ph_ionization_michaelis_menten_assumption()),
            validity=ValidityDomain(
                description="Dissolved, well-mixed Michaelis-Menten process with diprotic pH-dependent constants.",
                labels=("homogeneous", "dissolved", "ph_response"),
                limitations=(
                    "Not valid for solid-substrate surface accessibility by itself.",
                    "The pH is read once from the static environment; no pH dynamics or buffering.",
                ),
            ),
            failure_modes=(
                "missing environment pH",
                "zero or negative Km0",
                "negative k0",
                "pKa pairs not ordered",
                "negative substrate",
                "negative enzyme",
            ),
            source=source,
            notes=notes,
        )
        object.__setattr__(self, "substrate_state", substrate_state)
        object.__setattr__(self, "product_state", product_state)
        object.__setattr__(self, "enzyme_state", enzyme_state)
        object.__setattr__(self, "substrate_units", substrate_units)
        object.__setattr__(self, "enzyme_units", enzyme_units)
        object.__setattr__(self, "rate_units", rate_units)
        object.__setattr__(self, "turnover_symbol", turnover_symbol)
        object.__setattr__(self, "michaelis_constant_symbol", michaelis_constant_symbol)
        object.__setattr__(self, "free_enzyme_lower_pk_symbol", free_enzyme_lower_pk_symbol)
        object.__setattr__(self, "free_enzyme_upper_pk_symbol", free_enzyme_upper_pk_symbol)
        object.__setattr__(self, "complex_lower_pk_symbol", complex_lower_pk_symbol)
        object.__setattr__(self, "complex_upper_pk_symbol", complex_upper_pk_symbol)
        object.__setattr__(self, "minimum_ph_symbol", minimum_ph_symbol)
        object.__setattr__(self, "maximum_ph_symbol", maximum_ph_symbol)
        object.__setattr__(self, "product_coefficients", coefficients)

    @property
    def turnover_units(self) -> str:
        return f"{self.rate_units} / ({self.enzyme_units})"

    def _ph_range(self, parameters: ParameterSet) -> tuple[Quantity | None, Quantity | None]:
        if self.minimum_ph_symbol is None or self.maximum_ph_symbol is None:
            return None, None
        return (
            parameters.require_quantity(self.minimum_ph_symbol, "dimensionless"),
            parameters.require_quantity(self.maximum_ph_symbol, "dimensionless"),
        )

    def effective_constants(self, *, parameters: ParameterSet, environment: Any) -> dict[str, Any]:
        """Return the pH, ionization factors, and the constants that apply at that pH."""

        ph = _require_environment_ph(environment, process_name=self.name)
        minimum_ph, maximum_ph = self._ph_range(parameters)
        warn_if_ph_outside_range(ph=ph, minimum_ph=minimum_ph, maximum_ph=maximum_ph, source=self.source or self.name)
        free_lower = parameters.require_quantity(self.free_enzyme_lower_pk_symbol, "dimensionless")
        free_upper = parameters.require_quantity(self.free_enzyme_upper_pk_symbol, "dimensionless")
        complex_lower = parameters.require_quantity(self.complex_lower_pk_symbol, "dimensionless")
        complex_upper = parameters.require_quantity(self.complex_upper_pk_symbol, "dimensionless")
        turnover = ph_dependent_turnover(
            turnover=parameters.require_quantity(self.turnover_symbol, self.turnover_units),
            ph=ph,
            complex_lower_pk=complex_lower,
            complex_upper_pk=complex_upper,
        )
        michaelis_constant = ph_dependent_michaelis_constant(
            michaelis_constant=parameters.require_quantity(self.michaelis_constant_symbol, self.substrate_units),
            ph=ph,
            free_enzyme_lower_pk=free_lower,
            free_enzyme_upper_pk=free_upper,
            complex_lower_pk=complex_lower,
            complex_upper_pk=complex_upper,
        )
        return {
            "ph": float(ph.magnitude),
            "free_enzyme_ionization_factor": float(
                diprotic_ionization_factor(ph=ph, lower_pk=free_lower, upper_pk=free_upper).magnitude
            ),
            "complex_ionization_factor": float(
                diprotic_ionization_factor(ph=ph, lower_pk=complex_lower, upper_pk=complex_upper).magnitude
            ),
            "turnover_at_ph": turnover,
            "michaelis_constant_at_ph": michaelis_constant,
        }

    def rate(
        self,
        state: Mapping[str, Quantity],
        time: Quantity,
        parameters: ParameterSet,
        environment: Any = None,
        geometry: Any = None,
    ) -> Quantity:
        del time, geometry
        ph = _require_environment_ph(environment, process_name=self.name)
        minimum_ph, maximum_ph = self._ph_range(parameters)
        return ph_ionization_michaelis_menten_rate(
            substrate=assert_compatible(
                require_quantity(state[self.substrate_state], name=self.substrate_state),
                self.substrate_units,
                name=self.substrate_state,
            ),
            enzyme=assert_compatible(state[self.enzyme_state], self.enzyme_units, name=self.enzyme_state),
            turnover=parameters.require_quantity(self.turnover_symbol, self.turnover_units),
            michaelis_constant=parameters.require_quantity(self.michaelis_constant_symbol, self.substrate_units),
            ph=ph,
            free_enzyme_lower_pk=parameters.require_quantity(self.free_enzyme_lower_pk_symbol, "dimensionless"),
            free_enzyme_upper_pk=parameters.require_quantity(self.free_enzyme_upper_pk_symbol, "dimensionless"),
            complex_lower_pk=parameters.require_quantity(self.complex_lower_pk_symbol, "dimensionless"),
            complex_upper_pk=parameters.require_quantity(self.complex_upper_pk_symbol, "dimensionless"),
            rate_units=self.rate_units,
            minimum_ph=minimum_ph,
            maximum_ph=maximum_ph,
            source=self.source or self.name,
        )

    def compile_rate(self, context: KernelContext) -> RateKernel | None:
        """Fold the pH-dependent constants once; the environment is static during a run."""

        constants = self.effective_constants(parameters=context.parameters, environment=context.environment)
        substrate_index, to_substrate = context.state_slot(self.substrate_state, self.substrate_units)
        enzyme_index, to_enzyme = context.state_slot(self.enzyme_state, self.enzyme_units)
        kcat = float(
            assert_compatible(constants["turnover_at_ph"], self.turnover_units, name=self.turnover_symbol).magnitude
        )
        km = float(
            assert_compatible(
                constants["michaelis_constant_at_ph"], self.substrate_units, name=self.michaelis_constant_symbol
            ).magnitude
        )
        if km <= 0:
            raise ValueError("Km(pH) must be positive for Michaelis-Menten kinetics.")
        scale = float(
            assert_compatible(
                Q_(1.0, self.turnover_units) * Q_(1.0, self.enzyme_units),
                self.rate_units,
                name=f"{self.name} rate",
            ).magnitude
        )

        def kernel(time: float, state: np.ndarray) -> float:
            del time
            substrate = state[substrate_index] * to_substrate
            enzyme = state[enzyme_index] * to_enzyme
            if enzyme < 0:
                raise ValueError("enzyme must be non-negative for Michaelis-Menten kinetics.")
            if substrate < 0:
                raise ValueError("substrate must be non-negative for Michaelis-Menten kinetics.")
            return ((kcat * enzyme) * (substrate / (km + substrate))) * scale

        return kernel

    def contributions(self, rate: Quantity) -> Mapping[str, Quantity]:
        value = assert_compatible(rate, self.rate_units, name=f"{self.name} rate")
        contributions: dict[str, Quantity] = {self.substrate_state: cast(Quantity, -value)}
        for state_name, coefficient in self.product_coefficients.items():
            contributions[state_name] = coefficient * value
        return contributions

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "substrate_state": self.substrate_state,
                "product_state": self.product_state,
                "enzyme_state": self.enzyme_state,
                "product_coefficients": dict(self.product_coefficients),
                "rate_units": self.rate_units,
                "turnover_symbol": self.turnover_symbol,
                "michaelis_constant_symbol": self.michaelis_constant_symbol,
                "free_enzyme_lower_pk_symbol": self.free_enzyme_lower_pk_symbol,
                "free_enzyme_upper_pk_symbol": self.free_enzyme_upper_pk_symbol,
                "complex_lower_pk_symbol": self.complex_lower_pk_symbol,
                "complex_upper_pk_symbol": self.complex_upper_pk_symbol,
                "minimum_ph_symbol": self.minimum_ph_symbol,
                "maximum_ph_symbol": self.maximum_ph_symbol,
                "environment_conditions_read": list(PH_IONIZATION_MICHAELIS_MENTEN_ENVIRONMENT_CONDITIONS),
            }
        )
        return data


def _require_environment_ph(environment: Any, *, process_name: str) -> Quantity:
    if environment is None:
        raise ValueError(f"Process {process_name!r} requires an environment entity with pH.")
    require_ph = getattr(environment, "require_ph", None)
    if require_ph is None:
        raise ValueError(f"Process {process_name!r} requires an environment entity exposing require_ph().")
    return require_ph()


def _product_coefficients(
    *,
    product_state: str | None,
    product_coefficients: Mapping[str, float] | None,
) -> dict[str, float]:
    if product_coefficients is None:
        return {} if product_state is None else {product_state: 1.0}
    coefficients = {str(state): float(coefficient) for state, coefficient in product_coefficients.items()}
    if product_state is not None and product_state not in coefficients:
        coefficients[product_state] = 1.0
    return coefficients


__all__ = [
    "PH_IONIZATION_MICHAELIS_MENTEN_PROCESS_TYPE",
    "PHIonizationMichaelisMentenProcess",
]
