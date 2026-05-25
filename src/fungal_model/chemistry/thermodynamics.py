"""Thermodynamic metadata interfaces.

Stage 7 records approximate Gibbs free energy estimates when available. The
framework does not yet enforce full thermodynamic flux analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.provenance import ProvenanceError, UnknownParameterError, has_text
from fungal_model.core.units import Quantity, assert_compatible


@dataclass(frozen=True)
class GibbsFreeEnergyEstimate:
    """Approximate Gibbs free energy estimate with provenance."""

    reaction_name: str
    delta_gibbs: Parameter
    conditions: ParameterSet = field(default_factory=ParameterSet)
    source: str | None = None
    notes: str = ""

    def validate(
        self,
        *,
        allow_unsourced_for_testing: bool = False,
        require_value: bool = False,
    ) -> None:
        if not allow_unsourced_for_testing and not has_text(self.source):
            raise ProvenanceError(f"Gibbs free energy estimate for {self.reaction_name!r} is missing a source.")
        self.delta_gibbs.validate_provenance(allow_unsourced_for_testing=allow_unsourced_for_testing)
        if require_value:
            self.delta_gibbs.validate_value()
        if self.delta_gibbs.quantity is not None:
            assert_compatible(self.delta_gibbs.quantity, "joule / mole", name=self.delta_gibbs.symbol)
        self.conditions.validate(
            allow_unsourced_for_testing=allow_unsourced_for_testing,
            require_values=False,
        )

    def value(self) -> Quantity:
        quantity = self.delta_gibbs.quantity
        if quantity is None:
            raise UnknownParameterError(f"Delta G for {self.reaction_name} is unknown.")
        return assert_compatible(quantity, "joule / mole", name=self.delta_gibbs.symbol)

    def is_exergonic(self) -> bool | None:
        if self.delta_gibbs.quantity is None:
            return None
        value = self.value()
        return bool(np.all(np.asarray(value.magnitude, dtype=float) < 0.0))

    def to_dict(self) -> dict[str, Any]:
        return {
            "reaction_name": self.reaction_name,
            "delta_gibbs": self.delta_gibbs.to_dict(),
            "conditions": self.conditions.to_dict(),
            "source": self.source,
            "notes": self.notes,
        }


__all__ = ["GibbsFreeEnergyEstimate"]
