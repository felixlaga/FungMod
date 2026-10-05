"""Preregistered model criticism of the T. harzianum P49P11 cellulose registry case.

The study compares explicit mechanisms added to the registry hydrolysis
candidate on the three Gelain 2020 cellulose loadings under the frozen plan in
``data/benchmarks/gelain_2020_criticism/plan.json``: whole-condition
least-squares holdouts with the v2 complexity screen (stage A) and posterior
sampling with identifiability classes and posterior predictive coverage
(stage B). Every model variant is composed from the registry base case and
generic process laws; the registry records themselves are not changed. The
data are published duplicate means that already informed earlier model
development, so nothing here is blind, independent or a validation of biology.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import least_squares

from fungal_model.calibration.bayesian import (
    DEFAULT_IDENTIFIABILITY_CRITERIA,
    IDENTIFIED,
    WEAKLY_IDENTIFIED,
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
    posterior_predictive_coverage,
    run_ensemble_sampler,
)
from fungal_model.calibration.compiled_predictor import ConfiguredCondition, ConfiguredConditionPredictor
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.io.model_config import ModelConfig
from fungal_model.registry import load_registry
from fungal_model.registry.store import FungModRegistry
from fungal_model.research import gelain_bayesian
from fungal_model.research.gelain_bayesian import load_checkpoint, save_checkpoint
from fungal_model.research.gelain_culture import CultureBenchmarkError
from fungal_model.screening import registry_case_config_factory

PLAN_PATH = Path("data/benchmarks/gelain_2020_criticism/plan.json")
RESULTS_PATH = Path("data/benchmarks/gelain_2020_criticism/results")
BAYESIAN_PLAN_PATH = gelain_bayesian.PLAN_PATH
OBSERVATIONS_PATH = gelain_bayesian.OBSERVATIONS_PATH
REGISTRY_INDEX = gelain_bayesian.REGISTRY_INDEX
BASELINE_MODEL = "M0_baseline"
INDUCED_POOL_STATE = "induced_biomass_equivalent"
SOLUBLE_PRODUCT_STATE = "soluble_product_concentration"
MASS_UNITS = "gram / liter"
RATE_UNITS = "gram / liter / hour"
HYDROLYSIS_PROCESS = "cellulase_limited_cellulose_consumption"
SYNTHESIS_PROCESSES = ("cellulase_synthesis", "beta_glucosidase_synthesis")
CELLULOSE_STATE = "cellulose_concentration"
BIOMASS_STATE = "biomass_dry_mass_concentration"
LEDGER_STATE = "consumed_cellulose_not_retained_as_biomass"
INITIAL_LOADING_SYMBOL = "gelain_2020_cellulose_initial_loading"
YIELD_SYMBOL = "gelain_hydrolysis_Y"
INDUCTION_SYMBOL = "gelain_hydrolysis_K_ind"
UPTAKE_CAPACITY_SYMBOL = "gelain_criticism_uptake_capacity"
STUDY_SOURCE = (
    "Gelain 2020 model-criticism study plan gelain_2020_model_criticism_v1 (frozen 2026-10-05): a candidate "
    "value supplied by the study under its frozen plan, not a measured or registry constant."
)
STATISTICS = ("rmse", "bias", "normalized_mse")


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_plan(root: Path, plan_path: Path | None = None) -> dict[str, Any]:
    plan = json.loads((root / (plan_path or PLAN_PATH)).read_text(encoding="utf-8"))
    if plan.get("schema_version") != 1 or "models" not in plan or "decision_rules" not in plan:
        raise CultureBenchmarkError("Unsupported model-criticism plan schema.")
    if BASELINE_MODEL not in plan["models"]:
        raise CultureBenchmarkError("The plan must declare the baseline model.")
    return plan


@dataclass(frozen=True)
class ParameterSpec:
    symbol: str
    config_symbol: str
    lower: float
    upper: float
    units: str
    new: bool


@dataclass(frozen=True)
class FixedSpec:
    symbol: str
    config_symbol: str
    value: float
    units: str


@dataclass(frozen=True)
class ModelVariant:
    """One declared model: its free parameters, fixed constants and mechanism text."""

    model_id: str
    parameters: tuple[ParameterSpec, ...]
    fixed: tuple[FixedSpec, ...]
    mechanism: str

    @property
    def fit_symbols(self) -> tuple[str, ...]:
        return tuple(spec.symbol for spec in self.parameters)

    @property
    def config_symbols(self) -> tuple[str, ...]:
        return tuple(spec.config_symbol for spec in self.parameters)

    def log_bounds(self) -> tuple[np.ndarray, np.ndarray]:
        lower = np.log([spec.lower for spec in self.parameters])
        upper = np.log([spec.upper for spec in self.parameters])
        return lower, upper

    def config_values(self, fit_values: Mapping[str, float]) -> dict[str, float]:
        """Candidate values keyed by config symbol, including the fixed constants."""

        missing = sorted(set(self.fit_symbols).difference(fit_values))
        if missing:
            raise CultureBenchmarkError(f"{self.model_id}: candidate values are missing {missing}.")
        values = {spec.config_symbol: float(fit_values[spec.symbol]) for spec in self.parameters}
        for fixed in self.fixed:
            values[fixed.config_symbol] = fixed.value
        return values

    def fit_values(self, config_values: Mapping[str, float]) -> dict[str, float]:
        return {spec.symbol: float(config_values[spec.config_symbol]) for spec in self.parameters}


def model_variants(plan: Mapping[str, Any]) -> dict[str, ModelVariant]:
    variants: dict[str, ModelVariant] = {}
    for model_id, model in plan["models"].items():
        parameters = []
        for entry in model["parameters"]:
            lower, upper = float(entry["lower"]), float(entry["upper"])
            if not 0.0 < lower < upper:
                raise CultureBenchmarkError(f"{model_id}: {entry['symbol']} needs positive ordered bounds.")
            parameters.append(
                ParameterSpec(
                    symbol=str(entry["symbol"]),
                    config_symbol=str(entry["config_symbol"]),
                    lower=lower,
                    upper=upper,
                    units=str(entry["units"]),
                    new=bool(entry.get("new", False)),
                )
            )
        fixed = tuple(
            FixedSpec(str(entry["symbol"]), str(entry["config_symbol"]), float(entry["value"]), str(entry["units"]))
            for entry in model.get("fixed_parameters", [])
        )
        symbols = [spec.symbol for spec in parameters] + [item.symbol for item in fixed]
        if len(set(symbols)) != len(symbols):
            raise CultureBenchmarkError(f"{model_id}: duplicate parameter symbols.")
        variants[model_id] = ModelVariant(model_id, tuple(parameters), fixed, str(model["mechanism"]))
    return variants


def observed_conditions(root: Path, plan: Mapping[str, Any]) -> list[ObservedCondition]:
    """The three cellulose loadings with the shared assumed error model the plan declares."""

    bayesian_plan = gelain_bayesian.load_plan(root)
    fields = plan["shared_structure"]["error_model_fields"]
    declared = bayesian_plan["error_model"]
    if (
        float(declared["relative_sd_to_training_max"]) != float(fields["relative_sd_to_training_max"])
        or float(declared["rho_biomass_substrate"]) != float(fields["rho_biomass_substrate"])
        or str(declared["evidence"]) != str(fields["evidence"])
    ):
        raise CultureBenchmarkError("The criticism plan's error model disagrees with the Bayesian study plan it reuses.")
    return gelain_bayesian.load_cellulose_conditions(root, bayesian_plan)


def _parameter_entry(symbol: str, value: float, units: str, *, name: str, notes: str) -> dict[str, Any]:
    return {
        "name": name,
        "symbol": symbol,
        "value": float(value),
        "units": units,
        "uncertainty": None,
        "source": STUDY_SOURCE,
        "confidence_level": "low",
        "notes": notes,
        "measurement_method": "Candidate value set by the model-criticism study (least-squares start, fit or posterior sample).",
        "validity_range": "The Gelain 2020 model-criticism study only; never a registry constant.",
    }


def _product_map_entry(
    template: Mapping[str, Any],
    *,
    map_id: str,
    name: str,
    reactants: Mapping[str, float],
    products: Mapping[str, float],
    notes: str,
    coefficient_bindings: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    entry = deepcopy(dict(template))
    entry["id"] = map_id
    data = entry["data"]
    data["name"] = name
    data["maturity"] = "exploratory"
    data["notes"] = notes
    data["provenance"] = {
        "source": STUDY_SOURCE,
        "confidence_level": "low",
        "coefficient_provenance": {state: "model-criticism study variant" for state in list(reactants) + list(products)},
        "notes": notes,
    }
    data["reactants"] = dict(reactants)
    data["products"] = dict(products)
    # The template's bindings describe its own products; a variant map declares its own or none.
    data["coefficient_bindings"] = {state: dict(binding) for state, binding in (coefficient_bindings or {}).items()}
    return entry


def _process_by_id(raw: Mapping[str, Any], process_id: str) -> dict[str, Any]:
    for process in raw["processes"]:
        if process["id"] == process_id:
            return process
    raise CultureBenchmarkError(f"Base config has no process {process_id!r}.")


def _add_state(raw: dict[str, Any], state: str, value: float, units: str, *, conserved: bool) -> None:
    raw["initial_state"]["states"][state] = {"value": float(value), "units": units}
    for validator in raw["validators"]:
        if validator["validator_type"] == "non_negative":
            validator["species"].append(state)
        elif validator["validator_type"] == "mass_balance" and conserved:
            validator["conserved_weights"][state] = 1.0


def variant_config(model_id: str, base: Mapping[str, Any], values: Mapping[str, float]) -> dict[str, Any]:
    """Compose a model variant's config from the registry base config and candidate values.

    ``base`` is the registry case config rebuilt for the common nine constants;
    ``values`` carries every config symbol of the variant. M0 returns the base
    unchanged. The other variants run in exploratory mode because their added
    constants are study candidates, not registry records.
    """

    raw = deepcopy(dict(base))
    if model_id == BASELINE_MODEL:
        return raw
    raw["mode"] = "exploratory"
    raw["maturity"] = "exploratory"
    raw["name"] = f"{raw['name']} [{model_id} variant of the model-criticism study]"
    entries: list[dict[str, Any]] = raw["parameters"][0]["parameters"]
    roles = _process_by_id(raw, HYDROLYSIS_PROCESS)["output_state_roles"]

    def add_parameter(symbol: str, units: str, name: str, notes: str) -> None:
        if symbol not in values:
            raise CultureBenchmarkError(f"{model_id}: no candidate value for {symbol!r}.")
        entries.append(_parameter_entry(symbol, values[symbol], units, name=name, notes=notes))

    if model_id == "M1_induction_state":
        _add_state(raw, INDUCED_POOL_STATE, 0.0, MASS_UNITS, conserved=False)
        for process_id in SYNTHESIS_PROCESSES:
            process = _process_by_id(raw, process_id)
            process["states"] = {"producer": INDUCED_POOL_STATE, "product": process["states"]["product"]}
            process["parameters"] = {
                "specific_rate": process["parameters"]["specific_rate"],
                "rate_units": process["parameters"]["rate_units"],
            }
            process["assumptions"] = [
                "Activity is produced in proportion to the induced biomass equivalent z, not to instantaneous biomass; "
                "the material cost of production is not represented."
            ]
        raw["processes"].extend(
            [
                {
                    "id": "induction_state_formation",
                    "process_type": "proportional_synthesis",
                    "states": {"producer": BIOMASS_STATE, "inducer": CELLULOSE_STATE, "product": INDUCED_POOL_STATE},
                    "parameters": {
                        "specific_rate": "gelain_criticism_k_z",
                        "induction_half_saturation": INDUCTION_SYMBOL,
                        "rate_units": RATE_UNITS,
                    },
                    "modifiers": [],
                    "output_state_roles": roles,
                    "assumptions": [
                        "The induced biomass equivalent forms from biomass with saturable cellulose induction "
                        "(dz/dt = k_z X S / (K_ind + S)); k_z is fixed at one per hour because the scale of z is not "
                        "separately identifiable from the specific production rates."
                    ],
                },
                {
                    "id": "induction_state_loss",
                    "process_type": "first_order",
                    "states": {"source": INDUCED_POOL_STATE},
                    "parameters": {"rate_constant": "gelain_criticism_kz_loss"},
                    "modifiers": [],
                    "output_state_roles": roles,
                    "assumptions": ["The induced biomass equivalent decays at a constant first-order rate; it is bookkeeping, not mass."],
                },
            ]
        )
        add_parameter("gelain_criticism_k_z", "1 / hour", "Induction state formation rate (fixed scale)", "Fixed at 1 per hour by the plan; defines z as induced biomass equivalent.")
        add_parameter("gelain_criticism_kz_loss", "1 / hour", "Induction state loss rate", "Memory time constant of the induced state (plan symbol kz_loss).")
    elif model_id == "M2_soluble_product_pool":
        if "gelain_criticism_P0" not in values or YIELD_SYMBOL not in values or "gelain_criticism_mu" not in values:
            raise CultureBenchmarkError("M2 needs P0, mu and the yield among the candidate values.")
        _add_state(raw, SOLUBLE_PRODUCT_STATE, values["gelain_criticism_P0"], MASS_UNITS, conserved=True)
        maps = raw["entities"]["product_maps"]
        template = next(entry for entry in maps if entry["id"] == "cellulose_conversion_with_biomass_yield")
        yield_value = float(values[YIELD_SYMBOL])
        if not 0.0 < yield_value <= 1.0:
            raise CultureBenchmarkError("The biomass yield must lie in (0, 1].")
        raw["entities"]["product_maps"] = [
            entry for entry in maps if entry["id"] != "cellulose_conversion_with_biomass_yield"
        ] + [
            _product_map_entry(
                template,
                map_id="cellulose_to_soluble_product",
                name="Cellulose hydrolysis to a soluble product pool",
                reactants={CELLULOSE_STATE: 1.0},
                products={SOLUBLE_PRODUCT_STATE: 1.0},
                notes="One gram of hydrolysed cellulose forms one gram of soluble product (dry-mass basis); nothing is assimilated here.",
            ),
            _product_map_entry(
                template,
                map_id="soluble_product_uptake_with_biomass_yield",
                name="Soluble product uptake to biomass with an explicit yield and a closure ledger",
                reactants={SOLUBLE_PRODUCT_STATE: 1.0},
                products={BIOMASS_STATE: yield_value, LEDGER_STATE: 1.0 - yield_value},
                notes="One gram of soluble product taken up forms Y gram of biomass dry mass; (1 - Y) gram is booked to the closure ledger.",
                coefficient_bindings={
                    BIOMASS_STATE: {"parameter_symbol": YIELD_SYMBOL, "complement": False},
                    LEDGER_STATE: {"parameter_symbol": YIELD_SYMBOL, "complement": True},
                },
            ),
        ]
        hydrolysis = _process_by_id(raw, HYDROLYSIS_PROCESS)
        hydrolysis["states"]["product"] = SOLUBLE_PRODUCT_STATE
        hydrolysis["product_map"] = "cellulose_to_soluble_product"
        hydrolysis["modifiers"] = [
            {
                "type": "product_inhibition",
                "product_state": SOLUBLE_PRODUCT_STATE,
                "inhibition_constant": "gelain_criticism_Ki",
            }
        ]
        hydrolysis["assumptions"] = [
            "Bulk cellulose consumption is proportional to measured filter-paper activity, saturates in cellulose and is "
            "reversibly inhibited by the soluble product (consumption = k_h F S / (K_h + S) / (1 + P / K_i)).",
            "Hydrolysed cellulose enters a soluble product pool; biomass forms only by uptake from that pool.",
        ]
        raw["processes"].append(
            {
                "id": "soluble_product_uptake",
                "process_type": "homogeneous_michaelis_menten",
                "states": {"substrate": SOLUBLE_PRODUCT_STATE, "enzyme": BIOMASS_STATE, "product": BIOMASS_STATE},
                "parameters": {"kcat": UPTAKE_CAPACITY_SYMBOL, "km": "gelain_criticism_Ks", "rate_units": RATE_UNITS},
                "modifiers": [],
                "output_state_roles": roles,
                "product_map": "soluble_product_uptake_with_biomass_yield",
                "assumptions": [
                    "Biomass takes up the soluble product with Monod kinetics (uptake = (mu / Y) X P / (K_s + P)); "
                    "growth is Y times uptake and the complement is booked to the closure ledger.",
                    "The initial soluble product P0 stands for unmeasured soluble carbon carried in by inoculum and medium.",
                ],
            }
        )
        add_parameter("gelain_criticism_mu", "1 / hour", "Maximum specific growth rate on the soluble pool", "Plan symbol mu.")
        add_parameter("gelain_criticism_Ks", MASS_UNITS, "Soluble product uptake half-saturation", "Plan symbol Ks.")
        add_parameter("gelain_criticism_Ki", MASS_UNITS, "Soluble product inhibition constant of hydrolysis", "Plan symbol Ki.")
        add_parameter("gelain_criticism_P0", MASS_UNITS, "Initial soluble product", "Plan symbol P0; an explicit unknown, not a measured initial condition.")
        entries.append(
            _parameter_entry(
                UPTAKE_CAPACITY_SYMBOL,
                values["gelain_criticism_mu"] / yield_value,
                "1 / hour",
                name="Maximum specific uptake rate of the soluble pool",
                notes="Derived as mu / Y from the candidate values; not an independent parameter.",
            )
        )
    elif model_id == "M3_conversion_dependent_accessibility":
        hydrolysis = _process_by_id(raw, HYDROLYSIS_PROCESS)
        hydrolysis["modifiers"] = [
            {
                "type": "substrate_reactivity",
                "substrate_state": CELLULOSE_STATE,
                "reference_concentration": INITIAL_LOADING_SYMBOL,
                "exponent": "gelain_criticism_n",
            }
        ]
        hydrolysis["assumptions"] = list(hydrolysis["assumptions"]) + [
            "Consumption is further multiplied by (S / S0)^n, the Kadam 2004 substrate reactivity factor generalised by an exponent."
        ]
        add_parameter("gelain_criticism_n", "dimensionless", "Substrate reactivity exponent", "Plan symbol n; n = 1 is the Kadam form, n -> 0 recovers the baseline.")
    else:
        raise CultureBenchmarkError(f"Unknown model variant {model_id!r}.")
    outputs = dict(raw.get("outputs", {}))
    outputs["directory"] = None
    outputs["save"] = []
    outputs["plots"] = []
    raw["outputs"] = outputs
    return raw


def build_predictor(
    registry: FungModRegistry, plan: Mapping[str, Any], model_id: str, *, bayesian_plan: Mapping[str, Any]
) -> ConfiguredConditionPredictor:
    """A compiled-core predictor for one model variant over the three loadings."""

    variant = model_variants(plan)[model_id]
    case = bayesian_plan["registry_case"]
    mappings = gelain_bayesian.observable_mappings(bayesian_plan)
    common = {symbol for symbol in variant.config_symbols if symbol.startswith("gelain_hydrolysis_")}
    conditions = []
    for condition_id, environment_id in zip(case["condition_ids"], case["environment_ids"], strict=True):
        base_factory = registry_case_config_factory(
            fungus_id=case["fungus_id"],
            substrate_id=case["substrate_id"],
            environment_id=environment_id,
            registry=registry,
            mode=case["mode"],
        )

        def factory(values: Mapping[str, float], *, base_factory: Callable[..., ModelConfig] = base_factory) -> ModelConfig:
            # Fixed constants of the variant are part of every candidate; callers that supply only the
            # fitted symbols (the posterior sampler) still get a complete config.
            candidate = {**{fixed.config_symbol: fixed.value for fixed in variant.fixed}, **values}
            base = base_factory({symbol: value for symbol, value in candidate.items() if symbol in common}).raw
            raw = variant_config(model_id, base, candidate)
            return ModelConfig.from_mapping(raw, path=None)

        conditions.append(ConfiguredCondition(condition_id, factory, mappings))
    return ConfiguredConditionPredictor(conditions, fitted_symbols=list(variant.config_symbols))


def midpoint_values(variant: ModelVariant) -> dict[str, float]:
    lower, upper = variant.log_bounds()
    return dict(zip(variant.fit_symbols, np.exp((lower + upper) / 2.0).tolist(), strict=True))


# ---------------------------------------------------------------------------
# Stage A: least-squares whole-condition holdouts
# ---------------------------------------------------------------------------


def score_predictions(predicted: np.ndarray, observed: np.ndarray, names: Sequence[str], scales: np.ndarray) -> dict[str, Any]:
    values, data, normalizer = np.asarray(predicted, dtype=float), np.asarray(observed, dtype=float), np.asarray(scales, dtype=float)
    if values.shape != data.shape or not np.all(np.isfinite(values)) or normalizer.shape != (len(names),) or np.any(normalizer <= 0):
        raise CultureBenchmarkError("Aligned finite predictions and positive scoring scales are required.")
    error = values - data
    return {
        "rmse": dict(zip(names, np.sqrt(np.mean(error**2, axis=0)).tolist(), strict=True)),
        "bias": dict(zip(names, np.mean(error, axis=0).tolist(), strict=True)),
        "normalized_mse": dict(zip(names, np.mean((error / normalizer) ** 2, axis=0).tolist(), strict=True)),
        "n": int(values.size),
    }


def training_scales(training: Sequence[ObservedCondition]) -> np.ndarray:
    scales = np.max(np.concatenate([condition.observed for condition in training], axis=0), axis=0)
    if np.any(scales <= 0.0):
        raise CultureBenchmarkError("Every observable needs a positive training maximum.")
    return scales


class _PredictionFailure(RuntimeError):
    pass


def fit_model(
    predictor: ConfiguredConditionPredictor,
    variant: ModelVariant,
    training: Sequence[ObservedCondition],
    *,
    scenario: str,
    starts: int,
    seed: int,
    max_nfev: int,
    fixed: Mapping[str, float] | None = None,
    warm_start: Mapping[str, float] | None = None,
    relative_singular_value_cutoff: float = 1e-6,
    near_bound_log_fraction: float = 1e-3,
) -> dict[str, Any]:
    """Multi-start least squares in log-parameter space on the training conditions only.

    ``scenario`` is ``primary`` (residuals scaled by the training maxima) or
    ``correlated_assumption`` (whitened by the shared assumed error model).
    ``fixed`` pins fit symbols for profile refits. Failures are returned as
    failed starts, never converted into a fit.
    """

    if scenario not in {"primary", "correlated_assumption"}:
        raise CultureBenchmarkError(f"Unknown scenario {scenario!r}.")
    if not training:
        raise CultureBenchmarkError("At least one training condition is required.")
    names = training[0].observables
    pinned = dict(fixed or {})
    unknown = sorted(set(pinned).difference(variant.fit_symbols))
    if unknown:
        raise CultureBenchmarkError(f"Cannot pin unknown symbols {unknown}.")
    free = [spec for spec in variant.parameters if spec.symbol not in pinned]
    if not free:
        raise CultureBenchmarkError("At least one free parameter is required.")
    lower = np.log([spec.lower for spec in free])
    upper = np.log([spec.upper for spec in free])
    scales = training_scales(training)
    rng = np.random.default_rng(seed)
    initial = [(lower + upper) / 2.0 if warm_start is None else np.log([float(warm_start[spec.symbol]) for spec in free])]
    initial[0] = np.clip(initial[0], lower, upper)
    initial.extend(rng.uniform(lower, upper) for _ in range(max(starts - 1, 0)))

    def values_from(log_values: np.ndarray) -> dict[str, float]:
        values = {spec.symbol: float(value) for spec, value in zip(free, np.exp(log_values), strict=True)}
        values.update(pinned)
        return values

    def residual(log_values: np.ndarray) -> np.ndarray:
        config_values = variant.config_values(values_from(log_values))
        pieces = []
        for condition in training:
            try:
                predicted = predictor.predict_values(config_values, condition.condition_id, condition.times)
            except Exception as exc:  # noqa: BLE001 - any solver or assembly failure is a failed evaluation
                raise _PredictionFailure(str(exc)) from exc
            if not np.all(np.isfinite(predicted)):
                raise _PredictionFailure(f"non-finite prediction for {condition.condition_id}")
            if scenario == "primary":
                pieces.append(((predicted - condition.observed) / scales).ravel())
            else:
                pieces.append(condition.error.residuals(predicted, condition.observed))
        return np.concatenate(pieces)

    attempts: list[dict[str, Any]] = []
    best: Any = None
    for index, x0 in enumerate(initial):
        try:
            solution = least_squares(residual, x0, bounds=(lower, upper), max_nfev=max_nfev, method="trf")
        except _PredictionFailure as exc:
            attempts.append({"start": index, "success": False, "reason": str(exc)[:200]})
            continue
        cost = float(solution.cost)
        attempts.append({"start": index, "success": bool(solution.success), "cost": cost, "nfev": int(solution.nfev), "status": int(solution.status)})
        if np.isfinite(cost) and (best is None or cost < best.cost):
            best = solution
    if best is None:
        return {
            "model": variant.model_id,
            "scenario": scenario,
            "training_conditions": [condition.condition_id for condition in training],
            "success": False,
            "starts": attempts,
            "reason": "every start failed",
        }
    singular = np.linalg.svd(np.asarray(best.jac, dtype=float), compute_uv=False)
    practical_rank = int(np.sum(singular > singular[0] * relative_singular_value_cutoff)) if singular.size and singular[0] > 0 else 0
    log_range = upper - lower
    near_bounds = [
        spec.symbol
        for spec, value in zip(free, best.x, strict=True)
        if min(value - lower[free.index(spec)], upper[free.index(spec)] - value) <= near_bound_log_fraction * log_range[free.index(spec)]
    ]
    fitted = values_from(best.x)
    return {
        "model": variant.model_id,
        "scenario": scenario,
        "training_conditions": [condition.condition_id for condition in training],
        "success": bool(best.success),
        "cost": float(best.cost),
        "nfev": int(best.nfev),
        "normalization": {name: float(scale) for name, scale in zip(names, scales, strict=True)},
        "parameters": [
            {"symbol": spec.symbol, "config_symbol": spec.config_symbol, "value": fitted[spec.symbol], "units": spec.units, "fixed": spec.symbol in pinned}
            for spec in variant.parameters
        ],
        "diagnostics": {
            "singular_values": singular.tolist(),
            "practical_rank": practical_rank,
            "free_parameters": len(free),
            "full_rank": practical_rank == len(free),
            "condition_number": float(singular[0] / singular[-1]) if singular.size and singular[-1] > 0 else None,
            "near_bounds": near_bounds,
        },
        "starts": attempts,
        "noise": {condition.condition_id: condition.error.to_dict(condition.times.size) for condition in training}
        if scenario == "correlated_assumption"
        else {},
    }


def _fit_values(fit: Mapping[str, Any]) -> dict[str, float]:
    return {entry["symbol"]: float(entry["value"]) for entry in fit["parameters"]}


def _write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return file_digest(path)


def _screen(model_summary: Mapping[str, Any], baseline_summary: Mapping[str, Any], screen: Mapping[str, Any]) -> dict[str, Any]:
    """The plan's complexity screen of one model against the baseline (primary scenario)."""

    verdict: dict[str, Any] = {"reference": BASELINE_MODEL, "passed": False, "reasons": []}
    model_mean = model_summary["mean_normalized_mse"]
    base_mean = baseline_summary["mean_normalized_mse"]
    improvement = 1.0 - model_mean / base_mean if base_mean > 0 else float("nan")
    verdict["relative_improvement"] = improvement
    if not improvement >= float(screen["minimum_relative_cv_improvement"]):
        verdict["reasons"].append("pooled normalized held-out error improves by less than the required fraction")
    worsened = []
    for name, value in model_summary["pooled_normalized_mse"].items():
        reference = baseline_summary["pooled_normalized_mse"][name]
        if reference > 0 and value / reference - 1.0 > float(screen["maximum_observable_worsening"]):
            worsened.append(name)
    verdict["observables_worsened"] = worsened
    if worsened:
        verdict["reasons"].append("an observable worsens by more than the allowed fraction")
    if screen["full_practical_rank_required"] and not model_summary["full_rank_everywhere"]:
        verdict["reasons"].append("local sensitivity rank is deficient in a fold or the all-condition fit")
    verdict["passed"] = not verdict["reasons"]
    return verdict


def run_stage_a(
    root: Path,
    *,
    output_dir: Path,
    registry: FungModRegistry | None = None,
    models: Sequence[str] | None = None,
    scenarios: Sequence[str] | None = None,
    starts: int | None = None,
    max_nfev: int | None = None,
    profiles: bool = True,
    reuse_existing: bool = True,
    plan_path: Path | None = None,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Whole-condition holdouts, all-condition fits, the screen and profiles for the declared models.

    With ``reuse_existing`` a model whose fits and folds already exist under
    ``output_dir`` for the same plan digest is loaded instead of refitted, so
    the stage can be split across processes or resumed; the screen then needs
    the baseline's files to be present as well.
    """

    plan = load_plan(root, plan_path)
    bayesian_plan = gelain_bayesian.load_plan(root)
    store = registry if registry is not None else load_registry(root / REGISTRY_INDEX)
    conditions = observed_conditions(root, plan)
    variants = model_variants(plan)
    stage = plan["stage_A_least_squares"]
    chosen = list(models) if models is not None else list(variants)
    unknown = sorted(set(chosen).difference(variants))
    if unknown:
        raise CultureBenchmarkError(f"Unknown models {unknown}.")
    if BASELINE_MODEL not in chosen:
        chosen.insert(0, BASELINE_MODEL)
    chosen.sort(key=lambda name: (name != BASELINE_MODEL, name))
    scenario_names = list(scenarios) if scenarios is not None else ["primary", "correlated_assumption"]
    n_starts = int(starts if starts is not None else stage["starts"])
    nfev = int(max_nfev if max_nfev is not None else stage["max_nfev"])
    seed = int(stage["seed"])
    names = conditions[0].observables
    inputs = {
        "plan_sha256": file_digest(root / (plan_path or PLAN_PATH)),
        "observations_sha256": file_digest(root / OBSERVATIONS_PATH),
        "bayesian_plan_sha256": file_digest(root / BAYESIAN_PLAN_PATH),
        "starts": n_starts,
        "max_nfev": nfev,
        "seed": seed,
        "models": chosen,
        "scenarios": scenario_names,
        "amendments": plan["amendments"],
    }
    stage_dir = output_dir / "stage_a"
    stage_dir.mkdir(parents=True, exist_ok=True)
    _write_json(stage_dir / "inputs.json", inputs)
    summaries: dict[str, dict[str, Any]] = {}
    for model_id in chosen:
        model_dir = stage_dir / model_id
        model_summary: dict[str, Any] = {"model": model_id, "scenarios": {}}
        existing = _existing_stage_a_files(model_dir, scenario_names, inputs["plan_sha256"]) if reuse_existing else None
        if existing is not None:
            if log is not None:
                log(f"{model_id}: reusing existing stage A files")
            for scenario, (full, folds) in existing.items():
                model_summary["scenarios"][scenario] = _scenario_summary(full, folds, names)
            summaries[model_id] = model_summary
            continue
        variant = variants[model_id]
        predictor = build_predictor(store, plan, model_id, bayesian_plan=bayesian_plan)
        for scenario in scenario_names:
            if log is not None:
                log(f"{model_id} / {scenario}: all-condition fit")
            full = fit_model(predictor, variant, conditions, scenario=scenario, starts=n_starts, seed=seed, max_nfev=nfev)
            full["plan_sha256"] = inputs["plan_sha256"]
            _write_json(model_dir / f"full_fit_{scenario}.json", full)
            folds = []
            for held_out in conditions:
                training = [condition for condition in conditions if condition.condition_id != held_out.condition_id]
                if log is not None:
                    log(f"{model_id} / {scenario}: holding out {held_out.condition_id}")
                fit = fit_model(predictor, variant, training, scenario=scenario, starts=n_starts, seed=seed + 1, max_nfev=nfev)
                fold: dict[str, Any] = {"condition": held_out.condition_id, "scenario": scenario, "fit": fit}
                if fit["success"] or "cost" in fit:
                    config_values = variant.config_values(_fit_values(fit))
                    predicted = predictor.predict_values(config_values, held_out.condition_id, held_out.times)
                    frozen = {
                        "plan_sha256": inputs["plan_sha256"],
                        "model": model_id,
                        "scenario": scenario,
                        "condition": held_out.condition_id,
                        "training_conditions": fit["training_conditions"],
                        "times_h": held_out.times.tolist(),
                        "observables": list(names),
                        "predictions": np.asarray(predicted, dtype=float).tolist(),
                        "parameters": fit["parameters"],
                    }
                    frozen_path = model_dir / "frozen_predictions" / f"{held_out.condition_id}_{scenario}.json"
                    fold["frozen_prediction_file"] = frozen_path.relative_to(output_dir).as_posix()
                    fold["frozen_prediction_sha256"] = _write_json(frozen_path, frozen)
                    scales = np.array([fit["normalization"][name] for name in names])
                    fold["score"] = score_predictions(predicted, held_out.observed, names, scales)
                else:
                    fold["score"] = None
                folds.append(fold)
            _write_json(model_dir / f"folds_{scenario}.json", folds)
            model_summary["scenarios"][scenario] = _scenario_summary(full, folds, names)
        summaries[model_id] = model_summary
    screen = stage["screen"]
    for model_id, summary in summaries.items():
        for scenario, scenario_summary in summary["scenarios"].items():
            if model_id == BASELINE_MODEL:
                scenario_summary["screen"] = {"reference": BASELINE_MODEL, "passed": True, "reasons": ["baseline"]}
            elif scenario in summaries.get(BASELINE_MODEL, {}).get("scenarios", {}):
                scenario_summary["screen"] = _screen(scenario_summary, summaries[BASELINE_MODEL]["scenarios"][scenario], screen)
            else:
                scenario_summary["screen"] = {"reference": BASELINE_MODEL, "passed": False, "reasons": ["not run: baseline results absent"]}
    if profiles:
        for model_id, summary in summaries.items():
            primary = summary["scenarios"].get("primary")
            if primary is None or model_id == BASELINE_MODEL or not primary["screen"]["passed"]:
                continue
            if log is not None:
                log(f"{model_id}: profiles")
            summary["profiles"] = profile_model(
                build_predictor(store, plan, model_id, bayesian_plan=bayesian_plan),
                variants[model_id],
                conditions,
                _fit_values({"parameters": primary["full_fit_parameters"]}),
                factors=(0.5, 1.0, 2.0),
                seed=seed,
                max_nfev=min(nfev, 100),
            )
            _write_json(stage_dir / model_id / "profiles_primary.json", summary["profiles"])
    comparison = {"inputs": inputs, "models": summaries, "decision_rule": plan["decision_rules"]["R1_holdout_support"]}
    _write_json(stage_dir / "comparison.json", comparison)
    (stage_dir / "report.md").write_text(render_stage_a_report(plan, comparison), encoding="utf-8")
    return comparison


def _existing_stage_a_files(model_dir: Path, scenarios: Sequence[str], plan_sha256: str) -> dict[str, tuple[dict[str, Any], list[dict[str, Any]]]] | None:
    """Load a model's stage A fits and folds if every scenario exists for this plan digest."""

    found: dict[str, tuple[dict[str, Any], list[dict[str, Any]]]] = {}
    for scenario in scenarios:
        full_path = model_dir / f"full_fit_{scenario}.json"
        folds_path = model_dir / f"folds_{scenario}.json"
        if not full_path.exists() or not folds_path.exists():
            return None
        full = json.loads(full_path.read_text(encoding="utf-8"))
        folds = json.loads(folds_path.read_text(encoding="utf-8"))
        if full.get("plan_sha256") != plan_sha256:
            return None
        found[scenario] = (full, folds)
    return found


def _scenario_summary(full: Mapping[str, Any], folds: Sequence[Mapping[str, Any]], names: Sequence[str]) -> dict[str, Any]:
    scored = [fold for fold in folds if fold.get("score") is not None]
    pooled = {
        name: float(np.mean([fold["score"]["normalized_mse"][name] for fold in scored])) if scored else float("nan")
        for name in names
    }
    return {
        "folds_scored": len(scored),
        "folds": len(folds),
        "pooled_normalized_mse": pooled,
        "mean_normalized_mse": float(np.mean(list(pooled.values()))) if scored else float("nan"),
        "pooled_rmse": {
            name: float(np.sqrt(np.mean([fold["score"]["rmse"][name] ** 2 for fold in scored]))) if scored else float("nan")
            for name in names
        },
        "full_rank_everywhere": bool(full.get("diagnostics", {}).get("full_rank", False))
        and all(fold["fit"].get("diagnostics", {}).get("full_rank", False) for fold in folds),
        "full_fit_success": bool(full["success"]),
        "full_fit_parameters": full.get("parameters"),
        "near_bounds": sorted({symbol for fold in folds for symbol in fold["fit"].get("diagnostics", {}).get("near_bounds", [])}),
    }


def profile_model(
    predictor: ConfiguredConditionPredictor,
    variant: ModelVariant,
    conditions: Sequence[ObservedCondition],
    fitted: Mapping[str, float],
    *,
    factors: Sequence[float],
    seed: int,
    max_nfev: int,
) -> dict[str, Any]:
    """Nuisance-reoptimised profile loss at fitted value x factors (primary scenario)."""

    reference = fit_model(predictor, variant, conditions, scenario="primary", starts=1, seed=seed, max_nfev=max_nfev, warm_start=fitted)
    profiles: dict[str, Any] = {"reference_cost": reference.get("cost"), "parameters": {}}
    for spec in variant.parameters:
        points = []
        for factor in factors:
            value = float(np.clip(fitted[spec.symbol] * factor, spec.lower, spec.upper))
            refit = fit_model(
                predictor, variant, conditions, scenario="primary", starts=1, seed=seed, max_nfev=max_nfev,
                fixed={spec.symbol: value}, warm_start=fitted,
            )
            points.append({"factor": factor, "value": value, "cost": refit.get("cost"), "success": refit["success"]})
        costs = [point["cost"] for point in points if point["cost"] is not None]
        profiles["parameters"][spec.symbol] = {
            "points": points,
            "reference_improved": bool(costs) and reference.get("cost") is not None and min(costs) < reference["cost"] - 1e-12,
        }
    return profiles


def render_stage_a_report(plan: Mapping[str, Any], comparison: Mapping[str, Any]) -> str:
    lines = [
        f"# {plan['benchmark_id']}: stage A",
        "",
        plan["design_status"],
        "",
        f"Plan digest `{comparison['inputs']['plan_sha256']}`; {comparison['inputs']['starts']} starts, "
        f"{comparison['inputs']['max_nfev']} evaluations per start.",
        "",
        "| Model | Scenario | Folds scored | Mean normalized held-out MSE | Improvement vs M0 | Full rank everywhere | Screen |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for model_id, summary in comparison["models"].items():
        for scenario, item in summary["scenarios"].items():
            screen = item["screen"]
            improvement = screen.get("relative_improvement")
            lines.append(
                f"| {model_id} | {scenario} | {item['folds_scored']}/{item['folds']} | {item['mean_normalized_mse']:.4g} | "
                f"{'' if improvement is None else f'{improvement:+.1%}'} | {item['full_rank_everywhere']} | "
                f"{'passed' if screen['passed'] else 'failed: ' + '; '.join(screen['reasons'])} |"
            )
    lines.extend(["", "Per-observable pooled normalized held-out MSE (primary scenario):", ""])
    names = next(iter(comparison["models"].values()))["scenarios"]
    first_scenario = next(iter(names))
    observables = list(next(iter(comparison["models"].values()))["scenarios"][first_scenario]["pooled_normalized_mse"])
    lines.append("| Model | " + " | ".join(observables) + " |")
    lines.append("| --- | " + " | ".join("---" for _ in observables) + " |")
    for model_id, summary in comparison["models"].items():
        item = summary["scenarios"].get("primary")
        if item is None:
            continue
        lines.append(f"| {model_id} | " + " | ".join(f"{item['pooled_normalized_mse'][name]:.4g}" for name in observables) + " |")
    lines.extend(["", "Claims excluded by the plan: " + "; ".join(plan["reporting"]["claims_excluded"]) + ".", ""])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Stage B: posterior sampling, identifiability and coverage
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PosteriorStudy:
    model_id: str
    plan: Mapping[str, Any]
    predictor: ConfiguredConditionPredictor
    problem: BayesianProblem
    settings: SamplerSettings
    center: dict[str, float]


def sampler_settings(
    plan: Mapping[str, Any], *, dimension: int, n_steps: int | None = None, burn_in: int | None = None, n_walkers: int | None = None
) -> SamplerSettings:
    """Planned sampler settings; the walker count follows the plan's rule of at least two per dimension."""

    spec = dict(plan["stage_B_posterior"]["sampler"])
    criteria = plan["stage_B_posterior"]["identifiability"]
    planned = int(spec["walkers"])
    minimum = 2 * int(dimension)
    minimum += minimum % 2
    walkers = int(n_walkers) if n_walkers is not None else max(planned, minimum)
    return SamplerSettings(
        n_walkers=walkers,
        n_steps=int(n_steps if n_steps is not None else spec["steps"]),
        burn_in=int(burn_in if burn_in is not None else spec["burn_in"]),
        seed=int(spec["seed"]),
        stretch_scale=float(spec["stretch_scale"]),
        initial_spread=float(spec["initial_spread_fraction_of_prior_width"]),
        initial_distribution="ball",
        autocorrelation_tolerance=50.0,
        minimum_effective_samples=100.0,
        credible_mass=float(criteria["credible_mass"]),
    )


def build_posterior_study(
    root: Path,
    model_id: str,
    center: Mapping[str, float],
    *,
    registry: FungModRegistry | None = None,
    plan_path: Path | None = None,
    n_steps: int | None = None,
    burn_in: int | None = None,
    n_walkers: int | None = None,
) -> PosteriorStudy:
    """Priors from the plan's bounds, the shared noise multiplier and the predictor for one model."""

    plan = load_plan(root, plan_path)
    bayesian_plan = gelain_bayesian.load_plan(root)
    store = registry if registry is not None else load_registry(root / REGISTRY_INDEX)
    variant = model_variants(plan)[model_id]
    predictor = build_predictor(store, plan, model_id, bayesian_plan=bayesian_plan)
    conditions = observed_conditions(root, plan)
    source = f"{plan['benchmark_id']}: {plan['shared_structure']['priors']}"
    priors = [
        PriorSpecification(
            symbol=spec.config_symbol,
            lower=Q_(spec.lower, spec.units),
            upper=Q_(spec.upper, spec.units),
            source=source,
            kind="log_uniform",
        )
        for spec in variant.parameters
    ]
    noise = plan["shared_structure"]["error_model_fields"]["noise_scale"]
    noise_priors = [
        NoiseScalePrior(
            tuple(conditions[0].observables),
            float(noise["lower"]),
            float(noise["upper"]),
            f"{plan['benchmark_id']}: {plan['shared_structure']['error_model']}",
            label=str(noise["label"]),
        )
    ]
    config_center = variant.config_values(center)
    first = predictor._conditions[predictor.condition_ids[0]]  # noqa: SLF001 - research helper reading the public config
    config = first.config_factory(config_center)
    base_parameters = ParameterSet([Parameter.from_dict(entry) for block in config.parameters for entry in block.parameters])
    problem = build_bayesian_problem(
        base_parameters=base_parameters,
        priors=priors,
        conditions=conditions,
        predict=predictor,
        noise_scale_priors=noise_priors,
    )
    full_center = dict(config_center)
    full_center[f"noise_scale:{noise['label']}"] = 1.0
    settings = sampler_settings(plan, dimension=problem.dimension, n_steps=n_steps, burn_in=burn_in, n_walkers=n_walkers)
    return PosteriorStudy(model_id, plan, predictor, problem, settings, full_center)


CHECKPOINT_NAME = gelain_bayesian.CHECKPOINT_NAME


def sample_posterior_study(
    study: PosteriorStudy,
    output_dir: Path,
    *,
    map_function: Callable[..., Any] = map,
    checkpoint_every: int = 250,
    resume: bool = True,
    log: Callable[[str], None] | None = None,
    log_posterior: Callable[[np.ndarray], float] | None = None,
) -> EnsembleRun:
    """Run or resume the ensemble sampler for one model, checkpointing the chain."""

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
            log(f"{study.model_id}: resuming from checkpoint with {done} steps")
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
            log(f"{study.model_id}: checkpoint at {combined.chain.shape[1]} steps; mean acceptance {np.mean(combined.acceptance_fraction):.3f}")

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


def analyze_posterior_study(study: PosteriorStudy, run: EnsembleRun, *, with_predictive: bool = True) -> tuple[BayesianCalibrationResult, dict[str, Any] | None]:
    plan = study.plan
    stage = plan["stage_B_posterior"]
    result = analyze_run(
        study.problem,
        run,
        settings=study.settings,
        source=f"{plan['benchmark_id']} / {study.model_id}: {plan['models'][study.model_id]['mechanism']}",
        criteria=DEFAULT_IDENTIFIABILITY_CRITERIA,
        local_information=True,
        notes=(plan["design_status"], *plan["reporting"]["claims_excluded"]),
    )
    coverage = None
    if with_predictive:
        predictive_spec = stage["posterior_predictive"]
        grid = np.arange(0.0, 96.0 + 1e-9, 2.0)
        predictive = posterior_predictive(
            result,
            times_by_condition={condition.condition_id: grid for condition in study.problem.conditions},
            draws=int(predictive_spec["draws"]),
            quantiles=tuple(float(q) for q in predictive_spec["quantiles"]),
            seed=int(stage["sampler"]["seed"]),
        )
        result = BayesianCalibrationResult(
            problem=result.problem, run=result.run, settings=result.settings, criteria=result.criteria, source=result.source,
            diagnostics=result.diagnostics, summaries=result.summaries, identifiability=result.identifiability,
            local_information=result.local_information, best_sample=result.best_sample, noise_evidence=result.noise_evidence,
            data_digest=result.data_digest, posterior_predictive=predictive, notes=result.notes,
        )
        coverage = posterior_predictive_coverage(
            result, draws=int(predictive_spec["draws"]), credible_mass=float(stage["identifiability"]["credible_mass"]), seed=int(stage["sampler"]["seed"])
        )
    return result, coverage


def write_posterior_outputs(
    study: PosteriorStudy, result: BayesianCalibrationResult, coverage: Mapping[str, Any] | None, output_dir: Path, *, root: Path, plan_path: Path | None = None
) -> dict[str, Path]:
    paths = result.save(output_dir, thin=10)
    inputs = {
        "model": study.model_id,
        "plan_sha256": file_digest(root / (plan_path or PLAN_PATH)),
        "observations_sha256": file_digest(root / OBSERVATIONS_PATH),
        "bayesian_plan_sha256": file_digest(root / BAYESIAN_PLAN_PATH),
        "predictor": study.predictor.to_dict(),
        "data_sha256": result.data_digest,
        "center": study.center,
    }
    inputs_path = output_dir / "inputs.json"
    inputs_path.write_text(json.dumps(inputs, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    coverage_path = output_dir / "coverage.json"
    coverage_path.write_text(json.dumps(coverage if coverage is not None else {"status": "not computed"}, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    verdicts = stage_b_verdicts(study, result, stage_a_comparison=_stage_a_comparison_next_to(output_dir))
    verdicts_path = output_dir / "verdicts.json"
    verdicts_path.write_text(json.dumps(verdicts, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    report_path = output_dir / "report.md"
    report_path.write_text(render_stage_b_report(study, result, coverage, verdicts=verdicts), encoding="utf-8")
    artifacts = {
        name: file_digest(path)
        for name, path in (
            ("bayesian_calibration.json", paths["summary"]),
            ("posterior_samples.csv", paths["samples"]),
            ("inputs.json", inputs_path),
            ("coverage.json", coverage_path),
            ("verdicts.json", verdicts_path),
            ("report.md", report_path),
        )
    }
    artifacts_path = output_dir / "artifacts.json"
    artifacts_path.write_text(json.dumps(artifacts, indent=2) + "\n", encoding="utf-8")
    return {**paths, "inputs": inputs_path, "coverage": coverage_path, "verdicts": verdicts_path, "report": report_path, "artifacts": artifacts_path}


def stage_b_verdicts(
    study: PosteriorStudy, result: BayesianCalibrationResult, *, stage_a_comparison: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Apply the plan's R2 and R3 rules to a posterior and combine them with the recorded R1 screen.

    Every verdict carries ``provisional=True`` when the chain missed the
    declared convergence rule, as the plan requires.
    """

    plan = study.plan
    variant = model_variants(plan)[study.model_id]
    rules = plan["decision_rules"]
    multiplier = result.summaries.get("noise_scale:all_observables")
    adequate = None if multiplier is None else bool(float(multiplier["lower"]) <= 1.0 <= float(multiplier["upper"]))
    added = {spec.config_symbol: spec.symbol for spec in variant.parameters if spec.new}
    classes = {symbol: result.identifiability[symbol]["class"] for symbol in added if symbol in result.identifiability}
    identified = {IDENTIFIED, WEAKLY_IDENTIFIED}
    r3 = None if not added else all(klass in identified for klass in classes.values())
    r1 = None
    if stage_a_comparison is not None:
        scenario = stage_a_comparison.get("models", {}).get(study.model_id, {}).get("scenarios", {}).get("primary")
        if scenario is not None:
            r1 = bool(scenario["screen"]["passed"])
    if study.model_id == BASELINE_MODEL:
        outcome = "baseline (R1 and R3 do not apply)"
    elif r1 is None:
        outcome = "not scored (stage A screen not recorded)"
    elif not r1:
        outcome = "not supported (fails R1)"
    elif r3:
        outcome = "supported (R1 and R3)"
    else:
        outcome = "improves fit but unidentified (R1, not R3)"
    return {
        "provisional": not bool(result.converged),
        "R1_holdout_support": r1,
        "R2_adequacy": adequate,
        "R2_multiplier_interval": None if multiplier is None else [float(multiplier["lower"]), float(multiplier["upper"])],
        "R3_identification": r3,
        "added_parameter_classes": {added[symbol]: klass for symbol, klass in classes.items()},
        "outcome": outcome,
        "rules": {key: rules[key] for key in ("R1_holdout_support", "R2_adequacy", "R3_identification", "R4_coverage")},
    }


def _stage_a_comparison_next_to(output_dir: Path) -> Mapping[str, Any] | None:
    candidate = output_dir.parent.parent / "stage_a" / "comparison.json"
    if candidate.exists():
        return json.loads(candidate.read_text(encoding="utf-8"))
    return None


def render_stage_b_report(
    study: PosteriorStudy,
    result: BayesianCalibrationResult,
    coverage: Mapping[str, Any] | None,
    *,
    verdicts: Mapping[str, Any] | None = None,
) -> str:
    plan = study.plan
    variant = model_variants(plan)[study.model_id]
    by_config = {spec.config_symbol: spec for spec in variant.parameters}
    diagnostics = result.diagnostics
    taus = diagnostics.get("integrated_autocorrelation_time", [])
    reliable = diagnostics.get("autocorrelation_estimate_reliable", [])
    label = "provisional (chain not converged by the declared rule)" if not result.converged else "final"
    lines = [
        f"# {plan['benchmark_id']}: stage B, {study.model_id}",
        "",
        plan["models"][study.model_id]["mechanism"],
        "",
        f"Converged by the declared rule: **{result.converged}** (mean acceptance "
        f"{diagnostics['mean_acceptance_fraction']:.3f}, {diagnostics['post_burn_in_steps']} post-burn-in steps, "
        f"{diagnostics['walkers']} walkers). Verdicts below are **{label}**.",
        "",
        "| Parameter | Added | Class | Median | 95% interval | Prior box | Width / prior width | tau | tau reliable |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    order = list(result.summaries)
    for symbol, verdict in result.identifiability.items():
        summary = result.summaries[symbol]
        interval = verdict["credible_interval"]
        prior = verdict["prior_bounds"]
        coordinate = order.index(symbol) if symbol in order else -1
        tau = taus[coordinate] if 0 <= coordinate < len(taus) else None
        ok = reliable[coordinate] if 0 <= coordinate < len(reliable) else None
        added = "yes" if symbol in by_config and by_config[symbol].new else ""
        name = by_config[symbol].symbol if symbol in by_config else symbol
        lines.append(
            f"| `{name}` | {added} | {verdict['class']} | {summary['median']:.4g} | [{interval[0]:.3g}, {interval[1]:.3g}] | "
            f"[{prior[0]:.3g}, {prior[1]:.3g}] | {verdict['interval_width_fraction_of_prior']:.2f} | "
            f"{'n/a' if tau is None else f'{tau:.0f}'} | {'n/a' if ok is None else ok} |"
        )
    multiplier = result.summaries.get("noise_scale:all_observables")
    if multiplier is not None:
        lines.extend(
            [
                "",
                "| Noise-scale multiplier | Posterior median | 95% interval |",
                "| --- | --- | --- |",
                f"| `all_observables` | {multiplier['median']:.3g} | [{multiplier['lower']:.3g}, {multiplier['upper']:.3g}] |",
            ]
        )
    if verdicts is not None:
        lines.extend(
            [
                "",
                "Decision rules (" + ("provisional" if verdicts["provisional"] else "final") + "):",
                "",
                f"- R1 holdout support (stage A screen, primary): {verdicts['R1_holdout_support']}",
                f"- R2 adequacy (multiplier interval contains 1.0): {verdicts['R2_adequacy']}"
                + (f"; interval {verdicts['R2_multiplier_interval']}" if verdicts["R2_multiplier_interval"] else ""),
                f"- R3 identification of added parameters: {verdicts['R3_identification']}"
                + (f"; classes {verdicts['added_parameter_classes']}" if verdicts["added_parameter_classes"] else ""),
                f"- Outcome: **{verdicts['outcome']}**",
            ]
        )
    if coverage is not None and "overall" in coverage:
        overall = coverage["overall"]
        lines.extend(
            [
                "",
                f"Posterior predictive coverage at {float(coverage['credible_mass']):.0%} with measurement noise "
                f"({coverage['draws']} draws, {coverage.get('failed_draws', 0)} failed):",
                "",
            ]
        )
        for name, item in overall.items():
            lines.append(f"- {name}: {item['inside']}/{item['observations']} inside ({item['fraction']:.0%})")
    lines.extend(["", "Claims excluded by the plan: " + "; ".join(plan["reporting"]["claims_excluded"]) + ".", ""])
    return "\n".join(lines)


__all__ = [
    "BASELINE_MODEL",
    "ModelVariant",
    "PLAN_PATH",
    "PosteriorStudy",
    "RESULTS_PATH",
    "analyze_posterior_study",
    "build_posterior_study",
    "build_predictor",
    "file_digest",
    "fit_model",
    "load_plan",
    "midpoint_values",
    "model_variants",
    "observed_conditions",
    "profile_model",
    "render_stage_a_report",
    "render_stage_b_report",
    "run_stage_a",
    "sample_posterior_study",
    "score_predictions",
    "stage_b_verdicts",
    "training_scales",
    "variant_config",
    "write_posterior_outputs",
]
