"""Factory for the endogenous maintenance extent of the resource-limited closure.

The factory reads the same closure fields as ``resource_limited_growth`` and
``resource_limited_maintenance`` (``states``, ``parameters``, ``stoichiometry``)
plus ``parameters.endogenous_yield``, the symbol of the caller's ``Y_e``. It is
not registered with ``default_foundation_factories`` here; the integrator
registers it (integrator wiring).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fungal_model.processes.base import Process
from fungal_model.processes.culture import (
    ENDOGENOUS_MAINTENANCE_PROCESS_TYPE,
    EndogenousMaintenanceProcess,
)
from fungal_model.processes.factories import (
    BuildDecision,
    ProcessBuildContext,
    _apply_rate_modifiers,
    _closure_kwargs,
    _closure_missing,
    _decision,
    _mapping,
    _require_buildable,
)

ENDOGENOUS_YIELD_FIELD = "endogenous_yield"


@dataclass(frozen=True)
class EndogenousMaintenanceFactory:
    """Build the biomass-oxidising endogenous maintenance extent from config."""

    process_type: str = ENDOGENOUS_MAINTENANCE_PROCESS_TYPE

    def can_build(self, context: ProcessBuildContext, process_config: Any) -> BuildDecision:
        return _decision(
            self, missing_fields=_closure_missing(context, process_config, extra_parameters=(ENDOGENOUS_YIELD_FIELD,))
        )

    def build(self, context: ProcessBuildContext, process_config: Any) -> Process:
        _require_buildable(self.can_build(context, process_config))
        parameters = _mapping(process_config.parameters)
        process = EndogenousMaintenanceProcess(
            **_closure_kwargs(context, process_config),
            endogenous_yield_symbol=str(parameters[ENDOGENOUS_YIELD_FIELD]),
            notes="Built from generic endogenous maintenance config.",
        )
        return _apply_rate_modifiers(context, process_config, process)


__all__ = ["ENDOGENOUS_YIELD_FIELD", "EndogenousMaintenanceFactory"]
