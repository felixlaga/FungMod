"""First whole-organism registry case: T. harzianum P49P11 on particulate cellulose.

The registry case composes generic process laws through the ``culture_physiology``
template and binds the retrospectively calibrated Gelain 2020 hydrolysis candidate.
These tests pin three facts: the case is exact and modelable in scientific mode,
the assembled configured model reproduces the frozen research implementation of
the same candidate, and the public ``VirtualExperiment`` path writes biomass,
enzyme-activity and substrate trajectories for every culture condition.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
import yaml

from fungal_model import VirtualExperiment
from fungal_model.api import VirtualExperimentError
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.registry import load_registry
from fungal_model.research.gelain_culture import CultureDesign
from fungal_model.research.gelain_models import simulate_candidate
from fungal_model.screening import (
    RegistryCaseBuildError,
    assess_modelability,
    build_model_config_from_registry_case,
)
from fungal_model.solvers.compiled import NEGATIVE_STATE_POLICY
from fungal_model.workflows import run_configured_model

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"
FIT_ARTIFACT = ROOT / "data" / "benchmarks" / "gelain_2020_v2" / "results" / "full_fits" / "cellulose_hydrolysis_primary.json"

FUNGUS_ID = "trichoderma_harzianum_p49p11"
SUBSTRATE_ID = "cellulose_celufloc_200"
ENVIRONMENT_IDS = tuple(f"gelain_2020_cellulose_batch_{level}gl" for level in (10, 20, 30))
COMPATIBILITY_ID = "trichoderma_harzianum_cellulose_culture_physiology"
TEMPLATE_ID = "trichoderma_harzianum_cellulose_culture_template"
CALIBRATED_SYMBOLS = {
    "k_h": "gelain_hydrolysis_k_h",
    "Kh": "gelain_hydrolysis_Kh",
    "Y": "gelain_hydrolysis_Y",
    "kd": "gelain_hydrolysis_kd",
    "K_ind": "gelain_hydrolysis_K_ind",
    "qF": "gelain_hydrolysis_qF",
    "kF": "gelain_hydrolysis_kF",
    "qB": "gelain_hydrolysis_qB",
    "kB": "gelain_hydrolysis_kB",
}
STATE_BY_OBSERVABLE = {
    "biomass": "biomass_dry_mass_concentration",
    "substrate": "cellulose_concentration",
    "cellulase_activity": "cellulase_activity",
    "beta_glucosidase_activity": "beta_glucosidase_activity",
}


@pytest.fixture(scope="module")
def registry():
    return load_registry(REGISTRY_INDEX)


@pytest.fixture(scope="module")
def fit_artifact() -> dict[str, Any]:
    return json.loads(FIT_ARTIFACT.read_text(encoding="utf-8"))


def test_organism_record_names_a_real_strain_with_sourced_capabilities(registry) -> None:
    fungus = registry.get_fungus(FUNGUS_ID)
    assert fungus.scientific_name == "Trichoderma harzianum"
    assert "10.1016/j.cesx.2020.100085" in fungus.provenance["source"]
    assert "10.17632/shd3wcczsr.2" in fungus.provenance["source"]
    assert fungus.enzyme_classes == ("cellulase_total_filter_paper_activity", "beta_glucosidase")
    assert fungus.assimilable_products == ()
    enzyme = registry.get_enzyme_class("cellulase_total_filter_paper_activity")
    assert enzyme.compatible_processes == ("culture_physiology",)
    substrate = registry.get_substrate(SUBSTRATE_ID)
    assert substrate.substrate_class == "cellulose_particulate"
    assert substrate.products == ()
    assert all(spec.is_unknown for spec in substrate.properties.values())


def test_calibrated_records_match_the_frozen_fit_artifact_bit_for_bit(registry, fit_artifact) -> None:
    fitted = {item["symbol"]: item for item in fit_artifact["parameters"]}
    for fit_symbol, registry_symbol in CALIBRATED_SYMBOLS.items():
        (record,) = registry.get_parameter_records(parameter_symbol=registry_symbol)
        assert record.maturity == "calibrated"
        assert record.process_type == "culture_physiology"
        assert record.fungus_id == FUNGUS_ID and record.substrate_id == SUBSTRATE_ID
        assert record.environment_id is None
        assert record.value.is_exact
        assert record.value.value == fitted[fit_symbol]["value"], fit_symbol
        assert Q_(1.0, record.value.units or "").to(fitted[fit_symbol]["units"]).magnitude == pytest.approx(1.0)
        assert record.provenance["fit_artifact_sha256"] == _sha256(FIT_ARTIFACT)
        assert record.provenance["validation_status"] == "retrospective_development_fit_not_validated"
        assert record.allowed_use == "scientific_or_exploratory_when_all_other_inputs_are_valid"
    assert set(fit_artifact["near_bounds"]) == {"K_ind", "kF", "kB"}
    for fit_symbol in fit_artifact["near_bounds"]:
        (record,) = registry.get_parameter_records(parameter_symbol=CALIBRATED_SYMBOLS[fit_symbol])
        assert "bound" in record.notes


@pytest.mark.parametrize("environment_id", ENVIRONMENT_IDS)
def test_case_is_modelable_in_scientific_mode_through_the_cellulase_class_only(registry, environment_id: str) -> None:
    report = assess_modelability(
        fungus_id=FUNGUS_ID,
        substrate_id=SUBSTRATE_ID,
        environment_id=environment_id,
        registry=registry,
        mode="scientific",
    )
    assert report.status == "modelable", report.to_dict()
    assert not report.missing and not report.incompatible and not report.uncertain
    assert report.required_processes == ("culture_physiology",)
    assert len(report.required_parameters) == 13
    unmatched = [item for item in report.known if item.item_id == "beta_glucosidase"]
    assert unmatched and unmatched[0].details["used_for_process_selection"] is False


def test_configured_model_reproduces_the_frozen_research_candidate(registry, fit_artifact, tmp_path: Path) -> None:
    """The registry composition and the research implementation are the same model."""

    parameters = ParameterSet(
        [
            Parameter(item["symbol"], item["symbol"], item["value"], item["units"], None, item["source"], "low", "frozen fit")
            for item in fit_artifact["parameters"]
        ]
    )
    for level, environment_id in zip((10, 20, 30), ENVIRONMENT_IDS, strict=True):
        config = build_model_config_from_registry_case(
            fungus_id=FUNGUS_ID,
            substrate_id=SUBSTRATE_ID,
            environment_id=environment_id,
            registry=registry,
            mode="scientific",
            output_directory=str(tmp_path / environment_id / "bundle"),
        )
        assert config.mode == "scientific"
        assert config.raw["case_template"]["organism"]["fungus_id"] == FUNGUS_ID
        config_path = tmp_path / environment_id / "model_config.yml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(yaml.safe_dump(config.to_dict(), sort_keys=False), encoding="utf-8")
        result = run_configured_model(config_path, output_dir=tmp_path / environment_id / "bundle")
        assert all(item["passed"] for item in result.validation_report()), result.validation_report()
        kernels = result.solver_metadata["kernel"]["process_kernels"]
        assert set(kernels.values()) == {"numeric"} and len(kernels) == 6
        assert result.solver_metadata["kernel"]["negative_state_policy"] == NEGATIVE_STATE_POLICY
        times = np.asarray(result.time.to("hour").magnitude, dtype=float)
        design = CultureDesign(
            f"gelain_2020_cellulose_{level}gl",
            "cellulose",
            Q_(times, "hour"),
            Q_(0.3990672957214788, "gram / liter"),
            Q_(float(level), "gram / liter"),
            "registry parity test",
        )
        reference = simulate_candidate(
            design,
            {"cellulase_activity": Q_(0.0, "gelain_fpu / liter"), "beta_glucosidase_activity": Q_(0.0, "gelain_beta_u / liter")},
            parameters,
            model="hydrolysis",
            hypothesis_source="registry parity test",
        )
        for observable, state in STATE_BY_OBSERVABLE.items():
            expected = np.asarray(reference.observables[observable].magnitude, dtype=float)
            actual = np.asarray(result.states[state].to(reference.observables[observable].units).magnitude, dtype=float)
            scale = float(np.max(np.abs(expected)))
            np.testing.assert_allclose(actual, expected, rtol=1e-6, atol=1e-7 * scale, err_msg=f"{environment_id}:{observable}")
        substrate = np.asarray(result.states["cellulose_concentration"].magnitude, dtype=float)
        biomass = np.asarray(result.states["biomass_dry_mass_concentration"].magnitude, dtype=float)
        ledger = np.asarray(result.states["consumed_cellulose_not_retained_as_biomass"].magnitude, dtype=float)
        lost = np.asarray(result.states["biomass_dry_mass_lost"].magnitude, dtype=float)
        np.testing.assert_allclose(substrate + biomass + ledger + lost, level + 0.3990672957214788, rtol=1e-9)
        assert substrate[-1] < 1e-3 * level, "cellulose should be nearly consumed within 96 h at every loading"


def test_virtual_experiment_runs_the_organism_case_in_scientific_mode(tmp_path: Path) -> None:
    study = VirtualExperiment.from_names(
        fungi=["T. harzianum P49P11"],
        substrates=["Celufloc 200"],
        environments=list(ENVIRONMENT_IDS),
        registry=REGISTRY_INDEX,
    )
    result = study.simulate(mode="scientific", output_dir=tmp_path / "organism")
    assert [report.status for report in result.preflight_reports] == ["modelable"] * 3
    assert result.n_samples == 1
    rows = result.time_series()
    simulated = {(row["state"], row["state_role"]) for row in rows if row["source"] == "simulation_state"}
    assert {
        ("biomass_dry_mass_concentration", "biomass"),
        ("cellulase_activity", "enzyme"),
        ("beta_glucosidase_activity", "enzyme_beta_glucosidase"),
        ("cellulose_concentration", "substrate"),
        ("consumed_cellulose_not_retained_as_biomass", "ledger_unassimilated_substrate"),
        ("biomass_dry_mass_lost", "ledger_biomass_loss"),
    } <= simulated
    assert any(row["state"] == "substrate_degraded_fraction" for row in rows)
    assert {row["case_id"] for row in rows} and len({row["environment_id"] for row in rows}) == 3
    units = {row["units"] for row in rows if row["state"] == "cellulase_activity"}
    assert units == {"filter_paper_unit / liter"}
    thresholds = {
        (row["environment_id"], row["threshold_fraction"]): row["status"] for row in result.threshold_times()
    }
    assert all(status == "computed" for key, status in thresholds.items() if key[1] in {"0.1", "0.5", "0.9"})
    mechanisms = {row["mechanism_id"]: row for row in result.mechanism_summary()}
    assert mechanisms["culture_physiology"]["maturity"] == "software_tested_retrospectively_calibrated_unvalidated"
    limitation_categories = {row["category"] for row in result.limitations()}
    assert {"retrospective_calibration", "not_modelled"} <= limitation_categories
    manifest = json.loads((tmp_path / "organism" / "output_manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_label"] == "scientific_exact_unvalidated"
    assert (tmp_path / "organism" / "figures" / "substrate_remaining_vs_time.png").exists()


def test_exploratory_mode_is_the_same_exact_case_with_one_sample(tmp_path: Path) -> None:
    study = VirtualExperiment.from_registry(
        fungi=[FUNGUS_ID],
        substrates=[SUBSTRATE_ID],
        environments=[ENVIRONMENT_IDS[0]],
        registry=REGISTRY_INDEX,
    )
    result = study.simulate(mode="exploratory", n_samples=2, seed=3, output_dir=tmp_path / "exploratory")
    sampled = [row for row in result.sampled_parameters() if row["symbol"] == "gelain_hydrolysis_Y"]
    values = {row["sample_id"]: row["sampled_value"] for row in sampled}
    assert len(values) == 2 and len(set(values.values())) == 1, "exact records do not vary between samples"
    assert {row["source_maturity"] for row in sampled} == {"calibrated"}
    assert {row["sampled_value_kind"] for row in sampled} == {"exact"}


def test_scientific_mode_fails_closed_when_a_calibrated_record_is_withdrawn(tmp_path: Path) -> None:
    registry_dir = tmp_path / "registry"
    _copy_tree(ROOT / "data_registry", registry_dir)
    parameters_path = registry_dir / "parameters" / "parameter_records.yml"
    data = cast(dict[str, Any], yaml.safe_load(parameters_path.read_text(encoding="utf-8")))
    records = cast(list[dict[str, Any]], data["records"])
    target = next(record for record in records if record["record_id"] == "gelain_hydrolysis_Y_calibrated")
    target["value"] = {
        "kind": "unknown",
        "units": "dimensionless",
        "source": "withdrawn for the test",
        "confidence_level": "missing",
        "notes": "Yield withdrawn to prove the case fails closed.",
    }
    parameters_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    registry = load_registry(registry_dir / "registry_index.yml")
    report = assess_modelability(
        fungus_id=FUNGUS_ID,
        substrate_id=SUBSTRATE_ID,
        environment_id=ENVIRONMENT_IDS[0],
        registry=registry,
        mode="scientific",
    )
    assert report.status == "underparameterized"
    assert any(item.item_id == "gelain_hydrolysis_Y" for item in report.missing)
    with pytest.raises(RegistryCaseBuildError):
        build_model_config_from_registry_case(
            fungus_id=FUNGUS_ID,
            substrate_id=SUBSTRATE_ID,
            environment_id=ENVIRONMENT_IDS[0],
            registry=registry,
            mode="scientific",
        )
    study = VirtualExperiment.from_registry(
        fungi=[FUNGUS_ID], substrates=[SUBSTRATE_ID], environments=[ENVIRONMENT_IDS[0]], registry=registry
    )
    with pytest.raises(VirtualExperimentError, match="Scientific simulation requires"):
        study.simulate(mode="scientific", output_dir=tmp_path / "blocked")


def test_template_rejects_unused_or_unresolved_parameter_roles(registry) -> None:
    from fungal_model.screening.culture_physiology import build_culture_physiology_config_data

    template = registry.get_case_template(TEMPLATE_ID)
    compatibility = registry.get_process_compatibility(
        enzyme_class="cellulase_total_filter_paper_activity",
        substrate_class="cellulose_particulate",
        process_type="culture_physiology",
    )[0]
    records = {
        role: registry.get_parameter_records(parameter_symbol=symbol)[0]
        for role, symbol in compatibility.parameter_roles.items()
        if symbol != "gelain_2020_cellulose_initial_loading"
    }
    records["initial_substrate"] = registry.get_parameter_records(
        parameter_symbol="gelain_2020_cellulose_initial_loading", environment_id=ENVIRONMENT_IDS[0]
    )[0]
    kwargs = dict(
        registry=registry,
        compatibility=compatibility,
        case_template=template,
        substrate=registry.get_substrate(SUBSTRATE_ID),
        fungus_id=FUNGUS_ID,
        substrate_id=SUBSTRATE_ID,
        environment_id=ENVIRONMENT_IDS[0],
        output_directory=None,
    )
    data = build_culture_physiology_config_data(parameter_records=records, **kwargs)
    assert [process["id"] for process in data["processes"]] == data["case_template"]["process_ids"]
    product_map = data["entities"]["product_maps"][0]["data"]
    yield_value = records["biomass_yield"].value.value
    assert product_map["products"]["biomass_dry_mass_concentration"] == pytest.approx(yield_value)
    assert product_map["products"]["consumed_cellulose_not_retained_as_biomass"] == pytest.approx(1.0 - yield_value)
    missing = dict(records)
    del missing["biomass_yield"]
    with pytest.raises(RegistryCaseBuildError, match="biomass_yield"):
        build_culture_physiology_config_data(parameter_records=missing, **kwargs)
    extra = dict(records)
    extra["unused_role"] = records["biomass_yield"]
    with pytest.raises(RegistryCaseBuildError, match="unused_role"):
        build_culture_physiology_config_data(parameter_records=extra, **kwargs)


def _copy_tree(source: Path, destination: Path) -> None:
    import shutil

    shutil.copytree(source, destination)


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
