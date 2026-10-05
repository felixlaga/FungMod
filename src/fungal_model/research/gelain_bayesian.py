"""Posterior sampling of the T. harzianum P49P11 cellulose registry case.

The study samples the nine hydrolysis-candidate constants of the registry
case ``trichoderma_harzianum_p49p11`` x ``cellulose_celufloc_200`` on the
compiled core, jointly over the three Gelain 2020 cellulose loadings, with
the log-uniform prior box of the v2 joint benchmark and an explicit Gaussian
error model whose base standard deviations are assumptions (10 percent of
the training maxima) scaled by per-observable multipliers sampled with the
parameters. Its purpose is the identifiability report: which constants the
duplicate-mean data identify and which remain ranges. It is retrospective,
uses no replicate-level data (the deposit holds none) and validates nothing.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from fungal_model.calibration.bayesian import (
    DEFAULT_IDENTIFIABILITY_CRITERIA,
    BayesianCalibrationResult,
    BayesianProblem,
    EnsembleRun,
    NoiseScalePrior,
    ObservedCondition,
    PriorSpecification,
    SamplerSettings,
    analyze_run,
    build_bayesian_problem,
    initial_ensemble,
    posterior_predictive,
    run_ensemble_sampler,
)
from fungal_model.calibration.compiled_predictor import (
    ConfiguredCondition,
    ConfiguredConditionPredictor,
    ObservableMapping,
)
from fungal_model.calibration.observation_error import GaussianObservationError
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.registry import load_registry
from fungal_model.registry.store import FungModRegistry
from fungal_model.research.gelain_culture import CultureBenchmarkError
from fungal_model.research.gelain_models import OBSERVABLE_UNITS as _V2_OBSERVABLE_UNITS  # defines the v2 assay unit aliases
from fungal_model.screening import registry_case_config_factory

PLAN_PATH = Path("data/benchmarks/gelain_2020_bayesian/plan.json")
V2_PLAN_PATH = Path("data/benchmarks/gelain_2020_v2/plan.json")
OBSERVATIONS_PATH = Path("data/benchmarks/gelain_2020_v2/observations.json")
FROZEN_FIT_PATH = Path("data/benchmarks/gelain_2020_v2/results/full_fits/cellulose_hydrolysis_primary.json")
REGISTRY_INDEX = Path("data_registry/registry_index.yml")
V2_OBSERVABLE_UNITS = _V2_OBSERVABLE_UNITS
SOURCE_UNITS = {
    "biomass": "g/L",
    "substrate": "g/L",
    "cellulase_activity": "FPU/L",
    "beta_glucosidase_activity": "U/L",
}


def load_plan(root: Path, plan_path: Path | None = None) -> dict[str, Any]:
    """Load the primary plan, or the plan at ``plan_path`` (relative to ``root``)."""

    plan = json.loads((root / (plan_path or PLAN_PATH)).read_text(encoding="utf-8"))
    if plan.get("schema_version") != "1.0.0":
        raise CultureBenchmarkError("Unsupported Bayesian study plan schema.")
    return plan


def observable_mappings(plan: Mapping[str, Any]) -> tuple[ObservableMapping, ...]:
    return tuple(
        ObservableMapping(name, spec["state"], spec["units"]) for name, spec in plan["observables"].items()
    )


def load_cellulose_conditions(root: Path, plan: Mapping[str, Any]) -> list[ObservedCondition]:
    """Three cellulose loadings as observed conditions with the declared assumed error model."""

    records = json.loads((root / OBSERVATIONS_PATH).read_text(encoding="utf-8"))
    names = tuple(plan["observables"])
    units = tuple(plan["observables"][name]["units"] for name in names)
    cellulose = [r for r in records if r["family"] == "cellulose"]
    expected_ids = list(plan["registry_case"]["condition_ids"])
    if [r["condition_id"] for r in cellulose] != expected_ids:
        raise CultureBenchmarkError("Cellulose condition identifiers disagree with the plan.")
    values: dict[str, np.ndarray] = {}
    times: dict[str, np.ndarray] = {}
    for record in cellulose:
        for name in names:
            if record["observations"][name]["units"] != SOURCE_UNITS[name]:
                raise CultureBenchmarkError("Source assay units changed; review observation mapping.")
        times[record["condition_id"]] = np.asarray(record["times_h"], dtype=float)
        values[record["condition_id"]] = np.column_stack(
            [np.asarray(record["observations"][name]["values"], dtype=float) for name in names]
        )
    error_plan = plan["error_model"]
    training_max = np.max(np.concatenate(list(values.values()), axis=0), axis=0)
    if np.any(training_max <= 0.0):
        raise CultureBenchmarkError("Every observable needs a positive training maximum.")
    base_sd = training_max * float(error_plan["relative_sd_to_training_max"])
    correlation = np.eye(len(names))
    i, j = names.index("biomass"), names.index("substrate")
    correlation[i, j] = correlation[j, i] = float(error_plan["rho_biomass_substrate"])
    conditions = []
    for condition_id in expected_ids:
        error = GaussianObservationError(
            names,
            units,
            {name: Q_(float(sd), unit) for name, sd, unit in zip(names, base_sd, units, strict=True)},
            correlation,
            error_plan["source"],
            error_plan["evidence"],
        )
        conditions.append(ObservedCondition(condition_id, times[condition_id], values[condition_id], error))
    return conditions


def build_priors(root: Path, plan: Mapping[str, Any]) -> list[PriorSpecification]:
    """Log-uniform priors on the registry symbols from the v2 benchmark's declared bounds."""

    v2 = json.loads((root / V2_PLAN_PATH).read_text(encoding="utf-8"))
    declared = {r["symbol"]: r for r in v2["models"]["cellulose"]["hydrolysis"]["parameters"]}
    symbol_map: Mapping[str, str] = plan["priors"]["symbol_map"]
    if set(symbol_map) != set(declared):
        raise CultureBenchmarkError("Prior symbol map must cover exactly the v2 hydrolysis parameters.")
    priors = []
    for fit_symbol, registry_symbol in symbol_map.items():
        bounds = declared[fit_symbol]
        priors.append(
            PriorSpecification(
                symbol=registry_symbol,
                lower=Q_(float(bounds["lower"]), bounds["units"]),
                upper=Q_(float(bounds["upper"]), bounds["units"]),
                source=plan["priors"]["source"],
                kind=plan["priors"]["kind"],
            )
        )
    return priors


def build_noise_scale_priors(plan: Mapping[str, Any]) -> list[NoiseScalePrior]:
    """Noise-scale priors with the structure the plan declares.

    ``shared`` samples one multiplier for every observable (the relative
    weights of the assumed error model are kept); ``per_observable`` samples
    one multiplier per observable (each can be re-weighted independently).
    """

    spec = plan["error_model"]["noise_scale_priors"]
    structure = str(spec["structure"])
    names = tuple(plan["observables"])
    lower, upper, source = float(spec["lower"]), float(spec["upper"]), str(spec["source"])
    if structure == "shared":
        return [NoiseScalePrior(names, lower, upper, source, label=str(spec["label"]))]
    if structure == "per_observable":
        return [NoiseScalePrior((name,), lower, upper, source) for name in names]
    raise CultureBenchmarkError(f"Unknown noise-scale structure {structure!r}; expected 'shared' or 'per_observable'.")


def build_predictor(registry: FungModRegistry, plan: Mapping[str, Any]) -> ConfiguredConditionPredictor:
    case = plan["registry_case"]
    mappings = observable_mappings(plan)
    conditions = []
    for condition_id, environment_id in zip(case["condition_ids"], case["environment_ids"], strict=True):
        factory = registry_case_config_factory(
            fungus_id=case["fungus_id"],
            substrate_id=case["substrate_id"],
            environment_id=environment_id,
            registry=registry,
            mode=case["mode"],
        )
        conditions.append(ConfiguredCondition(condition_id, factory, mappings))
    return ConfiguredConditionPredictor(conditions, fitted_symbols=list(plan["priors"]["symbol_map"].values()))


def base_parameters_from_case(predictor: ConfiguredConditionPredictor, plan: Mapping[str, Any]) -> ParameterSet:
    """The registry case's own parameter set, read from the first condition's config."""

    first = plan["registry_case"]["condition_ids"][0]
    config = predictor._conditions[first].config_factory({})  # noqa: SLF001 - research helper reading the public config
    parameters = [Parameter.from_dict(entry) for block in config.parameters for entry in block.parameters]
    return ParameterSet(parameters)


def frozen_fit_center(root: Path, plan: Mapping[str, Any]) -> dict[str, float]:
    """Natural-unit center for the initial ball: the frozen least-squares fit and unit noise scales."""

    fit = json.loads((root / FROZEN_FIT_PATH).read_text(encoding="utf-8"))
    values = {item["symbol"]: float(item["value"]) for item in fit["parameters"]}
    center = {registry_symbol: values[fit_symbol] for fit_symbol, registry_symbol in plan["priors"]["symbol_map"].items()}
    for prior in build_noise_scale_priors(plan):
        center[f"noise_scale:{prior.name}"] = 1.0
    return center


def sampler_settings(plan: Mapping[str, Any], *, n_steps: int | None = None, burn_in: int | None = None, n_walkers: int | None = None) -> SamplerSettings:
    spec = dict(plan["sampler"])
    if n_walkers is not None:
        spec["n_walkers"] = n_walkers
    if n_steps is not None:
        spec["n_steps"] = n_steps
    if burn_in is not None:
        spec["burn_in"] = burn_in
    return SamplerSettings(
        n_walkers=int(spec["n_walkers"]),
        n_steps=int(spec["n_steps"]),
        burn_in=int(spec["burn_in"]),
        seed=int(spec["seed"]),
        stretch_scale=float(spec["stretch_scale"]),
        initial_spread=float(spec["initial_spread"]),
        initial_distribution=str(spec["initial_distribution"]),
        autocorrelation_tolerance=float(spec["autocorrelation_tolerance"]),
        minimum_effective_samples=float(spec["minimum_effective_samples"]),
        credible_mass=float(spec["credible_mass"]),
    )


@dataclass(frozen=True)
class StudyProblem:
    """Everything the sampler needs for the registry-case study."""

    plan: Mapping[str, Any]
    predictor: ConfiguredConditionPredictor
    problem: BayesianProblem
    settings: SamplerSettings
    center: dict[str, float]
    plan_path: Path = PLAN_PATH


def build_study(
    root: Path,
    *,
    registry: FungModRegistry | None = None,
    n_steps: int | None = None,
    burn_in: int | None = None,
    n_walkers: int | None = None,
    plan_path: Path | None = None,
) -> StudyProblem:
    plan = load_plan(root, plan_path)
    store = registry if registry is not None else load_registry(root / REGISTRY_INDEX)
    predictor = build_predictor(store, plan)
    problem = build_bayesian_problem(
        base_parameters=base_parameters_from_case(predictor, plan),
        priors=build_priors(root, plan),
        conditions=load_cellulose_conditions(root, plan),
        predict=predictor,
        noise_scale_priors=build_noise_scale_priors(plan),
    )
    return StudyProblem(
        plan,
        predictor,
        problem,
        sampler_settings(plan, n_steps=n_steps, burn_in=burn_in, n_walkers=n_walkers),
        frozen_fit_center(root, plan),
        plan_path or PLAN_PATH,
    )


CHECKPOINT_NAME = "chain_checkpoint.npz"


def save_checkpoint(path: Path, run: EnsembleRun, rng: np.random.Generator) -> None:
    state = json.dumps(rng.bit_generator.state)
    np.savez_compressed(
        path,
        chain=run.chain,
        log_posterior=run.log_posterior,
        accepted=run.accepted,
        evaluations=np.array([run.evaluations, run.failed_evaluations]),
        rng_state=np.array(state),
    )


def load_checkpoint(path: Path) -> tuple[EnsembleRun, np.random.Generator]:
    with np.load(path) as data:
        run = EnsembleRun(
            chain=np.array(data["chain"]),
            log_posterior=np.array(data["log_posterior"]),
            accepted=np.array(data["accepted"]),
            evaluations=int(data["evaluations"][0]),
            failed_evaluations=int(data["evaluations"][1]),
        )
        rng = np.random.default_rng()
        rng.bit_generator.state = json.loads(str(data["rng_state"]))
    return run, rng


def sample_study(
    study: StudyProblem,
    output_dir: Path,
    *,
    map_function: Callable[..., Any] = map,
    checkpoint_every: int = 250,
    resume: bool = True,
    log: Callable[[str], None] | None = None,
    log_posterior: Callable[[np.ndarray], float] | None = None,
) -> EnsembleRun:
    """Run or resume the ensemble sampler, checkpointing the full chain in ``output_dir``.

    ``log_posterior`` defaults to the study problem's own; a process pool needs
    a picklable module-level function that evaluates the same problem.
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = output_dir / CHECKPOINT_NAME
    settings = study.settings
    previous: EnsembleRun | None = None
    if resume and checkpoint.exists():
        previous, rng = load_checkpoint(checkpoint)
        if previous.chain.shape[0] != settings.n_walkers or previous.chain.shape[2] != study.problem.dimension:
            raise CultureBenchmarkError("Checkpoint does not match the study settings; use a fresh output directory.")
        done = previous.chain.shape[1]
        if log is not None:
            log(f"resuming from checkpoint with {done} steps")
        if done >= settings.n_steps:
            return previous
        start = previous.chain[:, -1, :]
        start_logp = previous.log_posterior[:, -1]
        remaining = settings.n_steps - done
    else:
        rng = np.random.default_rng(settings.seed)
        start = initial_ensemble(study.problem, settings, center=study.center, rng=rng)
        start_logp = None
        remaining = settings.n_steps

    def progress(step: int, partial: EnsembleRun) -> None:
        combined = previous.extend(partial) if previous is not None else partial
        save_checkpoint(checkpoint, combined, rng)
        if log is not None:
            log(f"checkpoint at {combined.chain.shape[1]} steps; mean acceptance {np.mean(combined.acceptance_fraction):.3f}")

    run = run_ensemble_sampler(
        log_posterior if log_posterior is not None else study.problem.log_posterior,
        start,
        remaining,
        rng=rng,
        stretch_scale=settings.stretch_scale,
        map_function=map_function,
        progress=progress,
        progress_every=checkpoint_every,
        start_log_posterior=start_logp,
    )
    combined = previous.extend(run) if previous is not None else run
    save_checkpoint(checkpoint, combined, rng)
    return combined


def analyze_study(study: StudyProblem, run: EnsembleRun, *, with_predictive: bool = True) -> BayesianCalibrationResult:
    plan = study.plan
    result = analyze_run(
        study.problem,
        run,
        settings=study.settings,
        source=plan["source"],
        criteria=DEFAULT_IDENTIFIABILITY_CRITERIA,
        local_information=True,
        notes=tuple(plan["notes"]),
    )
    if with_predictive:
        grid_spec = plan["posterior_predictive"]
        grid = np.arange(float(grid_spec["start_h"]), float(grid_spec["stop_h"]) + 1e-9, float(grid_spec["step_h"]))
        predictive = posterior_predictive(
            result,
            times_by_condition={condition.condition_id: grid for condition in study.problem.conditions},
            draws=int(grid_spec["draws"]),
            quantiles=tuple(float(q) for q in grid_spec["quantiles"]),
            seed=int(grid_spec["seed"]),
        )
        result = BayesianCalibrationResult(
            problem=result.problem,
            run=result.run,
            settings=result.settings,
            criteria=result.criteria,
            source=result.source,
            diagnostics=result.diagnostics,
            summaries=result.summaries,
            identifiability=result.identifiability,
            local_information=result.local_information,
            best_sample=result.best_sample,
            noise_evidence=result.noise_evidence,
            data_digest=result.data_digest,
            posterior_predictive=predictive,
            notes=result.notes,
        )
    return result


def write_study_outputs(study: StudyProblem, result: BayesianCalibrationResult, output_dir: Path, *, root: Path) -> dict[str, Path]:
    """Summary JSON, thinned samples, report and artifact digests."""

    plan = study.plan
    paths = result.save(output_dir, thin=int(plan["thin"]))
    inputs = {
        "plan": plan,
        "plan_path": study.plan_path.as_posix(),
        "plan_sha256": _digest(root / study.plan_path),
        "observations_sha256": _digest(root / OBSERVATIONS_PATH),
        "v2_plan_sha256": _digest(root / V2_PLAN_PATH),
        "frozen_fit_sha256": _digest(root / FROZEN_FIT_PATH),
        "predictor": study.predictor.to_dict(),
        "data_sha256": result.data_digest,
    }
    inputs_path = output_dir / "inputs.json"
    inputs_path.write_text(json.dumps(inputs, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    report_path = output_dir / "report.md"
    report_path.write_text(render_report(study, result), encoding="utf-8")
    artifacts = {
        name: _digest(path) for name, path in (("bayesian_calibration.json", paths["summary"]), ("posterior_samples.csv", paths["samples"]), ("inputs.json", inputs_path), ("report.md", report_path))
    }
    artifacts_path = output_dir / "artifacts.json"
    artifacts_path.write_text(json.dumps(artifacts, indent=2) + "\n", encoding="utf-8")
    return {**paths, "inputs": inputs_path, "report": report_path, "artifacts": artifacts_path}


def render_report(study: StudyProblem, result: BayesianCalibrationResult) -> str:
    plan = study.plan
    lines = [
        f"# {plan['benchmark_id']}",
        "",
        plan["source"],
        "",
        f"Converged by the declared rule: **{result.converged}** "
        f"(mean acceptance {result.diagnostics['mean_acceptance_fraction']:.3f}, "
        f"{result.diagnostics['post_burn_in_steps']} post-burn-in steps, {result.diagnostics['walkers']} walkers).",
        "",
        "| Symbol | Class | Posterior median | Credible interval | Prior box | Units | Width / prior width | tau |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    taus = result.diagnostics["integrated_autocorrelation_time"]
    for index, symbol in enumerate(result.problem.parameter_symbols):
        verdict = result.identifiability[symbol]
        summary = result.summaries[symbol]
        tau = taus[index]
        lines.append(
            f"| `{symbol}` | {verdict['class']} | {summary['median']:.4g} | "
            f"[{verdict['credible_interval'][0]:.3g}, {verdict['credible_interval'][1]:.3g}] | "
            f"[{verdict['prior_bounds'][0]:.3g}, {verdict['prior_bounds'][1]:.3g}] | {summary['units']} | "
            f"{verdict['interval_width_fraction_of_prior']:.2f} | {'n/a' if tau is None else f'{tau:.0f}'} |"
        )
    lines.extend(["", "| Noise-scale multiplier | Posterior median | Credible interval |", "| --- | --- | --- |"])
    for prior in result.problem.noise_scale_priors:
        summary = result.summaries[f"noise_scale:{prior.name}"]
        scope = ", ".join(prior.observables)
        lines.append(f"| `{prior.name}` ({scope}) | {summary['median']:.3g} | [{summary['lower']:.3g}, {summary['upper']:.3g}] |")
    lines.extend(["", result.to_dict()["claim_boundary"], ""])
    for note in result.notes:
        lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def condition_summary(conditions: Sequence[ObservedCondition]) -> dict[str, Any]:
    return {
        condition.condition_id: {"rows": int(condition.times.size), "observables": list(condition.observables)}
        for condition in conditions
    }


__all__ = [
    "CHECKPOINT_NAME",
    "FROZEN_FIT_PATH",
    "OBSERVATIONS_PATH",
    "PLAN_PATH",
    "StudyProblem",
    "analyze_study",
    "base_parameters_from_case",
    "build_noise_scale_priors",
    "build_predictor",
    "build_priors",
    "build_study",
    "condition_summary",
    "frozen_fit_center",
    "load_cellulose_conditions",
    "load_checkpoint",
    "load_plan",
    "render_report",
    "sample_study",
    "sampler_settings",
    "save_checkpoint",
    "write_study_outputs",
]
