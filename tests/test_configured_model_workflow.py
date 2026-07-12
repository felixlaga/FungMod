from __future__ import annotations

from copy import deepcopy
import csv
import json
from pathlib import Path

import pytest
import yaml

from fungal_model import (
    ConfiguredModelExecutionError,
    Parameter,
    ParameterMergeError,
    ParameterSet,
    merge_parameter_sets,
    run_configured_model,
)
from fungal_model.api.report import write_virtual_experiment_report
from fungal_model.core.units import Q_
from fungal_model.io.model_config import ModelConfigError, load_model_config
from fungal_model.plugins.pet import pet_substrate_loader_registry
from fungal_model.results import SimulationResult
from fungal_model.workflows import (
    ConfiguredInputLoader,
    ConfiguredOutputWriter,
    ConfiguredProcessAssembler,
)
from fungal_model.workflows.configured_outputs import (
    ConfiguredEntropyProductionError,
    _entropy_production_rate_timeseries,
)


ROOT = Path(__file__).resolve().parents[1]
MODEL_CONFIGS = ROOT / "data" / "model_configs"


def test_generic_configured_runner_executes_all_foundation_benchmarks(tmp_path) -> None:
    cases = (
        (MODEL_CONFIGS / "toy_homogeneous_ab.yml", {}, "a_to_b"),
        (MODEL_CONFIGS / "toy_surface_dummy_non_pet.yml", {}, "dummy_surface_catalysis"),
        (
            MODEL_CONFIGS / "toy_surface_dummy_non_pet_product_inhibition.yml",
            {},
            "dummy_surface_catalysis",
        ),
        (
            MODEL_CONFIGS / "toy_surface_pet_plugin.yml",
            {"substrate_registry": pet_substrate_loader_registry()},
            "plugin_surface_catalysis",
        ),
    )

    for config_path, options, expected_rate in cases:
        result = run_configured_model(
            config_path,
            output_dir=tmp_path / config_path.stem,
            **options,
        )

        assert isinstance(result, SimulationResult)
        assert result.assembly_report is not None
        assert result.assembly_report.success
        assert expected_rate in result.process_rates
        assert result.validation_results
        assert all(validation.passed for validation in result.validation_results)
        output = tmp_path / config_path.stem
        for relative_path in _expected_configured_output_files():
            assert (output / relative_path).exists(), relative_path
        manifest = json.loads((output / "output_manifest.json").read_text(encoding="utf-8"))
        metadata = json.loads((output / "configured_metadata.json").read_text(encoding="utf-8"))
        entity_index = json.loads((output / "entity_snapshots" / "index.json").read_text(encoding="utf-8"))
        assert manifest["mode"] == "toy"
        assert manifest["maturity"] == "framework_benchmark"
        assert "entity_snapshots/index.json" in manifest["files"]
        assert metadata["validation"]["passed"] is True
        assert entity_index["entities"]


def test_configured_output_records_generic_assembly_metadata(tmp_path) -> None:
    result = run_configured_model(
        MODEL_CONFIGS / "toy_surface_dummy_non_pet.yml",
        output_dir=tmp_path / "dummy_run",
    )

    record = json.loads((tmp_path / "dummy_run" / "record.json").read_text(encoding="utf-8"))
    run = json.loads((tmp_path / "dummy_run" / "configured_model_run.json").read_text(encoding="utf-8"))
    decisions = json.loads((tmp_path / "dummy_run" / "process_build_decisions.json").read_text(encoding="utf-8"))
    validators = json.loads((tmp_path / "dummy_run" / "validators.json").read_text(encoding="utf-8"))

    assert record["name"] == result.name
    assert record["assembly_report"]["matched_processes"][0]["process_type"] == "surface_catalysis"
    assert run["assembly_success"] is True
    assert run["mode"] == "toy"
    assert run["maturity"] == "framework_benchmark"
    assert run["validation"]["passed"] is True
    assert decisions["decisions"][0]["can_build"] is True
    assert validators["summary"]["passed"] is True


def test_configured_output_writes_conservation_diagnostics(tmp_path) -> None:
    output_dir = tmp_path / "homogeneous_run"

    run_configured_model(
        MODEL_CONFIGS / "toy_homogeneous_ab.yml",
        output_dir=output_dir,
    )

    diagnostics = json.loads((output_dir / "conservation_diagnostics.json").read_text(encoding="utf-8"))
    with (output_dir / "conservation_diagnostics.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    manifest = json.loads((output_dir / "output_manifest.json").read_text(encoding="utf-8"))

    assert diagnostics["kind"] == "configured_conservation_diagnostics"
    assert diagnostics["validator_count"] == 1
    assert diagnostics["evaluated_count"] == 1
    assert diagnostics["rows"][0]["validator_id"] == "closed_mass_balance"
    assert diagnostics["rows"][0]["status"] == "evaluated"
    assert diagnostics["rows"][0]["weighted_states"] == {
        "dissolved_substrate_amount": 1.0,
        "released_product_amount": 1.0,
    }
    assert diagnostics["rows"][0]["initial_conserved_total"] == pytest.approx(1.0)
    assert diagnostics["rows"][0]["final_conserved_total"] == pytest.approx(1.0)
    assert diagnostics["rows"][0]["final_drift"] == pytest.approx(0.0, abs=1e-12)
    assert diagnostics["rows"][0]["max_absolute_drift"] == pytest.approx(0.0, abs=1e-12)
    assert diagnostics["rows"][0]["relative_max_absolute_drift"] == pytest.approx(0.0, abs=1e-12)
    assert diagnostics["rows"][0]["units"] == "kilogram"
    assert "not validation, calibration" in diagnostics["rows"][0]["allowed_use"]
    assert rows[0]["validator_id"] == "closed_mass_balance"
    assert rows[0]["weighted_states"] == (
        '{"dissolved_substrate_amount": 1.0, "released_product_amount": 1.0}'
    )
    assert "conservation_diagnostics.json" in manifest["files"]
    assert "conservation_diagnostics.csv" in manifest["files"]


def test_configured_output_report_exposes_conservation_diagnostics_artifacts(tmp_path) -> None:
    output_dir = tmp_path / "homogeneous_run"

    run_configured_model(
        MODEL_CONFIGS / "toy_homogeneous_ab.yml",
        output_dir=output_dir,
    )

    report_path = write_virtual_experiment_report(
        table_dir=output_dir,
        output_dir=output_dir / "report",
        include_html=True,
        include_index=True,
    )
    report = report_path.read_text(encoding="utf-8")
    html = report_path.with_suffix(".html").read_text(encoding="utf-8")
    index = report_path.with_name("index.html").read_text(encoding="utf-8")

    assert "## Conservation diagnostics" in report
    assert (
        "existing configured-output `conservation_diagnostics.json` and "
        "`conservation_diagnostics.csv` artifacts only"
    ) in report
    assert "validator count=1" in report
    assert "evaluated count=1" in report
    assert "status counts={evaluated: 1}" in report
    assert "`closed_mass_balance`" in report
    assert "do not infer conserved quantities" in report
    assert "No standard `conservation_diagnostics.csv` rows were present." in report
    assert 'href="../conservation_diagnostics.json"' in html
    assert 'href="../conservation_diagnostics.csv"' in html
    assert 'href="../conservation_diagnostics.json"' in index
    assert 'href="../conservation_diagnostics.csv"' in index


def test_configured_output_writes_process_bound_entropy_production_rate_timeseries(tmp_path) -> None:
    config_path = _entropy_timeseries_config(tmp_path, include_conversion=True)
    output_dir = tmp_path / "entropy_timeseries"

    result = run_configured_model(config_path, output_dir=output_dir)

    diagnostics = json.loads(
        (output_dir / "entropy_production_rate_timeseries.json").read_text(encoding="utf-8")
    )
    with (output_dir / "entropy_production_rate_timeseries.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    manifest = json.loads((output_dir / "output_manifest.json").read_text(encoding="utf-8"))
    serialized_config = json.loads(
        (output_dir / "input_model_config.json").read_text(encoding="utf-8")
    )

    assert diagnostics["kind"] == "configured_process_entropy_production_rate_timeseries"
    assert diagnostics["diagnostic_count"] == 1
    assert diagnostics["evaluated_count"] == 1
    assert diagnostics["row_count"] == 11
    assert diagnostics["status"] == "evaluated"
    assert diagnostics["has_dynamic_delta_gibbs"] is False
    assert diagnostics["has_solver_time_enforcement"] is False
    assert diagnostics["diagnostics"][0]["process_id"] == "a_to_b"
    assert diagnostics["diagnostics"][0]["process_rate_units"] == "kilogram / second"
    assert diagnostics["diagnostics"][0]["extent_rate_units"] == "mole / second"
    assert diagnostics["diagnostics"][0]["process_rate_to_extent_rate"] == {
        "value": 2.0,
        "units": "mole / kilogram",
        "source": "Artificial framework-benchmark mass-to-extent conversion.",
    }
    assert diagnostics["rows"][0]["process_rate"] == pytest.approx(0.1)
    assert diagnostics["rows"][0]["extent_rate"] == pytest.approx(0.2)
    assert diagnostics["rows"][0]["entropy_production_rate"] == pytest.approx(100.0 / 3.0)
    assert diagnostics["rows"][0]["entropy_production_rate_units"] == "joule / kelvin / second"
    assert diagnostics["rows"][0]["provenance_refs"] == ["framework-benchmark:process-entropy"]
    assert diagnostics["rows"][0]["status"] == "evaluated"
    assert "Post-simulation diagnostic" in diagnostics["rows"][0]["guardrails"]
    assert rows[0]["process_id"] == "a_to_b"
    assert float(rows[0]["entropy_production_rate"]) == pytest.approx(100.0 / 3.0)
    assert "entropy_production_rate_timeseries.json" in manifest["files"]
    assert "entropy_production_rate_timeseries.csv" in manifest["files"]
    assert serialized_config["outputs"]["entropy_production_rate_timeseries"][0] == {
        "id": "a_to_b_entropy_rate",
        "process_id": "a_to_b",
        "process_rate_interpretation": "reaction_extent_rate",
        "condition_specific_delta_gibbs": {
            "value": -50.0,
            "units": "kilojoule / mole",
            "source": "Artificial framework-benchmark condition-specific delta Gibbs.",
        },
        "temperature": {
            "value": 300.0,
            "units": "kelvin",
            "source": "Artificial framework-benchmark temperature.",
        },
        "extent_rate_units": "mole / second",
        "process_rate_to_extent_rate": {
            "value": 2.0,
            "units": "mole / kilogram",
            "source": "Artificial framework-benchmark mass-to-extent conversion.",
        },
        "provenance_refs": ["framework-benchmark:process-entropy"],
    }
    assert result.process_rates["a_to_b"].units == "kilogram / second"
    assert result.derived_quantities == {}


def test_process_entropy_timeseries_accepts_direct_molar_extent_rate(tmp_path) -> None:
    config_path = _entropy_timeseries_config(
        tmp_path,
        include_conversion=False,
        state_units="mole",
        filename="direct_molar_entropy.yml",
    )
    output_dir = tmp_path / "direct_molar_entropy"

    run_configured_model(config_path, output_dir=output_dir)

    diagnostics = json.loads(
        (output_dir / "entropy_production_rate_timeseries.json").read_text(encoding="utf-8")
    )
    assert diagnostics["diagnostics"][0]["process_rate_units"] == "mole / second"
    assert diagnostics["diagnostics"][0]["process_rate_to_extent_rate"] is None
    assert diagnostics["rows"][0]["extent_rate"] == pytest.approx(0.1)
    assert diagnostics["rows"][0]["entropy_production_rate"] == pytest.approx(50.0 / 3.0)


def test_process_entropy_timeseries_preserves_the_thermodynamic_sign(tmp_path) -> None:
    config_path = _entropy_timeseries_config(
        tmp_path,
        include_conversion=False,
        state_units="mole",
        delta_gibbs_value=50.0,
        filename="positive_delta_g_entropy.yml",
    )
    output_dir = tmp_path / "positive_delta_g_entropy"

    run_configured_model(config_path, output_dir=output_dir)

    diagnostics = json.loads(
        (output_dir / "entropy_production_rate_timeseries.json").read_text(encoding="utf-8")
    )
    assert diagnostics["rows"][0]["extent_rate"] == pytest.approx(0.1)
    assert diagnostics["rows"][0]["entropy_production_rate"] == pytest.approx(-50.0 / 3.0)


def test_process_entropy_timeseries_accepts_absolute_celsius_temperature(tmp_path) -> None:
    config_path = _entropy_timeseries_config(
        tmp_path,
        temperature_value=25.0,
        temperature_units="degC",
        filename="absolute_celsius_entropy.yml",
    )
    output_dir = tmp_path / "absolute_celsius_entropy"

    run_configured_model(config_path, output_dir=output_dir)

    diagnostics = json.loads(
        (output_dir / "entropy_production_rate_timeseries.json").read_text(encoding="utf-8")
    )
    assert diagnostics["rows"][0]["temperature"] == pytest.approx(298.15)
    assert diagnostics["rows"][0]["temperature_units"] == "kelvin"


@pytest.mark.parametrize(
    "temperature_units",
    [
        "delta_degC",
        "delta_degree_Celsius",
        "delta_degF",
        "delta_degree_Fahrenheit",
    ],
)
def test_process_entropy_timeseries_rejects_temperature_interval_units(
    tmp_path,
    temperature_units,
) -> None:
    config_path = _entropy_timeseries_config(
        tmp_path,
        temperature_value=25.0,
        temperature_units=temperature_units,
        filename="temperature_interval_entropy.yml",
    )

    with pytest.raises(ValueError, match="absolute temperature, not a temperature interval"):
        run_configured_model(config_path, output_dir=tmp_path / "temperature_interval_entropy")


def test_process_entropy_timeseries_is_visible_in_configured_report(tmp_path) -> None:
    config_path = _entropy_timeseries_config(tmp_path, include_conversion=True)
    output_dir = tmp_path / "entropy_report"
    run_configured_model(config_path, output_dir=output_dir)

    report_path = write_virtual_experiment_report(
        table_dir=output_dir,
        output_dir=output_dir / "report",
        include_html=True,
        include_index=True,
    )
    report = report_path.read_text(encoding="utf-8")
    html = report_path.with_suffix(".html").read_text(encoding="utf-8")
    index = report_path.with_name("index.html").read_text(encoding="utf-8")

    assert "Process-bound entropy-production-rate timeseries" in report
    assert "dynamic delta Gibbs `False`" in report
    assert "solver-time enforcement `False`" in report
    assert "Rows from `entropy_production_rate_timeseries.csv`" in report
    assert "No inferred reaction quotient" in report
    assert 'href="../entropy_production_rate_timeseries.json"' in html
    assert 'href="../entropy_production_rate_timeseries.csv"' in html
    assert 'href="../entropy_production_rate_timeseries.json"' in index
    assert 'href="../entropy_production_rate_timeseries.csv"' in index


@pytest.mark.parametrize(
    ("config_changes", "message"),
    [
        ({"process_id": "missing_process"}, "binds unknown configured process"),
        ({"include_conversion": False}, "is not compatible with extent-rate units"),
        ({"extent_rate_units": "unknown_extent_unit / second"}, "is not compatible with extent-rate units"),
        ({"delta_gibbs_units": "kilogram"}, "must be compatible with energy per amount"),
        ({"temperature_units": "second"}, "temperature must be compatible with kelvin"),
        ({"temperature_value": 0.0}, "temperature must be positive in kelvin"),
        ({"conversion_value": 0.0}, "process_rate_to_extent_rate must be positive"),
        ({"delta_gibbs_value": [-50.0]}, "must be a finite scalar"),
    ],
)
def test_process_entropy_timeseries_fails_explicitly_for_unsupported_evaluation(
    tmp_path,
    config_changes,
    message,
) -> None:
    config_path = _entropy_timeseries_config(
        tmp_path,
        filename="invalid_entropy.yml",
        **config_changes,
    )
    output_dir = tmp_path / "invalid_entropy"

    with pytest.raises(ValueError, match=message):
        run_configured_model(config_path, output_dir=output_dir)

    assert not (output_dir / "entropy_production_rate_timeseries.json").exists()
    assert not (output_dir / "output_manifest.json").exists()


def test_process_entropy_timeseries_failed_same_directory_rerun_clears_stale_artifacts(
    tmp_path,
) -> None:
    config_path = _entropy_timeseries_config(tmp_path, filename="same_directory_entropy.yml")
    output_dir = tmp_path / "same_directory_output"
    run_configured_model(config_path, output_dir=output_dir)

    entropy_json = output_dir / "entropy_production_rate_timeseries.json"
    entropy_csv = output_dir / "entropy_production_rate_timeseries.csv"
    manifest_path = output_dir / "output_manifest.json"
    assert entropy_json.exists()
    assert entropy_csv.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert entropy_json.name in manifest["files"]
    assert entropy_csv.name in manifest["files"]

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["outputs"]["entropy_production_rate_timeseries"][0]["temperature"]["value"] = 0.0
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="temperature must be positive in kelvin"):
        run_configured_model(config_path, output_dir=output_dir)

    assert not entropy_json.exists()
    assert not entropy_csv.exists()
    assert not manifest_path.exists()


def test_process_entropy_timeseries_rejects_unsupported_metadata(tmp_path) -> None:
    config_path = _entropy_timeseries_config(tmp_path, filename="unsupported_entropy.yml")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["outputs"]["entropy_production_rate_timeseries"][0]["dynamic_delta_gibbs"] = True
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    with pytest.raises(ModelConfigError, match="unsupported fields"):
        load_model_config(config_path)


def test_process_entropy_timeseries_requires_sourced_metadata(tmp_path) -> None:
    config_path = _entropy_timeseries_config(tmp_path, filename="missing_entropy_metadata.yml")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["outputs"]["entropy_production_rate_timeseries"][0].pop("temperature")
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    with pytest.raises(ModelConfigError, match="temperature must be a mapping"):
        load_model_config(config_path)


@pytest.mark.parametrize("invalid_source", [None, 7, {"ref": "source"}, ["source"], "   "])
def test_process_entropy_timeseries_source_must_be_a_non_empty_string(
    tmp_path,
    invalid_source,
) -> None:
    config_path = _entropy_timeseries_config(tmp_path, filename="invalid_source.yml")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["outputs"]["entropy_production_rate_timeseries"][0][
        "condition_specific_delta_gibbs"
    ]["source"] = invalid_source
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    with pytest.raises(ModelConfigError, match="source must be a non-empty string"):
        load_model_config(config_path)


@pytest.mark.parametrize(
    "invalid_refs",
    [None, 7, [None], [7], [{"ref": "source"}], [["source"]], ["   "], []],
)
def test_process_entropy_timeseries_provenance_refs_require_non_empty_strings(
    tmp_path,
    invalid_refs,
) -> None:
    config_path = _entropy_timeseries_config(tmp_path, filename="invalid_provenance_refs.yml")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["outputs"]["entropy_production_rate_timeseries"][0][
        "provenance_refs"
    ] = invalid_refs
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    with pytest.raises(ModelConfigError, match="provenance_refs must"):
        load_model_config(config_path)


def test_process_entropy_timeseries_requires_explicit_extent_rate_interpretation(
    tmp_path,
) -> None:
    config_path = _entropy_timeseries_config(tmp_path, filename="invalid_interpretation.yml")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["outputs"]["entropy_production_rate_timeseries"][0][
        "process_rate_interpretation"
    ] = "mass_rate"
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    with pytest.raises(ModelConfigError, match="must be 'reaction_extent_rate'"):
        load_model_config(config_path)


def test_process_entropy_timeseries_rejects_missing_native_trajectory(tmp_path) -> None:
    config_path = _entropy_timeseries_config(
        tmp_path,
        include_conversion=False,
        state_units="mole",
        filename="missing_native_rate.yml",
    )
    result = run_configured_model(config_path, output_dir=tmp_path / "complete_result")
    result.process_rates.clear()

    with pytest.raises(ConfiguredEntropyProductionError, match="no native process-rate trajectory"):
        _entropy_production_rate_timeseries(load_model_config(config_path), result)


def test_process_entropy_timeseries_rejects_time_misalignment(tmp_path) -> None:
    config_path = _entropy_timeseries_config(
        tmp_path,
        include_conversion=False,
        state_units="mole",
        filename="misaligned_native_rate.yml",
    )
    result = run_configured_model(config_path, output_dir=tmp_path / "complete_result")
    result.process_rates["a_to_b"] = Q_([0.1, 0.09], "mole / second")

    with pytest.raises(ConfiguredEntropyProductionError, match="does not align with result time"):
        _entropy_production_rate_timeseries(load_model_config(config_path), result)


def test_configured_output_writes_zero_evaluated_conservation_diagnostics_without_mass_balance(
    tmp_path,
) -> None:
    config_path = _homogeneous_config_without_mass_balance(tmp_path)
    output_dir = tmp_path / "no_mass_balance"

    run_configured_model(config_path, output_dir=output_dir)

    diagnostics = json.loads((output_dir / "conservation_diagnostics.json").read_text(encoding="utf-8"))
    with (output_dir / "conservation_diagnostics.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert diagnostics["kind"] == "configured_conservation_diagnostics"
    assert diagnostics["validator_count"] == 0
    assert diagnostics["evaluated_count"] == 0
    assert diagnostics["rows"] == []
    assert rows == []
    assert "validator_id" in (reader.fieldnames or ())


def test_configured_output_writes_solver_diagnostics_from_existing_metadata(tmp_path) -> None:
    output_dir = tmp_path / "homogeneous_run"

    result = run_configured_model(
        MODEL_CONFIGS / "toy_homogeneous_ab.yml",
        output_dir=output_dir,
    )

    diagnostics = json.loads((output_dir / "solver_diagnostics.json").read_text(encoding="utf-8"))
    with (output_dir / "solver_diagnostics.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    manifest = json.loads((output_dir / "output_manifest.json").read_text(encoding="utf-8"))

    assert diagnostics["kind"] == "configured_solver_diagnostics"
    assert diagnostics["metadata_available"] is True
    assert diagnostics["row_count"] == 1
    assert diagnostics["status"] == "available"
    assert diagnostics["rows"][0]["config_name"] == "toy homogeneous A to B benchmark"
    assert diagnostics["rows"][0]["mode"] == "toy"
    assert diagnostics["rows"][0]["maturity"] == "framework_benchmark"
    assert diagnostics["rows"][0]["state_count"] == 2
    assert diagnostics["rows"][0]["configured_process_count"] == 1
    assert diagnostics["rows"][0]["process_rate_count"] == 1
    assert diagnostics["rows"][0]["time_units"] == "second"
    assert diagnostics["rows"][0]["configured_time_start"] == pytest.approx(0.0)
    assert diagnostics["rows"][0]["configured_time_stop"] == pytest.approx(10.0)
    assert diagnostics["rows"][0]["configured_time_evaluation_count"] == 11
    assert diagnostics["rows"][0]["result_time_point_count"] == 11
    assert diagnostics["rows"][0]["solver_backend"] == "scipy.solve_ivp"
    assert diagnostics["rows"][0]["solver_method"] == result.solver_settings.method
    assert diagnostics["rows"][0]["solver_success"] is True
    assert diagnostics["rows"][0]["nfev"] == result.solver_metadata["nfev"]
    assert "not validation, calibration" in diagnostics["rows"][0]["allowed_use"]
    assert "does not infer scientific values" in diagnostics["rows"][0]["interpretation_guardrail"]
    assert rows[0]["config_name"] == "toy homogeneous A to B benchmark"
    assert rows[0]["solver_backend"] == "scipy.solve_ivp"
    assert rows[0]["solver_success"] == "True"
    assert rows[0]["configured_time_evaluation_count"] == "11"
    assert "solver_diagnostics.json" in manifest["files"]
    assert "solver_diagnostics.csv" in manifest["files"]


def test_configured_output_report_exposes_solver_diagnostics_artifacts(tmp_path) -> None:
    output_dir = tmp_path / "homogeneous_run"

    run_configured_model(
        MODEL_CONFIGS / "toy_homogeneous_ab.yml",
        output_dir=output_dir,
    )

    report_path = write_virtual_experiment_report(
        table_dir=output_dir,
        output_dir=output_dir / "report",
        include_html=True,
        include_index=True,
    )
    report = report_path.read_text(encoding="utf-8")
    html = report_path.with_suffix(".html").read_text(encoding="utf-8")
    index = report_path.with_name("index.html").read_text(encoding="utf-8")

    assert "## Configured solver diagnostics" in report
    assert "existing configured-output `solver_diagnostics.json` and `solver_diagnostics.csv` artifacts only" in report
    assert "do not change solver behavior" in report
    assert "define numerical quality thresholds" in report
    assert "validation/calibration evidence" in report
    assert "`toy homogeneous A to B benchmark`" in report
    assert "backend `scipy.solve_ivp`" in report
    assert "configured time points `11`" in report
    assert "Diagnostic copy over existing configured run metadata" in report
    assert 'href="../solver_diagnostics.json"' in html
    assert 'href="../solver_diagnostics.csv"' in html
    assert 'href="../solver_diagnostics.json"' in index
    assert 'href="../solver_diagnostics.csv"' in index
    assert "empirically validated" not in report.lower()
    assert "calibrated against observations" not in report.lower()


def test_configured_output_writes_header_only_solver_diagnostics_without_metadata(tmp_path) -> None:
    config = load_model_config(MODEL_CONFIGS / "toy_homogeneous_ab.yml")
    inputs = ConfiguredInputLoader().load(config)
    assembly = ConfiguredProcessAssembler().assemble(config, inputs)
    result = assembly.model.run(
        initial_state=inputs.initial_state,
        t_span=inputs.t_span,
        t_eval=inputs.t_eval,
        label=config.mode,
        name=config.name,
    )
    result.solver_metadata = {}
    output_dir = tmp_path / "no_solver_metadata"

    ConfiguredOutputWriter().write_result_bundle(
        config=config,
        inputs=inputs,
        decisions=assembly.decisions,
        result=result,
        output_dir=output_dir,
    )

    diagnostics = json.loads((output_dir / "solver_diagnostics.json").read_text(encoding="utf-8"))
    with (output_dir / "solver_diagnostics.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    manifest = json.loads((output_dir / "output_manifest.json").read_text(encoding="utf-8"))

    assert diagnostics["kind"] == "configured_solver_diagnostics"
    assert diagnostics["metadata_available"] is False
    assert diagnostics["row_count"] == 0
    assert diagnostics["status"] == "unavailable"
    assert diagnostics["missing_metadata_fields"] == [
        "backend",
        "method",
        "success",
        "status",
        "message",
        "nfev",
        "njev",
        "nlu",
    ]
    assert diagnostics["rows"] == []
    assert rows == []
    assert "solver_backend" in (reader.fieldnames or ())
    assert "nfev" in (reader.fieldnames or ())
    assert "solver_diagnostics.json" in manifest["files"]
    assert "solver_diagnostics.csv" in manifest["files"]

    report_path = write_virtual_experiment_report(
        table_dir=output_dir,
        output_dir=output_dir / "report",
        include_html=True,
        include_index=True,
    )
    report = report_path.read_text(encoding="utf-8")
    html = report_path.with_suffix(".html").read_text(encoding="utf-8")
    index = report_path.with_name("index.html").read_text(encoding="utf-8")

    assert "status `unavailable`" in report
    assert "metadata available `False`" in report
    assert "missing metadata fields=[backend, method, success, status, message, nfev, njev, nlu]" in report
    assert "No row-level `solver_diagnostics.csv` diagnostics were present." in report
    assert 'href="../solver_diagnostics.json"' in html
    assert 'href="../solver_diagnostics.csv"' in html
    assert 'href="../solver_diagnostics.json"' in index
    assert 'href="../solver_diagnostics.csv"' in index


def test_configured_mass_balance_missing_state_remains_explicit(tmp_path) -> None:
    data = yaml.safe_load((MODEL_CONFIGS / "toy_homogeneous_ab.yml").read_text(encoding="utf-8"))
    data = deepcopy(data)
    data["validators"][1]["conserved_weights"]["missing_state"] = 1.0
    config_path = tmp_path / "toy_homogeneous_missing_mass_balance_state.yml"
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    output_dir = tmp_path / "missing_state"

    with pytest.raises(KeyError, match="missing_state"):
        run_configured_model(config_path, output_dir=output_dir)

    assert not (output_dir / "output_manifest.json").exists()


def test_configured_output_bundle_contains_entity_snapshots(tmp_path) -> None:
    run_configured_model(
        MODEL_CONFIGS / "toy_surface_dummy_non_pet.yml",
        output_dir=tmp_path / "dummy_run",
    )

    output = tmp_path / "dummy_run"
    index = json.loads((output / "entity_snapshots" / "index.json").read_text(encoding="utf-8"))
    roles = {entry["role"] for entry in index["entities"]}

    assert {"substrate", "enzyme", "environment", "geometry", "product_map"}.issubset(roles)
    for entry in index["entities"]:
        assert (output / entry["snapshot_path"]).exists()


def test_configured_model_runs_with_explicit_product_inhibition_modifier(tmp_path) -> None:
    config_path = _product_inhibited_homogeneous_config(tmp_path)

    result = run_configured_model(config_path, output_dir=tmp_path / "product_inhibited")

    assert "a_to_b" in result.process_rates
    assumptions = json.loads((tmp_path / "product_inhibited" / "assumptions.json").read_text(encoding="utf-8"))
    metadata = json.loads((tmp_path / "product_inhibited" / "configured_metadata.json").read_text(encoding="utf-8"))
    process_config = json.loads((tmp_path / "product_inhibited" / "input_model_config.json").read_text(encoding="utf-8"))[
        "processes"
    ][0]
    assert any(item["name"] == "reversible product inhibition modifier" for item in assumptions)
    assert metadata["configured_process_modifiers"] == [
        {
            "process_id": "a_to_b",
            "modifier_index": 0,
            "type": "product_inhibition",
            "product_state": "released_product_amount",
            "inhibition_constant": "K_i_product",
            "maturity": "exploratory_configured_mechanism",
            "limitation": (
                "Single-product reversible inhibition only; configured only when product_state "
                "and positive unit-compatible K_i are explicit."
            ),
        }
    ]
    assert process_config["modifiers"][0]["type"] == "product_inhibition"


def test_non_pet_surface_benchmark_runs_with_explicit_product_inhibition_modifier(tmp_path) -> None:
    output_dir = tmp_path / "dummy_non_pet_product_inhibited"

    result = run_configured_model(
        MODEL_CONFIGS / "toy_surface_dummy_non_pet_product_inhibition.yml",
        output_dir=output_dir,
    )

    metadata = json.loads((output_dir / "configured_metadata.json").read_text(encoding="utf-8"))
    assumptions = json.loads((output_dir / "assumptions.json").read_text(encoding="utf-8"))
    process_config = json.loads((output_dir / "input_model_config.json").read_text(encoding="utf-8"))[
        "processes"
    ][0]
    merged_parameters = json.loads((output_dir / "merged_parameters.json").read_text(encoding="utf-8"))

    assert result.solver_metadata["success"] is True
    assert "dummy_surface_catalysis" in result.process_rates
    assert metadata["mode"] == "toy"
    assert metadata["maturity"] == "framework_benchmark"
    assert metadata["provenance"]["validity_range"] == "framework tests and exploratory examples only"
    assert metadata["configured_process_modifiers"] == [
        {
            "process_id": "dummy_surface_catalysis",
            "modifier_index": 0,
            "type": "product_inhibition",
            "product_state": "released_product_amount",
            "inhibition_constant": "K_i_dummy_product",
            "maturity": "exploratory_configured_mechanism",
            "limitation": (
                "Single-product reversible inhibition only; configured only when product_state "
                "and positive unit-compatible K_i are explicit."
            ),
        }
    ]
    assert any(item["name"] == "reversible product inhibition modifier" for item in assumptions)
    assert process_config["modifiers"] == [
        {
            "type": "product_inhibition",
            "product_state": "released_product_amount",
            "inhibition_constant": "K_i_dummy_product",
        }
    ]
    ki_parameter = next(item for item in merged_parameters["parameters"] if item["symbol"] == "K_i_dummy_product")
    assert ki_parameter["units"] == "kilogram"
    assert "not biological inhibition evidence" in ki_parameter["notes"]


def test_configured_model_runs_with_explicit_environment_rate_modifiers(tmp_path) -> None:
    config_path = _environment_modified_homogeneous_config(tmp_path)

    base = run_configured_model(MODEL_CONFIGS / "toy_homogeneous_ab.yml", output_dir=tmp_path / "base")
    modified = run_configured_model(config_path, output_dir=tmp_path / "environment_modified")

    assumptions = json.loads((tmp_path / "environment_modified" / "assumptions.json").read_text(encoding="utf-8"))
    metadata = json.loads((tmp_path / "environment_modified" / "configured_metadata.json").read_text(encoding="utf-8"))
    process_config = json.loads(
        (tmp_path / "environment_modified" / "input_model_config.json").read_text(encoding="utf-8")
    )["processes"][0]

    assert "a_to_b" in modified.process_rates
    assert modified.process_rates["a_to_b"].magnitude[0] != pytest.approx(base.process_rates["a_to_b"].magnitude[0])
    assert any(item["name"] == "Arrhenius temperature scaling without deactivation" for item in assumptions)
    assert any(item["name"] == "Gaussian empirical pH activity profile" for item in assumptions)
    assert metadata["configured_process_modifiers"] == [
        {
            "process_id": "a_to_b",
            "modifier_index": 0,
            "type": "temperature_arrhenius_reference",
            "environment_value": "temperature",
            "activation_energy_symbol": "E_a_env",
            "reference_temperature_symbol": "T_ref_env",
            "minimum_temperature_symbol": "",
            "maximum_temperature_symbol": "",
            "maturity": "exploratory_configured_mechanism",
            "limitation": (
                "Arrhenius reference-temperature scaling only; configured only when environment "
                "temperature and explicit unit-compatible parameters are present."
            ),
        },
        {
            "process_id": "a_to_b",
            "modifier_index": 1,
            "type": "ph_gaussian",
            "environment_value": "ph",
            "optimum_symbol": "pH_opt_env",
            "width_symbol": "pH_width_env",
            "minimum_ph_symbol": "",
            "maximum_ph_symbol": "",
            "maturity": "exploratory_configured_mechanism",
            "limitation": (
                "Gaussian empirical pH activity scaling only; configured only when environment "
                "pH and explicit unit-compatible parameters are present."
            ),
        },
    ]
    assert process_config["modifiers"] == [
        {
            "type": "temperature_arrhenius_reference",
            "activation_energy_symbol": "E_a_env",
            "reference_temperature_symbol": "T_ref_env",
            "source": "FungMod configured environment-modifier software benchmark.",
        },
        {
            "type": "ph_gaussian",
            "optimum_symbol": "pH_opt_env",
            "width_symbol": "pH_width_env",
            "source": "FungMod configured environment-modifier software benchmark.",
        },
    ]


def test_configured_model_runs_with_explicit_oxygen_water_activity_modifiers(tmp_path) -> None:
    config_path = _oxygen_water_modified_homogeneous_config(tmp_path)

    base = run_configured_model(MODEL_CONFIGS / "toy_homogeneous_ab.yml", output_dir=tmp_path / "base")
    modified = run_configured_model(config_path, output_dir=tmp_path / "oxygen_water_modified")

    assumptions = json.loads((tmp_path / "oxygen_water_modified" / "assumptions.json").read_text(encoding="utf-8"))
    metadata = json.loads((tmp_path / "oxygen_water_modified" / "configured_metadata.json").read_text(encoding="utf-8"))
    process_config = json.loads(
        (tmp_path / "oxygen_water_modified" / "input_model_config.json").read_text(encoding="utf-8")
    )["processes"][0]
    merged_parameters = json.loads(
        (tmp_path / "oxygen_water_modified" / "merged_parameters.json").read_text(encoding="utf-8")
    )

    assert "a_to_b" in modified.process_rates
    assert modified.process_rates["a_to_b"].magnitude[0] != pytest.approx(base.process_rates["a_to_b"].magnitude[0])
    assert any(item["name"] == "oxygen Monod limitation modifier" for item in assumptions)
    assert any(item["name"] == "minimum water activity threshold" for item in assumptions)
    assert metadata["configured_process_modifiers"] == [
        {
            "process_id": "a_to_b",
            "modifier_index": 0,
            "type": "oxygen_monod",
            "environment_value": "oxygen_concentration",
            "half_saturation_symbol": "K_O2_env",
            "oxygen_units": "mole / liter",
            "maturity": "exploratory_configured_mechanism",
            "limitation": (
                "Monod oxygen scaling only; configured only when environment oxygen concentration "
                "and explicit positive unit-compatible half-saturation are present. No oxygen consumption, "
                "gas transfer, redox balance, or anaerobic metabolism."
            ),
        },
        {
            "process_id": "a_to_b",
            "modifier_index": 1,
            "type": "water_activity_threshold",
            "environment_value": "water_activity",
            "minimum_water_activity_symbol": "a_w_min_env",
            "maturity": "exploratory_configured_mechanism",
            "limitation": (
                "Binary water-activity threshold scaling only; configured only when environment water activity "
                "and an explicit unit-compatible threshold parameter are present. No smooth response curve, "
                "hysteresis, substrate water binding, or spatial moisture model."
            ),
        },
    ]
    assert process_config["modifiers"] == [
        {
            "type": "oxygen_monod",
            "half_saturation_symbol": "K_O2_env",
            "oxygen_units": "mole / liter",
            "source": "FungMod configured oxygen-water modifier software benchmark.",
        },
        {
            "type": "water_activity_threshold",
            "minimum_water_activity_symbol": "a_w_min_env",
            "source": "FungMod configured oxygen-water modifier software benchmark.",
        },
    ]
    assert {item["symbol"] for item in merged_parameters["parameters"]}.issuperset({"K_O2_env", "a_w_min_env"})


def test_configured_environment_modifier_requires_explicit_parameters(tmp_path) -> None:
    config_path = _environment_modified_homogeneous_config(tmp_path, include_ph_width_parameter=False)

    with pytest.raises(ConfiguredModelExecutionError) as exc_info:
        run_configured_model(config_path, output_dir=tmp_path / "missing_environment_modifier_parameter")

    report = exc_info.value.report.to_dict()
    assert report["stage"] == "model_assembly"
    assert "required_parameters" in report["missing_capabilities"]
    assert "pH_width_env" in json.dumps(report)


def test_configured_oxygen_water_modifiers_require_explicit_parameters(tmp_path) -> None:
    missing_oxygen = _oxygen_water_modified_homogeneous_config(tmp_path, include_oxygen_half_parameter=False)
    missing_water_activity = _oxygen_water_modified_homogeneous_config(
        tmp_path,
        config_name="toy_homogeneous_missing_water_activity_parameter.yml",
        include_water_activity_parameter=False,
    )

    with pytest.raises(ConfiguredModelExecutionError) as oxygen_exc:
        run_configured_model(missing_oxygen, output_dir=tmp_path / "missing_oxygen_modifier_parameter")
    with pytest.raises(ConfiguredModelExecutionError) as water_exc:
        run_configured_model(missing_water_activity, output_dir=tmp_path / "missing_water_activity_parameter")

    oxygen_report = oxygen_exc.value.report.to_dict()
    water_report = water_exc.value.report.to_dict()
    assert oxygen_report["stage"] == "model_assembly"
    assert "required_parameters" in oxygen_report["missing_capabilities"]
    assert "K_O2_env" in json.dumps(oxygen_report)
    assert water_report["stage"] == "model_assembly"
    assert "required_parameters" in water_report["missing_capabilities"]
    assert "a_w_min_env" in json.dumps(water_report)


def test_configured_environment_modifier_requires_environment_value(tmp_path) -> None:
    config_path = _environment_modified_homogeneous_config(tmp_path, include_environment_ph=False)

    with pytest.raises(ConfiguredModelExecutionError) as exc_info:
        run_configured_model(config_path, output_dir=tmp_path / "missing_environment_value")

    report = exc_info.value.report.to_dict()
    assert report["stage"] == "model_execution"
    assert "does not define pH" in report["message"]


def test_configured_oxygen_water_modifiers_require_environment_values(tmp_path) -> None:
    missing_oxygen = _oxygen_water_modified_homogeneous_config(tmp_path, include_environment_oxygen=False)
    missing_water_activity = _oxygen_water_modified_homogeneous_config(
        tmp_path,
        config_name="toy_homogeneous_without_water_activity.yml",
        include_environment_water_activity=False,
    )

    with pytest.raises(ConfiguredModelExecutionError) as oxygen_exc:
        run_configured_model(missing_oxygen, output_dir=tmp_path / "missing_oxygen_value")
    with pytest.raises(ConfiguredModelExecutionError) as water_exc:
        run_configured_model(missing_water_activity, output_dir=tmp_path / "missing_water_activity_value")

    oxygen_report = oxygen_exc.value.report.to_dict()
    water_report = water_exc.value.report.to_dict()
    assert oxygen_report["stage"] == "model_execution"
    assert "does not define oxygen concentration" in oxygen_report["message"]
    assert water_report["stage"] == "model_execution"
    assert "does not define water activity" in water_report["message"]


def test_configured_environment_modifier_requires_environment_entity(tmp_path) -> None:
    config_path = _environment_modified_homogeneous_config(tmp_path, include_environment_entity=False)

    with pytest.raises(ConfiguredModelExecutionError) as exc_info:
        run_configured_model(config_path, output_dir=tmp_path / "missing_environment_entity")

    report = exc_info.value.report.to_dict()
    assert report["stage"] == "model_execution"
    assert "Explicit environment rate modifiers require an environment entity" in report["message"]


def test_configured_oxygen_water_modifiers_require_environment_entity(tmp_path) -> None:
    config_path = _oxygen_water_modified_homogeneous_config(tmp_path, include_environment_entity=False)

    with pytest.raises(ConfiguredModelExecutionError) as exc_info:
        run_configured_model(config_path, output_dir=tmp_path / "missing_oxygen_water_environment_entity")

    report = exc_info.value.report.to_dict()
    assert report["stage"] == "model_execution"
    assert "Explicit environment rate modifiers require an environment entity" in report["message"]


def test_configured_oxygen_modifier_rejects_non_positive_half_saturation(tmp_path) -> None:
    config_path = _oxygen_water_modified_homogeneous_config(tmp_path, oxygen_half_value=0.0)

    with pytest.raises(ConfiguredModelExecutionError) as exc_info:
        run_configured_model(config_path, output_dir=tmp_path / "bad_oxygen_half_saturation")

    report = exc_info.value.report.to_dict()
    assert report["stage"] == "model_execution"
    assert "Oxygen half-saturation must be positive" in report["message"]


def test_configured_oxygen_water_modifiers_require_explicit_config_fields(tmp_path) -> None:
    config_path = _oxygen_water_modified_homogeneous_config(tmp_path, include_oxygen_units_config=False)

    with pytest.raises(ConfiguredModelExecutionError) as exc_info:
        run_configured_model(config_path, output_dir=tmp_path / "missing_oxygen_units_config")

    report = exc_info.value.report.to_dict()
    assert report["stage"] == "process_factory_build"
    assert "process_factory_requirements" in report["missing_capabilities"]
    assert "oxygen_monod modifier requires oxygen_units" in report["message"]


def test_configured_model_rejects_unsupported_modifier_type(tmp_path) -> None:
    data = yaml.safe_load((MODEL_CONFIGS / "toy_homogeneous_ab.yml").read_text(encoding="utf-8"))
    data = deepcopy(data)
    data["processes"][0]["modifiers"] = [{"type": "not_supported"}]
    config_path = tmp_path / "toy_homogeneous_unsupported_modifier.yml"
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    with pytest.raises(ConfiguredModelExecutionError) as exc_info:
        run_configured_model(config_path, output_dir=tmp_path / "unsupported_modifier")

    report = exc_info.value.report.to_dict()
    assert report["stage"] == "process_factory_build"
    assert "process_factory_requirements" in report["missing_capabilities"]
    assert "Unsupported rate modifier type" in report["message"]


def test_configured_product_inhibition_requires_explicit_inhibition_constant(tmp_path) -> None:
    config_path = _product_inhibited_homogeneous_config(tmp_path, include_ki_parameter=False)

    with pytest.raises(ConfiguredModelExecutionError) as exc_info:
        run_configured_model(config_path, output_dir=tmp_path / "missing_ki")

    report = exc_info.value.report.to_dict()
    assert report["stage"] == "model_assembly"
    assert "required_parameters" in report["missing_capabilities"]
    assert "K_i_product" in json.dumps(report)


def test_configured_product_inhibition_rejects_non_positive_inhibition_constant(tmp_path) -> None:
    config_path = _product_inhibited_homogeneous_config(tmp_path, ki_value=0.0)

    with pytest.raises(ConfiguredModelExecutionError) as exc_info:
        run_configured_model(config_path, output_dir=tmp_path / "bad_ki")

    report = exc_info.value.report.to_dict()
    assert report["stage"] == "model_execution"
    assert "Product inhibition constant must be positive" in report["message"]


def test_parameter_merging_allows_identical_duplicates() -> None:
    first = ParameterSet([_parameter(symbol="k_merge", value=1.0)])
    second = ParameterSet([_parameter(symbol="k_merge", value=1.0)])

    merged = merge_parameter_sets([first, second])

    assert len(merged) == 1
    assert merged.get("k_merge").quantity.magnitude == pytest.approx(1.0)


def test_parameter_merging_rejects_conflicting_duplicates() -> None:
    first = ParameterSet([_parameter(symbol="k_merge", value=1.0)])
    second = ParameterSet([_parameter(symbol="k_merge", value=2.0)])

    with pytest.raises(ParameterMergeError, match="k_merge"):
        merge_parameter_sets([first, second])


def _parameter(*, symbol: str, value: float) -> Parameter:
    return Parameter(
        name="merge benchmark parameter",
        symbol=symbol,
        value=value,
        units="1 / second",
        uncertainty=0.0,
        source="FungMod merge benchmark.",
        confidence_level="testing",
        notes="Artificial value for parameter-merge tests.",
        measurement_method="defined benchmark value",
    )


def _product_inhibited_homogeneous_config(
    tmp_path: Path,
    *,
    include_ki_parameter: bool = True,
    ki_value: float = 0.35,
) -> Path:
    data = yaml.safe_load((MODEL_CONFIGS / "toy_homogeneous_ab.yml").read_text(encoding="utf-8"))
    data = deepcopy(data)
    parameters = data["parameters"][0]["parameters"]
    if include_ki_parameter:
        parameters.append(
            {
                "name": "toy product inhibition constant",
                "symbol": "K_i_product",
                "value": ki_value,
                "units": "kilogram",
                "uncertainty": 0.0,
                "source": "FungMod generic product inhibition configured benchmark.",
                "confidence_level": "testing",
                "notes": "Artificial value for configured product-inhibition tests.",
                "measurement_method": "defined benchmark value",
                "validity_range": "framework tests only",
            }
        )
    data["processes"][0]["modifiers"] = [
        {
            "type": "product_inhibition",
            "product_state": "released_product_amount",
            "inhibition_constant": "K_i_product",
        }
    ]
    config_path = tmp_path / "toy_homogeneous_product_inhibition.yml"
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return config_path


def _environment_modified_homogeneous_config(
    tmp_path: Path,
    *,
    include_ph_width_parameter: bool = True,
    include_environment_entity: bool = True,
    include_environment_ph: bool = True,
) -> Path:
    data = yaml.safe_load((MODEL_CONFIGS / "toy_homogeneous_ab.yml").read_text(encoding="utf-8"))
    data = deepcopy(data)
    parameters = data["parameters"][0]["parameters"]
    parameters.extend(
        [
            {
                "name": "toy Arrhenius activation energy",
                "symbol": "E_a_env",
                "value": 50000.0,
                "units": "joule / mole",
                "uncertainty": 0.0,
                "source": "FungMod configured environment-modifier software benchmark.",
                "confidence_level": "testing",
                "notes": "Artificial framework-benchmark value; not a fitted or biological temperature response.",
                "measurement_method": "defined benchmark value",
                "validity_range": "framework tests only",
            },
            {
                "name": "toy Arrhenius reference temperature",
                "symbol": "T_ref_env",
                "value": 293.15,
                "units": "kelvin",
                "uncertainty": 0.0,
                "source": "FungMod configured environment-modifier software benchmark.",
                "confidence_level": "testing",
                "notes": "Artificial framework-benchmark value; not a fitted or biological temperature response.",
                "measurement_method": "defined benchmark value",
                "validity_range": "framework tests only",
            },
            {
                "name": "toy pH optimum",
                "symbol": "pH_opt_env",
                "value": 6.0,
                "units": "dimensionless",
                "uncertainty": 0.0,
                "source": "FungMod configured environment-modifier software benchmark.",
                "confidence_level": "testing",
                "notes": "Artificial framework-benchmark value; not a fitted or biological pH response.",
                "measurement_method": "defined benchmark value",
                "validity_range": "framework tests only",
            },
        ]
    )
    if include_ph_width_parameter:
        parameters.append(
            {
                "name": "toy pH width",
                "symbol": "pH_width_env",
                "value": 1.5,
                "units": "dimensionless",
                "uncertainty": 0.0,
                "source": "FungMod configured environment-modifier software benchmark.",
                "confidence_level": "testing",
                "notes": "Artificial framework-benchmark value; not a fitted or biological pH response.",
                "measurement_method": "defined benchmark value",
                "validity_range": "framework tests only",
            }
        )
    data["processes"][0]["modifiers"] = [
        {
            "type": "temperature_arrhenius_reference",
            "activation_energy_symbol": "E_a_env",
            "reference_temperature_symbol": "T_ref_env",
            "source": "FungMod configured environment-modifier software benchmark.",
        },
        {
            "type": "ph_gaussian",
            "optimum_symbol": "pH_opt_env",
            "width_symbol": "pH_width_env",
            "source": "FungMod configured environment-modifier software benchmark.",
        },
    ]
    if not include_environment_entity:
        data["entities"]["environment"] = None
    elif not include_environment_ph:
        environment = yaml.safe_load((ROOT / "data" / "environments" / "lab_30C_pH7.yml").read_text(encoding="utf-8"))
        environment = deepcopy(environment)
        del environment["conditions"]["ph"]
        environment_path = tmp_path / "lab_30C_without_ph.yml"
        environment_path.write_text(yaml.safe_dump(environment, sort_keys=False), encoding="utf-8")
        data["entities"]["environment"]["path"] = str(environment_path)
    config_path = tmp_path / "toy_homogeneous_environment_modifiers.yml"
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return config_path


def _oxygen_water_modified_homogeneous_config(
    tmp_path: Path,
    *,
    config_name: str = "toy_homogeneous_oxygen_water_modifiers.yml",
    include_oxygen_half_parameter: bool = True,
    oxygen_half_value: float = 0.25,
    include_water_activity_parameter: bool = True,
    include_environment_entity: bool = True,
    include_environment_oxygen: bool = True,
    include_environment_water_activity: bool = True,
    include_oxygen_units_config: bool = True,
) -> Path:
    data = yaml.safe_load((MODEL_CONFIGS / "toy_homogeneous_ab.yml").read_text(encoding="utf-8"))
    data = deepcopy(data)
    parameters = data["parameters"][0]["parameters"]
    if include_oxygen_half_parameter:
        parameters.append(
            {
                "name": "toy oxygen half saturation",
                "symbol": "K_O2_env",
                "value": oxygen_half_value,
                "units": "mole / liter",
                "uncertainty": 0.0,
                "source": "FungMod configured oxygen-water modifier software benchmark.",
                "confidence_level": "testing",
                "notes": "Artificial framework-benchmark value; not fitted oxygen physiology or redox behavior.",
                "measurement_method": "defined benchmark value",
                "validity_range": "framework tests only",
            }
        )
    if include_water_activity_parameter:
        parameters.append(
            {
                "name": "toy minimum water activity",
                "symbol": "a_w_min_env",
                "value": 0.9,
                "units": "dimensionless",
                "uncertainty": 0.0,
                "source": "FungMod configured oxygen-water modifier software benchmark.",
                "confidence_level": "testing",
                "notes": "Artificial framework-benchmark value; not a fitted moisture response.",
                "measurement_method": "defined benchmark value",
                "validity_range": "framework tests only",
            }
        )
    oxygen_modifier = {
        "type": "oxygen_monod",
        "half_saturation_symbol": "K_O2_env",
        "source": "FungMod configured oxygen-water modifier software benchmark.",
    }
    if include_oxygen_units_config:
        oxygen_modifier["oxygen_units"] = "mole / liter"
    data["processes"][0]["modifiers"] = [
        oxygen_modifier,
        {
            "type": "water_activity_threshold",
            "minimum_water_activity_symbol": "a_w_min_env",
            "source": "FungMod configured oxygen-water modifier software benchmark.",
        },
    ]
    if not include_environment_entity:
        data["entities"]["environment"] = None
    elif not include_environment_oxygen or not include_environment_water_activity:
        environment = yaml.safe_load((ROOT / "data" / "environments" / "lab_30C_pH7.yml").read_text(encoding="utf-8"))
        environment = deepcopy(environment)
        if not include_environment_oxygen:
            del environment["conditions"]["oxygen_concentration"]
        if not include_environment_water_activity:
            del environment["conditions"]["water_activity"]
        environment_path = tmp_path / f"{Path(config_name).stem}_environment.yml"
        environment_path.write_text(yaml.safe_dump(environment, sort_keys=False), encoding="utf-8")
        data["entities"]["environment"]["path"] = str(environment_path)
    config_path = tmp_path / config_name
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return config_path


def _homogeneous_config_without_mass_balance(tmp_path: Path) -> Path:
    data = yaml.safe_load((MODEL_CONFIGS / "toy_homogeneous_ab.yml").read_text(encoding="utf-8"))
    data = deepcopy(data)
    data["validators"] = [
        validator
        for validator in data["validators"]
        if validator["validator_type"] != "mass_balance"
    ]
    config_path = tmp_path / "toy_homogeneous_without_mass_balance.yml"
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return config_path


def _entropy_timeseries_config(
    tmp_path: Path,
    *,
    process_id: str = "a_to_b",
    delta_gibbs_value: object = -50.0,
    delta_gibbs_units: str = "kilojoule / mole",
    temperature_value: float = 300.0,
    temperature_units: str = "kelvin",
    extent_rate_units: str = "mole / second",
    include_conversion: bool = True,
    conversion_value: float = 2.0,
    state_units: str = "kilogram",
    filename: str = "toy_process_entropy.yml",
) -> Path:
    data = yaml.safe_load((MODEL_CONFIGS / "toy_homogeneous_ab.yml").read_text(encoding="utf-8"))
    data = deepcopy(data)
    for state in data["initial_state"]["states"].values():
        state["units"] = state_units
    diagnostic = {
        "id": "a_to_b_entropy_rate",
        "process_id": process_id,
        "process_rate_interpretation": "reaction_extent_rate",
        "condition_specific_delta_gibbs": {
            "value": delta_gibbs_value,
            "units": delta_gibbs_units,
            "source": "Artificial framework-benchmark condition-specific delta Gibbs.",
        },
        "temperature": {
            "value": temperature_value,
            "units": temperature_units,
            "source": "Artificial framework-benchmark temperature.",
        },
        "extent_rate_units": extent_rate_units,
        "provenance_refs": ["framework-benchmark:process-entropy"],
    }
    if include_conversion:
        diagnostic["process_rate_to_extent_rate"] = {
            "value": conversion_value,
            "units": "mole / kilogram",
            "source": "Artificial framework-benchmark mass-to-extent conversion.",
        }
    data["outputs"]["entropy_production_rate_timeseries"] = [diagnostic]
    config_path = tmp_path / filename
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return config_path


def _expected_configured_output_files() -> tuple[str, ...]:
    return (
        "record.json",
        "model_assembly_report.json",
        "assumptions.json",
        "parameters.csv",
        "validation_report.json",
        "solver_report.json",
        "state_trajectories.csv",
        "process_rates.csv",
        "derived_quantities.csv",
        "figures/state_trajectories.png",
        "figures/process_rates.png",
        "figures/mass_balance.png",
        "logs/provenance_report.md",
        "input_model_config.json",
        "configured_model_run.json",
        "configured_metadata.json",
        "process_build_decisions.json",
        "initial_state.json",
        "time_grid.json",
        "validators.json",
        "conservation_diagnostics.json",
        "conservation_diagnostics.csv",
        "solver_diagnostics.json",
        "solver_diagnostics.csv",
        "merged_parameters.json",
        "run_environment.json",
        "package_versions.json",
        "source_revision.json",
        "solver_settings.json",
        "entity_snapshots/index.json",
        "output_manifest.json",
    )
