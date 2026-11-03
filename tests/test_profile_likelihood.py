"""Analytical, artificial tests; no experimental or biological evidence."""
import json
from dataclasses import replace

import numpy as np
import pytest

from fungal_model.calibration import (
    DEFAULT_RELATIVE_DIFFERENCE_STEP, FittableParameter, fit_least_squares, profile_likelihood,
)
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_


def p(symbol, value, units='dimensionless'):
    return Parameter(name=symbol, symbol=symbol, value=value, units=units, uncertainty=None,
                     source='Artificial analytical profile benchmark', confidence_level='testing', notes='No biology')


def fixture(flat=False):
    x = np.arange(5.)
    def predict(parameters):
        a = parameters.require_quantity('a').magnitude
        b = parameters.require_quantity('b').magnitude
        return {'y': Q_(a + b + 0*x if flat else a*x+b, 'dimensionless')}
    observations = {'y': Q_(np.full(5, 3.) if flat else 2*x+1, 'dimensionless')}
    scales = {'y': Q_(np.full(5, 0.5), 'dimensionless')}
    fit = fit_least_squares(base_parameters=ParameterSet([p('a', 1), p('b', 1)]),
        fittable_parameters=[FittableParameter(s, p('lo', -10), p('hi', 10)) for s in ('a', 'b')],
        predict=predict, observations=observations, residual_scales=scales,
        validation_indices=(), calibration_source='Artificial analytic fixture')
    return fit, predict, observations, scales


def test_profile_reoptimizes_nuisance_and_matches_analytic_curve(tmp_path):
    fit, predict, observations, scales = fixture()
    result = profile_likelihood(result=fit, predict=predict, observations=observations,
        residual_scales=scales, grids={'a': Q_([1, 2, 3], 'dimensionless')},
        source='Artificial known independent Gaussian scales')
    assert result.complete
    np.testing.assert_allclose([p['delta_chi_squared'] for p in result.profiles['a']], [40, 0, 40], atol=1e-7)
    np.testing.assert_allclose([p['nuisance_parameters']['b'] for p in result.profiles['a']], [3, 1, -1], atol=1e-6)
    assert json.loads(result.save(tmp_path).read_text())['complete']


def test_flat_profile_exposes_nonidentifiable_parameter_combination():
    fit, predict, observations, scales = fixture(flat=True)
    result = profile_likelihood(result=fit, predict=predict, observations=observations,
        residual_scales=scales, grids={'a': Q_([0, 1, 2, 3], 'dimensionless')}, source='Artificial example')
    assert result.complete
    np.testing.assert_allclose([p['chi_squared'] for p in result.profiles['a']], 0, atol=1e-8)


def test_profile_keeps_failed_points_explicit(monkeypatch):
    from fungal_model.calibration import profile
    fit, predict, observations, scales = fixture()
    monkeypatch.setattr(profile, 'fit_least_squares', lambda **kwargs: replace(fit, success=False, message='limit'))
    result = profile_likelihood(result=fit, predict=predict, observations=observations,
        residual_scales=scales, grids={'a': Q_([1, 2], 'dimensionless')}, source='Artificial example')
    assert not result.complete
    assert all(p['chi_squared'] is None and not p['success'] for p in result.profiles['a'])


@pytest.mark.parametrize('case', ['missing_scales', 'wrong_training_data', 'out_of_bounds', 'failed_fit'])
def test_profile_rejects_invalid_context(case):
    fit, predict, observations, scales = fixture()
    grids = {'a': Q_([1, 2], 'dimensionless')}
    if case == 'missing_scales':
        scales = {}
    elif case == 'wrong_training_data':
        observations = {'y': observations['y'] + Q_(1, 'dimensionless')}
    elif case == 'out_of_bounds':
        grids = {'a': Q_([1, 20], 'dimensionless')}
    else:
        fit = replace(fit, success=False)
    with pytest.raises(ValueError):
        profile_likelihood(result=fit, predict=predict, observations=observations,
            residual_scales=scales, grids=grids, source='Artificial example')


def test_profile_reuses_reference_fit_difference_step_unless_overridden(tmp_path):
    fit, predict, observations, scales = fixture()
    common = dict(predict=predict, observations=observations, residual_scales=scales,
                  grids={'a': Q_([1, 2], 'dimensionless')}, source='Artificial example')

    inherited = profile_likelihood(result=fit, **common)
    assert inherited.complete
    assert inherited.nuisance_optimizer['finite_difference_step'] == fit.optimizer_metadata['finite_difference_step'] == 1e-3
    assert inherited.nuisance_optimizer['finite_difference_step_origin'] == 'reference fit optimizer_metadata'
    assert inherited.nuisance_optimizer['max_nfev'] is None
    assert inherited.nuisance_optimizer['max_nfev_origin'].startswith('scipy default')

    overridden = profile_likelihood(result=fit, **common, diff_step=5e-4, max_nfev=30)
    assert overridden.nuisance_optimizer == {
        'method': 'trf', 'max_nfev': 30, 'max_nfev_origin': 'caller',
        'finite_difference_step': 5e-4, 'finite_difference_step_origin': 'caller',
    }
    saved = json.loads(overridden.save(tmp_path).read_text())
    assert saved['schema_version'] == '1.1.0'
    assert saved['nuisance_optimizer']['finite_difference_step'] == 5e-4

    bare = replace(fit, optimizer_metadata={})
    fallback = profile_likelihood(result=bare, **common)
    assert fallback.nuisance_optimizer['finite_difference_step'] == DEFAULT_RELATIVE_DIFFERENCE_STEP.value
    assert fallback.nuisance_optimizer['finite_difference_step_origin'] == DEFAULT_RELATIVE_DIFFERENCE_STEP.symbol

    with pytest.raises(ValueError, match='diff_step'):
        profile_likelihood(result=fit, **common, diff_step=1.0)
