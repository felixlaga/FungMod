"""User-supplied enzyme and kinetics tables into virtual experiments (USERDATA-001)."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import shutil
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

import fungal_model
from fungal_model import (
    UserDataError,
    UserDataset,
    VirtualExperiment,
    environment_grid,
    load_user_dataset,
    virtual_experiment,
)
from fungal_model.api import VirtualExperimentError
from fungal_model.api.result_tables import _parameter_source_class, _suggestion_for_missing_item
from fungal_model.core.units import Q_
from fungal_model.provenance import (
    RESERVED_PROVENANCE_KEYS,
    USER_DATASET_PROVENANCE_KEY,
    classify_parameter_provenance,
)
from fungal_model.registry import FungModRegistry, load_registry
from fungal_model.registry.loaders import (
    RegistryRecordType,
    load_parameter_record_mapping,
    load_registry_record_mapping,
)
from fungal_model.registry.records import (
    PARAMETER_ALLOWED_USE_EXPLORATORY,
    PARAMETER_ALLOWED_USE_GAP_ANALYSIS_ONLY,
    PARAMETER_ALLOWED_USE_SCIENTIFIC,
    ParameterRecord,
    parameter_record_mode_eligibility_blocker,
    parameter_simulation_authorization_blocker,
)
from fungal_model.screening import assess_modelability

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_ROOT = ROOT / "data_registry"
REGISTRY_INDEX = REGISTRY_ROOT / "registry_index.yml"
FIXTURES = ROOT / "tests" / "fixtures" / "user_data"
ESTERASE = FIXTURES / "esterase_case"
LITERATURE = FIXTURES / "literature_reentry"

ESTERASE_ID = "esterase_demo"
ESTERASE_FUNGUS = "esterase_demo__strain_e1"
ESTERASE_SUBSTRATE = "esterase_demo__p_nitrophenyl_butyrate"
ESTERASE_ENVIRONMENT = "esterase_demo__c37_ph7_5"
ESTERASE_KCAT_SYMBOL = "esterase_demo__kcat__carboxylesterase__p_nitrophenyl_butyrate"
ESTERASE_SOURCE = "FungMod user-data import fixture; illustrative values, not measurements"

LITERATURE_FUNGUS = "reaction_618_reentry__os3bglu6_source"
LITERATURE_ENVIRONMENT = "reaction_618_reentry__c30_ph5"


@pytest.fixture(scope="module")
def base_registry() -> FungModRegistry:
    return load_registry(REGISTRY_INDEX)


@pytest.fixture(scope="module")
def esterase(base_registry: FungModRegistry) -> UserDataset:
    return load_user_dataset(ESTERASE, registry=base_registry)


@pytest.fixture(scope="module")
def literature(base_registry: FungModRegistry) -> UserDataset:
    return load_user_dataset(LITERATURE, registry=base_registry)


def _records(dataset: UserDataset, record_type: str) -> dict[str, Mapping[str, Any]]:
    return {str(mapping["record_id"]): mapping for mapping in dataset.records[record_type]}


def _parameter(dataset: UserDataset, record_id: str) -> ParameterRecord:
    return load_parameter_record_mapping(_records(dataset, "parameter_records")[record_id])


# ---------------------------------------------------------------------------
# (a) Non-specific esterase case: user-defined class and substrate, estimates only


def test_esterase_dataset_generates_namespaced_production_records(esterase: UserDataset) -> None:
    assert esterase.dataset_id == ESTERASE_ID
    for record_type, mappings in esterase.records.items():
        for mapping in mappings:
            assert str(mapping["record_id"]).startswith(f"{ESTERASE_ID}__"), (record_type, mapping["record_id"])

    enzyme_class = _records(esterase, "enzyme_classes")["esterase_demo__carboxylesterase"]
    assert enzyme_class["target_bond_classes"] == ["carboxylic_ester"]
    assert enzyme_class["compatible_substrate_classes"] == ["aryl_ester"]
    assert enzyme_class["compatible_processes"] == ["homogeneous_michaelis_menten"]
    assert enzyme_class["provenance"]["source"] == ESTERASE_SOURCE

    fungus = _records(esterase, "fungi")[ESTERASE_FUNGUS]
    assert fungus["enzyme_classes"] == ["esterase_demo__carboxylesterase"]
    assert "strain_e1" in fungus["aliases"]

    substrate = _records(esterase, "substrates")[ESTERASE_SUBSTRATE]
    assert substrate["physical_state"] == "dissolved"
    assert substrate["products"] == ["p_nitrophenol"]

    environment = _records(esterase, "environments")[ESTERASE_ENVIRONMENT]
    temperature = environment["conditions"]["temperature"]
    assert temperature["kind"] == "exact"
    assert temperature["units"] == "kelvin"
    assert temperature["value"] == pytest.approx(310.15)
    assert "37 degC" in temperature["notes"]
    assert environment["conditions"]["ph"]["value"] == 7.5
    assert environment["conditions"]["ph"]["units"] == "dimensionless"

    template = _records(esterase, "case_templates")[
        "esterase_demo__carboxylesterase__p_nitrophenyl_butyrate__homogeneous_mm_template"
    ]
    assert template["process_state_metadata"]["config_mode"] == "exploratory"
    assert template["process_state_metadata"]["config_maturity"] == "exploratory"
    assert template["product_map"]["stoichiometric_yield"] == 1.0
    assert template["stoichiometric_yields"] == {"product": 1.0}
    assert template["time_grid"]["stop"] == 60.0
    assert template["time_grid"]["units"] == "minute"
    assert template["time_grid"]["points"] == 61
    assert template["state_roles"] == {
        "substrate": "p_nitrophenyl_butyrate_concentration",
        "product": "p_nitrophenol_concentration",
        "enzyme": "carboxylesterase_concentration",
    }

    parameters = [load_parameter_record_mapping(mapping) for mapping in esterase.records["parameter_records"]]
    assert len(parameters) == 4
    for row, record in enumerate(parameters, start=2):
        assert record.maturity == "exploratory_prior"
        assert record.allowed_use == PARAMETER_ALLOWED_USE_EXPLORATORY
        assert record.provenance["exploratory_prior"] is True
        assert record.value.is_exact
        assert record.fungus_id == ESTERASE_FUNGUS
        assert record.substrate_id == ESTERASE_SUBSTRATE
        assert record.substrate_class == "aryl_ester"
        assert record.environment_id == ESTERASE_ENVIRONMENT
        assert record.enzyme_class == "esterase_demo__carboxylesterase"
        assert record.process_type == "homogeneous_michaelis_menten"
        assert record.parameter_symbol.startswith(f"{ESTERASE_ID}__")
        assert record.provenance["measurement_method"]
        assert "37 degC, pH 7.5" in record.provenance["validity_range"]
        user = record.provenance[USER_DATASET_PROVENANCE_KEY]
        assert user["dataset_id"] == ESTERASE_ID
        assert user["digest"] == esterase.digest
        assert user["file"] == "kinetics.csv"
        assert user["row"] == row
        assert user["evidence_type"] == "estimate"
        assert user["condition_id"] == "c37_ph7_5"
        assert user["source"] == ESTERASE_SOURCE
        assert set(user) >= {"contributor", "method", "sd", "replicates"}
    assert {record.value.units for record in parameters} == {"µM", "1/min"}


def test_esterase_case_runs_in_exploratory_mode_only(
    esterase: UserDataset,
    base_registry: FungModRegistry,
    tmp_path: Path,
) -> None:
    overlaid = esterase.overlay(base_registry)
    assert ESTERASE_FUNGUS in overlaid.fungi
    assert ESTERASE_FUNGUS not in base_registry.fungi
    assert overlaid.provenance["user_dataset_overlays"][-1]["digest"] == esterase.digest

    study = virtual_experiment(
        fungi="Esterase source strain E1",
        substrates="p-nitrophenyl butyrate",
        environments="c37_ph7_5",
        user_data=esterase,
    )
    assert (study.fungus_ids, study.substrate_ids, study.environment_ids) == (
        (ESTERASE_FUNGUS,),
        (ESTERASE_SUBSTRATE,),
        (ESTERASE_ENVIRONMENT,),
    )
    assert study.user_dataset_id == ESTERASE_ID
    assert study.user_dataset_digest == esterase.digest

    exploratory = study.preflight(mode="exploratory")[0]
    assert exploratory.status == "modelable"
    scientific = study.preflight(mode="scientific")[0]
    assert scientific.status != "modelable"
    for mapping in esterase.records["parameter_records"]:
        record = load_parameter_record_mapping(mapping)
        assert parameter_record_mode_eligibility_blocker(record, mode="scientific") is not None
        assert parameter_record_mode_eligibility_blocker(record, mode="exploratory") is None
    with pytest.raises(VirtualExperimentError, match="Scientific simulation requires exact"):
        study.simulate(mode="scientific", output_dir=tmp_path / "blocked", quicklook=False)

    result = study.simulate(mode="exploratory", n_samples=2, seed=5, output_dir=tmp_path / "esterase", quicklook=False)
    rows = result.time_series()
    for sample_id in {row["sample_id"] for row in rows}:
        substrate = [float(row["value"]) for row in rows if row["sample_id"] == sample_id and row["state_role"] == "substrate"]
        product = [float(row["value"]) for row in rows if row["sample_id"] == sample_id and row["state_role"] == "product"]
        assert substrate[0] == pytest.approx(200.0)
        assert substrate[-1] < substrate[0]
        assert all(later <= earlier + 1e-9 for earlier, later in itertools.pairwise(substrate))
        assert product[0] == pytest.approx(0.0)
        assert product[-1] > product[0]
        assert product[-1] == pytest.approx(substrate[0] - substrate[-1], rel=1e-6)

    sampled = result.sampled_parameters()
    assert {row["parameter_source_class"] for row in sampled} == {"user_supplied_exploratory_prior"}
    assert {row["exploratory_prior"] for row in sampled} == {"true"}
    summary = json.loads((Path(result.output_directory) / "virtual_experiment_summary.json").read_text())
    assert summary["experiment"]["user_dataset_id"] == ESTERASE_ID
    assert summary["experiment"]["user_dataset_digest"] == esterase.digest
    manifest = json.loads((Path(result.output_directory) / "output_manifest.json").read_text())
    assert manifest["user_dataset_id"] == ESTERASE_ID
    assert manifest["user_dataset_digest"] == esterase.digest


def test_registry_only_experiments_record_no_user_dataset() -> None:
    study = VirtualExperiment.from_registry(
        fungi="sabiork_beta_glucosidase_source",
        substrates="cellobiose",
        environments="sabiork_reaction_618_selected_conditions",
        registry=REGISTRY_INDEX,
    )

    assert study.user_dataset_id is None
    assert study.to_dict()["user_dataset_id"] is None
    assert study.to_dict()["user_dataset_digest"] is None


def test_user_kinetics_at_environment_grid_conditions_are_labelled_context_without_response_law(
    esterase: UserDataset,
) -> None:
    study = virtual_experiment(
        fungi="strain_e1",
        substrates="p_nitrophenyl_butyrate",
        environments=environment_grid(temperature_C=[30, 37], ph=[7.5]),
        user_data=esterase,
    )

    reports = study.preflight(mode="exploratory")
    assert len(reports) == 2
    copied = [
        record
        for record in study.registry.parameters.values()
        if record.provenance.get("runtime_environment_grid_overlay") and record.fungus_id == ESTERASE_FUNGUS
    ]
    assert len(copied) == 8
    for record in copied:
        assert record.provenance["source_environment_id"] == ESTERASE_ENVIRONMENT
        assert "no pH/temperature response law" in record.notes
        assert record.provenance[USER_DATASET_PROVENANCE_KEY]["digest"] == esterase.digest


# ---------------------------------------------------------------------------
# (b) Gap case: a missing kinetics row becomes an explicit unknown with a request


def test_missing_kcat_row_becomes_gap_with_measurement_request(tmp_path: Path) -> None:
    dataset_dir = _copy_fixture(tmp_path, ESTERASE)
    _drop_rows(dataset_dir / "kinetics.csv", ",kcat,")
    dataset = load_user_dataset(dataset_dir, registry=REGISTRY_INDEX)

    gap = _parameter(dataset, "esterase_demo__strain_e1__carboxylesterase__p_nitrophenyl_butyrate__c37_ph7_5__kcat__gap")
    assert gap.maturity == "user_dataset_gap"
    assert gap.allowed_use == PARAMETER_ALLOWED_USE_GAP_ANALYSIS_ONLY
    assert gap.value.is_unknown
    assert gap.value.units is None
    assert "1/time" in gap.notes
    request = gap.provenance["measurement_request"]
    assert request == (
        "Measure kcat of carboxylesterase from Esterase source strain E1 on p-nitrophenyl butyrate "
        "at 37 degC, pH 7.5 (units of 1/time)."
    )

    study = virtual_experiment(
        fungi="strain_e1",
        substrates="p_nitrophenyl_butyrate",
        environments="c37_ph7_5",
        user_data=dataset,
    )
    report = study.preflight(mode="exploratory")[0]
    assert report.status == "underparameterized"
    assert [item.item_id for item in report.missing] == [ESTERASE_KCAT_SYMBOL]
    assert report.missing[0].details["measurement_request"] == request
    assert request in report.suggested_experiments
    assert _suggestion_for_missing_item(report.missing[0]) == request

    written = study.write_preflight_report(mode="exploratory", output_dir=tmp_path / "preflight")
    assert request in Path(written.paths["modelability_preflight"]).read_text(encoding="utf-8")

    template = _records(dataset, "case_templates")[
        "esterase_demo__carboxylesterase__p_nitrophenyl_butyrate__homogeneous_mm_template"
    ]
    assert template["process_state_metadata"]["config_mode"] == "exploratory"


def test_gap_units_come_only_from_the_case_rows(tmp_path: Path) -> None:
    dataset_dir = _copy_fixture(tmp_path, ESTERASE)
    _drop_rows(dataset_dir / "kinetics.csv", ",km,")
    dataset = load_user_dataset(dataset_dir, registry=REGISTRY_INDEX)

    gap = _parameter(dataset, "esterase_demo__strain_e1__carboxylesterase__p_nitrophenyl_butyrate__c37_ph7_5__km__gap")
    assert gap.value.units == "µM"
    assert gap.provenance["measurement_request"].endswith("at 37 degC, pH 7.5 (µM).")


def test_shipped_registry_preflight_suggestions_are_unchanged(base_registry: FungModRegistry) -> None:
    assert not any("measurement_request" in record.provenance for record in base_registry.parameters.values())
    count = 0
    for fungus_id, substrate_id, environment_id in itertools.product(
        base_registry.fungi,
        base_registry.substrates,
        base_registry.environments,
    ):
        for mode in ("exploratory", "scientific"):
            report = assess_modelability(
                fungus_id=fungus_id,
                substrate_id=substrate_id,
                environment_id=environment_id,
                registry=base_registry,
                mode=mode,
            )
            legacy = tuple(
                dict.fromkeys(
                    f"Measure or curate {item.item_id} for the selected registry case."
                    for item in report.missing
                    if item.item_type == "parameter"
                )
            )
            assert report.suggested_experiments == legacy
            assert all("measurement_request" not in item.details for item in report.missing)
            assert all(
                _suggestion_for_missing_item(item) == f"Measure or curate {item.item_id} for the selected registry case."
                for item in report.missing
                if item.item_type == "parameter"
            )
            count += len(report.suggested_experiments)
    assert count > 0


# ---------------------------------------------------------------------------
# (c) Scientific case: the published Reaction 618 entry re-entered as user data


def test_literature_reentry_matches_the_curated_registry_values(
    literature: UserDataset,
    base_registry: FungModRegistry,
) -> None:
    curated_km = base_registry.parameters["sabiork_reaction_618_Km_cellobiose"].value
    curated_kcat = base_registry.parameters["sabiork_reaction_618_kcat_cellobiose"].value
    prefix = "reaction_618_reentry__os3bglu6_source__beta_glucosidase__cellobiose__c30_ph5__"
    km = _parameter(literature, f"{prefix}km")
    kcat = _parameter(literature, f"{prefix}kcat")

    assert Q_(km.value.value, km.value.units).to(curated_km.units).magnitude == pytest.approx(curated_km.value)
    assert Q_(kcat.value.value, kcat.value.units).to(curated_kcat.units).magnitude == pytest.approx(curated_kcat.value)
    for record in (km, kcat):
        assert record.maturity == "user_reported_literature"
        assert record.allowed_use == PARAMETER_ALLOWED_USE_SCIENTIFIC
        assert "SABIO-RK Reaction 618 selected kinetic law" in str(record.value.source)
        assert "35622" in str(record.value.source)
        assert record.substrate_id == "cellobiose"
        assert record.provenance[USER_DATASET_PROVENANCE_KEY]["evidence_type"] == "literature"
    assert km.provenance[USER_DATASET_PROVENANCE_KEY]["sd"] == 1.2
    for quantity in ("substrate_initial_concentration", "enzyme_concentration"):
        record = _parameter(literature, f"{prefix}{quantity}")
        assert record.maturity == "user_design_value"
        assert record.allowed_use == PARAMETER_ALLOWED_USE_SCIENTIFIC
        assert record.provenance["measurement_method"] == "experimental design"

    enzyme_class = _records(literature, "enzyme_classes")["reaction_618_reentry__beta_glucosidase"]
    parent = base_registry.enzyme_classes["beta_glucosidase"]
    assert enzyme_class["target_bond_classes"] == list(parent.target_bond_classes)
    assert enzyme_class["compatible_substrate_classes"] == list(parent.compatible_substrate_classes)
    assert enzyme_class["ec_number"] == parent.ec_number
    assert enzyme_class["provenance"]["registry_parent_enzyme_class"] == "beta_glucosidase"
    assert "aliases" not in enzyme_class
    assert enzyme_class["compatible_processes"] == ["homogeneous_michaelis_menten"]
    assert not literature.records["substrates"]
    template = _records(literature, "case_templates")[
        "reaction_618_reentry__beta_glucosidase__cellobiose__homogeneous_mm_template"
    ]
    assert template["process_state_metadata"]["config_mode"] == "scientific"
    assert template["process_state_metadata"]["config_maturity"] == "scientific"


def test_literature_reentry_scientific_trajectory_follows_integrated_michaelis_menten(
    literature: UserDataset,
    tmp_path: Path,
) -> None:
    study = virtual_experiment(
        fungi="Os3BGlu6 source",
        substrates="cellobiose",
        environments="c30_ph5",
        user_data=LITERATURE,
    )
    assert study.fungus_ids == (LITERATURE_FUNGUS,)
    assert study.environment_ids == (LITERATURE_ENVIRONMENT,)
    assert study.user_dataset_digest == literature.digest
    assert study.preflight(mode="scientific")[0].status == "modelable"

    result = study.simulate(mode="scientific", output_dir=tmp_path / "reentry", quicklook=False)

    sample = result.screen_result.case_results[0].samples[0]
    settings = json.loads((Path(sample.output_directory) / "solver_settings.json").read_text())["solver_settings"]
    rtol, atol = float(settings["rtol"]), float(settings["atol"])
    parameters = {role: Q_(entry["value"], entry["units"]) for role, entry in sample.parameters.items()}
    km = parameters["km"].to("mM").magnitude
    kcat = parameters["kcat"].to("1/s").magnitude
    enzyme = parameters["enzyme_initial_concentration"].to("mM").magnitude
    s0 = parameters["substrate_initial_concentration"].to("mM").magnitude

    rows = result.time_series()
    by_state: dict[str, list[tuple[float, float]]] = {}
    for row in rows:
        if row["state_role"] in {"substrate", "product", "enzyme"}:
            assert row["units"] == "millimolar"
            seconds = Q_(float(row["time"]), row["time_units"]).to("s").magnitude
            by_state.setdefault(row["state_role"], []).append((seconds, float(row["value"])))
    substrate = by_state["substrate"]
    product = by_state["product"]
    assert len(substrate) == 61
    assert substrate[0][1] == pytest.approx(s0)
    assert substrate[-1][1] < 0.9 * s0
    assert all(value == pytest.approx(enzyme) for _, value in by_state["enzyme"])

    # Local error control bounds each step by atol + rtol * |S|; the allowance
    # below propagates that bound through the integrated relation and admits
    # accumulation over the run (a misread kcat or time unit is off by order 1 mM).
    state_tolerance = 100.0 * (atol + rtol * s0)
    for (time, s_value), (_, p_value) in zip(substrate, product, strict=True):
        residual = km * math.log(s0 / s_value) + (s0 - s_value) - kcat * enzyme * time
        sensitivity = km / s_value + 1.0
        assert abs(residual) <= sensitivity * state_tolerance, (time, residual)
        assert p_value == pytest.approx(2.0 * (s0 - s_value), abs=2.0 * state_tolerance)

    sampled = {row["role"]: row["parameter_source_class"] for row in result.sampled_parameters()}
    assert sampled["km"] == "user_reported_literature_exact_value"
    assert sampled["enzyme_initial_concentration"] == "user_design_value_exact_value"
    assert {row["maturity"] for row in result.mechanism_summary()} == {"software_tested_user_supplied_parameterized"}


def test_overlay_refuses_a_base_registry_whose_referenced_records_changed(
    literature: UserDataset,
    base_registry: FungModRegistry,
) -> None:
    changed = replace(base_registry.enzyme_classes["beta_glucosidase"], target_bond_classes=("beta_1_4_glycosidic", "x"))
    other_base = FungModRegistry.build(
        registry_id=base_registry.registry_id,
        version=base_registry.version,
        maturity=base_registry.maturity,
        provenance=base_registry.provenance,
        fungi=base_registry.fungi.values(),
        enzyme_classes=(changed, *(r for k, r in base_registry.enzyme_classes.items() if k != "beta_glucosidase")),
        substrates=base_registry.substrates.values(),
        environments=base_registry.environments.values(),
        process_compatibility=base_registry.process_compatibility.values(),
        parameters=base_registry.parameters.values(),
        case_templates=base_registry.case_templates.values(),
        product_maps=base_registry.product_maps.values(),
    )

    with pytest.raises(UserDataError, match="beta_glucosidase") as excinfo:
        literature.overlay(other_base)
    assert excinfo.value.issues


# ---------------------------------------------------------------------------
# (d) Validation errors are collected with file, row and column


def _kinetics_text() -> str:
    return (ESTERASE / "kinetics.csv").read_text(encoding="utf-8")


def _km_line() -> str:
    return next(line for line in _kinetics_text().splitlines() if ",km," in line)


VALIDATION_CASES: dict[str, tuple[dict[str, str | None], tuple[str, int | None, str | None, str]]] = {
    "bad_units": (
        {"kinetics.csv": _kinetics_text().replace("150,,,µM", "150,,,microfoo")},
        ("kinetics.csv", 2, "units", "cannot be parsed"),
    ),
    "wrong_dimensionality": (
        {"kinetics.csv": _kinetics_text().replace("30,,,1/min", "30,,,µM")},
        ("kinetics.csv", 3, "units", "1/time"),
    ),
    "molar_versus_mass_km": (
        {"kinetics.csv": _kinetics_text().replace("150,,,µM", "150,,,mg/L")},
        ("kinetics.csv", 2, "units", "molar mass"),
    ),
    "duplicate_row": (
        {"kinetics.csv": _kinetics_text() + _km_line().replace(",150,", ",160,") + "\n"},
        ("kinetics.csv", 6, "quantity", "Rows 2, 6"),
    ),
    "exact_plus_range": (
        {"kinetics.csv": _kinetics_text() + _km_line().replace(",150,,,", ",,100,200,") + "\n"},
        ("kinetics.csv", 6, "quantity", "an exact value and a range"),
    ),
    "registry_collision": (
        {
            "strains.csv": (
                "strain_id,name,scientific_name,aliases\n"
                "strain_e1,beta-glucosidase source,,E1 esterase strain\n"
            )
        },
        ("strains.csv", 2, "name", "collides with registry fungi"),
    ),
    "undeclared_reference": (
        {"kinetics.csv": _kinetics_text().replace("strain_e1,carboxylesterase,p_nitrophenyl_butyrate,c37_ph7_5,km", "strain_x,carboxylesterase,p_nitrophenyl_butyrate,c37_ph7_5,km")},
        ("kinetics.csv", 2, "strain_id", "not declared in strains.csv"),
    ),
    "vmax_row": (
        {"kinetics.csv": _kinetics_text().replace(",kcat,30,,,1/min,", ",vmax,30,,,µM/min,")},
        ("kinetics.csv", 3, "quantity", "needs kcat and an enzyme concentration"),
    ),
    "unsupported_extra_csv": (
        {"responses.csv": "time,value\n0,1\n"},
        ("responses.csv", None, None, "Unsupported table 'responses.csv'"),
    ),
    "missing_time_grid": (
        {
            "user_dataset.yml": (
                "dataset_id: esterase_demo\n"
                "contributor: FungMod maintainers\n"
                f"source: {ESTERASE_SOURCE}\n"
            )
        },
        ("user_dataset.yml", None, "simulation", "no default time grid"),
    ),
    "ph_out_of_range": (
        {"conditions.csv": "condition_id,temperature,temperature_units,ph,notes\nc37_ph7_5,37,degC,15,\n"},
        ("conditions.csv", 2, "ph", "outside 0 to 14"),
    ),
}


@pytest.mark.parametrize("case", sorted(VALIDATION_CASES))
def test_invalid_datasets_report_file_row_and_column(tmp_path: Path, case: str) -> None:
    edits, (file, row, column, message) = VALIDATION_CASES[case]
    dataset_dir = _copy_fixture(tmp_path, ESTERASE, edits=edits)

    with pytest.raises(UserDataError) as excinfo:
        load_user_dataset(dataset_dir, registry=REGISTRY_INDEX)

    issues = excinfo.value.issues
    assert issues
    assert all(set(issue) == {"file", "row", "column", "message"} for issue in issues)
    matching = [
        issue
        for issue in issues
        if issue["file"] == file and issue["row"] == row and issue["column"] == column and message in issue["message"]
    ]
    assert matching, issues


def test_every_issue_is_collected_before_raising(tmp_path: Path) -> None:
    kinetics = (
        _kinetics_text()
        .replace("150,,,µM", "150,,,microfoo")
        .replace(",kcat,30,,,1/min,", ",vmax,30,,,µM/min,")
        .replace(
            "strain_e1,carboxylesterase,p_nitrophenyl_butyrate,c37_ph7_5,enzyme_concentration",
            "strain_x,carboxylesterase,p_nitrophenyl_butyrate,c37_ph7_5,enzyme_concentration",
        )
    )
    dataset_dir = _copy_fixture(
        tmp_path,
        ESTERASE,
        edits={
            "kinetics.csv": kinetics,
            "conditions.csv": "condition_id,temperature,temperature_units,ph,notes\nc37_ph7_5,37,degC,15,\n",
            "responses.csv": "time,value\n0,1\n",
        },
    )

    with pytest.raises(UserDataError) as excinfo:
        load_user_dataset(dataset_dir, registry=REGISTRY_INDEX)

    located = {(issue["file"], issue["row"], issue["column"]) for issue in excinfo.value.issues}
    assert {
        ("kinetics.csv", 2, "units"),
        ("kinetics.csv", 3, "quantity"),
        ("kinetics.csv", 5, "strain_id"),
        ("conditions.csv", 2, "ph"),
        ("responses.csv", None, None),
    } <= located
    assert "kinetics.csv row 2 column units" in str(excinfo.value)


def test_registry_substrate_rows_reference_without_copying(tmp_path: Path) -> None:
    substrates = (
        "substrate_id,registry_substrate,name,substrate_class,physical_state,bond_classes,product,product_yield,"
        "yield_basis,source\n"
        "cellobiose,cellobiose,Cellobiose,,,,beta_D_glucose,2,mol/mol,stated\n"
        "film,cellulose_film_generic,,,,,soluble_cellulose_hydrolysis_product,1,mol/mol,stated\n"
    )
    dataset_dir = _copy_fixture(tmp_path, LITERATURE, edits={"substrates.csv": substrates})

    with pytest.raises(UserDataError) as excinfo:
        load_user_dataset(dataset_dir, registry=REGISTRY_INDEX)

    messages = {(issue["file"], issue["row"], issue["column"]): issue["message"] for issue in excinfo.value.issues}
    assert "must leave" in messages[("substrates.csv", 2, "name")]
    assert "only dissolved substrates" in messages[("substrates.csv", 3, "registry_substrate")]


# ---------------------------------------------------------------------------
# (e) Integrity: registry untouched, production factories, digest, reserved key


def test_registry_files_are_untouched_and_mappings_load_through_production_factories(
    base_registry: FungModRegistry,
    tmp_path: Path,
) -> None:
    before = _tree_digest(REGISTRY_ROOT)
    for fixture in (ESTERASE, LITERATURE):
        dataset = load_user_dataset(fixture, registry=REGISTRY_INDEX)
        overlaid = dataset.overlay(load_registry(REGISTRY_INDEX))
        json.dumps(dataset.to_dict())
        for record_type, mappings in dataset.records.items():
            for mapping in mappings:
                record = load_registry_record_mapping(cast(RegistryRecordType, record_type), mapping)
                assert record.validate().passed
                if record_type == "parameter_records":
                    parameter = load_parameter_record_mapping(mapping)
                    assert parameter == record
                    assert classify_parameter_provenance(parameter.provenance) == "generic"
                    assert parameter_simulation_authorization_blocker(parameter) is None
                    assert parameter.provenance[USER_DATASET_PROVENANCE_KEY]["digest"] == dataset.digest
        for fungus_id in overlaid.fungi:
            if fungus_id.startswith(f"{dataset.dataset_id}__"):
                for environment_id in overlaid.environments:
                    if environment_id.startswith(f"{dataset.dataset_id}__"):
                        for substrate_id in overlaid.substrates:
                            assess_modelability(
                                fungus_id=fungus_id,
                                substrate_id=substrate_id,
                                environment_id=environment_id,
                                registry=overlaid,
                            )
    assert _tree_digest(REGISTRY_ROOT) == before
    assert set(base_registry.fungi) == set(load_registry(REGISTRY_INDEX).fungi)


def test_digest_is_stable_and_changes_with_one_table_byte(tmp_path: Path) -> None:
    first = load_user_dataset(ESTERASE, registry=REGISTRY_INDEX)
    second = load_user_dataset(ESTERASE, registry=REGISTRY_INDEX)
    assert first.digest == second.digest
    assert first.records == second.records
    assert len(first.digest) == 64

    dataset_dir = _copy_fixture(tmp_path, ESTERASE, edits={"kinetics.csv": _kinetics_text().replace(",150,", ",151,")})
    changed = load_user_dataset(dataset_dir, registry=REGISTRY_INDEX)
    assert changed.digest != first.digest
    assert changed.file_digests["kinetics.csv"] != first.file_digests["kinetics.csv"]
    assert changed.file_digests["strains.csv"] == first.file_digests["strains.csv"]


def test_user_dataset_provenance_namespace_is_reserved_for_curator_authoring() -> None:
    assert USER_DATASET_PROVENANCE_KEY == "fungmod_user_dataset"
    assert USER_DATASET_PROVENANCE_KEY in RESERVED_PROVENANCE_KEYS
    assert classify_parameter_provenance({USER_DATASET_PROVENANCE_KEY: {"dataset_id": "x"}}) == "generic"


def test_public_api_exports_user_data_names() -> None:
    import fungal_model.api as api

    for name in ("load_user_dataset", "UserDataset", "UserDataError"):
        assert name in fungal_model.__all__
        assert name in api.__all__
        assert getattr(fungal_model, name) is getattr(api, name)
    assert issubclass(UserDataError, ValueError)


def test_parameter_source_class_labels_user_maturities(literature: UserDataset, esterase: UserDataset) -> None:
    prefix = "reaction_618_reentry__os3bglu6_source__beta_glucosidase__cellobiose__c30_ph5__"
    assert _parameter_source_class(_parameter(literature, f"{prefix}km")) == "user_reported_literature_exact_value"
    ranged = replace(
        _parameter(literature, f"{prefix}km"),
        value=replace(_parameter(literature, f"{prefix}km").value, kind="range", value=None, lower=10.0, upper=20.0),
    )
    assert _parameter_source_class(ranged) == "user_reported_literature_range"
    estimate = load_parameter_record_mapping(esterase.records["parameter_records"][0])
    assert _parameter_source_class(estimate) == "user_supplied_exploratory_prior"


# ---------------------------------------------------------------------------
# Helpers


def _copy_fixture(tmp_path: Path, source: Path, *, edits: Mapping[str, str | None] | None = None) -> Path:
    target = tmp_path / source.name
    shutil.copytree(source, target)
    for name, text in (edits or {}).items():
        path = target / name
        if text is None:
            path.unlink()
        else:
            path.write_text(text, encoding="utf-8")
    return target


def _drop_rows(path: Path, marker: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    path.write_text("".join(line for line in lines if marker not in line), encoding="utf-8")


def _tree_digest(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
