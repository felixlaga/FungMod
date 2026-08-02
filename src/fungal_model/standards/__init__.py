"""Community-standard exchange formats for FungMod models.

This subpackage exports FungMod models to interoperable systems-biology
standards. It is optional: install the extra with ``pip install fungmod[standards]``.

Currently supported:

- **SBML** (Systems Biology Markup Language) Level 3 export for the supported
  well-mixed kinetic processes (first-order decay, mass action, and homogeneous
  Michaelis-Menten). See :mod:`fungal_model.standards.sbml`.
"""

from __future__ import annotations

from fungal_model.standards.combine import (
    model_config_to_combine_archive,
    write_combine_archive,
)
from fungal_model.standards.cross_engine import (
    CrossEngineComparison,
    cross_engine_trajectory_check,
    simulate_reference_sbml,
)
from fungal_model.standards.sbml import (
    SBML_EXPORTABLE_PROCESS_TYPES,
    SbmlExportError,
    model_config_to_sbml,
    to_sbml,
    write_model_config_sbml,
    write_sbml,
)
from fungal_model.standards.sedml import DEFAULT_KISAO_ID, to_sedml

__all__ = [
    "DEFAULT_KISAO_ID",
    "SBML_EXPORTABLE_PROCESS_TYPES",
    "CrossEngineComparison",
    "SbmlExportError",
    "cross_engine_trajectory_check",
    "model_config_to_combine_archive",
    "model_config_to_sbml",
    "simulate_reference_sbml",
    "to_sbml",
    "to_sedml",
    "write_combine_archive",
    "write_model_config_sbml",
    "write_sbml",
]
