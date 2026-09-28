"""Generic covariance/censoring tests use two non-biological sensors."""
from dataclasses import replace

import numpy as np
import pytest
from scipy.stats import multivariate_normal, norm

from fungal_model.calibration import GaussianObservationError
from fungal_model.core.units import Q_


def error(**kwargs):
    return GaussianObservationError(("pressure", "temperature"), ("pascal", "kelvin"),
        {"pressure":Q_(0.002,"kilopascal"), "temperature":Q_(3,"kelvin")},
        np.array([[1,.4],[.4,1]]), "Artificial sensor error calibration; software test only", "measured_standard_deviation", **kwargs)


def test_full_covariance_matches_multivariate_density_and_converts_units():
    model = error()
    prediction, data = np.array([[10,300],[9,302]]), np.array([[12,297],[8,300]])
    covariance = np.array([[4,2.4],[2.4,9]])
    expected = sum(-multivariate_normal.logpdf(d,mean=p,cov=covariance) for p,d in zip(prediction,data,strict=True))
    assert model.negative_log_likelihood(prediction,data) == pytest.approx(expected)
    sd,limits = model.arrays(2)
    np.testing.assert_allclose(sd, [[2,3],[2,3]])
    assert np.isnan(limits).all()
    assert not model.correlation.flags.writeable
    assert model.to_dict(2)["evidence"] == "measured_standard_deviation"
    assert GaussianObservationError.from_dict(model.to_dict(2)).to_dict(2)==model.to_dict(2)


def test_left_censoring_matches_conditional_gaussian_not_zero_imputation():
    model = error(left_limits={"pressure":Q_([11,np.nan],"pascal")}, detection_limit_source="Artificial instrument reporting rule")
    prediction,data = np.array([[10,300],[9,302]]),np.array([[0,303],[8,300]])
    conditional_mean = 10 + 2.4/9*(303-300)
    conditional_sd = np.sqrt(4-2.4**2/9)
    expected = -norm.logpdf(303,loc=300,scale=3)-norm.logcdf(11,loc=conditional_mean,scale=conditional_sd)
    expected -= multivariate_normal.logpdf(data[1],mean=prediction[1],cov=[[4,2.4],[2.4,9]])
    assert model.negative_log_likelihood(prediction,data) == pytest.approx(expected)
    restored = GaussianObservationError.from_dict(model.to_dict(2))
    assert restored.to_dict(2)==model.to_dict(2)
    assert restored.negative_log_likelihood(prediction,data)==pytest.approx(expected)
    data[0,0] = 10.5
    assert model.negative_log_likelihood(prediction,data) == pytest.approx(expected)
    data[0,0] = 12
    with pytest.raises(ValueError,match="exceed"):
        model.residuals(prediction,data)


def test_zeros_without_declared_limits_are_measurements():
    prediction,data = np.ones((2,2)),np.zeros((2,2))
    assert len(error().residuals(prediction,data)) == 4
    assert not np.allclose(error().residuals(prediction,data),0)


@pytest.mark.parametrize("change", [
    {"correlation":np.array([[1,2],[2,1]])}, {"correlation":np.eye(3)},
    {"correlation":np.array([[1,.4],[.3,1]])}, {"source":""}, {"evidence":"unknown"},
    {"standard_deviations":{"pressure":Q_(0,"Pa"),"temperature":Q_(1,"K")}},
    {"left_limits":{"pressure":Q_(1,"Pa")}},
    {"left_limits":{"pressure":Q_(np.inf,"Pa")},"detection_limit_source":"fixture"},
])
def test_noise_rejects_invented_or_invalid_error_contract(change):
    with pytest.raises((ValueError,TypeError)):
        replace(error(),**change)


def test_unsupported_multiple_censoring_and_misaligned_arrays_are_explicit():
    model = error(left_limits={"pressure":Q_(1,"Pa"),"temperature":Q_(1,"K")},detection_limit_source="fixture")
    with pytest.raises(ValueError,match="At most one"):
        model.residuals(np.ones((1,2)),np.zeros((1,2)))
    with pytest.raises(ValueError,match="time dimension"):
        replace(error(),standard_deviations={"pressure":Q_([1,2,3],"Pa"),"temperature":Q_(1,"K")}).arrays(2)
    with pytest.raises(ValueError,match="aligned finite"):
        error().residuals(np.full((1,2),np.nan),np.zeros((1,2)))


@pytest.mark.parametrize("defect",["units","infinite_limit","temporal"])
def test_noise_deserialization_does_not_drop_invalid_assumptions(defect):
    record=error().to_dict(2)
    if defect=="units":
        record["units"]=[]
    elif defect=="infinite_limit":
        record["left_limits"][0][0]=float("inf")
    else:
        record["temporal_independence_assumed"]=False
    with pytest.raises(ValueError):
        GaussianObservationError.from_dict(record)
