"""Lignin substrate metadata.

Lignin is recorded as a chemically heterogeneous aromatic polymer. Stage 9 only
defines identity, bond/product classes, enzyme-class requirements, and unknown
physical parameters. No redox chemistry, radical transport, mediator chemistry,
or lignocellulose architecture is implemented here.
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

LIGNIN_REFERENCE_NOTE = (
    "High-level lignin aromatic-polymer identity and ligninolytic enzyme-class "
    "metadata; no numerical material, thermodynamic, or kinetic values are supplied."
)

LIGNIN_PARAMETER_SPECS = (
    SubstrateParameterSpec(
        symbol="rho_lignin",
        name="lignin material density",
        units="kilogram / meter ** 3",
        notes="Density depends on lignin source, isolation method, hydration, and matrix context.",
    ),
    SubstrateParameterSpec(
        symbol="epsilon_lignin",
        name="lignin-containing substrate porosity",
        units="dimensionless",
        notes="Porosity is a bulk material property and is not inferred from lignin identity.",
    ),
    SubstrateParameterSpec(
        symbol="chi_order_lignin",
        name="lignin ordered or crystalline fraction",
        units="dimensionless",
        notes=(
            "Native lignin is not treated as a simple crystalline polymer; this "
            "placeholder records any measured ordered fraction only if supplied."
        ),
    ),
    SubstrateParameterSpec(
        symbol="A_surface_lignin",
        name="lignin-containing substrate geometric surface area",
        units="meter ** 2",
        notes="Surface area depends on matrix geometry and pretreatment.",
    ),
    SubstrateParameterSpec(
        symbol="A_accessible_lignin",
        name="lignin accessible reactive surface area",
        units="meter ** 2",
        notes="Accessible lignin surface requires material-specific measurement or derivation.",
    ),
    SubstrateParameterSpec(
        symbol="a_w_min_lignin",
        name="minimum water activity for lignin degradation",
        units="dimensionless",
        notes="Water and oxygen/redox dependence are not modelled in this placeholder.",
    ),
)


def lignin_metadata_assumption() -> Assumption:
    return Assumption(
        name="Lignin metadata placeholder",
        description=(
            "Lignin is represented as a heterogeneous aromatic polymer with "
            "aryl ether and carbon-carbon bond classes."
        ),
        justification=(
            "Stage 9 needs a substrate interface that can later host redox and "
            "thermodynamic lignin chemistry without inventing kinetics now."
        ),
        known_limitations=(
            "No bond-frequency distribution, mediator chemistry, oxygen/redox "
            "balance, radical reactions, enzyme adsorption, or lignocellulose "
            "matrix coupling is implemented."
        ),
        source=LIGNIN_REFERENCE_NOTE,
    )


def default_lignin_degradation_products() -> tuple[DegradationProduct, ...]:
    return (
        DegradationProduct(
            name="aromatic oligomers",
            formula=None,
            assimilable=None,
            notes="Oligomer composition depends on lignin source and oxidative chemistry.",
            source=LIGNIN_REFERENCE_NOTE,
        ),
        DegradationProduct(
            name="phenolic monomers",
            formula=None,
            assimilable=None,
            notes="No organism-specific uptake or catabolism is assumed.",
            source=LIGNIN_REFERENCE_NOTE,
        ),
        DegradationProduct(
            name="organic acids",
            formula=None,
            assimilable=None,
            notes="Product identities require explicit reaction chemistry.",
            source=LIGNIN_REFERENCE_NOTE,
        ),
    )


def make_lignin_parameter_set(
    overrides: Iterable[Parameter] | None = None,
) -> ParameterSet:
    return make_substrate_parameter_set(
        LIGNIN_PARAMETER_SPECS,
        substrate_name="lignin",
        stage_notes="Stage 9 records lignin physical properties but does not invent values.",
        overrides=overrides,
    )


@dataclass(frozen=True, init=False)
class LigninSubstrate(Substrate):
    """Lignin substrate metadata with placeholder completeness."""

    structural_units: tuple[str, ...]

    def __init__(
        self,
        *,
        parameters: ParameterSet | None = None,
        notes: str = "",
        references: tuple[str, ...] = (LIGNIN_REFERENCE_NOTE,),
    ) -> None:
        Substrate.__init__(
            self,
            name="lignin",
            chemical_class="aromatic heteropolymer",
            physical_state="solid_biomass",
            bond_types=(
                "beta-O-4 aryl ether",
                "alpha-O-4 aryl ether",
                "beta-5 carbon-carbon",
                "beta-beta carbon-carbon",
            ),
            accessible_bonds=(
                "accessible aryl ether",
                "accessible aromatic carbon-carbon",
            ),
            required_enzyme_classes=(
                "laccase",
                "lignin peroxidase",
                "manganese peroxidase",
                "versatile peroxidase",
                "auxiliary redox enzyme",
            ),
            degradation_products=default_lignin_degradation_products(),
            parameters=parameters or make_lignin_parameter_set(),
            assumptions=(lignin_metadata_assumption(),),
            completeness="placeholder",
            default_degradation_model="unknown",
            water_activity_dependence=(
                "unknown; lignin oxidation also requires explicit oxygen/redox handling."
            ),
            notes=notes or "Stage 9 metadata placeholder; no lignin degradation kinetics are implemented.",
            references=references,
        )
        object.__setattr__(
            self,
            "structural_units",
            ("p-hydroxyphenyl", "guaiacyl", "syringyl"),
        )
        self.validate(require_parameter_values=False)

    @property
    def density(self) -> Parameter:
        return self.parameters.get("rho_lignin")

    @property
    def porosity(self) -> Parameter:
        return self.parameters.get("epsilon_lignin")

    @property
    def ordered_fraction(self) -> Parameter:
        return self.parameters.get("chi_order_lignin")

    @property
    def accessible_surface_area_parameter(self) -> Parameter:
        return self.parameters.get("A_accessible_lignin")

    def validate(
        self,
        *,
        allow_unsourced_for_testing: bool = False,
        require_parameter_values: bool = False,
    ) -> None:
        validate_substrate_parameter_units(
            self.parameters,
            LIGNIN_PARAMETER_SPECS,
            substrate_name="lignin",
        )
        super().validate(
            allow_unsourced_for_testing=allow_unsourced_for_testing,
            require_parameter_values=require_parameter_values,
        )

    def to_dict(self) -> dict[str, object]:
        data = super().to_dict()
        data["structural_units"] = list(self.structural_units)
        return data


__all__ = [
    "LIGNIN_PARAMETER_SPECS",
    "LIGNIN_REFERENCE_NOTE",
    "LigninSubstrate",
    "default_lignin_degradation_products",
    "lignin_metadata_assumption",
    "make_lignin_parameter_set",
]
