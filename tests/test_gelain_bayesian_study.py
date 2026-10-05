"""Posterior-sampling study of the T. harzianum cellulose registry case.

These tests pin the study's inputs (plan, priors, observations, error
assumptions), prove the pipeline runs end to end on the compiled core with
checkpoint and resume, and keep the frozen artifact consistent with the
registry records that cite it. They do not re-run the full chain.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import yaml

from fungal_model.calibration.bayesian import IDENTIFIABILITY_CLASSES, IDENTIFIED, NOISE_SCALE_PREFIX
from fungal_model.research.gelain_culture import CultureBenchmarkError
from fungal_model.registry import load_registry
from fungal_model.research import gelain_bayesian
from fungal_model.screening import build_model_config_from_registry_case
from fungal_model.workflows import run_configured_model

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "data" / "benchmarks" / "gelain_2020_bayesian" / "results"
VARIANT_PLAN_PATH = Path("data/benchmarks/gelain_2020_bayesian/plan_per_observable_scales.json")
VARIANT_RESULTS = ROOT / "data" / "benchmarks" / "gelain_2020_bayesian" / "results_per_observable_scales"
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"


@pytest.fixture(scope="module")
def registry():
    return load_registry(REGISTRY_INDEX)


@pytest.fixture(scope="module")
def plan():
    return gelain_bayesian.load_plan(ROOT)


def test_plan_priors_cover_the_registry_symbols_with_v2_bounds(plan) -> None:
    priors = gelain_bayesian.build_priors(ROOT, plan)
    v2 = json.loads((ROOT / gelain_bayesian.V2_PLAN_PATH).read_text(encoding="utf-8"))
    declared = {r["symbol"]: r for r in v2["models"]["cellulose"]["hydrolysis"]["parameters"]}
    assert len(priors) == 9 and all(prior.kind == "log_uniform" for prior in priors)
    reverse = {v: k for k, v in plan["priors"]["symbol_map"].items()}
    for prior in priors:
        bounds = declared[reverse[prior.symbol]]
        assert float(prior.lower.magnitude) == bounds["lower"] and float(prior.upper.magnitude) == bounds["upper"]
        assert str(prior.lower.units) == str(prior.upper.units)
    (scale,) = gelain_bayesian.build_noise_scale_priors(plan)
    assert scale.name == plan["error_model"]["noise_scale_priors"]["label"] == "all_observables"
    assert scale.observables == tuple(plan["observables"]) and scale.lower == 0.1 and scale.upper == 10.0
    variant = gelain_bayesian.load_plan(ROOT, VARIANT_PLAN_PATH)
    per_observable = gelain_bayesian.build_noise_scale_priors(variant)
    assert [prior.name for prior in per_observable] == list(plan["observables"])
    assert all(prior.observables == (prior.name,) for prior in per_observable)
    assert variant["observables"] == plan["observables"] and variant["priors"] == plan["priors"]
    assert variant["benchmark_id"] != plan["benchmark_id"]
    broken = json.loads(json.dumps(plan))
    broken["error_model"]["noise_scale_priors"]["structure"] = "arbitrary"
    with pytest.raises(CultureBenchmarkError, match="noise-scale structure"):
        gelain_bayesian.build_noise_scale_priors(broken)


def test_conditions_carry_the_published_means_and_the_declared_assumed_errors(plan) -> None:
    conditions = gelain_bayesian.load_cellulose_conditions(ROOT, plan)
    assert [condition.condition_id for condition in conditions] == plan["registry_case"]["condition_ids"]
    records = {r["condition_id"]: r for r in json.loads((ROOT / gelain_bayesian.OBSERVATIONS_PATH).read_text(encoding="utf-8"))}
    stacked = np.concatenate([condition.observed for condition in conditions], axis=0)
    maxima = stacked.max(axis=0)
    for condition in conditions:
        record = records[condition.condition_id]
        assert record["raw_replicates_available"] is False
        np.testing.assert_array_equal(condition.times, np.asarray(record["times_h"], dtype=float))
        assert condition.observed.shape == (8, 4)
        for column, name in enumerate(condition.observables):
            np.testing.assert_array_equal(condition.observed[:, column], record["observations"][name]["values"])
        assert condition.error.evidence == "assumed"
        sd, limits = condition.error.arrays(8)
        np.testing.assert_allclose(sd[0], 0.1 * maxima)
        assert np.all(np.isnan(limits))
        assert condition.error.correlation[0, 1] == -0.5 and condition.error.correlation[2, 3] == 0.0
    assert sum(condition.observed.size for condition in conditions) == 96


def test_predictor_reproduces_the_public_scientific_run_at_the_frozen_fit(registry, plan, tmp_path: Path) -> None:
    predictor = gelain_bayesian.build_predictor(registry, plan)
    base = gelain_bayesian.base_parameters_from_case(predictor, plan)
    center = gelain_bayesian.frozen_fit_center(ROOT, plan)
    values = {symbol: center[symbol] for symbol in predictor.fitted_symbols}
    for symbol in predictor.fitted_symbols:
        assert float(base.require_quantity(symbol).magnitude) == pytest.approx(values[symbol])
    config = build_model_config_from_registry_case(
        fungus_id=plan["registry_case"]["fungus_id"],
        substrate_id=plan["registry_case"]["substrate_id"],
        environment_id=plan["registry_case"]["environment_ids"][1],
        registry=registry,
        mode="scientific",
        output_directory=str(tmp_path / "bundle"),
    )
    config_path = tmp_path / "model_config.yml"
    config_path.write_text(yaml.safe_dump(config.to_dict(), sort_keys=False), encoding="utf-8")
    reference = run_configured_model(config_path, output_dir=tmp_path / "bundle")
    times = np.asarray(reference.time.to("hour").magnitude, dtype=float)[::8]
    predicted = predictor.predict_values(values, plan["registry_case"]["condition_ids"][1], times)
    for column, (name, spec) in enumerate(plan["observables"].items()):
        expected = np.asarray(reference.states[spec["state"]].to(spec["units"]).magnitude, dtype=float)[::8]
        np.testing.assert_allclose(predicted[:, column], expected, rtol=1e-8, atol=1e-9 * max(1.0, float(np.max(np.abs(expected)))), err_msg=name)
    shifted = predictor.predict_values({**values, "gelain_hydrolysis_Y": 0.2}, plan["registry_case"]["condition_ids"][1], times)
    assert np.max(np.abs(shifted[:, 0] - predicted[:, 0])) > 0.1, "the yield override must reach the product map"


def test_study_runs_end_to_end_with_checkpoint_and_resume(tmp_path: Path, registry) -> None:
    study = gelain_bayesian.build_study(ROOT, registry=registry, n_walkers=24, n_steps=6, burn_in=2)
    assert study.problem.dimension == 10 and study.settings.n_walkers == 24
    assert study.problem.labels[-1] == NOISE_SCALE_PREFIX + "all_observables"
    straight = gelain_bayesian.sample_study(study, tmp_path / "straight", checkpoint_every=0, log=None)
    interrupted = gelain_bayesian.build_study(ROOT, registry=registry, n_walkers=24, n_steps=3, burn_in=2)
    first = gelain_bayesian.sample_study(interrupted, tmp_path / "resumed", checkpoint_every=0)
    assert first.chain.shape == (24, 3, 10) and (tmp_path / "resumed" / gelain_bayesian.CHECKPOINT_NAME).exists()
    resumed = gelain_bayesian.sample_study(study, tmp_path / "resumed", checkpoint_every=0)
    np.testing.assert_array_equal(resumed.chain, straight.chain)
    np.testing.assert_array_equal(resumed.log_posterior, straight.log_posterior)
    assert resumed.evaluations == straight.evaluations
    assert np.all(np.isfinite(straight.log_posterior[:, -1]))
    result = gelain_bayesian.analyze_study(study, straight, with_predictive=False)
    assert set(result.identifiability) == set(plan_symbols(study.plan))
    assert all(verdict["class"] in IDENTIFIABILITY_CLASSES for verdict in result.identifiability.values())
    assert not result.converged and any("not converged" in note for note in result.notes)
    variant = gelain_bayesian.build_study(ROOT, registry=registry, n_walkers=28, n_steps=2, burn_in=1, plan_path=VARIANT_PLAN_PATH)
    assert variant.problem.dimension == 13 and variant.plan_path == VARIANT_PLAN_PATH
    assert variant.problem.labels[-4:] == tuple(NOISE_SCALE_PREFIX + name for name in variant.plan["observables"])
    assert variant.problem.data_digest() == study.problem.data_digest(), "the variant samples the same data"
    paths = gelain_bayesian.write_study_outputs(study, result, tmp_path / "straight", root=ROOT)
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    assert summary["noise_evidence"] == ["assumed", "estimated_from_residuals"]
    assert summary["observation_count"] == 96 and summary["conditions"] == study.plan["registry_case"]["condition_ids"]
    assert (tmp_path / "straight" / "report.md").read_text(encoding="utf-8").startswith("# gelain_2020_cellulose_bayesian_v1")
    artifacts = json.loads(paths["artifacts"].read_text(encoding="utf-8"))
    assert artifacts["posterior_samples.csv"] == hashlib.sha256(paths["samples"].read_bytes()).hexdigest()


def plan_symbols(plan) -> list[str]:
    return list(plan["priors"]["symbol_map"].values())


def test_frozen_artifact_is_consistent_with_its_inputs_and_the_registry(registry, plan) -> None:
    summary = json.loads((RESULTS / "bayesian_calibration.json").read_text(encoding="utf-8"))
    artifacts = json.loads((RESULTS / "artifacts.json").read_text(encoding="utf-8"))
    for name, digest in artifacts.items():
        assert hashlib.sha256((RESULTS / name).read_bytes()).hexdigest() == digest, name
    inputs = json.loads((RESULTS / "inputs.json").read_text(encoding="utf-8"))
    assert inputs["plan_sha256"] == hashlib.sha256((ROOT / gelain_bayesian.PLAN_PATH).read_bytes()).hexdigest()
    assert inputs["observations_sha256"] == hashlib.sha256((ROOT / gelain_bayesian.OBSERVATIONS_PATH).read_bytes()).hexdigest()
    study = gelain_bayesian.build_study(ROOT, registry=registry)
    assert summary["data_sha256"] == study.problem.data_digest()
    assert summary["parameters"] == plan_symbols(plan)
    assert summary["settings"]["n_walkers"] == plan["sampler"]["n_walkers"]
    assert summary["settings"]["n_steps"] == plan["sampler"]["n_steps"]
    assert summary["converged"] is True
    assert summary["diagnostics"]["failed_evaluations"] < summary["diagnostics"]["evaluations"]
    with (RESULTS / "posterior_samples.csv").open(encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == plan_symbols(plan) + [NOISE_SCALE_PREFIX + prior.name for prior in gelain_bayesian.build_noise_scale_priors(plan)]
    samples = np.asarray([[float(v) for v in row] for row in rows[1:]])
    assert samples.shape[0] >= 1000
    for index, symbol in enumerate(plan_symbols(plan)):
        verdict = summary["identifiability"][symbol]
        lower, upper = verdict["prior_bounds"]
        assert np.all(samples[:, index] >= lower) and np.all(samples[:, index] <= upper)
        median = float(np.median(samples[:, index]))
        assert verdict["credible_interval"][0] <= median <= verdict["credible_interval"][1]
        (record,) = registry.get_parameter_records(parameter_symbol=symbol)
        bayes = record.provenance["bayesian_identifiability"]
        assert bayes["artifact"] == "data/benchmarks/gelain_2020_bayesian/results/bayesian_calibration.json"
        assert bayes["artifact_sha256"] == artifacts["bayesian_calibration.json"]
        assert bayes["class"] == verdict["class"]
        assert bayes["credible_interval"] == verdict["credible_interval"]
        assert bayes["credible_mass"] == verdict["credible_mass"]
        assert bayes["posterior_median"] == summary["summaries"][symbol]["median"]
        assert record.value.is_exact, "point values are unchanged by the posterior study"
        point = float(record.value.value)
        assert bayes["point_value_inside_credible_interval"] == (verdict["credible_interval"][0] <= point <= verdict["credible_interval"][1])
    assert set(summary["identified_parameters"]) == {
        symbol for symbol, verdict in summary["identifiability"].items() if verdict["class"] == IDENTIFIED
    }
    assert set(summary["parameters_left_as_ranges"]) == set(plan_symbols(plan)) - set(summary["identified_parameters"])


def test_per_observable_variant_is_a_labelled_sensitivity_study_of_the_same_data(registry, plan) -> None:
    variant_plan = gelain_bayesian.load_plan(ROOT, VARIANT_PLAN_PATH)
    summary = json.loads((VARIANT_RESULTS / "bayesian_calibration.json").read_text(encoding="utf-8"))
    artifacts = json.loads((VARIANT_RESULTS / "artifacts.json").read_text(encoding="utf-8"))
    for name, digest in artifacts.items():
        assert hashlib.sha256((VARIANT_RESULTS / name).read_bytes()).hexdigest() == digest, name
    inputs = json.loads((VARIANT_RESULTS / "inputs.json").read_text(encoding="utf-8"))
    assert inputs["plan_path"] == str(VARIANT_PLAN_PATH)
    assert inputs["plan_sha256"] == hashlib.sha256((ROOT / VARIANT_PLAN_PATH).read_bytes()).hexdigest()
    primary = json.loads((RESULTS / "bayesian_calibration.json").read_text(encoding="utf-8"))
    assert summary["data_sha256"] == primary["data_sha256"], "both studies sample the same observations"
    assert summary["parameters"] == primary["parameters"] == plan_symbols(plan)
    assert summary["noise_scales"] == {name: [name] for name in variant_plan["observables"]}
    assert primary["noise_scales"] == {"all_observables": list(plan["observables"])}
    assert summary["settings"]["n_steps"] == variant_plan["sampler"]["n_steps"]
    assert summary["converged"] is False and any("sensitivity variant" in note for note in summary["notes"])
    for symbol in plan_symbols(plan):
        (record,) = registry.get_parameter_records(parameter_symbol=symbol)
        cited = record.provenance["bayesian_identifiability"]
        assert cited["benchmark_id"] == plan["benchmark_id"] != variant_plan["benchmark_id"]
        assert "per_observable" not in cited["artifact"], "the registry cites only the primary study"
