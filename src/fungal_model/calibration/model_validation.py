"""Validation bound to immutable model, parameters, observation law and scope.

This composes the existing raw-replicate/frozen-prediction evaluator. A passing
record describes supplied empirical evidence at tested conditions; it never
claims every point in a proposed operating range was validated or authenticates
an external review merely because a citation is supplied.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from fungal_model.calibration.independent import IndependentValidationPlan, evaluate_frozen_prediction, freeze_prediction
from fungal_model.core.parameters import Parameter
from fungal_model.core.provenance import has_text
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity
from fungal_model.data.comparison import ObservableMapping
from fungal_model.data.datasets import ExperimentDataset
from fungal_model.results import SimulationResult


def scientific_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class ScopeRange:
    lower: Quantity
    upper: Quantity

    def __post_init__(self) -> None:
        a = np.asarray(require_quantity(self.lower).magnitude, dtype=float)
        b = np.asarray(assert_compatible(self.upper, str(self.lower.units)).magnitude, dtype=float)
        if a.ndim or b.ndim or not np.isfinite(a+b) or a > b:
            raise ValueError("Scope bounds must be finite ordered scalar quantities.")

    def to_dict(self) -> dict:
        return {"lower": float(self.lower.magnitude), "upper": float(self.upper.to(self.lower.units).magnitude),
                "units": str(self.lower.units)}


@dataclass(frozen=True)
class ModelScope:
    categorical: Mapping[str, str]
    numeric: Mapping[str, ScopeRange]
    observable_units: Mapping[str, str]
    source: str
    observation_time: ScopeRange | None = None

    def __post_init__(self) -> None:
        if (not self.categorical or not self.observable_units or not has_text(self.source)
                or any(not has_text(k) or not has_text(v) for k,v in self.categorical.items())):
            raise ValueError("Scope requires explicit system labels, observables and provenance.")
        if set(self.categorical) & set(self.numeric):
            raise ValueError("Categorical and quantitative scope fields must not overlap.")
        for unit in self.observable_units.values():
            Q_(1, unit)
        if self.observation_time is not None:
            assert_compatible(self.observation_time.lower, "second")

    def check(self, categorical: Mapping[str, str], numeric: Mapping[str, Quantity]) -> None:
        if dict(categorical) != dict(self.categorical) or set(numeric) != set(self.numeric):
            raise ValueError("Conditions do not match the declared model scope exactly.")
        for key, bound in self.numeric.items():
            value = np.asarray(assert_compatible(numeric[key], str(bound.lower.units)).magnitude, dtype=float)
            if (value.ndim or not np.isfinite(value) or value < bound.lower.magnitude
                    or value > bound.upper.to(bound.lower.units).magnitude):
                raise ValueError(f"Condition {key} is outside the declared operating scope.")

    def to_dict(self) -> dict:
        return {"categorical": dict(self.categorical), "numeric": {k:v.to_dict() for k,v in self.numeric.items()},
                "observable_units": dict(self.observable_units), "source": self.source,
                "observation_time": self.observation_time.to_dict() if self.observation_time else None}

    @classmethod
    def from_dict(cls, record: Mapping[str, Any]) -> ModelScope:
        time = record.get("observation_time")
        return cls(record["categorical"], {k: ScopeRange(Q_(v["lower"],v["units"]), Q_(v["upper"],v["units"]))
                                          for k,v in record["numeric"].items()}, record["observable_units"], record["source"],
                   ScopeRange(Q_(time["lower"],time["units"]), Q_(time["upper"],time["units"])) if time else None)


def model_identity(*, model_id: str, model_version: str, equation_source: str, equation_sha256: str,
                   parameter_records: Sequence[Mapping[str, Any]], observation_model: Mapping[str, Any],
                   training_experiment_ids: Sequence[str]) -> dict:
    if not all(has_text(x) for x in (model_id, model_version, equation_source)):
        raise ValueError("Explicit model identity, version and equation source are required.")
    if len(equation_sha256) != 64 or any(c not in "0123456789abcdef" for c in equation_sha256):
        raise ValueError("Equation implementation requires a SHA-256 digest.")
    if not parameter_records or not observation_model or not training_experiment_ids:
        raise ValueError("Exact parameters, observation law and training identities are required.")
    if len(set(training_experiment_ids)) != len(training_experiment_ids) or not all(has_text(x) for x in training_experiment_ids):
        raise ValueError("Training experiment identities must be nonblank and unique.")
    symbols = []
    for r in parameter_records:
        if not r.get("source") or r.get("value") is None or not r.get("units"):
            raise ValueError("Identity parameters need known values, units and provenance.")
        value = np.asarray(Q_(r["value"], r["units"]).magnitude, dtype=float)
        if value.ndim or not np.isfinite(value):
            raise ValueError("Identity parameters must be finite scalars.")
        symbols.append(r["symbol"])
    if len(set(symbols)) != len(symbols):
        raise ValueError("Duplicate model identity parameters.")
    result = {"model_id": model_id, "model_version": model_version, "equation_source": equation_source,
              "equation_sha256": equation_sha256, "parameters": list(parameter_records),
              "observation_model": dict(observation_model), "training_experiment_ids": list(training_experiment_ids)}
    return json.loads(json.dumps(result, allow_nan=False))


def _checked_identity(identity: Mapping[str, Any]) -> dict:
    fields = dict(identity)
    fields["parameter_records"] = fields.pop("parameters")
    return model_identity(**fields)


def freeze_scoped_prediction(*, result: SimulationResult, training_dataset: ExperimentDataset, identity: Mapping[str, Any],
                             scope: ModelScope, maximum_rmse: Mapping[str, Parameter],
                             observable_mapping: Sequence[ObservableMapping], output_dir: Path) -> dict:
    """Freeze criteria with predictions so scoring cannot loosen them afterward."""
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise ValueError("Scoped prediction output must be empty; overwriting frozen evidence is refused.")
    checked = _checked_identity(identity)
    if result.model_version != identity["model_version"]:
        raise ValueError("Simulation version differs from the model identity.")
    actual = {p.symbol: p for p in result.parameters}
    if set(actual) != {r["symbol"] for r in identity["parameters"]}:
        raise ValueError("Prediction parameter set differs from model identity.")
    for r in identity["parameters"]:
        quantity = actual[r["symbol"]].quantity
        if quantity is None or float(quantity.to(r["units"]).magnitude) != float(r["value"]):
            raise ValueError("Prediction parameter values differ from model identity.")
    if set(maximum_rmse) != set(scope.observable_units):
        raise ValueError("One predefined criterion is required for each scoped observable.")
    if (len(observable_mapping) != len(scope.observable_units)
            or {m.dataset_measurement_id for m in observable_mapping} != set(scope.observable_units)):
        raise ValueError("Every scoped observable needs exactly one frozen observation mapping.")
    for key, parameter in maximum_rmse.items():
        parameter.validate_provenance()
        number = float(assert_compatible(parameter.quantity, scope.observable_units[key]).magnitude)
        if not np.isfinite(number) or number <= 0:
            raise ValueError("Acceptance thresholds must be finite and positive.")
    contract = {"schema_version": 1, "identity": checked, "scope": scope.to_dict(),
                "maximum_rmse": {k:v.to_dict() for k,v in maximum_rmse.items()},
                "observable_mapping": [m.to_dict() for m in observable_mapping]}
    binding = scientific_digest(contract)
    prediction_hash = freeze_prediction(result=result, training_dataset=training_dataset,
                                        model_source=binding, path=output_dir/"prediction.json")
    bundle = {**contract, "prediction_sha256": prediction_hash, "contract_sha256": binding}
    (output_dir/"contract.json").write_text(json.dumps(bundle, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    return bundle


def evaluate_scoped_prediction(*, bundle_dir: Path, dataset: ExperimentDataset, plan: IndependentValidationPlan,
                               raw_replicates_path: Path, observable_mapping: Sequence[ObservableMapping],
                               categorical_conditions: Mapping[str, str], numeric_conditions: Mapping[str, Quantity],
                               domain_review_source: str, output_dir: Path | None = None,
                               allow_synthetic_for_testing: bool = False) -> dict:
    """Compute bounded evidence status from verified inputs, never from a status flag."""
    if not has_text(domain_review_source):
        raise ValueError("Documented external domain review is required for scoped empirical evidence.")
    bundle = json.loads((bundle_dir/"contract.json").read_text(encoding="utf-8"))
    contract = {k:bundle[k] for k in ("schema_version", "identity", "scope", "maximum_rmse", "observable_mapping")}
    if scientific_digest(contract) != bundle["contract_sha256"]:
        raise ValueError("Model/scope/criteria contract was changed after freezing.")
    if [m.to_dict() for m in observable_mapping] != bundle["observable_mapping"]:
        raise ValueError("Observation mapping differs from the frozen model contract.")
    prediction = json.loads((bundle_dir/"prediction.json").read_text(encoding="utf-8"))
    if (prediction["model_source"] != bundle["contract_sha256"]
            or plan.prediction_sha256 != bundle["prediction_sha256"]):
        raise ValueError("Prediction and validation plan are not bound to this exact model contract.")
    if plan.validation_experiment_id in bundle["identity"]["training_experiment_ids"]:
        raise ValueError("Validation experiment was used during model development.")
    if plan.training_experiment_id not in bundle["identity"]["training_experiment_ids"]:
        raise ValueError("Validation plan names an unrelated training experiment.")
    scope = ModelScope.from_dict(bundle["scope"])
    scope.check(categorical_conditions, numeric_conditions)
    if {s.measurement_id for s in dataset.measurements} != set(scope.observable_units):
        raise ValueError("Validation observables differ from scoped claims.")
    for series in dataset.measurements:
        assert_compatible(Q_(1, series.value_units), scope.observable_units[series.measurement_id])
        if scope.observation_time:
            times = Q_([p.time for p in series.points],series.time_units).to(scope.observation_time.lower.units).magnitude
            if (np.any(times < scope.observation_time.lower.magnitude)
                    or np.any(times > scope.observation_time.upper.to(scope.observation_time.lower.units).magnitude)):
                raise ValueError("Validation observation times lie outside the frozen scope.")
    evidence = evaluate_frozen_prediction(prediction_path=bundle_dir/"prediction.json", dataset=dataset,
        plan=plan, raw_replicates_path=raw_replicates_path, observable_mapping=observable_mapping,
        maximum_rmse={k: Parameter.from_dict(v) for k,v in bundle["maximum_rmse"].items()},
        allow_synthetic_for_testing=allow_synthetic_for_testing)
    passed = evidence["empirical_criteria_met"]
    record = {"schema_version": 1, "model_sha256": scientific_digest(bundle["identity"]),
        "identity": bundle["identity"], "declared_scope": bundle["scope"], "contract_sha256": bundle["contract_sha256"],
        "status": "empirical_criteria_met_at_tested_conditions" if passed else "not_validated",
        "tested_conditions": {"categorical": dict(categorical_conditions), "numeric": {
            k: {"value": float(v.magnitude), "units": str(v.units)} for k,v in numeric_conditions.items()}},
        "tested_observation_times": {s.measurement_id: {"values": [p.time for p in s.points], "units": s.time_units}
                                     for s in dataset.measurements},
        "domain_review_source": domain_review_source, "evidence": evidence,
        "entire_declared_range_validated": False, "external_review_authenticated_by_software": False,
        "publication_claim_authorized": False}
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        with (output_dir/"model_validation.json").open("x", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2, allow_nan=False)
            handle.write("\n")
    return record


def validation_readiness(identity: Mapping[str, Any], scope: ModelScope, *, criteria_source: str | None,
                         independent_data_source: str | None, measurement_error_source: str | None,
                         domain_review_source: str | None) -> dict:
    """A readiness packet is not a validated profile, even if all inputs are named."""
    checked = _checked_identity(identity)
    sources = {"predeclared_acceptance_criteria": criteria_source, "matched_independent_data": independent_data_source,
               "measurement_error_evidence": measurement_error_source, "domain_review": domain_review_source}
    missing = [key for key, value in sources.items() if not has_text(value)]
    return {"schema_version": 1, "identity": checked, "model_sha256": scientific_digest(checked),
            "scope": scope.to_dict(), "evidence_sources": sources, "missing_requirements": missing,
            "status": "awaiting_evidence" if missing else "ready_for_frozen_evaluation",
            "validated": False, "publication_claim_authorized": False}
