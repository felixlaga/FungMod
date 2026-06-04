from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from fungal_model.registry import load_registry
from fungal_model.screening import assess_modelability


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"

FUNGUS_ID = "sabiork_beta_glucosidase_source"
ENZYME_CLASS = "beta_glucosidase"
SUBSTRATE_ID = "cellobiose"
ENVIRONMENT_ID = "sabiork_reaction_618_selected_conditions"
PROCESS_RECORD_ID = "beta_glucosidase_cellobiose_homogeneous_mm"
PROCESS_TYPE = "homogeneous_michaelis_menten"
SELECTED_ENTRY_ID = "35622"
REACTION_ID = "618"


def test_registry_loads_reaction_618_enzyme_source_record() -> None:
    registry = load_registry(REGISTRY_INDEX)

    source = registry.get_fungus(FUNGUS_ID)

    assert source.name == "SABIO-RK Reaction 618 beta-glucosidase source"
    assert source.enzyme_classes == (ENZYME_CLASS,)
    assert source.assimilable_products == ()
    assert "not a whole-fungus growth model" in source.notes
    _assert_sabiork_provenance(source.provenance)


def test_registry_loads_beta_glucosidase_enzyme_class() -> None:
    registry = load_registry(REGISTRY_INDEX)

    enzyme = registry.get_enzyme_class(ENZYME_CLASS)

    assert enzyme.name == "beta-glucosidase"
    assert enzyme.target_bond_classes == ("beta_1_4_glycosidic",)
    assert enzyme.compatible_substrate_classes == ("cellobiose",)
    assert enzyme.compatible_processes == (PROCESS_TYPE,)
    _assert_sabiork_provenance(enzyme.provenance)


def test_registry_loads_cellobiose_substrate() -> None:
    registry = load_registry(REGISTRY_INDEX)

    substrate = registry.get_substrate(SUBSTRATE_ID)

    assert substrate.name == "Cellobiose"
    assert substrate.substrate_class == "cellobiose"
    assert substrate.physical_state == "dissolved"
    assert substrate.bond_classes == ("beta_1_4_glycosidic",)
    assert substrate.products == ("beta_D_glucose",)
    assert substrate.provenance["kegg_reaction"] == "R00026"
    assert substrate.provenance["metanetx"] == "MNXR146826"
    _assert_sabiork_provenance(substrate.provenance)


def test_registry_loads_selected_conditions() -> None:
    registry = load_registry(REGISTRY_INDEX)

    environment = registry.get_environment(ENVIRONMENT_ID)

    assert environment.name == "SABIO-RK Reaction 618 selected assay conditions"
    assert environment.conditions["temperature"].kind == "exact"
    assert environment.conditions["temperature"].to_quantity().to("kelvin").magnitude == pytest.approx(303.15)
    assert environment.conditions["ph"].kind == "exact"
    assert environment.conditions["ph"].to_quantity().magnitude == pytest.approx(5.0)
    _assert_sabiork_provenance(environment.provenance)


def test_registry_loads_homogeneous_michaelis_menten_compatibility_record() -> None:
    registry = load_registry(REGISTRY_INDEX)

    records = registry.get_process_compatibility(
        enzyme_class=ENZYME_CLASS,
        substrate_class="cellobiose",
        process_type=PROCESS_TYPE,
    )

    assert len(records) == 1
    compatibility = records[0]
    assert compatibility.record_id == PROCESS_RECORD_ID
    assert compatibility.required_parameters == ("Km_cellobiose", "kcat_cellobiose")
    assert compatibility.parameter_roles == {
        "km": "Km_cellobiose",
        "kcat": "kcat_cellobiose",
    }
    assert compatibility.product_map_required
    _assert_sabiork_provenance(compatibility.provenance)


def test_parameter_records_preserve_exact_and_unknown_value_specs(tmp_path: Path) -> None:
    registry = load_registry(REGISTRY_INDEX)
    exact_parameters = {
        record.parameter_symbol: record
        for record in registry.get_parameter_records(process_type=PROCESS_TYPE)
    }

    assert exact_parameters["Km_cellobiose"].value.kind == "exact"
    assert exact_parameters["Km_cellobiose"].value.value == pytest.approx(15.3)
    assert exact_parameters["Km_cellobiose"].value.units == "mM"
    assert exact_parameters["kcat_cellobiose"].value.kind == "exact"
    assert exact_parameters["kcat_cellobiose"].value.value == pytest.approx(0.13)
    assert exact_parameters["kcat_cellobiose"].value.units == "s^(-1)"
    _assert_sabiork_provenance(exact_parameters["Km_cellobiose"].provenance)
    _assert_sabiork_provenance(exact_parameters["kcat_cellobiose"].provenance)

    unknown_registry = _registry_with_unknown_parameter(tmp_path, "kcat_cellobiose")
    unknown = unknown_registry.get_parameter_records(parameter_symbol="kcat_cellobiose")[0]

    assert unknown.value.kind == "unknown"
    assert unknown.value.units == "s^(-1)"
    assert unknown.value.confidence_level == "missing_from_selected_entry"


def test_reaction_618_modelability_is_modelable_when_required_parameters_are_exact() -> None:
    registry = load_registry(REGISTRY_INDEX)

    report = assess_modelability(
        fungus_id=FUNGUS_ID,
        substrate_id=SUBSTRATE_ID,
        environment_id=ENVIRONMENT_ID,
        registry=registry,
        mode="scientific",
    )

    assert report.status == "modelable"
    assert report.required_processes == (PROCESS_TYPE,)
    assert report.required_parameters == ("Km_cellobiose", "kcat_cellobiose")
    assert _has_item(report.known, "parameter", "Km_cellobiose")
    assert _has_item(report.known, "parameter", "kcat_cellobiose")
    assert not report.missing
    assert not report.incompatible


def test_reaction_618_modelability_is_underparameterized_when_required_value_is_unknown(tmp_path: Path) -> None:
    registry = _registry_with_unknown_parameter(tmp_path, "kcat_cellobiose")

    report = assess_modelability(
        fungus_id=FUNGUS_ID,
        substrate_id=SUBSTRATE_ID,
        environment_id=ENVIRONMENT_ID,
        registry=registry,
        mode="scientific",
    )

    assert report.status == "underparameterized"
    assert _has_item(report.missing, "parameter", "kcat_cellobiose")
    assert "Measure or curate kcat_cellobiose" in report.suggested_experiments[0]


def test_reaction_618_provenance_includes_sabiork_reaction_and_selected_entry() -> None:
    registry = load_registry(REGISTRY_INDEX)
    records = [
        registry.get_fungus(FUNGUS_ID),
        registry.get_enzyme_class(ENZYME_CLASS),
        registry.get_substrate(SUBSTRATE_ID),
        registry.get_environment(ENVIRONMENT_ID),
        registry.get_process_compatibility(
            enzyme_class=ENZYME_CLASS,
            substrate_class="cellobiose",
            process_type=PROCESS_TYPE,
        )[0],
        *registry.get_parameter_records(process_type=PROCESS_TYPE),
    ]

    for record in records:
        _assert_sabiork_provenance(record.provenance)


def _registry_with_unknown_parameter(tmp_path: Path, parameter_symbol: str):
    registry_dir = _copy_registry(tmp_path)
    parameters_path = registry_dir / "parameters" / "parameter_records.yml"
    data = _yaml_mapping(parameters_path)
    records = cast(list[dict[str, Any]], data["records"])
    for record in records:
        if record.get("parameter_symbol") == parameter_symbol and record.get("process_type") == PROCESS_TYPE:
            record["value"] = {
                "kind": "unknown",
                "units": record["value"]["units"],
                "source": "SABIO-RK Reaction 618 selected kinetic law",
                "confidence_level": "missing_from_selected_entry",
                "notes": "Parameter required by FungMod but absent in selected SABIO-RK kinetic law.",
            }
            break
    else:
        raise AssertionError(f"Missing parameter record {parameter_symbol}")
    parameters_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return load_registry(registry_dir / "registry_index.yml")


def _copy_registry(tmp_path: Path) -> Path:
    destination = tmp_path / "data_registry"
    shutil.copytree(ROOT / "data_registry", destination)
    return destination


def _yaml_mapping(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return cast(dict[str, Any], data)


def _assert_sabiork_provenance(provenance) -> None:
    assert provenance["source_database"] == "SABIO-RK"
    assert provenance["source_reaction_id"] == REACTION_ID
    assert provenance["selected_kinlaw_entry_id"] == SELECTED_ENTRY_ID


def _has_item(items, item_type: str, item_id: str) -> bool:
    return any(item.item_type == item_type and item.item_id == item_id for item in items)
