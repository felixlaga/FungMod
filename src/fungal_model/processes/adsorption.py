"""Provenance-backed, quasi-steady adsorbed-enzyme hydrolysis (BIO-004 M1)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from typing import Any

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.kernels import JacobianKernel, KernelContext, RateKernel, magnitude_in
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import ASSAY_BASE_UNITS, Q_, Quantity, assert_compatible, units_are_compatible
from fungal_model.kinetics.adsorption import enzyme_partition, partition_derivatives, partition_magnitudes
from fungal_model.processes.base import ParameterRequirement, Process, StateVariableSpec, ValidityDomain
from fungal_model.processes.surface import ProductReleaseMap

ADSORBED_ENZYME_HYDROLYSIS_PROCESS_TYPE = "adsorbed_enzyme_hydrolysis"
ADSORPTION_SOURCE = "https://doi.org/10.1186/1754-6834-3-18"
ADSORPTION_MATURITY = "software_tested"
ADSORPTION_LIMITATIONS = (
    "Single productive binding-site class at quasi-steady equilibrium; no binding kinetics or nonproductive adsorption.",
    "No competition, surface area, crystallinity, particle-size, or morphology law.",
    "Proportional bound activity is a case assumption supported for CBH I, not a universal enzyme relation.",
    "Law forms are source-backed and software-tested; supplied constants remain uncalibrated unless separately evidenced.",
)


@dataclass(frozen=True, init=False)
class AdsorbedEnzymeHydrolysisProcess(Process):
    substrate_state: str
    enzyme_state: str
    substrate_units: str
    enzyme_units: str
    rate_units: str
    binding_capacity_symbol: str
    bound_rate_constant_symbol: str
    adsorption_constant_symbol: str | None
    adsorption_dissociation_constant_symbol: str | None
    product_release_map: ProductReleaseMap

    def __init__(
        self, *, name: str, substrate_state: str, enzyme_state: str, substrate_units: str,
        enzyme_units: str, rate_units: str, binding_capacity_symbol: str,
        bound_rate_constant_symbol: str, product_release_map: ProductReleaseMap,
        substrate_physical_state: str, amount_basis: str,
        adsorption_constant_symbol: str | None = None,
        adsorption_dissociation_constant_symbol: str | None = None,
        state_units: Mapping[str, str] | None = None,
        source: str = ADSORPTION_SOURCE, notes: str = "",
    ) -> None:
        if substrate_physical_state != "solid_polymer" or amount_basis != "dry_mass":
            raise ValueError("Adsorbed enzyme hydrolysis requires a solid_polymer substrate on a dry_mass basis.")
        assert_compatible(Q_(1, substrate_units), "g/L", name="solid substrate dry-mass concentration")
        assert_compatible(Q_(1, rate_units), f"({substrate_units})/second", name="hydrolysis rate")
        if not any(units_are_compatible(enzyme_units, u) for u in ("g/L", "mol/L", *(f"{unit}/L" for unit in ASSAY_BASE_UNITS))):
            raise ValueError("Enzyme units must be protein mass, molar amount or declared assay units per volume.")
        if substrate_state == enzyme_state:
            raise ValueError("Substrate and enzyme must be distinct states.")
        if (adsorption_constant_symbol is None) == (adsorption_dissociation_constant_symbol is None):
            raise ValueError("Give exactly one of adsorption_constant and adsorption_dissociation_constant.")
        if dict(product_release_map.reactants) != {substrate_state: 1.0}:
            raise ValueError("Adsorption hydrolysis requires a unit-coefficient solid substrate reactant.")
        if substrate_state in product_release_map.products or enzyme_state in product_release_map.species:
            raise ValueError("The product map cannot create substrate or consume/create total enzyme.")
        units = dict(state_units or {})
        units.update({substrate_state: substrate_units, enzyme_state: enzyme_units})
        for species, coefficient in product_release_map.products.items():
            if not math.isfinite(float(coefficient)) or float(coefficient) < 0.0:
                raise ValueError("Product coefficients must be finite and non-negative.")
            product_units = units.get(species, substrate_units)
            assert_compatible(Q_(1, substrate_units) * Q_(1, product_release_map.coefficient_units.get(species, "dimensionless")), product_units, name=f"product yield for {species}")
            units[species] = product_units
        requirements = [
            ParameterRequirement(binding_capacity_symbol, f"({enzyme_units})/({substrate_units})", "binding capacity"),
            ParameterRequirement(bound_rate_constant_symbol, f"({rate_units})/({enzyme_units})", "rate per bound enzyme"),
        ]
        if adsorption_constant_symbol is not None:
            requirements.append(ParameterRequirement(adsorption_constant_symbol, f"1/({enzyme_units})", "association constant"))
        else:
            assert adsorption_dissociation_constant_symbol is not None
            requirements.append(ParameterRequirement(adsorption_dissociation_constant_symbol, enzyme_units, "dissociation constant"))
        Process.__init__(
            self, name=name, process_type=ADSORBED_ENZYME_HYDROLYSIS_PROCESS_TYPE,
            required_state_variables=(StateVariableSpec(substrate_state, substrate_units, role="substrate"), StateVariableSpec(enzyme_state, enzyme_units, role="enzyme")),
            changed_state_variables=tuple(StateVariableSpec(s, units[s], role="substrate" if s == substrate_state else "product") for s in sorted(product_release_map.species)),
            required_parameters=tuple(requirements),
            assumptions=(Assumption(name="quasi-steady finite-enzyme Langmuir partition", description="E_b = Gamma S E_f/(Kd+E_f); E_T = E_f + E_b; r = k_b E_b.", justification="Published single-site isotherm with exact enzyme conservation and explicit proportional bound activity.", known_limitations=" ".join(ADSORPTION_LIMITATIONS), source=source),),
            validity=ValidityDomain(description="Quasi-steady productive single-site adsorption on a dry-mass solid.", labels=("adsorption", "software_tested"), limitations=ADSORPTION_LIMITATIONS),
            failure_modes=("incompatible enzyme/capacity units", "non-solid substrate", "missing or ambiguous adsorption constant", "non-positive binding constants"), source=source, notes=notes,
        )
        for key, value in locals().copy().items():
            if key in self.__annotations__:
                object.__setattr__(self, key, value)

    def _constants(self, parameters: ParameterSet) -> tuple[float, float, float]:
        capacity = magnitude_in(parameters.require_quantity(self.binding_capacity_symbol), f"({self.enzyme_units})/({self.substrate_units})", name="binding capacity")
        rate = magnitude_in(parameters.require_quantity(self.bound_rate_constant_symbol), f"({self.rate_units})/({self.enzyme_units})", name="bound rate constant")
        if self.adsorption_constant_symbol is not None:
            association = magnitude_in(parameters.require_quantity(self.adsorption_constant_symbol), f"1/({self.enzyme_units})", name="adsorption constant")
            if not math.isfinite(association) or association <= 0.0:
                raise ValueError("adsorption constant must be finite and positive.")
            dissociation = 1.0 / association
        else:
            assert self.adsorption_dissociation_constant_symbol is not None
            dissociation = magnitude_in(parameters.require_quantity(self.adsorption_dissociation_constant_symbol), self.enzyme_units, name="adsorption dissociation constant")
        if not math.isfinite(capacity) or capacity < 0.0 or not math.isfinite(rate) or rate < 0.0:
            raise ValueError("binding capacity and bound rate constant must be finite and non-negative.")
        if not math.isfinite(dissociation) or dissociation <= 0.0:
            raise ValueError("adsorption dissociation constant must be finite and positive.")
        return capacity, rate, dissociation

    def partition(self, state: Mapping[str, Quantity], parameters: ParameterSet):
        capacity, _, dissociation = self._constants(parameters)
        return enzyme_partition(total_enzyme=assert_compatible(state[self.enzyme_state], self.enzyme_units, name=self.enzyme_state), solid_substrate=assert_compatible(state[self.substrate_state], self.substrate_units, name=self.substrate_state), binding_capacity=Q_(capacity, f"({self.enzyme_units})/({self.substrate_units})"), adsorption_dissociation_constant=Q_(dissociation, self.enzyme_units))

    def rate(self, state: Mapping[str, Quantity], time: Quantity, parameters: ParameterSet, environment: Any = None, geometry: Any = None) -> Quantity:
        del time, environment, geometry
        _, rate, _ = self._constants(parameters)
        return Q_(rate * float(self.partition(state, parameters).bound.magnitude), self.rate_units)

    def compile_rate(self, context: KernelContext) -> RateKernel:
        si, ss = context.state_slot(self.substrate_state, self.substrate_units)
        ei, es = context.state_slot(self.enzyme_state, self.enzyme_units)
        capacity, rate, dissociation = self._constants(context.parameters)
        def kernel(time: float, state: np.ndarray) -> float:
            del time
            substrate = state[si] * ss
            if not math.isfinite(substrate) or substrate < 0.0:
                raise ValueError("solid substrate must be finite and non-negative.")
            return rate * partition_magnitudes(state[ei] * es, capacity * substrate, dissociation)[1]
        return kernel

    def compile_jacobian(self, context: KernelContext) -> JacobianKernel:
        si, ss = context.state_slot(self.substrate_state, self.substrate_units)
        ei, es = context.state_slot(self.enzyme_state, self.enzyme_units)
        capacity, rate, dissociation = self._constants(context.parameters)
        def gradient(time: float, state: np.ndarray) -> np.ndarray:
            del time
            substrate = state[si] * ss
            if not math.isfinite(substrate) or substrate < 0.0:
                raise ValueError("solid substrate must be finite and non-negative.")
            de, dc = partition_derivatives(state[ei] * es, capacity * substrate, dissociation)
            result = np.zeros(len(context.state_index), dtype=float)
            result[si] = rate * dc * capacity * ss
            result[ei] = rate * de * es
            return result
        return gradient

    def contributions(self, rate: Quantity) -> Mapping[str, Quantity]:
        rate = assert_compatible(rate, self.rate_units, name="adsorbed-enzyme hydrolysis rate")
        result = {self.substrate_state: Q_(-rate.magnitude, rate.units)}
        for state, coefficient in self.product_release_map.products.items():
            units = self.product_release_map.coefficient_units.get(state, "dimensionless")
            result[state] = Q_(float(coefficient) * rate.magnitude, f"({rate.units}) * ({units})")
        return result

    def derived_quantities(self, states: Mapping[str, Quantity], parameters: ParameterSet) -> dict[str, Quantity]:
        """Free/bound curves and enzyme conservation; no extra ODE state."""
        substrate = states[self.substrate_state].to(self.substrate_units)
        total = states[self.enzyme_state].to(self.enzyme_units)
        sm, em = np.broadcast_arrays(np.asarray(substrate.magnitude, dtype=float), np.asarray(total.magnitude, dtype=float))
        free, bound = np.empty_like(em), np.empty_like(em)
        capacity, _, dissociation = self._constants(parameters)
        for index in np.ndindex(em.shape):
            free[index], bound[index] = partition_magnitudes(float(em[index]), capacity * float(sm[index]), dissociation)
        defined = em != 0.0
        fraction = np.divide(bound, em, out=np.full_like(bound, np.nan), where=defined)
        return {
            "free_enzyme": Q_(free, self.enzyme_units),
            "bound_enzyme": Q_(bound, self.enzyme_units),
            "total_enzyme": Q_(em, self.enzyme_units),
            "enzyme_conservation_residual": Q_(free + bound - em, self.enzyme_units),
            "bound_fraction": Q_(fraction, "dimensionless"),
            "bound_fraction_defined": Q_(defined, "dimensionless"),
        }

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result.update({"maturity": ADSORPTION_MATURITY, "law_source_ids": ["jaeger_2010_langmuir", "medve_1998_bound_activity"], "product_release_map": self.product_release_map.to_dict()})
        return result


@dataclass(frozen=True)
class AdsorbedEnzymeHydrolysisFactory:
    process_type: str = ADSORBED_ENZYME_HYDROLYSIS_PROCESS_TYPE

    def can_build(self, context: Any, process_config: Any) -> Any:
        from fungal_model.processes.factories import BuildDecision
        states = getattr(process_config, "states", {})
        parameters = getattr(process_config, "parameters", {})
        missing = [f"states.{key}" for key in ("substrate", "enzyme") if key not in states]
        missing += [f"parameters.{key}" for key in ("binding_capacity", "bound_rate_constant", "rate_units") if key not in parameters]
        missing += [f"state_units.{states[key]}" for key in ("substrate", "enzyme") if key in states and states[key] not in context.state_units]
        raw = getattr(process_config, "raw", {}) or {}
        missing += [key for key in ("substrate_physical_state", "amount_basis") if key not in raw]
        product_map_id = getattr(process_config, "product_map", None)
        if product_map_id not in context.product_maps:
            missing.append("product_map")
        reasons = []
        if (parameters.get("adsorption_constant") is None) == (parameters.get("adsorption_dissociation_constant") is None):
            reasons.append("Give exactly one of adsorption_constant and adsorption_dissociation_constant.")
        return BuildDecision(can_build=not missing and not reasons, process_type=self.process_type, factory=type(self).__name__, missing_fields=tuple(missing), reasons=tuple(reasons))

    def build(self, context: Any, process_config: Any) -> Process:
        from fungal_model.processes.factories import _apply_rate_modifiers, _require_buildable
        _require_buildable(self.can_build(context, process_config))
        states, parameters = process_config.states, process_config.parameters
        process = AdsorbedEnzymeHydrolysisProcess(
            name=process_config.id, substrate_state=states["substrate"], enzyme_state=states["enzyme"],
            substrate_units=context.state_units[states["substrate"]], enzyme_units=context.state_units[states["enzyme"]],
            rate_units=parameters["rate_units"], binding_capacity_symbol=parameters["binding_capacity"],
            bound_rate_constant_symbol=parameters["bound_rate_constant"], adsorption_constant_symbol=parameters.get("adsorption_constant"),
            adsorption_dissociation_constant_symbol=parameters.get("adsorption_dissociation_constant"),
            substrate_physical_state=process_config.raw["substrate_physical_state"], amount_basis=process_config.raw["amount_basis"],
            product_release_map=context.product_maps[process_config.product_map], state_units=context.state_units,
            source=ADSORPTION_SOURCE, notes="Quasi-steady adsorption; constants supplied by explicit records.",
        )
        return _apply_rate_modifiers(context, process_config, process)
