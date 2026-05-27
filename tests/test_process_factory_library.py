from __future__ import annotations

from pathlib import Path

import pytest

from fungal_model import load_model_config, load_product_map
from fungal_model.core.errors import InvalidMechanismError
from fungal_model.io import ProcessConfig
from fungal_model.processes import (
    FirstOrderDecayProcess,
    FirstOrderFactory,
    HomogeneousMichaelisMentenProcess,
    MassActionFactory,
    ProcessBuildContext,
    ProcessLibrary,
    SurfaceCatalysisFactory,
    SurfaceCatalysisProcess,
)


ROOT = Path(__file__).resolve().parents[1]
MODEL_CONFIGS = ROOT / "data" / "model_configs"


def _state_units(config) -> dict[str, str]:
    return {
        name: str(value["units"])
        for name, value in config.initial_state.states.items()
    }


def _product_maps(config) -> dict[str, object]:
    maps = {}
    for reference in config.entities.product_maps:
        maps[reference.id] = load_product_map(ROOT / reference.path)
    return maps


def _context(config) -> ProcessBuildContext:
    return ProcessBuildContext(
        state_units=_state_units(config),
        product_maps=_product_maps(config),
        source=f"Factory test context for {config.name}.",
    )


def test_default_foundation_library_registers_expected_factories() -> None:
    library = ProcessLibrary.default_foundation()

    assert set(library.factory_types()) == {
        "first_order",
        "mass_action",
        "homogeneous_michaelis_menten",
        "surface_catalysis",
    }


def test_duplicate_factory_registration_fails() -> None:
    library = ProcessLibrary()
    library.register_factory(FirstOrderFactory())

    with pytest.raises(InvalidMechanismError, match="Duplicate process factory"):
        library.register_factory(FirstOrderFactory())


def test_unknown_process_type_fails_structurally() -> None:
    library = ProcessLibrary.default_foundation()

    with pytest.raises(InvalidMechanismError, match="No process factory registered"):
        library.factory_for("not_a_process")


def test_first_order_factory_builds_homogeneous_config_process() -> None:
    config = load_model_config(MODEL_CONFIGS / "toy_homogeneous_ab.yml")
    library = ProcessLibrary.default_foundation()

    processes = library.build_processes(_context(config), config.processes)

    assert len(processes) == 1
    process = processes[0]
    assert isinstance(process, FirstOrderDecayProcess)
    assert process.substrate_state == "dissolved_substrate_amount"
    assert process.product_state == "released_product_amount"
    assert process.rate_constant_symbol == "k_ab"


def test_surface_factory_builds_pet_plugin_and_non_pet_configs_with_same_factory() -> None:
    library = ProcessLibrary.default_foundation()
    plugin_config = load_model_config(MODEL_CONFIGS / "toy_surface_pet_plugin.yml")
    dummy_config = load_model_config(MODEL_CONFIGS / "toy_surface_dummy_non_pet.yml")

    plugin_process = library.build_processes(_context(plugin_config), plugin_config.processes)[0]
    dummy_process = library.build_processes(_context(dummy_config), dummy_config.processes)[0]

    assert isinstance(plugin_process, SurfaceCatalysisProcess)
    assert isinstance(dummy_process, SurfaceCatalysisProcess)
    assert plugin_process.substrate_state == "solid_polymer_amount"
    assert dummy_process.substrate_state == "solid_substrate_amount"
    assert plugin_process.product_release_map.products == {"released_product_amount": 1.0}
    assert dummy_process.product_release_map.products == {"released_product_amount": 1.0}


def test_surface_factory_reports_missing_product_map() -> None:
    config = load_model_config(MODEL_CONFIGS / "toy_surface_dummy_non_pet.yml")
    context = ProcessBuildContext(state_units=_state_units(config), product_maps={})
    factory = SurfaceCatalysisFactory()

    decision = factory.can_build(context, config.processes[0])

    assert not decision.can_build
    assert "missing_fields" in decision.reasons
    assert "product_maps.dummy_release_map" in decision.missing_fields


def test_missing_state_unit_fails_in_build_decision() -> None:
    config = load_model_config(MODEL_CONFIGS / "toy_homogeneous_ab.yml")
    context = ProcessBuildContext(state_units={}, product_maps={})

    decision = FirstOrderFactory().can_build(context, config.processes[0])

    assert not decision.can_build
    assert "state_units.dissolved_substrate_amount" in decision.missing_fields


def test_mass_action_factory_builds_generic_process_from_config() -> None:
    process_config = ProcessConfig.from_mapping(
        {
            "id": "generic_mass_action",
            "process_type": "mass_action",
            "states": {
                "reactants": {"A": 1.0, "B": 1.0},
                "products": {"C": 1.0},
            },
            "parameters": {
                "rate_constant": "k_ab",
                "rate_constant_units": "liter / mole / second",
                "rate_units": "mole / liter / second",
            },
        }
    )
    context = ProcessBuildContext(
        state_units={
            "A": "mole / liter",
            "B": "mole / liter",
            "C": "mole / liter",
        }
    )

    process = MassActionFactory().build(context, process_config)

    assert process.process_type == "mass_action"
    assert process.rate_constant_symbol == "k_ab"


def test_homogeneous_michaelis_menten_factory_builds_generic_process() -> None:
    process_config = ProcessConfig.from_mapping(
        {
            "id": "generic_mm",
            "process_type": "homogeneous_michaelis_menten",
            "states": {
                "substrate": "S",
                "product": "P",
            },
            "parameters": {
                "km": "Km",
                "vmax": "Vmax",
                "rate_units": "mole / liter / second",
            },
        }
    )
    context = ProcessBuildContext(
        state_units={
            "S": "mole / liter",
            "P": "mole / liter",
        }
    )

    process = ProcessLibrary.default_foundation().build_processes(context, (process_config,))[0]

    assert isinstance(process, HomogeneousMichaelisMentenProcess)
    assert process.km_symbol == "Km"
    assert process.vmax_symbol == "Vmax"


def test_factory_module_has_no_plugin_imports_or_domain_names() -> None:
    source = (ROOT / "src" / "fungal_model" / "processes" / "factories.py").read_text(encoding="utf-8")

    assert "PET" not in source
    assert "petase" not in source.lower()
    assert "substrates.pet" not in source
