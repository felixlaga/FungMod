from __future__ import annotations

import pytest

from fungal_model.core.errors import InvalidMechanismError, MissingParameterError
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.entities import Enzyme
from fungal_model.fungi import EnzymeCapability, EnzymeProfile, Fungus, make_fungal_parameter_set
from fungal_model.fungi.metabolism import ProductAssimilation
from fungal_model.kinetics.surface_kinetics import PETSurfaceHydrolysisRateLaw
from fungal_model.processes import ModelBuilder, ParameterRequirement, Process, ProcessRegistry
from fungal_model.substrates.pet import PETSubstrate, make_pet_parameter_set


def parameter(
    *,
    name: str,
    symbol: str,
    value,
    units: str,
) -> Parameter:
    return Parameter(
        name=name,
        symbol=symbol,
        value=value,
        units=units,
        uncertainty=0.0 if value is not None else None,
        source="Artificial enzyme-compatibility benchmark value; no physical claim.",
        confidence_level="testing",
        notes="Used only to test process compatibility matching.",
        measurement_method="defined benchmark value",
    )


def pet() -> PETSubstrate:
    return PETSubstrate(
        parameters=make_pet_parameter_set(
            [
                parameter(
                    name="PET accessible surface area",
                    symbol="A_accessible",
                    value=0.2,
                    units="meter ** 2",
                )
            ]
        )
    )


def surface_parameters() -> ParameterSet:
    return ParameterSet(
        [
            parameter(name="adsorption constant", symbol="K_ads", value=1.0, units="liter / mole"),
            parameter(
                name="surface catalysis constant",
                symbol="k_surface",
                value=1.0e-6,
                units="kilogram / meter ** 2 / second",
            ),
        ]
    )


def pet_process():
    return PETSurfaceHydrolysisRateLaw(
        pet=pet(),
        enzyme="E",
        pet_mass="PET",
        adsorption_symbol="K_ads",
        surface_rate_symbol="k_surface",
        rate_units="kilogram / second",
        enzyme_units="mole / liter",
    ).as_generic_process(product_state="hydrolysate")


def compatible_enzyme() -> Enzyme:
    return Enzyme(
        name="toy PET-active enzyme",
        enzyme_class="PETase-like hydrolase",
        target_bond_types=("ester",),
        target_substrate_names=("polyethylene terephthalate",),
        source="Artificial PET enzyme compatibility fixture.",
    )


def incompatible_enzyme() -> Enzyme:
    return Enzyme(
        name="toy cellulose enzyme",
        enzyme_class="cellulase",
        target_bond_types=("beta-1,4-glycosidic",),
        target_substrate_classes=("polysaccharide",),
        source="Artificial incompatible enzyme fixture.",
    )


def compatible_fungus(*, uptake: tuple[ProductAssimilation, ...] = ()) -> Fungus:
    return Fungus(
        species_name="Toy PET fungus",
        enzyme_profile=EnzymeProfile(
            capabilities=(
                EnzymeCapability(
                    name="toy PET hydrolase",
                    enzyme_class="PETase-like hydrolase",
                    target_substrate="polyethylene terephthalate",
                    target_bond_type="ester",
                    evidence="Artificial compatibility fixture.",
                    source="Artificial compatibility fixture.",
                ),
            ),
            source="Artificial compatibility fixture.",
        ),
        parameters=make_fungal_parameter_set(),
        uptake_capabilities=uptake,
        references=("Artificial compatibility fixture.",),
    )


def incompatible_fungus() -> Fungus:
    return Fungus(
        species_name="Toy cellulose fungus",
        enzyme_profile=EnzymeProfile(
            capabilities=(
                EnzymeCapability(
                    name="toy cellulase",
                    enzyme_class="cellulase",
                    target_substrate="cellulose",
                    target_bond_type="beta-1,4-glycosidic",
                    evidence="Artificial compatibility fixture.",
                    source="Artificial compatibility fixture.",
                ),
            ),
            source="Artificial compatibility fixture.",
        ),
        parameters=make_fungal_parameter_set(),
        references=("Artificial compatibility fixture.",),
    )


def test_enzyme_entity_matches_pet_metadata() -> None:
    enzyme = compatible_enzyme()

    enzyme.validate()
    assert enzyme.compatible_with_substrate(pet(), bond_type="ester")
    assert not incompatible_enzyme().compatible_with_substrate(pet(), bond_type="ester")


def test_isolated_enzyme_surface_process_assembles_without_fungus() -> None:
    process = pet_process()
    model = ModelBuilder(
        substrates=[pet()],
        enzymes=[compatible_enzyme()],
        process_library=ProcessRegistry([process]),
        requested_processes=("surface_catalysis",),
        parameters=surface_parameters(),
    ).assemble()

    assert model.assembly_report.success
    assert model.context.enzymes[0].name == "toy PET-active enzyme"


def test_incompatible_enzyme_substrate_pairing_fails_assembly() -> None:
    process = pet_process()
    with pytest.raises(InvalidMechanismError) as exc_info:
        ModelBuilder(
            substrates=[pet()],
            enzymes=[incompatible_enzyme()],
            process_library=ProcessRegistry([process]),
            requested_processes=("surface_catalysis",),
            parameters=surface_parameters(),
        ).assemble()

    issue = exc_info.value.report.incompatible_mechanisms[0]
    assert issue.reason == "enzyme_substrate_mismatch"
    assert issue.bond_type == "ester"


def test_fungus_without_compatible_capability_cannot_drive_surface_process() -> None:
    process = pet_process()
    with pytest.raises(InvalidMechanismError) as exc_info:
        ModelBuilder(
            fungus=incompatible_fungus(),
            substrates=[pet()],
            enzymes=[compatible_enzyme()],
            process_library=ProcessRegistry([process]),
            requested_processes=("surface_catalysis",),
            parameters=surface_parameters(),
        ).assemble()

    reasons = {issue.reason for issue in exc_info.value.report.incompatible_mechanisms}
    assert "fungus_lacks_capability" in reasons


def test_fungus_with_compatible_capability_can_assemble_surface_process() -> None:
    process = pet_process()
    model = ModelBuilder(
        fungus=compatible_fungus(),
        substrates=[pet()],
        enzymes=[compatible_enzyme()],
        process_library=ProcessRegistry([process]),
        requested_processes=("surface_catalysis",),
        parameters=surface_parameters(),
    ).assemble()

    assert model.assembly_report.success
    assert model.context.fungus.species_name == "Toy PET fungus"


def test_living_fungus_secretion_process_requires_known_secretion_parameter() -> None:
    process = Process(
        name="enzyme secretion requirement check",
        process_type="enzyme_secretion",
        required_parameters=(
            ParameterRequirement(
                symbol="alpha_E",
                units="mole / liter / kilogram / second",
                name="enzyme secretion coefficient",
            ),
        ),
        source="Artificial secretion assembly fixture.",
    )

    with pytest.raises(MissingParameterError) as exc_info:
        ModelBuilder(
            fungus=compatible_fungus(),
            process_library=ProcessRegistry([process]),
            requested_processes=("enzyme_secretion",),
            parameters=compatible_fungus().parameters,
        ).assemble()

    assert exc_info.value.report.missing_parameters[0].reason == "unknown_value"


def test_fungus_product_uptake_capabilities_are_explicit() -> None:
    fungus = compatible_fungus(
        uptake=(
            ProductAssimilation(
                product="ethylene glycol",
                assimilable=True,
                source="Artificial uptake fixture.",
            ),
            ProductAssimilation(
                product="terephthalic acid",
                assimilable=False,
                source="Artificial uptake fixture.",
            ),
        )
    )

    fungus.validate(allow_unsourced_for_testing=True, require_parameter_values=False)
    assert fungus.can_assimilate_product("ethylene glycol")
    assert not fungus.can_assimilate_product("terephthalic acid")
