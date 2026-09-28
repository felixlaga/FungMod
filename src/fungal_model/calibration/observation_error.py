"""Explicit Gaussian observation errors, covariance and single left censoring.

Covariance is between simultaneous observables, not between times. Assumed
scales remain assumptions; this module never estimates SD from arbitrary loss
weights or treats absent detection limits as zero. Conditional Gaussian
factorization handles one censored component per row exactly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np
from scipy.linalg import solve_triangular
from scipy.special import log_ndtr

from fungal_model.core.provenance import has_text
from fungal_model.core.units import Q_, Quantity, assert_compatible


@dataclass(frozen=True)
class GaussianObservationError:
    observables: tuple[str, ...]
    units: tuple[str, ...]
    standard_deviations: Mapping[str, Quantity]
    correlation: np.ndarray
    source: str
    evidence: str  # measured_standard_deviation, measured_standard_error, assumed
    left_limits: Mapping[str, Quantity] | None = None  # NaN entries mean uncensored.
    detection_limit_source: str | None = None

    def __post_init__(self) -> None:
        size = len(self.observables)
        if (not size or len(set(self.observables)) != size or len(self.units) != size
                or set(self.standard_deviations) != set(self.observables) or not has_text(self.source)):
            raise ValueError("Noise requires unique observables, explicit units, SDs and provenance.")
        if self.evidence not in {"measured_standard_deviation", "measured_standard_error", "assumed"}:
            raise ValueError("Noise evidence must distinguish measured errors from assumptions.")
        correlation = np.array(self.correlation, dtype=float, copy=True)
        if (correlation.shape != (size, size) or not np.all(np.isfinite(correlation))
                or not np.allclose(correlation, correlation.T, atol=1e-12, rtol=0)
                or not np.allclose(np.diag(correlation), 1, atol=1e-12, rtol=0)):
            raise ValueError("Correlation must be finite, symmetric and have a unit diagonal.")
        try:
            np.linalg.cholesky(correlation)
        except np.linalg.LinAlgError as exc:
            raise ValueError("Correlation must be positive definite.") from exc
        correlation.setflags(write=False)
        object.__setattr__(self, "correlation", correlation)
        for key, unit in zip(self.observables, self.units, strict=True):
            sd = np.asarray(assert_compatible(self.standard_deviations[key], unit).magnitude, dtype=float)
            if sd.ndim > 1 or not sd.size or not np.all(np.isfinite(sd)) or np.any(sd <= 0):
                raise ValueError("Every supplied observation SD/SE must be finite and strictly positive.")
        if self.left_limits is not None:
            if not set(self.left_limits) <= set(self.observables) or not has_text(self.detection_limit_source):
                raise ValueError("Censoring requires known observables and detection-limit provenance.")
            for key, value in self.left_limits.items():
                bound = np.asarray(assert_compatible(value, self.units[self.observables.index(key)]).magnitude)
                if bound.ndim > 1 or np.any(np.isinf(bound)):
                    raise ValueError("Detection limits must be finite or explicitly NaN for uncensored entries.")

    def arrays(self, n: int) -> tuple[np.ndarray, np.ndarray]:
        if n < 1:
            raise ValueError("At least one observation is required.")
        scales, limits = [], []
        for name, unit in zip(self.observables, self.units, strict=True):
            sd = np.asarray(assert_compatible(self.standard_deviations[name], unit).magnitude, dtype=float)
            try:
                scales.append(np.broadcast_to(sd, (n,)))
                bound = ((self.left_limits or {}).get(name))
                values = np.nan if bound is None else assert_compatible(bound, unit).magnitude
                limits.append(np.broadcast_to(values, (n,)))
            except ValueError as exc:
                raise ValueError("Noise arrays must match the observation time dimension.") from exc
        return np.column_stack(scales), np.column_stack(limits)

    def _evaluate(self, predicted: np.ndarray, observed: np.ndarray) -> tuple[np.ndarray, float]:
        prediction, data = np.asarray(predicted, dtype=float), np.asarray(observed, dtype=float)
        if (prediction.shape != data.shape or data.ndim != 2 or data.shape[1] != len(self.observables)
                or not np.all(np.isfinite(prediction)) or not np.all(np.isfinite(data))):
            raise ValueError("Predictions and observations must be aligned finite time-by-observable arrays.")
        sd, limits = self.arrays(data.shape[0])
        if not np.any(np.isfinite(limits)):
            chol = np.linalg.cholesky(self.correlation)
            vector = solve_triangular(chol, ((data-prediction)/sd).T, lower=True).T.ravel()
            if not np.all(np.isfinite(vector)):
                raise ValueError("Nonfinite Gaussian objective.")
            constant = float(np.log(sd).sum() + data.shape[0]*np.log(np.diag(chol)).sum()
                             + data.size*np.log(2*np.pi)/2)
            return vector, constant
        residuals, constant = [], 0.0
        for i in range(data.shape[0]):
            censored = np.flatnonzero(np.isfinite(limits[i]))
            if len(censored) > 1:
                raise ValueError("At most one correlated censored observable per time row is supported.")
            exact = np.flatnonzero(~np.isfinite(limits[i]))
            covariance = self.correlation * np.outer(sd[i], sd[i])
            if exact.size:
                sub = covariance[np.ix_(exact, exact)]
                chol = np.linalg.cholesky(sub)
                difference = data[i, exact] - prediction[i, exact]
                whitened = solve_triangular(chol, difference, lower=True)
                residuals.extend(whitened.tolist())
                constant += float(np.log(np.diag(chol)).sum() + exact.size * np.log(2*np.pi)/2)
            if censored.size:
                j = int(censored[0])
                if data[i, j] > limits[i, j]:
                    raise ValueError("A reported left-censored value cannot exceed its detection limit.")
                mean, variance = prediction[i, j], covariance[j, j]
                if exact.size:
                    cross = covariance[j, exact]
                    mean += cross @ np.linalg.solve(covariance[np.ix_(exact, exact)],
                                                   data[i, exact] - prediction[i, exact])
                    variance -= cross @ np.linalg.solve(covariance[np.ix_(exact, exact)], cross)
                log_probability = float(log_ndtr((limits[i, j] - mean) / np.sqrt(variance)))
                residuals.append(float(np.sqrt(-2 * log_probability)))
        vector = np.asarray(residuals)
        if not np.all(np.isfinite(vector)):
            raise ValueError("Nonfinite Gaussian/censoring objective.")
        return vector, constant

    def residuals(self, predicted: np.ndarray, observed: np.ndarray) -> np.ndarray:
        """Whitened residuals plus sqrt(-2 log conditional CDF) for censoring."""
        return self._evaluate(predicted, observed)[0]

    def negative_log_likelihood(self, predicted: np.ndarray, observed: np.ndarray) -> float:
        residual, constant = self._evaluate(predicted, observed)
        return float(residual @ residual / 2 + constant)

    def to_dict(self, n: int) -> dict:
        sd, bounds = self.arrays(n)
        return {"observables": list(self.observables), "units": list(self.units),
                "standard_deviations": sd.tolist(), "correlation": self.correlation.tolist(),
                "left_limits": [[float(v) if np.isfinite(v) else None for v in row] for row in bounds],
                "source": self.source, "evidence": self.evidence,
                "detection_limit_source": self.detection_limit_source,
                "temporal_independence_assumed": True,
                "supports": "zero or one left-censored component per simultaneous row"}

    @classmethod
    def from_dict(cls, record: Mapping[str, Any]) -> GaussianObservationError:
        """Restore the exact error and censoring law for nuisance refits."""
        names, units = tuple(record["observables"]), tuple(record["units"])
        sd = np.asarray(record["standard_deviations"],dtype=float)
        limits = np.asarray([[np.nan if v is None else v for v in row] for row in record["left_limits"]],dtype=float)
        if (len(units) != len(names) or sd.ndim != 2 or sd.shape[1] != len(names)
                or limits.shape != sd.shape or np.any(np.isinf(limits))):
            raise ValueError("Serialized noise arrays must be aligned time-by-observable matrices.")
        if record.get("temporal_independence_assumed") is not True:
            raise ValueError("Correlated errors across times are not implemented.")
        return cls(names,units,{k:Q_(sd[:,j],units[j]) for j,k in enumerate(names)},
            np.asarray(record["correlation"]),record["source"],record["evidence"],
            {k:Q_(limits[:,j],units[j]) for j,k in enumerate(names) if np.any(np.isfinite(limits[:,j]))} or None,
            record.get("detection_limit_source"))
