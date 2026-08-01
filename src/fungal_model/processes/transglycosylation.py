"""Coupled hydrolysis and substrate-transglycosylation branch kinetics."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.errors import InvalidMechanismError
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Quantity, assert_compatible, require_quantity
from fungal_model.processes.base import ParameterRequirement, Process, StateVariableSpec, ValidityDomain
from fungal_model.processes.homogeneous import homogeneous_process_assumption
from fungal_model.processes.surface import ProductReleaseMap


TransglycosylationBranch = Literal["hydrolysis", "transglycosylation"]
TRANSGLYCOSYLATION_MATURITY = "literature_backed_software_tested"


@dataclass(frozen=True, init=False)
class SubstrateTransglycosylationProcess(Process):
    """One explicit branch of a coupled retaining-glycosidase rate law.

    Two instances with the same state and parameter symbols represent the
    hydrolysis and substrate-transglycosylation branches. Their product maps
    own the distinct stoichiometries; the kinetic denominator is shared by
    construction, without a substrate-, enzyme-, or organism-specific branch.
    """

    branch: TransglycosylationBranch
    substrate_state: str
    enzyme_state: str
    substrate_units: str
    enzyme_units: str
    rate_units: str
    hydrolysis_km_symbol: str
    transglycosylation_km_symbol: str
    hydrolysis_kcat_symbol: str
    transglycosylation_kcat_symbol: str
    product_release_map: ProductReleaseMap
    primary_source: str
    maturity: str

    def __init__(
        self,
        *,
        name: str,
        branch: TransglycosylationBranch,
        substrate_state: str,
        enzyme_state: str,
        substrate_units: str,
        enzyme_units: str,
        rate_units: str,
        hydrolysis_km_symbol: str,
        transglycosylation_km_symbol: str,
        hydrolysis_kcat_symbol: str,
        transglycosylation_kcat_symbol: str,
        product_release_map: ProductReleaseMap,
        primary_source: str,
        maturity: str,
        notes: str = "",
    ) -> None:
        if branch not in {"hydrolysis", "transglycosylation"}:
            raise InvalidMechanismError(
                "Substrate transglycosylation branch must be 'hydrolysis' or 'transglycosylation'."
            )
        source = str(primary_source).strip()
        if not source:
            raise InvalidMechanismError("Substrate transglycosylation requires a nonblank primary_source.")
        if maturity != TRANSGLYCOSYLATION_MATURITY:
            raise InvalidMechanismError(
                "Substrate transglycosylation maturity must be "
                f"{TRANSGLYCOSYLATION_MATURITY!r}."
            )
        expected_reactant_coefficient = 1.0 if branch == "hydrolysis" else 2.0
        if set(product_release_map.reactants) != {substrate_state} or not np.isclose(
            float(product_release_map.reactants.get(substrate_state, 0.0)),
            expected_reactant_coefficient,
        ):
            raise InvalidMechanismError(
                f"The {branch} product map must consume exactly "
                f"{expected_reactant_coefficient:g} equivalents of the configured substrate."
            )
        if not product_release_map.products:
            raise InvalidMechanismError("Substrate transglycosylation product maps require explicit products.")

        state_specs = tuple(
            StateVariableSpec(species, substrate_units, role="reactant" if species == substrate_state else "product")
            for species in sorted(product_release_map.species)
        )
        turnover_units = f"({rate_units}) / ({enzyme_units})"
        Process.__init__(
            self,
            name=name,
            process_type="substrate_transglycosylation",
            required_state_variables=(
                StateVariableSpec(substrate_state, substrate_units, role="substrate_donor_acceptor"),
                StateVariableSpec(enzyme_state, enzyme_units, role="enzyme"),
            ),
            changed_state_variables=state_specs,
            required_parameters=(
                ParameterRequirement(
                    symbol=hydrolysis_km_symbol,
                    units=substrate_units,
                    name="hydrolysis Michaelis constant",
                ),
                ParameterRequirement(
                    symbol=transglycosylation_km_symbol,
                    units=substrate_units,
                    name="substrate-transglycosylation Michaelis constant",
                ),
                ParameterRequirement(
                    symbol=hydrolysis_kcat_symbol,
                    units=turnover_units,
                    name="hydrolysis turnover coefficient",
                ),
                ParameterRequirement(
                    symbol=transglycosylation_kcat_symbol,
                    units=turnover_units,
                    name="substrate-transglycosylation turnover coefficient",
                ),
            ),
            assumptions=(
                homogeneous_process_assumption(),
                Assumption(
                    name="coupled retaining-glycosidase substrate transglycosylation",
                    description=(
                        "Hydrolysis and substrate transglycosylation compete through "
                        "Km_h + S + S^2/Km_t; a second substrate molecule is the acceptor."
                    ),
                    justification=(
                        "Primary fungal kinetic studies report the coupled law and direct "
                        "formation of substrate-transglycosylation products."
                    ),
                    known_limitations=(
                        "Initial-rate, well-mixed law only; transfer-product re-hydrolysis, "
                        "multiple acceptors/products, water activity, transport, regulation, "
                        "growth, secretion, uptake, and whole-fungus physiology are omitted."
                    ),
                    source=source,
                ),
            ),
            validity=ValidityDomain(
                description="Coupled homogeneous hydrolysis/substrate-transglycosylation initial-rate branch.",
                labels=("homogeneous", "retaining_glycosidase", "substrate_transglycosylation", maturity),
                limitations=(
                    "Case applicability and parameters require separate source evidence.",
                    "A configured product map must explicitly own branch stoichiometry and product identity or pool scope.",
                ),
            ),
            failure_modes=(
                "missing or non-positive kinetic constants",
                "negative substrate or enzyme state",
                "unsupported maturity or missing primary source",
                "branch/product-map stoichiometry mismatch",
            ),
            source=source,
            notes=notes,
        )
        object.__setattr__(self, "branch", branch)
        object.__setattr__(self, "substrate_state", substrate_state)
        object.__setattr__(self, "enzyme_state", enzyme_state)
        object.__setattr__(self, "substrate_units", substrate_units)
        object.__setattr__(self, "enzyme_units", enzyme_units)
        object.__setattr__(self, "rate_units", rate_units)
        object.__setattr__(self, "hydrolysis_km_symbol", hydrolysis_km_symbol)
        object.__setattr__(self, "transglycosylation_km_symbol", transglycosylation_km_symbol)
        object.__setattr__(self, "hydrolysis_kcat_symbol", hydrolysis_kcat_symbol)
        object.__setattr__(self, "transglycosylation_kcat_symbol", transglycosylation_kcat_symbol)
        object.__setattr__(self, "product_release_map", product_release_map)
        object.__setattr__(self, "primary_source", source)
        object.__setattr__(self, "maturity", maturity)

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
        enzyme = assert_compatible(
            require_quantity(state[self.enzyme_state], name=self.enzyme_state),
            self.enzyme_units,
            name=self.enzyme_state,
        )
        _require_nonnegative(substrate, self.substrate_state)
        _require_nonnegative(enzyme, self.enzyme_state)

        km_h = parameters.require_quantity(self.hydrolysis_km_symbol, self.substrate_units)
        km_t = parameters.require_quantity(self.transglycosylation_km_symbol, self.substrate_units)
        turnover_units = f"({self.rate_units}) / ({self.enzyme_units})"
        kcat_h = parameters.require_quantity(self.hydrolysis_kcat_symbol, turnover_units)
        kcat_t = parameters.require_quantity(self.transglycosylation_kcat_symbol, turnover_units)
        _require_positive(km_h, self.hydrolysis_km_symbol)
        _require_positive(km_t, self.transglycosylation_km_symbol)
        _require_nonnegative(kcat_h, self.hydrolysis_kcat_symbol)
        _require_nonnegative(kcat_t, self.transglycosylation_kcat_symbol)

        acceptor_term = substrate**2 / km_t
        denominator = km_h + substrate + acceptor_term
        if self.branch == "hydrolysis":
            branch_rate = enzyme * kcat_h * substrate / denominator
        else:
            branch_rate = enzyme * kcat_t * acceptor_term / denominator
        return assert_compatible(branch_rate, self.rate_units, name=f"{self.name} rate")

    def contributions(self, rate: Quantity) -> Mapping[str, Quantity]:
        value = assert_compatible(rate, self.rate_units, name=f"{self.name} rate")
        return {
            species: cast(Quantity, self.product_release_map.signed_coefficient(species) * value)
            for species in self.product_release_map.species
        }

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "branch": self.branch,
                "substrate_state": self.substrate_state,
                "enzyme_state": self.enzyme_state,
                "hydrolysis_km_symbol": self.hydrolysis_km_symbol,
                "transglycosylation_km_symbol": self.transglycosylation_km_symbol,
                "hydrolysis_kcat_symbol": self.hydrolysis_kcat_symbol,
                "transglycosylation_kcat_symbol": self.transglycosylation_kcat_symbol,
                "product_release_map": self.product_release_map.to_dict(),
                "primary_source": self.primary_source,
                "maturity": self.maturity,
                "equation": (
                    "r_h = E*kcat_h*S/(Km_h + S + S^2/Km_t); "
                    "r_t = E*kcat_t*(S^2/Km_t)/(Km_h + S + S^2/Km_t)"
                ),
            }
        )
        return data


def _require_nonnegative(quantity: Quantity, name: str) -> None:
    values = np.asarray(quantity.magnitude, dtype=float)
    if not np.all(np.isfinite(values)) or np.any(values < 0.0):
        raise ValueError(f"{name} must be finite and non-negative.")


def _require_positive(quantity: Quantity, name: str) -> None:
    values = np.asarray(quantity.magnitude, dtype=float)
    if not np.all(np.isfinite(values)) or np.any(values <= 0.0):
        raise ValueError(f"{name} must be finite and positive.")


__all__ = [
    "TRANSGLYCOSYLATION_MATURITY",
    "SubstrateTransglycosylationProcess",
    "TransglycosylationBranch",
]
