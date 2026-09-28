"""Frozen-prediction scoring with explicit external validation evidence.

This workflow never fits parameters. Evidence declarations and a criteria pass
cannot prove experimental independence or authorize publication. Raw replicate
means must match the supplied comparison dataset; arbitrary preprocessing is
outside this deliberately narrow intake contract.
"""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.provenance import ProvenanceError, has_text
from fungal_model.core.simulation import SolverSettings
from fungal_model.core.units import Q_, assert_compatible
from fungal_model.data.comparison import ObservableMapping, evaluate_model_against_dataset
from fungal_model.data.datasets import ExperimentDataset
from fungal_model.results import SimulationResult


def _digest(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, allow_nan=False).encode()).hexdigest()


def _observations_digest(dataset: ExperimentDataset) -> str:
    return _digest([{'time_units': s.time_units, 'value_units': s.value_units,
                     'points': [(p.time, p.value) for p in s.points]} for s in dataset.measurements])


def freeze_prediction(
    *, result: SimulationResult, training_dataset: ExperimentDataset,
    model_source: str, path: str | Path,
) -> str:
    """Write a new prediction snapshot, returning its SHA-256 for an archived plan.

    The file is created exclusively: overwriting a frozen prediction is refused.
    Freeze before examining independent validation responses; the external plan
    must establish that chronology, which a local file timestamp cannot prove.
    """
    if not has_text(model_source):
        raise ProvenanceError('An immutable model source/version is required.')
    if result.solver_metadata.get('success') is not True:
        raise ValueError('Only successful solver results may be frozen.')
    if not training_dataset.validate().passed:
        raise ValueError('Training dataset must pass its schema/provenance checks.')
    data = {'schema_version': '1.0.0', 'model_source': model_source,
            'training_dataset_id': training_dataset.dataset_id,
            'training_observations_sha256': _observations_digest(training_dataset),
            'training_maturity': training_dataset.maturity, 'result': result.to_dict()}
    content = (json.dumps(data, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as handle:
        handle.write(content)
    return hashlib.sha256(content).hexdigest()


@dataclass(frozen=True)
class IndependentValidationPlan:
    analysis_plan_source: str
    prediction_sha256: str
    training_experiment_id: str
    validation_experiment_id: str
    preparation_id: str
    preparation_match_source: str
    independence_source: str
    uncertainty_source: str
    raw_replicates_source: str
    raw_replicates_sha256: str

    def __post_init__(self):
        for name, value in asdict(self).items():
            if not has_text(value):
                raise ProvenanceError(f'Independent validation requires {name}.')
        if self.training_experiment_id == self.validation_experiment_id:
            raise ValueError('Training and validation experiment IDs must differ.')
        for digest in (self.prediction_sha256, self.raw_replicates_sha256):
            if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                raise ValueError('Artifact hashes must be lowercase SHA-256 digests.')


def _check_replicates(path: Path, dataset: ExperimentDataset, plan: IndependentValidationPlan) -> None:
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != plan.raw_replicates_sha256:
        raise ValueError('Raw replicate checksum mismatch.')
    with path.open(newline='', encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    required = {'measurement_id', 'time', 'time_units', 'value', 'units', 'replicate_id', 'experiment_id', 'preparation_id'}
    if not rows or any(not required <= set(row) for row in rows):
        raise ValueError('Raw replicate CSV lacks required columns or observations.')
    if any(row['experiment_id'] != plan.validation_experiment_id or row['preparation_id'] != plan.preparation_id for row in rows):
        raise ValueError('Raw replicate experiment/preparation does not match the plan.')
    for series in dataset.measurements:
        for point in series.points:
            group = [row for row in rows if row['measurement_id'] == series.measurement_id
                     and np.isclose(float(Q_(float(row['time']), row['time_units']).to(series.time_units).magnitude),
                                    point.time, rtol=1e-10, atol=1e-12)]
            ids = [row['replicate_id'].strip() for row in group]
            if len(ids) < 2 or not all(ids) or len(set(ids)) != len(ids):
                raise ValueError('Each comparison point needs at least two distinct raw replicate IDs.')
            values = [float(Q_(float(row['value']), row['units']).to(series.value_units).magnitude) for row in group]
            if not np.all(np.isfinite(values)) or not np.isclose(np.mean(values), point.value, rtol=1e-8, atol=1e-12):
                raise ValueError('Comparison observations must equal the raw replicate means.')


def evaluate_frozen_prediction(
    *, prediction_path: str | Path, dataset: ExperimentDataset,
    plan: IndependentValidationPlan, raw_replicates_path: str | Path,
    observable_mapping: Sequence[ObservableMapping], maximum_rmse: Mapping[str, Parameter],
    output_dir: str | Path | None = None, allow_synthetic_for_testing: bool = False,
) -> dict[str, Any]:
    """Score an unchanged prediction against independently declared replicate means.

    The normal empirical path refuses synthetic data and digitization-only
    uncertainty. Synthetic software tests require explicit opt-in and can never
    set ``empirical_criteria_met``. Thresholds must come from the archived plan.
    """
    content = Path(prediction_path).read_bytes()
    if hashlib.sha256(content).hexdigest() != plan.prediction_sha256:
        raise ValueError('Frozen prediction checksum mismatch; no refitting or replacement is allowed.')
    snapshot = json.loads(content)
    if snapshot.get('schema_version') != '1.0.0':
        raise ValueError('Unsupported frozen prediction schema.')
    if snapshot['training_dataset_id'] == dataset.dataset_id or snapshot['training_observations_sha256'] == _observations_digest(dataset):
        raise ValueError('Validation reuses the training dataset or observations.')
    if not dataset.validate().passed:
        raise ValueError('Validation dataset does not pass its schema/provenance checks.')
    synthetic = dataset.maturity == 'synthetic' or snapshot['training_maturity'] == 'synthetic'
    if snapshot['training_maturity'] not in {'literature_raw', 'literature_processed', 'synthetic'}:
        raise ValueError('Training data must be unpromoted literature observations or an explicit synthetic test.')
    if synthetic and not allow_synthetic_for_testing:
        raise ValueError('Synthetic data are not independent empirical validation.')
    if dataset.maturity not in {'literature_raw', 'literature_processed', 'synthetic'}:
        raise ValueError('Validation requires unpromoted raw/processed literature observations.')
    if not dataset.preprocessing.raw_data_available:
        raise ValueError('Independent validation requires raw replicate observations.')
    if any(s.uncertainty_type not in {'standard_deviation', 'standard_error'}
           or any(p.uncertainty is None or not np.isfinite(p.uncertainty) or p.uncertainty <= 0 for p in s.points)
           for s in dataset.measurements):
        raise ValueError('Independent validation requires positive experimental uncertainty, not digitization resolution.')
    ids = {s.measurement_id for s in dataset.measurements}
    mapped = [m.dataset_measurement_id for m in observable_mapping]
    if set(maximum_rmse) != ids or set(mapped) != ids or len(mapped) != len(ids):
        raise ValueError('Exactly one mapping and sourced RMSE threshold per measurement are required.')
    _check_replicates(Path(raw_replicates_path), dataset, plan)
    record = snapshot['result']
    def quantities(key):
        return {name: Q_(value['value'], value['units']) for name, value in record[key].items()}
    # This view is used only by the comparison routine, never by a solver.
    view = SimulationResult(time=Q_(record['time']['value'], record['time']['units']),
        states=quantities('states'), process_rates=quantities('process_rates'),
        derived_quantities=quantities('derived_quantities'), parameters=ParameterSet([]),
        assumptions=(), solver_settings=SolverSettings(), name=record['name'], model_version=record['model_version'])
    comparison = evaluate_model_against_dataset(result=view, dataset=dataset,
        observable_mapping=observable_mapping, fitted_parameter_count=0)
    checks = {}
    for series in comparison.residuals:
        threshold = maximum_rmse[series.measurement_id]
        threshold.validate_provenance()
        value = float(assert_compatible(threshold.quantity, series.units).magnitude)
        if not np.isfinite(value) or value <= 0:
            raise ValueError('RMSE thresholds must be finite and positive.')
        rmse = float(np.sqrt(np.mean([point.residual**2 for point in series.points])))
        checks[series.measurement_id] = {'rmse': rmse, 'units': series.units, 'maximum': value,
                                        'passed': rmse <= value, 'criterion': threshold.to_dict()}
    report = {'schema_version': '1.0.0', 'plan': asdict(plan), 'checks': checks,
        'comparison': comparison.to_dict(), 'validation_dataset': dataset.to_dict(),
        'frozen_prediction': snapshot, 'parameters_refitted': False,
        'meets_declared_criteria': all(c['passed'] for c in checks.values()),
        'empirical_criteria_met': not synthetic and all(c['passed'] for c in checks.values()),
        'evidence_mode': 'synthetic_software_test' if synthetic else 'externally_declared_empirical_evidence',
        'publication_claim_authorized': False,
        'limitations': 'Software verifies hashes, raw replicate means and supplied criteria, not external independence, chronology, preparation identity or biological generality.'}
    if output_dir is not None:
        directory = Path(output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'independent_validation.json').write_text(
            json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return report
