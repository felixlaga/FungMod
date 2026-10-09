"""Compare virtual experiments with a user dataset's time courses, and fit its kinetic constants to them.

``compare_with_timecourses`` brings the simulated median trajectory and its
5-95 percent band of each case to the times a user observed substrate remaining
or product formed (linear interpolation on the simulated output grid, never
extrapolation) and reports residuals, RMSE, the fraction of observations inside
the band and the number of observations with a standard deviation. It writes
``timecourse_comparison.csv``. The agreement is in-sample agreement with the
user's own data, not validation.

``fit_user_dataset`` fits named kinetic constants of one case (``km`` with
``kcat`` or ``vmax``) to that case's time courses across the chosen conditions
with the existing least-squares calibration (``fit_least_squares``), predicting
with the same assembled model a virtual experiment runs, on the compiled core
(``ConfiguredConditionPredictor``). Bounds are required. Residuals are weighted
by each observation's reported standard deviation; without one the fit is
refused unless ``error_model="unweighted"`` is chosen explicitly. Every fitted
quantity gets an identifiability verdict: a profile likelihood
(``fungal_model.calibration.profile``) for the sd-weighted objective, local
information (``fungal_model.calibration.bayesian.local_information_analysis``)
with linearized intervals for the unweighted one. An unidentified quantity
refuses the fit unless ``allow_unidentified=True``. The result is a new user
dataset whose fitted constants are ``kinetics.csv`` rows of evidence type
``fitted`` (maturity ``user_fitted``, exploratory screening only, refused by
scientific mode), described by a manifest ``fit`` block and a fit report.
Fitted values are in-sample estimates, never validated values.
"""

from __future__ import annotations

import hashlib
import json
import math
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import numpy as np
from scipy.stats import chi2, norm

from fungal_model.api.result_tables import WrittenTables, _write_table
from fungal_model.api.user_data import (
    FIT_BLOCK_KIND,
    FIT_ERROR_MODELS,
    FIT_IDENTIFIED,
    FIT_NOT_IDENTIFIED,
    FITTABLE_QUANTITIES,
    FITTED_EVIDENCE_TYPE,
    TIMECOURSE_TABLE,
    USER_DATASET_MANIFEST,
    UserDataError,
    UserDataset,
    UserTimecourse,
    _base_registry,
    _concentration_kind,
    _dataset_files_with_kinetics,
    _DATASET_ID_PATTERN,
    _issue,
    _Kinetics,
    _number_text,
    _QUANTITY_ROLE,
    _quantity_units_error,
    _QUANTITY_VMAX_ROUTE,
    _write_dataset_files,
    load_user_dataset,
)
from fungal_model.calibration.bayesian import (
    BOUNDED_ABOVE_ONLY,
    BOUNDED_BELOW_ONLY,
    COORDINATE_LOG,
    local_information_analysis,
)
from fungal_model.calibration.compiled_predictor import (
    ConfiguredCondition,
    ConfiguredConditionPredictor,
    ObservableMapping,
)
from fungal_model.calibration.fitting import FittableParameter, LeastSquaresCalibrationResult, fit_least_squares
from fungal_model.calibration.profile import ProfileLikelihoodResult, profile_likelihood
from fungal_model.calibration.residuals import residuals_between
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_, Quantity
from fungal_model.io.model_config import ModelConfig
from fungal_model.registry.records import ParameterRecord, ProcessCompatibilityRecord
from fungal_model.registry.store import FungModRegistry
from fungal_model.screening.case_builder import build_registry_process_config_data, select_registry_case_compatibility
from fungal_model.screening.ensemble import resolve_screen_role_records
from fungal_model.screening.modelability import assess_modelability

if TYPE_CHECKING:
    from fungal_model.api.virtual_experiment import DegradationScreenResult

TIMECOURSE_COMPARISON_TABLE = "timecourse_comparison"
TIMECOURSE_COMPARISON_FILE = "timecourse_comparison.csv"
TIMECOURSE_COMPARISON_ALLOWED_USE = "in_sample_agreement_with_user_timecourses_not_validation"
TIMECOURSE_COMPARISON_NOTE = (
    "In-sample agreement between this simulation and the user's own time courses from the same dataset; it is "
    "not validation. The observations are not independent of the dataset that parameterized the simulation, and "
    "a value fitted to them (used_in_fit) agrees with them by construction."
)
TIMECOURSE_INTERPOLATION = (
    "linear interpolation of the simulated p05, p50 and p95 trajectories between the points of the simulated "
    "output grid; observations outside the simulated time range are refused, never extrapolated"
)
# The simulated trajectory each observable is compared with, as (trajectory_quantiles column, value):
# the substrate state of the case template, and the product formed since time zero.
_OBSERVABLE_TRAJECTORY = {
    "substrate": ("state_role", "substrate"),
    "product": ("state", "product_formed"),
    "soluble_sugar": ("state_role", "soluble_product"),
    "biomass": ("state_role", "biomass"),
    "dissolved_oxygen": ("state_role", "dissolved_oxygen"),
}
# The case-template state each observable measures in a fit.
_OBSERVABLE_STATE_ROLE = {
    "substrate": "substrate", "product": "product", "soluble_sugar": "soluble_product",
    "biomass": "biomass", "dissolved_oxygen": "dissolved_oxygen",
}

FIT_REPORT_FILE = "fit_report.json"
FIT_REPORT_KIND = "fungmod_user_dataset_fit_report"
FIT_METHOD = (
    "bounded nonlinear least squares on the natural logarithm of each fitted value "
    "(fungal_model.calibration.fit_least_squares, scipy.optimize.least_squares trust-region reflective), "
    "predicting the time courses with the assembled virtual-experiment model of the case on the compiled core "
    "(fungal_model.calibration.ConfiguredConditionPredictor)"
)
# Relative finite-difference step of the optimizer Jacobian in log-parameter space. The predictions come
# from an adaptive ODE solver whose step noise scipy's default step (about 1.5e-8) would differentiate; the
# Gelain criticism plan (data/benchmarks/gelain_2020_criticism/plan.json, PETAB-001) declares 1e-3 for the
# same reason. It is a numerical setting, recorded in every fit report, not a model constant.
FIT_DIFFERENCE_STEP = 1e-3
# Bisection steps that narrow each profile-likelihood threshold crossing found between two grid values;
# each step halves the bracket in log space with one more profile evaluation. It sets the precision of an
# interval limit and never the verdict.
FIT_PROFILE_BISECTION_STEPS = 10
FIT_CLAIM_BOUNDARY = (
    "Values fitted to the dataset's own time courses: in-sample parameter estimation, not validation. Agreement "
    "with the fitted time courses is expected by construction and is not independent evidence; the values apply "
    "only to the assay, preparation and conditions of these time courses, under the assumed model and error model."
)
_PROFILE_SOURCE = (
    "fit_user_dataset profile likelihood: each fitted quantity is fixed on a grid in natural-log space spanning "
    "its bounds and the other fitted quantities are refitted; the observation standard deviations are the sd "
    "values the user reported in timecourse.csv, treated as independent Gaussian errors (Raue et al. 2009)."
)
_WORKING_ROW_SOURCE = "fit_user_dataset optimizer starting value; not a measurement"


class UserDataFitError(UserDataError):
    """Raised when ``fit_user_dataset`` refuses to write fitted values.

    ``report`` holds the fit report built so far (convergence, residuals and
    identifiability) when the refusal comes after the fit ran, else ``None``.
    """

    def __init__(
        self,
        message: str,
        *,
        issues: Sequence[Mapping[str, Any]],
        report: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message, issues=issues)
        self.report: dict[str, Any] | None = None if report is None else dict(report)


# ---------------------------------------------------------------------------
# Comparison


@dataclass(frozen=True)
class TimecourseComparison:
    """Simulated trajectories of a virtual experiment against a user dataset's time courses.

    ``rows`` are the ``timecourse_comparison.csv`` rows, one per observation;
    ``series`` summarizes each compared case and observable (RMSE and mean
    residual in the observable's units, fraction inside the 5-95 percent band,
    observations and observations with sd); ``not_compared`` lists the time
    courses the experiment did not simulate, with the reason. ``path`` is the
    written table.
    """

    dataset_id: str
    dataset_digest: str
    rows: tuple[Mapping[str, Any], ...]
    series: tuple[Mapping[str, Any], ...]
    not_compared: tuple[Mapping[str, Any], ...]
    path: str | None
    note: str = TIMECOURSE_COMPARISON_NOTE
    interpolation: str = TIMECOURSE_INTERPOLATION

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "fungmod_timecourse_comparison",
            "dataset_id": self.dataset_id,
            "dataset_digest": self.dataset_digest,
            "note": self.note,
            "interpolation": self.interpolation,
            "allowed_use": TIMECOURSE_COMPARISON_ALLOWED_USE,
            "path": self.path,
            "series": [dict(item) for item in self.series],
            "not_compared": [dict(item) for item in self.not_compared],
            "rows": [dict(item) for item in self.rows],
        }


@dataclass(frozen=True)
class _SimulatedBand:
    context: Mapping[str, str]
    state: str
    times: np.ndarray
    time_units: str
    p05: np.ndarray
    p50: np.ndarray
    p95: np.ndarray
    units: str
    count: int


def compare_with_timecourses(
    result: DegradationScreenResult,
    dataset: UserDataset,
    *,
    output_dir: str | Path | None = None,
) -> TimecourseComparison:
    """Compare a virtual experiment's simulated trajectories with the time courses of its user dataset.

    For every simulated case with time courses, the median (p50) and the 5-95
    percent band (p05, p95) of ``trajectory_quantiles.csv`` are interpolated
    linearly on the simulated output grid to each observed time and converted
    to the observation's units: the substrate state for ``substrate``,
    ``product_formed`` for assay ``product``, or the corresponding uptake-culture
    pool for ``soluble_sugar``, ``biomass`` and ``dissolved_oxygen``. An observation outside the simulated
    time range refuses the comparison; nothing is extrapolated. Residuals are
    simulated median minus observed (``residuals_between``).

    ``dataset`` must be the dataset the experiment was built from (same
    digest). The table is written as ``timecourse_comparison.csv`` into
    ``output_dir``, by default the result's output directory, where it is also
    added to the result's tables and manifest. The agreement is in-sample, not
    validation.
    """

    if result.experiment.user_dataset_digest != dataset.digest:
        raise UserDataError(
            "The virtual experiment was not built from this user dataset.",
            issues=[
                _issue(
                    TIMECOURSE_TABLE,
                    None,
                    None,
                    f"The experiment simulated user dataset {result.experiment.user_dataset_id!r} (digest "
                    f"{result.experiment.user_dataset_digest}); dataset {dataset.dataset_id!r} has digest "
                    f"{dataset.digest}. Compare a result with the time courses of the dataset it simulated.",
                )
            ],
        )
    if not dataset.timecourses:
        raise UserDataError(
            f"User dataset {dataset.dataset_id!r} has no time courses to compare with.",
            issues=[_issue(TIMECOURSE_TABLE, None, None, f"Add a {TIMECOURSE_TABLE} to the dataset directory.")],
        )
    quantile_rows = result.trajectory_quantiles()
    fit_rows = _rows_used_in_fit(dataset)
    by_case: dict[tuple[str, str, str], list[UserTimecourse]] = {}
    for series_list in dataset.timecourses.values():
        for series in series_list:
            by_case.setdefault((series.fungus_id, series.substrate_record_id, series.environment_id), []).append(series)
    matched: list[tuple[UserTimecourse, _SimulatedBand]] = []
    not_compared: list[dict[str, Any]] = []
    simulated: set[tuple[str, str, str]] = set()
    issues: list[dict[str, Any]] = []
    for case in result.screen_result.case_results:
        key = (case.fungus_id, case.substrate_id, case.environment_id)
        simulated.add(key)
        candidates = by_case.get(key, [])
        if not candidates:
            continue
        compatibility = select_registry_case_compatibility(
            registry=result.experiment.registry,
            fungus_id=case.fungus_id,
            substrate_id=case.substrate_id,
            report=case.modelability_report,
        )
        for series in candidates:
            culture_class = dataset._parsed.cultured.get((series.strain_id, series.substrate_id))
            culture = dataset._parsed.culture_pairs.get((culture_class, series.substrate_id))
            shared_culture_pool = culture is not None and culture.uptake and series.class_key in culture.consuming_pools
            if series.enzyme_class_id != compatibility.enzyme_class and not shared_culture_pool:
                not_compared.append(
                    _not_compared(series, f"the simulated case uses enzyme class {compatibility.enzyme_class!r}")
                )
                continue
            band = _simulated_band(quantile_rows, key, series.observable)
            if band is None:
                not_compared.append(_not_compared(series, "trajectory_quantiles.csv has no trajectory for it"))
                continue
            issues.extend(_out_of_range_issues(series, band))
            matched.append((series, band))
    for key, series_list in by_case.items():
        if key not in simulated:
            not_compared.extend(
                _not_compared(series, "the virtual experiment did not simulate this case") for series in series_list
            )
    if issues:
        raise UserDataError(
            "Time-course observations lie outside the simulated time range; FungMod does not extrapolate.",
            issues=issues,
        )
    if not matched:
        raise UserDataError(
            "None of the dataset's time courses matches a case of this virtual experiment.",
            issues=[
                _issue(TIMECOURSE_TABLE, None, None, f"{item['series_id']}: {item['reason']}.") for item in not_compared
            ],
        )
    rows: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for series, band in matched:
        series_rows, summary = _comparison_rows(series, band, fit_rows=fit_rows)
        rows.extend(series_rows)
        summaries.append(summary)
    in_result_directory = output_dir is None
    destination = Path(result.output_directory if output_dir is None else output_dir) / TIMECOURSE_COMPARISON_FILE
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_table(destination, table_name=TIMECOURSE_COMPARISON_TABLE, rows=rows)
    if in_result_directory:
        paths = {} if result.tables is None else dict(result.tables.paths)
        result.tables = WrittenTables(paths={**paths, TIMECOURSE_COMPARISON_TABLE: str(destination)})
        result.write_summary()
        result.write_manifest()
    return TimecourseComparison(
        dataset_id=dataset.dataset_id,
        dataset_digest=dataset.digest,
        rows=tuple(MappingProxyType(row) for row in rows),
        series=tuple(MappingProxyType(item) for item in summaries),
        not_compared=tuple(MappingProxyType(item) for item in not_compared),
        path=str(destination),
    )


def _rows_used_in_fit(dataset: UserDataset) -> frozenset[int]:
    block = dataset.manifest.get("fit")
    if not isinstance(block, Mapping):
        return frozenset()
    return frozenset(int(row) for row in block.get("timecourse_rows", []))


def _not_compared(series: UserTimecourse, reason: str) -> dict[str, Any]:
    return {
        "series_id": series.series_id,
        "case_id": series.case_id,
        "observable": series.observable,
        "rows": list(series.rows),
        "reason": reason,
    }


def _simulated_band(
    quantile_rows: Sequence[Mapping[str, str]],
    key: tuple[str, str, str],
    observable: str,
) -> _SimulatedBand | None:
    column, wanted = _OBSERVABLE_TRAJECTORY[observable]
    rows = [
        row
        for row in quantile_rows
        if (row.get("fungus_id"), row.get("substrate_id"), row.get("environment_id")) == key and row.get(column) == wanted
    ]
    if not rows:
        return None
    rows.sort(key=lambda row: int(row["time_index"]))
    time_units = {row["time_units"] for row in rows}
    units = {row["units"] for row in rows}
    states = {row["state"] for row in rows}
    if len(time_units) != 1 or len(units) != 1 or len(states) != 1:
        raise UserDataError(
            "The simulated trajectory mixes units or states.",
            issues=[_issue("trajectory_quantiles.csv", None, None, f"Case {key} {observable}: {sorted(states)}.")],
        )
    return _SimulatedBand(
        context=rows[0],
        state=states.pop(),
        times=np.asarray([float(row["time"]) for row in rows], dtype=float),
        time_units=time_units.pop(),
        p05=np.asarray([float(row["p05"]) for row in rows], dtype=float),
        p50=np.asarray([float(row["p50"]) for row in rows], dtype=float),
        p95=np.asarray([float(row["p95"]) for row in rows], dtype=float),
        units=units.pop(),
        count=min(int(row["count"]) for row in rows),
    )


def _grid_times(series: UserTimecourse, band: _SimulatedBand) -> np.ndarray:
    return np.asarray(Q_(band.times, band.time_units).to(series.time_units).magnitude, dtype=float)


def _out_of_range_issues(series: UserTimecourse, band: _SimulatedBand) -> list[dict[str, Any]]:
    grid = _grid_times(series, band)
    lower, upper = float(grid[0]), float(grid[-1])
    tolerance = 1e-12 * max(1.0, abs(lower), abs(upper))
    return [
        _issue(
            TIMECOURSE_TABLE,
            point.row,
            "time",
            f"time {_number_text(point.time)} {series.time_units} of {series.series_id} lies outside the simulated "
            f"time range [{_number_text(lower)}, {_number_text(upper)}] {series.time_units}; FungMod does not "
            "extrapolate the simulation. Extend simulation.duration in user_dataset.yml or leave the observation out.",
        )
        for point in series.points
        if point.time < lower - tolerance or point.time > upper + tolerance
    ]


def _comparison_rows(
    series: UserTimecourse,
    band: _SimulatedBand,
    *,
    fit_rows: frozenset[int],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    grid = _grid_times(series, band)
    times = np.asarray([point.time for point in series.points], dtype=float)
    observed = np.asarray([point.value for point in series.points], dtype=float)

    def at_times(values: np.ndarray) -> np.ndarray:
        converted = np.asarray(Q_(values, band.units).to(series.units).magnitude, dtype=float)
        return np.interp(times, grid, converted)

    p05, p50, p95 = at_times(band.p05), at_times(band.p50), at_times(band.p95)
    residuals = residuals_between(
        {series.series_id: Q_(p50, series.units)},
        {series.series_id: Q_(observed, series.units)},
        label="timecourse_comparison",
    )
    residual = np.asarray(residuals.residuals[series.series_id].magnitude, dtype=float)
    rmse = float(residuals.rmse_by_species()[series.series_id]["rmse"])
    inside = (p05 <= observed) & (observed <= p95)
    with_sd = sum(1 for point in series.points if point.sd is not None)
    summary = {
        "series_id": series.series_id,
        "case_id": band.context["case_id"],
        "timecourse_case_id": series.case_id,
        "observable": series.observable,
        "simulated_state": band.state,
        "units": series.units,
        "time_units": series.time_units,
        "n_observations": len(series.points),
        "n_with_sd": with_sd,
        "rmse": rmse,
        "mean_residual": float(np.mean(residual)),
        "fraction_inside_band": float(np.mean(inside)),
        "rows": list(series.rows),
    }
    case_columns = {name: band.context.get(name, "") for name in _CASE_COLUMN_NAMES}
    rows = []
    for index, point in enumerate(series.points):
        rows.append(
            {
                **case_columns,
                "timecourse_case_id": series.case_id,
                "observable": series.observable,
                "simulated_state": band.state,
                "timecourse_row": point.row,
                "time": point.time,
                "time_units": series.time_units,
                "observed": point.value,
                "sd": point.sd,
                "replicates": point.replicates,
                "units": series.units,
                "simulated_p05": float(p05[index]),
                "simulated_p50": float(p50[index]),
                "simulated_p95": float(p95[index]),
                "sample_count": band.count,
                "residual": float(residual[index]),
                "standardized_residual": None if point.sd is None else float(residual[index] / point.sd),
                "inside_band": bool(inside[index]),
                "series_n_observations": summary["n_observations"],
                "series_n_with_sd": with_sd,
                "series_rmse": rmse,
                "series_mean_residual": summary["mean_residual"],
                "series_fraction_inside_band": summary["fraction_inside_band"],
                "interpolation": TIMECOURSE_INTERPOLATION,
                "used_in_fit": point.row in fit_rows,
                "allowed_use": TIMECOURSE_COMPARISON_ALLOWED_USE,
                "interpretation_guardrail": TIMECOURSE_COMPARISON_NOTE,
            }
        )
    return rows, summary


_CASE_COLUMN_NAMES = (
    "output_schema_version",
    "case_id",
    "fungus_id",
    "fungus_name",
    "substrate_id",
    "substrate_name",
    "environment_id",
    "environment_name",
    "temperature_C",
    "ph",
    "oxygen",
    "environment_source",
    "environment_effect_status",
    "environment_response_model",
    "environment_comparison_allowed",
    "environment_ranking_allowed",
    "environment_response_plot_allowed",
    "environment_guardrail",
    "process_type",
)


# ---------------------------------------------------------------------------
# Fit


@dataclass(frozen=True)
class FittedQuantity:
    """One fitted kinetic constant, its bounds, starting value and identifiability verdict.

    ``interval`` is the profile-likelihood interval (sd-weighted objective) or
    the linearized interval (unweighted objective) at ``confidence_level``; an
    end that the data do not constrain is the bound itself, and an unidentified
    quantity has no interval.
    """

    quantity: str
    symbol: str
    value: float
    units: str
    lower_bound: float
    upper_bound: float
    initial: float
    initial_source: str
    identifiability: str
    identifiability_method: str
    interval: tuple[float, float] | None
    reason: str

    @property
    def identified(self) -> bool:
        return self.identifiability == FIT_IDENTIFIED

    def to_dict(self) -> dict[str, Any]:
        return {
            "quantity": self.quantity,
            "symbol": self.symbol,
            "value": self.value,
            "units": self.units,
            "bounds": [self.lower_bound, self.upper_bound],
            "initial": self.initial,
            "initial_source": self.initial_source,
            "identifiability": self.identifiability,
            "identifiability_method": self.identifiability_method,
            "interval": None if self.interval is None else list(self.interval),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class UserDatasetFit:
    """A fit of a user dataset's kinetic constants to its time courses, and the fitted dataset's files.

    ``report`` is the full fit report (``fit_report.json``); ``files`` are the
    fitted dataset's files by relative path. ``write(path)`` writes them into
    a new directory and loads the fitted dataset from it.
    """

    input_dataset_id: str
    input_dataset_digest: str
    dataset_id: str
    quantities: tuple[FittedQuantity, ...]
    report: Mapping[str, Any]
    files: Mapping[str, bytes] = field(repr=False)

    @property
    def identified(self) -> bool:
        return all(item.identified for item in self.quantities)

    def write(self, path: str | Path, *, registry: str | Path | FungModRegistry | None = None) -> UserDataset:
        """Write the fitted dataset into a new or empty directory and return it loaded from there."""

        directory = Path(path)
        _write_dataset_files(self.files, directory)
        return load_user_dataset(directory, registry=registry)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.report)


@dataclass(frozen=True)
class _FitTarget:
    quantity: str
    units: str
    lower: float
    upper: float
    initial: float
    initial_source: str


@dataclass(frozen=True)
class _FitCase:
    strain_id: str
    class_key: str
    substrate_id: str
    series: tuple[UserTimecourse, ...]
    conditions: tuple[str, ...]


def fit_user_dataset(
    dataset: UserDataset | str | Path,
    *,
    parameters: Sequence[tuple[str, str, str, str]],
    bounds: Mapping[Any, tuple[float, float, str]],
    initial: Mapping[Any, float] | None = None,
    conditions: Sequence[str] | None = None,
    base_registry: str | Path | FungModRegistry | None = None,
    error_model: str = "sd_weighted",
    allow_unidentified: bool = False,
    fitted_dataset_id: str | None = None,
    confidence_level: float = 0.95,
    profile_points: int = 21,
    diff_step: float = FIT_DIFFERENCE_STEP,
    max_nfev: int | None = None,
) -> UserDatasetFit:
    """Fit kinetic constants of one case of a user dataset to that case's time courses.

    ``parameters`` names ``(strain_id, enzyme_class, substrate_id, quantity)``
    tuples of one case (strain, enzyme class and substrate) with quantities
    among ``km``, ``kcat`` and ``vmax``; the class is the ``class_id`` or
    registry enzyme-class id the tables use. The time courses of that case at
    ``conditions`` (by default every condition with time courses) are fitted
    together, so each fitted constant is shared by those conditions, which must
    then have the same known temperature and pH. Every other role of the case
    must be an exact value.

    ``bounds`` is required for every quantity, keyed by the parameter tuple or
    the quantity name, as ``(lower, upper, units)`` with ``0 < lower < upper``;
    the fitted value is reported in those units. ``initial`` gives starting
    values in the same units; a quantity without one starts from the dataset's
    exact value of every fitted condition, and is refused when there is none.

    ``error_model`` is ``sd_weighted`` (residuals divided by each observation's
    sd; refused when any observation lacks sd) or ``unweighted`` (raw
    residuals, chosen explicitly and recorded; refused when the series use
    different units). Identifiability is judged by a profile likelihood for
    ``sd_weighted`` (threshold: the chi-square quantile of one degree of
    freedom at ``confidence_level``) and by local information with linearized
    intervals for ``unweighted``. A quantity that is not identified on both
    sides within its bounds refuses the fit with ``UserDataFitError`` unless
    ``allow_unidentified=True``, in which case its rows are labelled. A fit
    that does not converge is always refused.

    Returns a ``UserDatasetFit`` whose files are a copy of the input dataset
    with the fitted quantities as ``fitted`` rows at the fitted conditions,
    the manifest ``fit`` block, ``fit_report.json`` and the input digest; its
    id is ``fitted_dataset_id`` (default ``<input id>_fitted``). A dataset that
    is itself the result of a fit is refused: fits are not chained.
    """

    base = _base_registry(base_registry)
    source = dataset if isinstance(dataset, UserDataset) else load_user_dataset(dataset, registry=base)
    _check_settings(
        error_model=error_model,
        confidence_level=confidence_level,
        profile_points=profile_points,
        diff_step=diff_step,
    )
    if source._parsed is None or "kinetics.csv" not in source._raw_files:
        raise UserDataFitError(
            f"User dataset {source.dataset_id!r} was not read by load_user_dataset.",
            issues=[_issue(USER_DATASET_MANIFEST, None, None, "Load the dataset directory with load_user_dataset.")],
        )
    if isinstance(source.manifest.get("fit"), Mapping):
        raise UserDataFitError(
            f"User dataset {source.dataset_id!r} is itself the result of a fit.",
            issues=[
                _issue(
                    USER_DATASET_MANIFEST,
                    None,
                    "fit",
                    "fit_user_dataset fits the dataset that holds the original time courses and kinetics; refitting "
                    "fitted values would chain in-sample estimates.",
                )
            ],
        )
    case, quantities = _fit_case(source, parameters, conditions)
    targets = _fit_targets(source, case, quantities, parameters, bounds, initial)
    _check_rate_form(source, case, quantities)
    points = [(series, point) for series in case.series for point in series.points]
    _check_error_model(case, error_model)
    if len(points) <= len(quantities):
        raise UserDataFitError(
            "Too few observations for the fitted quantities.",
            issues=[
                _issue(
                    TIMECOURSE_TABLE,
                    None,
                    None,
                    f"{len(points)} observations cannot determine {len(quantities)} quantities; the fit needs more "
                    "observations than fitted quantities.",
                )
            ],
        )
    working_registry = _working_registry(source, base, case, targets)
    problem = _FitProblem.build(working_registry, case, targets)
    observations = {
        series.series_id: Q_(np.asarray([point.value for point in series.points], dtype=float), series.units)
        for series in case.series
    }
    scales: dict[str, Quantity] | None = None
    if error_model == "sd_weighted":
        scales = {
            series.series_id: Q_(np.asarray([float(point.sd or 0.0) for point in series.points], dtype=float), series.units)
            for series in case.series
        }
    base_parameters = ParameterSet(
        _log_parameter(problem.log_symbol(target.quantity), math.log(target.initial), target, label="starting value")
        for target in targets
    )
    fittables = tuple(
        FittableParameter(
            symbol=problem.log_symbol(target.quantity),
            lower_bound=_log_parameter(f"{problem.log_symbol(target.quantity)}_lower_bound", math.log(target.lower), target, label="lower bound"),
            upper_bound=_log_parameter(f"{problem.log_symbol(target.quantity)}_upper_bound", math.log(target.upper), target, label="upper bound"),
            notes=f"natural log of {target.quantity} in {target.units}; bounds from the caller",
        )
        for target in targets
    )
    calibration_source = (
        f"fit_user_dataset on user dataset {source.dataset_id} (sha256 {source.digest}), {TIMECOURSE_TABLE} rows "
        f"{_rows_text([point.row for _, point in points])}"
    )
    fit = fit_least_squares(
        base_parameters=base_parameters,
        fittable_parameters=fittables,
        predict=problem.predict,
        observations=observations,
        residual_scales=scales,
        validation_indices=(),
        calibration_source=calibration_source,
        max_nfev=max_nfev,
        diff_step=diff_step,
    )
    settings = {
        "error_model": error_model,
        "confidence_level": confidence_level,
        "profile_points": profile_points,
        "profile_bisection_steps": FIT_PROFILE_BISECTION_STEPS,
        "difference_step": diff_step,
        "difference_step_note": (
            "relative finite-difference step of the optimizer Jacobian in natural-log parameter space, above the "
            "step noise of the adaptive ODE solver"
        ),
        "max_nfev": max_nfev,
        "parameter_space": "natural logarithm of each fitted value in the units of its bounds",
    }
    report: dict[str, Any] = {
        "kind": FIT_REPORT_KIND,
        "schema_version": "1",
        "input_dataset_id": source.dataset_id,
        "input_dataset_digest": source.digest,
        "fitted_dataset_id": None,
        "case": {"strain_id": case.strain_id, "enzyme_class": case.class_key, "substrate_id": case.substrate_id},
        "conditions": list(case.conditions),
        "timecourse_file": TIMECOURSE_TABLE,
        "timecourse_rows": sorted(point.row for _, point in points),
        "method": FIT_METHOD,
        "objective": _objective_text(error_model, case),
        "error_model": error_model,
        "settings": settings,
        "n_observations": len(points),
        "n_parameters": len(targets),
        "residual_degrees_of_freedom": len(points) - len(targets),
        "observations_per_parameter": len(points) / len(targets),
        "convergence": _convergence(fit),
        "claim_boundary": FIT_CLAIM_BOUNDARY,
    }
    if not fit.success or fit.training_residuals is None:
        report["warnings"] = list(fit.warnings)
        raise UserDataFitError(
            "The fit did not converge; no fitted values are written.",
            issues=[_issue(TIMECOURSE_TABLE, None, None, f"Optimizer: {fit.message}")],
            report=report,
        )
    center = np.asarray(
        [float(fit.fitted_parameters.require_quantity(problem.log_symbol(target.quantity)).magnitude) for target in targets],
        dtype=float,
    )
    report["residuals"] = problem.residual_report(fit.fitted_parameters, scales)
    local = local_information_analysis(
        lambda vector: problem.scaled_residuals(vector, [target.quantity for target in targets], observations, scales),
        center,
        labels=[target.quantity for target in targets],
        coordinate_kinds=[COORDINATE_LOG] * len(targets),
    )
    if error_model == "sd_weighted":
        assert scales is not None
        fitted, identifiability = _profile_identifiability(
            fit=fit,
            problem=problem,
            targets=targets,
            center=center,
            observations=observations,
            scales=scales,
            confidence_level=confidence_level,
            profile_points=profile_points,
            diff_step=diff_step,
            max_nfev=max_nfev,
        )
    else:
        fitted, identifiability = _local_identifiability(
            fit=fit,
            problem=problem,
            targets=targets,
            center=center,
            local=local,
            confidence_level=confidence_level,
        )
    report["quantities"] = [item.to_dict() for item in fitted]
    report["identifiability"] = {**identifiability, "local_information": local}
    report["identified"] = all(item.identified for item in fitted)
    report["allow_unidentified"] = allow_unidentified
    report["warnings"] = list(fit.warnings)
    unidentified = [item for item in fitted if not item.identified]
    if unidentified and not allow_unidentified:
        raise UserDataFitError(
            "A fitted quantity is not identified by the time courses; no fitted values are written.",
            issues=[
                _issue(
                    TIMECOURSE_TABLE,
                    None,
                    None,
                    f"{item.quantity} is {item.identifiability} ({item.identifiability_method}): {item.reason} "
                    "Add observations that constrain it (for example time courses at substrate concentrations near "
                    "and below Km), narrow the bounds with independent evidence, or pass allow_unidentified=True "
                    "to write it labelled as not identified.",
                )
                for item in unidentified
            ],
            report=report,
        )
    new_id = fitted_dataset_id or f"{source.dataset_id}_fitted"
    if not _DATASET_ID_PATTERN.fullmatch(new_id) or new_id == source.dataset_id:
        raise UserDataFitError(
            f"fitted_dataset_id {new_id!r} is not usable.",
            issues=[
                _issue(
                    USER_DATASET_MANIFEST,
                    None,
                    "dataset_id",
                    "The fitted dataset needs its own lowercase snake_case dataset_id, different from the input's.",
                )
            ],
        )
    report["fitted_dataset_id"] = new_id
    files = _fitted_files(source, case, fitted, report, allow_unidentified=allow_unidentified)
    with tempfile.TemporaryDirectory(prefix="fungmod_fitted_dataset_") as directory:
        _write_dataset_files(files, Path(directory) / "dataset")
        try:
            load_user_dataset(Path(directory) / "dataset", registry=base)
        except UserDataError as exc:
            raise UserDataFitError(
                "The fitted dataset does not load; no fitted values are written.", issues=exc.issues, report=report
            ) from exc
    return UserDatasetFit(
        input_dataset_id=source.dataset_id,
        input_dataset_digest=source.digest,
        dataset_id=new_id,
        quantities=tuple(fitted),
        report=MappingProxyType(report),
        files=MappingProxyType(files),
    )


def _check_settings(*, error_model: str, confidence_level: float, profile_points: int, diff_step: float) -> None:
    problems: list[str] = []
    if error_model not in FIT_ERROR_MODELS:
        problems.append(
            f"error_model must be one of {', '.join(FIT_ERROR_MODELS)}; unweighted is used only when named."
        )
    if not isinstance(confidence_level, float) or not 0.0 < confidence_level < 1.0:
        problems.append("confidence_level must be a number between 0 and 1.")
    if isinstance(profile_points, bool) or not isinstance(profile_points, int) or profile_points < 3:
        problems.append("profile_points must be an integer of at least 3.")
    if not isinstance(diff_step, float) or not 0.0 < diff_step < 1.0:
        problems.append("diff_step must be a relative step between 0 and 1.")
    if problems:
        raise UserDataFitError(
            "Invalid fit settings.", issues=[_issue(TIMECOURSE_TABLE, None, None, problem) for problem in problems]
        )


def _fit_case(
    dataset: UserDataset,
    parameters: Sequence[tuple[str, str, str, str]],
    conditions: Sequence[str] | None,
) -> tuple[_FitCase, tuple[str, ...]]:
    keys = [tuple(item) for item in parameters]
    if not keys or not all(len(key) == 4 and all(isinstance(part, str) and part for part in key) for key in keys):
        raise UserDataFitError(
            "parameters must name (strain_id, enzyme_class, substrate_id, quantity) tuples.",
            issues=[_issue(TIMECOURSE_TABLE, None, None, f"Received {list(parameters)!r}.")],
        )
    cases = sorted({key[:3] for key in keys})
    if len(cases) != 1:
        raise UserDataFitError(
            "One fit covers one case (strain, enzyme class and substrate).",
            issues=[_issue(TIMECOURSE_TABLE, None, None, f"parameters name the cases {cases}; fit them separately.")],
        )
    strain_id, class_text, substrate_id = cases[0]
    if (strain_id, substrate_id) in dataset._parsed.cultured:
        raise UserDataFitError(
            "Culture time courses support comparison, not parameter fitting in this version.",
            issues=[_issue(TIMECOURSE_TABLE, None, None,
                "fit_user_dataset fits km, kcat and vmax in kinetics.csv only. It does not fit uptake, "
                "maintenance, yield, secretion or oxygen constants in culture.csv or aeration.csv.")],
        )
    quantities = tuple(key[3] for key in keys)
    bad = [quantity for quantity in quantities if quantity not in FITTABLE_QUANTITIES]
    if bad or len(set(quantities)) != len(quantities):
        raise UserDataFitError(
            "Unsupported or repeated fitted quantities.",
            issues=[
                _issue(
                    TIMECOURSE_TABLE,
                    None,
                    None,
                    f"Quantities {list(quantities)}: each must appear once and be one of "
                    f"{', '.join(FITTABLE_QUANTITIES)} (the kinetic constants of the rate form).",
                )
            ],
        )
    if "kcat" in quantities and "vmax" in quantities:
        raise UserDataFitError(
            "kcat and vmax belong to different rate forms.",
            issues=[_issue(TIMECOURSE_TABLE, None, None, "Fit km with kcat, or km with vmax, not kcat with vmax.")],
        )
    candidates = [
        series
        for series_list in dataset.timecourses.values()
        for series in series_list
        if series.strain_id == strain_id
        and series.substrate_id == substrate_id
        and class_text in {series.class_key, series.enzyme_class_id}
    ]
    if not candidates:
        available = sorted({series.case_id for series_list in dataset.timecourses.values() for series in series_list})
        raise UserDataFitError(
            "The dataset has no time courses for this case.",
            issues=[
                _issue(
                    TIMECOURSE_TABLE,
                    None,
                    None,
                    f"No time course for strain {strain_id!r}, enzyme class {class_text!r}, substrate "
                    f"{substrate_id!r}; cases with time courses: {available or 'none'}.",
                )
            ],
        )
    parsed = dataset._parsed
    with_timecourses = {series.condition_id for series in candidates}
    # Conditions in conditions.csv order, so a report does not depend on the order of timecourse.csv rows.
    available_conditions = tuple(condition for condition in parsed.conditions if condition in with_timecourses)
    chosen = available_conditions if conditions is None else tuple(dict.fromkeys(conditions))
    missing = [condition for condition in chosen if condition not in available_conditions]
    if missing or not chosen:
        raise UserDataFitError(
            "Fit conditions without time courses.",
            issues=[
                _issue(
                    TIMECOURSE_TABLE,
                    None,
                    "condition_id",
                    f"Conditions {missing or list(chosen)} have no time course for this case; conditions with time "
                    f"courses: {list(available_conditions)}.",
                )
            ],
        )
    if len(chosen) > 1:
        environments = {
            condition: (parsed.conditions[condition].temperature_kelvin, parsed.conditions[condition].ph)
            for condition in chosen
        }
        if any(value is None for pair in environments.values() for value in pair) or len(set(environments.values())) > 1:
            raise UserDataFitError(
                "A constant shared across conditions needs one temperature and pH.",
                issues=[
                    _issue(
                        "conditions.csv",
                        parsed.conditions[condition].row,
                        None,
                        f"Condition {condition!r}: temperature {parsed.conditions[condition].temperature_text} "
                        f"{parsed.conditions[condition].temperature_units}, pH {parsed.conditions[condition].ph_text}. "
                        "The fitted constants are shared by all fitted conditions, so these must have the same known "
                        "temperature and pH (for example several initial substrate concentrations in one assay); fit "
                        "each temperature or pH separately.",
                    )
                    for condition in chosen
                ],
            )
    return (
        _FitCase(
            strain_id=strain_id,
            class_key=candidates[0].class_key,
            substrate_id=substrate_id,
            series=tuple(series for series in candidates if series.condition_id in chosen),
            conditions=chosen,
        ),
        quantities,
    )


def _keyed(
    mapping: Mapping[Any, Any] | None,
    *,
    label: str,
    parameters: Sequence[tuple[str, str, str, str]],
    quantities: Sequence[str],
) -> dict[str, Any]:
    """Re-key a mapping by quantity; keys are the parameter tuples or the bare quantity names."""

    if mapping is None:
        return {}
    by_tuple = {tuple(key): key[3] for key in parameters}
    output: dict[str, Any] = {}
    unknown: list[Any] = []
    for key, value in mapping.items():
        quantity = key if isinstance(key, str) and key in quantities else by_tuple.get(tuple(key)) if isinstance(key, tuple) else None
        if quantity is None:
            unknown.append(key)
            continue
        output[str(quantity)] = value
    if unknown:
        raise UserDataFitError(
            f"{label} names quantities that are not fitted.",
            issues=[_issue(TIMECOURSE_TABLE, None, None, f"{label} keys {unknown!r} are not among {list(quantities)}.")],
        )
    return output


def _fit_targets(
    dataset: UserDataset,
    case: _FitCase,
    quantities: Sequence[str],
    parameters: Sequence[tuple[str, str, str, str]],
    bounds: Mapping[Any, tuple[float, float, str]],
    initial: Mapping[Any, float] | None,
) -> tuple[_FitTarget, ...]:
    keyed_bounds = _keyed(bounds, label="bounds", parameters=parameters, quantities=quantities)
    keyed_initial = _keyed(initial, label="initial", parameters=parameters, quantities=quantities)
    issues: list[dict[str, Any]] = []
    targets: list[_FitTarget] = []
    for quantity in quantities:
        spec = keyed_bounds.get(quantity)
        if spec is None:
            issues.append(
                _issue(
                    TIMECOURSE_TABLE,
                    None,
                    None,
                    f"bounds for {quantity} are required as (lower, upper, units); fit_user_dataset has no default bounds.",
                )
            )
            continue
        problem = _bounds_problem(quantity, spec)
        if problem is not None:
            issues.append(_issue(TIMECOURSE_TABLE, None, None, problem))
            continue
        lower, upper, units = float(spec[0]), float(spec[1]), str(spec[2])
        start, start_source, start_problem = _initial_value(dataset, case, quantity, units, keyed_initial.get(quantity))
        if start_problem is not None:
            issues.append(_issue("kinetics.csv", None, None, start_problem))
            continue
        assert start is not None
        if not lower <= start <= upper:
            issues.append(
                _issue(
                    TIMECOURSE_TABLE,
                    None,
                    None,
                    f"The starting value of {quantity}, {_number_text(start)} {units}, lies outside its bounds "
                    f"[{_number_text(lower)}, {_number_text(upper)}] {units}.",
                )
            )
            continue
        targets.append(_FitTarget(quantity, units, lower, upper, start, start_source))
    if issues:
        raise UserDataFitError("Invalid fit bounds or starting values.", issues=issues)
    return tuple(targets)


def _bounds_problem(quantity: str, spec: Any) -> str | None:
    if not isinstance(spec, (tuple, list)) or len(spec) != 3:
        return f"bounds for {quantity} must be (lower, upper, units)."
    lower, upper, units = spec
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in (lower, upper)):
        return f"bounds for {quantity} must be numbers."
    if not (math.isfinite(lower) and math.isfinite(upper) and 0.0 < lower < upper):
        return (
            f"bounds for {quantity} must satisfy 0 < lower < upper and be finite; the fit works on ln({quantity}), "
            "so a bound of zero or below has no meaning."
        )
    if not isinstance(units, str) or not units:
        return f"bounds for {quantity} need units."
    error = _quantity_units_error(quantity, units)
    if error is not None:
        return error
    if quantity == "km" and _concentration_kind(units) != "molar":
        return f"km units {units!r} must be an amount per volume, the kind of the case's concentrations."
    return None


def _initial_value(
    dataset: UserDataset,
    case: _FitCase,
    quantity: str,
    units: str,
    given: Any,
) -> tuple[float | None, str, str | None]:
    if given is not None:
        if isinstance(given, bool) or not isinstance(given, (int, float)) or not math.isfinite(given) or given <= 0.0:
            return None, "", f"initial for {quantity} must be a finite positive number in {units}."
        return float(given), "caller-supplied starting value", None
    rows = [
        row
        for row in dataset._parsed.kinetics
        if (row.strain_id, row.class_key, row.substrate_id) == (case.strain_id, case.class_key, case.substrate_id)
        and row.condition_id in case.conditions
        and row.quantity == quantity
        and row.value is not None
    ]
    values = sorted({float(Q_(row.value, row.units).to(units).magnitude) for row in rows})
    if len({row.condition_id for row in rows}) != len(case.conditions) or not values:
        return (
            None,
            "",
            f"{quantity} has no exact kinetics.csv value at every fitted condition to start from; give initial for it.",
        )
    if not all(math.isclose(value, values[0], rel_tol=1e-12) for value in values) or values[0] <= 0.0:
        return None, "", f"The kinetics.csv values of {quantity} differ between the fitted conditions; give initial for it."
    return values[0], f"kinetics.csv rows {_rows_text([row.row for row in rows])}", None


def _case_rows(dataset: UserDataset, case: _FitCase, condition: str) -> list[_Kinetics]:
    return [
        row
        for row in dataset._parsed.kinetics
        if row.case_key == (case.strain_id, case.class_key, case.substrate_id, condition)
    ]


def _check_rate_form(dataset: UserDataset, case: _FitCase, quantities: Sequence[str]) -> None:
    issues: list[dict[str, Any]] = []
    for condition in case.conditions:
        rows = _case_rows(dataset, case, condition)
        present = {row.quantity for row in rows}
        if "kcat" in quantities and present.intersection(_QUANTITY_VMAX_ROUTE):
            issues.append(
                _issue(
                    "kinetics.csv",
                    None,
                    "quantity",
                    f"Condition {condition!r} uses the Vmax form ({sorted(present.intersection(_QUANTITY_VMAX_ROUTE))}); "
                    "fitting kcat would mix the two rate forms. Fit vmax instead.",
                )
            )
        if "vmax" in quantities and present.intersection({"kcat", "enzyme_concentration"}):
            issues.append(
                _issue(
                    "kinetics.csv",
                    None,
                    "quantity",
                    f"Condition {condition!r} uses the kcat form ({sorted(present.intersection({'kcat', 'enzyme_concentration'}))}); "
                    "fitting vmax would mix the two rate forms. Fit kcat instead.",
                )
            )
    if issues:
        raise UserDataFitError("The fitted quantities do not match the case's rate form.", issues=issues)


def _check_error_model(case: _FitCase, error_model: str) -> None:
    if error_model == "sd_weighted":
        missing = [(series, point) for series in case.series for point in series.points if point.sd is None]
        if missing:
            raise UserDataFitError(
                "Observations without sd cannot be weighted.",
                issues=[
                    _issue(
                        TIMECOURSE_TABLE,
                        point.row,
                        "sd",
                        f"{series.series_id} at time {_number_text(point.time)} {series.time_units} has no sd. The "
                        "sd-weighted objective divides each residual by its observation's standard deviation and "
                        "FungMod does not invent one. Give sd, or pass error_model='unweighted' to fit raw residuals "
                        "(an explicit choice the fit records).",
                    )
                    for series, point in missing
                ],
            )
        return
    units = sorted({series.units for series in case.series})
    if len(units) > 1:
        raise UserDataFitError(
            "An unweighted objective needs one value unit.",
            issues=[
                _issue(
                    TIMECOURSE_TABLE,
                    None,
                    "units",
                    f"The fitted series use {units}; an unweighted sum of squared residuals would weight them by the "
                    "choice of units. Use one unit for every series, or give sd and use the sd-weighted objective.",
                )
            ],
        )


def _replacement_rows(
    dataset: UserDataset,
    case: _FitCase,
    values: Mapping[str, tuple[float, str]],
    *,
    evidence_type: str,
    method: str,
    source: str,
) -> tuple[list[int], list[dict[str, str]]]:
    """kinetics.csv lines replaced by the fitted quantities at the fitted conditions, and the new rows.

    A fitted ``vmax`` replaces the case's whole Vmax route (explicit Vmax,
    specific activity and enzyme loading, or assay activity) at that condition.
    """

    drop: list[int] = []
    rows: list[dict[str, str]] = []
    for condition in case.conditions:
        for row in _case_rows(dataset, case, condition):
            replaced = row.quantity in values or ("vmax" in values and row.quantity in _QUANTITY_VMAX_ROUTE)
            if replaced:
                drop.append(row.row)
        for quantity, (value, units) in values.items():
            rows.append(
                {
                    "strain_id": case.strain_id,
                    "enzyme_class": case.class_key,
                    "substrate_id": case.substrate_id,
                    "condition_id": condition,
                    "quantity": quantity,
                    "value": repr(float(value)),
                    "units": units,
                    "evidence_type": evidence_type,
                    "method": method,
                    "source": source,
                }
            )
    return drop, rows


def _working_registry(
    dataset: UserDataset,
    base: FungModRegistry,
    case: _FitCase,
    targets: Sequence[_FitTarget],
) -> FungModRegistry:
    """The dataset with the fitted quantities as exact starting values, overlaid on the base registry.

    The starting-value rows are exploratory estimates; every prediction
    replaces their values, so they only carry the units and the role binding.
    """

    drop, rows = _replacement_rows(
        dataset,
        case,
        {target.quantity: (target.initial, target.units) for target in targets},
        evidence_type="estimate",
        method="fit_user_dataset optimizer starting value",
        source=_WORKING_ROW_SOURCE,
    )
    files = _dataset_files_with_kinetics(dataset, drop_rows=drop, new_rows=rows, manifest=dataset.manifest)
    with tempfile.TemporaryDirectory(prefix="fungmod_fit_working_") as directory:
        _write_dataset_files(files, Path(directory) / "dataset")
        try:
            working = load_user_dataset(Path(directory) / "dataset", registry=base)
        except UserDataError as exc:
            raise UserDataFitError(
                "The dataset with the fit's starting values is invalid (row numbers refer to that copy).",
                issues=exc.issues,
            ) from exc
    return working.overlay(base)


@dataclass
class _FitProblem:
    """Predictions of the fitted case's time courses for candidate values of the fitted quantities."""

    case: _FitCase
    targets: tuple[_FitTarget, ...]
    symbols: dict[str, str]
    predictor: ConfiguredConditionPredictor
    times: dict[str, np.ndarray]
    indices: dict[str, np.ndarray]

    @classmethod
    def build(cls, registry: FungModRegistry, case: _FitCase, targets: Sequence[_FitTarget]) -> _FitProblem:
        issues: list[dict[str, Any]] = []
        conditions: list[ConfiguredCondition] = []
        symbols: dict[str, str] = {}
        times: dict[str, np.ndarray] = {}
        indices: dict[str, np.ndarray] = {}
        fitted_roles = {_QUANTITY_ROLE[target.quantity]: target.quantity for target in targets}
        for condition in case.conditions:
            condition_series = [series for series in case.series if series.condition_id == condition]
            first = condition_series[0]
            ids = (first.fungus_id, first.substrate_record_id, first.environment_id)
            report = assess_modelability(
                fungus_id=ids[0], substrate_id=ids[1], environment_id=ids[2], registry=registry, mode="exploratory"
            )
            if report.status not in {"modelable", "exploratory"}:
                missing = "; ".join(item.message for item in (*report.missing, *report.incompatible))
                issues.append(
                    _issue(
                        "kinetics.csv",
                        None,
                        None,
                        f"Condition {condition!r} cannot be simulated with the starting values ({report.status}): "
                        f"{missing}. Every role the fit does not vary needs a value.",
                    )
                )
                continue
            compatibility = select_registry_case_compatibility(
                registry=registry, fungus_id=ids[0], substrate_id=ids[1], report=report
            )
            if compatibility.enzyme_class != first.enzyme_class_id:
                issues.append(
                    _issue(
                        TIMECOURSE_TABLE,
                        None,
                        "enzyme_class",
                        f"Condition {condition!r}: the simulated case uses enzyme class {compatibility.enzyme_class!r}, "
                        f"not {first.enzyme_class_id!r}.",
                    )
                )
                continue
            records = resolve_screen_role_records(
                registry=registry,
                compatibility=compatibility,
                fungus_id=ids[0],
                substrate_id=ids[1],
                environment_id=ids[2],
                mode="exploratory",
            )
            for role, record in records.items():
                if role in fitted_roles:
                    symbols.setdefault(fitted_roles[role], record.parameter_symbol)
                elif not record.value.is_exact:
                    issues.append(
                        _issue(
                            "kinetics.csv",
                            None,
                            None,
                            f"Condition {condition!r}: role {role} is a {record.value.kind} value "
                            f"({record.record_id}); the fit needs every role it does not vary to be exact, and "
                            "FungMod does not pick a value from a range.",
                        )
                    )
            missing_roles = sorted(set(fitted_roles).difference(records))
            if missing_roles:
                issues.append(
                    _issue("kinetics.csv", None, None, f"Condition {condition!r} has no role {missing_roles} to fit.")
                )
                continue
            template = registry.get_case_template(str(compatibility.case_template_id))
            product_start = template.initial_state_mapping.get(_OBSERVABLE_STATE_ROLE["product"], {})
            if any(series.observable == "product" for series in condition_series) and product_start.get("value") != 0.0:
                issues.append(
                    _issue(
                        TIMECOURSE_TABLE,
                        None,
                        "observable",
                        f"Condition {condition!r}: product formed equals the product state only when the product "
                        "starts at zero, which this case template does not state.",
                    )
                )
                continue
            time_grid = template.time_grid
            grid_units = str(time_grid["units"])
            start, stop = float(time_grid["start"]), float(time_grid["stop"])
            # The comparison's tolerance: a unit conversion may move an end time by a rounding error.
            tolerance = 1e-12 * max(1.0, abs(start), abs(stop))
            all_times: list[np.ndarray] = []
            for series in condition_series:
                converted = np.asarray(
                    Q_(np.asarray([point.time for point in series.points], dtype=float), series.time_units)
                    .to(grid_units)
                    .magnitude,
                    dtype=float,
                )
                for point, value in zip(series.points, converted, strict=True):
                    if value < start - tolerance or value > stop + tolerance:
                        issues.append(
                            _issue(
                                TIMECOURSE_TABLE,
                                point.row,
                                "time",
                                f"time {_number_text(point.time)} {series.time_units} lies outside the simulated "
                                f"time range [{_number_text(start)}, {_number_text(stop)}] {grid_units}; FungMod "
                                "does not extrapolate. Extend simulation.duration or leave the observation out.",
                            )
                        )
                all_times.append(np.clip(converted, start, stop))
            union = np.unique(np.concatenate(all_times))
            times[condition] = union
            for series, converted in zip(condition_series, all_times, strict=True):
                indices[series.series_id] = np.searchsorted(union, converted)
            conditions.append(
                ConfiguredCondition(
                    condition,
                    _config_factory(registry, compatibility, ids, records),
                    tuple(
                        ObservableMapping(
                            series.series_id, template.state_roles[_OBSERVABLE_STATE_ROLE[series.observable]], series.units
                        )
                        for series in condition_series
                    ),
                )
            )
        if issues:
            raise UserDataFitError("The fitted case cannot be predicted.", issues=issues)
        return cls(
            case=case,
            targets=tuple(targets),
            symbols=symbols,
            predictor=ConfiguredConditionPredictor(conditions, fitted_symbols=[symbols[t.quantity] for t in targets]),
            times=times,
            indices=indices,
        )

    def log_symbol(self, quantity: str) -> str:
        return f"ln__{self.symbols[quantity]}"

    def values_from_vector(self, vector: Sequence[float], quantities: Sequence[str]) -> dict[str, float]:
        return {self.symbols[quantity]: float(math.exp(value)) for quantity, value in zip(quantities, vector, strict=True)}

    def predict_values(self, values: Mapping[str, float]) -> dict[str, Quantity]:
        output: dict[str, Quantity] = {}
        for condition in self.case.conditions:
            predicted = self.predictor.predict_values(values, condition, self.times[condition])
            for column, series in enumerate(s for s in self.case.series if s.condition_id == condition):
                output[series.series_id] = Q_(predicted[self.indices[series.series_id], column], series.units)
        return output

    def predict(self, parameters: ParameterSet) -> dict[str, Quantity]:
        vector = [float(parameters.require_quantity(self.log_symbol(t.quantity)).magnitude) for t in self.targets]
        return self.predict_values(self.values_from_vector(vector, [t.quantity for t in self.targets]))

    def scaled_residuals(
        self,
        vector: np.ndarray,
        quantities: Sequence[str],
        observations: Mapping[str, Quantity],
        scales: Mapping[str, Quantity] | None,
    ) -> np.ndarray:
        predictions = self.predict_values(self.values_from_vector(list(vector), quantities))
        return residuals_between(predictions, observations, residual_scales=scales).flattened_scaled()

    def residual_report(self, parameters: ParameterSet, scales: Mapping[str, Quantity] | None) -> list[dict[str, Any]]:
        predictions = self.predict(parameters)
        output: list[dict[str, Any]] = []
        for series in self.case.series:
            predicted = np.asarray(predictions[series.series_id].magnitude, dtype=float)
            observed = np.asarray([point.value for point in series.points], dtype=float)
            residual = predicted - observed
            output.append(
                {
                    "series_id": series.series_id,
                    "condition_id": series.condition_id,
                    "observable": series.observable,
                    "units": series.units,
                    "time_units": series.time_units,
                    "rmse": float(np.sqrt(np.mean(residual**2))),
                    "points": [
                        {
                            "row": point.row,
                            "time": point.time,
                            "observed": point.value,
                            "predicted": float(predicted[index]),
                            "residual": float(residual[index]),
                            "sd": point.sd,
                            "standardized_residual": (
                                None if scales is None or point.sd is None else float(residual[index] / point.sd)
                            ),
                        }
                        for index, point in enumerate(series.points)
                    ],
                }
            )
        return output


def _config_factory(
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord,
    ids: tuple[str, str, str],
    records: Mapping[str, ParameterRecord],
) -> Any:
    """Rebuild the case's assembled config with candidate values for the fitted symbols.

    The config is built by the same registry assembler a virtual experiment
    uses, from the records the screen resolves, so a candidate value reaches
    every place the template binds its symbol.
    """

    def factory(values: Mapping[str, float]) -> ModelConfig:
        replaced = dict(records)
        for role, record in records.items():
            if record.parameter_symbol in values:
                replaced[role] = replace(record, value=replace(record.value, value=float(values[record.parameter_symbol])))
        data = build_registry_process_config_data(
            registry=registry,
            compatibility=compatibility,
            fungus_id=ids[0],
            substrate_id=ids[1],
            environment_id=ids[2],
            parameter_records=replaced,
            output_directory=None,
        )
        return ModelConfig.from_mapping(data)

    return factory


def _log_parameter(symbol: str, value: float, target: _FitTarget, *, label: str) -> Parameter:
    return Parameter(
        name=f"natural log of {target.quantity} in {target.units} ({label})",
        symbol=symbol,
        value=float(value),
        units="dimensionless",
        uncertainty=None,
        source=f"fit_user_dataset {label}: {_number_text(math.exp(value))} {target.units} ({target.initial_source if label == 'starting value' else 'caller-supplied bounds'})",
        confidence_level="unknown",
        notes=f"Optimizer {label} in natural-log space; not an observation.",
        measurement_method="fit_user_dataset configuration",
    )


def _objective_text(error_model: str, case: _FitCase) -> str:
    if error_model == "sd_weighted":
        return (
            "sum over the time-course observations of ((simulated - observed) / sd)^2, each observation divided by "
            "the standard deviation reported with it; independent Gaussian errors with those standard deviations "
            "are assumed"
        )
    units = case.series[0].units
    return (
        f"sum over the time-course observations of (simulated - observed)^2 in {units}, unweighted: chosen "
        "explicitly with error_model='unweighted'; equal error variance for every observation is assumed and the "
        "residual variance is estimated from the residuals"
    )


def _convergence(fit: LeastSquaresCalibrationResult) -> dict[str, Any]:
    metadata = dict(fit.optimizer_metadata)
    return {
        "success": fit.success,
        "message": fit.message,
        "cost": fit.cost,
        "objective": None if fit.cost is None else 2.0 * fit.cost,
        "jacobian_rank": fit.jacobian_rank,
        "optimizer": metadata,
    }


def _profile_identifiability(
    *,
    fit: LeastSquaresCalibrationResult,
    problem: _FitProblem,
    targets: Sequence[_FitTarget],
    center: np.ndarray,
    observations: Mapping[str, Quantity],
    scales: Mapping[str, Quantity],
    confidence_level: float,
    profile_points: int,
    diff_step: float,
    max_nfev: int | None,
) -> tuple[list[FittedQuantity], dict[str, Any]]:
    """Profile each fitted quantity on a log grid across its bounds, then bisect each threshold crossing.

    The grid holds ``profile_points`` values spanning the bounds plus the
    optimum. Where the profile crosses the threshold between two grid values,
    the crossing is bisected with further profile evaluations, so an interval
    limit is never interpolated across a coarse grid step (a profile can be
    flat and then rise steeply).
    """

    threshold = float(chi2.ppf(confidence_level, df=1))

    def evaluate(symbol: str, values: Sequence[float]) -> ProfileLikelihoodResult:
        return profile_likelihood(
            result=fit,
            predict=problem.predict,
            observations=observations,
            residual_scales=scales,
            grids={symbol: Q_(np.asarray(values, dtype=float), "dimensionless")},
            source=_PROFILE_SOURCE,
            max_nfev=max_nfev,
            diff_step=diff_step,
        )

    fitted: list[FittedQuantity] = []
    method = (
        f"profile likelihood, delta chi-square threshold {threshold:.4g} (chi-square, 1 degree of freedom, "
        f"{confidence_level:g})"
    )
    profiles: dict[str, Any] = {}
    warnings: list[str] = []
    reference: float | None = None
    for index, target in enumerate(targets):
        symbol = problem.log_symbol(target.quantity)
        bounds = (math.log(target.lower), math.log(target.upper))
        optimum = float(center[index])
        grid = np.unique(np.clip([*np.linspace(*bounds, profile_points).tolist(), optimum], *bounds))
        coarse = evaluate(symbol, grid.tolist())
        reference = coarse.reference_chi_squared
        points = list(coarse.profiles[symbol])
        notes = list(coarse.warnings)
        for outward in (-1.0, 1.0):
            bracket = _threshold_bracket(points, optimum, threshold, outward)
            for _ in range(FIT_PROFILE_BISECTION_STEPS if bracket is not None else 0):
                assert bracket is not None
                middle = 0.5 * (bracket[0] + bracket[1])
                extra = evaluate(symbol, [middle])
                point = extra.profiles[symbol][0]
                points.append(point)
                notes.extend(warning for warning in extra.warnings if warning not in notes)
                if not point["success"] or point["delta_chi_squared"] is None:
                    break
                bracket = (bracket[0], middle) if float(point["delta_chi_squared"]) > threshold else (middle, bracket[1])
        points.sort(key=lambda point: point["value"])
        verdict, interval, reason = _profile_verdict(points, notes, symbol, optimum, threshold, bounds)
        fitted.append(_fitted_quantity(problem, target, optimum, verdict, method, interval, reason))
        warnings.extend(warning for warning in notes if warning not in warnings)
        profiles[target.quantity] = {
            "symbol": symbol,
            "units": target.units,
            "points": [
                {
                    "value": float(math.exp(point["value"])),
                    "log_value": point["value"],
                    "chi_squared": point["chi_squared"],
                    "delta_chi_squared": point["delta_chi_squared"],
                    "success": point["success"],
                    "nuisance_values": None
                    if point["nuisance_parameters"] is None
                    else {name: float(math.exp(value)) for name, value in point["nuisance_parameters"].items()},
                    "message": point.get("message"),
                }
                for point in points
            ],
        }
    return fitted, {
        "method": "profile_likelihood",
        "method_source": "https://doi.org/10.1093/bioinformatics/btp358",
        "confidence_level": confidence_level,
        "delta_chi_squared_threshold": threshold,
        "threshold_source": "chi-square quantile with one degree of freedom at the confidence level (Raue et al. 2009)",
        "reference_chi_squared": reference,
        "bisection_steps": FIT_PROFILE_BISECTION_STEPS,
        "rule": (
            "a side of a quantity is constrained when, moving outward from the optimum within the bounds, the "
            "profile's delta chi-square exceeds the threshold before any failed point; identified needs both sides, "
            "bounded_above_only and bounded_below_only one side, not_identified_within_bounds neither; a profile "
            "point better than the fit leaves the optimum unestablished (not identified). Each crossing between "
            "grid values is bisected with further profile evaluations and the limit interpolated linearly in log "
            "space inside the final bracket. Verdicts and intervals are conditional on the bounds of the other "
            "fitted quantities, which are refitted at every profile point."
        ),
        "noise_model": "independent Gaussian errors with the sd values reported in timecourse.csv",
        "claim_boundary": (
            "Conditional on the noise model, the bounds and a finite grid with local refits; no global "
            "identifiability claim."
        ),
        "warnings": warnings,
        "profiles": profiles,
    }


def _threshold_bracket(
    points: Sequence[Mapping[str, Any]], optimum: float, threshold: float, outward: float
) -> tuple[float, float] | None:
    """The last value under the threshold and the first above it, moving outward from the optimum."""

    side = sorted(
        (point for point in points if (point["value"] - optimum) * outward > 0.0),
        key=lambda point: abs(point["value"] - optimum),
    )
    inside = optimum
    for point in side:
        if not point["success"] or point["delta_chi_squared"] is None:
            return None
        if float(point["delta_chi_squared"]) > threshold:
            return inside, float(point["value"])
        inside = float(point["value"])
    return None


def _fisher_standard_errors(local: Mapping[str, Any]) -> np.ndarray | None:
    """Local standard errors in log space from the Fisher information, when it has full rank."""

    eigenvalues = np.asarray(local["eigenvalues"], dtype=float)
    if int(local["practical_rank"]) < eigenvalues.size or np.any(eigenvalues <= 0.0):
        return None
    vectors = np.asarray(local["eigenvectors_by_column"], dtype=float)
    inverse = vectors @ np.diag(1.0 / eigenvalues) @ vectors.T
    return np.sqrt(np.maximum(np.diag(inverse), 0.0))


def _profile_verdict(
    points: Sequence[Mapping[str, Any]],
    warnings: Sequence[str],
    symbol: str,
    center: float,
    threshold: float,
    bounds: tuple[float, float],
) -> tuple[str, tuple[float, float] | None, str]:
    if any(warning.startswith(f"{symbol}=") and "improves" in warning for warning in warnings):
        return (
            FIT_NOT_IDENTIFIED,
            None,
            "the profile found a better fit than the optimizer, so the optimum is not established; refit from other "
            "starting values.",
        )

    def first_crossing(side: list[Mapping[str, Any]]) -> tuple[float | None, bool]:
        previous_value, previous_delta = center, 0.0
        for point in side:
            if not point["success"] or point["delta_chi_squared"] is None:
                return None, True
            delta = float(point["delta_chi_squared"])
            if delta > threshold:
                span = delta - previous_delta
                fraction = 1.0 if span <= 0.0 else (threshold - previous_delta) / span
                return previous_value + fraction * (float(point["value"]) - previous_value), False
            previous_value, previous_delta = float(point["value"]), max(delta, 0.0)
        return None, False

    below = sorted((p for p in points if p["value"] < center), key=lambda p: p["value"], reverse=True)
    above = sorted((p for p in points if p["value"] > center), key=lambda p: p["value"])
    low, low_failed = first_crossing(below)
    high, high_failed = first_crossing(above)
    failed = (
        " A profile point failed before the threshold on a side, so that side is not established."
        if (low_failed or high_failed)
        else ""
    )
    if low is not None and high is not None:
        return (
            FIT_IDENTIFIED,
            (math.exp(low), math.exp(high)),
            "the profile exceeds the threshold on both sides within the bounds.",
        )
    if high is not None:
        return (
            BOUNDED_ABOVE_ONLY,
            (math.exp(bounds[0]), math.exp(high)),
            "the data give an upper limit only; below the optimum the profile stays under the threshold down to the "
            f"lower bound.{failed}",
        )
    if low is not None:
        return (
            BOUNDED_BELOW_ONLY,
            (math.exp(low), math.exp(bounds[1])),
            "the data give a lower limit only; above the optimum the profile stays under the threshold up to the "
            f"upper bound.{failed}",
        )
    return FIT_NOT_IDENTIFIED, None, f"the profile stays under the threshold across the bounds on both sides.{failed}"


def _local_identifiability(
    *,
    fit: LeastSquaresCalibrationResult,
    problem: _FitProblem,
    targets: Sequence[_FitTarget],
    center: np.ndarray,
    local: Mapping[str, Any],
    confidence_level: float,
) -> tuple[list[FittedQuantity], dict[str, Any]]:
    assert fit.training_residuals is not None
    residual = fit.training_residuals.flattened_scaled()
    dof = residual.size - len(targets)
    variance = float(residual @ residual) / dof
    z_value = float(norm.ppf(0.5 + confidence_level / 2.0))
    standard_errors = _fisher_standard_errors(local)
    method = f"local information with linearized intervals (z {z_value:.4g}, {confidence_level:g}), residual variance from the residuals"
    fitted: list[FittedQuantity] = []
    for index, target in enumerate(targets):
        lower, upper = math.log(target.lower), math.log(target.upper)
        if standard_errors is None:
            fitted.append(
                _fitted_quantity(
                    problem,
                    target,
                    float(center[index]),
                    FIT_NOT_IDENTIFIED,
                    method,
                    None,
                    "the local information matrix is rank deficient, so the time courses do not separate the fitted "
                    "quantities.",
                )
            )
            continue
        half = z_value * math.sqrt(variance) * float(standard_errors[index])
        low, high = float(center[index]) - half, float(center[index]) + half
        low_inside, high_inside = low > lower, high < upper
        if low_inside and high_inside:
            verdict, interval, reason = FIT_IDENTIFIED, (math.exp(low), math.exp(high)), "the linearized interval lies within the bounds."
        elif high_inside:
            verdict, interval, reason = BOUNDED_ABOVE_ONLY, (target.lower, math.exp(high)), "the linearized interval reaches the lower bound."
        elif low_inside:
            verdict, interval, reason = BOUNDED_BELOW_ONLY, (math.exp(low), target.upper), "the linearized interval reaches the upper bound."
        else:
            verdict, interval, reason = FIT_NOT_IDENTIFIED, None, "the linearized interval reaches both bounds."
        fitted.append(_fitted_quantity(problem, target, float(center[index]), verdict, method, interval, reason))
    return fitted, {
        "method": "local_information",
        "confidence_level": confidence_level,
        "z_value": z_value,
        "residual_variance": variance,
        "residual_degrees_of_freedom": dof,
        "rule": (
            "practical rank of the Fisher information of the raw residuals in log space; with full rank, the "
            "linearized interval ln(value) +/- z * sqrt(residual variance * inverse information) inside both bounds "
            "is identified, inside one bound only one-sided, otherwise not identified"
        ),
    }


def _fitted_quantity(
    problem: _FitProblem,
    target: _FitTarget,
    log_value: float,
    verdict: str,
    method: str,
    interval: tuple[float, float] | None,
    reason: str,
) -> FittedQuantity:
    return FittedQuantity(
        quantity=target.quantity,
        symbol=problem.symbols[target.quantity],
        value=float(math.exp(log_value)),
        units=target.units,
        lower_bound=target.lower,
        upper_bound=target.upper,
        initial=target.initial,
        initial_source=target.initial_source,
        identifiability=verdict,
        identifiability_method=method,
        interval=interval,
        reason=reason,
    )


def _fitted_files(
    dataset: UserDataset,
    case: _FitCase,
    fitted: Sequence[FittedQuantity],
    report: Mapping[str, Any],
    *,
    allow_unidentified: bool,
) -> dict[str, bytes]:
    report_bytes = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    rows = sorted(int(row) for row in report["timecourse_rows"])
    method = (
        f"fit_user_dataset: {report['error_model']} least squares on ln(value) to {TIMECOURSE_TABLE} rows "
        f"{_rows_text(rows)} at conditions {', '.join(case.conditions)}; see {FIT_REPORT_FILE}"
    )
    source = (
        f"Fitted to the time courses of user dataset {dataset.dataset_id} (sha256 {dataset.digest}); in-sample "
        "estimate, not a measurement"
    )
    drop, new_rows = _replacement_rows(
        dataset,
        case,
        {item.quantity: (item.value, item.units) for item in fitted},
        evidence_type=FITTED_EVIDENCE_TYPE,
        method=method,
        source=source,
    )
    block = {
        "kind": FIT_BLOCK_KIND,
        "method": FIT_METHOD,
        "objective": report["objective"],
        "error_model": report["error_model"],
        "input_dataset_id": dataset.dataset_id,
        "input_dataset_digest": dataset.digest,
        "report_file": FIT_REPORT_FILE,
        "report_sha256": hashlib.sha256(report_bytes).hexdigest(),
        "case": {"strain_id": case.strain_id, "enzyme_class": case.class_key, "substrate_id": case.substrate_id},
        "conditions": list(case.conditions),
        "timecourse_rows": rows,
        "quantities": [
            {
                "quantity": item.quantity,
                "value": float(item.value),
                "units": item.units,
                "bounds": [item.lower_bound, item.upper_bound],
                "initial": item.initial,
                "identifiability": item.identifiability,
                "identifiability_method": item.identifiability_method,
                "interval": None if item.interval is None else [float(item.interval[0]), float(item.interval[1])],
            }
            for item in fitted
        ],
        "allow_unidentified": allow_unidentified,
        "claim_boundary": FIT_CLAIM_BOUNDARY,
    }
    manifest = {**dict(dataset.manifest), "dataset_id": report["fitted_dataset_id"], "fit": block}
    return _dataset_files_with_kinetics(
        dataset,
        drop_rows=drop,
        new_rows=new_rows,
        manifest=manifest,
        extra_files={FIT_REPORT_FILE: report_bytes},
    )


def _rows_text(rows: Sequence[int]) -> str:
    """Compact spreadsheet line ranges such as ``2-9, 12``."""

    ordered = sorted(set(rows))
    parts: list[str] = []
    start = previous = ordered[0] if ordered else 0
    for row in ordered[1:]:
        if row == previous + 1:
            previous = row
            continue
        parts.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = row
    if ordered:
        parts.append(str(start) if start == previous else f"{start}-{previous}")
    return ", ".join(parts)


__all__ = [
    "FIT_CLAIM_BOUNDARY",
    "FIT_DIFFERENCE_STEP",
    "FIT_METHOD",
    "FIT_REPORT_FILE",
    "FittedQuantity",
    "TIMECOURSE_COMPARISON_FILE",
    "TIMECOURSE_COMPARISON_NOTE",
    "TIMECOURSE_COMPARISON_TABLE",
    "TimecourseComparison",
    "UserDataFitError",
    "UserDatasetFit",
    "compare_with_timecourses",
    "fit_user_dataset",
]
