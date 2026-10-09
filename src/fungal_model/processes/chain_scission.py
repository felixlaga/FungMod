"""Finite-chain endo/exo scission with exact chain-end exhaustion.

Niu, Shah & Kontoravdi (2016), doi:10.1016/j.bej.2015.10.017, Eqs 12-20.
This implements the scission submodel, not the full published model. Ends
are derived from the chain populations; an independently integrated end
pool would permit physically inconsistent material and end counts.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.kernels import JacobianKernel, KernelContext, RateKernel, conversion_factor
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Q_, Quantity, assert_compatible
from fungal_model.kinetics.chain_scission import chain_scission_rate_and_gradient
from fungal_model.processes.base import ParameterRequirement, Process, StateVariableSpec, ValidityDomain

CHAIN_SOURCE = "Niu et al. 2016, doi:10.1016/j.bej.2015.10.017, Eqs 12-20; data/mechanism_sources/niu2016_chain_scission/source.yml"


def _chain_structure(chain_states: Mapping[int, str], solid_min_length: int) -> dict[int, str]:
    if type(solid_min_length) is not int or solid_min_length < 2:
        raise ValueError("solid_min_length must be an integer at least 2.")
    if any(type(length) is not int for length in chain_states):
        raise ValueError("chain_states must contain every integer length from 1 to maximum.")
    chains = dict(sorted(chain_states.items()))
    if not chains or set(chains) != set(range(1, max(chains) + 1)):
        raise ValueError("chain_states must contain every integer length from 1 to maximum.")
    if max(chains) < solid_min_length:
        raise ValueError("chain_states must include at least one solid chain.")
    if any(not isinstance(name, str) or not name.strip() for name in chains.values()):
        raise ValueError("Chain state names must be nonempty strings.")
    return chains


@dataclass(frozen=True, init=False)
class ChainScissionProcess(Process):
    """One exact cleavage channel in an explicit chain-length population.

    ``mode='endo'`` uses bond-weighted competition and uniform cut positions.
    ``mode='exo'`` uses chain-end competition. ``fragment_length`` is the cut
    position for endo, or the released terminal oligomer length for exo.
    ``solid_min_length`` and ``fragment_length`` are structural definitions,
    not fitted constants; values other than the sourced DP4/dimer convention
    must be described by the caller's source and remain exploratory.
    """

    chain_states: Mapping[int, str]
    parent_length: int
    fragment_length: int
    mode: Literal["endo", "exo"]
    solid_min_length: int
    enzyme_state: str
    kcat_symbol: str
    km_symbol: str
    accessible_fraction_symbol: str
    state_units: str
    enzyme_units: str
    rate_units: str

    def __init__(
        self,
        *,
        name: str,
        chain_states: Mapping[int, str],
        parent_length: int,
        fragment_length: int,
        mode: Literal["endo", "exo"],
        solid_min_length: int,
        enzyme_state: str,
        kcat_symbol: str,
        km_symbol: str,
        accessible_fraction_symbol: str,
        state_units: str,
        enzyme_units: str,
        source: str,
        rate_units: str | None = None,
        notes: str = "",
    ) -> None:
        if not source.strip():
            raise ValueError("Chain scission requires a source for its structural assumptions.")
        chains = _chain_structure(chain_states, solid_min_length)
        if type(parent_length) is not int or type(fragment_length) is not int:
            raise ValueError("parent_length and fragment_length must be integers.")
        if len(set(chains.values())) != len(chains) or enzyme_state in chains.values():
            raise ValueError("Chain and enzyme state names must be distinct.")
        if mode not in ("endo", "exo") or solid_min_length < 2:
            raise ValueError("mode must be endo or exo and solid_min_length at least 2.")
        if parent_length not in chains or parent_length < solid_min_length:
            raise ValueError("parent_length must identify a solid chain.")
        if not 1 <= fragment_length < parent_length:
            raise ValueError("fragment_length must lie strictly within the parent chain.")
        # Concentration bases may scale, but mass/activity-to-mole conversion is never implicit.
        assert_compatible(Q_(1, state_units), "mole/liter", name="chain concentration")
        assert_compatible(Q_(1, enzyme_units), state_units, name="enzyme concentration")
        rate_units = rate_units or f"{state_units}/second"
        required = tuple(
            StateVariableSpec(v, state_units, role="substrate" if i >= solid_min_length else "soluble chain")
            for i, v in chains.items()
        )
        changed_names = set((chains[parent_length], chains[fragment_length], chains[parent_length - fragment_length]))
        Process.__init__(
            self,
            name=name,
            process_type=f"chain_{mode}_scission",
            required_state_variables=required + (StateVariableSpec(enzyme_state, enzyme_units, role="enzyme"),),
            changed_state_variables=tuple(
                StateVariableSpec(v, state_units, role="product") for v in sorted(changed_names)
            ),
            required_parameters=(
                ParameterRequirement(kcat_symbol, "1/second"),
                ParameterRequirement(km_symbol, state_units),
                ParameterRequirement(accessible_fraction_symbol, "dimensionless"),
            ),
            assumptions=(
                Assumption(
                    name="finite-chain scission",
                    description="Explicit chain populations with uniform accessible bond cutting or terminal shortening.",
                    justification="The source supplies exact creation and exhaustion bookkeeping.",
                    known_limitations="No stalling, crystallinity or spatial transport. Alternative structural conventions require separate evidence.",
                    source=CHAIN_SOURCE,
                ),
            ),
            validity=ValidityDomain(
                description="Finite-chain population scission, software_tested.",
                labels=("software_tested", "chain_end"),
                limitations=("The full source model is not reproduced; no biological constants are supplied.",),
            ),
            source=source,
            notes=notes,
        )
        for key, value in locals().copy().items():
            if key in self.__annotations__:
                object.__setattr__(self, key, chains if key == "chain_states" else value)

    def _constants(self, parameters: ParameterSet) -> tuple[float, float, float]:
        return cast(
            tuple[float, float, float],
            tuple(
                float(parameters.require_quantity(symbol, units).magnitude)
                for symbol, units in (
                    (self.kcat_symbol, "1/second"),
                    (self.km_symbol, self.state_units),
                    (self.accessible_fraction_symbol, "dimensionless"),
                )
            ),
        )

    def _solid(self) -> list[tuple[int, str]]:
        return [(i, n) for i, n in self.chain_states.items() if i >= self.solid_min_length]

    def rate(
        self,
        state: Mapping[str, Quantity],
        time: Quantity,
        parameters: ParameterSet,
        environment: Any = None,
        geometry: Any = None,
    ) -> Quantity:
        del time, environment, geometry
        solid = self._solid()
        kcat, km, fraction = self._constants(parameters)
        rate, _, _ = chain_scission_rate_and_gradient(
            enzyme=float(assert_compatible(state[self.enzyme_state], self.state_units).magnitude),
            chains=np.array([float(assert_compatible(state[n], self.state_units).magnitude) for _, n in solid]),
            weights=np.array([i - 1 if self.mode == "endo" else 1 for i, _ in solid], dtype=float),
            parent_index=[i for i, _ in solid].index(self.parent_length),
            kcat=kcat,
            km=km,
            accessible_fraction=fraction,
        )
        return Q_(rate, f"{self.state_units}/second").to(self.rate_units)

    def _compiled(self, context: KernelContext) -> tuple[RateKernel, JacobianKernel]:
        solid = self._solid()
        slots = [context.state_slot(n, self.state_units) for _, n in solid]
        ei, ef = context.state_slot(self.enzyme_state, self.state_units)
        kcat, km, fraction = self._constants(context.parameters)
        weights = np.array([i - 1 if self.mode == "endo" else 1 for i, _ in solid], dtype=float)
        parent = [i for i, _ in solid].index(self.parent_length)
        scale = conversion_factor(f"{self.state_units}/second", self.rate_units)

        def values(y: np.ndarray) -> tuple[float, float, np.ndarray]:
            return chain_scission_rate_and_gradient(
                enzyme=y[ei] * ef,
                chains=np.array([y[i] * f for i, f in slots]),
                weights=weights,
                parent_index=parent,
                kcat=kcat,
                km=km,
                accessible_fraction=fraction,
            )

        def kernel(t: float, y: np.ndarray) -> float:
            return values(y)[0] * scale

        def gradient(t: float, y: np.ndarray) -> np.ndarray:
            _, de, dc = values(y)
            result = np.zeros(len(context.state_index))
            result[ei] = de * ef * scale
            for (index, factor), value in zip(slots, dc, strict=True):
                result[index] += value * factor * scale
            return result

        return kernel, gradient

    def compile_rate(self, context: KernelContext) -> RateKernel:
        return self._compiled(context)[0]

    def compile_jacobian(self, context: KernelContext) -> JacobianKernel:
        return self._compiled(context)[1]

    def contributions(self, rate: Quantity) -> Mapping[str, Quantity]:
        value = assert_compatible(rate, self.rate_units)
        result: dict[str, Quantity] = {self.chain_states[self.parent_length]: cast(Quantity, -value)}
        for length in (self.fragment_length, self.parent_length - self.fragment_length):
            name = self.chain_states[length]
            result[name] = cast(Quantity, result.get(name, cast(Quantity, value * 0)) + value)
        return result

    def derived_quantities(self, states: Mapping[str, Quantity], parameters: ParameterSet) -> dict[str, Quantity]:
        del parameters
        return chain_observables(states, self.chain_states, solid_min_length=self.solid_min_length)

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result.update({name: getattr(self, name) for name in self.__annotations__})
        return result


def chain_scission_processes(
    *,
    name: str,
    chain_states: Mapping[int, str],
    mode: Literal["endo", "exo"],
    solid_min_length: int,
    enzyme_state: str,
    kcat_symbol: str,
    km_symbol: str,
    accessible_fraction_symbol: str,
    state_units: str,
    enzyme_units: str,
    source: str,
    exo_fragment_length: int | None = None,
) -> tuple[ChainScissionProcess, ...]:
    """Expand a complete finite-chain scission family without missing fragments."""
    chain_states = _chain_structure(chain_states, solid_min_length)
    if mode not in ("endo", "exo"):
        raise ValueError("mode must be endo or exo.")
    if mode == "exo" and (type(exo_fragment_length) is not int or not 1 <= exo_fragment_length < solid_min_length):
        raise ValueError("Exo action requires an explicit soluble fragment length below solid_min_length.")
    return tuple(
        ChainScissionProcess(
            name=f"{name}_{i}_{j}",
            chain_states=chain_states,
            parent_length=i,
            fragment_length=cast(int, j),
            mode=mode,
            solid_min_length=solid_min_length,
            enzyme_state=enzyme_state,
            kcat_symbol=kcat_symbol,
            km_symbol=km_symbol,
            accessible_fraction_symbol=accessible_fraction_symbol,
            state_units=state_units,
            enzyme_units=enzyme_units,
            source=source,
        )
        for i in sorted(chain_states)
        if i >= solid_min_length
        for j in (range(1, i) if mode == "endo" else (exo_fragment_length,))
    )


def chain_observables(
    state: Mapping[str, Quantity], chain_states: Mapping[int, str], *, solid_min_length: int
) -> dict[str, Quantity]:
    """Material, soluble monomer-equivalents and one attackable end per solid chain."""
    if not chain_states:
        raise ValueError("chain_states cannot be empty.")
    zero = state[next(iter(chain_states.values()))] * 0
    return {
        "material_equivalents": sum((i * state[n] for i, n in chain_states.items()), zero),
        "solid_equivalents": sum((i * state[n] for i, n in chain_states.items() if i >= solid_min_length), zero),
        "soluble_equivalents": sum((i * state[n] for i, n in chain_states.items() if i < solid_min_length), zero),
        "chain_ends": sum((state[n] for i, n in chain_states.items() if i >= solid_min_length), zero),
    }
