"""SED-ML export for FungMod models exported to SBML.

`SED-ML <https://sed-ml.org/>`_ (the Simulation Experiment Description Markup
Language) describes *how* to run a model: which model file, what simulation, and
what to report. This module builds a **SED-ML Level 1 Version 4** document that
runs a uniform time course over a FungMod-exported SBML model and reports the
time course of every species.

The SED-ML references the SBML by a relative source filename, so it pairs with a
COMBINE archive (see :mod:`fungal_model.standards.combine`). Species targets are
read from the SBML document itself, so identifiers always match.
"""

from __future__ import annotations

from typing import Any

from fungal_model.core.units import Q_, Quantity
from fungal_model.standards.sbml import SbmlExportError

# KISAO:0000019 = CVODE, a standard deterministic ODE solver.
DEFAULT_KISAO_ID = "KISAO:0000019"
SBML_L3V2_LANGUAGE_URN = "urn:sedml:language:sbml.level-3.version-2"


def _require_libsedml() -> Any:
    try:
        import libsedml
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised via error path
        raise SbmlExportError(
            "SED-ML export requires the optional 'standards' dependency. "
            "Install it with: pip install fungmod[standards]"
        ) from exc
    return libsedml


def _species_ids_and_names(sbml: str) -> list[tuple[str, str]]:
    import libsbml

    document = libsbml.readSBMLFromString(sbml)
    model = document.getModel()
    if model is None:
        raise SbmlExportError("Could not parse the SBML document for SED-ML export.")
    return [
        (model.getSpecies(i).getId(), model.getSpecies(i).getName() or model.getSpecies(i).getId())
        for i in range(model.getNumSpecies())
    ]


def to_sedml(
    sbml: str,
    *,
    output_end_time: Quantity,
    number_of_steps: int,
    output_start_time: Quantity | None = None,
    model_source: str = "model.xml",
    model_id: str = "fungmod_model",
    simulation_id: str = "simulation",
    task_id: str = "task",
    report_id: str = "report",
    kisao_id: str = DEFAULT_KISAO_ID,
) -> str:
    """Build a SED-ML document running a uniform time course over ``sbml``.

    Args:
        sbml: An SBML document (as produced by
            :func:`fungal_model.standards.sbml.to_sbml`).
        output_end_time: Simulation end time (a pint quantity; converted to seconds).
        number_of_steps: Number of uniform output steps.
        output_start_time: Output start time (defaults to 0 seconds).
        model_source: Relative filename the SED-ML uses to reference the SBML.
        model_id: SED-ML model element identifier.
        simulation_id: SED-ML simulation element identifier.
        task_id: SED-ML task element identifier.
        report_id: SED-ML report element identifier.
        kisao_id: KiSAO term for the solver algorithm (default CVODE).

    Returns:
        The SED-ML document serialized as an XML string.
    """

    libsedml = _require_libsedml()

    end_seconds = float(Q_(output_end_time).to("second").magnitude)
    start_seconds = 0.0 if output_start_time is None else float(Q_(output_start_time).to("second").magnitude)
    if number_of_steps < 1:
        raise SbmlExportError("number_of_steps must be a positive integer.")

    document = libsedml.SedDocument(1, 4)

    model = document.createModel()
    model.setId(model_id)
    model.setLanguage(SBML_L3V2_LANGUAGE_URN)
    model.setSource(model_source)

    simulation = document.createUniformTimeCourse()
    simulation.setId(simulation_id)
    simulation.setInitialTime(start_seconds)
    simulation.setOutputStartTime(start_seconds)
    simulation.setOutputEndTime(end_seconds)
    simulation.setNumberOfSteps(int(number_of_steps))
    algorithm = simulation.createAlgorithm()
    algorithm.setKisaoID(kisao_id)

    task = document.createTask()
    task.setId(task_id)
    task.setModelReference(model_id)
    task.setSimulationReference(simulation_id)

    report = document.createReport()
    report.setId(report_id)

    # Time data generator.
    _add_data_generator(
        libsedml, document, report,
        generator_id="time", label="time", task_id=task_id,
        symbol="urn:sedml:symbol:time",
    )

    # One data generator + dataset per species.
    for species_id, species_name in _species_ids_and_names(sbml):
        target = f"/sbml:sbml/sbml:model/sbml:listOfSpecies/sbml:species[@id='{species_id}']"
        _add_data_generator(
            libsedml, document, report,
            generator_id=f"dg_{species_id}", label=species_name, task_id=task_id,
            target=target,
        )

    _raise_on_sedml_errors(libsedml, document)
    return libsedml.writeSedMLToString(document)


def _add_data_generator(
    libsedml: Any,
    document: Any,
    report: Any,
    *,
    generator_id: str,
    label: str,
    task_id: str,
    symbol: str | None = None,
    target: str | None = None,
) -> None:
    variable_id = f"var_{generator_id}"
    generator = document.createDataGenerator()
    generator.setId(generator_id)
    variable = generator.createVariable()
    variable.setId(variable_id)
    variable.setTaskReference(task_id)
    if symbol is not None:
        variable.setSymbol(symbol)
    if target is not None:
        variable.setTarget(target)
    math = libsedml.parseFormula(variable_id)
    if math is None:  # pragma: no cover - defensive
        raise SbmlExportError(f"Failed to build SED-ML math for {generator_id!r}.")
    generator.setMath(math)

    dataset = report.createDataSet()
    dataset.setId(f"ds_{generator_id}")
    dataset.setLabel(label)
    dataset.setDataReference(generator_id)


def _raise_on_sedml_errors(libsedml: Any, document: Any) -> None:
    problems = []
    log = document.getErrorLog()
    for index in range(log.getNumErrors()):
        error = log.getError(index)
        if error.getSeverity() >= libsedml.LIBSEDML_SEV_ERROR:
            problems.append(f"[{error.getErrorId()}] {error.getMessage().strip()}")
    if problems:
        raise SbmlExportError("SED-ML export produced an invalid document:\n" + "\n".join(problems))


__all__ = ["DEFAULT_KISAO_ID", "to_sedml"]
