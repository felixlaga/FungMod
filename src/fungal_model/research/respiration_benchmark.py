"""Small-sample Pirt calibration and checksum-bound public respiration data.

Calibration is conditional on supplied growth rates. Quoted source error bars
have no supplied covariance and their statistical meaning is not established
for every table: no likelihood, confidence interval, or significance is claimed.
Reconciled measurements are kept distinct from unreconciled measurements.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from scipy.optimize import nnls

from fungal_model.chemistry import ElementalComposition, MacrochemicalBalance, MacrochemicalSpecies
from fungal_model.core.parameters import Parameter
from fungal_model.core.provenance import ProvenanceError, has_text
from fungal_model.core.units import Quantity, assert_compatible, require_quantity
from fungal_model.resources import package_data_path
from fungal_model.fungi.respiration import RespiratoryGrowthModel

DATA_PATH = "data/benchmarks/lameiras_respiration"


def _rates(value: Quantity, name: str) -> np.ndarray:
    array = np.asarray(assert_compatible(require_quantity(value, name=name), "1/hour", name=name).magnitude, dtype=float)
    if array.ndim != 1 or not np.isfinite(array).all() or np.any(array < 0):
        raise ValueError(f"{name} must be a finite nonnegative one-dimensional rate array.")
    return array


@dataclass(frozen=True)
class PirtFit:
    true_yield: Parameter
    maintenance_demand: Parameter
    training_conditions: tuple[str, ...]
    residual_sum_squares: float
    include_maintenance: bool

    def predict(self, growth_rates: Quantity) -> np.ndarray:
        mu = _rates(growth_rates, "growth_rates")
        assert self.true_yield.quantity is not None and self.maintenance_demand.quantity is not None
        return mu / float(self.true_yield.quantity.to("dimensionless").magnitude) + float(
            self.maintenance_demand.quantity.to("1/hour").magnitude)

    def to_dict(self) -> dict[str, Any]:
        return {"true_yield": self.true_yield.to_dict(), "maintenance_demand": self.maintenance_demand.to_dict(),
                "training_conditions": list(self.training_conditions), "include_maintenance": self.include_maintenance,
                "residual_sum_squares_per_hour_squared": self.residual_sum_squares,
                "fitted_parameter_count": 2 if self.include_maintenance else 1,
                "objective": "Unweighted nonnegative least squares in substrate uptake per biomass per hour",
                "uncertainty": "Unknown; source errors/covariances do not establish a likelihood."}


def fit_pirt(*, growth_rates: Quantity, substrate_uptake: Quantity, condition_ids: Sequence[str],
             source: str, include_maintenance: bool) -> PirtFit:
    """Fit qS = mu/Y + m using only caller-selected training conditions.

    At least one residual degree of freedom and full design rank are required.
    No reported all-condition literature fit is used as a prior/initial value.
    """
    if not has_text(source):
        raise ProvenanceError("Pirt calibration requires a source.")
    mu, uptake = _rates(growth_rates, "growth_rates"), _rates(substrate_uptake, "substrate_uptake")
    count = 2 if include_maintenance else 1
    if mu.shape != uptake.shape or len(condition_ids) != mu.size or mu.size <= count:
        raise ValueError("Matched arrays and at least one residual degree of freedom are required.")
    if any(not has_text(n) for n in condition_ids) or len(set(condition_ids)) != len(condition_ids):
        raise ValueError("Training condition IDs must be nonempty and unique.")
    design = np.column_stack((mu, np.ones(mu.size))) if include_maintenance else mu[:, None]
    if np.linalg.matrix_rank(design) < count:
        raise ValueError("The growth-rate design is rank deficient.")
    parameters, residual_norm = nnls(design, uptake)
    if parameters[0] <= 0:
        raise ValueError("No finite positive true yield is identified by these observations.")
    provenance = f"Unweighted Pirt fit to {', '.join(condition_ids)}; {source}"
    notes = "Conditional on supplied growth rates; mol biomass formula/mol substrate basis. Calibration, not validation."
    true_yield = Parameter("true biomass yield", "Y_XS", float(1 / parameters[0]), "dimensionless", None,
                           provenance, "low", notes)
    maintenance = Parameter("non-growth substrate maintenance", "m_S", float(parameters[1]) if include_maintenance else 0.,
                            "1/hour", None, provenance if include_maintenance else
                            "Explicit zero-maintenance comparison hypothesis; " + source, "low", notes)
    return PirtFit(true_yield, maintenance, tuple(condition_ids), float(residual_norm ** 2), include_maintenance)


def load_respiration_data(root: Path | None = None) -> dict[str, Any]:
    """Load the preserved extracts only after every source/extract hash passes."""
    directory = package_data_path(DATA_PATH) if root is None else root / DATA_PATH
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Source manifest paths must remain inside the dataset.")
        path = directory / relative
        content = path.read_bytes()
        if len(content) != entry["bytes"] or hashlib.sha256(content).hexdigest() != entry["sha256"]:
            raise ValueError(f"Respiration source/extract checksum mismatch: {relative}")
    if not any(e["path"] == "observations.json" for e in manifest["files"]):
        raise ValueError("Observation extract is not bound by the manifest.")
    return json.loads((directory / "observations.json").read_text(encoding="utf-8"))


def lameiras_glucose_model(fit: PirtFit, data: dict[str, Any]) -> RespiratoryGrowthModel:
    """Bounded study assembly; no species-specific logic enters core chemistry.

    The reported average CHNO biomass formula omits minor ash/P/S; neutral
    biomass and ammonium assimilation are explicit macrochemical assumptions.
    This deliberately omits unresolved excreted organic matter. Its composition
    was not identified, so it cannot honestly be assigned an O2/energy balance.
    """
    source = "Lameiras et al. (2015), doi:10.1007/s11306-015-0781-z, Table 2 and biomass composition paragraph."
    chemical = "Chemical identity of glucose, ammonium, oxygen, carbon dioxide, water and proton."
    species = []
    for name, formula, charge in (("glucose", "C6H12O6", 0), ("ammonium", "NH4", 1),
                                 ("oxygen", "O2", 0), ("biomass", None, 0),
                                 ("carbon_dioxide", "CO2", 0), ("water", "H2O", 0), ("proton", "H", 1)):
        composition = (ElementalComposition.from_formula(formula, source=chemical) if formula else
                       ElementalComposition.from_elements(data["lameiras_2015"]["biomass_composition"], source=source,
                           notes="Reported mean CHNO formula; minor ash/P/S not represented; no condition-specific composition uncertainty."))
        species.append(MacrochemicalSpecies(name, composition, charge,
                        "Explicit neutral empirical biomass convention; " + source if name == "biomass" else chemical))
    balance = MacrochemicalBalance("A. niger NW185 glucose/ammonium respiration hypothesis", tuple(species), source)
    return RespiratoryGrowthModel(balance, "glucose", "biomass", fit.true_yield, fit.maintenance_demand,
        "Pirt growth/maintenance allocation with complete oxidation and no resolved organic secretion; " + source)


__all__ = ["PirtFit", "fit_pirt", "load_respiration_data", "lameiras_glucose_model"]
