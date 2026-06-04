from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from fungal_model.io.model_config import ModelConfig
from fungal_model.registry import load_registry
from fungal_model.screening import (
    RegistryCaseBuildError,
    assess_modelability,
    build_model_config_from_registry_case,
)
from fungal_model.workflows import run_configured_model


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
ENZYME_CONCENTRATION_SYMBOL = "enzyme_concentration_beta_glucosidase"


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
    assert compatibility.required_parameters == (
        "Km_cellobiose",
        "kcat_cellobiose",
        "initial_cellobiose_concentration",
        ENZYME_CONCENTRATION_SYMBOL,
    )
    assert compatibility.parameter_roles == {
        "km": "Km_cellobiose",
        "kcat": "kcat_cellobiose",
        "substrate_initial_concentration": "initial_cellobiose_concentration",
        "enzyme_initial_concentration": ENZYME_CONCENTRATION_SYMBOL,
    }
    assert compatibility.product_map_required
    _assert_sabiork_provenance(compatibility.provenance)


def test_parameter_records_preserve_exact_and_unknown_value_specs(tmp_path: Path) -> None:
    registry = load_registry(REGISTRY_INDEX)
    parameter_records = registry.get_parameter_records(process_type=PROCESS_TYPE)
    exact_parameters = {
        record.parameter_symbol: record
        for record in parameter_records
        if record.maturity == "literature_processed"
    }
    km_range_record = _parameter_record(
        parameter_records,
        symbol="Km_cellobiose",
        maturity="literature_range",
    )
    kcat_range_record = _parameter_record(
        parameter_records,
        symbol="kcat_cellobiose",
        maturity="literature_range",
    )
    unknown_enzyme_record = _parameter_record(
        parameter_records,
        symbol=ENZYME_CONCENTRATION_SYMBOL,
        maturity="literature_processed",
    )
    exploratory_enzyme_record = _parameter_record(
        parameter_records,
        symbol=ENZYME_CONCENTRATION_SYMBOL,
        maturity="exploratory_prior",
    )

    assert exact_parameters["Km_cellobiose"].value.kind == "exact"
    assert exact_parameters["Km_cellobiose"].value.value == pytest.approx(15.3)
    assert exact_parameters["Km_cellobiose"].value.units == "mM"
    assert exact_parameters["kcat_cellobiose"].value.kind == "exact"
    assert exact_parameters["kcat_cellobiose"].value.value == pytest.approx(0.13)
    assert exact_parameters["kcat_cellobiose"].value.units == "s^(-1)"
    assert km_range_record.value.kind == "range"
    assert km_range_record.value.lower == pytest.approx(0.68)
    assert km_range_record.value.upper == pytest.approx(114.0)
    assert km_range_record.value.units == "mM"
    assert km_range_record.value.confidence_level == "literature_range"
    assert kcat_range_record.value.kind == "range"
    assert kcat_range_record.value.lower == pytest.approx(0.13)
    assert kcat_range_record.value.upper == pytest.approx(7.17)
    assert kcat_range_record.value.units == "s^(-1)"
    assert kcat_range_record.value.confidence_level == "literature_range"
    assert exact_parameters["initial_cellobiose_concentration"].value.kind == "exact"
    assert exact_parameters["initial_cellobiose_concentration"].value.value == pytest.approx(3.06)
    assert exact_parameters["initial_cellobiose_concentration"].value.units == "mM"
    assert unknown_enzyme_record.value.kind == "unknown"
    assert unknown_enzyme_record.value.units == "mM"
    assert unknown_enzyme_record.value.confidence_level == "missing_from_selected_entry"
    assert exploratory_enzyme_record.value.kind == "distribution"
    assert exploratory_enzyme_record.value.distribution == "loguniform"
    assert exploratory_enzyme_record.value.parameters["lower"] == pytest.approx(1.0e-6)
    assert exploratory_enzyme_record.value.parameters["upper"] == pytest.approx(1.0e-3)
    assert exploratory_enzyme_record.value.units == "mM"
    assert exploratory_enzyme_record.value.source == "user-supplied exploratory range"
    assert exploratory_enzyme_record.value.confidence_level == "exploratory_assumption"
    assert exploratory_enzyme_record.provenance["exploratory_prior"] is True
    _assert_sabiork_provenance(exact_parameters["Km_cellobiose"].provenance)
    _assert_sabiork_provenance(exact_parameters["kcat_cellobiose"].provenance)
    _assert_sabiork_range_provenance(km_range_record.provenance)
    _assert_sabiork_range_provenance(kcat_range_record.provenance)
    _assert_sabiork_provenance(exact_parameters["initial_cellobiose_concentration"].provenance)
    _assert_sabiork_provenance(unknown_enzyme_record.provenance)
    _assert_sabiork_provenance(exploratory_enzyme_record.provenance)

    unknown_registry = _registry_with_parameter_values(
        tmp_path,
        {
            "kcat_cellobiose": {
                "kind": "unknown",
                "units": "s^(-1)",
                "source": "SABIO-RK Reaction 618 selected kinetic law",
                "confidence_level": "missing_from_selected_entry",
                "notes": "Parameter required by FungMod but absent in selected SABIO-RK kinetic law.",
            }
        },
    )
    unknown = unknown_registry.get_parameter_records(parameter_symbol="kcat_cellobiose")[0]

    assert unknown.value.kind == "unknown"
    assert unknown.value.units == "s^(-1)"
    assert unknown.value.confidence_level == "missing_from_selected_entry"


def test_reaction_618_modelability_is_underparameterized_when_enzyme_concentration_is_unknown() -> None:
    registry = load_registry(REGISTRY_INDEX)

    report = assess_modelability(
        fungus_id=FUNGUS_ID,
        substrate_id=SUBSTRATE_ID,
        environment_id=ENVIRONMENT_ID,
        registry=registry,
        mode="scientific",
    )

    assert report.status == "underparameterized"
    assert report.required_processes == (PROCESS_TYPE,)
    assert report.required_parameters == (
        "Km_cellobiose",
        "kcat_cellobiose",
        "initial_cellobiose_concentration",
        ENZYME_CONCENTRATION_SYMBOL,
    )
    assert _has_item(report.known, "parameter", "Km_cellobiose")
    assert _has_item(report.known, "parameter", "kcat_cellobiose")
    assert _has_item(report.known, "parameter", "initial_cellobiose_concentration")
    assert _has_item(report.missing, "parameter", ENZYME_CONCENTRATION_SYMBOL)
    assert not report.incompatible


def test_reaction_618_exploratory_modelability_uses_marked_prior_only_in_exploratory_mode() -> None:
    registry = load_registry(REGISTRY_INDEX)

    report = assess_modelability(
        fungus_id=FUNGUS_ID,
        substrate_id=SUBSTRATE_ID,
        environment_id=ENVIRONMENT_ID,
        registry=registry,
        mode="exploratory",
    )

    assert report.status == "exploratory"
    assert _has_item(report.uncertain, "parameter", ENZYME_CONCENTRATION_SYMBOL)
    assert not _has_item(report.missing, "parameter", ENZYME_CONCENTRATION_SYMBOL)
    enzyme_item = next(
        item for item in report.uncertain if item.item_id == ENZYME_CONCENTRATION_SYMBOL
    )
    assert (
        enzyme_item.details["record_id"]
        == "exploratory_reaction_618_enzyme_concentration_beta_glucosidase_loguniform"
    )
    assert enzyme_item.details["value"]["confidence_level"] == "exploratory_assumption"


def test_reaction_618_modelability_is_modelable_when_required_values_are_exact(tmp_path: Path) -> None:
    registry = _registry_with_exact_enzyme_concentration(tmp_path)

    report = assess_modelability(
        fungus_id=FUNGUS_ID,
        substrate_id=SUBSTRATE_ID,
        environment_id=ENVIRONMENT_ID,
        registry=registry,
        mode="scientific",
    )

    assert report.status == "modelable"
    assert _has_item(report.known, "parameter", ENZYME_CONCENTRATION_SYMBOL)
    assert not report.missing
    assert not report.incompatible


def test_reaction_618_modelability_is_underparameterized_when_required_value_is_unknown(tmp_path: Path) -> None:
    registry = _registry_with_parameter_values(
        tmp_path,
        {
            ENZYME_CONCENTRATION_SYMBOL: _exact_enzyme_concentration_value(),
            "kcat_cellobiose": {
                "kind": "unknown",
                "units": "s^(-1)",
                "source": "SABIO-RK Reaction 618 selected kinetic law",
                "confidence_level": "missing_from_selected_entry",
                "notes": "Parameter required by FungMod but absent in selected SABIO-RK kinetic law.",
            },
        },
    )

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


def test_builder_refuses_default_reaction_618_when_enzyme_concentration_is_unknown() -> None:
    registry = load_registry(REGISTRY_INDEX)

    with pytest.raises(RegistryCaseBuildError, match=ENZYME_CONCENTRATION_SYMBOL):
        build_model_config_from_registry_case(
            fungus_id=FUNGUS_ID,
            substrate_id=SUBSTRATE_ID,
            environment_id=ENVIRONMENT_ID,
            registry=registry,
            mode="scientific",
        )


def test_builder_emits_valid_homogeneous_michaelis_menten_config_when_required_values_are_exact(
    tmp_path: Path,
) -> None:
    registry = _registry_with_exact_enzyme_concentration(tmp_path)

    config = build_model_config_from_registry_case(
        fungus_id=FUNGUS_ID,
        substrate_id=SUBSTRATE_ID,
        environment_id=ENVIRONMENT_ID,
        registry=registry,
        mode="scientific",
        output_directory=str(tmp_path / "outputs"),
    )

    assert isinstance(config, ModelConfig)
    assert config.mode == "scientific"
    assert config.maturity == "scientific"
    assert config.validate().passed
    process = config.processes[0]
    assert process.process_type == PROCESS_TYPE
    assert process.parameters["km"] == "Km_cellobiose"
    assert process.parameters["kcat"] == "kcat_cellobiose"
    assert process.parameters["rate_units"] == "mM / second"
    _assert_sabiork_provenance(config.to_dict()["provenance"])


def test_built_homogeneous_michaelis_menten_config_runs_and_preserves_sabiork_metadata(
    tmp_path: Path,
) -> None:
    registry = _registry_with_exact_enzyme_concentration(tmp_path)
    config = build_model_config_from_registry_case(
        fungus_id=FUNGUS_ID,
        substrate_id=SUBSTRATE_ID,
        environment_id=ENVIRONMENT_ID,
        registry=registry,
        mode="scientific",
        output_directory=str(tmp_path / "outputs"),
    )
    config_path = tmp_path / "sabiork_reaction_618_config.yml"
    config_path.write_text(yaml.safe_dump(config.to_dict(), sort_keys=False), encoding="utf-8")

    result = run_configured_model(config_path, output_dir=tmp_path / "bundle")

    substrate = result.state("cellobiose_concentration").to("mM").magnitude
    product = result.state("beta_D_glucose_concentration").to("mM").magnitude
    assert substrate[-1] < substrate[0]
    assert product[-1] > product[0]
    metadata = json.loads((tmp_path / "bundle" / "configured_metadata.json").read_text(encoding="utf-8"))
    _assert_sabiork_provenance(metadata["provenance"])
    assert metadata["provenance"]["parameter_record_ids"]["km"] == "sabiork_reaction_618_Km_cellobiose"


@pytest.mark.parametrize(
    "value_spec",
    [
        {
            "kind": "range",
            "lower": 10.0,
            "upper": 20.0,
            "units": "mM",
            "source": "SABIO-RK Reaction 618 selected kinetic law",
            "confidence_level": "literature_curated",
            "notes": "Local range fixture for deterministic-builder refusal.",
        },
        {
            "kind": "distribution",
            "distribution": "uniform",
            "parameters": {"lower": 10.0, "upper": 20.0},
            "units": "mM",
            "source": "SABIO-RK Reaction 618 selected kinetic law",
            "confidence_level": "literature_curated",
            "notes": "Local distribution fixture for deterministic-builder refusal.",
        },
    ],
)
def test_deterministic_builder_refuses_uncertain_required_parameters(
    tmp_path: Path,
    value_spec: dict[str, Any],
) -> None:
    registry = _registry_with_parameter_values(
        tmp_path,
        {
            ENZYME_CONCENTRATION_SYMBOL: _exact_enzyme_concentration_value(),
            "Km_cellobiose": value_spec,
        },
    )

    with pytest.raises(RegistryCaseBuildError, match="modelability status"):
        build_model_config_from_registry_case(
            fungus_id=FUNGUS_ID,
            substrate_id=SUBSTRATE_ID,
            environment_id=ENVIRONMENT_ID,
            registry=registry,
            mode="scientific",
        )


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
        if record.maturity == "literature_range":
            _assert_sabiork_range_provenance(record.provenance)
        else:
            _assert_sabiork_provenance(record.provenance)


def _registry_with_exact_enzyme_concentration(tmp_path: Path):
    return _registry_with_parameter_values(
        tmp_path,
        {ENZYME_CONCENTRATION_SYMBOL: _exact_enzyme_concentration_value()},
    )


def _registry_with_parameter_values(tmp_path: Path, values_by_symbol: dict[str, dict[str, Any]]):
    registry_dir = _copy_registry(tmp_path)
    parameters_path = registry_dir / "parameters" / "parameter_records.yml"
    data = _yaml_mapping(parameters_path)
    records = cast(list[dict[str, Any]], data["records"])
    missing = set(values_by_symbol)
    for record in records:
        symbol = record.get("parameter_symbol")
        if symbol in values_by_symbol and record.get("process_type") == PROCESS_TYPE:
            record["value"] = values_by_symbol[str(symbol)]
            missing.discard(str(symbol))
    if missing:
        raise AssertionError(f"Missing parameter record(s): {sorted(missing)}")
    parameters_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return load_registry(registry_dir / "registry_index.yml")


def _exact_enzyme_concentration_value() -> dict[str, Any]:
    return {
        "kind": "exact",
        "value": 0.01,
        "units": "mM",
        "source": "Local deterministic enzyme concentration fixture",
        "confidence_level": "synthetic_control",
        "notes": "Used only to exercise homogeneous builder mechanics; not a SABIO-RK value.",
    }


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


def _assert_sabiork_range_provenance(provenance) -> None:
    assert provenance["source_database"] == "SABIO-RK"
    assert provenance["source_reaction_id"] == REACTION_ID
    assert "parameter_range_report" in provenance
    assert len(provenance["included_kinlaw_entry_ids"]) == 15
    assert SELECTED_ENTRY_ID in provenance["included_kinlaw_entry_ids"]


def _parameter_record(records, *, symbol: str, maturity: str):
    for record in records:
        if record.parameter_symbol == symbol and record.maturity == maturity:
            return record
    raise AssertionError(f"Missing parameter record for {symbol!r} with maturity {maturity!r}")


def _has_item(items, item_type: str, item_id: str) -> bool:
    return any(item.item_type == item_type and item.item_id == item_id for item in items)
