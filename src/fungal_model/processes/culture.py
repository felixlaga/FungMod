"""Generic resource-limited culture physiology as registry-bindable processes.

These processes express the well-mixed Pirt/Monod closure that the opt-in
physiology classes (`fungal_model.fungi.respiration.ResourceLimitedCulture`,
`fungal_model.fungi.degradation.DegradingCulture`) own, so that the same
closure runs through the compiled process core with the same kernels as every
other shipped process. They name roles, never organisms:

* ``resource_limited_growth``: the biomass-forming extent of a culture whose
  uptake capacity ``q_max S/(K_S+S) O/(K_O+O)`` first pays a maintenance demand
  ``m``; growth proceeds at ``(1-f) Y max(capacity-m, 0) N/(K_N+N) X`` with an
  optional allocation fraction ``f`` diverted to costed secretion.
* ``resource_limited_maintenance``: the maintenance extent ``min(m, capacity) X``.
* ``costed_secretion``: the secretion extent ``f max(capacity-m, 0) N/(K_N+N) y X``,
  with ``y`` the declared protein formula units per substrate formula unit of the
  secretion chemistry.
* ``dilution_exchange``: ``D (c_feed - c)`` for one pool of a chemostat.
* ``gas_transfer``: ``k_La (c_sat - c)`` for one dissolved pool.

Every extent is converted into pool changes by an explicit stoichiometry
(formula units per unit extent) supplied by the caller from a macrochemical
balance; reservoir species that are not model states are left out of the
stoichiometry and must be accounted for by the caller's ledger. An optional
``extent_state`` receives ``+1`` per unit extent so that an open-system
conservation check can integrate the extents alongside the pools. Negative
trial states are projected to zero by the compiled core before a kernel runs
(the classes' zero extension); the unit-aware ``rate`` methods refuse them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.kernels import KernelContext, RateKernel
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity
from fungal_model.processes.base import (
    ParameterRequirement,
    Process,
    StateVariableSpec,
    ValidityDomain,
)

RESOURCE_LIMITED_GROWTH_PROCESS_TYPE = "resource_limited_growth"
RESOURCE_LIMITED_MAINTENANCE_PROCESS_TYPE = "resource_limited_maintenance"
COSTED_SECRETION_PROCESS_TYPE = "costed_secretion"
DILUTION_EXCHANGE_PROCESS_TYPE = "dilution_exchange"
GAS_TRANSFER_PROCESS_TYPE = "gas_transfer"


def resource_limited_closure_assumption() -> Assumption:
    return Assumption(
        name="resource-limited Pirt/Monod closure",
        description=(
            "Uptake capacity q_max S/(K_S+S) O/(K_O+O) is spent first on a maintenance demand m; what is left "
            "forms biomass at the true yield Y, limited by N/(K_N+N), or is diverted by an allocation fraction "
            "to a costed secretion. Unused capacity is not consumed."
        ),
        justification=(
            "The Pirt maintenance partition with Monod saturation in substrate, oxidant and nitrogen is the "
            "canonical effective closure for well-mixed respiring cultures."
        ),
        known_limitations=(
            "No death, storage, intracellular regulation, morphology, pH or unmet-maintenance physiology is "
            "represented; the closure has a kink at capacity equal to demand; the stoichiometry of every extent "
            "must be supplied from an explicit macrochemical balance."
        ),
        source="Pirt (1965) maintenance energy partition; Monod saturation; no organism claim.",
    )


def exchange_assumption(kind: str) -> Assumption:
    return Assumption(
        name=f"well-mixed {kind}",
        description=(
            "A chemostat dilution D (c_feed - c) of one pool." if kind == "dilution exchange"
            else "A first-order gas transfer k_La (c_sat - c) into one dissolved pool."
        ),
        justification="Ideal well-mixed reactor boundary exchange.",
        known_limitations="No spatial gradients, holdup, foam, or transfer-coefficient dynamics are represented.",
        source="Ideal continuous stirred-tank reactor balance; no organism claim.",
    )


def _state_specs(names: Mapping[str, str], units: str, roles: Mapping[str, str]) -> tuple[StateVariableSpec, ...]:
    return tuple(StateVariableSpec(name, units, role=roles[role]) for role, name in names.items())


def _stoichiometry_specs(stoichiometry: Mapping[str, float], units: str) -> tuple[StateVariableSpec, ...]:
    return tuple(StateVariableSpec(name, units, role="product" if coefficient > 0 else "reactant") for name, coefficient in stoichiometry.items())


def _check_stoichiometry(stoichiometry: Mapping[str, float], *, name: str) -> dict[str, float]:
    if not stoichiometry:
        raise ValueError(f"{name} needs a stoichiometry: formula units per unit extent for every pool it changes.")
    cleaned: dict[str, float] = {}
    for state, coefficient in stoichiometry.items():
        value = float(coefficient)
        if not np.isfinite(value) or value == 0.0:
            raise ValueError(f"{name}: stoichiometric coefficient of {state!r} must be finite and non-zero.")
        cleaned[str(state)] = value
    return cleaned


def _non_negative(quantity: Quantity, name: str) -> float:
    value = float(np.asarray(quantity.magnitude, dtype=float))
    if value < 0:
        raise ValueError(f"{name} must be non-negative.")
    return value


@dataclass(frozen=True)
class ClosureConstants:
    """Plain-float constants of the Pirt/Monod closure, resolved once at build time."""

    true_yield: float
    maintenance_demand: float
    uptake_capacity: float
    substrate_half_saturation: float
    nutrient_half_saturation: float
    oxidant_half_saturation: float

    def capacity(self, substrate: float, oxidant: float) -> float:
        return (
            self.uptake_capacity
            * substrate / (self.substrate_half_saturation + substrate)
            * oxidant / (self.oxidant_half_saturation + oxidant)
        )

    def potential_growth(self, substrate: float, nutrient: float, oxidant: float) -> float:
        """``Y max(capacity - m, 0) N/(K_N+N)``: the specific growth rate before any allocation."""

        return (
            self.true_yield
            * max(self.capacity(substrate, oxidant) - self.maintenance_demand, 0.0)
            * nutrient / (self.nutrient_half_saturation + nutrient)
        )

    def maintenance(self, substrate: float, oxidant: float) -> float:
        return min(self.maintenance_demand, self.capacity(substrate, oxidant))


@dataclass(frozen=True, init=False)
class _ClosureProcess(Process):
    """Shared fields and validation of the three closure processes."""

    substrate_state: str
    biomass_state: str
    nutrient_state: str
    oxidant_state: str
    concentration_units: str
    rate_units: str
    time_units: str
    true_yield_symbol: str
    maintenance_demand_symbol: str
    uptake_capacity_symbol: str
    substrate_half_saturation_symbol: str
    nutrient_half_saturation_symbol: str
    oxidant_half_saturation_symbol: str
    stoichiometry: Mapping[str, float]
    extent_state: str | None

    def _init_closure(
        self,
        *,
        name: str,
        process_type: str,
        substrate_state: str,
        biomass_state: str,
        nutrient_state: str,
        oxidant_state: str,
        concentration_units: str,
        time_units: str,
        true_yield_symbol: str,
        maintenance_demand_symbol: str,
        uptake_capacity_symbol: str,
        substrate_half_saturation_symbol: str,
        nutrient_half_saturation_symbol: str,
        oxidant_half_saturation_symbol: str,
        stoichiometry: Mapping[str, float],
        extent_state: str | None,
        extra_requirements: tuple[ParameterRequirement, ...],
        extra_states: tuple[StateVariableSpec, ...],
        description: str,
        source: str,
        notes: str,
    ) -> None:
        pools = (substrate_state, biomass_state, nutrient_state, oxidant_state)
        if len(set(pools)) != 4:
            raise ValueError(f"{name}: substrate, biomass, nutrient and oxidant must be four distinct states.")
        cleaned = _check_stoichiometry(stoichiometry, name=name)
        if extent_state is not None and (extent_state in cleaned or extent_state in pools):
            raise ValueError(f"{name}: the extent ledger state must not be a pool the process reads or changes.")
        rate_units = f"({concentration_units}) / ({time_units})"
        specific_units = f"1 / ({time_units})"
        roles = {"substrate": "substrate", "biomass": "biomass", "nutrient": "nutrient", "oxidant": "oxidant"}
        required = _state_specs(
            {"substrate": substrate_state, "biomass": biomass_state, "nutrient": nutrient_state, "oxidant": oxidant_state},
            concentration_units,
            roles,
        ) + extra_states
        changed = list(_stoichiometry_specs(cleaned, concentration_units))
        if extent_state is not None:
            changed.append(StateVariableSpec(extent_state, concentration_units, role="extent ledger"))
        requirements = (
            ParameterRequirement(symbol=true_yield_symbol, units="dimensionless", name="true yield (biomass per substrate formula unit)"),
            ParameterRequirement(symbol=maintenance_demand_symbol, units=specific_units, name="maintenance demand"),
            ParameterRequirement(symbol=uptake_capacity_symbol, units=specific_units, name="uptake capacity"),
            ParameterRequirement(symbol=substrate_half_saturation_symbol, units=concentration_units, name="substrate half-saturation"),
            ParameterRequirement(symbol=nutrient_half_saturation_symbol, units=concentration_units, name="nutrient half-saturation"),
            ParameterRequirement(symbol=oxidant_half_saturation_symbol, units=concentration_units, name="oxidant half-saturation"),
            *extra_requirements,
        )
        Process.__init__(
            self,
            name=name,
            process_type=process_type,
            required_state_variables=tuple(required),
            changed_state_variables=tuple(changed),
            required_parameters=requirements,
            assumptions=(resource_limited_closure_assumption(),),
            validity=ValidityDomain(
                description=description,
                labels=("homogeneous", "physiology", "resource-limited"),
                limitations=(
                    "No death, storage, regulation, morphology or pH; the closure has a kink at capacity equal to demand.",
                ),
            ),
            failure_modes=(
                "negative pool state",
                "non-positive half-saturation constant",
                "negative yield, demand or capacity",
            ),
            source=source,
            notes=notes,
        )
        object.__setattr__(self, "substrate_state", substrate_state)
        object.__setattr__(self, "biomass_state", biomass_state)
        object.__setattr__(self, "nutrient_state", nutrient_state)
        object.__setattr__(self, "oxidant_state", oxidant_state)
        object.__setattr__(self, "concentration_units", concentration_units)
        object.__setattr__(self, "rate_units", rate_units)
        object.__setattr__(self, "time_units", time_units)
        object.__setattr__(self, "true_yield_symbol", true_yield_symbol)
        object.__setattr__(self, "maintenance_demand_symbol", maintenance_demand_symbol)
        object.__setattr__(self, "uptake_capacity_symbol", uptake_capacity_symbol)
        object.__setattr__(self, "substrate_half_saturation_symbol", substrate_half_saturation_symbol)
        object.__setattr__(self, "nutrient_half_saturation_symbol", nutrient_half_saturation_symbol)
        object.__setattr__(self, "oxidant_half_saturation_symbol", oxidant_half_saturation_symbol)
        object.__setattr__(self, "stoichiometry", cleaned)
        object.__setattr__(self, "extent_state", extent_state)

    @property
    def specific_units(self) -> str:
        return f"1 / ({self.time_units})"

    def closure_constants(self, parameters: ParameterSet) -> ClosureConstants:
        def value(symbol: str, units: str, *, positive: bool = False, non_negative: bool = False) -> float:
            magnitude = float(np.asarray(parameters.require_quantity(symbol, units).magnitude, dtype=float))
            if positive and magnitude <= 0:
                raise ValueError(f"{symbol} must be positive.")
            if non_negative and magnitude < 0:
                raise ValueError(f"{symbol} must be non-negative.")
            return magnitude

        return ClosureConstants(
            true_yield=value(self.true_yield_symbol, "dimensionless", non_negative=True),
            maintenance_demand=value(self.maintenance_demand_symbol, self.specific_units, non_negative=True),
            uptake_capacity=value(self.uptake_capacity_symbol, self.specific_units, non_negative=True),
            substrate_half_saturation=value(self.substrate_half_saturation_symbol, self.concentration_units, positive=True),
            nutrient_half_saturation=value(self.nutrient_half_saturation_symbol, self.concentration_units, positive=True),
            oxidant_half_saturation=value(self.oxidant_half_saturation_symbol, self.concentration_units, positive=True),
        )

    def _compiled_closure(self, context: KernelContext) -> tuple[ClosureConstants, tuple[tuple[int, float], ...]]:
        constants = self.closure_constants(context.parameters)
        slots = tuple(
            context.state_slot(state, self.concentration_units)
            for state in (self.substrate_state, self.biomass_state, self.nutrient_state, self.oxidant_state)
        )
        return constants, slots

    def _pools(self, state: Mapping[str, Quantity]) -> tuple[float, float, float, float]:
        values = []
        for name in (self.substrate_state, self.biomass_state, self.nutrient_state, self.oxidant_state):
            quantity = assert_compatible(require_quantity(state[name], name=name), self.concentration_units, name=name)
            values.append(_non_negative(quantity, name))
        return values[0], values[1], values[2], values[3]

    def contributions(self, rate: Quantity) -> Mapping[str, Quantity]:
        value = assert_compatible(rate, self.rate_units, name=f"{self.name} rate")
        result: dict[str, Quantity] = {state: cast(Quantity, value * coefficient) for state, coefficient in self.stoichiometry.items()}
        if self.extent_state is not None:
            result[self.extent_state] = value
        return result

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "pools": {
                    "substrate": self.substrate_state,
                    "biomass": self.biomass_state,
                    "nutrient": self.nutrient_state,
                    "oxidant": self.oxidant_state,
                },
                "stoichiometry": dict(self.stoichiometry),
                "extent_state": self.extent_state,
                "rate_units": self.rate_units,
            }
        )
        return data


@dataclass(frozen=True, init=False)
class ResourceLimitedGrowthProcess(_ClosureProcess):
    """Biomass-forming extent ``(1-f) Y max(capacity-m, 0) N/(K_N+N) X`` of the Pirt/Monod closure."""

    allocation_fraction_symbol: str | None

    def __init__(
        self,
        *,
        name: str,
        substrate_state: str,
        biomass_state: str,
        nutrient_state: str,
        oxidant_state: str,
        concentration_units: str,
        time_units: str,
        true_yield_symbol: str,
        maintenance_demand_symbol: str,
        uptake_capacity_symbol: str,
        substrate_half_saturation_symbol: str,
        nutrient_half_saturation_symbol: str,
        oxidant_half_saturation_symbol: str,
        stoichiometry: Mapping[str, float],
        extent_state: str | None = None,
        allocation_fraction_symbol: str | None = None,
        source: str = "Generic resource-limited growth process.",
        notes: str = "",
    ) -> None:
        extra = ()
        if allocation_fraction_symbol is not None:
            extra = (ParameterRequirement(symbol=allocation_fraction_symbol, units="dimensionless", name="allocation fraction diverted to secretion"),)
        self._init_closure(
            name=name,
            process_type=RESOURCE_LIMITED_GROWTH_PROCESS_TYPE,
            substrate_state=substrate_state,
            biomass_state=biomass_state,
            nutrient_state=nutrient_state,
            oxidant_state=oxidant_state,
            concentration_units=concentration_units,
            time_units=time_units,
            true_yield_symbol=true_yield_symbol,
            maintenance_demand_symbol=maintenance_demand_symbol,
            uptake_capacity_symbol=uptake_capacity_symbol,
            substrate_half_saturation_symbol=substrate_half_saturation_symbol,
            nutrient_half_saturation_symbol=nutrient_half_saturation_symbol,
            oxidant_half_saturation_symbol=oxidant_half_saturation_symbol,
            stoichiometry=stoichiometry,
            extent_state=extent_state,
            extra_requirements=extra,
            extra_states=(),
            description="Well-mixed resource-limited growth after maintenance, optionally sharing its budget with secretion.",
            source=source,
            notes=notes,
        )
        object.__setattr__(self, "allocation_fraction_symbol", allocation_fraction_symbol)

    def _fraction(self, parameters: ParameterSet) -> float:
        if self.allocation_fraction_symbol is None:
            return 0.0
        value = float(np.asarray(parameters.require_quantity(self.allocation_fraction_symbol, "dimensionless").magnitude, dtype=float))
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{self.allocation_fraction_symbol} must lie in [0, 1].")
        return value

    def rate(self, state: Mapping[str, Quantity], time: Quantity, parameters: ParameterSet, environment: object = None, geometry: object = None) -> Quantity:
        del time, environment, geometry
        substrate, biomass, nutrient, oxidant = self._pools(state)
        constants = self.closure_constants(parameters)
        fraction = self._fraction(parameters)
        return Q_((1.0 - fraction) * constants.potential_growth(substrate, nutrient, oxidant) * biomass, self.rate_units)

    def compile_rate(self, context: KernelContext) -> RateKernel | None:
        constants, slots = self._compiled_closure(context)
        fraction = self._fraction(context.parameters)
        (s_index, s_scale), (x_index, x_scale), (n_index, n_scale), (o_index, o_scale) = slots
        share = 1.0 - fraction

        def kernel(time: float, state: np.ndarray) -> float:
            del time
            return share * constants.potential_growth(state[s_index] * s_scale, state[n_index] * n_scale, state[o_index] * o_scale) * (state[x_index] * x_scale)

        return kernel

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["allocation_fraction_symbol"] = self.allocation_fraction_symbol
        return data


@dataclass(frozen=True, init=False)
class ResourceLimitedMaintenanceProcess(_ClosureProcess):
    """Maintenance extent ``min(m, capacity) X`` of the Pirt/Monod closure."""

    def __init__(
        self,
        *,
        name: str,
        substrate_state: str,
        biomass_state: str,
        nutrient_state: str,
        oxidant_state: str,
        concentration_units: str,
        time_units: str,
        true_yield_symbol: str,
        maintenance_demand_symbol: str,
        uptake_capacity_symbol: str,
        substrate_half_saturation_symbol: str,
        nutrient_half_saturation_symbol: str,
        oxidant_half_saturation_symbol: str,
        stoichiometry: Mapping[str, float],
        extent_state: str | None = None,
        source: str = "Generic resource-limited maintenance process.",
        notes: str = "",
    ) -> None:
        self._init_closure(
            name=name,
            process_type=RESOURCE_LIMITED_MAINTENANCE_PROCESS_TYPE,
            substrate_state=substrate_state,
            biomass_state=biomass_state,
            nutrient_state=nutrient_state,
            oxidant_state=oxidant_state,
            concentration_units=concentration_units,
            time_units=time_units,
            true_yield_symbol=true_yield_symbol,
            maintenance_demand_symbol=maintenance_demand_symbol,
            uptake_capacity_symbol=uptake_capacity_symbol,
            substrate_half_saturation_symbol=substrate_half_saturation_symbol,
            nutrient_half_saturation_symbol=nutrient_half_saturation_symbol,
            oxidant_half_saturation_symbol=oxidant_half_saturation_symbol,
            stoichiometry=stoichiometry,
            extent_state=extent_state,
            extra_requirements=(),
            extra_states=(),
            description="Well-mixed maintenance consumption capped by the uptake capacity; unmet demand is not consumed.",
            source=source,
            notes=notes,
        )

    def rate(self, state: Mapping[str, Quantity], time: Quantity, parameters: ParameterSet, environment: object = None, geometry: object = None) -> Quantity:
        del time, environment, geometry
        substrate, biomass, _, oxidant = self._pools(state)
        constants = self.closure_constants(parameters)
        return Q_(constants.maintenance(substrate, oxidant) * biomass, self.rate_units)

    def compile_rate(self, context: KernelContext) -> RateKernel | None:
        constants, slots = self._compiled_closure(context)
        (s_index, s_scale), (x_index, x_scale), _, (o_index, o_scale) = slots

        def kernel(time: float, state: np.ndarray) -> float:
            del time
            return constants.maintenance(state[s_index] * s_scale, state[o_index] * o_scale) * (state[x_index] * x_scale)

        return kernel


@dataclass(frozen=True, init=False)
class CostedSecretionProcess(_ClosureProcess):
    """Secretion extent ``f max(capacity-m, 0) N/(K_N+N) y X`` paid from the post-maintenance budget.

    ``y`` (``secretion_yield_symbol``, dimensionless) is the number of product
    formula units formed per substrate formula unit of the secretion chemistry;
    the stoichiometry then charges substrate, nutrient and oxidant and credits
    the product per unit extent.
    """

    allocation_fraction_symbol: str
    secretion_yield_symbol: str

    def __init__(
        self,
        *,
        name: str,
        substrate_state: str,
        biomass_state: str,
        nutrient_state: str,
        oxidant_state: str,
        concentration_units: str,
        time_units: str,
        true_yield_symbol: str,
        maintenance_demand_symbol: str,
        uptake_capacity_symbol: str,
        substrate_half_saturation_symbol: str,
        nutrient_half_saturation_symbol: str,
        oxidant_half_saturation_symbol: str,
        allocation_fraction_symbol: str,
        secretion_yield_symbol: str,
        stoichiometry: Mapping[str, float],
        extent_state: str | None = None,
        source: str = "Generic costed secretion process.",
        notes: str = "",
    ) -> None:
        self._init_closure(
            name=name,
            process_type=COSTED_SECRETION_PROCESS_TYPE,
            substrate_state=substrate_state,
            biomass_state=biomass_state,
            nutrient_state=nutrient_state,
            oxidant_state=oxidant_state,
            concentration_units=concentration_units,
            time_units=time_units,
            true_yield_symbol=true_yield_symbol,
            maintenance_demand_symbol=maintenance_demand_symbol,
            uptake_capacity_symbol=uptake_capacity_symbol,
            substrate_half_saturation_symbol=substrate_half_saturation_symbol,
            nutrient_half_saturation_symbol=nutrient_half_saturation_symbol,
            oxidant_half_saturation_symbol=oxidant_half_saturation_symbol,
            stoichiometry=stoichiometry,
            extent_state=extent_state,
            extra_requirements=(
                ParameterRequirement(symbol=allocation_fraction_symbol, units="dimensionless", name="allocation fraction diverted to secretion"),
                ParameterRequirement(symbol=secretion_yield_symbol, units="dimensionless", name="product formula units per substrate formula unit"),
            ),
            extra_states=(),
            description="Well-mixed costed secretion sharing the post-maintenance substrate budget with growth.",
            source=source,
            notes=notes,
        )
        object.__setattr__(self, "allocation_fraction_symbol", allocation_fraction_symbol)
        object.__setattr__(self, "secretion_yield_symbol", secretion_yield_symbol)

    def _allocation(self, parameters: ParameterSet) -> tuple[float, float]:
        fraction = float(np.asarray(parameters.require_quantity(self.allocation_fraction_symbol, "dimensionless").magnitude, dtype=float))
        if not 0.0 <= fraction <= 1.0:
            raise ValueError(f"{self.allocation_fraction_symbol} must lie in [0, 1].")
        secretion_yield = float(np.asarray(parameters.require_quantity(self.secretion_yield_symbol, "dimensionless").magnitude, dtype=float))
        if secretion_yield <= 0:
            raise ValueError(f"{self.secretion_yield_symbol} must be positive.")
        return fraction, secretion_yield

    def rate(self, state: Mapping[str, Quantity], time: Quantity, parameters: ParameterSet, environment: object = None, geometry: object = None) -> Quantity:
        del time, environment, geometry
        substrate, biomass, nutrient, oxidant = self._pools(state)
        constants = self.closure_constants(parameters)
        fraction, secretion_yield = self._allocation(parameters)
        budget = max(constants.capacity(substrate, oxidant) - constants.maintenance_demand, 0.0)
        limitation = nutrient / (constants.nutrient_half_saturation + nutrient)
        return Q_(fraction * budget * limitation * secretion_yield * biomass, self.rate_units)

    def compile_rate(self, context: KernelContext) -> RateKernel | None:
        constants, slots = self._compiled_closure(context)
        fraction, secretion_yield = self._allocation(context.parameters)
        (s_index, s_scale), (x_index, x_scale), (n_index, n_scale), (o_index, o_scale) = slots
        scale = fraction * secretion_yield

        def kernel(time: float, state: np.ndarray) -> float:
            del time
            substrate, nutrient, oxidant = state[s_index] * s_scale, state[n_index] * n_scale, state[o_index] * o_scale
            budget = max(constants.capacity(substrate, oxidant) - constants.maintenance_demand, 0.0)
            return scale * budget * nutrient / (constants.nutrient_half_saturation + nutrient) * (state[x_index] * x_scale)

        return kernel

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({"allocation_fraction_symbol": self.allocation_fraction_symbol, "secretion_yield_symbol": self.secretion_yield_symbol})
        return data


@dataclass(frozen=True, init=False)
class _ExchangeProcess(Process):
    """Shared fields of the two boundary-exchange processes (one pool each)."""

    pool_state: str
    concentration_units: str
    rate_units: str
    time_units: str
    coefficient_symbol: str
    target_symbol: str
    ledger_state: str | None

    def _init_exchange(
        self,
        *,
        name: str,
        process_type: str,
        pool_state: str,
        concentration_units: str,
        time_units: str,
        coefficient_symbol: str,
        coefficient_name: str,
        target_symbol: str,
        target_name: str,
        ledger_state: str | None,
        kind: str,
        source: str,
        notes: str,
    ) -> None:
        if ledger_state == pool_state:
            raise ValueError(f"{name}: the boundary ledger state must differ from the pool it tracks.")
        rate_units = f"({concentration_units}) / ({time_units})"
        changed = [StateVariableSpec(pool_state, concentration_units, role="pool")]
        if ledger_state is not None:
            changed.append(StateVariableSpec(ledger_state, concentration_units, role="boundary ledger"))
        Process.__init__(
            self,
            name=name,
            process_type=process_type,
            required_state_variables=(StateVariableSpec(pool_state, concentration_units, role="pool"),),
            changed_state_variables=tuple(changed),
            required_parameters=(
                ParameterRequirement(symbol=coefficient_symbol, units=f"1 / ({time_units})", name=coefficient_name),
                ParameterRequirement(symbol=target_symbol, units=concentration_units, name=target_name),
            ),
            assumptions=(exchange_assumption(kind),),
            validity=ValidityDomain(description=f"Ideal well-mixed {kind} of one pool.", labels=("homogeneous", "boundary", kind.replace(" ", "-"))),
            failure_modes=("negative exchange coefficient", "negative target concentration"),
            source=source,
            notes=notes,
        )
        object.__setattr__(self, "pool_state", pool_state)
        object.__setattr__(self, "concentration_units", concentration_units)
        object.__setattr__(self, "rate_units", rate_units)
        object.__setattr__(self, "time_units", time_units)
        object.__setattr__(self, "coefficient_symbol", coefficient_symbol)
        object.__setattr__(self, "target_symbol", target_symbol)
        object.__setattr__(self, "ledger_state", ledger_state)

    def _constants(self, parameters: ParameterSet) -> tuple[float, float]:
        coefficient = float(np.asarray(parameters.require_quantity(self.coefficient_symbol, f"1 / ({self.time_units})").magnitude, dtype=float))
        target = float(np.asarray(parameters.require_quantity(self.target_symbol, self.concentration_units).magnitude, dtype=float))
        if coefficient < 0:
            raise ValueError(f"{self.coefficient_symbol} must be non-negative.")
        if target < 0:
            raise ValueError(f"{self.target_symbol} must be non-negative.")
        return coefficient, target

    def rate(self, state: Mapping[str, Quantity], time: Quantity, parameters: ParameterSet, environment: object = None, geometry: object = None) -> Quantity:
        del time, environment, geometry
        pool = float(np.asarray(assert_compatible(require_quantity(state[self.pool_state], name=self.pool_state), self.concentration_units, name=self.pool_state).magnitude, dtype=float))
        coefficient, target = self._constants(parameters)
        return Q_(coefficient * (target - pool), self.rate_units)

    def compile_rate(self, context: KernelContext) -> RateKernel | None:
        index, scale = context.state_slot(self.pool_state, self.concentration_units)
        coefficient, target = self._constants(context.parameters)

        def kernel(time: float, state: np.ndarray) -> float:
            del time
            return coefficient * (target - state[index] * scale)

        return kernel

    def contributions(self, rate: Quantity) -> Mapping[str, Quantity]:
        value = assert_compatible(rate, self.rate_units, name=f"{self.name} rate")
        result: dict[str, Quantity] = {self.pool_state: value}
        if self.ledger_state is not None:
            result[self.ledger_state] = value
        return result

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({"pool_state": self.pool_state, "ledger_state": self.ledger_state, "rate_units": self.rate_units})
        return data


@dataclass(frozen=True, init=False)
class DilutionExchangeProcess(_ExchangeProcess):
    """Chemostat exchange ``D (c_feed - c)`` of one pool; negative when the pool exceeds its feed."""

    def __init__(
        self,
        *,
        name: str,
        pool_state: str,
        concentration_units: str,
        time_units: str,
        dilution_rate_symbol: str,
        feed_symbol: str,
        ledger_state: str | None = None,
        source: str = "Generic chemostat dilution exchange.",
        notes: str = "",
    ) -> None:
        self._init_exchange(
            name=name,
            process_type=DILUTION_EXCHANGE_PROCESS_TYPE,
            pool_state=pool_state,
            concentration_units=concentration_units,
            time_units=time_units,
            coefficient_symbol=dilution_rate_symbol,
            coefficient_name="dilution rate",
            target_symbol=feed_symbol,
            target_name="feed concentration",
            ledger_state=ledger_state,
            kind="dilution exchange",
            source=source,
            notes=notes,
        )


@dataclass(frozen=True, init=False)
class GasTransferProcess(_ExchangeProcess):
    """First-order gas transfer ``k_La (c_sat - c)`` into one dissolved pool."""

    def __init__(
        self,
        *,
        name: str,
        pool_state: str,
        concentration_units: str,
        time_units: str,
        transfer_rate_symbol: str,
        saturation_symbol: str,
        ledger_state: str | None = None,
        source: str = "Generic first-order gas transfer.",
        notes: str = "",
    ) -> None:
        self._init_exchange(
            name=name,
            process_type=GAS_TRANSFER_PROCESS_TYPE,
            pool_state=pool_state,
            concentration_units=concentration_units,
            time_units=time_units,
            coefficient_symbol=transfer_rate_symbol,
            coefficient_name="volumetric transfer coefficient",
            target_symbol=saturation_symbol,
            target_name="saturation concentration",
            ledger_state=ledger_state,
            kind="gas transfer",
            source=source,
            notes=notes,
        )


__all__ = [
    "COSTED_SECRETION_PROCESS_TYPE",
    "DILUTION_EXCHANGE_PROCESS_TYPE",
    "GAS_TRANSFER_PROCESS_TYPE",
    "RESOURCE_LIMITED_GROWTH_PROCESS_TYPE",
    "RESOURCE_LIMITED_MAINTENANCE_PROCESS_TYPE",
    "ClosureConstants",
    "CostedSecretionProcess",
    "DilutionExchangeProcess",
    "GasTransferProcess",
    "ResourceLimitedGrowthProcess",
    "ResourceLimitedMaintenanceProcess",
    "exchange_assumption",
    "resource_limited_closure_assumption",
]
