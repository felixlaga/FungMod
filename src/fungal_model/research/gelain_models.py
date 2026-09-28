"""Source-scoped culture model candidates with assay-specific observations.

Sources: Gelain et al. doi:10.1016/j.cesx.2020.100085, Eqs 2-10 and deposited
model doi:10.17632/shd3wcczsr.2. New hydrolysis and retained-mass candidates are
explicit hypotheses, not validated physiology. Activities stay in assay units.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
from scipy.integrate import solve_ivp

from fungal_model.core.parameters import ParameterSet
from fungal_model.core.provenance import has_text
from fungal_model.core.units import Q_, Quantity, assert_compatible, ureg
from fungal_model.research.gelain_culture import CultureBenchmarkError, CultureDesign, source_projection_rates

# These dimensions deliberately cannot convert to enzyme mass, molarity, or to
# each other. The experiment's two assays measure different responses.
ureg.define("gelain_fpu = [gelain_filter_paper_activity]")
ureg.define("gelain_beta_u = [gelain_pnpg_activity]")
OBSERVABLE_UNITS = {"biomass": "gram/liter", "substrate": "gram/liter",
                    "cellulase_activity": "gelain_fpu/liter", "beta_glucosidase_activity": "gelain_beta_u/liter"}
DISPLAY_UNITS = {"biomass": "g/L", "substrate": "g/L", "cellulase_activity": "FPU/L",
                 "beta_glucosidase_activity": "U/L (pNPG assay)"}
BASE = {"mu": "1/hour", "K": "gram/liter", "Y": "dimensionless", "kd": "1/hour"}
ACTIVITY = {"qF": "gelain_fpu/gram/hour", "kF": "1/hour", "qB": "gelain_beta_u/gram/hour", "kB": "1/hour"}
RETAINED = {"f_retained": "dimensionless", "k_clear": "1/hour", "initial_retained_fraction": "dimensionless"}
SOURCE_GROWTH = {"mu": "1/hour", "K": "gram/liter", "Xmax": "gram/liter", "d": "1/hour", "alpha": "liter/gram"}
SOURCE_INDUCTION = {"Kd": "gram/liter", "k_ind": "liter/gram/hour", "Ke": "gram/liter",
                    "kda": "1/hour", "b_ind": "gram/liter"}
SOURCE_ACTIVITY = {"qF": "gelain_fpu/liter/hour", "kF": "1/hour", "KI_F": "(gram/liter)**2",
                   "Fmax": "gelain_fpu/liter", "SI_F": "gram/liter",
                   "qB": "gelain_beta_u/liter/hour", "kB": "1/hour", "KI_B": "(gram/liter)**2",
                   "Bmax": "gelain_beta_u/liter", "SI_B": "gram/liter"}
HYDROLYSIS = {"k_h": "gram/gelain_fpu/hour", "Kh": "gram/liter", "Y": "dimensionless", "kd": "1/hour",
              "K_ind": "gram/liter", **ACTIVITY}


def parameter_units(model: str, family: str) -> dict[str, str]:
    if family not in {"glycerol", "cellulose"}:
        raise CultureBenchmarkError("Only the named Gelain culture families are supported.")
    if model in {"effective", "retained"}:
        units = dict(BASE)
        if family == "cellulose":
            units.update(ACTIVITY)
    elif model == "published":
        units = dict(SOURCE_GROWTH)
        if family == "cellulose":
            units.update(SOURCE_INDUCTION | SOURCE_ACTIVITY)
    elif model in {"hydrolysis", "hydrolysis_retained"} and family == "cellulose":
        units = dict(HYDROLYSIS)
    else:
        raise CultureBenchmarkError(f"Unsupported model/family: {model}/{family}")
    if model in {"retained", "hydrolysis_retained"}:
        units.update(RETAINED)
    return units


@dataclass(frozen=True)
class CultureMeasurements:
    design: CultureDesign
    observations: Mapping[str, Quantity]
    initial_activities: Mapping[str, Quantity]
    source: str

    def __post_init__(self) -> None:
        keys = tuple(OBSERVABLE_UNITS) if self.design.family == "cellulose" else ("biomass", "substrate")
        if set(self.observations) != set(keys) or not has_text(self.source):
            raise CultureBenchmarkError("Each condition needs exactly its supported assays and provenance.")
        for key in keys:
            values = np.asarray(assert_compatible(self.observations[key], OBSERVABLE_UNITS[key]).magnitude)
            if values.shape != np.asarray(self.design.times.magnitude).shape or not np.all(np.isfinite(values)):
                raise CultureBenchmarkError("Observation arrays must match time and be finite.")
        if set(self.initial_activities) != set(keys).difference({"biomass", "substrate"}):
            raise CultureBenchmarkError("Initial activities must be explicitly supplied for every activity assay.")
        for key, value in self.initial_activities.items():
            number = np.asarray(assert_compatible(value, OBSERVABLE_UNITS[key]).magnitude)
            if number.ndim or not np.isfinite(number) or number < 0:
                raise CultureBenchmarkError("Initial activities must be finite nonnegative scalar assay quantities.")

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(k for k in OBSERVABLE_UNITS if k in self.observations)

    @property
    def values(self) -> np.ndarray:
        return np.column_stack([self.observations[k].to(OBSERVABLE_UNITS[k]).magnitude for k in self.names])


@dataclass(frozen=True)
class CultureModelPrediction:
    times: Quantity
    observables: Mapping[str, Quantity]
    retained_dry_mass: Quantity | None
    model: str
    hypothesis_source: str
    solver: Mapping[str, object]
    maturity: str = "exploratory_software_tested"

    @property
    def values(self) -> np.ndarray:
        return np.column_stack([v.to(OBSERVABLE_UNITS[k]).magnitude for k, v in self.observables.items()])


def _integrate(model: str, family: str, times: np.ndarray, initial: np.ndarray, p: Mapping[str, float], *,
               method: str, rtol: float, atol: float) -> tuple[np.ndarray, np.ndarray | None, dict]:
    """Canonical numeric kernel shared by public simulation and calibration."""
    if method not in {"LSODA", "DOP853", "Radau", "BDF"} or not 0 < rtol < 1 or not 0 < atol < 1:
        raise CultureBenchmarkError("Explicit supported solver and finite positive tolerances are required.")
    if not np.isfinite(rtol + atol):
        raise CultureBenchmarkError("Solver tolerances must be finite.")
    retained = model in {"retained", "hydrolysis_retained"}
    cellulose = family == "cellulose"
    x0, s0 = initial[:2]
    if model == "published" and x0 > p["Xmax"]:
        raise CultureBenchmarkError("Initial biomass exceeds the source capacity.")
    if retained:
        fraction = p["initial_retained_fraction"]
        y0 = [x0*(1-fraction), s0, x0*fraction]
    elif model == "published" and cellulose:
        y0 = [x0, s0, 0.0]  # Source's A(0)=0; z=A/Amax removes an exact scale ambiguity.
    else:
        y0 = [x0, s0]
    activity_offset = len(y0)
    if cellulose:
        y0 += initial[2:].tolist()
    source_parameters = dict(p)
    if model == "published" and cellulose:
        # Amax=1 is a coordinate normalization, not a supplied biological value.
        source_parameters.update(mue=p["k_ind"], Amax=1.0, beta=p["b_ind"])

    def rhs(_time: float, state: np.ndarray) -> list[float]:
        x, s = max(float(state[0]), 0.0), max(float(state[1]), 0.0)
        if model == "published":
            rates = source_projection_rates(state, source_parameters, family=family, deposited_glycerol=False)
            if cellulose:
                z = max(float(state[2]), 0.0)
                f, b = max(float(state[3]), 0.0), max(float(state[4]), 0.0)
                # KI absorbs the source's manually selected 0.15 coefficient;
                # its value is fitted afresh, not fixed from all-condition data.
                fi = 1 + s*s/p["KI_F"] if s > p["SI_F"] else 1
                bi = 1 + s*s/p["KI_B"] if s > p["SI_B"] else 1
                rates += [p["qF"]*z*(1-f/p["Fmax"])/fi - p["kF"]*f,
                          p["qB"]*z*(1-b/p["Bmax"])/bi - p["kB"]*b]
            return rates
        if model.startswith("hydrolysis"):
            f = max(float(state[activity_offset]), 0.0)
            consumption = p["k_h"] * f * s/(s+p["Kh"])
            growth = p["Y"] * consumption
            induction = s/(s+p["K_ind"])
        else:
            growth = p["mu"] * s/(s+p["K"]) * x
            consumption = growth / p["Y"]
            induction = 1.0  # Explicit constitutive-activity null hypothesis.
        loss = p["kd"] * x
        rates = [growth-loss, -consumption]
        if retained:
            r = max(float(state[2]), 0.0)
            rates += [p["f_retained"]*loss-p["k_clear"]*r]
        if cellulose:
            f, b = max(float(state[activity_offset]), 0.0), max(float(state[activity_offset+1]), 0.0)
            rates += [p["qF"]*x*induction - p["kF"]*f, p["qB"]*x*induction - p["kB"]*b]
        return rates

    solution = solve_ivp(rhs, (0.0, float(times[-1])), y0, t_eval=times, method=method, rtol=rtol, atol=atol)
    state = np.asarray(solution.y, dtype=float)
    if not solution.success or state.shape != (len(y0), len(times)) or not np.all(np.isfinite(state)):
        raise CultureBenchmarkError(f"Invalid/incomplete culture integration: {solution.message}")
    if np.any(state < -10*atol):
        raise CultureBenchmarkError("Materially negative culture states.")
    mass = state[0] + state[2] if retained else state[0]
    columns = [mass, state[1]] + ([state[activity_offset], state[activity_offset+1]] if cellulose else [])
    return np.column_stack(columns), state[2] if retained else None, {
        "method": method, "rtol": rtol, "atol_in_canonical_observable_units": atol,
        "nfev": int(solution.nfev), "minimum_state": float(state.min()),
        "negative_roundoff_count": int(np.sum(state < 0)), "success": True}


def simulate_candidate(design: CultureDesign, initial_activities: Mapping[str, Quantity], parameters: ParameterSet, *,
                       model: str, hypothesis_source: str, method: str = "LSODA", rtol: float = 1e-8,
                       atol: float = 1e-10) -> CultureModelPrediction:
    """Predict dry mass and assay activities; no viable-biomass output is emitted."""
    if not has_text(hypothesis_source):
        raise CultureBenchmarkError("Explicit model-hypothesis provenance is required.")
    units = parameter_units(model, design.family)
    parameters.validate(require_values=True)
    if set(p.symbol for p in parameters) != set(units):
        raise CultureBenchmarkError("Exactly the model's declared parameters must be supplied.")
    p = {}
    for key, unit in units.items():
        value = np.asarray(parameters.require_quantity(key, unit).magnitude, dtype=float)
        if value.ndim or not np.isfinite(value) or value < 0:
            raise CultureBenchmarkError("Parameters must be finite nonnegative scalars.")
        p[key] = float(value)
    positive = set(units).intersection({"K", "Y", "Kh", "K_ind", "Xmax", "Kd", "Ke", "KI_F", "KI_B", "Fmax", "Bmax"})
    if any(p[k] <= 0 for k in positive) or any(p.get(k, 0) > 1 for k in ("Y", "f_retained", "initial_retained_fraction")):
        raise CultureBenchmarkError("Saturation/capacity constants must be positive and fractions at most one.")
    names = tuple(OBSERVABLE_UNITS) if design.family == "cellulose" else ("biomass", "substrate")
    if set(initial_activities) != set(names[2:]):
        raise CultureBenchmarkError("Initial assay activities must be explicit and complete.")
    initial = [float(design.initial_biomass.to("gram/liter").magnitude),
               float(design.initial_substrate.to("gram/liter").magnitude)]
    for name in names[2:]:
        value = np.asarray(assert_compatible(initial_activities[name], OBSERVABLE_UNITS[name]).magnitude)
        if value.ndim or not np.isfinite(value) or value < 0:
            raise CultureBenchmarkError("Initial activities must be finite nonnegative scalars.")
        initial.append(float(value))
    if model == "published" and design.family == "cellulose":
        if initial[2] > p["Fmax"] or initial[3] > p["Bmax"]:
            raise CultureBenchmarkError("Initial activity exceeds the source capacity.")
    times = np.asarray(design.times.to("hour").magnitude)
    values, retained, solver = _integrate(model, design.family, times, np.asarray(initial), p,
                                        method=method, rtol=rtol, atol=atol)
    return CultureModelPrediction(Q_(times, "hour"), {k: Q_(values[:, i], OBSERVABLE_UNITS[k]) for i, k in enumerate(names)},
                                  Q_(retained, "gram/liter") if retained is not None else None,
                                  model, hypothesis_source, solver)
