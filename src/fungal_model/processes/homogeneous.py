"""Generic homogeneous reaction processes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

import numpy as np

from fungal_model.chemistry.reactions import Reaction
from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Quantity, assert_compatible, require_quantity
from fungal_model.kinetics.michaelis_menten import (
    enzyme_explicit_michaelis_menten_rate,
    michaelis_menten_rate,
)
from fungal_model.processes.base import (
    ParameterRequirement,
    Process,
    StateVariableSpec,
    ValidityDomain,
)


def homogeneous_process_assumption() -> Assumption:
    """Return the generic well-mixed homogeneous-process assumption."""

    return Assumption(
        name="generic homogeneous well-mixed process",
        description="Reactants and products are represented as well-mixed state variables.",
        justification="Homogeneous process forms are useful for dissolved systems and software benchmarks.",
        known_limitations=(
            "Does not represent adsorption, spatial gradients, inaccessible solid "
            "substrate pools, transport limitation, or changing surface morphology."
        ),
        source="Canonical homogeneous reaction modelling assumption.",
    )


def _ensure_non_negative(quantity: Quantity, name: str) -> None:
    if np.any(np.asarray(quantity.magnitude, dtype=float) < 0):
        raise ValueError(f"{name} must be non-negative.")


def _reaction_from_process(
    process: Process,
    *,
    reactants: Mapping[str, float],
    products: Mapping[str, float],
    rate_units: str,
    source: str,
    notes: str = "",
) -> Reaction:
    return Reaction(
        name=process.name,
        reactants=reactants,
        products=products,
        rate_law=process.rate,
        rate_units=rate_units,
        assumptions=list(process.assumptions),
        source=source,
        notes=notes,
    )


@dataclass(frozen=True, init=False)
class FirstOrderDecayProcess(Process):
    """Generic first-order loss process for one homogeneous state variable."""

    substrate_state: str
    product_state: str | None
    rate_constant_symbol: str
    state_units: str
    rate_units: str

    def __init__(
        self,
        *,
        name: str,
        substrate_state: str,
        rate_constant_symbol: str,
        state_units: str,
        product_state: str | None = None,
        rate_units: str | None = None,
        source: str = "Generic first-order homogeneous process.",
        notes: str = "",
    ) -> None:
        units = rate_units or f"{state_units} / second"
        changed = [StateVariableSpec(substrate_state, state_units, role="reactant")]
        if product_state is not None:
            changed.append(StateVariableSpec(product_state, state_units, role="product"))
        Process.__init__(
            self,
            name=name,
            process_type="first_order_decay",
            required_state_variables=(StateVariableSpec(substrate_state, state_units, role="reactant"),),
            changed_state_variables=tuple(changed),
            required_parameters=(
                ParameterRequirement(
                    symbol=rate_constant_symbol,
                    units="1 / second",
                    name="first-order rate constant",
                ),
            ),
            assumptions=(homogeneous_process_assumption(),),
            validity=ValidityDomain(
                description="Well-mixed homogeneous first-order process.",
                labels=("homogeneous", "toy", "benchmark"),
                limitations=("No substrate accessibility or transport limitation is represented.",),
            ),
            failure_modes=("negative substrate state", "missing first-order rate constant"),
            source=source,
            notes=notes,
        )
        object.__setattr__(self, "substrate_state", substrate_state)
        object.__setattr__(self, "product_state", product_state)
        object.__setattr__(self, "rate_constant_symbol", rate_constant_symbol)
        object.__setattr__(self, "state_units", state_units)
        object.__setattr__(self, "rate_units", units)

    def rate(
        self,
        state: Mapping[str, Quantity],
        time: Quantity,
        parameters: ParameterSet,
        environment: object = None,
        geometry: object = None,
    ) -> Quantity:
        del time, environment, geometry
        substrate = assert_compatible(state[self.substrate_state], self.state_units, name=self.substrate_state)
        _ensure_non_negative(substrate, self.substrate_state)
        rate = parameters.require_quantity(self.rate_constant_symbol, "1 / second") * substrate
        return assert_compatible(rate, self.rate_units, name=f"{self.name} rate")

    def contributions(self, rate: Quantity) -> Mapping[str, Quantity]:
        value = assert_compatible(rate, self.rate_units, name=f"{self.name} rate")
        contributions: dict[str, Quantity] = {self.substrate_state: cast(Quantity, -value)}
        if self.product_state is not None:
            contributions[self.product_state] = value
        return contributions

    def as_reaction(self) -> Reaction:
        products = {} if self.product_state is None else {self.product_state: 1.0}
        return _reaction_from_process(
            self,
            reactants={self.substrate_state: 1.0},
            products=products,
            rate_units=self.rate_units,
            source=self.source or "Generic first-order homogeneous process.",
            notes=self.notes,
        )


@dataclass(frozen=True, init=False)
class MassActionProcess(Process):
    """Generic homogeneous mass-action process."""

    reactants: dict[str, float]
    products: dict[str, float]
    state_units: dict[str, str]
    rate_constant_symbol: str
    rate_constant_units: str
    rate_units: str

    def __init__(
        self,
        *,
        name: str,
        reactants: Mapping[str, float],
        products: Mapping[str, float],
        state_units: Mapping[str, str],
        rate_constant_symbol: str,
        rate_constant_units: str,
        rate_units: str,
        source: str = "Generic mass-action homogeneous process.",
        notes: str = "",
    ) -> None:
        all_species = set(reactants) | set(products)
        missing_units = all_species.difference(state_units)
        if missing_units:
            raise ValueError(f"Missing state units for species: {sorted(missing_units)}")
        Process.__init__(
            self,
            name=name,
            process_type="mass_action",
            required_state_variables=tuple(
                StateVariableSpec(species, state_units[species], role="reactant")
                for species in reactants
            ),
            changed_state_variables=tuple(
                StateVariableSpec(species, state_units[species])
                for species in all_species
            ),
            required_parameters=(
                ParameterRequirement(
                    symbol=rate_constant_symbol,
                    units=rate_constant_units,
                    name="mass-action rate constant",
                ),
            ),
            assumptions=(homogeneous_process_assumption(),),
            validity=ValidityDomain(
                description="Well-mixed homogeneous mass-action process.",
                labels=("homogeneous", "mass_action"),
            ),
            failure_modes=("negative reactant state", "missing mass-action rate constant"),
            source=source,
            notes=notes,
        )
        object.__setattr__(self, "reactants", dict(reactants))
        object.__setattr__(self, "products", dict(products))
        object.__setattr__(self, "state_units", dict(state_units))
        object.__setattr__(self, "rate_constant_symbol", rate_constant_symbol)
        object.__setattr__(self, "rate_constant_units", rate_constant_units)
        object.__setattr__(self, "rate_units", rate_units)

    def rate(
        self,
        state: Mapping[str, Quantity],
        time: Quantity,
        parameters: ParameterSet,
        environment: object = None,
        geometry: object = None,
    ) -> Quantity:
        del time, environment, geometry
        rate = parameters.require_quantity(self.rate_constant_symbol, self.rate_constant_units)
        for species, order in self.reactants.items():
            quantity = assert_compatible(state[species], self.state_units[species], name=species)
            _ensure_non_negative(quantity, species)
            rate *= quantity ** float(order)
        return assert_compatible(rate, self.rate_units, name=f"{self.name} rate")

    def contributions(self, rate: Quantity) -> Mapping[str, Quantity]:
        value = assert_compatible(rate, self.rate_units, name=f"{self.name} rate")
        return {
            species: coefficient * value
            for species, coefficient in _signed_stoichiometry(self.reactants, self.products).items()
        }

    def as_reaction(self) -> Reaction:
        return _reaction_from_process(
            self,
            reactants=self.reactants,
            products=self.products,
            rate_units=self.rate_units,
            source=self.source or "Generic mass-action homogeneous process.",
            notes=self.notes,
        )


@dataclass(frozen=True, init=False)
class HomogeneousMichaelisMentenProcess(Process):
    """Generic homogeneous Michaelis-Menten process."""

    substrate_state: str
    product_state: str | None
    substrate_units: str
    rate_units: str
    km_symbol: str
    vmax_symbol: str | None
    enzyme_state: str | None
    enzyme_units: str | None
    kcat_symbol: str | None
    product_coefficients: dict[str, float]

    def __init__(
        self,
        *,
        name: str,
        substrate_state: str,
        km_symbol: str,
        rate_units: str,
        substrate_units: str,
        product_state: str | None = None,
        vmax_symbol: str | None = None,
        enzyme_state: str | None = None,
        enzyme_units: str | None = None,
        kcat_symbol: str | None = None,
        product_coefficients: Mapping[str, float] | None = None,
        source: str = "Generic homogeneous Michaelis-Menten process.",
        notes: str = "",
    ) -> None:
        if (vmax_symbol is None) == (kcat_symbol is None or enzyme_state is None):
            raise ValueError(
                "Provide either vmax_symbol, or both enzyme_state and kcat_symbol."
            )
        coefficients = _product_coefficients(product_state=product_state, product_coefficients=product_coefficients)
        required_states = [StateVariableSpec(substrate_state, substrate_units, role="substrate")]
        changed_states = [StateVariableSpec(substrate_state, substrate_units, role="reactant")]
        changed_states.extend(
            StateVariableSpec(state_name, substrate_units, role="product")
            for state_name in coefficients
        )
        parameter_requirements = [
            ParameterRequirement(symbol=km_symbol, units=substrate_units, name="Michaelis constant")
        ]
        if vmax_symbol is not None:
            parameter_requirements.append(
                ParameterRequirement(symbol=vmax_symbol, units=rate_units, name="maximum rate")
            )
        else:
            assert enzyme_state is not None
            assert enzyme_units is not None
            assert kcat_symbol is not None
            required_states.append(StateVariableSpec(enzyme_state, enzyme_units, role="enzyme"))
            changed_states.append(StateVariableSpec(enzyme_state, enzyme_units, role="enzyme"))
            parameter_requirements.append(
                ParameterRequirement(symbol=kcat_symbol, units=f"{rate_units} / ({enzyme_units})", name="turnover coefficient")
            )
        Process.__init__(
            self,
            name=name,
            process_type="homogeneous_michaelis_menten",
            required_state_variables=tuple(required_states),
            changed_state_variables=tuple(changed_states),
            required_parameters=tuple(parameter_requirements),
            assumptions=(homogeneous_process_assumption(),),
            validity=ValidityDomain(
                description="Dissolved, well-mixed homogeneous Michaelis-Menten process.",
                labels=("homogeneous", "dissolved", "benchmark"),
                limitations=("Not valid for solid-substrate surface accessibility by itself.",),
            ),
            failure_modes=("zero or negative Km", "negative substrate", "negative enzyme"),
            source=source,
            notes=notes,
        )
        object.__setattr__(self, "substrate_state", substrate_state)
        object.__setattr__(self, "product_state", product_state)
        object.__setattr__(self, "substrate_units", substrate_units)
        object.__setattr__(self, "rate_units", rate_units)
        object.__setattr__(self, "km_symbol", km_symbol)
        object.__setattr__(self, "vmax_symbol", vmax_symbol)
        object.__setattr__(self, "enzyme_state", enzyme_state)
        object.__setattr__(self, "enzyme_units", enzyme_units)
        object.__setattr__(self, "kcat_symbol", kcat_symbol)
        object.__setattr__(self, "product_coefficients", coefficients)

    def rate(
        self,
        state: Mapping[str, Quantity],
        time: Quantity,
        parameters: ParameterSet,
        environment: object = None,
        geometry: object = None,
    ) -> Quantity:
        del time, environment, geometry
        substrate = assert_compatible(
            require_quantity(state[self.substrate_state], name=self.substrate_state),
            self.substrate_units,
            name=self.substrate_state,
        )
        km = parameters.require_quantity(self.km_symbol, self.substrate_units)
        if self.vmax_symbol is not None:
            return michaelis_menten_rate(
                substrate=substrate,
                vmax=parameters.require_quantity(self.vmax_symbol, self.rate_units),
                km=km,
                rate_units=self.rate_units,
            )
        assert self.enzyme_state is not None
        assert self.enzyme_units is not None
        assert self.kcat_symbol is not None
        return enzyme_explicit_michaelis_menten_rate(
            substrate=substrate,
            enzyme=assert_compatible(state[self.enzyme_state], self.enzyme_units, name=self.enzyme_state),
            kcat=parameters.require_quantity(self.kcat_symbol, f"{self.rate_units} / ({self.enzyme_units})"),
            km=km,
            rate_units=self.rate_units,
        )

    def contributions(self, rate: Quantity) -> Mapping[str, Quantity]:
        value = assert_compatible(rate, self.rate_units, name=f"{self.name} rate")
        contributions: dict[str, Quantity] = {self.substrate_state: cast(Quantity, -value)}
        for state_name, coefficient in self.product_coefficients.items():
            contributions[state_name] = coefficient * value
        return contributions

    def as_reaction(self) -> Reaction:
        return _reaction_from_process(
            self,
            reactants={self.substrate_state: 1.0},
            products=self.product_coefficients,
            rate_units=self.rate_units,
            source=self.source or "Generic homogeneous Michaelis-Menten process.",
            notes=self.notes,
        )


def _signed_stoichiometry(
    reactants: Mapping[str, float],
    products: Mapping[str, float],
) -> dict[str, float]:
    species = set(reactants) | set(products)
    return {
        name: float(products.get(name, 0.0) - reactants.get(name, 0.0))
        for name in species
    }


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
    "FirstOrderDecayProcess",
    "HomogeneousMichaelisMentenProcess",
    "MassActionProcess",
    "homogeneous_process_assumption",
]
