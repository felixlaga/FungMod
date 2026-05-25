"""Chitin substrate metadata.

Stage 9 records chitin as a nitrogen-containing beta-glucan-like structural
polysaccharide with unresolved crystalline form, acetylation state, morphology,
and enzyme accessibility. No chitin hydrolysis kinetics are implemented.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.substrates.base import (
    DegradationProduct,
    Substrate,
    SubstrateParameterSpec,
    make_substrate_parameter_set,
    validate_substrate_parameter_units,
)

CHITIN_REFERENCE_NOTE = (
    "High-level chitin polymer identity and chitinolytic enzyme-class metadata; "
    "no numerical material or kinetic parameter values are supplied."
)

CHITIN_PARAMETER_SPECS = (
    SubstrateParameterSpec(
        symbol="rho_chitin",
        name="chitin material density",
        units="kilogram / meter ** 3",
        notes="Density depends on source organism, polymorph, hydration, and extraction method.",
    ),
    SubstrateParameterSpec(
        symbol="epsilon_chitin",
        name="chitin substrate porosity",
        units="dimensionless",
        notes="Porosity is substrate-preparation specific and is not inferred.",
    ),
    SubstrateParameterSpec(
        symbol="chi_c_chitin",
        name="chitin crystallinity fraction",
        units="dimensionless",
        notes="Crystallinity and polymorph must be measured for the material.",
    ),
    SubstrateParameterSpec(
        symbol="A_surface_chitin",
        name="chitin geometric surface area",
        units="meter ** 2",
        notes="Surface area depends on morphology and sample preparation.",
    ),
    SubstrateParameterSpec(
        symbol="A_accessible_chitin",
        name="chitin accessible bond surface area",
        units="meter ** 2",
        notes="Accessible glycosidic-bond surface requires material-specific evidence.",
    ),
    SubstrateParameterSpec(
        symbol="a_w_min_chitin",
        name="minimum water activity for chitin degradation",
        units="dimensionless",
        notes="Water-activity dependence is not implemented.",
    ),
)


def chitin_metadata_assumption() -> Assumption:
    return Assumption(
        name="Chitin metadata placeholder",
        description=(
            "Chitin is represented as a solid nitrogen-containing polysaccharide "
            "with beta-1,4 glycosidic bonds between N-acetylglucosamine units."
        ),
        justification=(
            "Stage 9 records substrate identity and required enzyme classes "
            "without inventing chitin hydrolysis kinetics."
        ),
        known_limitations=(
            "No chitin polymorph model, degree of acetylation, chitosan "
            "conversion, adsorption, enzyme synergy, or nitrogen assimilation "
            "model is implemented."
        ),
        source=CHITIN_REFERENCE_NOTE,
    )


def default_chitin_degradation_products() -> tuple[DegradationProduct, ...]:
    return (
        DegradationProduct(
            name="N-acetyl-D-glucosamine",
            formula="C8H15NO6",
            assimilable=None,
            notes="Assimilation requires organism-specific uptake and metabolism evidence.",
            source=CHITIN_REFERENCE_NOTE,
        ),
        DegradationProduct(
            name="chitobiose",
            formula="C16H28N2O11",
            assimilable=None,
            notes="Product uptake and catabolism are not assumed.",
            source=CHITIN_REFERENCE_NOTE,
        ),
        DegradationProduct(
            name="chitooligosaccharides",
            formula=None,
            assimilable=None,
            notes="Product distribution depends on enzyme mixture and substrate morphology.",
            source=CHITIN_REFERENCE_NOTE,
        ),
    )


def make_chitin_parameter_set(
    overrides: Iterable[Parameter] | None = None,
) -> ParameterSet:
    return make_substrate_parameter_set(
        CHITIN_PARAMETER_SPECS,
        substrate_name="chitin",
        stage_notes="Stage 9 records chitin physical properties but does not invent values.",
        overrides=overrides,
    )


@dataclass(frozen=True, init=False)
class ChitinSubstrate(Substrate):
    """Chitin substrate metadata with placeholder completeness."""

    repeating_unit: str

    def __init__(
        self,
        *,
        parameters: ParameterSet | None = None,
        notes: str = "",
        references: tuple[str, ...] = (CHITIN_REFERENCE_NOTE,),
    ) -> None:
        Substrate.__init__(
            self,
            name="chitin",
            chemical_class="nitrogen-containing polysaccharide",
            physical_state="solid_biomass",
            bond_types=("beta-1,4-glycosidic",),
            accessible_bonds=("beta-1,4-glycosidic",),
            required_enzyme_classes=(
                "endochitinase",
                "exochitinase",
                "N-acetylglucosaminidase",
                "chitin deacetylase",
            ),
            degradation_products=default_chitin_degradation_products(),
            parameters=parameters or make_chitin_parameter_set(),
            assumptions=(chitin_metadata_assumption(),),
            completeness="placeholder",
            default_degradation_model="unknown",
            water_activity_dependence="unknown; no chitin water-activity response is implemented.",
            notes=notes or "Stage 9 metadata placeholder; no chitin degradation kinetics are implemented.",
            references=references,
        )
        object.__setattr__(self, "repeating_unit", "C8H13NO5")
        self.validate(require_parameter_values=False)

    @property
    def density(self) -> Parameter:
        return self.parameters.get("rho_chitin")

    @property
    def porosity(self) -> Parameter:
        return self.parameters.get("epsilon_chitin")

    @property
    def crystallinity(self) -> Parameter:
        return self.parameters.get("chi_c_chitin")

    @property
    def accessible_surface_area_parameter(self) -> Parameter:
        return self.parameters.get("A_accessible_chitin")

    def validate(
        self,
        *,
        allow_unsourced_for_testing: bool = False,
        require_parameter_values: bool = False,
    ) -> None:
        validate_substrate_parameter_units(
            self.parameters,
            CHITIN_PARAMETER_SPECS,
            substrate_name="chitin",
        )
        super().validate(
            allow_unsourced_for_testing=allow_unsourced_for_testing,
            require_parameter_values=require_parameter_values,
        )

    def to_dict(self) -> dict[str, object]:
        data = super().to_dict()
        data["repeating_unit"] = self.repeating_unit
        return data


__all__ = [
    "CHITIN_PARAMETER_SPECS",
    "CHITIN_REFERENCE_NOTE",
    "ChitinSubstrate",
    "chitin_metadata_assumption",
    "default_chitin_degradation_products",
    "make_chitin_parameter_set",
]
