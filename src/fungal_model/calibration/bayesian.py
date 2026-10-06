"""Posterior sampling, identifiability classification and posterior prediction.

Gradient-free affine-invariant ensemble sampling (the stretch move of Goodman
and Weare 2010, https://doi.org/10.2140/camcos.2010.5.65, as popularized by
emcee, Foreman-Mackey et al. 2013, https://doi.org/10.1086/670067) over
explicit priors and explicit Gaussian observation-error models. The module
adds no model, no default noise level and no biology: the caller supplies the
prediction function, the error model with its evidence label, and the priors
with their sources. Every threshold used to call a parameter identified is
declared in the result. A finite chain cannot prove global identifiability;
the classification is conditional on the prior box, the error model and the
sampled chain, and the result says so.

Observation errors whose magnitude is unknown may be scaled by per-observable
multipliers sampled jointly with the parameters. Such a multiplier absorbs
both measurement noise and model misfit, and the result labels it as
``estimated_from_residuals`` rather than measured.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np

from fungal_model.calibration.observation_error import GaussianObservationError
from fungal_model.core.numerics import IntegrationError
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.provenance import ProvenanceError, has_text
from fungal_model.core.units import Q_, Quantity, assert_compatible

SCHEMA_VERSION = "1.0.0"
PRIOR_LOG_UNIFORM = "log_uniform"
PRIOR_UNIFORM = "uniform"
PRIOR_KINDS = (PRIOR_LOG_UNIFORM, PRIOR_UNIFORM)
COORDINATE_LOG = "natural_log"
COORDINATE_LINEAR = "linear"
NOISE_SCALE_PREFIX = "noise_scale:"
METHOD_SOURCES = {
    "sampler": "Goodman and Weare (2010) affine-invariant ensemble stretch move, https://doi.org/10.2140/camcos.2010.5.65",
    "autocorrelation": "Integrated autocorrelation time with the automated window of Sokal (1997) as implemented by emcee, Foreman-Mackey et al. (2013), https://doi.org/10.1086/670067",
    "local_information": "Finite-difference Fisher information of the whitened residuals at the best posterior sample; eigen-decomposition after Gutenkunst et al. (2007), https://doi.org/10.1371/journal.pcbi.0030189",
}
CLAIM_BOUNDARY = (
    "Posterior and identifiability statements are conditional on the declared prior box, the supplied "
    "observation-error model (and any estimated noise-scale multipliers, which absorb model misfit), the "
    "model structure and a finite chain. They do not establish global identifiability, empirical "
    "validation or biological truth; a parameter the data do not identify must be kept as the reported range."
)
IDENTIFIED = "identified"
WEAKLY_IDENTIFIED = "weakly_identified"
BOUNDED_ABOVE_ONLY = "bounded_above_only"
BOUNDED_BELOW_ONLY = "bounded_below_only"
PRIOR_DOMINATED = "prior_dominated"
IDENTIFIABILITY_CLASSES = (IDENTIFIED, WEAKLY_IDENTIFIED, BOUNDED_ABOVE_ONLY, BOUNDED_BELOW_ONLY, PRIOR_DOMINATED)
NOISE_SCALE_EVIDENCE = "estimated_from_residuals"

ConditionPredictor = Callable[[ParameterSet, str, np.ndarray], np.ndarray]
"""``predict(parameters, condition_id, times)`` returns a ``len(times) x observables`` array."""

_PREDICTION_FAILURES = (ValueError, IntegrationError, FloatingPointError, RuntimeError, ArithmeticError, KeyError)


def _finite_array(values: Any, *, name: str, ndim: int) -> np.ndarray:
    array = np.array(values, dtype=float, copy=True)
    if array.ndim != ndim or not array.size or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be a nonempty finite {ndim}-dimensional array.")
    array.setflags(write=False)
    return array


@dataclass(frozen=True)
class PriorSpecification:
    """A bounded prior on one parameter with explicit provenance.

    ``log_uniform`` priors are uniform in ``ln(value)`` between positive bounds
    and are sampled in natural-log coordinates; ``uniform`` priors are uniform
    in the value itself. Bounds carry units and are converted to the base
    parameter's units when the problem is built.
    """

    symbol: str
    lower: Quantity
    upper: Quantity
    source: str
    kind: str = PRIOR_LOG_UNIFORM

    def __post_init__(self) -> None:
        if not has_text(self.symbol):
            raise ValueError("A prior requires a parameter symbol.")
        if not has_text(self.source):
            raise ProvenanceError(f"Prior on {self.symbol!r} requires a source.")
        if self.kind not in PRIOR_KINDS:
            raise ValueError(f"Prior kind must be one of {PRIOR_KINDS}; got {self.kind!r}.")
        units = str(self.lower.units)
        lower = float(np.asarray(self.lower.magnitude, dtype=float))
        upper = float(assert_compatible(self.upper, units, name=self.symbol).magnitude)
        if not np.isfinite(lower) or not np.isfinite(upper) or upper <= lower:
            raise ValueError(f"Prior on {self.symbol!r} needs finite ordered bounds.")
        if self.kind == PRIOR_LOG_UNIFORM and lower <= 0.0:
            raise ValueError(f"A log-uniform prior on {self.symbol!r} needs a positive lower bound.")

    def bounds_in(self, units: str) -> tuple[float, float]:
        lower = float(assert_compatible(self.lower, units, name=self.symbol).magnitude)
        upper = float(assert_compatible(self.upper, units, name=self.symbol).magnitude)
        return lower, upper

    def to_dict(self, units: str) -> dict[str, Any]:
        lower, upper = self.bounds_in(units)
        return {"symbol": self.symbol, "kind": self.kind, "lower": lower, "upper": upper, "units": units, "source": self.source}


@dataclass(frozen=True)
class NoiseScalePrior:
    """Log-uniform prior on one multiplier of the supplied standard deviations.

    ``observables`` names the observables that share the multiplier. A prior on
    one observable is labelled after it; one shared by several observables
    needs an explicit ``label``. The sampled coordinate is
    ``noise_scale:<name>``.
    """

    observables: tuple[str, ...]
    lower: float
    upper: float
    source: str
    label: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.observables, str):
            raise TypeError("Noise-scale prior observables must be a sequence of names, not one string.")
        names = tuple(self.observables)
        object.__setattr__(self, "observables", names)
        if not names or not all(has_text(name) for name in names):
            raise ValueError("A noise-scale prior requires at least one observable name.")
        if len(set(names)) != len(names):
            raise ValueError(f"Noise-scale prior observables must be unique: {names}.")
        if len(names) > 1 and not has_text(self.label):
            raise ValueError(f"A noise-scale prior shared by {names} requires a label.")
        if not has_text(self.source):
            raise ProvenanceError(f"Noise-scale prior {self.name!r} requires a source.")
        if not (np.isfinite(self.lower) and np.isfinite(self.upper) and 0.0 < self.lower < self.upper):
            raise ValueError(f"Noise-scale prior {self.name!r} needs finite positive ordered bounds.")

    @property
    def name(self) -> str:
        """Coordinate name: the label, or the single observable it scales."""

        return self.label if has_text(self.label) else self.observables[0]

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.name,
            "observables": list(self.observables),
            "kind": PRIOR_LOG_UNIFORM,
            "lower": self.lower,
            "upper": self.upper,
            "source": self.source,
            "evidence": NOISE_SCALE_EVIDENCE,
        }


@dataclass(frozen=True)
class ObservedCondition:
    """Observations of one experimental condition with their error model.

    Rows are individual observations; repeated times are replicates. Values are
    expressed in the error model's observable units and order.
    """

    condition_id: str
    times: np.ndarray
    observed: np.ndarray
    error: GaussianObservationError

    def __post_init__(self) -> None:
        if not has_text(self.condition_id):
            raise ValueError("An observed condition requires an identifier.")
        times = _finite_array(self.times, name=f"{self.condition_id} times", ndim=1)
        observed = _finite_array(self.observed, name=f"{self.condition_id} observations", ndim=2)
        if observed.shape != (times.size, len(self.error.observables)):
            raise ValueError(
                f"{self.condition_id}: observations must have shape (times, observables) = "
                f"({times.size}, {len(self.error.observables)}); got {observed.shape}."
            )
        self.error.arrays(times.size)
        object.__setattr__(self, "times", times)
        object.__setattr__(self, "observed", observed)

    @property
    def observables(self) -> tuple[str, ...]:
        return self.error.observables

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition_id": self.condition_id,
            "times": self.times.tolist(),
            "observed": self.observed.tolist(),
            "error": self.error.to_dict(self.times.size),
        }


@dataclass(frozen=True)
class SamplerSettings:
    """Ensemble-sampler settings; every value is recorded in the result."""

    n_walkers: int
    n_steps: int
    burn_in: int
    seed: int
    stretch_scale: float = 2.0
    initial_spread: float = 0.05
    initial_distribution: str = "ball"
    autocorrelation_tolerance: float = 50.0
    minimum_effective_samples: float = 100.0
    credible_mass: float = 0.95

    def __post_init__(self) -> None:
        if self.n_walkers < 4 or self.n_walkers % 2:
            raise ValueError("n_walkers must be an even integer of at least 4.")
        if self.n_steps < 1 or not 0 <= self.burn_in < self.n_steps:
            raise ValueError("n_steps must be positive and burn_in must lie in [0, n_steps).")
        if not np.isfinite(self.stretch_scale) or self.stretch_scale <= 1.0:
            raise ValueError("stretch_scale must exceed 1.")
        if not np.isfinite(self.initial_spread) or not 0.0 < self.initial_spread <= 1.0:
            raise ValueError("initial_spread must lie in (0, 1] as a fraction of the prior width.")
        if self.initial_distribution not in {"ball", "prior"}:
            raise ValueError("initial_distribution must be 'ball' or 'prior'.")
        if self.autocorrelation_tolerance <= 0.0 or self.minimum_effective_samples <= 0.0:
            raise ValueError("Convergence tolerances must be positive.")
        if not 0.0 < self.credible_mass < 1.0:
            raise ValueError("credible_mass must lie in (0, 1).")

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_walkers": self.n_walkers,
            "n_steps": self.n_steps,
            "burn_in": self.burn_in,
            "seed": self.seed,
            "stretch_scale": self.stretch_scale,
            "initial_spread": self.initial_spread,
            "initial_distribution": self.initial_distribution,
            "autocorrelation_tolerance": self.autocorrelation_tolerance,
            "minimum_effective_samples": self.minimum_effective_samples,
            "credible_mass": self.credible_mass,
        }


@dataclass(frozen=True)
class IdentifiabilityCriteria:
    """Declared thresholds for classifying a posterior relative to its prior.

    Widths are measured in the sampled coordinate (natural log for log-uniform
    priors) as a fraction of the prior width. Contact with a bound means the
    credible interval ends within ``bound_contact_fraction`` of the prior
    width from that bound.
    """

    source: str
    identified_max_width_fraction: float = 0.25
    weak_max_width_fraction: float = 0.75
    bound_contact_fraction: float = 0.02

    def __post_init__(self) -> None:
        if not has_text(self.source):
            raise ProvenanceError("Identifiability criteria require a source describing the convention.")
        if not 0.0 < self.identified_max_width_fraction < self.weak_max_width_fraction <= 1.0:
            raise ValueError("Width fractions must satisfy 0 < identified < weak <= 1.")
        if not 0.0 < self.bound_contact_fraction < 0.5:
            raise ValueError("bound_contact_fraction must lie in (0, 0.5).")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "identified_max_width_fraction": self.identified_max_width_fraction,
            "weak_max_width_fraction": self.weak_max_width_fraction,
            "bound_contact_fraction": self.bound_contact_fraction,
            "classes": list(IDENTIFIABILITY_CLASSES),
        }


DEFAULT_IDENTIFIABILITY_CRITERIA = IdentifiabilityCriteria(
    source=(
        "FungMod declared convention: a parameter is identified when its credible interval spans at most "
        "one quarter of the prior width without touching a bound, weakly identified up to three quarters, "
        "bounded on one side only when the interval touches exactly one bound, and prior-dominated otherwise. "
        "Fractions are analysis conventions, not statistical tests."
    )
)


@dataclass(frozen=True)
class BayesianProblem:
    """Log posterior, residuals and coordinate transforms for one calibration."""

    base_parameters: ParameterSet
    priors: tuple[PriorSpecification, ...]
    noise_scale_priors: tuple[NoiseScalePrior, ...]
    conditions: tuple[ObservedCondition, ...]
    predict: ConditionPredictor
    labels: tuple[str, ...]
    units: tuple[str, ...]
    coordinate_kinds: tuple[str, ...]
    lower: np.ndarray
    upper: np.ndarray

    @property
    def dimension(self) -> int:
        return len(self.labels)

    @property
    def parameter_symbols(self) -> tuple[str, ...]:
        return tuple(prior.symbol for prior in self.priors)

    def coordinates_from_values(self, values: Mapping[str, float]) -> np.ndarray:
        vector = np.empty(self.dimension, dtype=float)
        for index, (label, kind) in enumerate(zip(self.labels, self.coordinate_kinds, strict=True)):
            if label not in values:
                raise KeyError(f"Missing value for {label!r}.")
            value = float(values[label])
            vector[index] = np.log(value) if kind == COORDINATE_LOG else value
        if not np.all(np.isfinite(vector)):
            raise ValueError("Coordinates must be finite; log coordinates require positive values.")
        return vector

    def values_from_coordinates(self, vector: np.ndarray) -> dict[str, float]:
        x = np.asarray(vector, dtype=float)
        return {
            label: float(np.exp(x[index]) if kind == COORDINATE_LOG else x[index])
            for index, (label, kind) in enumerate(zip(self.labels, self.coordinate_kinds, strict=True))
        }

    def inside(self, vector: np.ndarray) -> bool:
        x = np.asarray(vector, dtype=float)
        return bool(x.shape == self.lower.shape and np.all(np.isfinite(x)) and np.all(x >= self.lower) and np.all(x <= self.upper))

    def parameters_from_coordinates(self, vector: np.ndarray) -> ParameterSet:
        values = self.values_from_coordinates(vector)
        return ParameterSet(
            [
                replace(parameter, value=values[parameter.symbol]) if parameter.symbol in values else parameter
                for parameter in self.base_parameters
            ]
        )

    def noise_scales_from_coordinates(self, vector: np.ndarray) -> dict[str, float]:
        values = self.values_from_coordinates(vector)
        return {
            observable: values[NOISE_SCALE_PREFIX + prior.name]
            for prior in self.noise_scale_priors
            for observable in prior.observables
        }

    def scaled_error(self, condition: ObservedCondition, scales: Mapping[str, float]) -> GaussianObservationError:
        if not scales:
            return condition.error
        deviations = {
            name: condition.error.standard_deviations[name] * float(scales.get(name, 1.0))
            for name in condition.error.observables
        }
        return replace(condition.error, standard_deviations=deviations)

    def _predictions(self, vector: np.ndarray) -> list[tuple[ObservedCondition, np.ndarray, GaussianObservationError]]:
        parameters = self.parameters_from_coordinates(vector)
        scales = self.noise_scales_from_coordinates(vector)
        results = []
        for condition in self.conditions:
            predicted = np.asarray(self.predict(parameters, condition.condition_id, condition.times), dtype=float)
            if predicted.shape != condition.observed.shape:
                raise ValueError(
                    f"Prediction for {condition.condition_id!r} has shape {predicted.shape}; "
                    f"expected {condition.observed.shape}."
                )
            results.append((condition, predicted, self.scaled_error(condition, scales)))
        return results

    def whitened_residuals(self, vector: np.ndarray) -> np.ndarray:
        """Concatenated whitened residuals; ``-0.5 * r @ r`` is the data term up to constants."""

        return np.concatenate([error.residuals(predicted, condition.observed) for condition, predicted, error in self._predictions(vector)])

    def log_likelihood(self, vector: np.ndarray) -> float:
        return float(-sum(error.negative_log_likelihood(predicted, condition.observed) for condition, predicted, error in self._predictions(vector)))

    def log_posterior(self, vector: np.ndarray) -> float:
        """Log posterior density in sampled coordinates; ``-inf`` outside the box or on prediction failure."""

        if not self.inside(vector):
            return -np.inf
        try:
            value = self.log_likelihood(vector)
        except _PREDICTION_FAILURES:
            return -np.inf
        return value if np.isfinite(value) else -np.inf

    def data_digest(self) -> str:
        payload = json.dumps([condition.to_dict() for condition in self.conditions], sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def prior_records(self) -> list[dict[str, Any]]:
        records = [prior.to_dict(units) for prior, units in zip(self.priors, self.units[: len(self.priors)], strict=True)]
        records.extend(prior.to_dict() for prior in self.noise_scale_priors)
        return records


def build_bayesian_problem(
    *,
    base_parameters: ParameterSet,
    priors: Sequence[PriorSpecification],
    conditions: Sequence[ObservedCondition],
    predict: ConditionPredictor,
    noise_scale_priors: Sequence[NoiseScalePrior] = (),
) -> BayesianProblem:
    """Validate priors, data and error models against each other and build the posterior."""

    if not priors:
        raise ValueError("At least one prior is required.")
    symbols = [prior.symbol for prior in priors]
    if len(set(symbols)) != len(symbols):
        raise ValueError("Prior symbols must be unique.")
    if not conditions:
        raise ValueError("At least one observed condition is required.")
    ids = [condition.condition_id for condition in conditions]
    if len(set(ids)) != len(ids):
        raise ValueError("Condition identifiers must be unique.")
    observed_names = {name for condition in conditions for name in condition.error.observables}
    scale_names = [observable for prior in noise_scale_priors for observable in prior.observables]
    if len(set(scale_names)) != len(scale_names):
        raise ValueError("Noise-scale observables must be unique across priors.")
    scale_labels = [prior.name for prior in noise_scale_priors]
    if len(set(scale_labels)) != len(scale_labels):
        raise ValueError("Noise-scale labels must be unique.")
    unknown = sorted(set(scale_names).difference(observed_names))
    if unknown:
        raise ValueError(f"Noise-scale priors name observables absent from every condition: {unknown}.")
    labels: list[str] = []
    units: list[str] = []
    kinds: list[str] = []
    lower: list[float] = []
    upper: list[float] = []
    for prior in priors:
        if prior.symbol not in base_parameters:
            raise KeyError(f"Prior symbol {prior.symbol!r} is not in the base parameter set.")
        parameter = base_parameters.get(prior.symbol)
        low, high = prior.bounds_in(parameter.units)
        labels.append(prior.symbol)
        units.append(parameter.units)
        if prior.kind == PRIOR_LOG_UNIFORM:
            kinds.append(COORDINATE_LOG)
            lower.append(float(np.log(low)))
            upper.append(float(np.log(high)))
        else:
            kinds.append(COORDINATE_LINEAR)
            lower.append(low)
            upper.append(high)
    for prior in noise_scale_priors:
        labels.append(NOISE_SCALE_PREFIX + prior.name)
        units.append("dimensionless")
        kinds.append(COORDINATE_LOG)
        lower.append(float(np.log(prior.lower)))
        upper.append(float(np.log(prior.upper)))
    lower_array = np.asarray(lower, dtype=float)
    upper_array = np.asarray(upper, dtype=float)
    lower_array.setflags(write=False)
    upper_array.setflags(write=False)
    return BayesianProblem(
        base_parameters=base_parameters,
        priors=tuple(priors),
        noise_scale_priors=tuple(noise_scale_priors),
        conditions=tuple(conditions),
        predict=predict,
        labels=tuple(labels),
        units=tuple(units),
        coordinate_kinds=tuple(kinds),
        lower=lower_array,
        upper=upper_array,
    )


@dataclass(frozen=True)
class EnsembleRun:
    """Raw output of the ensemble sampler in sampled coordinates."""

    chain: np.ndarray
    log_posterior: np.ndarray
    accepted: np.ndarray
    evaluations: int
    failed_evaluations: int

    def __post_init__(self) -> None:
        walkers, steps, _ = self.chain.shape
        if self.log_posterior.shape != (walkers, steps) or self.accepted.shape != (walkers,):
            raise ValueError("Ensemble run arrays are inconsistent.")

    @property
    def acceptance_fraction(self) -> np.ndarray:
        return self.accepted / max(self.chain.shape[1], 1)

    def extend(self, other: EnsembleRun) -> EnsembleRun:
        """Concatenate a resumed run that started from this run's final ensemble."""

        if other.chain.shape[0] != self.chain.shape[0] or other.chain.shape[2] != self.chain.shape[2]:
            raise ValueError("Resumed runs must keep the walker count and dimension.")
        return EnsembleRun(
            chain=np.concatenate([self.chain, other.chain], axis=1),
            log_posterior=np.concatenate([self.log_posterior, other.log_posterior], axis=1),
            accepted=self.accepted + other.accepted,
            evaluations=self.evaluations + other.evaluations,
            failed_evaluations=self.failed_evaluations + other.failed_evaluations,
        )


def initial_ensemble(
    problem: BayesianProblem,
    settings: SamplerSettings,
    *,
    center: Mapping[str, float] | None = None,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Starting walkers: a ball around ``center`` (natural units) or draws from the prior box."""

    generator = rng if rng is not None else np.random.default_rng(settings.seed)
    width = problem.upper - problem.lower
    if settings.initial_distribution == "prior":
        return generator.uniform(problem.lower, problem.upper, size=(settings.n_walkers, problem.dimension))
    if center is None:
        middle = 0.5 * (problem.lower + problem.upper)
    else:
        missing = [label for label in problem.labels if label not in center]
        if missing:
            raise KeyError(f"Initial center lacks values for {missing}.")
        middle = problem.coordinates_from_values(center)
        if not problem.inside(middle):
            raise ValueError("The initial center must lie inside the prior box.")
    draws = middle + settings.initial_spread * width * generator.standard_normal((settings.n_walkers, problem.dimension))
    margin = 1e-9 * width
    return np.clip(draws, problem.lower + margin, problem.upper - margin)


def run_ensemble_sampler(
    log_posterior: Callable[[np.ndarray], float],
    start: np.ndarray,
    n_steps: int,
    *,
    rng: np.random.Generator,
    stretch_scale: float = 2.0,
    map_function: Callable[..., Any] = map,
    progress: Callable[[int, EnsembleRun], None] | None = None,
    progress_every: int = 0,
    start_log_posterior: np.ndarray | None = None,
) -> EnsembleRun:
    """Advance an ensemble by ``n_steps`` stretch moves, updating each half against the other.

    ``map_function`` evaluates ``log_posterior`` on a sequence of proposals and may
    be a process pool's ``map``. ``progress`` receives the partial run every
    ``progress_every`` steps, for checkpointing.
    """

    ensemble = np.array(start, dtype=float, copy=True)
    if ensemble.ndim != 2 or ensemble.shape[0] < 4 or ensemble.shape[0] % 2 or not np.all(np.isfinite(ensemble)):
        raise ValueError("The starting ensemble must be a finite (walkers, dimension) array with an even walker count of at least 4.")
    walkers, dimension = ensemble.shape
    if walkers < 2 * dimension:
        raise ValueError(f"At least {2 * dimension} walkers are needed for {dimension} dimensions; got {walkers}.")
    if n_steps < 1:
        raise ValueError("n_steps must be positive.")
    if start_log_posterior is None:
        logp = np.asarray(list(map_function(log_posterior, ensemble)), dtype=float)
        evaluations = walkers
    else:
        logp = np.array(start_log_posterior, dtype=float, copy=True)
        evaluations = 0
        if logp.shape != (walkers,):
            raise ValueError("start_log_posterior must have one value per walker.")
    if not np.any(np.isfinite(logp)):
        raise ValueError("No starting walker has a finite log posterior; check the prior box and the model.")
    failed = int(np.sum(~np.isfinite(logp)))
    chain = np.empty((walkers, n_steps, dimension), dtype=float)
    chain_logp = np.empty((walkers, n_steps), dtype=float)
    accepted = np.zeros(walkers, dtype=int)
    half = walkers // 2
    halves = (np.arange(0, half), np.arange(half, walkers))
    for step in range(n_steps):
        for active, complement in ((halves[0], halves[1]), (halves[1], halves[0])):
            count = active.size
            z = ((stretch_scale - 1.0) * rng.random(count) + 1.0) ** 2 / stretch_scale
            partners = complement[rng.integers(0, complement.size, count)]
            proposals = ensemble[partners] + z[:, None] * (ensemble[active] - ensemble[partners])
            proposal_logp = np.asarray(list(map_function(log_posterior, proposals)), dtype=float)
            evaluations += count
            failed += int(np.sum(~np.isfinite(proposal_logp)))
            with np.errstate(invalid="ignore"):
                log_ratio = (dimension - 1) * np.log(z) + proposal_logp - logp[active]
            accept = np.log(rng.random(count)) < log_ratio
            accept &= np.isfinite(proposal_logp)
            chosen = active[accept]
            ensemble[chosen] = proposals[accept]
            logp[chosen] = proposal_logp[accept]
            accepted[chosen] += 1
        chain[:, step, :] = ensemble
        chain_logp[:, step] = logp
        if progress is not None and progress_every > 0 and (step + 1) % progress_every == 0 and step + 1 < n_steps:
            progress(
                step + 1,
                EnsembleRun(chain[:, : step + 1].copy(), chain_logp[:, : step + 1].copy(), accepted.copy(), evaluations, failed),
            )
    return EnsembleRun(chain=chain, log_posterior=chain_logp, accepted=accepted, evaluations=evaluations, failed_evaluations=failed)


def _next_power_of_two(n: int) -> int:
    size = 1
    while size < n:
        size <<= 1
    return size


def _autocorrelation_function(series: np.ndarray) -> np.ndarray:
    x = np.asarray(series, dtype=float)
    n = _next_power_of_two(x.size)
    transform = np.fft.fft(x - x.mean(), n=2 * n)
    acf = np.fft.ifft(transform * np.conjugate(transform))[: x.size].real
    if acf[0] <= 0.0:
        return np.full(x.size, np.nan)
    return acf / acf[0]


def integrated_autocorrelation_time(chain: np.ndarray, *, window_constant: float = 5.0) -> float:
    """Integrated autocorrelation time of one coordinate from a (walkers, steps) chain.

    The autocorrelation function is averaged across walkers and summed up to
    the automated window ``M`` with ``M >= c * tau(M)``; NaN for a constant chain.
    """

    values = np.asarray(chain, dtype=float)
    if values.ndim != 2 or values.shape[1] < 2:
        raise ValueError("Autocorrelation needs a (walkers, steps) chain with at least two steps.")
    functions = np.array([_autocorrelation_function(values[walker]) for walker in range(values.shape[0])])
    if np.all(np.isnan(functions)):
        return float("nan")
    mean_function = np.nanmean(functions, axis=0)
    taus = 2.0 * np.cumsum(mean_function) - 1.0
    beyond = np.arange(taus.size) < window_constant * taus
    window = int(np.argmin(beyond)) if np.any(beyond) else taus.size - 1
    return float(taus[window])


def chain_diagnostics(run: EnsembleRun, settings: SamplerSettings) -> dict[str, Any]:
    """Autocorrelation times, effective sample sizes and a declared convergence verdict."""

    chain = run.chain[:, settings.burn_in :, :]
    walkers, steps, dimension = chain.shape
    taus = []
    for index in range(dimension):
        try:
            taus.append(integrated_autocorrelation_time(chain[:, :, index]))
        except ValueError:
            taus.append(float("nan"))
    tau = np.asarray(taus, dtype=float)
    finite = np.isfinite(tau) & (tau > 0.0)
    reliable = finite & (settings.autocorrelation_tolerance * tau < steps)
    effective = np.where(finite, walkers * steps / np.where(finite, tau, 1.0), np.nan)
    acceptance = run.acceptance_fraction
    converged = bool(np.all(reliable) and np.all(effective[finite] >= settings.minimum_effective_samples))
    return {
        "post_burn_in_steps": int(steps),
        "walkers": int(walkers),
        "integrated_autocorrelation_time": [None if not np.isfinite(t) else float(t) for t in tau],
        "autocorrelation_estimate_reliable": [bool(flag) for flag in reliable],
        "effective_sample_size": [None if not np.isfinite(n) else float(n) for n in effective],
        "mean_acceptance_fraction": float(np.mean(acceptance)),
        "min_acceptance_fraction": float(np.min(acceptance)),
        "max_acceptance_fraction": float(np.max(acceptance)),
        "evaluations": int(run.evaluations),
        "failed_evaluations": int(run.failed_evaluations),
        "failed_evaluations_meaning": (
            "proposals with a non-finite log posterior: outside the prior box or a prediction failure"
        ),
        "converged": converged,
        "convergence_rule": (
            f"every autocorrelation estimate reliable (chain longer than {settings.autocorrelation_tolerance:g} tau) "
            f"and every effective sample size at least {settings.minimum_effective_samples:g}"
        ),
    }


def _quantile_bounds(mass: float) -> tuple[float, float, float]:
    tail = 0.5 * (1.0 - mass)
    return tail, 0.5, 1.0 - tail


def summarize_samples(problem: BayesianProblem, samples: np.ndarray, *, credible_mass: float) -> dict[str, dict[str, Any]]:
    """Per-coordinate posterior medians and credible intervals in natural units."""

    lower_q, middle_q, upper_q = _quantile_bounds(credible_mass)
    summaries: dict[str, dict[str, Any]] = {}
    for index, (label, kind, units) in enumerate(zip(problem.labels, problem.coordinate_kinds, problem.units, strict=True)):
        coordinate = samples[:, index]
        natural = np.exp(coordinate) if kind == COORDINATE_LOG else coordinate
        q_low, q_mid, q_high = np.quantile(natural, [lower_q, middle_q, upper_q])
        summaries[label] = {
            "units": units,
            "coordinate": kind,
            "median": float(q_mid),
            "lower": float(q_low),
            "upper": float(q_high),
            "mean": float(np.mean(natural)),
            "standard_deviation": float(np.std(natural, ddof=1)) if natural.size > 1 else None,
            "credible_mass": credible_mass,
        }
    return summaries


def classify_identifiability(
    problem: BayesianProblem,
    samples: np.ndarray,
    *,
    credible_mass: float,
    criteria: IdentifiabilityCriteria,
) -> dict[str, dict[str, Any]]:
    """Classify each parameter's posterior relative to its prior box with declared thresholds."""

    lower_q, _, upper_q = _quantile_bounds(credible_mass)
    verdicts: dict[str, dict[str, Any]] = {}
    for index, prior in enumerate(problem.priors):
        coordinate = samples[:, index]
        kind = problem.coordinate_kinds[index]
        low, high = float(problem.lower[index]), float(problem.upper[index])
        prior_width = high - low
        q_low, q_high = np.quantile(coordinate, [lower_q, upper_q])
        width = float(q_high - q_low)
        fraction = width / prior_width
        lower_contact = bool(q_low - low < criteria.bound_contact_fraction * prior_width)
        upper_contact = bool(high - q_high < criteria.bound_contact_fraction * prior_width)
        if lower_contact and upper_contact:
            verdict = PRIOR_DOMINATED
        elif lower_contact:
            verdict = BOUNDED_ABOVE_ONLY if fraction <= criteria.weak_max_width_fraction else PRIOR_DOMINATED
        elif upper_contact:
            verdict = BOUNDED_BELOW_ONLY if fraction <= criteria.weak_max_width_fraction else PRIOR_DOMINATED
        elif fraction <= criteria.identified_max_width_fraction:
            verdict = IDENTIFIED
        elif fraction <= criteria.weak_max_width_fraction:
            verdict = WEAKLY_IDENTIFIED
        else:
            verdict = PRIOR_DOMINATED
        to_natural = (lambda value: float(np.exp(value))) if kind == COORDINATE_LOG else float
        verdicts[prior.symbol] = {
            "class": verdict,
            "units": problem.units[index],
            "credible_interval": [to_natural(q_low), to_natural(q_high)],
            "credible_mass": credible_mass,
            "prior_bounds": [to_natural(low), to_natural(high)],
            "interval_width_fraction_of_prior": fraction,
            "interval_width_log10": width / np.log(10.0) if kind == COORDINATE_LOG else None,
            "prior_width_log10": prior_width / np.log(10.0) if kind == COORDINATE_LOG else None,
            "lower_bound_contact": lower_contact,
            "upper_bound_contact": upper_contact,
            "data_constrain": {
                IDENTIFIED: "both sides",
                WEAKLY_IDENTIFIED: "both sides, weakly",
                BOUNDED_ABOVE_ONLY: "an upper limit only; the lower end is the prior bound",
                BOUNDED_BELOW_ONLY: "a lower limit only; the upper end is the prior bound",
                PRIOR_DOMINATED: "nothing beyond the prior box",
            }[verdict],
        }
    return verdicts


def local_information_analysis(
    residuals: Callable[[np.ndarray], np.ndarray],
    center: np.ndarray,
    *,
    labels: Sequence[str],
    coordinate_kinds: Sequence[str],
    relative_step: float = 1e-3,
    relative_eigenvalue_cutoff: float = 1e-6,
) -> dict[str, Any]:
    """Fisher information ``J^T J`` of the whitened residuals by central differences.

    Eigenvalues below ``relative_eigenvalue_cutoff`` times the largest mark
    locally flat parameter combinations; the eigenvectors name them.
    """

    x0 = np.asarray(center, dtype=float)
    dimension = x0.size
    if len(labels) != dimension or len(coordinate_kinds) != dimension:
        raise ValueError("Labels and coordinate kinds must match the center dimension.")
    if not 0.0 < relative_step < 0.1 or not 0.0 < relative_eigenvalue_cutoff < 1.0:
        raise ValueError("Finite-difference step and eigenvalue cutoff must be small positive fractions.")
    reference = np.asarray(residuals(x0), dtype=float)
    if reference.ndim != 1 or not reference.size or not np.all(np.isfinite(reference)):
        raise ValueError("Residuals at the center must be a finite vector.")
    jacobian = np.empty((reference.size, dimension), dtype=float)
    for index in range(dimension):
        step = relative_step if coordinate_kinds[index] == COORDINATE_LOG else relative_step * max(abs(x0[index]), 1.0)
        forward = x0.copy()
        backward = x0.copy()
        forward[index] += step
        backward[index] -= step
        jacobian[:, index] = (np.asarray(residuals(forward), dtype=float) - np.asarray(residuals(backward), dtype=float)) / (2.0 * step)
    if not np.all(np.isfinite(jacobian)):
        raise ValueError("Finite-difference Jacobian is not finite.")
    information = jacobian.T @ jacobian
    eigenvalues, eigenvectors = np.linalg.eigh(information)
    order = np.argsort(eigenvalues)[::-1]
    eigenvalues = np.maximum(eigenvalues[order], 0.0)
    eigenvectors = eigenvectors[:, order]
    largest = float(eigenvalues[0]) if eigenvalues.size else 0.0
    sloppy = eigenvalues < relative_eigenvalue_cutoff * largest if largest > 0.0 else np.ones(dimension, dtype=bool)
    rank = int(np.sum(~sloppy))
    participation = np.sum(eigenvectors[:, sloppy] ** 2, axis=1) if np.any(sloppy) else np.zeros(dimension)
    smallest = eigenvectors[:, -1] if dimension else np.zeros(0)
    return {
        "method": METHOD_SOURCES["local_information"],
        "coordinates": list(coordinate_kinds),
        "labels": list(labels),
        "relative_step": relative_step,
        "relative_eigenvalue_cutoff": relative_eigenvalue_cutoff,
        "eigenvalues": eigenvalues.tolist(),
        "eigenvectors_by_column": eigenvectors.tolist(),
        "practical_rank": rank,
        "condition_number": float(eigenvalues[0] / eigenvalues[-1]) if eigenvalues.size and eigenvalues[-1] > 0.0 else None,
        "sloppy_direction_participation": {label: float(value) for label, value in zip(labels, participation, strict=True)},
        "least_constrained_combination": {label: float(value) for label, value in zip(labels, smallest, strict=True)},
        "residual_count": int(reference.size),
        "interpretation": "Local curvature at one point in sampled coordinates; a flat direction here is not a global identifiability proof and a steep one is not validation.",
    }


def pooled_replicate_standard_deviation(times: Sequence[float], values: Sequence[float], *, units: str, source: str) -> dict[str, Any]:
    """Pooled within-time replicate standard deviation of one observable.

    Groups observations by exact time; every group with at least two replicates
    contributes ``(n - 1) s^2``. Returns the measured-evidence record a
    :class:`GaussianObservationError` can be built from.
    """

    if not has_text(source):
        raise ProvenanceError("Pooled replicate deviations require a source naming the replicate structure.")
    t = _finite_array(times, name="times", ndim=1)
    y = _finite_array(values, name="values", ndim=1)
    if t.shape != y.shape:
        raise ValueError("times and values must align.")
    Q_(1.0, units)
    sum_of_squares = 0.0
    degrees_of_freedom = 0
    groups: list[dict[str, Any]] = []
    for time in np.unique(t):
        members = y[t == time]
        if members.size < 2:
            continue
        variance = float(np.var(members, ddof=1))
        sum_of_squares += (members.size - 1) * variance
        degrees_of_freedom += members.size - 1
        groups.append({"time": float(time), "replicates": int(members.size), "standard_deviation": float(np.sqrt(variance))})
    if degrees_of_freedom < 1:
        raise ValueError("Pooling requires at least one time with two or more replicates.")
    pooled = float(np.sqrt(sum_of_squares / degrees_of_freedom))
    if pooled <= 0.0:
        raise ValueError("Replicates are identical at every pooled time; a zero standard deviation is not an error model.")
    return {
        "standard_deviation": pooled,
        "units": units,
        "degrees_of_freedom": int(degrees_of_freedom),
        "groups": groups,
        "evidence": "measured_standard_deviation",
        "source": source,
        "assumption": "homoscedastic within-time replicate scatter pooled across times",
    }


@dataclass(frozen=True)
class BayesianCalibrationResult:
    """Posterior samples with their diagnostics, summaries, verdicts and provenance."""

    problem: BayesianProblem
    run: EnsembleRun
    settings: SamplerSettings
    criteria: IdentifiabilityCriteria
    source: str
    diagnostics: dict[str, Any]
    summaries: dict[str, dict[str, Any]]
    identifiability: dict[str, dict[str, Any]]
    local_information: dict[str, Any] | None
    best_sample: dict[str, Any]
    noise_evidence: tuple[str, ...]
    data_digest: str
    posterior_predictive: dict[str, Any] | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def converged(self) -> bool:
        return bool(self.diagnostics["converged"])

    def flat_samples(self) -> np.ndarray:
        """Post-burn-in samples in sampled coordinates, flattened over walkers and steps."""

        chain = self.run.chain[:, self.settings.burn_in :, :]
        return chain.reshape(-1, chain.shape[-1])

    def natural_samples(self, *, thin: int = 1) -> tuple[list[str], np.ndarray]:
        if thin < 1:
            raise ValueError("thin must be positive.")
        chain = self.run.chain[:, self.settings.burn_in :: thin, :]
        flat = chain.reshape(-1, chain.shape[-1])
        natural = flat.copy()
        for index, kind in enumerate(self.problem.coordinate_kinds):
            if kind == COORDINATE_LOG:
                natural[:, index] = np.exp(flat[:, index])
        return list(self.problem.labels), natural

    def identified_parameters(self) -> list[str]:
        return [symbol for symbol, verdict in self.identifiability.items() if verdict["class"] == IDENTIFIED]

    def parameters_left_as_ranges(self) -> dict[str, list[float]]:
        return {
            symbol: list(verdict["credible_interval"])
            for symbol, verdict in self.identifiability.items()
            if verdict["class"] != IDENTIFIED
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "method": METHOD_SOURCES,
            "claim_boundary": CLAIM_BOUNDARY,
            "source": self.source,
            "settings": self.settings.to_dict(),
            "identifiability_criteria": self.criteria.to_dict(),
            "parameters": list(self.problem.parameter_symbols),
            "parameter_units": {symbol: units for symbol, units in zip(self.problem.labels, self.problem.units, strict=True)},
            "priors": self.problem.prior_records(),
            "noise_scales": {prior.name: list(prior.observables) for prior in self.problem.noise_scale_priors},
            "noise_evidence": list(self.noise_evidence),
            "conditions": [condition.condition_id for condition in self.problem.conditions],
            "observation_count": int(sum(condition.observed.size for condition in self.problem.conditions)),
            "data_sha256": self.data_digest,
            "diagnostics": self.diagnostics,
            "converged": self.converged,
            "summaries": self.summaries,
            "identifiability": self.identifiability,
            "identified_parameters": self.identified_parameters(),
            "parameters_left_as_ranges": self.parameters_left_as_ranges(),
            "best_sample": self.best_sample,
            "local_information": self.local_information,
            "posterior_predictive": self.posterior_predictive,
            "notes": list(self.notes),
        }

    def save(self, output_dir: str | Path, *, thin: int = 1) -> dict[str, Path]:
        directory = Path(output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        summary_path = directory / "bayesian_calibration.json"
        summary_path.write_text(json.dumps(self.to_dict(), indent=2, allow_nan=False) + "\n", encoding="utf-8")
        labels, samples = self.natural_samples(thin=thin)
        samples_path = directory / "posterior_samples.csv"
        with samples_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(labels)
            for row in samples:
                writer.writerow([repr(float(value)) for value in row])
        return {"summary": summary_path, "samples": samples_path}


def analyze_run(
    problem: BayesianProblem,
    run: EnsembleRun,
    *,
    settings: SamplerSettings,
    source: str,
    criteria: IdentifiabilityCriteria = DEFAULT_IDENTIFIABILITY_CRITERIA,
    local_information: bool = True,
    notes: Sequence[str] = (),
) -> BayesianCalibrationResult:
    """Diagnostics, summaries, identifiability verdicts and local information for a run."""

    if not has_text(source):
        raise ProvenanceError("A Bayesian calibration result requires a source describing data, model and assumptions.")
    if run.chain.shape[0] != settings.n_walkers or run.chain.shape[2] != problem.dimension:
        raise ValueError("The run does not match the settings and problem.")
    if run.chain.shape[1] <= settings.burn_in:
        raise ValueError("The run is shorter than the burn-in.")
    diagnostics = chain_diagnostics(run, settings)
    samples = run.chain[:, settings.burn_in :, :].reshape(-1, problem.dimension)
    summaries = summarize_samples(problem, samples, credible_mass=settings.credible_mass)
    verdicts = classify_identifiability(problem, samples, credible_mass=settings.credible_mass, criteria=criteria)
    best_index = np.unravel_index(int(np.argmax(run.log_posterior)), run.log_posterior.shape)
    best_vector = run.chain[best_index[0], best_index[1], :]
    best = {
        "log_posterior": float(run.log_posterior[best_index]),
        "values": problem.values_from_coordinates(best_vector),
        "walker": int(best_index[0]),
        "step": int(best_index[1]),
        "meaning": "Highest-posterior sample in the chain, not an optimized mode.",
    }
    information: dict[str, Any] | None = None
    if local_information:
        count = len(problem.priors)
        fixed = best_vector.copy()

        def model_residuals(vector: np.ndarray) -> np.ndarray:
            full = fixed.copy()
            full[:count] = vector
            return problem.whitened_residuals(full)

        try:
            information = local_information_analysis(
                model_residuals,
                best_vector[:count],
                labels=problem.labels[:count],
                coordinate_kinds=problem.coordinate_kinds[:count],
            )
        except _PREDICTION_FAILURES as exc:
            information = {"failed": f"{type(exc).__name__}: {exc}"}
    evidence = sorted({condition.error.evidence for condition in problem.conditions})
    if problem.noise_scale_priors:
        evidence.append(NOISE_SCALE_EVIDENCE)
    all_notes = list(notes)
    if not diagnostics["converged"]:
        all_notes.append("Chain not converged by the declared rule; summaries and verdicts are provisional.")
    return BayesianCalibrationResult(
        problem=problem,
        run=run,
        settings=settings,
        criteria=criteria,
        source=source,
        diagnostics=diagnostics,
        summaries=summaries,
        identifiability=verdicts,
        local_information=information,
        best_sample=best,
        noise_evidence=tuple(evidence),
        data_digest=problem.data_digest(),
        notes=tuple(all_notes),
    )


def sample_posterior(
    *,
    base_parameters: ParameterSet,
    priors: Sequence[PriorSpecification],
    conditions: Sequence[ObservedCondition],
    predict: ConditionPredictor,
    settings: SamplerSettings,
    source: str,
    noise_scale_priors: Sequence[NoiseScalePrior] = (),
    criteria: IdentifiabilityCriteria = DEFAULT_IDENTIFIABILITY_CRITERIA,
    initial_center: Mapping[str, float] | None = None,
    map_function: Callable[..., Any] = map,
    local_information: bool = True,
    notes: Sequence[str] = (),
) -> BayesianCalibrationResult:
    """Build the problem, sample it and analyze the chain in one call."""

    problem = build_bayesian_problem(
        base_parameters=base_parameters,
        priors=priors,
        conditions=conditions,
        predict=predict,
        noise_scale_priors=noise_scale_priors,
    )
    rng = np.random.default_rng(settings.seed)
    start = initial_ensemble(problem, settings, center=initial_center, rng=rng)
    run = run_ensemble_sampler(
        problem.log_posterior,
        start,
        settings.n_steps,
        rng=rng,
        stretch_scale=settings.stretch_scale,
        map_function=map_function,
    )
    return analyze_run(
        problem,
        run,
        settings=settings,
        source=source,
        criteria=criteria,
        local_information=local_information,
        notes=notes,
    )


def posterior_predictive(
    result: BayesianCalibrationResult,
    *,
    times_by_condition: Mapping[str, np.ndarray],
    draws: int,
    quantiles: Sequence[float] = (0.05, 0.5, 0.95),
    seed: int = 0,
    include_measurement_noise: bool = False,
) -> dict[str, Any]:
    """Quantiles of the model prediction over posterior draws at requested times.

    With ``include_measurement_noise`` the (scaled) error model is added to each
    draw, giving bands for new observations rather than for the mean trajectory.
    """

    if draws < 2:
        raise ValueError("At least two posterior draws are required.")
    levels = np.asarray(quantiles, dtype=float)
    if levels.ndim != 1 or not levels.size or np.any(levels <= 0.0) or np.any(levels >= 1.0) or np.any(np.diff(levels) <= 0):
        raise ValueError("Quantiles must be increasing values in (0, 1).")
    problem = result.problem
    conditions = {condition.condition_id: condition for condition in problem.conditions}
    unknown = sorted(set(times_by_condition).difference(conditions))
    if unknown:
        raise KeyError(f"Unknown conditions for posterior prediction: {unknown}.")
    flat = result.flat_samples()
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, flat.shape[0], draws)
    output: dict[str, Any] = {
        "draws": int(draws),
        "quantiles": levels.tolist(),
        "includes_measurement_noise": include_measurement_noise,
        "seed": int(seed),
        "conditions": {},
        "failed_draws": 0,
    }
    for condition_id, requested in times_by_condition.items():
        times = _finite_array(requested, name=f"{condition_id} prediction times", ndim=1)
        condition = conditions[condition_id]
        if include_measurement_noise:
            try:
                condition.error.arrays(times.size)
            except ValueError as exc:
                raise ValueError(
                    f"{condition_id}: measurement-noise bands need standard deviations defined at the requested "
                    "times (scalar per observable, or exactly the observation rows)."
                ) from exc
        predictions: list[np.ndarray] = []
        for pick in picks:
            vector = flat[pick]
            try:
                parameters = problem.parameters_from_coordinates(vector)
                predicted = np.asarray(problem.predict(parameters, condition_id, times), dtype=float)
            except _PREDICTION_FAILURES:
                output["failed_draws"] += 1
                continue
            if predicted.shape != (times.size, len(condition.observables)) or not np.all(np.isfinite(predicted)):
                output["failed_draws"] += 1
                continue
            if include_measurement_noise:
                error = problem.scaled_error(condition, problem.noise_scales_from_coordinates(vector))
                sd, _ = error.arrays(times.size)
                chol = np.linalg.cholesky(error.correlation)
                predicted = predicted + (rng.standard_normal(predicted.shape) @ chol.T) * sd
            predictions.append(predicted)
        if len(predictions) < 2:
            raise ValueError(f"Too few successful posterior draws for {condition_id!r}.")
        stack = np.stack(predictions)
        bands = np.quantile(stack, levels, axis=0)
        output["conditions"][condition_id] = {
            "times": times.tolist(),
            "observables": list(condition.observables),
            "units": list(condition.error.units),
            "quantile_bands": {
                name: bands[:, :, index].tolist() for index, name in enumerate(condition.observables)
            },
            "successful_draws": int(stack.shape[0]),
            "band_layout": "quantile_bands[observable][quantile_index][time_index]",
        }
    return output


def prior_from_bounds(
    *,
    symbol: str,
    lower: float,
    upper: float,
    units: str,
    source: str,
    kind: str = PRIOR_LOG_UNIFORM,
) -> PriorSpecification:
    """Convenience constructor from plain numbers with explicit units."""

    return PriorSpecification(symbol=symbol, lower=Q_(lower, units), upper=Q_(upper, units), source=source, kind=kind)


def parameter_for_testing(symbol: str, value: float, units: str = "dimensionless") -> Parameter:
    """A provenance-labelled artificial parameter for tests and examples; never scientific."""

    return Parameter(
        name=symbol,
        symbol=symbol,
        value=value,
        units=units,
        uncertainty=None,
        source="Artificial parameter for a software test; no scientific meaning.",
        confidence_level="testing",
        notes="Artificial value.",
    )


def posterior_predictive_coverage(
    result: BayesianCalibrationResult,
    *,
    draws: int,
    credible_mass: float = 0.95,
    seed: int = 0,
) -> dict[str, Any]:
    """Fraction of the fitted observations inside the central posterior predictive interval.

    Each draw adds the (scaled) measurement error of that draw to the model
    prediction at the observed times, so the interval is for new observations,
    not for the mean trajectory. Coverage far below ``credible_mass`` means the
    model plus its error model cannot account for the data; coverage far above
    it means the error model is wider than the residuals. It is a diagnostic,
    not a test statistic.
    """

    if draws < 2:
        raise ValueError("At least two posterior draws are required.")
    if not 0.0 < credible_mass < 1.0:
        raise ValueError("credible_mass must lie strictly between 0 and 1.")
    lower_level, upper_level = (1.0 - credible_mass) / 2.0, 1.0 - (1.0 - credible_mass) / 2.0
    problem = result.problem
    flat = result.flat_samples()
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, flat.shape[0], draws)
    output: dict[str, Any] = {
        "draws": int(draws),
        "credible_mass": float(credible_mass),
        "seed": int(seed),
        "includes_measurement_noise": True,
        "conditions": {},
        "failed_draws": 0,
        "overall": {},
    }
    inside_total: dict[str, int] = {}
    count_total: dict[str, int] = {}
    for condition in problem.conditions:
        times = condition.times
        predictions: list[np.ndarray] = []
        for pick in picks:
            vector = flat[pick]
            try:
                parameters = problem.parameters_from_coordinates(vector)
                predicted = np.asarray(problem.predict(parameters, condition.condition_id, times), dtype=float)
            except _PREDICTION_FAILURES:
                output["failed_draws"] += 1
                continue
            if predicted.shape != condition.observed.shape or not np.all(np.isfinite(predicted)):
                output["failed_draws"] += 1
                continue
            error = problem.scaled_error(condition, problem.noise_scales_from_coordinates(vector))
            sd, _ = error.arrays(times.size)
            chol = np.linalg.cholesky(error.correlation)
            predictions.append(predicted + (rng.standard_normal(predicted.shape) @ chol.T) * sd)
        if len(predictions) < 2:
            raise ValueError(f"Too few successful posterior draws for {condition.condition_id!r}.")
        stack = np.stack(predictions)
        lower = np.quantile(stack, lower_level, axis=0)
        upper = np.quantile(stack, upper_level, axis=0)
        inside = (condition.observed >= lower) & (condition.observed <= upper)
        per_observable = {}
        for index, name in enumerate(condition.observables):
            hits, total = int(inside[:, index].sum()), int(inside.shape[0])
            per_observable[name] = {"inside": hits, "observations": total, "fraction": hits / total}
            inside_total[name] = inside_total.get(name, 0) + hits
            count_total[name] = count_total.get(name, 0) + total
        output["conditions"][condition.condition_id] = {
            "successful_draws": int(stack.shape[0]),
            "per_observable": per_observable,
            "fraction": float(inside.mean()),
        }
    overall = {
        name: {"inside": inside_total[name], "observations": count_total[name], "fraction": inside_total[name] / count_total[name]}
        for name in inside_total
    }
    all_inside, all_count = sum(inside_total.values()), sum(count_total.values())
    overall["all_observables"] = {"inside": all_inside, "observations": all_count, "fraction": all_inside / all_count}
    output["overall"] = overall
    return output


__all__ = [
    "BOUNDED_ABOVE_ONLY",
    "BOUNDED_BELOW_ONLY",
    "CLAIM_BOUNDARY",
    "DEFAULT_IDENTIFIABILITY_CRITERIA",
    "IDENTIFIABILITY_CLASSES",
    "IDENTIFIED",
    "METHOD_SOURCES",
    "NOISE_SCALE_EVIDENCE",
    "NOISE_SCALE_PREFIX",
    "PRIOR_DOMINATED",
    "PRIOR_KINDS",
    "SCHEMA_VERSION",
    "WEAKLY_IDENTIFIED",
    "BayesianCalibrationResult",
    "BayesianProblem",
    "ConditionPredictor",
    "EnsembleRun",
    "IdentifiabilityCriteria",
    "NoiseScalePrior",
    "ObservedCondition",
    "PriorSpecification",
    "SamplerSettings",
    "analyze_run",
    "build_bayesian_problem",
    "chain_diagnostics",
    "classify_identifiability",
    "initial_ensemble",
    "integrated_autocorrelation_time",
    "local_information_analysis",
    "parameter_for_testing",
    "pooled_replicate_standard_deviation",
    "posterior_predictive",
    "posterior_predictive_coverage",
    "prior_from_bounds",
    "run_ensemble_sampler",
    "sample_posterior",
    "summarize_samples",
]
