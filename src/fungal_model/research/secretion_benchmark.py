"""Bounded empirical protein-output comparison, separate from catalytic activity.

This is a conditional growth-associated effective ratio, qP = r * mu. At one
growth rate it is only a ratio calibration: the dynamic mechanism and a
non-growth intercept cannot be identified. Reported SDs are preserved, not
used as independent likelihood weights. No confidence interval is inferred.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from fungal_model.core.parameters import Parameter
from fungal_model.core.provenance import ProvenanceError, has_text
from fungal_model.core.units import Quantity, assert_compatible, require_quantity
from fungal_model.resources import package_data_path

DATA_PATH = "data/benchmarks/jorgensen_2009_secretion"


def _array(value: Quantity, units: str, name: str) -> np.ndarray:
    result = np.asarray(assert_compatible(require_quantity(value, name=name), units, name=name).magnitude, dtype=float)
    if result.ndim != 1 or not np.isfinite(result).all() or np.any(result < 0):
        raise ValueError(f"{name} must be a finite, nonnegative one-dimensional array.")
    return result


@dataclass(frozen=True)
class ProteinOutputFit:
    protein_per_biomass: Parameter
    training_conditions: tuple[str, ...]
    residual_sum_squares: float

    def predict(self, growth_rates: Quantity) -> np.ndarray:
        """Return g protein/(g dry biomass h), conditional on supplied growth."""
        mu = _array(growth_rates, "1/h", "growth_rates")
        assert self.protein_per_biomass.quantity is not None
        return mu * float(self.protein_per_biomass.quantity.to("dimensionless").magnitude)

    def to_dict(self) -> dict[str, Any]:
        return {"protein_per_biomass": self.protein_per_biomass.to_dict(),
                "training_conditions": list(self.training_conditions), "fitted_parameter_count": 1,
                "residual_degrees_of_freedom": len(self.training_conditions)-1,
                "residual_sum_squares_per_h_squared": self.residual_sum_squares,
                "objective": "Unweighted zero-intercept least squares, g protein/(g dry biomass h)",
                "identifiability": "An effective ratio at supplied growth rates; the growth-associated mechanism, "
                    "a non-growth intercept and protein losses are not identified.", "uncertainty": "Unknown"}


def fit_protein_output(*, growth_rates: Quantity, protein_output: Quantity,
                       condition_ids: Sequence[str], source: str) -> ProteinOutputFit:
    if not has_text(source):
        raise ProvenanceError("Protein-output calibration requires source provenance.")
    mu = _array(growth_rates, "1/h", "growth_rates")
    qp = _array(protein_output, "g/g/h", "protein_output")
    if mu.size == 0 or mu.shape != qp.shape or len(condition_ids) != mu.size or not np.any(mu > 0):
        raise ValueError("Matched nonempty arrays with at least one positive growth rate are required.")
    if any(not has_text(n) for n in condition_ids) or len(set(condition_ids)) != len(condition_ids):
        raise ValueError("Training condition IDs must be nonempty and unique.")
    ratio = float(np.dot(mu, qp) / np.dot(mu, mu))
    parameter = Parameter("effective extracellular protein per new dry biomass", "r_PX", ratio, "g/g", None,
        f"Conditional protein-output calibration to {', '.join(condition_ids)}; {source}", "low",
        "Total extracellular protein, not active enzyme. qP = r * mu is an explicit hypothesis. "
        "Biosynthesis may differ from net output; activity, composition, yields and uncertainty remain unidentified.")
    return ProteinOutputFit(parameter, tuple(condition_ids), float(np.sum((ratio*mu-qp)**2)))


def load_secretion_data(root: Path | None = None) -> dict[str, Any]:
    directory = package_data_path(DATA_PATH) if root is None else root / DATA_PATH
    manifest = json.loads((directory / "manifest.json").read_text())
    for entry in manifest["files"]:
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Manifest path must remain within the dataset.")
        content = (directory / relative).read_bytes()
        if len(content) != entry["bytes"] or hashlib.sha256(content).hexdigest() != entry["sha256"]:
            raise ValueError(f"Secretion source/extract checksum mismatch: {relative}")
    if not any(e["path"] == "observations.json" for e in manifest["files"]):
        raise ValueError("Observations must be bound by the manifest.")
    return json.loads((directory / "observations.json").read_text())


def strain_holdouts(data: dict[str, Any]) -> dict[str, Any]:
    """Retrospectively hold out both carbon conditions of an entire strain.

    Carbon-source labels and nominal growth rates are allowed predictors. The
    target strain's measurements are never used for calibration. Two strains
    in one laboratory are not an independent prospective replication.
    """
    from fungal_model.core.units import Q_

    records = data["records"]
    if len({r["id"] for r in records}) != len(records):
        raise ValueError("Condition IDs must be unique.")
    if len({r["strain"] for r in records}) < 2:
        raise ValueError("Strain holdouts require at least two strains.")
    predictions = []
    for target in records:
        training_strains = [r for r in records if r["strain"] != target["strain"]]
        for mode in ("pooled", "carbon_source_conditioned"):
            train = [r for r in training_strains if mode == "pooled" or r["carbon_source"] == target["carbon_source"]]
            if not train:
                raise ValueError("A held-out carbon source has no training coverage.")
            fit = fit_protein_output(growth_rates=Q_([r["growth_rate_per_h"] for r in train], "1/h"),
                protein_output=Q_([r["extracellular_protein_mg_gDW_h"]["value"] for r in train], "mg/g/h"),
                condition_ids=[r["id"] for r in train], source=f"doi:{data['doi']}, Table 1")
            predictions.append({"target_id": target["id"], "strain": target["strain"],
                "carbon_source": target["carbon_source"], "mode": mode,
                "observed_mg_gDW_h": target["extracellular_protein_mg_gDW_h"]["value"],
                "observed_sd_mg_gDW_h": target["extracellular_protein_mg_gDW_h"]["sd"],
                "predicted_mg_gDW_h": float(fit.predict(Q_([target["growth_rate_per_h"]], "1/h"))[0]*1000),
                "fit": fit.to_dict()})
    metrics = {mode: float(np.sqrt(np.mean([(p["predicted_mg_gDW_h"]-p["observed_mg_gDW_h"])**2
                                          for p in predictions if p["mode"] == mode])))
               for mode in ("pooled", "carbon_source_conditioned")}
    return {"predictions": predictions, "rmse_mg_gDW_h": metrics,
            "split": "Leave an entire strain out, including both sequential carbon-source conditions",
            "comparison_parameter_counts": {"pooled": 1, "carbon_source_conditioned": 2},
            "claim": "Retrospective conditional total-protein-output component test; source-conditioned model is more flexible. "
                     "Only two strain folds; no independent laboratory, confidence interval or whole-fungus validation."}


__all__ = ["ProteinOutputFit", "fit_protein_output", "load_secretion_data", "strain_holdouts"]
