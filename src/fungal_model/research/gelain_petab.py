"""Cross-solver reproduction of the Gelain 2020 registry-case fit through PEtab and COPASI.

The study exports the model-criticism baseline (``M0_baseline``: the registry
case ``trichoderma_harzianum_p49p11`` x ``cellulose_celufloc_200`` on the three
Gelain 2020 cellulose loadings) as a PEtab problem whose objective is the
stage A ``primary`` least-squares objective of the criticism plan, then lets
COPASI simulate and fit the same problem. Everything is fixed by the frozen
plan ``data/benchmarks/gelain_2020_petab/plan.json``: sources and their
digests, the COPASI settings, the random starts and the agreement gates.

Retrospective: the data already informed the fit being reproduced. It validates
no biology and makes no claim beyond "two solvers agree on this problem".
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from fungal_model.calibration.bayesian import ObservedCondition
from fungal_model.calibration.compiled_predictor import ConfiguredConditionPredictor
from fungal_model.core.units import Q_
from fungal_model.registry import load_registry
from fungal_model.registry.store import FungModRegistry
from fungal_model.research import gelain_bayesian, gelain_criticism
from fungal_model.research.gelain_culture import CultureBenchmarkError
from fungal_model.screening import registry_case_config_factory
from fungal_model.standards.petab import PetabCondition, PetabExport, PetabObservable, PetabParameter, conditions_to_petab
from fungal_model.workflows.configured_inputs import ConfiguredInputLoader
from fungal_model.workflows.configured_processes import ConfiguredProcessAssembler

PLAN_PATH = Path("data/benchmarks/gelain_2020_petab/plan.json")
RESULTS_PATH = Path("data/benchmarks/gelain_2020_petab/results")
REGISTRY_INDEX = gelain_criticism.REGISTRY_INDEX
BASELINE_MODEL = gelain_criticism.BASELINE_MODEL
MODEL_ID = "gelain_2020_cellulose_hydrolysis_candidate"


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_plan(root: Path, plan_path: Path | None = None) -> dict[str, Any]:
    plan = json.loads((root / (plan_path or PLAN_PATH)).read_text(encoding="utf-8"))
    if plan.get("schema_version") != 1 or "gates" not in plan or "copasi" not in plan:
        raise CultureBenchmarkError("Unsupported cross-solver plan schema.")
    return plan


def verify_sources(root: Path, plan: Mapping[str, Any]) -> dict[str, str]:
    """Every source file must carry the digest the plan froze; returns the digests."""

    digests: dict[str, str] = {}
    for name, entry in plan["sources"].items():
        path = root / entry["path"]
        if not path.exists():
            raise CultureBenchmarkError(f"Plan source {name!r} is missing: {path}.")
        digest = file_digest(path)
        if digest != entry["sha256"]:
            raise CultureBenchmarkError(f"Plan source {name!r} changed since the plan was frozen ({digest} != {entry['sha256']}).")
        digests[name] = digest
    return digests


def reference_fit(root: Path, plan: Mapping[str, Any]) -> dict[str, Any]:
    fit = json.loads((root / plan["sources"]["reference_fit"]["path"]).read_text(encoding="utf-8"))
    if fit.get("model") != BASELINE_MODEL or fit.get("scenario") != "primary" or not fit.get("success"):
        raise CultureBenchmarkError("The reference fit must be the successful stage A primary fit of M0_baseline.")
    return fit


def nominal_config_values(fit: Mapping[str, Any]) -> dict[str, float]:
    """Registry symbol -> fitted value, in the registry parameter units."""

    return {str(entry["config_symbol"]): float(entry["value"]) for entry in fit["parameters"] if not entry.get("fixed")}


@dataclass(frozen=True)
class Problem:
    """The exported PEtab problem together with the FungMod side of the comparison."""

    export: PetabExport
    predictor: ConfiguredConditionPredictor
    nominal: dict[str, float]
    conditions: list[ObservedCondition]
    scales: np.ndarray
    observable_ids: tuple[str, ...]
    digests: dict[str, str]

    def fungmod_predictor(self) -> Callable[[str, np.ndarray], dict[str, np.ndarray]]:
        """``(condition_id, seconds) -> {observable_id: values}`` from the compiled core at the nominal values."""

        def predict(condition_id: str, seconds: np.ndarray) -> dict[str, np.ndarray]:
            hours = np.asarray(Q_(np.asarray(seconds, dtype=float), "second").to("hour").magnitude, dtype=float)
            values = self.predictor.predict_values(self.nominal, condition_id, hours)
            return {observable_id: values[:, column] for column, observable_id in enumerate(self.observable_ids)}

        return predict

    def fungmod_objective(self, values: Mapping[str, float] | None = None) -> float:
        """FungMod's PEtab objective at ``values`` (default: the nominal values, the stage A primary objective)."""

        candidate = dict(self.nominal if values is None else values)
        total = 0.0
        for condition in self.conditions:
            predicted = self.predictor.predict_values(candidate, condition.condition_id, condition.times)
            total += float(np.sum(((predicted - condition.observed) / self.scales) ** 2))
        return total


def _condition_factories(registry: FungModRegistry, bayesian_plan: Mapping[str, Any]) -> dict[str, Callable[[Mapping[str, float]], Any]]:
    case = bayesian_plan["registry_case"]
    factories = {}
    for condition_id, environment_id in zip(case["condition_ids"], case["environment_ids"], strict=True):
        factories[condition_id] = registry_case_config_factory(
            fungus_id=case["fungus_id"],
            substrate_id=case["substrate_id"],
            environment_id=environment_id,
            registry=registry,
            mode=case["mode"],
        )
    return factories


def build_problem(
    root: Path,
    output_dir: Path,
    *,
    registry: FungModRegistry | None = None,
    plan_path: Path | None = None,
) -> Problem:
    """Export the PEtab problem the plan describes into ``output_dir``."""

    plan = load_plan(root, plan_path)
    digests = verify_sources(root, plan)
    digests["plan"] = file_digest(root / (plan_path or PLAN_PATH))
    criticism_plan = gelain_criticism.load_plan(root)
    bayesian_plan = gelain_bayesian.load_plan(root)
    store = registry if registry is not None else load_registry(root / REGISTRY_INDEX)
    fit = reference_fit(root, plan)
    nominal = nominal_config_values(fit)

    observed = gelain_criticism.observed_conditions(root, criticism_plan)
    if [condition.condition_id for condition in observed] != list(plan["problem"]["conditions"]):
        raise CultureBenchmarkError("Observed conditions disagree with the plan.")
    scales = gelain_criticism.training_scales(observed)
    mappings = gelain_bayesian.observable_mappings(bayesian_plan)
    if [mapping.observable for mapping in mappings] != list(plan["problem"]["observables"]):
        raise CultureBenchmarkError("Observables disagree with the plan.")
    recorded = fit["normalization"]
    for mapping, scale in zip(mappings, scales, strict=True):
        if not np.isclose(float(recorded[mapping.observable]), float(scale), rtol=1e-12, atol=0.0):
            raise CultureBenchmarkError(f"Training scale of {mapping.observable!r} differs from the reference fit's normalization.")

    factories = _condition_factories(store, bayesian_plan)
    loader = ConfiguredInputLoader()
    assembler = ConfiguredProcessAssembler()
    petab_conditions: list[PetabCondition] = []
    for condition in observed:
        config = factories[condition.condition_id](nominal)
        inputs = loader.load(config)
        assembled = assembler.assemble(config, inputs)
        time_units = str(inputs.t_span[1].units)
        petab_conditions.append(
            PetabCondition(
                condition.condition_id,
                assembled.model,
                inputs.initial_state,
                time_units,
                condition.times,
                condition.observed,
                scales,
                name=config.name,
            )
        )

    specs = criticism_plan["models"][BASELINE_MODEL]["parameters"]
    model_parameters = {parameter.symbol: parameter for parameter in petab_conditions[0].model.parameters}
    parameters: list[PetabParameter] = []
    for spec in specs:
        symbol = str(spec["config_symbol"])
        if symbol not in model_parameters or model_parameters[symbol].quantity is None:
            raise CultureBenchmarkError(f"Plan parameter {symbol!r} is not a valued model parameter.")
        factor = float(Q_(1.0, str(spec["units"])).to(model_parameters[symbol].units).magnitude)
        if not np.isclose(factor, 1.0, rtol=1e-12, atol=0.0):
            raise CultureBenchmarkError(f"Plan bounds of {symbol!r} are in units that differ from the registry parameter's units.")
        parameters.append(
            PetabParameter(symbol, float(spec["lower"]), float(spec["upper"]), nominal[symbol], "log10", name=str(spec["symbol"]))
        )
    observables = [PetabObservable(mapping.observable, mapping.state, mapping.units) for mapping in mappings]
    export = conditions_to_petab(petab_conditions, observables=observables, parameters=parameters, output_dir=output_dir, model_id=MODEL_ID)
    digests["sbml"] = file_digest(export.sbml_model)
    predictor = gelain_bayesian.build_predictor(store, bayesian_plan)
    assert export.metadata is not None
    metadata = json.loads(export.metadata.read_text(encoding="utf-8"))
    observable_ids = tuple(metadata["observables"])
    problem = Problem(export, predictor, nominal, observed, scales, observable_ids, digests)
    (output_dir / "problem_metadata.json").write_text(
        json.dumps(
            {
                "plan_sha256": digests["plan"],
                "sources": digests,
                "nominal": nominal,
                "scales": {mapping.observable: float(scale) for mapping, scale in zip(mappings, scales, strict=True)},
                "reference_objective": 2.0 * float(fit["cost"]),
                "fungmod_objective_at_nominal": problem.fungmod_objective(),
            },
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return problem


def _relative(a: float, b: float) -> float:
    return abs(a - b) / max(abs(b), np.finfo(float).tiny)


def compare(plan: Mapping[str, Any], problem: Problem, reproduction: Mapping[str, Any], reference_objective: float) -> dict[str, Any]:
    """Apply the plan's gates to a COPASI reproduction record."""

    gates = plan["gates"]
    simulation = reproduction["simulation_at_nominal"]
    worst = max(simulation["max_abs_difference_over_sigma"].values())
    simulation_pass = (
        worst <= float(gates["simulation_agreement"]["max_abs_difference_over_sigma"])
        and simulation["objective_relative_difference"] <= float(gates["simulation_agreement"]["objective_relative_difference"])
    )
    best = reproduction["best"]
    tolerance = float(gates["optimum_agreement"]["objective_relative_difference"])
    optimum_relative = _relative(best["objective"], reference_objective)
    copasi_improves = best["objective"] < reference_objective * (1.0 - tolerance)
    optimum_pass = optimum_relative <= tolerance
    parameters = []
    fit_symbols = {row.symbol: row.name for row in _plan_parameters(problem)}
    for symbol, nominal in problem.nominal.items():
        value = float(best["values"][symbol])
        parameters.append(
            {
                "symbol": fit_symbols.get(symbol, symbol),
                "config_symbol": symbol,
                "fungmod": nominal,
                "copasi": value,
                "relative_difference": _relative(value, nominal),
            }
        )
    if copasi_improves:
        outcome = "copasi_improves"
    elif simulation_pass and optimum_pass:
        outcome = "reproduced"
    else:
        outcome = "not_reproduced"
    # Reported, not gated: FungMod's compiled core evaluated at COPASI's best point. When the two
    # objectives agree there as well, an optimum difference is the optimisers' stopping, not the solvers'.
    fungmod_at_best = problem.fungmod_objective({symbol: float(best["values"][symbol]) for symbol in problem.nominal})
    return {
        "outcome": outcome,
        "cross_check_at_copasi_best": {
            "fungmod_objective": fungmod_at_best,
            "copasi_objective": best["objective"],
            "relative_difference": _relative(fungmod_at_best, best["objective"]),
        },
        "simulation_gate": {
            "passed": simulation_pass,
            "worst_abs_difference_over_sigma": worst,
            "per_observable": simulation["max_abs_difference_over_sigma"],
            "objective_relative_difference": simulation["objective_relative_difference"],
            "copasi_objective": simulation["copasi"]["objective"],
            "fungmod_objective": simulation["fungmod"]["objective"],
        },
        "optimum_gate": {
            "passed": optimum_pass,
            "reference_objective": reference_objective,
            "copasi_best_objective": best["objective"],
            "copasi_best_source": best["source"],
            "relative_difference": optimum_relative,
            "copasi_improves": copasi_improves,
            "local_fit_objective": reproduction["local_fit"]["objective"],
            "start_objectives": [run["objective"] for run in reproduction["starts"]],
        },
        "parameters": parameters,
    }


def _plan_parameters(problem: Problem) -> list[PetabParameter]:
    rows = []
    with problem.export.parameters.open(encoding="utf-8") as handle:
        header = handle.readline().rstrip("\n").split("\t")
        for line in handle:
            values = dict(zip(header, line.rstrip("\n").split("\t"), strict=True))
            rows.append(
                PetabParameter(
                    values["parameterId"], float(values["lowerBound"]), float(values["upperBound"]), float(values["nominalValue"]),
                    values["parameterScale"], values["parameterName"],
                )
            )
    return rows


def render_report(plan: Mapping[str, Any], comparison: Mapping[str, Any], reproduction: Mapping[str, Any], digests: Mapping[str, str]) -> str:
    simulation = comparison["simulation_gate"]
    optimum = comparison["optimum_gate"]
    lines = [
        "# Gelain 2020 cross-solver reproduction (PEtab, COPASI)",
        "",
        f"Plan `{digests['plan']}`; outcome: **{comparison['outcome']}** (plan vocabulary).",
        "",
        "Retrospective check that an independent simulator and optimiser reproduce FungMod's",
        "all-condition least-squares optimum of the registry hydrolysis candidate on the same",
        "PEtab problem. It validates no biology.",
        "",
        "## Simulation at FungMod's optimum",
        "",
        f"- Worst |COPASI - FungMod| / sigma over all measurements: {simulation['worst_abs_difference_over_sigma']:.3g}"
        f" (gate {plan['gates']['simulation_agreement']['max_abs_difference_over_sigma']:g}).",
        f"- Objective: COPASI {simulation['copasi_objective']:.10g}, FungMod {simulation['fungmod_objective']:.10g},"
        f" relative difference {simulation['objective_relative_difference']:.3g}"
        f" (gate {plan['gates']['simulation_agreement']['objective_relative_difference']:g}).",
        "",
        "| Observable | max abs difference / sigma |",
        "| --- | --- |",
    ]
    for observable, value in simulation["per_observable"].items():
        lines.append(f"| `{observable}` | {value:.3g} |")
    lines += [
        "",
        "## COPASI optimum",
        "",
        f"- Method: {reproduction['method']['name']}, settings {json.dumps(reproduction['method']['settings'])},"
        f" integrator {reproduction['method']['integrator'].get('name', '')} with relative tolerance"
        f" {reproduction['method']['integrator'].get('Relative Tolerance')} and absolute tolerance"
        f" {reproduction['method']['integrator'].get('Absolute Tolerance')}.",
        f"- Local fit from FungMod's optimum: objective {optimum['local_fit_objective']:.10g}.",
        f"- Random starts: {len(optimum['start_objectives'])}; objectives "
        + ", ".join(f"{value:.6g}" for value in optimum["start_objectives"])
        + ".",
        f"- Best COPASI objective {optimum['copasi_best_objective']:.10g} ({optimum['copasi_best_source']}) versus FungMod"
        f" {optimum['reference_objective']:.10g}: relative difference {optimum['relative_difference']:.3g}"
        f" (gate {plan['gates']['optimum_agreement']['objective_relative_difference']:g});"
        f" COPASI improves on FungMod: {'yes' if optimum['copasi_improves'] else 'no'}.",
        "",
        "| Parameter | FungMod | COPASI best | relative difference |",
        "| --- | --- | --- | --- |",
    ]
    for row in comparison["parameters"]:
        lines.append(f"| `{row['symbol']}` | {row['fungmod']:.6g} | {row['copasi']:.6g} | {row['relative_difference']:.3g} |")
    cross = comparison["cross_check_at_copasi_best"]
    lines += [
        "",
        "Parameter differences are reported, not gated: stage A of the criticism study found two",
        "weakly determined directions along which equally good optima differ.",
        "",
        f"At COPASI's best point FungMod's compiled core gives objective {cross['fungmod_objective']:.10g} against COPASI's"
        f" {cross['copasi_objective']:.10g} (relative difference {cross['relative_difference']:.3g}); reported, not gated.",
        "",
        "## Weights",
        "",
        "COPASI's PEtab importer stored each observable's sigma as the column weight; the runner",
        "rewrote every weight to 1/sigma^2 and switched off per-experiment normalisation:",
        "",
        "| Condition | Observable | sigma | importer weight | weight used |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in reproduction["weights"]:
        lines.append(f"| `{row['condition']}` | `{row['observable']}` | {row['sigma']:.6g} | {row['importer_weight']:.6g} | {row['weight']:.6g} |")
    lines += [
        "",
        "## Versions",
        "",
        ", ".join(f"{name} {version}" for name, version in reproduction["versions"].items()) + ".",
        "",
        "## What this does not show",
        "",
    ]
    for claim in plan["claims_excluded"]:
        lines.append(f"- {claim}")
    return "\n".join(lines) + "\n"


def run_reproduction(
    root: Path,
    *,
    output_dir: Path,
    registry: FungModRegistry | None = None,
    plan_path: Path | None = None,
    starts: int | None = None,
    seed: int | None = None,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Export the problem, reproduce it in COPASI and write the comparison under ``output_dir``."""

    from fungal_model.standards.copasi import reproduce_in_copasi

    plan = load_plan(root, plan_path)
    say = log or (lambda message: None)
    problem = build_problem(root, output_dir / "petab", registry=registry, plan_path=plan_path)
    say(f"PEtab problem exported to {problem.export.directory}")
    settings = plan["copasi"]
    chosen_starts = int(settings["random_starts"] if starts is None else starts)
    chosen_seed = int(settings["seed"] if seed is None else seed)
    reproduction = reproduce_in_copasi(
        problem.export.problem_yaml,
        output_dir / "copasi",
        predictor=problem.fungmod_predictor(),
        method=str(settings["method"]),
        starts=chosen_starts,
        seed=chosen_seed,
        log=log,
    ).to_dict()
    integrator = reproduction["method"]["integrator"]
    if float(integrator.get("Relative Tolerance", np.nan)) != float(settings["integrator"]["relative_tolerance"]) or float(
        integrator.get("Absolute Tolerance", np.nan)
    ) != float(settings["integrator"]["absolute_tolerance"]):
        raise CultureBenchmarkError("COPASI integrator tolerances differ from the plan.")
    fit = reference_fit(root, plan)
    reference_objective = 2.0 * float(fit["cost"])
    comparison = compare(plan, problem, reproduction, reference_objective)
    comparison["plan_sha256"] = problem.digests["plan"]
    comparison["sources"] = dict(problem.digests)
    comparison["settings"] = {"starts": chosen_starts, "seed": chosen_seed, "as_planned": chosen_starts == int(settings["random_starts"]) and chosen_seed == int(settings["seed"])}
    comparison["fungmod_objective_at_nominal"] = problem.fungmod_objective()
    (output_dir / "comparison.json").write_text(json.dumps(comparison, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (output_dir / "report.md").write_text(render_report(plan, comparison, reproduction, problem.digests), encoding="utf-8")
    say(f"outcome: {comparison['outcome']}")
    return comparison


__all__ = [
    "BASELINE_MODEL",
    "MODEL_ID",
    "PLAN_PATH",
    "RESULTS_PATH",
    "Problem",
    "build_problem",
    "compare",
    "load_plan",
    "nominal_config_values",
    "reference_fit",
    "render_report",
    "run_reproduction",
    "verify_sources",
]
