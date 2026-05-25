"""Generic reactions for deterministic ODE systems."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.provenance import ProvenanceError, has_text
from fungal_model.core.units import Q_, Quantity, UnitError, assert_compatible

RateLaw = Callable[[Mapping[str, Quantity], Quantity, ParameterSet], Quantity]


@dataclass
class Reaction:
    """A reaction with stoichiometry and a unit-aware rate law.

    The rate law must return a pint quantity compatible with ``rate_units``.
    Stoichiometric coefficients are positive in ``reactants`` and ``products``;
    the signed coefficient is computed as products minus reactants.
    """

    name: str
    reactants: Mapping[str, float]
    products: Mapping[str, float]
    rate_law: RateLaw
    rate_units: str
    assumptions: list[Assumption] = field(default_factory=list)
    source: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Reaction.name must be provided.")
        self.reactants = dict(self.reactants)
        self.products = dict(self.products)
        if not self.reactants and not self.products:
            raise ValueError(f"Reaction {self.name} must include at least one species.")
        for collection_name, collection in (
            ("reactants", self.reactants),
            ("products", self.products),
        ):
            for species, coefficient in collection.items():
                if coefficient < 0:
                    raise ValueError(
                        f"Reaction {self.name} has a negative coefficient for "
                        f"{species} in {collection_name}."
                    )
        assert_compatible(Q_(1, self.rate_units), self.rate_units, name=f"{self.name} rate_units")

    @property
    def species(self) -> set[str]:
        return set(self.reactants) | set(self.products)

    def stoichiometric_coefficient(self, species: str) -> float:
        return float(self.products.get(species, 0.0) - self.reactants.get(species, 0.0))

    def rate(
        self,
        state: Mapping[str, Quantity],
        time: Quantity,
        parameters: ParameterSet,
    ) -> Quantity:
        value = self.rate_law(state, time, parameters)
        if not hasattr(value, "units"):
            raise UnitError(f"Reaction {self.name} rate law returned a value without units.")
        return assert_compatible(value, self.rate_units, name=f"{self.name} rate")

    def validate_provenance(self, allow_unsourced_for_testing: bool = False) -> None:
        if allow_unsourced_for_testing:
            return
        if not has_text(self.source) and not self.assumptions:
            raise ProvenanceError(
                f"Reaction {self.name} requires a source or explicit modelling assumptions."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "reactants": dict(self.reactants),
            "products": dict(self.products),
            "rate_units": self.rate_units,
            "assumptions": [assumption.to_dict() for assumption in self.assumptions],
            "source": self.source,
            "notes": self.notes,
        }


__all__ = ["RateLaw", "Reaction"]
