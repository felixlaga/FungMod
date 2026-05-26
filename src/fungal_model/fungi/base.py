"""Fungus metadata for Stage 6 biomass/enzyme models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_, UnitError
from fungal_model.fungi.enzyme_profile import EnzymeProfile
from fungal_model.fungi.metabolism import ProductAssimilation


FUNGAL_PARAMETER_UNITS = {
    "T_growth_min": "kelvin",
    "T_growth_max": "kelvin",
    "pH_growth_min": "dimensionless",
    "pH_growth_max": "dimensionless",
    "a_w_min": "dimensionless",
    "alpha_E": "mole / liter / kilogram / second",
    "delta_E": "1 / second",
    "c_E": "kilogram / (mole / liter)",
    "m_B": "1 / second",
    "q_product": "1 / kilogram / second",
    "Y_B": "dimensionless",
}

FUNGAL_PARAMETER_NAMES = {
    "T_growth_min": "minimum fungal growth temperature",
    "T_growth_max": "maximum fungal growth temperature",
    "pH_growth_min": "minimum fungal growth pH",
    "pH_growth_max": "maximum fungal growth pH",
    "a_w_min": "minimum water activity for growth",
    "alpha_E": "enzyme secretion coefficient",
    "delta_E": "extracellular enzyme decay constant",
    "c_E": "active biomass cost per secreted enzyme concentration",
    "m_B": "active biomass maintenance constant",
    "q_product": "assimilable product uptake coefficient",
    "Y_B": "biomass yield on assimilated product",
}


def _unknown_fungal_parameter(symbol: str) -> Parameter:
    return Parameter(
        name=FUNGAL_PARAMETER_NAMES[symbol],
        symbol=symbol,
        value=None,
        units=FUNGAL_PARAMETER_UNITS[symbol],
        uncertainty=None,
        source="Not provided; explicitly marked unknown by fungus construction.",
        confidence_level="unknown",
        notes="Supply a sourced Parameter before scientific simulation.",
        measurement_method=None,
    )


def make_fungal_parameter_set(overrides: Iterable[Parameter] | None = None) -> ParameterSet:
    """Create a complete Stage 6 fungal parameter set with optional overrides."""

    parameters = {
        symbol: _unknown_fungal_parameter(symbol)
        for symbol in FUNGAL_PARAMETER_UNITS
    }
    for override in overrides or ():
        if override.symbol not in FUNGAL_PARAMETER_UNITS:
            raise KeyError(f"{override.symbol!r} is not a recognized fungal parameter symbol.")
        expected_units = FUNGAL_PARAMETER_UNITS[override.symbol]
        try:
            Q_(1, override.units).to(expected_units)
        except Exception as exc:
            raise UnitError(
                f"Fungal parameter {override.symbol} must use units compatible with {expected_units}."
            ) from exc
        parameters[override.symbol] = override
    return ParameterSet(parameters.values())


def fungal_stage6_assumption() -> Assumption:
    """Return the overall Stage 6 fungal modelling assumption."""

    return Assumption(
        name="minimal active-biomass fungal enzyme model",
        description=(
            "Fungus is represented by active/dormant/dead biomass states, "
            "secreted enzyme concentration, maintenance loss, and optional "
            "growth from explicitly assimilable degradation product."
        ),
        justification=(
            "Fungal dynamics should enter only after enzyme-only PET hydrolysis "
            "has been validated, and should begin with a small interpretable ODE model."
        ),
        known_limitations=(
            "Does not model gene regulation, oxygen limitation, moisture "
            "feedback, dormancy transitions, intracellular metabolism, toxicity, "
            "or thermodynamic yield constraints."
        ),
        source="Stage 6 modelling assumption for minimal fungal enzyme secretion and biomass dynamics.",
    )


@dataclass(frozen=True)
class Fungus:
    """Fungal metadata and provenance-backed Stage 6 parameters."""

    species_name: str
    enzyme_profile: EnzymeProfile
    parameters: ParameterSet
    known_substrates: tuple[str, ...] = field(default_factory=tuple)
    uptake_capabilities: tuple[ProductAssimilation, ...] = field(default_factory=tuple)
    oxygen_requirement: str = "unknown"
    moisture_requirement: str = "unknown"
    assumptions: tuple[Assumption, ...] = field(default_factory=lambda: (fungal_stage6_assumption(),))
    notes: str = ""
    references: tuple[str, ...] = field(default_factory=tuple)

    def validate(
        self,
        *,
        allow_unsourced_for_testing: bool = False,
        require_parameter_values: bool = False,
    ) -> None:
        self.enzyme_profile.validate(allow_unsourced_for_testing=allow_unsourced_for_testing)
        for capability in self.uptake_capabilities:
            capability.validate(allow_unsourced_for_testing=allow_unsourced_for_testing)
        self.parameters.validate(
            allow_unsourced_for_testing=allow_unsourced_for_testing,
            require_values=require_parameter_values,
        )
        for symbol, units in FUNGAL_PARAMETER_UNITS.items():
            parameter = self.parameters.get(symbol)
            try:
                Q_(1, parameter.units).to(units)
            except Exception as exc:
                raise UnitError(
                    f"Fungal parameter {symbol} must use units compatible with {units}."
                ) from exc

    def can_assimilate_product(self, product: str) -> bool:
        normalized = product.casefold()
        return any(
            capability.product.casefold() == normalized and capability.assimilable
            for capability in self.uptake_capabilities
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "species_name": self.species_name,
            "enzyme_profile": self.enzyme_profile.to_dict(),
            "parameters": self.parameters.to_dict(),
            "known_substrates": list(self.known_substrates),
            "uptake_capabilities": [
                capability.to_dict() for capability in self.uptake_capabilities
            ],
            "oxygen_requirement": self.oxygen_requirement,
            "moisture_requirement": self.moisture_requirement,
            "assumptions": [assumption.to_dict() for assumption in self.assumptions],
            "notes": self.notes,
            "references": list(self.references),
        }


__all__ = [
    "FUNGAL_PARAMETER_NAMES",
    "FUNGAL_PARAMETER_UNITS",
    "Fungus",
    "fungal_stage6_assumption",
    "make_fungal_parameter_set",
]
