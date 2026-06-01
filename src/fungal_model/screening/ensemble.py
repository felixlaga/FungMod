"""Exploratory registry ensemble simulation over ValueSpec uncertainty."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import product
import json
from pathlib import Path
from typing import Any, Literal

import numpy as np
import yaml

from fungal_model.core.value_spec import ValueSpec
from fungal_model.io.model_config import ModelConfig
from fungal_model.registry.records import ParameterRecord, ProcessCompatibilityRecord
from fungal_model.registry.store import FungModRegistry
from fungal_model.results import SimulationResult
from fungal_model.screening.case_builder import (
    RegistryCaseBuildError,
    SURFACE_CATALYSIS_PARAMETER_ROLES,
    _best_parameter_record,
    _select_compatibility,
    _surface_catalysis_config_data,
)
from fungal_model.screening.modelability import ModelabilityReport, assess_modelability
from fungal_model.workflows import run_configured_model

ScreenSimulationMode = Literal["exploratory"]


class RegistryScreenSimulationError(ValueError):
    """Raised when an exploratory registry screen cannot be simulated."""


@dataclass(frozen=True)
class EnsembleSample:
    """One sampled config/run record in an exploratory registry screen."""

    sample_index: int
    config_path: str
    output_directory: str
    parameters: Mapping[str, Mapping[str, Any]]
    final_states: Mapping[str, Mapping[str, Any]]
    validation_passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_index": self.sample_index,
            "config_path": self.config_path,
            "output_directory": self.output_directory,
            "parameters": {
                role: dict(value)
                for role, value in self.parameters.items()
            },
            "final_states": {
                name: dict(value)
                for name, value in self.final_states.items()
            },
            "validation_passed": self.validation_passed,
        }


@dataclass(frozen=True)
class RegistryCaseEnsemble:
    """All sampled runs for one fungus/substrate/environment registry case."""

    fungus_id: str
    substrate_id: str
    environment_id: str
    modelability_report: ModelabilityReport
    samples: tuple[EnsembleSample, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "fungus_id": self.fungus_id,
            "substrate_id": self.substrate_id,
            "environment_id": self.environment_id,
            "modelability_report": self.modelability_report.to_dict(),
            "samples": [sample.to_dict() for sample in self.samples],
        }


@dataclass(frozen=True)
class RegistryScreenResult:
    """Structured result for one exploratory registry screen."""

    mode: ScreenSimulationMode
    n_samples: int
    seed: int | None
    output_directory: str
    case_results: tuple[RegistryCaseEnsemble, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "n_samples": self.n_samples,
            "seed": self.seed,
            "output_directory": self.output_directory,
            "case_results": [case.to_dict() for case in self.case_results],
        }

    def save(self, path: str | Path | None = None) -> Path:
        destination = Path(path) if path is not None else Path(self.output_directory)
        destination.mkdir(parents=True, exist_ok=True)
        summary_path = destination / "screen_summary.json"
        summary_path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return summary_path


def simulate_screen(
    *,
    fungus_ids: Sequence[str],
    substrate_ids: Sequence[str],
    environment_ids: Sequence[str],
    registry: FungModRegistry,
    n_samples: int,
    seed: int | None = None,
    output_dir: str | Path | None = None,
    mode: ScreenSimulationMode = "exploratory",
) -> RegistryScreenResult:
    """Sample ValueSpec uncertainty and run toy configs for registry cases."""

    _validate_screen_inputs(
        fungus_ids=fungus_ids,
        substrate_ids=substrate_ids,
        environment_ids=environment_ids,
        n_samples=n_samples,
        mode=mode,
    )
    root = Path(output_dir) if output_dir is not None else Path("outputs/registry_screen")
    rng = np.random.default_rng(seed)
    case_results: list[RegistryCaseEnsemble] = []
    for fungus_id, substrate_id, environment_id in product(fungus_ids, substrate_ids, environment_ids):
        case_seed = int(rng.integers(0, np.iinfo(np.uint32).max))
        case_results.append(
            _simulate_case_ensemble(
                fungus_id=fungus_id,
                substrate_id=substrate_id,
                environment_id=environment_id,
                registry=registry,
                n_samples=n_samples,
                rng=np.random.default_rng(case_seed),
                output_root=root,
            )
        )
    result = RegistryScreenResult(
        mode=mode,
        n_samples=n_samples,
        seed=seed,
        output_directory=str(root),
        case_results=tuple(case_results),
    )
    result.save()
    return result


def _simulate_case_ensemble(
    *,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    registry: FungModRegistry,
    n_samples: int,
    rng: np.random.Generator,
    output_root: Path,
) -> RegistryCaseEnsemble:
    report = assess_modelability(
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        environment_id=environment_id,
        registry=registry,
        mode="exploratory",
    )
    if report.status not in {"modelable", "exploratory"}:
        raise RegistryScreenSimulationError(
            "Registry case cannot be simulated as an exploratory ensemble because "
            f"modelability status is {report.status!r}. Report: {report.to_dict()}"
        )
    compatibility = _select_compatibility(
        registry=registry,
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        report=report,
    )
    if compatibility.process_type != "surface_catalysis":
        raise RegistryScreenSimulationError(
            "R4 exploratory screen currently supports only existing generic "
            f"surface_catalysis configs, not {compatibility.process_type!r}."
        )
    role_records = _resolve_role_records(
        registry=registry,
        compatibility=compatibility,
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        environment_id=environment_id,
    )
    samples: list[EnsembleSample] = []
    case_dir = output_root / f"{fungus_id}__{substrate_id}__{environment_id}"
    for sample_index in range(n_samples):
        sampled_records = _sample_role_records(
            role_records,
            rng=rng,
            sample_index=sample_index,
        )
        sample_dir = case_dir / f"sample_{sample_index:04d}"
        config = _build_sample_config(
            registry=registry,
            compatibility=compatibility,
            fungus_id=fungus_id,
            substrate_id=substrate_id,
            environment_id=environment_id,
            sampled_records=sampled_records,
            sample_dir=sample_dir,
        )
        samples.append(_run_sample(config=config, sample_dir=sample_dir, sample_index=sample_index))
    return RegistryCaseEnsemble(
        fungus_id=fungus_id,
        substrate_id=substrate_id,
        environment_id=environment_id,
        modelability_report=report,
        samples=tuple(samples),
    )


def _resolve_role_records(
    *,
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
) -> Mapping[str, ParameterRecord]:
    missing_roles = tuple(
        role for role in SURFACE_CATALYSIS_PARAMETER_ROLES if role not in compatibility.parameter_roles
    )
    if missing_roles:
        raise RegistryScreenSimulationError(
            "Surface-catalysis compatibility is missing parameter role mappings "
            f"for: {', '.join(missing_roles)}."
        )
    records: dict[str, ParameterRecord] = {}
    for role in SURFACE_CATALYSIS_PARAMETER_ROLES:
        symbol = compatibility.parameter_roles[role]
        record = _best_parameter_record(
            registry=registry,
            parameter_symbol=symbol,
            compatibility=compatibility,
            fungus_id=fungus_id,
            substrate_id=substrate_id,
            environment_id=environment_id,
        )
        if record is None:
            raise RegistryScreenSimulationError(
                f"No registry parameter record found for role {role!r} and symbol {symbol!r}."
            )
        validation = record.value.validate(nonnegative=True)
        if not validation.passed:
            raise RegistryScreenSimulationError(
                f"Parameter {symbol!r} for role {role!r} failed ValueSpec validation: "
                f"{validation.to_dict()}"
            )
        if not record.value.is_exact and not record.value.is_uncertain:
            raise RegistryScreenSimulationError(
                f"Parameter role {role!r} uses ValueSpec kind {record.value.kind!r}, "
                "which cannot be sampled for R4 exploratory simulation."
            )
        records[role] = record
    return records


def _sample_role_records(
    role_records: Mapping[str, ParameterRecord],
    *,
    rng: np.random.Generator,
    sample_index: int,
) -> Mapping[str, ParameterRecord]:
    return {
        role: _sample_record(record, rng=rng, sample_index=sample_index)
        for role, record in role_records.items()
    }


def _sample_record(
    record: ParameterRecord,
    *,
    rng: np.random.Generator,
    sample_index: int,
) -> ParameterRecord:
    quantity = record.value.sample(rng)
    return ParameterRecord(
        record_id=f"{record.record_id}_sample_{sample_index}",
        name=record.name,
        maturity=record.maturity,
        provenance=dict(record.provenance),
        notes=f"{record.notes} Sampled for R4 exploratory toy ensemble.",
        parameter_symbol=record.parameter_symbol,
        process_type=record.process_type,
        enzyme_class=record.enzyme_class,
        substrate_class=record.substrate_class,
        fungus_id=record.fungus_id,
        substrate_id=record.substrate_id,
        environment_id=record.environment_id,
        value=ValueSpec(
            kind="exact",
            value=float(quantity.magnitude),
            units=str(quantity.units),
            source=record.value.source or record.provenance.get("source"),
            confidence_level=record.value.confidence_level or record.provenance.get("confidence_level"),
            notes=f"Sample {sample_index} from original ValueSpec kind {record.value.kind}.",
        ),
    )


def _build_sample_config(
    *,
    registry: FungModRegistry,
    compatibility: ProcessCompatibilityRecord,
    fungus_id: str,
    substrate_id: str,
    environment_id: str,
    sampled_records: Mapping[str, ParameterRecord],
    sample_dir: Path,
) -> ModelConfig:
    substrate = registry.get_substrate(substrate_id)
    try:
        data = _surface_catalysis_config_data(
            registry=registry,
            compatibility=compatibility,
            substrate=substrate,
            fungus_id=fungus_id,
            substrate_id=substrate_id,
            environment_id=environment_id,
            parameter_records=sampled_records,
            output_directory=str(sample_dir / "bundle"),
        )
    except RegistryCaseBuildError as exc:
        raise RegistryScreenSimulationError(str(exc)) from exc
    data["name"] = f"{data['name']} sample {sample_dir.name}"
    data["provenance"]["screen_mode"] = "exploratory"
    data["provenance"]["sample_directory"] = str(sample_dir)
    return ModelConfig.from_mapping(data)


def _run_sample(*, config: ModelConfig, sample_dir: Path, sample_index: int) -> EnsembleSample:
    sample_dir.mkdir(parents=True, exist_ok=True)
    config_path = sample_dir / "model_config.yml"
    config_path.write_text(yaml.safe_dump(config.to_dict(), sort_keys=False), encoding="utf-8")
    result = run_configured_model(config_path, output_dir=sample_dir / "bundle")
    return EnsembleSample(
        sample_index=sample_index,
        config_path=str(config_path),
        output_directory=str(sample_dir / "bundle"),
        parameters=_sample_parameters(config),
        final_states=_final_states(result),
        validation_passed=_validation_passed(result),
    )


def _sample_parameters(config: ModelConfig) -> Mapping[str, Mapping[str, Any]]:
    process = config.processes[0]
    parameters = {
        str(parameter["symbol"]): parameter
        for parameter_set in config.parameters
        for parameter in parameter_set.parameters
    }
    return {
        str(role): {
            "symbol": str(symbol),
            "value": parameters[str(symbol)]["value"],
            "units": parameters[str(symbol)]["units"],
        }
        for role, symbol in process.parameters.items()
    }


def _final_states(result: SimulationResult) -> Mapping[str, Mapping[str, Any]]:
    final: dict[str, Mapping[str, Any]] = {}
    for name, quantity in result.states.items():
        values = np.asarray(quantity.magnitude, dtype=float).reshape(-1)
        final[name] = {
            "value": float(values[-1]),
            "units": str(quantity.units),
        }
    return final


def _validation_passed(result: SimulationResult) -> bool:
    report = result.validation_report()
    return bool(report) and all(bool(item.get("passed")) for item in report)


def _validate_screen_inputs(
    *,
    fungus_ids: Sequence[str],
    substrate_ids: Sequence[str],
    environment_ids: Sequence[str],
    n_samples: int,
    mode: str,
) -> None:
    if mode != "exploratory":
        raise RegistryScreenSimulationError("R4 simulate_screen supports only mode='exploratory'.")
    if n_samples < 1:
        raise RegistryScreenSimulationError("n_samples must be at least 1.")
    if not fungus_ids or not substrate_ids or not environment_ids:
        raise RegistryScreenSimulationError(
            "fungus_ids, substrate_ids, and environment_ids must each contain at least one id."
        )


__all__ = [
    "EnsembleSample",
    "RegistryCaseEnsemble",
    "RegistryScreenResult",
    "RegistryScreenSimulationError",
    "ScreenSimulationMode",
    "simulate_screen",
]
