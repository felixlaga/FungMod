"""PEtab export for FungMod calibration cases.

`PEtab <https://petab.readthedocs.io/>`_ is the community standard for specifying
parameter-estimation problems. A FungMod calibration config (model + dataset +
fittable parameters + observable mappings) maps directly onto a PEtab problem:

- the model config is exported to SBML (``model.xml``);
- dataset measurements become the PEtab measurement table;
- observable mappings become the observable table;
- fittable parameters and their bounds become the parameter table;
- a single simulation condition ties them together;
- a PEtab ``problem.yaml`` links the pieces.

The files are written with the standard library, so producing a PEtab problem
needs no PEtab dependency (only the ``standards`` extra's libsbml, for the SBML
model). Units are converted so measurement values and times match the SBML
model's species units and seconds.
"""

from __future__ import annotations

import csv
import io
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from fungal_model.core.units import Q_
from fungal_model.standards.sbml import SbmlExportError, to_sbml

PETAB_FORMAT_VERSION = 1


class PetabExportError(SbmlExportError):
    """Raised when a FungMod calibration case cannot be exported to PEtab."""


@dataclass(frozen=True)
class PetabExport:
    """Paths written by :func:`calibration_config_to_petab`."""

    directory: Path
    problem_yaml: Path
    sbml_model: Path
    observables: Path
    measurements: Path
    conditions: Path
    parameters: Path
    validation_measurements: Path | None = None
    holdout_measurements: Path | None = None
    metadata: Path | None = None


def _sanitize_id(name: str) -> str:
    import re

    candidate = re.sub(r"[^0-9A-Za-z_]", "_", str(name))
    if not candidate or not (candidate[0].isalpha() or candidate[0] == "_"):
        candidate = f"_{candidate}"
    return candidate


def _resolve(base: Path, value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() and candidate.exists():
        return candidate
    for root in (base.parent, Path.cwd(), *base.parents):
        resolved = (root / value).resolve()
        if resolved.exists():
            return resolved
    raise PetabExportError(f"Cannot resolve referenced path {value!r} from {base}.")


def _write_tsv(path: Path, header: list[str], rows: list[list[Any]]) -> None:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter="\t", lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    path.write_text(buffer.getvalue(), encoding="utf-8", newline="")


def calibration_config_to_petab(
    config_path: str | Path,
    output_dir: str | Path,
    *,
    condition_id: str = "condition1",
) -> PetabExport:
    """Export a FungMod calibration config to a PEtab problem directory.

    Args:
        config_path: Path to a ``calibration_config`` YAML file.
        output_dir: Directory to write the PEtab problem into (created if needed).
        condition_id: Identifier for the single simulation condition.

    Only training rows enter ``problem.yaml``. Validation and holdout rows are
    written separately. Every observation requires finite positive uncertainty;
    an unknown scale is never replaced by an implicit noise model.

    Returns:
        A :class:`PetabExport` with the written file paths.

    Raises:
        PetabExportError: If the model is not SBML-exportable, an observable is
            not a supported state observable, or bounds are missing.
    """

    from fungal_model.data.loaders import load_experiment_dataset
    from fungal_model.calibration.configured import _build_split
    from fungal_model.io.model_config import load_model_config
    from fungal_model.workflows.configured_inputs import ConfiguredInputLoader
    from fungal_model.workflows.configured_processes import ConfiguredProcessAssembler

    config_path = Path(config_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or config.get("kind") != "calibration_config":
        raise PetabExportError(f"{config_path} is not a calibration_config file.")

    model_config_path = _resolve(config_path, str(config["model_config"]))
    dataset_path = _resolve(config_path, str(config["dataset"]))
    parameter_symbols = [str(symbol) for symbol in config.get("parameter_symbols", [])]
    if not parameter_symbols:
        raise PetabExportError("calibration_config requires at least one parameter symbol.")
    bounds = config.get("bounds", {}) or {}
    initial_guess = config.get("initial_guess", {}) or {}
    observable_mapping = config.get("observable_mapping", []) or []
    if not observable_mapping:
        raise PetabExportError("calibration_config requires at least one observable mapping.")

    model_config = load_model_config(model_config_path)
    inputs = ConfiguredInputLoader().load(model_config)
    assembled = ConfiguredProcessAssembler().assemble(model_config, inputs)

    sbml_text = to_sbml(assembled.model, initial_state=inputs.initial_state, model_id=model_config.name)
    exported_symbols = [p.symbol for p in assembled.model.parameters if p.quantity is not None]
    species_name_to_id, parameter_ids = _sbml_symbol_maps(sbml_text, exported_symbols)
    state_units = {spec.name: spec.units for spec in assembled.model.state_variables}

    dataset = load_experiment_dataset(dataset_path)
    series_by_id = {series.measurement_id: series for series in dataset.measurements}
    split = _build_split(dataset, config.get("split"))

    directory = Path(output_dir)
    sbml_path = directory / "model.xml"

    observable_rows: list[list[Any]] = []
    measurement_rows: list[list[Any]] = []
    validation_rows: list[list[Any]] = []
    holdout_rows: list[list[Any]] = []
    seen_observables: set[str] = set()
    for mapping in observable_mapping:
        measurement_id = str(mapping["dataset_measurement_id"])
        model_observable = str(mapping["model_observable"])
        observable_type = str(mapping.get("observable_type", "state"))
        transform = str(mapping.get("transform", "identity"))
        if observable_type != "state":
            raise PetabExportError(
                f"PEtab export supports 'state' observables only; got {observable_type!r} "
                f"for {measurement_id!r}."
            )
        if transform != "identity":
            raise PetabExportError(
                f"PEtab export supports the 'identity' transform only; got {transform!r}."
            )
        if model_observable not in species_name_to_id:
            raise PetabExportError(
                f"Observable {model_observable!r} is not an exported SBML species."
            )
        if measurement_id not in series_by_id:
            raise PetabExportError(f"Dataset has no measurement series {measurement_id!r}.")

        species_id = species_name_to_id[model_observable]
        observable_units = state_units[model_observable]
        observable_id = _sanitize_id(f"observable_{measurement_id}")
        if observable_id in seen_observables:
            raise PetabExportError(f"Duplicate or colliding observable ID: {observable_id!r}.")
        seen_observables.add(observable_id)
        observable_rows.append(
            [observable_id, measurement_id, species_id, "lin", f"noiseParameter1_{observable_id}", "normal"]
        )

        series = series_by_id[measurement_id]
        uncertainty_units = series.uncertainty_units or series.value_units
        for index, point in enumerate(series.points):
            value = float(Q_(point.value, series.value_units).to(observable_units).magnitude)
            time = float(Q_(point.time, series.time_units).to("second").magnitude)
            if point.uncertainty is None:
                raise PetabExportError(
                    f"Measurement {measurement_id!r} point {index} has unknown uncertainty; "
                    "supply an explicit observation noise scale before PEtab export."
                )
            else:
                noise = float(Q_(point.uncertainty, uncertainty_units).to(observable_units).magnitude)
            if not math.isfinite(noise) or noise <= 0:
                raise PetabExportError(f"Measurement {measurement_id!r} uncertainty must be finite and positive.")
            target = (measurement_rows if index in split.train_indices[measurement_id]
                      else validation_rows if index in split.validation_indices[measurement_id]
                      else holdout_rows)
            target.append([observable_id, condition_id, value, time, noise])

    parameter_rows: list[list[Any]] = []
    for symbol in parameter_symbols:
        if symbol not in parameter_ids:
            raise PetabExportError(f"Parameter {symbol!r} is not an exported SBML parameter.")
        parameter_id = parameter_ids[symbol]
        if symbol not in bounds or len(bounds[symbol]) != 2:
            raise PetabExportError(f"calibration_config is missing [lower, upper] bounds for {symbol!r}.")
        lower, upper = (float(value) for value in bounds[symbol])
        nominal = float(initial_guess.get(symbol, (lower + upper) / 2.0))
        if not all(math.isfinite(v) for v in (lower, upper, nominal)) or not lower < upper or not lower <= nominal <= upper:
            raise PetabExportError(f"Parameter {symbol!r} requires finite ordered bounds containing its nominal value.")
        parameter_rows.append([parameter_id, symbol, "lin", lower, upper, nominal, 1])

    observables_path = directory / "observables.tsv"
    measurements_path = directory / "measurements.tsv"
    conditions_path = directory / "conditions.tsv"
    parameters_path = directory / "parameters.tsv"
    validation_path = directory / "validation_measurements.tsv"
    holdout_path = directory / "holdout_measurements.tsv"
    metadata_path = directory / "export_metadata.json"
    directory.mkdir(parents=True, exist_ok=True)
    sbml_path.write_text(sbml_text, encoding="utf-8", newline="")

    _write_tsv(
        observables_path,
        ["observableId", "observableName", "observableFormula", "observableTransformation", "noiseFormula", "noiseDistribution"],
        observable_rows,
    )
    _write_tsv(
        measurements_path,
        ["observableId", "simulationConditionId", "measurement", "time", "noiseParameters"],
        measurement_rows,
    )
    _write_tsv(conditions_path, ["conditionId", "conditionName"], [[condition_id, str(config.get("name", condition_id))]])
    measurement_header = ["observableId", "simulationConditionId", "measurement", "time", "noiseParameters"]
    _write_tsv(validation_path, measurement_header, validation_rows)
    _write_tsv(holdout_path, measurement_header, holdout_rows)
    metadata_path.write_text(json.dumps({
        "schema_version": "1.0.0", "dataset_id": dataset.dataset_id,
        "split": split.to_dict(), "training_rows": len(measurement_rows),
        "validation_rows": len(validation_rows), "holdout_rows": len(holdout_rows),
        "noise_policy": "explicit_positive_observation_scales",
        "noise_interpretation": "Normal errors are assumed; supplied scales do not establish experimental variance.",
        "validation_usage": "Separate tables are excluded from the estimation problem; do not refit on them.",
    }, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    _write_tsv(
        parameters_path,
        ["parameterId", "parameterName", "parameterScale", "lowerBound", "upperBound", "nominalValue", "estimate"],
        parameter_rows,
    )

    problem = {
        "format_version": PETAB_FORMAT_VERSION,
        "parameter_file": parameters_path.name,
        "problems": [
            {
                "sbml_files": [sbml_path.name],
                "condition_files": [conditions_path.name],
                "observable_files": [observables_path.name],
                "measurement_files": [measurements_path.name],
            }
        ],
    }
    problem_yaml = directory / "problem.yaml"
    problem_yaml.write_text(yaml.safe_dump(problem, sort_keys=False), encoding="utf-8", newline="")

    return PetabExport(
        directory=directory,
        problem_yaml=problem_yaml,
        sbml_model=sbml_path,
        observables=observables_path,
        measurements=measurements_path,
        conditions=conditions_path,
        parameters=parameters_path,
        validation_measurements=validation_path,
        holdout_measurements=holdout_path,
        metadata=metadata_path,
    )


def _sbml_symbol_maps(sbml_text: str, parameter_symbols: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    """Return species and parameter symbol maps from the exported SBML.

    ``to_sbml`` sets each species/parameter *name* to the original FungMod name
    and its *id* to a unique sanitized symbol. Parameters follow the exporter's
    ordered parameter list, including any SId collision suffixes.
    """

    try:
        import libsbml
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised via error path
        raise PetabExportError(
            "PEtab export requires the optional 'standards' dependency. "
            "Install it with: pip install fungmod[standards]"
        ) from exc

    document = libsbml.readSBMLFromString(sbml_text)
    model = document.getModel()
    if model is None:
        raise PetabExportError("Could not parse the exported SBML model for PEtab export.")
    species_name_to_id = {
        (model.getSpecies(i).getName() or model.getSpecies(i).getId()): model.getSpecies(i).getId()
        for i in range(model.getNumSpecies())
    }
    parameter_ids = dict(zip(parameter_symbols,
        [model.getParameter(i).getId() for i in range(model.getNumParameters())], strict=True))
    return species_name_to_id, parameter_ids


__all__ = ["PETAB_FORMAT_VERSION", "PetabExport", "PetabExportError", "calibration_config_to_petab"]
