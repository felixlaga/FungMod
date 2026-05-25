"""Cellulose substrate metadata.

Stage 9 records cellulose identity, relevant bond classes, broad enzyme-class
requirements, and explicitly unknown physical parameters. This module does not
provide cellulose hydrolysis kinetics, crystallite accessibility, lignocellulose
embedding, adsorption, or fungal regulation.
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

CELLULOSE_REFERENCE_NOTE = (
    "High-level cellulose polymer identity and cellulolytic enzyme-class "
    "metadata; no numerical material or kinetic parameter values are supplied."
)

CELLULOSE_PARAMETER_SPECS = (
    SubstrateParameterSpec(
        symbol="rho_cellulose",
        name="cellulose material density",
        units="kilogram / meter ** 3",
        notes="Density depends on cellulose source, hydration, porosity, and sample preparation.",
    ),
    SubstrateParameterSpec(
        symbol="epsilon_cellulose",
        name="cellulose substrate porosity",
        units="dimensionless",
        notes="Bulk porosity is substrate-preparation specific and is not inferred.",
    ),
    SubstrateParameterSpec(
        symbol="chi_c_cellulose",
        name="cellulose crystallinity fraction",
        units="dimensionless",
        notes="Crystallinity strongly affects accessibility and must be measured for the material.",
    ),
    SubstrateParameterSpec(
        symbol="A_surface_cellulose",
        name="cellulose geometric surface area",
        units="meter ** 2",
        notes="Surface area requires material geometry or measurement.",
    ),
    SubstrateParameterSpec(
        symbol="A_accessible_cellulose",
        name="cellulose accessible bond surface area",
        units="meter ** 2",
        notes="Accessible surface is not equivalent to total geometric surface area.",
    ),
    SubstrateParameterSpec(
        symbol="a_w_min_cellulose",
        name="minimum water activity for cellulose degradation",
        units="dimensionless",
        notes="Water-activity dependence is organism/enzyme/environment specific.",
    ),
)


def cellulose_metadata_assumption() -> Assumption:
    return Assumption(
        name="Cellulose metadata placeholder",
        description=(
            "Cellulose is represented as a solid polysaccharide with "
            "beta-1,4-glycosidic bonds and unresolved physical accessibility."
        ),
        justification=(
            "Stage 9 separates substrate identity from kinetic laws so later "
            "cellulase models can consume measured material properties."
        ),
        known_limitations=(
            "No cellulose hydrolysis rate law, adsorption model, degree of "
            "polymerization, fibril morphology, lignin/hemicellulose embedding, "
            "or enzyme synergy is implemented."
        ),
        source=CELLULOSE_REFERENCE_NOTE,
    )


def default_cellulose_degradation_products() -> tuple[DegradationProduct, ...]:
    return (
        DegradationProduct(
            name="cellobiose",
            formula="C12H22O11",
            assimilable=None,
            notes="Assimilation requires organism-specific transport and metabolism evidence.",
            source=CELLULOSE_REFERENCE_NOTE,
        ),
        DegradationProduct(
            name="glucose",
            formula="C6H12O6",
            assimilable=None,
            notes="Glucose is not assumed assimilable without organism-specific evidence.",
            source=CELLULOSE_REFERENCE_NOTE,
        ),
        DegradationProduct(
            name="cello-oligosaccharides",
            formula=None,
            assimilable=None,
            notes="Product distribution depends on enzyme mixture and substrate morphology.",
            source=CELLULOSE_REFERENCE_NOTE,
        ),
    )


def make_cellulose_parameter_set(
    overrides: Iterable[Parameter] | None = None,
) -> ParameterSet:
    return make_substrate_parameter_set(
        CELLULOSE_PARAMETER_SPECS,
        substrate_name="cellulose",
        stage_notes=(
            "Stage 9 records cellulose physical properties but does not invent values."
        ),
        overrides=overrides,
    )


@dataclass(frozen=True, init=False)
class CelluloseSubstrate(Substrate):
    """Cellulose substrate metadata with placeholder completeness."""

    repeating_unit: str

    def __init__(
        self,
        *,
        parameters: ParameterSet | None = None,
        notes: str = "",
        references: tuple[str, ...] = (CELLULOSE_REFERENCE_NOTE,),
    ) -> None:
        Substrate.__init__(
            self,
            name="cellulose",
            chemical_class="polysaccharide",
            physical_state="solid_biomass",
            bond_types=("beta-1,4-glycosidic",),
            accessible_bonds=("beta-1,4-glycosidic",),
            required_enzyme_classes=(
                "endoglucanase",
                "cellobiohydrolase",
                "beta-glucosidase",
                "lytic polysaccharide monooxygenase",
            ),
            degradation_products=default_cellulose_degradation_products(),
            parameters=parameters or make_cellulose_parameter_set(),
            assumptions=(cellulose_metadata_assumption(),),
            completeness="placeholder",
            default_degradation_model="unknown",
            water_activity_dependence="unknown; no cellulose water-activity response is implemented.",
            notes=notes or "Stage 9 metadata placeholder; no cellulose kinetics are implemented.",
            references=references,
        )
        object.__setattr__(self, "repeating_unit", "C6H10O5")
        self.validate(require_parameter_values=False)

    @property
    def density(self) -> Parameter:
        return self.parameters.get("rho_cellulose")

    @property
    def porosity(self) -> Parameter:
        return self.parameters.get("epsilon_cellulose")

    @property
    def crystallinity(self) -> Parameter:
        return self.parameters.get("chi_c_cellulose")

    @property
    def accessible_surface_area_parameter(self) -> Parameter:
        return self.parameters.get("A_accessible_cellulose")

    def validate(
        self,
        *,
        allow_unsourced_for_testing: bool = False,
        require_parameter_values: bool = False,
    ) -> None:
        validate_substrate_parameter_units(
            self.parameters,
            CELLULOSE_PARAMETER_SPECS,
            substrate_name="cellulose",
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
    "CELLULOSE_PARAMETER_SPECS",
    "CELLULOSE_REFERENCE_NOTE",
    "CelluloseSubstrate",
    "cellulose_metadata_assumption",
    "default_cellulose_degradation_products",
    "make_cellulose_parameter_set",
]
