"""Artificial, analytic tests of posterior sampling and identifiability reporting.

No experimental or biological evidence: every model here is a software
fixture with declared artificial noise.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pytest

from fungal_model.calibration import (
    DEFAULT_IDENTIFIABILITY_CRITERIA,
    ConfiguredCondition,
    ConfiguredConditionPredictor,
    IdentifiabilityCriteria,
    NoiseScalePrior,
    ObservableMapping,
    ObservedCondition,
    PriorSpecification,
    SamplerSettings,
    analyze_run,
    build_bayesian_problem,
    classify_identifiability,
    inline_parameter_config_factory,
    integrated_autocorrelation_time,
    local_information_analysis,
    pooled_replicate_standard_deviation,
    posterior_predictive,
    prior_from_bounds,
    run_ensemble_sampler,
    sample_posterior,
)
from fungal_model.calibration.bayesian import (
    BOUNDED_ABOVE_ONLY,
    BOUNDED_BELOW_ONLY,
    IDENTIFIED,
    NOISE_SCALE_EVIDENCE,
    NOISE_SCALE_PREFIX,
    PRIOR_DOMINATED,
    WEAKLY_IDENTIFIED,
    initial_ensemble,
    parameter_for_testing,
)
from fungal_model.calibration.observation_error import GaussianObservationError
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.provenance import ProvenanceError
from fungal_model.core.units import Q_
from fungal_model.io.model_config import load_model_config
from fungal_model.workflows import run_configured_model

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "Artificial analytic fixture with declared Gaussian noise; software test only."
X = np.arange(5, dtype=float)


def gaussian_error(observable: str, sd: float, n: int | None = None, *, evidence: str = "assumed") -> GaussianObservationError:
    deviation = Q_(sd if n is None else np.full(n, sd), "dimensionless")
    return GaussianObservationError(
        (observable,),
        ("dimensionless",),
        {observable: deviation},
        np.eye(1),
        SOURCE,
        evidence,
    )


def linear_predict(parameters: ParameterSet, condition_id: str, times: np.ndarray) -> np.ndarray:
    a = float(parameters.require_quantity("a").magnitude)
    b = float(parameters.require_quantity("b").magnitude)
    return (a * times + b)[:, None]


def linear_problem(observed: np.ndarray, *, sd: float = 0.5, noise_scale: bool = False, scalar_sd: bool = False):
    base = ParameterSet([parameter_for_testing("a", 1.0), parameter_for_testing("b", 1.0)])
    priors = [
        prior_from_bounds(symbol="a", lower=-10.0, upper=10.0, units="dimensionless", source=SOURCE, kind="uniform"),
        prior_from_bounds(symbol="b", lower=-10.0, upper=10.0, units="dimensionless", source=SOURCE, kind="uniform"),
    ]
    condition = ObservedCondition("line", X, observed[:, None], gaussian_error("y", sd, None if scalar_sd else X.size))
    scales = [NoiseScalePrior(("y",), 0.1, 10.0, SOURCE)] if noise_scale else []
    return base, priors, condition, scales


def test_sampler_recovers_the_analytic_gaussian_posterior() -> None:
    observed = 2.0 * X + 1.0 + np.array([0.3, -0.2, 0.1, -0.4, 0.2])
    base, priors, condition, _ = linear_problem(observed)
    settings = SamplerSettings(n_walkers=16, n_steps=1500, burn_in=300, seed=7)
    result = sample_posterior(
        base_parameters=base, priors=priors, conditions=[condition], predict=linear_predict, settings=settings, source=SOURCE
    )
    design = np.column_stack([X, np.ones_like(X)])
    covariance = 0.25 * np.linalg.inv(design.T @ design)
    mean = np.linalg.solve(design.T @ design, design.T @ observed)
    samples = result.flat_samples()
    assert result.converged, result.diagnostics
    effective = min(n for n in result.diagnostics["effective_sample_size"] if n is not None)
    tolerance = 4.0 * np.sqrt(np.diag(covariance) / effective)
    assert np.all(np.abs(samples.mean(axis=0) - mean) <= tolerance), (samples.mean(axis=0), mean, tolerance)
    np.testing.assert_allclose(np.cov(samples.T), covariance, rtol=0.2)
    assert result.identifiability["a"]["class"] == IDENTIFIED
    assert result.identifiability["b"]["class"] == IDENTIFIED
    assert result.identified_parameters() == ["a", "b"] and result.parameters_left_as_ranges() == {}
    assert result.diagnostics["failed_evaluations"] == 0
    assert result.best_sample["log_posterior"] == pytest.approx(float(np.max(result.run.log_posterior)))
    info = result.local_information
    assert info is not None and info["practical_rank"] == 2
    np.testing.assert_allclose(sorted(info["eigenvalues"]), sorted(np.linalg.eigvalsh(design.T @ design / 0.25)), rtol=1e-4)


def test_identifiability_classifier_uses_declared_thresholds() -> None:
    base = ParameterSet([parameter_for_testing(s, 1.0) for s in ("p", "q", "r", "s", "t")])
    priors = [prior_from_bounds(symbol=s, lower=1e-3, upper=1e3, units="dimensionless", source=SOURCE) for s in ("p", "q", "r", "s", "t")]
    condition = ObservedCondition("c", X, np.zeros((5, 1)), gaussian_error("y", 1.0, 5))
    problem = build_bayesian_problem(
        base_parameters=base, priors=priors, conditions=[condition], predict=lambda *_: np.zeros((5, 1))
    )
    rng = np.random.default_rng(1)
    low, high = np.log(1e-3), np.log(1e3)
    width = high - low
    n = 20000
    samples = np.column_stack(
        [
            rng.normal(0.0, 0.05 * width / 4.0, n),  # narrow around the middle: identified
            rng.uniform(low, high, n),  # the whole box: prior dominated
            rng.uniform(low, low + 0.6 * width, n),  # lower 60 percent: only an upper limit
            rng.uniform(high - 0.6 * width, high, n),  # upper 60 percent: only a lower limit
            rng.uniform(low + 0.25 * width, low + 0.75 * width, n),  # middle half: weakly identified
        ]
    )
    verdicts = classify_identifiability(problem, samples, credible_mass=0.95, criteria=DEFAULT_IDENTIFIABILITY_CRITERIA)
    assert [verdicts[s]["class"] for s in ("p", "q", "r", "s", "t")] == [
        IDENTIFIED,
        PRIOR_DOMINATED,
        BOUNDED_ABOVE_ONLY,
        BOUNDED_BELOW_ONLY,
        WEAKLY_IDENTIFIED,
    ]
    assert verdicts["r"]["lower_bound_contact"] and not verdicts["r"]["upper_bound_contact"]
    assert 1e-3 < verdicts["r"]["credible_interval"][0] < 2e-3
    assert verdicts["q"]["interval_width_fraction_of_prior"] > 0.9
    assert verdicts["p"]["prior_width_log10"] == pytest.approx(6.0)
    strict = IdentifiabilityCriteria(source=SOURCE, identified_max_width_fraction=0.03, weak_max_width_fraction=0.1)
    assert classify_identifiability(problem, samples, credible_mass=0.95, criteria=strict)["p"]["class"] == WEAKLY_IDENTIFIED


def test_sampled_posterior_separates_identified_flat_and_one_sided_parameters() -> None:
    times = np.array([0.0, 0.005, 0.01])
    observed = np.exp(-0.5 * times)[:, None]
    base = ParameterSet([parameter_for_testing("a", 1.0), parameter_for_testing("c", 1.0), parameter_for_testing("d", 1.0)])
    priors = [
        prior_from_bounds(symbol="a", lower=0.1, upper=10.0, units="dimensionless", source=SOURCE),
        prior_from_bounds(symbol="c", lower=1e-4, upper=1e4, units="dimensionless", source=SOURCE),
        prior_from_bounds(symbol="d", lower=1e-3, upper=1e3, units="dimensionless", source=SOURCE),
    ]

    def predict(parameters: ParameterSet, condition_id: str, t: np.ndarray) -> np.ndarray:
        a = float(parameters.require_quantity("a").magnitude)
        c = float(parameters.require_quantity("c").magnitude)
        return (a * np.exp(-c * t))[:, None]

    condition = ObservedCondition("decay", times, observed, gaussian_error("y", 0.02, times.size))
    settings = SamplerSettings(n_walkers=12, n_steps=1500, burn_in=300, seed=3, initial_distribution="prior")
    result = sample_posterior(
        base_parameters=base, priors=priors, conditions=[condition], predict=predict, settings=settings, source=SOURCE
    )
    classes = {symbol: verdict["class"] for symbol, verdict in result.identifiability.items()}
    assert classes["a"] == IDENTIFIED
    assert classes["c"] == BOUNDED_ABOVE_ONLY
    assert classes["d"] == PRIOR_DOMINATED
    assert result.identifiability["c"]["credible_interval"][1] < 100.0
    assert set(result.parameters_left_as_ranges()) == {"c", "d"}
    info = result.local_information
    assert info is not None and info["practical_rank"] <= 2
    assert info["sloppy_direction_participation"]["d"] == pytest.approx(1.0)


def test_noise_scale_multiplier_is_estimated_from_residual_scatter() -> None:
    rng = np.random.default_rng(11)
    x = np.linspace(0.0, 10.0, 60)
    observed = 2.0 * x + 1.0 + rng.normal(0.0, 0.5, x.size)
    base = ParameterSet([parameter_for_testing("a", 1.0), parameter_for_testing("b", 1.0)])
    priors = [
        prior_from_bounds(symbol="a", lower=-10.0, upper=10.0, units="dimensionless", source=SOURCE, kind="uniform"),
        prior_from_bounds(symbol="b", lower=-10.0, upper=10.0, units="dimensionless", source=SOURCE, kind="uniform"),
    ]
    condition = ObservedCondition("line", x, observed[:, None], gaussian_error("y", 0.25, x.size))
    settings = SamplerSettings(n_walkers=16, n_steps=1200, burn_in=300, seed=5)
    result = sample_posterior(
        base_parameters=base,
        priors=priors,
        conditions=[condition],
        predict=linear_predict,
        settings=settings,
        source=SOURCE,
        noise_scale_priors=[NoiseScalePrior(("y",), 0.1, 10.0, SOURCE)],
    )
    scale = result.summaries[NOISE_SCALE_PREFIX + "y"]
    assert 1.5 < scale["median"] < 2.7, scale
    assert NOISE_SCALE_EVIDENCE in result.noise_evidence and "assumed" in result.noise_evidence
    assert result.to_dict()["noise_scales"] == {"y": ["y"]}
    assert "noise_scale:y" not in result.identifiability


def test_shared_noise_scale_covers_several_observables_under_one_label() -> None:
    rng = np.random.default_rng(3)
    times = np.linspace(0.0, 4.0, 25)
    observed = np.column_stack([2.0 * times + 1.0 + rng.normal(0.0, 0.6, times.size) for _ in range(2)])
    design = np.column_stack([times, np.ones_like(times)])
    fitted = design @ np.linalg.lstsq(design, observed, rcond=None)[0]
    whitened_sum = float(np.sum(((observed - fitted) / 0.2) ** 2))
    expected_scale = np.sqrt(whitened_sum / (observed.size - 2))
    base = ParameterSet([parameter_for_testing("a", 1.0), parameter_for_testing("b", 1.0)])
    priors = [
        prior_from_bounds(symbol="a", lower=-10.0, upper=10.0, units="dimensionless", source=SOURCE, kind="uniform"),
        prior_from_bounds(symbol="b", lower=-10.0, upper=10.0, units="dimensionless", source=SOURCE, kind="uniform"),
    ]
    error = GaussianObservationError(
        ("y", "z"),
        ("dimensionless", "dimensionless"),
        {"y": Q_(0.2, "dimensionless"), "z": Q_(0.2, "dimensionless")},
        np.eye(2),
        SOURCE,
        "assumed",
    )
    condition = ObservedCondition("pair", times, observed, error)

    def predict(parameters: ParameterSet, condition_id: str, times: np.ndarray) -> np.ndarray:
        line = linear_predict(parameters, condition_id, times)[:, 0]
        return np.column_stack([line, line])

    with pytest.raises(ValueError, match="requires a label"):
        NoiseScalePrior(("y", "z"), 0.1, 10.0, SOURCE)
    with pytest.raises(TypeError, match="not one string"):
        NoiseScalePrior("y", 0.1, 10.0, SOURCE)  # type: ignore[arg-type]
    shared = NoiseScalePrior(("y", "z"), 0.1, 10.0, SOURCE, label="both")
    assert shared.name == "both" and shared.to_dict()["observables"] == ["y", "z"]
    problem = build_bayesian_problem(
        base_parameters=base, priors=priors, conditions=[condition], predict=predict, noise_scale_priors=[shared]
    )
    assert problem.labels[-1] == "noise_scale:both"
    vector = problem.coordinates_from_values({"a": 2.0, "b": 1.0, "noise_scale:both": 3.0})
    scales = problem.noise_scales_from_coordinates(vector)
    assert set(scales) == {"y", "z"} and np.allclose([scales["y"], scales["z"]], 3.0)
    with pytest.raises(ValueError, match="unique across priors"):
        build_bayesian_problem(
            base_parameters=base, priors=priors, conditions=[condition], predict=predict,
            noise_scale_priors=[shared, NoiseScalePrior(("y",), 0.1, 10.0, SOURCE)],
        )
    settings = SamplerSettings(n_walkers=12, n_steps=1200, burn_in=300, seed=5)
    result = sample_posterior(
        base_parameters=base, priors=priors, conditions=[condition], predict=predict, settings=settings,
        source=SOURCE, noise_scale_priors=[shared],
    )
    scale = result.summaries["noise_scale:both"]
    assert 0.8 * expected_scale < scale["median"] < 1.25 * expected_scale, (scale, expected_scale)
    assert 2.0 < expected_scale < 4.0
    assert result.to_dict()["noise_scales"] == {"both": ["y", "z"]}


def test_pooled_replicate_standard_deviation_matches_the_analytic_value() -> None:
    times = [0.0, 0.0, 0.0, 1.0, 1.0, 2.0]
    values = [1.0, 2.0, 3.0, 4.0, 6.0, 9.0]
    record = pooled_replicate_standard_deviation(times, values, units="gram / liter", source="Synthetic triplicate and duplicate rows.")
    expected = np.sqrt((2 * 1.0 + 1 * 2.0) / 3)
    assert record["standard_deviation"] == pytest.approx(expected)
    assert record["degrees_of_freedom"] == 3 and record["evidence"] == "measured_standard_deviation"
    assert [group["replicates"] for group in record["groups"]] == [3, 2]
    error = GaussianObservationError(
        ("biomass",), ("gram / liter",), {"biomass": Q_(record["standard_deviation"], record["units"])}, np.eye(1), record["source"], record["evidence"]
    )
    assert error.evidence == "measured_standard_deviation"
    with pytest.raises(ValueError, match="two or more replicates"):
        pooled_replicate_standard_deviation([0.0, 1.0, 2.0], [1.0, 2.0, 3.0], units="gram / liter", source="no replicates")
    with pytest.raises(ValueError, match="identical"):
        pooled_replicate_standard_deviation([0.0, 0.0], [1.0, 1.0], units="gram / liter", source="identical replicates")
    with pytest.raises(ProvenanceError):
        pooled_replicate_standard_deviation(times, values, units="gram / liter", source="")


def test_local_information_exposes_a_flat_direction() -> None:
    def residuals(vector: np.ndarray) -> np.ndarray:
        a, _ = vector
        return (np.full(5, 3.0) - a) / 0.5

    info = local_information_analysis(residuals, np.array([3.0, 1.0]), labels=["a", "b"], coordinate_kinds=["linear", "linear"])
    assert info["practical_rank"] == 1
    assert info["eigenvalues"][0] == pytest.approx(5 / 0.25, rel=1e-6)
    assert info["least_constrained_combination"]["b"] == pytest.approx(1.0, abs=1e-9) or info["least_constrained_combination"]["b"] == pytest.approx(-1.0, abs=1e-9)
    assert info["sloppy_direction_participation"] == {"a": pytest.approx(0.0, abs=1e-12), "b": pytest.approx(1.0)}


def test_integrated_autocorrelation_time_of_an_ar1_chain() -> None:
    rng = np.random.default_rng(2)
    phi = 0.9
    walkers, steps = 32, 20000
    chain = np.empty((walkers, steps))
    chain[:, 0] = rng.standard_normal(walkers)
    for step in range(1, steps):
        chain[:, step] = phi * chain[:, step - 1] + rng.standard_normal(walkers) * np.sqrt(1 - phi**2)
    tau = integrated_autocorrelation_time(chain)
    assert tau == pytest.approx((1 + phi) / (1 - phi), rel=0.2)
    assert np.isnan(integrated_autocorrelation_time(np.ones((4, 50))))


def test_resumed_runs_concatenate_to_the_single_run() -> None:
    observed = 2.0 * X + 1.0
    base, priors, condition, _ = linear_problem(observed)
    problem = build_bayesian_problem(base_parameters=base, priors=priors, conditions=[condition], predict=linear_predict)
    settings = SamplerSettings(n_walkers=8, n_steps=100, burn_in=10, seed=9)
    start = initial_ensemble(problem, settings)
    full = run_ensemble_sampler(problem.log_posterior, start, 100, rng=np.random.default_rng(1))
    rng = np.random.default_rng(1)
    first = run_ensemble_sampler(problem.log_posterior, start, 60, rng=rng)
    second = run_ensemble_sampler(
        problem.log_posterior, first.chain[:, -1, :], 40, rng=rng, start_log_posterior=first.log_posterior[:, -1]
    )
    joined = first.extend(second)
    np.testing.assert_array_equal(joined.chain, full.chain)
    np.testing.assert_array_equal(joined.log_posterior, full.log_posterior)
    assert joined.evaluations == full.evaluations and np.array_equal(joined.accepted, full.accepted)
    result = analyze_run(problem, joined, settings=settings, source=SOURCE, local_information=False)
    assert result.local_information is None and result.diagnostics["post_burn_in_steps"] == 90
    checkpoints: list[int] = []
    run_ensemble_sampler(
        problem.log_posterior, start, 50, rng=np.random.default_rng(4), progress=lambda step, _: checkpoints.append(step), progress_every=20
    )
    assert checkpoints == [20, 40]


def test_posterior_predictive_bands_follow_the_fit_and_widen_with_noise() -> None:
    observed = 2.0 * X + 1.0
    base, priors, condition, _ = linear_problem(observed, sd=0.2, scalar_sd=True)
    settings = SamplerSettings(n_walkers=12, n_steps=800, burn_in=200, seed=8)
    result = sample_posterior(
        base_parameters=base, priors=priors, conditions=[condition], predict=linear_predict, settings=settings, source=SOURCE
    )
    grid = np.linspace(0.0, 4.0, 9)
    bands = posterior_predictive(result, times_by_condition={"line": grid}, draws=400, seed=2)
    noisy = posterior_predictive(result, times_by_condition={"line": grid}, draws=400, seed=2, include_measurement_noise=True)
    line = bands["conditions"]["line"]["quantile_bands"]["y"]
    assert np.shape(line) == (3, 9) and bands["failed_draws"] == 0
    np.testing.assert_allclose(line[1], 2.0 * grid + 1.0, atol=0.15)
    width = np.asarray(line[2]) - np.asarray(line[0])
    noisy_width = np.asarray(noisy["conditions"]["line"]["quantile_bands"]["y"][2]) - np.asarray(
        noisy["conditions"]["line"]["quantile_bands"]["y"][0]
    )
    assert np.all(noisy_width > width)
    with pytest.raises(KeyError):
        posterior_predictive(result, times_by_condition={"other": grid}, draws=10)
    with pytest.raises(ValueError):
        posterior_predictive(result, times_by_condition={"line": grid}, draws=10, quantiles=(0.5, 0.2))
    per_time = linear_problem(observed, sd=0.2)[2]
    per_time_result = sample_posterior(
        base_parameters=base, priors=priors, conditions=[per_time], predict=linear_predict,
        settings=SamplerSettings(n_walkers=8, n_steps=60, burn_in=10, seed=1), source=SOURCE, local_information=False,
    )
    with pytest.raises(ValueError, match="measurement-noise bands"):
        posterior_predictive(per_time_result, times_by_condition={"line": grid}, draws=10, include_measurement_noise=True)


def test_configured_predictor_matches_the_public_run_and_samples_a_toy_config(tmp_path: Path) -> None:
    config = load_model_config(ROOT / "data" / "model_configs" / "toy_homogeneous_ab.yml")
    factory = inline_parameter_config_factory(config)
    condition = ConfiguredCondition(
        "toy", factory, (ObservableMapping("product", "released_product_amount", "gram"),)
    )
    predictor = ConfiguredConditionPredictor([condition], fitted_symbols=["k_ab"])
    times = np.linspace(0.0, 10.0, 11)
    predicted = predictor.predict_values({"k_ab": 0.1}, "toy", times)
    reference = run_configured_model(ROOT / "data" / "model_configs" / "toy_homogeneous_ab.yml", output_dir=tmp_path / "ref")
    expected = np.asarray(reference.states["released_product_amount"].to("gram").magnitude, dtype=float)
    np.testing.assert_allclose(predicted[:, 0], expected, rtol=1e-9, atol=1e-9)
    assert predictor.predict_values({"k_ab": 0.3}, "toy", times)[5, 0] > predicted[5, 0]
    with pytest.raises(ValueError, match="outside the configured span"):
        predictor.predict_values({"k_ab": 0.1}, "toy", np.array([11.0]))
    with pytest.raises(KeyError):
        predictor.predict_values({"k_ab": 0.1}, "missing", times)
    with pytest.raises(KeyError):
        factory({"k_unknown": 1.0})

    observation_times = np.arange(1.0, 11.0)
    truth = 1000.0 * (1.0 - np.exp(-0.1 * observation_times))
    observed = truth + np.array([3.0, -2.0, 1.0, -4.0, 2.0, 0.5, -1.5, 2.5, -3.0, 1.0])
    error = GaussianObservationError(("product",), ("gram",), {"product": Q_(np.full(10, 3.0), "gram")}, np.eye(1), SOURCE, "assumed")
    data = ObservedCondition("toy", observation_times, observed[:, None], error)
    prior = prior_from_bounds(symbol="k_ab", lower=0.01, upper=1.0, units="1 / second", source=SOURCE)
    base = ParameterSet([config_parameter for config_parameter in _config_parameters(config)])
    settings = SamplerSettings(n_walkers=8, n_steps=120, burn_in=40, seed=21)
    result = sample_posterior(
        base_parameters=base, priors=[prior], conditions=[data], predict=predictor, settings=settings, source=SOURCE,
        local_information=False,
    )
    assert result.summaries["k_ab"]["units"] == "1 / second"
    assert 0.085 < result.summaries["k_ab"]["median"] < 0.115
    assert result.diagnostics["failed_evaluations"] == 0
    paths = result.save(tmp_path / "bayes", thin=2)
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    assert summary["schema_version"] == "1.0.0" and summary["parameters"] == ["k_ab"]
    assert summary["claim_boundary"].startswith("Posterior and identifiability statements are conditional")
    assert summary["priors"][0]["units"] == "1 / second"
    with paths["samples"].open(encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == ["k_ab"] and len(rows) - 1 == 8 * len(range(40, 120, 2))
    assert all(0.01 <= float(row[0]) <= 1.0 for row in rows[1:])
    again = sample_posterior(
        base_parameters=base, priors=[prior], conditions=[data], predict=predictor, settings=settings, source=SOURCE,
        local_information=False,
    )
    np.testing.assert_array_equal(again.run.chain, result.run.chain)


def _config_parameters(config):
    from fungal_model.core.parameters import Parameter

    for parameter_set in config.parameters:
        for entry in parameter_set.parameters:
            yield Parameter.from_dict(entry)


def test_invalid_inputs_are_rejected() -> None:
    with pytest.raises(ProvenanceError):
        PriorSpecification("a", Q_(1.0, "dimensionless"), Q_(2.0, "dimensionless"), source="")
    with pytest.raises(ValueError, match="positive lower bound"):
        prior_from_bounds(symbol="a", lower=0.0, upper=1.0, units="dimensionless", source=SOURCE)
    with pytest.raises(ValueError, match="ordered"):
        prior_from_bounds(symbol="a", lower=2.0, upper=1.0, units="dimensionless", source=SOURCE, kind="uniform")
    with pytest.raises(ValueError, match="kind"):
        prior_from_bounds(symbol="a", lower=1.0, upper=2.0, units="dimensionless", source=SOURCE, kind="normal")
    with pytest.raises(ValueError, match="even"):
        SamplerSettings(n_walkers=7, n_steps=10, burn_in=1, seed=0)
    with pytest.raises(ValueError, match="burn_in"):
        SamplerSettings(n_walkers=8, n_steps=10, burn_in=10, seed=0)
    with pytest.raises(ValueError):
        IdentifiabilityCriteria(source=SOURCE, identified_max_width_fraction=0.9, weak_max_width_fraction=0.5)
    with pytest.raises(ProvenanceError):
        NoiseScalePrior(("y",), 0.1, 10.0, source="")
    with pytest.raises(ValueError, match="shape"):
        ObservedCondition("c", X, np.zeros((5, 2)), gaussian_error("y", 1.0, 5))
    base, priors, condition, _ = linear_problem(2.0 * X + 1.0)
    with pytest.raises(ValueError, match="absent from every condition"):
        build_bayesian_problem(
            base_parameters=base, priors=priors, conditions=[condition], predict=linear_predict,
            noise_scale_priors=[NoiseScalePrior(("z",), 0.1, 10.0, SOURCE)],
        )
    with pytest.raises(KeyError):
        build_bayesian_problem(
            base_parameters=ParameterSet([parameter_for_testing("a", 1.0)]), priors=priors, conditions=[condition], predict=linear_predict
        )
    problem = build_bayesian_problem(base_parameters=base, priors=priors, conditions=[condition], predict=linear_predict)
    assert problem.log_posterior(np.array([11.0, 0.0])) == -np.inf
    wrong_shape = build_bayesian_problem(
        base_parameters=base, priors=priors, conditions=[condition], predict=lambda *_: np.zeros((2, 1))
    )
    assert wrong_shape.log_posterior(np.array([1.0, 1.0])) == -np.inf
    settings = SamplerSettings(n_walkers=8, n_steps=10, burn_in=1, seed=0)
    with pytest.raises(ValueError, match="No starting walker"):
        run_ensemble_sampler(wrong_shape.log_posterior, initial_ensemble(wrong_shape, settings), 5, rng=np.random.default_rng(0))
    with pytest.raises(ValueError, match="walkers are needed"):
        run_ensemble_sampler(problem.log_posterior, np.zeros((4, 3)), 5, rng=np.random.default_rng(0))
    with pytest.raises(KeyError):
        initial_ensemble(problem, settings, center={"a": 1.0})
    with pytest.raises(ValueError, match="inside the prior box"):
        initial_ensemble(problem, settings, center={"a": 20.0, "b": 0.0})
    with pytest.raises(ProvenanceError):
        sample_posterior(
            base_parameters=base, priors=priors, conditions=[condition], predict=linear_predict, settings=settings, source=""
        )
