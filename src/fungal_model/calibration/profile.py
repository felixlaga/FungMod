"""Grid profile likelihood with explicit independent Gaussian observation scales.

At each fixed parameter value the remaining parameters are reoptimized. This
implements the diagnostic construction described by Raue et al. (2009),
https://doi.org/10.1093/bioinformatics/btp358. A finite grid and local optimizer
cannot prove global identifiability or automatically define confidence limits.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from fungal_model.calibration.fitting import (
    LeastSquaresCalibrationResult, PredictionFunction, _build_replacements,
    _replace_parameters, fit_least_squares,
)
from fungal_model.calibration.residuals import residuals_between
from fungal_model.core.provenance import ProvenanceError, has_text
from fungal_model.core.units import Quantity, assert_compatible


@dataclass(frozen=True)
class ProfileLikelihoodResult:
    profiles: Mapping[str, list[dict[str, Any]]]
    parameter_units: Mapping[str, str]
    reference_chi_squared: float
    source: str
    complete: bool
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            'schema_version': '1.0.0', 'profiles': dict(self.profiles),
            'parameter_units': dict(self.parameter_units),
            'reference_chi_squared': self.reference_chi_squared, 'source': self.source,
            'complete': self.complete, 'warnings': list(self.warnings),
            'method': 'fixed-parameter grid with bounded local nuisance reoptimization',
            'noise_model': 'independent Gaussian errors with fixed supplied observation standard deviations',
            'claim_boundary': 'Conditional on the supplied noise model and grid; no global identifiability or automatic confidence-limit claim.',
            'method_source': 'https://doi.org/10.1093/bioinformatics/btp358',
        }

    def save(self, output_dir: str | Path) -> Path:
        directory = Path(output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / 'profile_likelihood.json'
        path.write_text(json.dumps(self.to_dict(), indent=2, allow_nan=False) + '\n', encoding='utf-8')
        return path


def profile_likelihood(
    *, result: LeastSquaresCalibrationResult, predict: PredictionFunction,
    observations: Mapping[str, Quantity], residual_scales: Mapping[str, Quantity],
    grids: Mapping[str, Quantity], source: str, train_indices: Sequence[int] | None = None,
    max_nfev: int | None = None,
) -> ProfileLikelihoodResult:
    """Profile the original fit's training objective on explicit unit-bearing grids.

    ``source`` must describe the analysis plan and justification for treating the
    scales as independent Gaussian standard deviations. Failed points remain
    explicit with null costs; they are never replaced by successful neighbours.
    Validation observations must not be passed as training observations.
    """
    if not has_text(source):
        raise ProvenanceError('Profile likelihood requires a source for its analysis and noise assumptions.')
    if not result.success or result.training_residuals is None:
        raise ValueError('Profile likelihood requires a successful reference fit.')
    if not grids or set(observations) != set(residual_scales):
        raise ValueError('Profiles require a nonempty grid and explicit scales for every observable.')
    baseline = residuals_between(predict(result.fitted_parameters), observations,
                                 indices=train_indices, residual_scales=residual_scales).flattened_scaled()
    original = result.training_residuals.flattened_scaled()
    if baseline.shape != original.shape or not np.allclose(baseline, original, rtol=1e-7, atol=1e-9):
        raise ValueError('Profile inputs must reproduce the reference fit training objective.')
    if not baseline.size or not np.all(np.isfinite(baseline)):
        raise ValueError('Profile residuals must be nonempty and finite.')
    reference = float(baseline @ baseline)
    specs = {spec.symbol: spec for spec in result.fittable_parameters}
    profiles: dict[str, list[dict[str, Any]]] = {}
    units: dict[str, str] = {}
    warnings = ['Finite grids and local nuisance optima do not establish global identifiability.']
    complete = True
    for symbol, grid in grids.items():
        if symbol not in specs:
            raise ValueError(f'{symbol!r} was not fitted.')
        unit = result.fitted_parameters.get(symbol).units
        values = np.asarray(assert_compatible(grid, unit, name=symbol).magnitude, dtype=float)
        lower, upper = specs[symbol].bounds_numeric(result.fitted_parameters)
        if (values.ndim != 1 or not values.size or not np.all(np.isfinite(values))
                or np.any(np.diff(values) <= 0) or np.any(values < lower) or np.any(values > upper)):
            raise ValueError(f'{symbol} profile grid must be finite, increasing and within optimizer bounds.')
        units[symbol] = unit
        points: list[dict[str, Any]] = []
        nuisance = tuple(spec for name, spec in specs.items() if name != symbol)
        for value in values:
            point: dict[str, Any] = {'value': float(value), 'success': False, 'chi_squared': None,
                                     'delta_chi_squared': None, 'nuisance_parameters': None}
            try:
                fixed = _replace_parameters(result.fitted_parameters, _build_replacements(
                    result.fitted_parameters, [specs[symbol]], [float(value)], calibration_source=source,
                ))
                if nuisance:
                    fit = fit_least_squares(base_parameters=fixed, fittable_parameters=nuisance,
                        predict=predict, observations=observations, train_indices=train_indices,
                        validation_indices=(), residual_scales=residual_scales,
                        calibration_source=source, max_nfev=max_nfev)
                    if not fit.success or fit.training_residuals is None:
                        raise ValueError(fit.message)
                    vector = fit.training_residuals.flattened_scaled()
                    parameters = fit.fitted_parameters
                else:
                    vector = residuals_between(predict(fixed), observations, indices=train_indices,
                        residual_scales=residual_scales).flattened_scaled()
                    parameters = fixed
                cost = float(vector @ vector)
                if not np.isfinite(cost):
                    raise ValueError('Nonfinite profile cost.')
                point.update(success=True, chi_squared=cost, delta_chi_squared=cost-reference,
                    nuisance_parameters={spec.symbol: float(parameters.require_quantity(spec.symbol).magnitude)
                                         for spec in nuisance}, message='converged' if nuisance else 'evaluated')
                if cost < reference - 1e-7 * max(1.0, reference):
                    warnings.append(f'{symbol}={value}: profile improves the reference fit; refit before interpreting likelihood differences.')
            except Exception as exc:
                point['message'] = f'{type(exc).__name__}: {exc}'
                complete = False
            points.append(point)
        profiles[symbol] = points
    if not complete:
        warnings.append('Some profile points failed; the profile is incomplete.')
    return ProfileLikelihoodResult(profiles, units, reference, source, complete, tuple(warnings))
