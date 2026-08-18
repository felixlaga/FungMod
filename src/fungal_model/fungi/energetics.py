"""Thermodynamic bounds on growth energetics.

Biomass yield is not a free parameter. Growth couples an exergonic catabolic
reaction to an endergonic anabolic one, and the coupled system cannot create
free energy. If forming one unit of biomass requires `dG_anabolic > 0` and
consuming one unit of substrate releases `|dG_catabolic|`, then

    Y_max = |dG_catabolic| / dG_anabolic

is a hard ceiling on biomass produced per substrate consumed. Every real
organism sits strictly below it, because real growth dissipates energy rather
than operating reversibly.

This is the one place where fundamental thermodynamics does useful predictive
work in FungMod. It cannot supply a reaction rate, because rate depends on an
enzyme's activation barrier rather than on the reaction's Gibbs energy. It can
bound an organism-level parameter that is otherwise left entirely free, and it
does so without any organism-specific measurement.

The bound is an upper limit, never an estimate. A model that sets its yield at
the bound is claiming reversible, zero-dissipation growth, which is
thermodynamically permitted and biologically false. Both Gibbs energies must be
supplied as sourced parameters; nothing here invents an energy value.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from fungal_model.core.parameters import Parameter
from fungal_model.core.provenance import ProvenanceError, has_text
from fungal_model.core.units import Quantity, assert_compatible
from fungal_model.core.validators import ValidationResult


class GrowthEnergeticsError(ValueError):
    """Raised when a growth-energetics bound cannot be formed or is violated."""


@dataclass(frozen=True)
class GibbsEnergyYieldBound:
    """A thermodynamic upper bound on biomass yield from sourced Gibbs energies.

    `catabolic_delta_gibbs` is the free energy released per unit of substrate or
    degradation product catabolised and must be negative. `anabolic_delta_gibbs`
    is the free energy required per unit of biomass formed and must be positive.
    The resulting bound carries units of biomass per substrate.
    """

    catabolic_delta_gibbs: Parameter
    anabolic_delta_gibbs: Parameter

    def __post_init__(self) -> None:
        for parameter in (self.catabolic_delta_gibbs, self.anabolic_delta_gibbs):
            if parameter.value is None:
                raise GrowthEnergeticsError(
                    f"Gibbs energy {parameter.symbol!r} must have an explicit value."
                )
            if not has_text(parameter.source):
                raise ProvenanceError(
                    f"Gibbs energy {parameter.symbol!r} requires a source; this bound "
                    "does not invent energy values."
                )
        if self._catabolic_magnitude() >= 0.0:
            raise GrowthEnergeticsError(
                "catabolic_delta_gibbs must be negative: catabolism must release free energy."
            )
        if self._anabolic_magnitude() <= 0.0:
            raise GrowthEnergeticsError(
                "anabolic_delta_gibbs must be positive: biomass synthesis must require free energy."
            )

    @staticmethod
    def _quantity(parameter: Parameter) -> Quantity:
        """Return a parameter's quantity, narrowing away the optional value."""

        quantity = parameter.quantity
        if quantity is None:
            raise GrowthEnergeticsError(
                f"Gibbs energy {parameter.symbol!r} must have an explicit value with units."
            )
        return quantity

    def _catabolic_magnitude(self) -> float:
        return float(self._quantity(self.catabolic_delta_gibbs).magnitude)

    def _anabolic_magnitude(self) -> float:
        return float(self._quantity(self.anabolic_delta_gibbs).magnitude)

    def maximum_yield(self) -> Quantity:
        """Return the reversible-limit yield ceiling, biomass per substrate."""

        catabolic = self._quantity(self.catabolic_delta_gibbs)
        anabolic = self._quantity(self.anabolic_delta_gibbs)
        return abs(catabolic) / anabolic

    def validate_yield(
        self,
        declared_yield: Quantity,
        *,
        symbol: str = "Y_B",
    ) -> ValidationResult:
        """Check a declared yield against the thermodynamic ceiling."""

        bound = self.maximum_yield()
        declared = assert_compatible(declared_yield, str(bound.units), name=symbol)
        declared_value = float(declared.to(bound.units).magnitude)
        bound_value = float(bound.magnitude)
        if not math.isfinite(declared_value) or declared_value < 0.0:
            raise GrowthEnergeticsError(f"{symbol} must be finite and non-negative.")
        passed = declared_value <= bound_value
        fraction = declared_value / bound_value if bound_value > 0 else math.inf
        return ValidationResult(
            name="gibbs_energy_yield_bound",
            passed=passed,
            message=(
                f"{symbol} is within the thermodynamic ceiling."
                if passed
                else (
                    f"{symbol} exceeds the thermodynamic ceiling: the configured growth "
                    "would create free energy, which is impossible."
                )
            ),
            details={
                "symbol": symbol,
                "declared_yield": declared_value,
                "maximum_yield": bound_value,
                "units": str(bound.units),
                "fraction_of_ceiling": fraction,
                "catabolic_delta_gibbs_source": self.catabolic_delta_gibbs.source,
                "anabolic_delta_gibbs_source": self.anabolic_delta_gibbs.source,
                "interpretation": (
                    "The ceiling assumes reversible, zero-dissipation growth. Real "
                    "organisms operate strictly below it, so a declared yield close to "
                    "the ceiling should itself be treated as suspect."
                ),
            },
        )

    def enforce_yield(self, declared_yield: Quantity, *, symbol: str = "Y_B") -> ValidationResult:
        """Validate a declared yield and raise when it exceeds the ceiling."""

        result = self.validate_yield(declared_yield, symbol=symbol)
        if not result.passed:
            raise GrowthEnergeticsError(
                f"{result.message} declared={result.details['declared_yield']!r} "
                f"maximum={result.details['maximum_yield']!r} {result.details['units']}"
            )
        return result

    def to_dict(self) -> dict[str, Any]:
        bound = self.maximum_yield()
        return {
            "catabolic_delta_gibbs": self.catabolic_delta_gibbs.to_dict(),
            "anabolic_delta_gibbs": self.anabolic_delta_gibbs.to_dict(),
            "maximum_yield": float(bound.magnitude),
            "maximum_yield_units": str(bound.units),
            "claim_boundary": (
                "Upper bound only. Thermodynamics constrains yield; it does not "
                "predict a reaction rate, which depends on an enzyme's activation "
                "barrier rather than the reaction's Gibbs energy."
            ),
        }


__all__ = ["GibbsEnergyYieldBound", "GrowthEnergeticsError"]
