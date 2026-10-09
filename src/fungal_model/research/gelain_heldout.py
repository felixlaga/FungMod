"""Frozen-prediction test of the Gelain 2020 cellulose models on two held-out loadings.

Gelain et al. (2020, doi:10.1016/j.cesx.2020.100085) grew *T. harzianum*
P49P11 on 5, 10, 20, 30 and 40 g/L cellulose. Every FungMod fit of this case
used 10, 20 and 30 g/L only; the article's Figure 3 plots the 5 and 40 g/L
cultures, which the source also kept out of its own parameter estimation.
``scripts/digitize_gelain_2020_figures_2_3.py`` digitizes that figure after
verifying the digitizer against the deposited 10 to 30 g/L means.

This module predicts the held-out cultures with models whose parameters were
frozen before the held-out data entered the repository, and scores them:

- ``registry_M0``: the registry case (hydrolysis candidate) with its
  calibrated records, exactly what ``VirtualExperiment`` runs;
- ``M1_induction_state``, ``M2_soluble_product_pool``,
  ``M3_conversion_dependent_accessibility``: the model-criticism variants with
  their recorded stage A all-condition fits (plan frozen 2026-10-05);
- ``gelain_published``: the source's own equations and parameters.

Nothing here fits a parameter. Agreement is retrospective (the article and its
figure are public), on digitized duplicate means and standard deviations, for
one strain in one laboratory; it validates no biology.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
from numpy.typing import ArrayLike

from fungal_model.calibration.compiled_predictor import ConfiguredCondition, ConfiguredConditionPredictor
from fungal_model.core.units import Q_
from fungal_model.io.model_config import ModelConfig
from fungal_model.registry import load_registry
from fungal_model.registry.store import FungModRegistry
from fungal_model.research import gelain_bayesian, gelain_criticism
from fungal_model.research.gelain_culture import CultureBenchmarkError, CultureDesign, parameters_from_records
from fungal_model.research.gelain_models import simulate_candidate
from fungal_model.screening import registry_case_config_factory

HELDOUT_DIR = Path("data/experiments/literature/gelain_2020_t_harzianum_heldout")
HELDOUT_CSV = HELDOUT_DIR / "gelain_2020_figure_3_heldout.csv"
TRAINING_SD_CSV = HELDOUT_DIR / "gelain_2020_figure_2_training_with_sd.csv"
SOURCE_PARAMETERS = Path("data/benchmarks/gelain_2020_v2/source_parameters.json")
CRITICISM_FITS = Path("data/benchmarks/gelain_2020_criticism/results/stage_a")

FUNGUS_ID = "trichoderma_harzianum_p49p11"
SUBSTRATE_ID = "cellulose_celufloc_200"
ENVIRONMENTS = {
    5.0: "gelain_2020_cellulose_batch_5gl",
    10.0: "gelain_2020_cellulose_batch_10gl",
    20.0: "gelain_2020_cellulose_batch_20gl",
    30.0: "gelain_2020_cellulose_batch_30gl",
    40.0: "gelain_2020_cellulose_batch_40gl",
}
TRAINING_LOADINGS = (10.0, 20.0, 30.0)
HELDOUT_LOADINGS = (5.0, 40.0)
VIRTUAL_BASE_ENVIRONMENT = ENVIRONMENTS[10.0]
INITIAL_LOADING_SYMBOL = gelain_criticism.INITIAL_LOADING_SYMBOL
OBSERVABLES = ("biomass", "substrate", "cellulase_activity", "beta_glucosidase_activity")
OBSERVABLE_UNITS = {
    "biomass": "gram / liter",
    "substrate": "gram / liter",
    "cellulase_activity": "filter_paper_unit / liter",
    "beta_glucosidase_activity": "beta_glucosidase_assay_unit / liter",
}
SAMPLING_TIMES_H = (8.0, 12.0, 24.0, 32.0, 48.0, 54.0, 72.0, 96.0)
INITIAL_BIOMASS_G_L = 0.3990672957214788  # registry record gelain_2020_cellulose_initial_biomass
CRITICISM_MODELS = (
    "M1_induction_state",
    "M2_soluble_product_pool",
    "M3_conversion_dependent_accessibility",
)
MODEL_IDS = ("registry_M0", *CRITICISM_MODELS, "gelain_published")
MODEL_LABELS = {
    "registry_M0": "FungMod registry case (M0)",
    "M1_induction_state": "FungMod M1 induction state",
    "M2_soluble_product_pool": "FungMod M2 soluble product pool",
    "M3_conversion_dependent_accessibility": "FungMod M3 accessibility loss",
    "gelain_published": "Gelain 2020 published model",
}
CLAIM_BOUNDARY = (
    "Frozen retrospective predictions of two held-out loadings digitized from a public figure "
    "(duplicate means and standard deviations, one strain, one laboratory). No parameter was fitted to "
    "these data. Agreement or disagreement is evidence about model structure under these conditions, "
    "not validation of a biological mechanism."
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------- observations


@dataclass(frozen=True)
class DigitizedObservation:
    """One digitized duplicate mean, its standard deviation and its censoring."""

    condition_g_l: float
    observable: str
    time_h: float
    mean: float
    sd: float | None
    sd_upper_bound: float
    censored_upper_limit: float | None
    digitization_error: float
    flags: tuple[str, ...]

    @property
    def censored(self) -> bool:
        return self.censored_upper_limit is not None

    @property
    def scoring_sd(self) -> float:
        """Measured SD, or its upper bound when the bar is hidden, combined with digitization error."""

        spread = self.sd if self.sd is not None else self.sd_upper_bound
        return math.hypot(spread, self.digitization_error)


def load_digitized(root: Path, path: Path = HELDOUT_CSV) -> tuple[DigitizedObservation, ...]:
    rows = list(csv.DictReader((root / path).open(encoding="utf-8")))
    observations = []
    for row in rows:
        observable = row["observable"]
        if observable not in OBSERVABLE_UNITS or row["units"] != OBSERVABLE_UNITS[observable]:
            raise CultureBenchmarkError(f"Unexpected observable or units in {path}: {observable} {row['units']}.")
        observations.append(
            DigitizedObservation(
                condition_g_l=float(row["condition_g_l"]),
                observable=observable,
                time_h=float(row["time_h"]),
                mean=float(row["mean"]),
                sd=float(row["sd"]) if row["sd"] else None,
                sd_upper_bound=float(row["sd_upper_bound"]),
                censored_upper_limit=float(row["censored_upper_limit"]) if row["censored_upper_limit"] else None,
                digitization_error=float(row["digitization_error"]),
                flags=tuple(flag for flag in row["flags"].split(";") if flag),
            )
        )
    if not observations:
        raise CultureBenchmarkError(f"{path} holds no observations.")
    return tuple(observations)


def deposited_training_means(root: Path) -> dict[float, dict[str, np.ndarray]]:
    """The deposited 10, 20 and 30 g/L means at the sampling times, keyed by loading and observable."""

    plan = gelain_bayesian.load_plan(root)
    conditions = gelain_bayesian.load_cellulose_conditions(root, plan)
    loadings = dict(zip(plan["registry_case"]["condition_ids"], TRAINING_LOADINGS, strict=True))
    result: dict[float, dict[str, np.ndarray]] = {}
    for condition in conditions:
        if tuple(float(t) for t in condition.times) != SAMPLING_TIMES_H:
            raise CultureBenchmarkError("Deposited sampling times changed.")
        result[loadings[condition.condition_id]] = {
            name: np.asarray(condition.observed[:, index], dtype=float) for index, name in enumerate(OBSERVABLES)
        }
    return result


def training_scales(root: Path) -> np.ndarray:
    """Per-observable training maxima, the normalization of the model-criticism stage A scores."""

    plan = gelain_bayesian.load_plan(root)
    return gelain_criticism.training_scales(gelain_bayesian.load_cellulose_conditions(root, plan))


# --------------------------------------------------------------------------- frozen models


@dataclass(frozen=True)
class FrozenModel:
    model_id: str
    label: str
    values: Mapping[str, float]
    source: str
    source_sha256: str | None


def frozen_models(root: Path) -> dict[str, FrozenModel]:
    """The five models with the parameter values frozen before the held-out data existed here."""

    models = {
        "registry_M0": FrozenModel(
            "registry_M0",
            MODEL_LABELS["registry_M0"],
            {},
            "data_registry/parameters/parameter_records.yml calibrated gelain_hydrolysis_* records "
            "(gelain_2020_joint_culture_v2 all-condition fit of the hydrolysis candidate)",
            None,
        )
    }
    for model_id in CRITICISM_MODELS:
        path = root / CRITICISM_FITS / model_id / "full_fit_primary.json"
        fit = json.loads(path.read_text(encoding="utf-8"))
        if fit["model"] != model_id or not fit["success"]:
            raise CultureBenchmarkError(f"{path} is not a successful {model_id} fit.")
        values = {item["config_symbol"]: float(item["value"]) for item in fit["parameters"] if not item.get("fixed")}
        models[model_id] = FrozenModel(model_id, MODEL_LABELS[model_id], values, str(path.relative_to(root)), _digest(path))
    source = root / SOURCE_PARAMETERS
    models["gelain_published"] = FrozenModel(
        "gelain_published",
        MODEL_LABELS["gelain_published"],
        {item["symbol"]: float(item["value"]) for item in json.loads(source.read_text(encoding="utf-8"))["parameters"]},
        f"{SOURCE_PARAMETERS} (Gelain 2020 all-condition published fit, deposited model doi:10.17632/shd3wcczsr.2)",
        _digest(source),
    )
    return models


class FrozenPredictor:
    """Observable predictions of the frozen models at any cellulose loading.

    Loadings with a registry environment record use it. Any other loading is a
    *virtual condition*: the 10 g/L registry condition rebuilt with its initial
    loading record overridden, through the same calibration hook every
    posterior draw uses. Predictions are ``len(times) x 4`` arrays in
    :data:`OBSERVABLE_UNITS` order of :data:`OBSERVABLES`.
    """

    def __init__(self, root: Path, registry: FungModRegistry | None = None) -> None:
        self.root = root
        self.registry = registry if registry is not None else load_registry(root / gelain_bayesian.REGISTRY_INDEX)
        self.models = frozen_models(root)
        bayesian_plan = gelain_bayesian.load_plan(root)
        self._mappings = gelain_bayesian.observable_mappings(bayesian_plan)
        if tuple(mapping.observable for mapping in self._mappings) != OBSERVABLES:
            raise CultureBenchmarkError("Observable order of the Bayesian plan changed.")
        self.registry_symbols = tuple(bayesian_plan["priors"]["symbol_map"].values())
        self._variants = gelain_criticism.model_variants(gelain_criticism.load_plan(root))
        self._factories: dict[str, Callable[[Mapping[str, float]], ModelConfig]] = {}
        self._predictors: dict[tuple[str, str], ConfiguredConditionPredictor] = {}
        self._published = parameters_from_records(
            json.loads((root / SOURCE_PARAMETERS).read_text(encoding="utf-8"))["parameters"],
            source="Gelain 2020 published all-condition fit (doi:10.17632/shd3wcczsr.2)",
        )

    @staticmethod
    def environment_for(loading_g_l: float) -> tuple[str, bool]:
        """Registry environment for a loading and whether the condition is virtual."""

        if float(loading_g_l) in ENVIRONMENTS:
            return ENVIRONMENTS[float(loading_g_l)], False
        return VIRTUAL_BASE_ENVIRONMENT, True

    def _base_factory(self, environment_id: str) -> Callable[[Mapping[str, float]], ModelConfig]:
        if environment_id not in self._factories:
            self._factories[environment_id] = registry_case_config_factory(
                fungus_id=FUNGUS_ID,
                substrate_id=SUBSTRATE_ID,
                environment_id=environment_id,
                registry=self.registry,
                mode="scientific",
            )
        return self._factories[environment_id]

    def _predictor(self, model_id: str, environment_id: str) -> ConfiguredConditionPredictor:
        key = (model_id, environment_id)
        if key in self._predictors:
            return self._predictors[key]
        base_factory = self._base_factory(environment_id)
        if model_id == "registry_M0":
            predictor = ConfiguredConditionPredictor(
                [ConfiguredCondition(environment_id, base_factory, self._mappings)],
                fitted_symbols=[*self.registry_symbols, INITIAL_LOADING_SYMBOL],
            )
        elif model_id in CRITICISM_MODELS:
            variant = self._variants[model_id]
            common = {symbol for symbol in variant.config_symbols if symbol.startswith("gelain_hydrolysis_")}
            common.add(INITIAL_LOADING_SYMBOL)

            def factory(values: Mapping[str, float]) -> ModelConfig:
                candidate = {**{fixed.config_symbol: fixed.value for fixed in variant.fixed}, **values}
                base = base_factory({symbol: value for symbol, value in candidate.items() if symbol in common}).raw
                return ModelConfig.from_mapping(gelain_criticism.variant_config(model_id, base, candidate), path=None)

            # The variants add exploratory study constants, so their configs run in exploratory mode.
            predictor = ConfiguredConditionPredictor(
                [ConfiguredCondition(environment_id, factory, self._mappings)],
                fitted_symbols=[*variant.config_symbols, INITIAL_LOADING_SYMBOL],
                enforce_maturity=False,
            )
        else:
            raise KeyError(model_id)
        self._predictors[key] = predictor
        return predictor

    def registry_defaults(self) -> dict[str, float]:
        """The registry case's own values of the nine calibrated constants."""

        config = self._base_factory(VIRTUAL_BASE_ENVIRONMENT)({})
        values = {}
        for block in config.parameters:
            for entry in block.parameters:
                symbol = entry["symbol"] if isinstance(entry, Mapping) else entry.symbol
                if symbol in self.registry_symbols:
                    values[symbol] = float(entry["value"] if isinstance(entry, Mapping) else entry.value)
        if set(values) != set(self.registry_symbols):
            raise CultureBenchmarkError("Registry case config does not carry all nine calibrated constants.")
        return values

    def predict(
        self,
        model_id: str,
        loading_g_l: float,
        times: ArrayLike,
        *,
        values: Mapping[str, float] | None = None,
    ) -> np.ndarray:
        """Predict one model at one loading; ``values`` overrides registry constants (posterior draws)."""

        times_array = np.asarray(times, dtype=float)
        if model_id == "gelain_published":
            if values:
                raise CultureBenchmarkError("The published model is evaluated at its published parameters only.")
            design = CultureDesign(
                f"cellulose_{loading_g_l:g}gl",
                "cellulose",
                Q_(times_array, "hour"),
                Q_(INITIAL_BIOMASS_G_L, "gram/liter"),
                Q_(float(loading_g_l), "gram/liter"),
                "Gelain 2020 Methods 2.2 initial conditions",
            )
            prediction = simulate_candidate(
                design,
                {"cellulase_activity": Q_(0.0, "gelain_fpu/liter"), "beta_glucosidase_activity": Q_(0.0, "gelain_beta_u/liter")},
                self._published,
                model="published",
                hypothesis_source="Gelain 2020 Eqs 2-10 with the deposited all-condition parameters",
            )
            return np.column_stack([prediction.observables[name].magnitude for name in OBSERVABLES])
        environment_id, _virtual = self.environment_for(loading_g_l)
        frozen = dict(self.registry_defaults()) if model_id == "registry_M0" else dict(self.models[model_id].values)
        if values:
            if model_id != "registry_M0":
                raise CultureBenchmarkError("Only the registry case takes posterior draws.")
            unknown = set(values) - set(self.registry_symbols)
            if unknown:
                raise CultureBenchmarkError(f"Unknown registry constants {sorted(unknown)}.")
            frozen.update(values)
        frozen[INITIAL_LOADING_SYMBOL] = float(loading_g_l)
        return self._predictor(model_id, environment_id).predict_values(frozen, environment_id, times_array)


# --------------------------------------------------------------------------- scoring


def score_model(
    predict_at: Callable[[float], np.ndarray],
    observations: Sequence[DigitizedObservation],
    scales: np.ndarray,
    *,
    loadings: Sequence[float] = HELDOUT_LOADINGS,
) -> dict[str, Any]:
    """Score one model's predictions at the sampling times against digitized observations.

    ``predict_at(loading)`` returns the prediction at :data:`SAMPLING_TIMES_H`.
    Uncensored points give RMSE, bias, the stage A normalized MSE (squared
    error over the squared training maximum) and z-scores against the
    measured SD combined with digitization error. A censored zero-line point is
    consistent when the prediction does not exceed its upper limit plus the
    digitization error.
    """

    cells: dict[str, Any] = {}
    pooled: dict[str, list[float]] = {name: [] for name in OBSERVABLES}
    for loading in loadings:
        prediction = predict_at(loading)
        for index, name in enumerate(OBSERVABLES):
            rows = [o for o in observations if o.condition_g_l == loading and o.observable == name]
            uncensored = [o for o in rows if not o.censored]
            censored = [o for o in rows if o.censored]
            if not uncensored:
                continue
            column = prediction[:, index]
            predicted = np.array([column[SAMPLING_TIMES_H.index(o.time_h)] for o in uncensored])
            observed = np.array([o.mean for o in uncensored])
            spread = np.array([o.scoring_sd for o in uncensored])
            error = predicted - observed
            with np.errstate(divide="ignore", invalid="ignore"):
                z = np.where(spread > 0.0, error / np.where(spread > 0.0, spread, 1.0), np.nan)
            consistent = [
                0.0 <= column[SAMPLING_TIMES_H.index(o.time_h)] <= float(o.censored_upper_limit or 0.0) + o.digitization_error
                for o in censored
            ]
            normalized = (error / scales[index]) ** 2
            pooled[name].extend(normalized.tolist())
            cells[f"{loading:g}gl:{name}"] = {
                "loading_g_l": loading,
                "observable": name,
                "n": int(observed.size),
                "rmse": float(np.sqrt(np.mean(error**2))),
                "bias": float(np.mean(error)),
                "nrmse_observed_range": float(np.sqrt(np.mean(error**2)) / max(np.ptp(observed), 1e-12)),
                "normalized_mse": float(np.mean(normalized)),
                "median_abs_z": float(np.nanmedian(np.abs(z))) if np.isfinite(z).any() else None,
                "fraction_within_2_sd": float(np.mean(np.abs(z[np.isfinite(z)]) <= 2.0)) if np.isfinite(z).any() else None,
                "censored_points": len(censored),
                "censored_consistent": int(sum(consistent)),
            }
    pooled_nmse = {name: float(np.mean(values)) for name, values in pooled.items() if values}
    return {
        "cells": cells,
        "pooled_normalized_mse": pooled_nmse,
        "mean_normalized_mse": float(np.mean(list(pooled_nmse.values()))),
        "mean_nrmse_observed_range": float(np.mean([cell["nrmse_observed_range"] for cell in cells.values()])),
    }


# --------------------------------------------------------------------------- model-free summaries


def threshold_time(times: ArrayLike, substrate: ArrayLike, initial: float, fraction: float) -> float | None:
    """First time the substrate falls to ``(1 - fraction) * initial``, by linear interpolation; None if never."""

    t = np.asarray(times, dtype=float)
    s = np.asarray(substrate, dtype=float)
    if not 0.0 < fraction < 1.0 or initial <= 0.0 or t.shape != s.shape or t.size < 2:
        raise CultureBenchmarkError("threshold_time needs a fraction in (0, 1), a positive initial value and aligned arrays.")
    target = (1.0 - fraction) * initial
    below = np.flatnonzero(s <= target)
    if below.size == 0:
        return None
    k = int(below[0])
    if k == 0:
        return float(t[0])
    t0, t1, s0, s1 = t[k - 1], t[k], s[k - 1], s[k]
    return float(t0 + (s0 - target) * (t1 - t0) / (s0 - s1)) if s0 != s1 else float(t1)


def apparent_yield(
    times: ArrayLike,
    biomass: ArrayLike,
    substrate: ArrayLike,
    initial_biomass: float,
    initial_substrate: float,
) -> dict[str, float]:
    """Biomass gained per cellulose consumed at the biomass peak: (X_peak - X0) / (S0 - S(t_peak)).

    A model-free summary of a time course. In a cellulose-only, constant-yield,
    mass-closed model it cannot exceed the yield constant; values above it mean
    biomass came from somewhere the model does not represent.
    """

    t = np.asarray(times, dtype=float)
    x = np.asarray(biomass, dtype=float)
    s = np.asarray(substrate, dtype=float)
    k = int(np.argmax(x))
    consumed = initial_substrate - s[k]
    if consumed <= 0.0:
        raise CultureBenchmarkError("No substrate consumed at the biomass peak.")
    return {
        "time_of_peak_h": float(t[k]),
        "peak_biomass": float(x[k]),
        "substrate_consumed": float(consumed),
        "apparent_yield": float((x[k] - initial_biomass) / consumed),
    }
