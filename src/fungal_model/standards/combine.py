"""COMBINE archive (.omex) generation for FungMod models.

A `COMBINE archive <https://combinearchive.org/>`_ bundles a model and the
simulation that runs it into a single, self-describing ``.omex`` file: a ZIP that
contains an OMEX ``manifest.xml`` declaring the format of each entry. This module
bundles a FungMod-exported SBML model (:mod:`fungal_model.standards.sbml`) with a
SED-ML simulation description (:mod:`fungal_model.standards.sedml`) so a single
file fully describes a runnable virtual experiment.

The archive is built with the standard library (``zipfile``) so it has no extra
native dependency and is byte-reproducible (fixed entry order and timestamps).
"""

from __future__ import annotations

import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING
from xml.sax.saxutils import quoteattr

from fungal_model.core.units import Q_, Quantity
from fungal_model.standards.sbml import MiriamAnnotation, to_sbml
from fungal_model.standards.sedml import to_sedml

if TYPE_CHECKING:
    from fungal_model.processes.assembly import AssembledModel

_OMEX_MANIFEST_NS = "http://identifiers.org/combine.specifications/omex-manifest"
_FORMAT_OMEX = "http://identifiers.org/combine.specifications/omex"
_FORMAT_MANIFEST = "http://identifiers.org/combine.specifications/omex-manifest"
_FORMAT_SBML = "http://identifiers.org/combine.specifications/sbml"
_FORMAT_SEDML = "http://identifiers.org/combine.specifications/sed-ml"

# Fixed timestamp for byte-reproducible archives (ZIP epoch lower bound).
_FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _omex_manifest(entries: list[tuple[str, str, bool]]) -> str:
    """Build an OMEX ``manifest.xml`` from (location, format, is_master) rows."""

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<omexManifest xmlns="{_OMEX_MANIFEST_NS}">',
        f'  <content location="." format={quoteattr(_FORMAT_OMEX)}/>',
        f'  <content location="./manifest.xml" format={quoteattr(_FORMAT_MANIFEST)}/>',
    ]
    for location, content_format, is_master in entries:
        master = " master=\"true\"" if is_master else ""
        lines.append(
            f'  <content location={quoteattr("./" + location)} '
            f"format={quoteattr(content_format)}{master}/>"
        )
    lines.append("</omexManifest>")
    return "\n".join(lines) + "\n"


def _write_zip(path: Path, members: list[tuple[str, str]]) -> None:
    """Write ``members`` (name, text) to a deterministic ZIP at ``path``."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, text in sorted(members):
            info = zipfile.ZipInfo(name, date_time=_FIXED_ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, text)


def write_combine_archive(
    model: "AssembledModel",
    path: str | Path,
    *,
    initial_state: Mapping[str, Quantity],
    output_end_time: Quantity,
    number_of_steps: int,
    output_start_time: Quantity | None = None,
    model_source: str = "model.xml",
    sedml_source: str = "simulation.sedml",
    model_id: str = "fungmod_model",
    model_name: str | None = None,
    annotations: Mapping[str, Sequence[MiriamAnnotation]] | None = None,
) -> Path:
    """Write a COMBINE archive bundling the model's SBML and a SED-ML time course.

    Args:
        model: An SBML-exportable assembled model.
        path: Destination ``.omex`` path.
        initial_state: Initial value for each state variable.
        output_end_time: Simulation end time (a pint quantity).
        number_of_steps: Number of uniform output steps.
        output_start_time: Output start time (defaults to 0 seconds).
        model_source: Filename for the SBML entry inside the archive.
        sedml_source: Filename for the SED-ML entry inside the archive.
        model_id: SBML/SED-ML model identifier.
        model_name: Human-readable model name.

    Returns:
        The path to the written archive.
    """

    sbml_text = to_sbml(
        model, initial_state=initial_state, model_id=model_id, model_name=model_name, annotations=annotations
    )
    sedml_text = to_sedml(
        sbml_text,
        output_end_time=output_end_time,
        number_of_steps=number_of_steps,
        output_start_time=output_start_time,
        model_source=model_source,
        model_id=model_id,
    )
    manifest = _omex_manifest(
        [(model_source, _FORMAT_SBML, False), (sedml_source, _FORMAT_SEDML, True)]
    )
    destination = Path(path)
    _write_zip(
        destination,
        [
            ("manifest.xml", manifest),
            (model_source, sbml_text),
            (sedml_source, sedml_text),
        ],
    )
    return destination


def model_config_to_combine_archive(
    config_path: str | Path,
    path: str | Path,
    *,
    output_end_time: Quantity | None = None,
    number_of_steps: int | None = None,
    output_start_time: Quantity | None = None,
) -> Path:
    """Load a model config, assemble it, and write a COMBINE archive.

    When ``output_end_time``/``number_of_steps`` are omitted they default to the
    config's own time span and evaluation grid.
    """

    from fungal_model.io.model_config import load_model_config
    from fungal_model.workflows.configured_inputs import ConfiguredInputLoader
    from fungal_model.workflows.configured_processes import ConfiguredProcessAssembler

    config = load_model_config(config_path)
    inputs = ConfiguredInputLoader().load(config)
    assembly = ConfiguredProcessAssembler().assemble(config, inputs)

    end_time = inputs.t_span[1] if output_end_time is None else output_end_time
    if number_of_steps is None:
        t_eval = getattr(inputs, "t_eval", None)
        number_of_steps = (len(t_eval) - 1) if t_eval is not None and len(t_eval) > 1 else 50
    if number_of_steps < 1:
        number_of_steps = 50

    return write_combine_archive(
        assembly.model,
        path,
        initial_state=inputs.initial_state,
        output_end_time=Q_(end_time),
        number_of_steps=number_of_steps,
        output_start_time=output_start_time,
        model_id=config.name,
        model_name=config.name,
    )


__all__ = ["model_config_to_combine_archive", "write_combine_archive"]
