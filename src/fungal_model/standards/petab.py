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
    for root in (Path.cwd(), base.parent):
        resolved = (root / value).resolve()
        if resolved.exists():
            return resolved
    return candidate


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

    Returns:
        A :class:`PetabExport` with the written file paths.

    Raises:
        PetabExportError: If the model is not SBML-exportable, an observable is
            not a supported state observable, or bounds are missing.
    """

    from fungal_model.data.loaders import load_experiment_dataset
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
    species_name_to_id, parameter_id_set = _sbml_symbol_maps(sbml_text)
    state_units = {spec.name: spec.units for spec in assembled.model.state_variables}

    dataset = load_experiment_dataset(dataset_path)
    series_by_id = {series.measurement_id: series for series in dataset.measurements}

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    sbml_path = directory / "model.xml"
    sbml_path.write_text(sbml_text, encoding="utf-8", newline="")

    observable_rows: list[list[Any]] = []
    measurement_rows: list[list[Any]] = []
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
        observable_rows.append(
            [observable_id, measurement_id, species_id, "lin", f"noiseParameter1_{observable_id}", "normal"]
        )

        series = series_by_id[measurement_id]
        uncertainty_units = series.uncertainty_units or series.value_units
        for point in series.points:
            value = float(Q_(point.value, series.value_units).to(observable_units).magnitude)
            time = float(Q_(point.time, series.time_units).to("second").magnitude)
            if point.uncertainty is None:
                noise = 1.0
            else:
                noise = float(Q_(point.uncertainty, uncertainty_units).to(observable_units).magnitude)
            measurement_rows.append([observable_id, condition_id, value, time, noise])

    parameter_rows: list[list[Any]] = []
    for symbol in parameter_symbols:
        parameter_id = _sanitize_id(symbol)
        if parameter_id not in parameter_id_set:
            raise PetabExportError(f"Parameter {symbol!r} is not an exported SBML parameter.")
        if symbol not in bounds or len(bounds[symbol]) != 2:
            raise PetabExportError(f"calibration_config is missing [lower, upper] bounds for {symbol!r}.")
        lower, upper = (float(value) for value in bounds[symbol])
        nominal = float(initial_guess.get(symbol, (lower + upper) / 2.0))
        parameter_rows.append([parameter_id, symbol, "lin", lower, upper, nominal, 1])

    observables_path = directory / "observables.tsv"
    measurements_path = directory / "measurements.tsv"
    conditions_path = directory / "conditions.tsv"
    parameters_path = directory / "parameters.tsv"

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
    )


def _sbml_symbol_maps(sbml_text: str) -> tuple[dict[str, str], set[str]]:
    """Return (species name->id, parameter ids) from the exported SBML.

    ``to_sbml`` sets each species/parameter *name* to the original FungMod name
    and its *id* to the sanitized symbol. Observables map by species name (a
    FungMod state name); parameters map by their sanitized-symbol id.
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
    parameter_ids = {model.getParameter(i).getId() for i in range(model.getNumParameters())}
    return species_name_to_id, parameter_ids


__all__ = ["PETAB_FORMAT_VERSION", "PetabExport", "PetabExportError", "calibration_config_to_petab"]
