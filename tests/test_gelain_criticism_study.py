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
    optimiser = study.OptimiserSettings.from_plan(plan["stage_A_least_squares"])
    with pytest.raises(CultureBenchmarkError, match="scenario"):
        study.fit_model(predictor, variant, conditions, scenario="bogus", starts=1, seed=1, max_nfev=2, optimiser=optimiser)
    with pytest.raises(CultureBenchmarkError, match="pin"):
        study.fit_model(
            predictor, variant, conditions, scenario="primary", starts=1, seed=1, max_nfev=2, optimiser=optimiser, fixed={"nope": 1.0}
        )


def test_optimiser_settings_come_from_the_plan_without_defaults(plan) -> None:
    stage = plan["stage_A_least_squares"]
    settings = study.OptimiserSettings.from_plan(stage)
    assert settings.diff_step == stage["optimiser"]["log_parameter_difference_step"] == 0.001
    assert settings.to_dict()["restart_relative_cost_tolerance"] == stage["optimiser"]["restart_relative_cost_tolerance"]
    with pytest.raises(CultureBenchmarkError, match="optimiser"):
        study.OptimiserSettings.from_plan({key: value for key, value in stage.items() if key != "optimiser"})
    partial = {**stage, "optimiser": {key: value for key, value in stage["optimiser"].items() if key != "ftol"}}
    with pytest.raises(CultureBenchmarkError, match="ftol"):
        study.OptimiserSettings.from_plan(partial)
    with pytest.raises(CultureBenchmarkError, match="diff_step"):
        study.OptimiserSettings(diff_step=0.0, ftol=1e-10, xtol=1e-10, gtol=1e-10, restarts=1, restart_tolerance=1e-6)
    with pytest.raises(CultureBenchmarkError, match="restarts"):
        study.OptimiserSettings(diff_step=1e-3, ftol=1e-10, xtol=1e-10, gtol=1e-10, restarts=-1, restart_tolerance=1e-6)


def test_recorded_m0_primary_fit_is_stationary_within_its_bounds(registry, plan, bayesian_plan, conditions) -> None:
    """The recorded all-condition M0 optimum has a small projected cost gradient in log space.

    Central differences with the plan's difference step; coordinates on a
    bound whose gradient points outward are projected out. The point the
    first stage A run recorded (before amendment 3) had a projected gradient
    norm of 0.22 and was 1.3 percent above the minimum COPASI found.
    """

    fit_path = ROOT / study.PLAN_PATH.parent / "results" / "stage_a" / "M0_baseline" / "full_fit_primary.json"
    if not fit_path.exists():
        pytest.skip("no stage A results recorded yet")
    fit = json.loads(fit_path.read_text(encoding="utf-8"))
    current = hashlib.sha256((ROOT / study.PLAN_PATH).read_bytes()).hexdigest()
    since_amendment_3 = {current, *(entry["previous_sha256"] for entry in plan["amendments"][3:])}
    assert fit["success"] and fit["plan_sha256"] in since_amendment_3
    variant = study.model_variants(plan)["M0_baseline"]
    predictor = study.build_predictor(registry, plan, "M0_baseline", bayesian_plan=bayesian_plan)
    scales = study.training_scales(conditions)
    free = list(variant.parameters)
    lower, upper = variant.log_bounds()

    def cost(log_values: np.ndarray) -> float:
        values = {spec.symbol: float(value) for spec, value in zip(free, np.exp(log_values), strict=True)}
        config_values = variant.config_values(values)
        residuals = np.concatenate(
            [((predictor.predict_values(config_values, c.condition_id, c.times) - c.observed) / scales).ravel() for c in conditions]
        )
        return 0.5 * float(residuals @ residuals)

    point = np.log([float(entry["value"]) for entry in fit["parameters"]])
    assert cost(point) == pytest.approx(fit["cost"], rel=1e-9)
    step = float(plan["stage_A_least_squares"]["optimiser"]["log_parameter_difference_step"])
    gradient = np.zeros_like(point)
    for index in range(point.size):
        unit = np.zeros_like(point)
        unit[index] = step
        gradient[index] = (cost(point + unit) - cost(point - unit)) / (2.0 * step)
    on_lower = (point - lower < 1e-6) & (gradient > 0.0)
    on_upper = (upper - point < 1e-6) & (gradient < 0.0)
    projected = np.where(on_lower | on_upper, 0.0, gradient)
    assert float(np.linalg.norm(projected)) < 1e-2
    assert {spec.symbol for spec, flag in zip(free, on_lower, strict=True) if flag} <= set(fit["diagnostics"]["near_bounds"])


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
    full = json.loads((tmp_path / "stage_a" / "M0_baseline" / "full_fit_primary.json").read_text(encoding="utf-8"))
    assert full["optimiser"] == study.OptimiserSettings.from_plan(plan["stage_A_least_squares"]).to_dict() == inputs["optimiser"]
    assert len(full["restarts"]) <= plan["stage_A_least_squares"]["optimiser"]["restarts"]
    assert all({"restart", "success"} <= set(entry) for entry in full["restarts"])
    assert all("relative_cost_decrease" in entry for entry in full["restarts"] if entry["success"])
    report = (tmp_path / "stage_a" / "report.md").read_text(encoding="utf-8")
    assert "biological validation" in report and "M3_conversion_dependent_accessibility" in report
    assert "finite-difference step 0.001" in report


def test_stage_a_reuses_existing_files_for_the_same_plan_digest(tmp_path: Path, registry) -> None:
    first = study.run_stage_a(
        ROOT, output_dir=tmp_path, registry=registry, models=["M0_baseline"], scenarios=["primary"], starts=1, max_nfev=3, profiles=False,
    )
    log: list[str] = []
    second = study.run_stage_a(
        ROOT, output_dir=tmp_path, registry=registry, models=["M0_baseline"], scenarios=["primary"], starts=1, max_nfev=3, profiles=False,
        log=log.append,
    )
    assert any("reusing" in line for line in log)
    assert second["models"]["M0_baseline"]["scenarios"]["primary"] == first["models"]["M0_baseline"]["scenarios"]["primary"]
    full = json.loads((tmp_path / "stage_a" / "M0_baseline" / "full_fit_primary.json").read_text(encoding="utf-8"))
    assert full["plan_sha256"] == first["inputs"]["plan_sha256"]
    # a different digest must not be reused
    (tmp_path / "stage_a" / "M0_baseline" / "full_fit_primary.json").write_text(json.dumps({**full, "plan_sha256": "0" * 64}), encoding="utf-8")
    assert study._existing_stage_a_files(tmp_path / "stage_a" / "M0_baseline", ["primary"], first["inputs"]["plan_sha256"]) is None  # noqa: SLF001


@pytest.mark.parametrize("model_id", ["M1_induction_state", "M3_conversion_dependent_accessibility"])
def test_posterior_study_is_finite_at_a_candidate_for_variants_with_fixed_constants(registry, plan, model_id) -> None:
    """The sampler supplies only the fitted symbols; the variant's fixed constants must still reach the config."""

    variant = study.model_variants(plan)[model_id]
    if model_id == "M1_induction_state":
        assert variant.fixed, "M1 declares a fixed constant; the regression needs one"
    center = candidate_values(variant)
    posterior = study.build_posterior_study(ROOT, model_id, center, registry=registry)
    assert set(posterior.predictor.fitted_symbols) == set(variant.config_symbols)
    assert all(fixed.config_symbol not in posterior.problem.labels for fixed in variant.fixed)
    vector = posterior.problem.coordinates_from_values(posterior.center)
    assert posterior.problem.inside(vector)
    assert np.isfinite(posterior.problem.log_posterior(vector))


def test_sampler_settings_apply_the_declared_overrides(plan) -> None:
    base = study.sampler_settings(plan, dimension=10)
    assert (base.n_steps, base.burn_in, base.n_walkers) == (8000, 2000, 24)
    m2 = study.sampler_settings(plan, dimension=14, model_id="M2_soluble_product_pool")
    assert (m2.n_steps, m2.burn_in, m2.n_walkers) == (36000, 8000, 28)
    m1 = study.sampler_settings(plan, dimension=11, model_id="M1_induction_state")
    assert (m1.n_steps, m1.burn_in) == (8000, 2000)
    holdout = study.sampler_settings(plan, dimension=14, model_id="M2_soluble_product_pool", holdout=True)
    assert (holdout.n_steps, holdout.burn_in, holdout.n_walkers) == (8000, 2000, 28)
    development = study.sampler_settings(plan, dimension=14, model_id="M2_soluble_product_pool", n_steps=6, burn_in=2)
    assert (development.n_steps, development.burn_in) == (6, 2)
    stripped = {**plan, "stage_B_posterior": {k: v for k, v in plan["stage_B_posterior"].items() if k != "holdout_sampler"}}
    with pytest.raises(CultureBenchmarkError, match="holdout_sampler"):
        study.sampler_settings(stripped, dimension=14, holdout=True)


def test_holdout_posterior_study_scores_the_held_out_loading(tmp_path: Path, registry, plan) -> None:
    """A holdout study fits two loadings, keeps the third apart and reports its coverage separately (tiny budget)."""

    model_id = "M3_conversion_dependent_accessibility"
    variant = study.model_variants(plan)[model_id]
    center = candidate_values(variant)
    held = "gelain_2020_cellulose_20gl"
    posterior = study.build_posterior_study(ROOT, model_id, center, registry=registry, held_out=held, n_steps=6, burn_in=2)
    assert [condition.condition_id for condition in posterior.problem.conditions] == [
        "gelain_2020_cellulose_10gl", "gelain_2020_cellulose_30gl"
    ]
    assert [condition.condition_id for condition in posterior.held_out] == [held]
    with pytest.raises(CultureBenchmarkError, match="held-out"):
        study.build_posterior_study(ROOT, model_id, center, registry=registry, held_out="nope")
    output = tmp_path / "stage_b" / model_id / f"holdout_{held}"
    run = study.sample_posterior_study(posterior, output, checkpoint_every=3, resume=False)
    assert run.chain.shape[1] == 6
    result, coverage = study.analyze_posterior_study(posterior, run, draws=4)
    assert coverage is not None and coverage["held_out"] == [] and set(coverage["conditions"]) == {
        "gelain_2020_cellulose_10gl", "gelain_2020_cellulose_30gl"
    }
    held_coverage = coverage["held_out_coverage"]
    assert held_coverage["held_out"] == [held] and set(held_coverage["conditions"]) == {held}
    assert held_coverage["overall"]["all_observables"]["observations"] == 32
    assert result.posterior_predictive is not None and result.posterior_predictive["held_out"] == [held]
    paths = study.write_posterior_outputs(posterior, result, coverage, output, root=ROOT)
    inputs = json.loads(paths["inputs"].read_text(encoding="utf-8"))
    assert inputs["held_out_conditions"] == [held] and held not in inputs["fitted_conditions"]
    report = paths["report"].read_text(encoding="utf-8")
    assert "Holdout posterior" in report and "Held-out posterior predictive coverage" in report
    assert "provisional" in report


def test_stage_b_verdicts_follow_the_plan_rules(plan) -> None:
    """R2 and R3 from a synthetic result; R1 from a recorded stage A screen; provisional when not converged."""

    class _Result:
        def __init__(self, converged: bool, classes: dict[str, str], multiplier: tuple[float, float]) -> None:
            self.converged = converged
            self.identifiability = {symbol: {"class": klass} for symbol, klass in classes.items()}
            self.summaries = {"noise_scale:all_observables": {"lower": multiplier[0], "upper": multiplier[1], "median": sum(multiplier) / 2}}

    plan_data = plan

    class _Study:
        plan = plan_data
        model_id = "M3_conversion_dependent_accessibility"

    comparison = {"models": {"M3_conversion_dependent_accessibility": {"scenarios": {"primary": {"screen": {"passed": True}}}}}}
    verdict = study.stage_b_verdicts(_Study(), _Result(False, {"gelain_criticism_n": "identified"}, (0.9, 1.4)), stage_a_comparison=comparison)
    assert verdict["provisional"] is True
    assert verdict["R1_holdout_support"] is True and verdict["R2_adequacy"] is True and verdict["R3_identification"] is True
    assert verdict["outcome"] == "supported (R1 and R3)"
    assert verdict["added_parameter_classes"] == {"n": "identified"}
    unidentified = study.stage_b_verdicts(_Study(), _Result(True, {"gelain_criticism_n": "bounded_below_only"}, (1.5, 2.5)), stage_a_comparison=comparison)
    assert unidentified["provisional"] is False and unidentified["R2_adequacy"] is False
    assert unidentified["outcome"] == "improves fit but unidentified (R1, not R3)"
    failed = {"models": {"M3_conversion_dependent_accessibility": {"scenarios": {"primary": {"screen": {"passed": False}}}}}}
    assert study.stage_b_verdicts(_Study(), _Result(True, {"gelain_criticism_n": "identified"}, (0.9, 1.4)), stage_a_comparison=failed)["outcome"] == "not supported (fails R1)"
    assert study.stage_b_verdicts(_Study(), _Result(True, {}, (0.9, 1.4)))["outcome"] == "not scored (stage A screen not recorded)"
