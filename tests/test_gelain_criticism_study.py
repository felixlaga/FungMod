"""The Gelain model-criticism study: variants compose from the registry case and stage A runs under the frozen plan."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from fungal_model.core.numerics import solve_checked
from fungal_model.core.units import assert_compatible
from fungal_model.registry import load_registry
from fungal_model.research import gelain_bayesian
from fungal_model.research import gelain_criticism as study
from fungal_model.research.gelain_culture import CultureBenchmarkError
from fungal_model.solvers.compiled import compile_assembled_model, resolve_state_units
from fungal_model.workflows.configured_inputs import ConfiguredInputLoader
from fungal_model.workflows.configured_processes import ConfiguredProcessAssembler

ROOT = Path(__file__).resolve().parents[1]
MODELS = ("M0_baseline", "M1_induction_state", "M2_soluble_product_pool", "M3_conversion_dependent_accessibility")
ADDED_VALUES = {"kz_loss": 0.05, "mu": 0.2, "Ks": 0.5, "Ki": 10.0, "P0": 0.5, "n": 1.0}


@pytest.fixture(scope="module")
def registry():
    return load_registry(ROOT / study.REGISTRY_INDEX)


@pytest.fixture(scope="module")
def plan():
    return study.load_plan(ROOT)


@pytest.fixture(scope="module")
def bayesian_plan():
    return gelain_bayesian.load_plan(ROOT)


@pytest.fixture(scope="module")
def conditions(plan):
    return study.observed_conditions(ROOT, plan)


def frozen_common_values() -> dict[str, float]:
    fit = json.loads((ROOT / gelain_bayesian.FROZEN_FIT_PATH).read_text(encoding="utf-8"))
    return {entry["symbol"]: float(entry["value"]) for entry in fit["parameters"]}


def frozen_config_values() -> dict[str, float]:
    return {f"gelain_hydrolysis_{symbol}": value for symbol, value in frozen_common_values().items()}


def candidate_values(variant: study.ModelVariant) -> dict[str, float]:
    values = study.midpoint_values(variant)
    values.update({symbol: value for symbol, value in frozen_common_values().items() if symbol in values})
    values.update({symbol: value for symbol, value in ADDED_VALUES.items() if symbol in values})
    return values


def test_plan_models_map_to_variants_with_flagged_additions(plan) -> None:
    variants = study.model_variants(plan)
    assert tuple(variants) == MODELS
    for variant in variants.values():
        for spec in variant.parameters:
            if spec.new:
                assert spec.config_symbol == f"gelain_criticism_{spec.symbol}"
            else:
                assert spec.config_symbol == f"gelain_hydrolysis_{spec.symbol}"
        assert variant.config_values(candidate_values(variant))
    assert [spec.symbol for spec in variants["M0_baseline"].parameters if spec.new] == []
    assert [item.symbol for item in variants["M1_induction_state"].fixed] == ["k_z"]
    with pytest.raises(CultureBenchmarkError, match="missing"):
        variants["M2_soluble_product_pool"].config_values({"k_h": 0.01})


def test_baseline_variant_reproduces_the_bayesian_study_predictor_at_the_frozen_fit(registry, plan, bayesian_plan, conditions) -> None:
    predictor = study.build_predictor(registry, plan, "M0_baseline", bayesian_plan=bayesian_plan)
    reference = gelain_bayesian.build_predictor(registry, bayesian_plan)
    values = frozen_config_values()
    for condition in conditions:
        ours = predictor.predict_values(values, condition.condition_id, condition.times)
        theirs = reference.predict_values(values, condition.condition_id, condition.times)
        np.testing.assert_allclose(ours, theirs, rtol=1e-10, atol=1e-12)


@pytest.mark.parametrize("model_id", MODELS)
def test_every_variant_integrates_and_closes_its_declared_mass_balance(registry, plan, bayesian_plan, conditions, model_id) -> None:
    variant = study.model_variants(plan)[model_id]
    predictor = study.build_predictor(registry, plan, model_id, bayesian_plan=bayesian_plan)
    values = variant.config_values(candidate_values(variant))
    condition = conditions[1]
    predicted = predictor.predict_values(values, condition.condition_id, condition.times)
    assert predicted.shape == condition.observed.shape and np.all(np.isfinite(predicted))
    assert np.all(predicted >= -1e-9)
    config = predictor._conditions[condition.condition_id].config_factory(values)  # noqa: SLF001
    weights = next(v for v in config.raw["validators"] if v["validator_type"] == "mass_balance")["conserved_weights"]
    inputs = ConfiguredInputLoader().load(config)
    model = ConfiguredProcessAssembler().assemble(config, inputs).model
    units = resolve_state_units(model)
    names = list(units)
    initial = np.array([float(assert_compatible(inputs.initial_state[name], unit, name=name).magnitude) for name, unit in units.items()])
    compiled = compile_assembled_model(model, time_units="hour")
    solution = solve_checked(compiled.rhs, (0.0, 96.0), initial, t_eval=np.array([0.0, 48.0, 96.0]), **model.solver_settings.scipy_options(units, "hour"))
    conserved = sum(float(weight) * solution.y[names.index(state)] for state, weight in weights.items())
    np.testing.assert_allclose(conserved, conserved[0], rtol=1e-6)
    if model_id == "M2_soluble_product_pool":
        assert study.SOLUBLE_PRODUCT_STATE in weights and names.index(study.SOLUBLE_PRODUCT_STATE) >= 0
    if model_id == "M1_induction_state":
        assert study.INDUCED_POOL_STATE in names and study.INDUCED_POOL_STATE not in weights


def test_variant_configs_declare_their_additions_honestly(registry, plan, bayesian_plan, conditions) -> None:
    variants = study.model_variants(plan)
    configs = {}
    for model_id in MODELS:
        predictor = study.build_predictor(registry, plan, model_id, bayesian_plan=bayesian_plan)
        values = variants[model_id].config_values(candidate_values(variants[model_id]))
        configs[model_id] = predictor._conditions[conditions[0].condition_id].config_factory(values).raw  # noqa: SLF001
    base = configs["M0_baseline"]
    assert base["mode"] == "scientific" and len(base["processes"]) == 6
    for model_id in MODELS[1:]:
        raw = configs[model_id]
        assert raw["mode"] == "exploratory" and raw["maturity"] == "exploratory"
        added = [entry for entry in raw["parameters"][0]["parameters"] if entry["symbol"].startswith("gelain_criticism_")]
        assert added and all(entry["source"] == study.STUDY_SOURCE and entry["confidence_level"] == "low" for entry in added)
    hydrolysis = lambda raw: next(p for p in raw["processes"] if p["id"] == study.HYDROLYSIS_PROCESS)  # noqa: E731
    assert hydrolysis(configs["M2_soluble_product_pool"])["modifiers"][0]["type"] == "product_inhibition"
    assert hydrolysis(configs["M2_soluble_product_pool"])["product_map"] == "cellulose_to_soluble_product"
    uptake = next(p for p in configs["M2_soluble_product_pool"]["processes"] if p["id"] == "soluble_product_uptake")
    yield_map = next(m for m in configs["M2_soluble_product_pool"]["entities"]["product_maps"] if m["id"] == uptake["product_map"])
    assert yield_map["data"]["products"][study.BIOMASS_STATE] == pytest.approx(frozen_common_values()["Y"])
    assert {entry["symbol"]: entry["value"] for entry in configs["M2_soluble_product_pool"]["parameters"][0]["parameters"]}[
        study.UPTAKE_CAPACITY_SYMBOL
    ] == pytest.approx(0.2 / frozen_common_values()["Y"])
    modifier = hydrolysis(configs["M3_conversion_dependent_accessibility"])["modifiers"][0]
    assert modifier["type"] == "substrate_reactivity" and modifier["reference_concentration"] == study.INITIAL_LOADING_SYMBOL
    assert len([p for p in configs["M1_induction_state"]["processes"] if p["id"].startswith("induction_state")]) == 2


def test_score_predictions_reports_the_v2_statistics() -> None:
    predicted = np.array([[1.0, 10.0], [2.0, 20.0]])
    observed = np.array([[1.5, 10.0], [2.5, 25.0]])
    score = study.score_predictions(predicted, observed, ("a", "b"), np.array([2.0, 50.0]))
    assert score["rmse"]["a"] == pytest.approx(0.5) and score["bias"]["a"] == pytest.approx(-0.5)
    assert score["normalized_mse"]["b"] == pytest.approx(((0.0) ** 2 + (5.0 / 50.0) ** 2) / 2)
    with pytest.raises(CultureBenchmarkError):
        study.score_predictions(predicted, observed, ("a", "b"), np.array([2.0, 0.0]))


def test_fit_model_rejects_unknown_scenarios_and_pins(registry, plan, bayesian_plan, conditions) -> None:
    variant = study.model_variants(plan)["M0_baseline"]
    predictor = study.build_predictor(registry, plan, "M0_baseline", bayesian_plan=bayesian_plan)
    with pytest.raises(CultureBenchmarkError, match="scenario"):
        study.fit_model(predictor, variant, conditions, scenario="bogus", starts=1, seed=1, max_nfev=2)
    with pytest.raises(CultureBenchmarkError, match="pin"):
        study.fit_model(predictor, variant, conditions, scenario="primary", starts=1, seed=1, max_nfev=2, fixed={"nope": 1.0})


def test_stage_a_runs_end_to_end_on_a_tiny_budget(tmp_path: Path, registry, plan) -> None:
    comparison = study.run_stage_a(
        ROOT, output_dir=tmp_path, registry=registry, models=["M3_conversion_dependent_accessibility"],
        scenarios=["primary"], starts=1, max_nfev=4, profiles=False,
    )
    assert list(comparison["models"]) == ["M0_baseline", "M3_conversion_dependent_accessibility"]
    inputs = json.loads((tmp_path / "stage_a" / "inputs.json").read_text(encoding="utf-8"))
    assert inputs["plan_sha256"] == hashlib.sha256((ROOT / study.PLAN_PATH).read_bytes()).hexdigest()
    assert inputs["amendments"] == plan["amendments"]
    for model_id in comparison["models"]:
        folds = json.loads((tmp_path / "stage_a" / model_id / "folds_primary.json").read_text(encoding="utf-8"))
        assert [fold["condition"] for fold in folds] == [c for c in inputs and ("gelain_2020_cellulose_10gl", "gelain_2020_cellulose_20gl", "gelain_2020_cellulose_30gl")]
        for fold in folds:
            frozen_path = tmp_path / fold["frozen_prediction_file"]
            assert hashlib.sha256(frozen_path.read_bytes()).hexdigest() == fold["frozen_prediction_sha256"]
            frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
            assert frozen["plan_sha256"] == inputs["plan_sha256"] and fold["condition"] not in fold["fit"]["training_conditions"]
            assert set(fold["score"]) == {"rmse", "bias", "normalized_mse", "n"}
        summary = comparison["models"][model_id]["scenarios"]["primary"]
        assert summary["folds_scored"] == 3 and np.isfinite(summary["mean_normalized_mse"])
    assert comparison["models"]["M0_baseline"]["scenarios"]["primary"]["screen"]["reasons"] == ["baseline"]
    screen = comparison["models"]["M3_conversion_dependent_accessibility"]["scenarios"]["primary"]["screen"]
    assert isinstance(screen["passed"], bool) and "relative_improvement" in screen
    report = (tmp_path / "stage_a" / "report.md").read_text(encoding="utf-8")
    assert "biological validation" in report and "M3_conversion_dependent_accessibility" in report
