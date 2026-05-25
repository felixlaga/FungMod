"""Starch substrate metadata.

Stage 9 records starch as an alpha-glucan substrate with unresolved granule,
gelatinization, crystallinity, hydration, and enzyme-accessibility behaviour.
No starch hydrolysis kinetics are implemented in this module.
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

STARCH_REFERENCE_NOTE = (
    "High-level starch alpha-glucan identity and amylolytic enzyme-class "
    "metadata; no numerical material or kinetic parameter values are supplied."
)

STARCH_PARAMETER_SPECS = (
    SubstrateParameterSpec(
        symbol="rho_starch",
        name="starch material density",
        units="kilogram / meter ** 3",
        notes="Density depends on botanical source, hydration, and processing.",
    ),
    SubstrateParameterSpec(
        symbol="epsilon_starch",
        name="starch substrate porosity",
        units="dimensionless",
        notes="Porosity is preparation-specific and is not inferred.",
    ),
    SubstrateParameterSpec(
        symbol="chi_c_starch",
        name="starch crystallinity fraction",
        units="dimensionless",
        notes="Granule crystallinity and gelatinization state require measurement.",
    ),
    SubstrateParameterSpec(
        symbol="A_surface_starch",
        name="starch geometric surface area",
        units="meter ** 2",
        notes="Surface area depends on granule size and processing.",
    ),
    SubstrateParameterSpec(
        symbol="A_accessible_starch",
        name="starch accessible bond surface area",
        units="meter ** 2",
        notes="Accessible alpha-glucan surface is not inferred from total mass.",
    ),
    SubstrateParameterSpec(
        symbol="a_w_min_starch",
        name="minimum water activity for starch degradation",
        units="dimensionless",
        notes="Water-activity dependence is not implemented.",
    ),
)


def starch_metadata_assumption() -> Assumption:
    return Assumption(
        name="Starch metadata placeholder",
        description=(
            "Starch is represented as an alpha-glucan substrate containing "
            "alpha-1,4 and alpha-1,6 glycosidic bonds."
        ),
        justification=(
            "Stage 9 records substrate identity without assuming whether the "
            "material behaves as dissolved starch, swollen granules, or a solid surface."
        ),
        known_limitations=(
            "No gelatinization model, granule morphology, amylose/amylopectin "
            "ratio, enzyme adsorption, or starch hydrolysis kinetics are implemented."
        ),
        source=STARCH_REFERENCE_NOTE,
    )


def default_starch_degradation_products() -> tuple[DegradationProduct, ...]:
    return (
        DegradationProduct(
            name="maltose",
            formula="C12H22O11",
            assimilable=None,
            notes="Assimilation requires organism-specific evidence.",
            source=STARCH_REFERENCE_NOTE,
        ),
        DegradationProduct(
            name="glucose",
            formula="C6H12O6",
            assimilable=None,
            notes="Glucose is not assumed assimilable without organism-specific evidence.",
            source=STARCH_REFERENCE_NOTE,
        ),
        DegradationProduct(
            name="malto-oligosaccharides",
            formula=None,
            assimilable=None,
            notes="Product distribution depends on enzyme mixture and starch state.",
            source=STARCH_REFERENCE_NOTE,
        ),
    )


def make_starch_parameter_set(
    overrides: Iterable[Parameter] | None = None,
) -> ParameterSet:
    return make_substrate_parameter_set(
        STARCH_PARAMETER_SPECS,
        substrate_name="starch",
        stage_notes="Stage 9 records starch physical properties but does not invent values.",
        overrides=overrides,
    )


@dataclass(frozen=True, init=False)
class StarchSubstrate(Substrate):
    """Starch substrate metadata with placeholder completeness."""

    component_polymers: tuple[str, ...]

    def __init__(
        self,
        *,
        parameters: ParameterSet | None = None,
        notes: str = "",
        references: tuple[str, ...] = (STARCH_REFERENCE_NOTE,),
    ) -> None:
        Substrate.__init__(
            self,
            name="starch",
            chemical_class="polysaccharide",
            physical_state="solid_biomass",
            bond_types=("alpha-1,4-glycosidic", "alpha-1,6-glycosidic"),
            accessible_bonds=("alpha-1,4-glycosidic", "alpha-1,6-glycosidic"),
            required_enzyme_classes=(
                "alpha-amylase",
                "glucoamylase",
                "alpha-glucosidase",
                "debranching enzyme",
            ),
            degradation_products=default_starch_degradation_products(),
            parameters=parameters or make_starch_parameter_set(),
            assumptions=(starch_metadata_assumption(),),
            completeness="placeholder",
            default_degradation_model="unknown",
            water_activity_dependence="unknown; no starch water-activity response is implemented.",
            notes=notes or "Stage 9 metadata placeholder; no starch degradation kinetics are implemented.",
            references=references,
        )
        object.__setattr__(self, "component_polymers", ("amylose", "amylopectin"))
        self.validate(require_parameter_values=False)

    @property
    def density(self) -> Parameter:
        return self.parameters.get("rho_starch")

    @property
    def porosity(self) -> Parameter:
        return self.parameters.get("epsilon_starch")

    @property
    def crystallinity(self) -> Parameter:
        return self.parameters.get("chi_c_starch")

    @property
    def accessible_surface_area_parameter(self) -> Parameter:
        return self.parameters.get("A_accessible_starch")

    def validate(
        self,
        *,
        allow_unsourced_for_testing: bool = False,
        require_parameter_values: bool = False,
    ) -> None:
        validate_substrate_parameter_units(
            self.parameters,
            STARCH_PARAMETER_SPECS,
            substrate_name="starch",
        )
        super().validate(
            allow_unsourced_for_testing=allow_unsourced_for_testing,
            require_parameter_values=require_parameter_values,
        )

    def to_dict(self) -> dict[str, object]:
        data = super().to_dict()
        data["component_polymers"] = list(self.component_polymers)
        return data


__all__ = [
    "STARCH_PARAMETER_SPECS",
    "STARCH_REFERENCE_NOTE",
    "StarchSubstrate",
    "default_starch_degradation_products",
    "make_starch_parameter_set",
    "starch_metadata_assumption",
]
