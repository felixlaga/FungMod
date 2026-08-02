"""Community-standard exchange formats for FungMod models.

This subpackage exports FungMod models to interoperable systems-biology
standards. It is optional: install the extra with ``pip install fungmod[standards]``.

Currently supported:

- **SBML** (Systems Biology Markup Language) Level 3 export for the supported
  well-mixed kinetic processes (first-order decay, mass action, and homogeneous
  Michaelis-Menten). See :mod:`fungal_model.standards.sbml`.
"""

from __future__ import annotations

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

__all__ = [
    "SBML_EXPORTABLE_PROCESS_TYPES",
    "CrossEngineComparison",
    "SbmlExportError",
    "cross_engine_trajectory_check",
    "model_config_to_sbml",
    "simulate_reference_sbml",
    "to_sbml",
    "write_model_config_sbml",
    "write_sbml",
]
