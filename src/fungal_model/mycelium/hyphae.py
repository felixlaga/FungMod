"""Generic continuum processes of a growing mycelium on the spatial core.

The fields are densities per unit length, area or volume of the grid: hyphal
length density (length per measure), tip density (count per measure),
internal substrate carried inside hyphae and external substrate, enzyme or
product fields. The laws are the continuum (density) forms of hyphal growth
first written down by Edelstein (1982) and extended with substrate by
Boswell et al. (2003): tips extend and lay down hyphal length, tips move with
a random-walk diffusion and an optional drift, lateral or dichotomous
branching creates tips, anastomosis removes tips that meet hyphae, hyphae and
tips are lost at first order, external substrate is taken up where hyphae
are, internal substrate translocates along hyphae, and hyphae secrete into an
external field. Every functional form is this implementation's declared
choice and is documented on the process; no parameter value is claimed from
the literature, so a model built from these processes is exploratory until a
registry record parameterises it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.errors import InvalidMechanismError
from fungal_model.mycelium.fields import FieldKernelContext, FieldSpec, RateFieldKernel, TendencyKernel
from fungal_model.mycelium.jacobian import (
    FieldJacobianKernel,
    StencilBlock,
    diffusion_stencil,
    transport_blocks,
    upwind_drift_stencil,
)
from fungal_model.mycelium.operators import (
    diffusive_tendency,
    divergence,
    drift_face_velocities,
    face_gradient,
    upwind_face_flux,
)
from fungal_model.mycelium.processes import FieldProcess
from fungal_model.processes.base import ParameterRequirement, ValidityDomain

CONTINUUM_LITERATURE = (
    "Continuum forms after Edelstein, J. Theor. Biol. 98 (1982) 679-701 and Boswell, Jacobs, Davidson, Gadd and "
    "Ritz, Bull. Math. Biol. 65 (2003) 447-477; the functional form is this implementation's declared choice and "
    "no parameter value is taken from either source."
)
LABELS_CONTINUUM = ("spatial", "mycelium", "continuum")


def _positive(value: float, *, name: str) -> float:
    if not np.isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be finite and positive.")
    return float(value)


def _non_negative(value: float, *, name: str) -> float:
    if not np.isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative.")
    return float(value)


def _spec(name: str, units: str, description: str, role: str) -> FieldSpec:
    return FieldSpec(name=name, units=units, description=description, role=role)


def _assumption(name: str, description: str, justification: str, limitations: str) -> Assumption:
    return Assumption(name=name, description=description, justification=justification, known_limitations=limitations, source=CONTINUUM_LITERATURE)


def _declare(process: FieldProcess, *, required: tuple[FieldSpec, ...], changed: tuple[FieldSpec, ...], parameters: tuple[ParameterRequirement, ...], assumption: Assumption, labels: tuple[str, ...], limitations: tuple[str, ...], failure_modes: tuple[str, ...], rate_units: str) -> None:
    object.__setattr__(process, "required_fields", required)
    object.__setattr__(process, "changed_fields", changed)
    object.__setattr__(process, "required_parameters", parameters)
    object.__setattr__(process, "assumptions", (assumption,))
    object.__setattr__(process, "validity", ValidityDomain(description=assumption.description, labels=LABELS_CONTINUUM + labels, limitations=limitations))
    object.__setattr__(process, "failure_modes", failure_modes)
    object.__setattr__(process, "rate_units", rate_units)
    if process.source is None:
        object.__setattr__(process, "source", CONTINUUM_LITERATURE)
    FieldProcess.__post_init__(process)


def _per_time(units: str, time_units: str) -> str:
    return f"({units}) / ({time_units})"


# ---------------------------------------------------------------------------
# Transport of a single field
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class FieldDiffusion(FieldProcess):
    """Fickian diffusion of one field with a constant diffusivity."""

    process_type: str = "field_diffusion"
    field: str
    field_units: str
    diffusivity_symbol: str

    def __post_init__(self) -> None:
        spec = _spec(self.field, self.field_units, "diffusing field", "field")
        _declare(
            self,
            required=(spec,),
            changed=(spec,),
            parameters=(ParameterRequirement(self.diffusivity_symbol, "meter ** 2 / hour", description="diffusivity of the field"),),
            assumption=_assumption("fickian_field_diffusion", "The field spreads by Fickian diffusion with a constant, isotropic diffusivity.", "Standard continuum transport on a uniform grid.", "No anisotropy, no dependence on the mycelium or the medium, no advection."),
            labels=("transport",),
            limitations=("constant isotropic diffusivity",),
            failure_modes=("negative diffusivity refused at compile time",),
            rate_units=_per_time(self.field_units, "hour"),
        )

    def compile_tendency(self, context: FieldKernelContext) -> TendencyKernel:
        row, _ = context.field_slot(self.field, self.field_units)
        diffusivity = _non_negative(context.parameter(self.diffusivity_symbol, f"meter ** 2 / ({context.time_units})"), name=self.diffusivity_symbol)
        grid = context.grid

        def tendency(time: float, fields: np.ndarray) -> np.ndarray:
            del time
            out = np.zeros_like(fields)
            out[row] = diffusive_tendency(fields[row], grid=grid, diffusivity=diffusivity)
            return out

        return tendency

    def compile_jacobian(self, context: FieldKernelContext) -> FieldJacobianKernel:
        row, _ = context.field_slot(self.field, self.field_units)
        diffusivity = _non_negative(context.parameter(self.diffusivity_symbol, f"meter ** 2 / ({context.time_units})"), name=self.diffusivity_symbol)
        values = diffusion_stencil(context.grid, diffusivity).values()
        return FieldJacobianKernel(blocks=transport_blocks(row, row, context.grid.ndim), values=lambda time, fields: values)


# ---------------------------------------------------------------------------
# Tips and hyphae
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class TipExtension(FieldProcess):
    """Tips extend at a speed and lay down hyphal length; optionally paid from an internal substrate.

    Hyphal density grows at ``speed * tip_density`` (Edelstein 1982). With an
    internal substrate field the speed is ``v_max * s / (K + s)`` in that
    field; with a cost field, ``cost_per_length * speed * tip_density`` is
    removed from it.
    """

    process_type: str = "tip_extension"
    tip_field: str
    tip_units: str
    hypha_field: str
    hypha_units: str
    speed_symbol: str
    substrate_field: str | None = None
    substrate_units: str | None = None
    half_saturation_symbol: str | None = None
    cost_field: str | None = None
    cost_units: str | None = None
    cost_symbol: str | None = None

    def __post_init__(self) -> None:
        if (self.substrate_field is None) != (self.substrate_units is None) or (self.substrate_field is None) != (self.half_saturation_symbol is None):
            raise InvalidMechanismError("TipExtension needs substrate_field, substrate_units and half_saturation_symbol together.")
        if (self.cost_field is None) != (self.cost_units is None) or (self.cost_field is None) != (self.cost_symbol is None):
            raise InvalidMechanismError("TipExtension needs cost_field, cost_units and cost_symbol together.")
        if self.cost_field is not None and self.cost_field != self.substrate_field:
            raise InvalidMechanismError(
                "TipExtension can only charge a cost to the internal substrate field that saturates its speed; "
                "a cost drawn from a field the speed ignores could overdraw it."
            )
        tips = _spec(self.tip_field, self.tip_units, "hyphal tip density", "tips")
        hyphae = _spec(self.hypha_field, self.hypha_units, "hyphal length density", "hyphae")
        required: list[FieldSpec] = [tips]
        changed: list[FieldSpec] = [hyphae]
        parameters: list[ParameterRequirement] = [ParameterRequirement(self.speed_symbol, "meter / hour", description="tip extension speed")]
        if self.substrate_field is not None and self.substrate_units is not None and self.half_saturation_symbol is not None:
            substrate = _spec(self.substrate_field, self.substrate_units, "internal substrate density", "internal_substrate")
            required.append(substrate)
            parameters.append(ParameterRequirement(self.half_saturation_symbol, self.substrate_units, description="half-saturation of the extension speed in the internal substrate"))
        if self.cost_field is not None and self.cost_units is not None and self.cost_symbol is not None:
            cost = _spec(self.cost_field, self.cost_units, "field paying for hyphal extension", "cost")
            changed.append(cost)
            if self.cost_field not in {spec.name for spec in required}:
                required.append(cost)
            parameters.append(ParameterRequirement(self.cost_symbol, f"({self.cost_units}) / ({self.hypha_units})", description="amount removed from the cost field per unit hyphal length created"))
        _declare(
            self,
            required=tuple(required),
            changed=tuple(changed),
            parameters=tuple(parameters),
            assumption=_assumption(
                "tip_extension_lays_down_hyphae",
                "Hyphal length density grows at the tip density times the extension speed; the speed is constant or saturates in the internal substrate; extension may consume a cost field in proportion to the length created.",
                "The density form of apical growth (Edelstein 1982); the saturating speed and the cost follow the substrate coupling of Boswell et al. (2003).",
                "No tip orientation, no septation, no diameter; the speed law and the cost are declared choices without organism values.",
            ),
            labels=("growth",),
            limitations=("constant or saturating extension speed", "cost proportional to length created and drawn only from the saturating substrate, so it cannot overdraw"),
            failure_modes=("non-positive half-saturation or negative speed or cost refused at compile time", "tip density evaluated at max(value, 0)"),
            rate_units=_per_time(self.hypha_units, "hour"),
        )

    def _creation_constants(self, context: FieldKernelContext) -> tuple[int, float, int | None, float]:
        """Tip row, ``speed`` times the length conversion, and the substrate row and half-saturation (or ``None``, 0)."""

        tip_row, _ = context.field_slot(self.tip_field, self.tip_units)
        hypha_row, _ = context.field_slot(self.hypha_field, self.hypha_units)
        del hypha_row
        speed = _non_negative(context.parameter(self.speed_symbol, f"meter / ({context.time_units})"), name=self.speed_symbol)
        to_hyphae = context.factor(f"meter * ({context.stored_units(self.tip_field)})", context.stored_units(self.hypha_field), name=self.name)
        gain = speed * to_hyphae
        if self.substrate_field is None or self.substrate_units is None or self.half_saturation_symbol is None:
            return tip_row, gain, None, 0.0
        substrate_row, _ = context.field_slot(self.substrate_field, self.substrate_units)
        half = _positive(context.parameter(self.half_saturation_symbol, context.stored_units(self.substrate_field)), name=self.half_saturation_symbol)
        return tip_row, gain, substrate_row, half

    def _creation_kernel(self, context: FieldKernelContext) -> RateFieldKernel:
        tip_row, gain, substrate_row, half = self._creation_constants(context)
        if substrate_row is None:
            return lambda time, fields: gain * fields[tip_row]

        def creation(time: float, fields: np.ndarray) -> np.ndarray:
            del time
            substrate = fields[substrate_row]
            return gain * fields[tip_row] * substrate / (half + substrate)

        return creation

    def compile_rate(self, context: FieldKernelContext) -> RateFieldKernel:
        creation = self._creation_kernel(context)
        to_rate = context.factor(_per_time(context.stored_units(self.hypha_field), context.time_units), self.rate_units, name=self.name)
        return lambda time, fields: to_rate * creation(time, fields)

    def compile_tendency(self, context: FieldKernelContext) -> TendencyKernel:
        creation = self._creation_kernel(context)
        hypha_row, _ = context.field_slot(self.hypha_field, self.hypha_units)
        if self.cost_field is None or self.cost_units is None or self.cost_symbol is None:
            def tendency(time: float, fields: np.ndarray) -> np.ndarray:
                out = np.zeros_like(fields)
                out[hypha_row] = creation(time, fields)
                return out

            return tendency
        cost_row, _ = context.field_slot(self.cost_field, self.cost_units)
        cost = _non_negative(
            context.parameter(self.cost_symbol, f"({context.stored_units(self.cost_field)}) / ({context.stored_units(self.hypha_field)})"),
            name=self.cost_symbol,
        )

        def tendency_with_cost(time: float, fields: np.ndarray) -> np.ndarray:
            out = np.zeros_like(fields)
            created = creation(time, fields)
            out[hypha_row] = created
            out[cost_row] -= cost * created
            return out

        return tendency_with_cost

    def compile_jacobian(self, context: FieldKernelContext) -> FieldJacobianKernel:
        """``d(v n s/(K+s))/dn = v s/(K+s)`` and ``d/ds = v n K/(K+s)^2`` into hyphae, times ``-cost`` into the cost field."""

        tip_row, gain, substrate_row, half = self._creation_constants(context)
        hypha_row, _ = context.field_slot(self.hypha_field, self.hypha_units)
        if substrate_row is None:
            return FieldJacobianKernel(blocks=(StencilBlock(hypha_row, tip_row),), values=lambda time, fields: (gain,))
        blocks = [StencilBlock(hypha_row, tip_row), StencilBlock(hypha_row, substrate_row)]
        cost = 0.0
        if self.cost_field is not None and self.cost_units is not None and self.cost_symbol is not None:
            cost_row, _ = context.field_slot(self.cost_field, self.cost_units)
            cost = _non_negative(
                context.parameter(self.cost_symbol, f"({context.stored_units(self.cost_field)}) / ({context.stored_units(self.hypha_field)})"),
                name=self.cost_symbol,
            )
            blocks += [StencilBlock(cost_row, tip_row), StencilBlock(cost_row, substrate_row)]
        charged = len(blocks) == 4

        def values(time: float, fields: np.ndarray) -> list[np.ndarray]:
            del time
            substrate = fields[substrate_row]
            by_tips = gain * substrate / (half + substrate)
            by_substrate = gain * fields[tip_row] * half / (half + substrate) ** 2
            if not charged:
                return [by_tips, by_substrate]
            return [by_tips, by_substrate, -cost * by_tips, -cost * by_substrate]

        return FieldJacobianKernel(blocks=tuple(blocks), values=values)


@dataclass(frozen=True, kw_only=True)
class TipMotion(FieldProcess):
    """Tips move by a random-walk diffusion and an optional drift along the gradient of a field.

    The tip flux is ``-D grad(n) + n * direction * mobility * grad(g)`` with
    ``g`` the drift field; ``direction`` is +1 (towards higher ``g``) or -1
    (away from it). The drift is discretised upwind, so the tip density stays
    non-negative under a stable step.
    """

    process_type: str = "tip_motion"
    tip_field: str
    tip_units: str
    diffusivity_symbol: str | None = None
    drift_field: str | None = None
    drift_units: str | None = None
    mobility_symbol: str | None = None
    drift_direction: int = 1

    def __post_init__(self) -> None:
        if self.diffusivity_symbol is None and self.drift_field is None:
            raise InvalidMechanismError("TipMotion needs a diffusivity, a drift field or both.")
        if (self.drift_field is None) != (self.drift_units is None) or (self.drift_field is None) != (self.mobility_symbol is None):
            raise InvalidMechanismError("TipMotion needs drift_field, drift_units and mobility_symbol together.")
        if self.drift_direction not in (1, -1):
            raise InvalidMechanismError("TipMotion.drift_direction must be +1 or -1.")
        tips = _spec(self.tip_field, self.tip_units, "hyphal tip density", "tips")
        required: list[FieldSpec] = [tips]
        parameters: list[ParameterRequirement] = []
        if self.diffusivity_symbol is not None:
            parameters.append(ParameterRequirement(self.diffusivity_symbol, "meter ** 2 / hour", description="random-walk diffusivity of the tips"))
        if self.drift_field is not None and self.drift_units is not None and self.mobility_symbol is not None:
            required.append(_spec(self.drift_field, self.drift_units, "field whose gradient steers the tips", "drift"))
            parameters.append(ParameterRequirement(self.mobility_symbol, f"meter ** 2 / hour / ({self.drift_units})", description="tip drift velocity per unit gradient of the drift field"))
        _declare(
            self,
            required=tuple(required),
            changed=(tips,),
            parameters=tuple(parameters),
            assumption=_assumption(
                "tip_density_random_walk_with_drift",
                "Tip motion is the diffusion limit of a persistent random walk plus an optional drift up or down the gradient of a declared field.",
                "The diffusion approximation of tip reorientation (Edelstein-Keshet and Ermentrout 1989) and the tropism terms of Boswell et al. (2003).",
                "No individual tip orientation, no persistence beyond the diffusivity, no contact guidance; first-order upwind drift is diffusive numerically.",
            ),
            labels=("transport", "tropism"),
            limitations=("diffusion approximation of tip orientation", "first-order upwind drift"),
            failure_modes=("negative diffusivity or mobility refused at compile time",),
            rate_units=_per_time(self.tip_units, "hour"),
        )

    def compile_tendency(self, context: FieldKernelContext) -> TendencyKernel:
        grid = context.grid
        tip_row, _ = context.field_slot(self.tip_field, self.tip_units)
        diffusivity = 0.0 if self.diffusivity_symbol is None else _non_negative(context.parameter(self.diffusivity_symbol, f"meter ** 2 / ({context.time_units})"), name=self.diffusivity_symbol)
        drift_row = None
        mobility = 0.0
        if self.drift_field is not None and self.drift_units is not None and self.mobility_symbol is not None:
            drift_row, _ = context.field_slot(self.drift_field, self.drift_units)
            mobility = self.drift_direction * _non_negative(
                context.parameter(self.mobility_symbol, f"meter ** 2 / ({context.time_units}) / ({context.stored_units(self.drift_field)})"),
                name=self.mobility_symbol,
            )
        widths = grid.cell_widths
        periodic = grid.periodic_axes

        def tendency(time: float, fields: np.ndarray) -> np.ndarray:
            del time
            tips = fields[tip_row]
            fluxes = []
            velocities = None if drift_row is None else drift_face_velocities(fields[drift_row], grid=grid, mobility=mobility)
            for axis, (width, wrap) in enumerate(zip(widths, periodic, strict=True)):
                flux = -diffusivity * face_gradient(tips, axis=axis, cell_width=width, periodic=wrap)
                if velocities is not None:
                    flux = flux + upwind_face_flux(tips, velocities[axis], axis=axis, periodic=wrap)
                fluxes.append(flux)
            out = np.zeros_like(fields)
            out[tip_row] = divergence(fluxes, grid=grid)
            return out

        return tendency

    def compile_jacobian(self, context: FieldKernelContext) -> FieldJacobianKernel:
        """Diffusion coefficients (constant) plus the upwind drift's derivatives in the tips and the drift field."""

        grid = context.grid
        tip_row, _ = context.field_slot(self.tip_field, self.tip_units)
        diffusivity = 0.0 if self.diffusivity_symbol is None else _non_negative(context.parameter(self.diffusivity_symbol, f"meter ** 2 / ({context.time_units})"), name=self.diffusivity_symbol)
        diffusion = diffusion_stencil(grid, diffusivity)
        diffusion_values = diffusion.values()
        blocks = transport_blocks(tip_row, tip_row, grid.ndim)
        if self.drift_field is None or self.drift_units is None or self.mobility_symbol is None:
            return FieldJacobianKernel(blocks=blocks, values=lambda time, fields: diffusion_values)
        drift_row, _ = context.field_slot(self.drift_field, self.drift_units)
        mobility = self.drift_direction * _non_negative(
            context.parameter(self.mobility_symbol, f"meter ** 2 / ({context.time_units}) / ({context.stored_units(self.drift_field)})"),
            name=self.mobility_symbol,
        )

        def values(time: float, fields: np.ndarray) -> list[np.ndarray]:
            del time
            carried, potential = upwind_drift_stencil(grid, fields[tip_row], fields[drift_row], mobility)
            return (diffusion + carried).values() + potential.values()

        return FieldJacobianKernel(blocks=blocks + transport_blocks(tip_row, drift_row, grid.ndim), values=values)


@dataclass(frozen=True, kw_only=True)
class LateralBranching(FieldProcess):
    """New tips appear along existing hyphae: ``b * hyphal_density`` (times the internal substrate when given)."""

    process_type: str = "lateral_branching"
    tip_field: str
    tip_units: str
    hypha_field: str
    hypha_units: str
    rate_symbol: str
    substrate_field: str | None = None
    substrate_units: str | None = None

    def __post_init__(self) -> None:
        if (self.substrate_field is None) != (self.substrate_units is None):
            raise InvalidMechanismError("LateralBranching needs substrate_field and substrate_units together.")
        tips = _spec(self.tip_field, self.tip_units, "hyphal tip density", "tips")
        hyphae = _spec(self.hypha_field, self.hypha_units, "hyphal length density", "hyphae")
        units = f"({self.tip_units}) / ({self.hypha_units}) / hour"
        required: list[FieldSpec] = [hyphae]
        if self.substrate_field is not None and self.substrate_units is not None:
            required.append(_spec(self.substrate_field, self.substrate_units, "internal substrate density", "internal_substrate"))
            units = f"({self.tip_units}) / ({self.hypha_units}) / ({self.substrate_units}) / hour"
        _declare(
            self,
            required=tuple(required),
            changed=(tips,),
            parameters=(ParameterRequirement(self.rate_symbol, units, description="lateral branching rate per unit hyphal density"),),
            assumption=_assumption(
                "lateral_branching_proportional_to_hyphae",
                "Tips are created in proportion to the local hyphal density, and in proportion to the local internal substrate when a substrate field is declared.",
                "The lateral branching term of Edelstein (1982); the substrate dependence follows Boswell et al. (2003).",
                "No branch angle, no minimum distance between branches, no dependence on hyphal age.",
            ),
            labels=("branching",),
            limitations=("branching rate linear in hyphal density",),
            failure_modes=("negative branching rate refused at compile time",),
            rate_units=_per_time(self.tip_units, "hour"),
        )

    def compile_rate(self, context: FieldKernelContext) -> RateFieldKernel:
        tip_row, _ = context.field_slot(self.tip_field, self.tip_units)
        hypha_row, _ = context.field_slot(self.hypha_field, self.hypha_units)
        del tip_row
        tip_units = context.stored_units(self.tip_field)
        hypha_units = context.stored_units(self.hypha_field)
        if self.substrate_field is None or self.substrate_units is None:
            rate = _non_negative(context.parameter(self.rate_symbol, f"({tip_units}) / ({hypha_units}) / ({context.time_units})"), name=self.rate_symbol)
            to_rate = context.factor(_per_time(tip_units, context.time_units), self.rate_units, name=self.name)
            return lambda time, fields: to_rate * rate * fields[hypha_row]
        substrate_row, _ = context.field_slot(self.substrate_field, self.substrate_units)
        substrate_units = context.stored_units(self.substrate_field)
        rate = _non_negative(context.parameter(self.rate_symbol, f"({tip_units}) / ({hypha_units}) / ({substrate_units}) / ({context.time_units})"), name=self.rate_symbol)
        to_rate = context.factor(_per_time(tip_units, context.time_units), self.rate_units, name=self.name)
        return lambda time, fields: to_rate * rate * fields[hypha_row] * fields[substrate_row]

    def compile_tendency(self, context: FieldKernelContext) -> TendencyKernel:
        creation = self.compile_rate(context)
        tip_row, _ = context.field_slot(self.tip_field, self.tip_units)
        to_stored = context.factor(self.rate_units, _per_time(context.stored_units(self.tip_field), context.time_units), name=self.name)

        def tendency(time: float, fields: np.ndarray) -> np.ndarray:
            out = np.zeros_like(fields)
            out[tip_row] = to_stored * creation(time, fields)
            return out

        return tendency

    def compile_jacobian(self, context: FieldKernelContext) -> FieldJacobianKernel:
        """``d(b rho s)/drho = b s`` and ``d/ds = b rho`` (``b`` alone without a substrate field)."""

        tip_row, _ = context.field_slot(self.tip_field, self.tip_units)
        hypha_row, _ = context.field_slot(self.hypha_field, self.hypha_units)
        tip_units = context.stored_units(self.tip_field)
        hypha_units = context.stored_units(self.hypha_field)
        to_rate = context.factor(_per_time(tip_units, context.time_units), self.rate_units, name=self.name)
        to_stored = context.factor(self.rate_units, _per_time(tip_units, context.time_units), name=self.name)
        if self.substrate_field is None or self.substrate_units is None:
            rate = _non_negative(context.parameter(self.rate_symbol, f"({tip_units}) / ({hypha_units}) / ({context.time_units})"), name=self.rate_symbol)
            coefficient = to_stored * to_rate * rate
            return FieldJacobianKernel(blocks=(StencilBlock(tip_row, hypha_row),), values=lambda time, fields: (coefficient,))
        substrate_row, _ = context.field_slot(self.substrate_field, self.substrate_units)
        substrate_units = context.stored_units(self.substrate_field)
        rate = _non_negative(context.parameter(self.rate_symbol, f"({tip_units}) / ({hypha_units}) / ({substrate_units}) / ({context.time_units})"), name=self.rate_symbol)
        coefficient = to_stored * to_rate * rate
        return FieldJacobianKernel(
            blocks=(StencilBlock(tip_row, hypha_row), StencilBlock(tip_row, substrate_row)),
            values=lambda time, fields: (coefficient * fields[substrate_row], coefficient * fields[hypha_row]),
        )


@dataclass(frozen=True, kw_only=True)
class DichotomousBranching(FieldProcess):
    """Tips split: ``alpha * tip_density`` new tips per time."""

    process_type: str = "dichotomous_branching"
    tip_field: str
    tip_units: str
    rate_symbol: str

    def __post_init__(self) -> None:
        tips = _spec(self.tip_field, self.tip_units, "hyphal tip density", "tips")
        _declare(
            self,
            required=(tips,),
            changed=(tips,),
            parameters=(ParameterRequirement(self.rate_symbol, "1 / hour", description="dichotomous branching rate per tip"),),
            assumption=_assumption(
                "dichotomous_branching_proportional_to_tips",
                "Each tip splits into two at a constant rate, so tips are created in proportion to the tip density.",
                "The dichotomous branching term of Edelstein (1982).",
                "No dependence on substrate or on the time since the last branch.",
            ),
            labels=("branching",),
            limitations=("constant per-tip rate",),
            failure_modes=("negative rate refused at compile time",),
            rate_units=_per_time(self.tip_units, "hour"),
        )

    def compile_rate(self, context: FieldKernelContext) -> RateFieldKernel:
        tip_row, _ = context.field_slot(self.tip_field, self.tip_units)
        rate = _non_negative(context.parameter(self.rate_symbol, f"1 / ({context.time_units})"), name=self.rate_symbol)
        to_rate = context.factor(_per_time(context.stored_units(self.tip_field), context.time_units), self.rate_units, name=self.name)
        return lambda time, fields: to_rate * rate * fields[tip_row]

    def compile_tendency(self, context: FieldKernelContext) -> TendencyKernel:
        tip_row, _ = context.field_slot(self.tip_field, self.tip_units)
        rate = _non_negative(context.parameter(self.rate_symbol, f"1 / ({context.time_units})"), name=self.rate_symbol)

        def tendency(time: float, fields: np.ndarray) -> np.ndarray:
            del time
            out = np.zeros_like(fields)
            out[tip_row] = rate * fields[tip_row]
            return out

        return tendency

    def compile_jacobian(self, context: FieldKernelContext) -> FieldJacobianKernel:
        tip_row, _ = context.field_slot(self.tip_field, self.tip_units)
        rate = _non_negative(context.parameter(self.rate_symbol, f"1 / ({context.time_units})"), name=self.rate_symbol)
        return FieldJacobianKernel(blocks=(StencilBlock(tip_row, tip_row),), values=lambda time, fields: (rate,))


@dataclass(frozen=True, kw_only=True)
class Anastomosis(FieldProcess):
    """Tips fuse with hyphae they meet and stop: ``-a * tip_density * hyphal_density``."""

    process_type: str = "anastomosis"
    tip_field: str
    tip_units: str
    hypha_field: str
    hypha_units: str
    rate_symbol: str

    def __post_init__(self) -> None:
        tips = _spec(self.tip_field, self.tip_units, "hyphal tip density", "tips")
        hyphae = _spec(self.hypha_field, self.hypha_units, "hyphal length density", "hyphae")
        _declare(
            self,
            required=(tips, hyphae),
            changed=(tips,),
            parameters=(ParameterRequirement(self.rate_symbol, f"1 / ({self.hypha_units}) / hour", description="tip loss rate per unit hyphal density"),),
            assumption=_assumption(
                "anastomosis_mass_action",
                "Tips are lost at a rate proportional to the product of tip density and hyphal density, as in a bimolecular encounter.",
                "The anastomosis term of Edelstein (1982).",
                "No distinction between tip-to-hypha and tip-to-tip fusion, no dependence on hyphal age or compatibility.",
            ),
            labels=("network",),
            limitations=("mass-action encounter rate",),
            failure_modes=("negative rate refused at compile time",),
            rate_units=_per_time(self.tip_units, "hour"),
        )

    def compile_rate(self, context: FieldKernelContext) -> RateFieldKernel:
        tip_row, _ = context.field_slot(self.tip_field, self.tip_units)
        hypha_row, _ = context.field_slot(self.hypha_field, self.hypha_units)
        rate = _non_negative(context.parameter(self.rate_symbol, f"1 / ({context.stored_units(self.hypha_field)}) / ({context.time_units})"), name=self.rate_symbol)
        to_rate = context.factor(_per_time(context.stored_units(self.tip_field), context.time_units), self.rate_units, name=self.name)
        return lambda time, fields: to_rate * rate * fields[tip_row] * fields[hypha_row]

    def compile_tendency(self, context: FieldKernelContext) -> TendencyKernel:
        tip_row, _ = context.field_slot(self.tip_field, self.tip_units)
        hypha_row, _ = context.field_slot(self.hypha_field, self.hypha_units)
        rate = _non_negative(context.parameter(self.rate_symbol, f"1 / ({context.stored_units(self.hypha_field)}) / ({context.time_units})"), name=self.rate_symbol)

        def tendency(time: float, fields: np.ndarray) -> np.ndarray:
            del time
            out = np.zeros_like(fields)
            out[tip_row] = -rate * fields[tip_row] * fields[hypha_row]
            return out

        return tendency

    def compile_jacobian(self, context: FieldKernelContext) -> FieldJacobianKernel:
        """``d(-a n rho)/dn = -a rho`` and ``d/drho = -a n``."""

        tip_row, _ = context.field_slot(self.tip_field, self.tip_units)
        hypha_row, _ = context.field_slot(self.hypha_field, self.hypha_units)
        rate = _non_negative(context.parameter(self.rate_symbol, f"1 / ({context.stored_units(self.hypha_field)}) / ({context.time_units})"), name=self.rate_symbol)
        return FieldJacobianKernel(
            blocks=(StencilBlock(tip_row, tip_row), StencilBlock(tip_row, hypha_row)),
            values=lambda time, fields: (-rate * fields[hypha_row], -rate * fields[tip_row]),
        )


@dataclass(frozen=True, kw_only=True)
class FirstOrderLoss(FieldProcess):
    """A field is lost at first order, optionally into a product field of compatible units."""

    process_type: str = "first_order_field_loss"
    field: str
    field_units: str
    rate_symbol: str
    product_field: str | None = None
    product_units: str | None = None

    def __post_init__(self) -> None:
        if (self.product_field is None) != (self.product_units is None):
            raise InvalidMechanismError("FirstOrderLoss needs product_field and product_units together.")
        spec = _spec(self.field, self.field_units, "field lost at first order", "field")
        changed: list[FieldSpec] = [spec]
        if self.product_field is not None and self.product_units is not None:
            changed.append(_spec(self.product_field, self.product_units, "field receiving the loss", "product"))
        _declare(
            self,
            required=(spec,),
            changed=tuple(changed),
            parameters=(ParameterRequirement(self.rate_symbol, "1 / hour", description="first-order loss rate"),),
            assumption=_assumption(
                "first_order_field_loss",
                "The field decays at a constant specific rate; the lost amount appears in the product field when one is declared.",
                "Tip death, hyphal inactivation and the decay of inactive hyphae are first order in Edelstein (1982) and Boswell et al. (2003).",
                "No age structure, no dependence on substrate or crowding.",
            ),
            labels=("loss",),
            limitations=("constant specific rate",),
            failure_modes=("negative rate refused at compile time", "incompatible product units refused at compile time"),
            rate_units=_per_time(self.field_units, "hour"),
        )

    def compile_rate(self, context: FieldKernelContext) -> RateFieldKernel:
        row, _ = context.field_slot(self.field, self.field_units)
        rate = _non_negative(context.parameter(self.rate_symbol, f"1 / ({context.time_units})"), name=self.rate_symbol)
        to_rate = context.factor(_per_time(context.stored_units(self.field), context.time_units), self.rate_units, name=self.name)
        return lambda time, fields: to_rate * rate * fields[row]

    def compile_tendency(self, context: FieldKernelContext) -> TendencyKernel:
        row, _ = context.field_slot(self.field, self.field_units)
        rate = _non_negative(context.parameter(self.rate_symbol, f"1 / ({context.time_units})"), name=self.rate_symbol)
        if self.product_field is None or self.product_units is None:
            def tendency(time: float, fields: np.ndarray) -> np.ndarray:
                del time
                out = np.zeros_like(fields)
                out[row] = -rate * fields[row]
                return out

            return tendency
        product_row, _ = context.field_slot(self.product_field, self.product_units)
        to_product = context.factor(context.stored_units(self.field), context.stored_units(self.product_field), name=self.name)

        def tendency_with_product(time: float, fields: np.ndarray) -> np.ndarray:
            del time
            out = np.zeros_like(fields)
            lost = rate * fields[row]
            out[row] = -lost
            out[product_row] = to_product * lost
            return out

        return tendency_with_product

    def compile_jacobian(self, context: FieldKernelContext) -> FieldJacobianKernel:
        row, _ = context.field_slot(self.field, self.field_units)
        rate = _non_negative(context.parameter(self.rate_symbol, f"1 / ({context.time_units})"), name=self.rate_symbol)
        if self.product_field is None or self.product_units is None:
            return FieldJacobianKernel(blocks=(StencilBlock(row, row),), values=lambda time, fields: (-rate,))
        product_row, _ = context.field_slot(self.product_field, self.product_units)
        to_product = context.factor(context.stored_units(self.field), context.stored_units(self.product_field), name=self.name)
        return FieldJacobianKernel(
            blocks=(StencilBlock(row, row), StencilBlock(product_row, row)),
            values=lambda time, fields: (-rate, to_product * rate),
        )


# ---------------------------------------------------------------------------
# Substrate coupling
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class LocalUptake(FieldProcess):
    """External substrate becomes internal substrate where hyphae are present.

    The flux is ``c * hyphal_density * external`` or, with a half-saturation,
    ``c * hyphal_density * external / (K + external)``; the same amount
    (converted) is added to the internal field.
    """

    process_type: str = "local_uptake"
    external_field: str
    external_units: str
    internal_field: str
    internal_units: str
    hypha_field: str
    hypha_units: str
    rate_symbol: str
    half_saturation_symbol: str | None = None

    def __post_init__(self) -> None:
        external = _spec(self.external_field, self.external_units, "external substrate", "external_substrate")
        internal = _spec(self.internal_field, self.internal_units, "internal substrate carried by hyphae", "internal_substrate")
        hyphae = _spec(self.hypha_field, self.hypha_units, "hyphal length density", "hyphae")
        parameters: list[ParameterRequirement] = []
        if self.half_saturation_symbol is None:
            parameters.append(ParameterRequirement(self.rate_symbol, f"1 / ({self.hypha_units}) / hour", description="uptake rate per unit hyphal density"))
        else:
            parameters.append(ParameterRequirement(self.rate_symbol, f"({self.external_units}) / ({self.hypha_units}) / hour", description="maximum uptake flux per unit hyphal density"))
            parameters.append(ParameterRequirement(self.half_saturation_symbol, self.external_units, description="half-saturation of uptake in the external substrate"))
        _declare(
            self,
            required=(external, hyphae),
            changed=(external, internal),
            parameters=tuple(parameters),
            assumption=_assumption(
                "local_uptake_proportional_to_hyphae",
                "Hyphae take up the external substrate of their own cell at a rate proportional to the hyphal density and linear or saturating in the external substrate; the amount moves to the internal field without loss.",
                "The uptake term of Boswell et al. (2003) with a declared linear or Michaelis-Menten form.",
                "No diffusion limitation within the cell, no uptake cost, no dependence on hyphal age or tips.",
            ),
            labels=("substrate",),
            limitations=("uptake linear in hyphal density",),
            failure_modes=("negative rate or non-positive half-saturation refused at compile time",),
            rate_units=_per_time(self.external_units, "hour"),
        )

    def compile_rate(self, context: FieldKernelContext) -> RateFieldKernel:
        external_row, _ = context.field_slot(self.external_field, self.external_units)
        hypha_row, _ = context.field_slot(self.hypha_field, self.hypha_units)
        external_units = context.stored_units(self.external_field)
        hypha_units = context.stored_units(self.hypha_field)
        to_rate = context.factor(_per_time(external_units, context.time_units), self.rate_units, name=self.name)
        if self.half_saturation_symbol is None:
            rate = _non_negative(context.parameter(self.rate_symbol, f"1 / ({hypha_units}) / ({context.time_units})"), name=self.rate_symbol)
            return lambda time, fields: to_rate * rate * fields[hypha_row] * fields[external_row]
        maximum = _non_negative(context.parameter(self.rate_symbol, f"({external_units}) / ({hypha_units}) / ({context.time_units})"), name=self.rate_symbol)
        half = _positive(context.parameter(self.half_saturation_symbol, external_units), name=self.half_saturation_symbol)

        def flux(time: float, fields: np.ndarray) -> np.ndarray:
            del time
            external = fields[external_row]
            return to_rate * maximum * fields[hypha_row] * external / (half + external)

        return flux

    def compile_tendency(self, context: FieldKernelContext) -> TendencyKernel:
        flux = self.compile_rate(context)
        external_row, _ = context.field_slot(self.external_field, self.external_units)
        internal_row, _ = context.field_slot(self.internal_field, self.internal_units)
        to_external = context.factor(self.rate_units, _per_time(context.stored_units(self.external_field), context.time_units), name=self.name)
        to_internal = context.factor(self.rate_units, _per_time(context.stored_units(self.internal_field), context.time_units), name=self.name)

        def tendency(time: float, fields: np.ndarray) -> np.ndarray:
            out = np.zeros_like(fields)
            taken = flux(time, fields)
            out[external_row] = -to_external * taken
            out[internal_row] = to_internal * taken
            return out

        return tendency

    def compile_jacobian(self, context: FieldKernelContext) -> FieldJacobianKernel:
        """The uptake flux differentiated in the hyphal density and the external substrate, with opposite signs in the two fields."""

        external_row, _ = context.field_slot(self.external_field, self.external_units)
        internal_row, _ = context.field_slot(self.internal_field, self.internal_units)
        hypha_row, _ = context.field_slot(self.hypha_field, self.hypha_units)
        external_units = context.stored_units(self.external_field)
        hypha_units = context.stored_units(self.hypha_field)
        to_rate = context.factor(_per_time(external_units, context.time_units), self.rate_units, name=self.name)
        to_external = context.factor(self.rate_units, _per_time(external_units, context.time_units), name=self.name)
        to_internal = context.factor(self.rate_units, _per_time(context.stored_units(self.internal_field), context.time_units), name=self.name)
        blocks = (
            StencilBlock(external_row, hypha_row),
            StencilBlock(external_row, external_row),
            StencilBlock(internal_row, hypha_row),
            StencilBlock(internal_row, external_row),
        )
        if self.half_saturation_symbol is None:
            rate = to_rate * _non_negative(context.parameter(self.rate_symbol, f"1 / ({hypha_units}) / ({context.time_units})"), name=self.rate_symbol)

            def linear(time: float, fields: np.ndarray) -> list[np.ndarray]:
                del time
                by_hyphae = rate * fields[external_row]
                by_external = rate * fields[hypha_row]
                return [-to_external * by_hyphae, -to_external * by_external, to_internal * by_hyphae, to_internal * by_external]

            return FieldJacobianKernel(blocks=blocks, values=linear)
        maximum = to_rate * _non_negative(context.parameter(self.rate_symbol, f"({external_units}) / ({hypha_units}) / ({context.time_units})"), name=self.rate_symbol)
        half = _positive(context.parameter(self.half_saturation_symbol, external_units), name=self.half_saturation_symbol)

        def saturating(time: float, fields: np.ndarray) -> list[np.ndarray]:
            del time
            external = fields[external_row]
            by_hyphae = maximum * external / (half + external)
            by_external = maximum * fields[hypha_row] * half / (half + external) ** 2
            return [-to_external * by_hyphae, -to_external * by_external, to_internal * by_hyphae, to_internal * by_external]

        return FieldJacobianKernel(blocks=blocks, values=saturating)


ACTIVE_TRANSLOCATION_AGGREGATION = (
    "finite-time aggregation: carrying substrate up the tip-density gradient while a branching process makes tips "
    "where the substrate is forms a chemotaxis-like positive feedback (Keller-Segel type) that can concentrate tips "
    "into a spike whose height grows without bound as the grid is refined; check grid convergence of every result "
    "that uses the active term (COLONY-001 stage 0: the 24 h tip count doubled with each halving of the cell)"
)


@dataclass(frozen=True, kw_only=True)
class Translocation(FieldProcess):
    """Internal substrate moves through the mycelium: diffusion plus an optional active flux towards tips.

    The diffusive flux is ``-D_i grad(s)``; the active flux, when a tip
    field is declared, is ``D_a * s * grad(n)`` (substrate carried up the
    tip-density gradient, discretised upwind). Both act on the internal
    substrate density; the hyphal density is not a conductance here, so the
    substrate can reach the tip zone ahead of the hyphae, as the continuum
    model needs for substrate-limited extension.
    """

    process_type: str = "translocation"
    internal_field: str
    internal_units: str
    diffusivity_symbol: str
    tip_field: str | None = None
    tip_units: str | None = None
    active_diffusivity_symbol: str | None = None

    def __post_init__(self) -> None:
        if (self.tip_field is None) != (self.tip_units is None) or (self.tip_field is None) != (self.active_diffusivity_symbol is None):
            raise InvalidMechanismError("Translocation needs tip_field, tip_units and active_diffusivity_symbol together.")
        internal = _spec(self.internal_field, self.internal_units, "internal substrate carried by the mycelium", "internal_substrate")
        required: list[FieldSpec] = [internal]
        parameters: list[ParameterRequirement] = [ParameterRequirement(self.diffusivity_symbol, "meter ** 2 / hour", description="diffusive translocation coefficient of the internal substrate")]
        if self.tip_field is not None and self.tip_units is not None and self.active_diffusivity_symbol is not None:
            required.append(_spec(self.tip_field, self.tip_units, "hyphal tip density", "tips"))
            parameters.append(ParameterRequirement(self.active_diffusivity_symbol, f"meter ** 2 / hour / ({self.tip_units})", description="active translocation velocity of the internal substrate per unit tip-density gradient"))
        _declare(
            self,
            required=tuple(required),
            changed=(internal,),
            parameters=tuple(parameters),
            assumption=_assumption(
                "translocation_diffusive_and_towards_tips",
                "Internal substrate diffuses down its own density gradient and, when a tip field is declared, is carried up the tip-density gradient at a velocity proportional to that gradient.",
                "The diffusive and active (tip-directed) translocation terms of Boswell et al. (2003) in declared form.",
                "No restriction of the flux to cells that already hold hyphae; no metabolic cost of translocation; first-order upwind active flux.",
            ),
            labels=("transport", "substrate"),
            limitations=("translocation not gated by hyphal density",),
            failure_modes=(
                ("negative diffusivity refused at compile time", ACTIVE_TRANSLOCATION_AGGREGATION)
                if self.active_diffusivity_symbol is not None
                else ("negative diffusivity refused at compile time",)
            ),
            rate_units=_per_time(self.internal_units, "hour"),
        )

    def compile_tendency(self, context: FieldKernelContext) -> TendencyKernel:
        grid = context.grid
        internal_row, _ = context.field_slot(self.internal_field, self.internal_units)
        diffusivity = _non_negative(context.parameter(self.diffusivity_symbol, f"meter ** 2 / ({context.time_units})"), name=self.diffusivity_symbol)
        tip_row = None
        active = 0.0
        if self.tip_field is not None and self.tip_units is not None and self.active_diffusivity_symbol is not None:
            tip_row, _ = context.field_slot(self.tip_field, self.tip_units)
            active = _non_negative(
                context.parameter(self.active_diffusivity_symbol, f"meter ** 2 / ({context.time_units}) / ({context.stored_units(self.tip_field)})"),
                name=self.active_diffusivity_symbol,
            )
        widths = grid.cell_widths
        periodic = grid.periodic_axes

        def tendency(time: float, fields: np.ndarray) -> np.ndarray:
            del time
            substrate = fields[internal_row]
            velocities = None if tip_row is None else drift_face_velocities(fields[tip_row], grid=grid, mobility=active)
            fluxes = []
            for axis, (width, wrap) in enumerate(zip(widths, periodic, strict=True)):
                flux = -diffusivity * face_gradient(substrate, axis=axis, cell_width=width, periodic=wrap)
                if velocities is not None:
                    flux = flux + upwind_face_flux(substrate, velocities[axis], axis=axis, periodic=wrap)
                fluxes.append(flux)
            out = np.zeros_like(fields)
            out[internal_row] = divergence(fluxes, grid=grid)
            return out

        return tendency

    def compile_jacobian(self, context: FieldKernelContext) -> FieldJacobianKernel:
        """Diffusion coefficients (constant) plus the active upwind flux's derivatives in the substrate and the tips."""

        grid = context.grid
        internal_row, _ = context.field_slot(self.internal_field, self.internal_units)
        diffusivity = _non_negative(context.parameter(self.diffusivity_symbol, f"meter ** 2 / ({context.time_units})"), name=self.diffusivity_symbol)
        diffusion = diffusion_stencil(grid, diffusivity)
        diffusion_values = diffusion.values()
        blocks = transport_blocks(internal_row, internal_row, grid.ndim)
        if self.tip_field is None or self.tip_units is None or self.active_diffusivity_symbol is None:
            return FieldJacobianKernel(blocks=blocks, values=lambda time, fields: diffusion_values)
        tip_row, _ = context.field_slot(self.tip_field, self.tip_units)
        active = _non_negative(
            context.parameter(self.active_diffusivity_symbol, f"meter ** 2 / ({context.time_units}) / ({context.stored_units(self.tip_field)})"),
            name=self.active_diffusivity_symbol,
        )

        def values(time: float, fields: np.ndarray) -> list[np.ndarray]:
            del time
            carried, tips = upwind_drift_stencil(grid, fields[internal_row], fields[tip_row], active)
            return (diffusion + carried).values() + tips.values()

        return FieldJacobianKernel(blocks=blocks + transport_blocks(internal_row, tip_row, grid.ndim), values=values)


@dataclass(frozen=True, kw_only=True)
class LocalSecretion(FieldProcess):
    """Hyphae release a product into an external field: ``k * hyphal_density`` (times ``s/(K+s)`` of an internal substrate when given), optionally at a cost."""

    process_type: str = "local_secretion"
    hypha_field: str
    hypha_units: str
    product_field: str
    product_units: str
    rate_symbol: str
    substrate_field: str | None = None
    substrate_units: str | None = None
    half_saturation_symbol: str | None = None
    cost_field: str | None = None
    cost_units: str | None = None
    cost_symbol: str | None = None

    def __post_init__(self) -> None:
        if (self.substrate_field is None) != (self.substrate_units is None) or (self.substrate_field is None) != (self.half_saturation_symbol is None):
            raise InvalidMechanismError("LocalSecretion needs substrate_field, substrate_units and half_saturation_symbol together.")
        if (self.cost_field is None) != (self.cost_units is None) or (self.cost_field is None) != (self.cost_symbol is None):
            raise InvalidMechanismError("LocalSecretion needs cost_field, cost_units and cost_symbol together.")
        if self.cost_field is not None and self.cost_field != self.substrate_field:
            raise InvalidMechanismError(
                "LocalSecretion can only charge a cost to the internal substrate field that saturates its rate; "
                "a cost drawn from a field the rate ignores could overdraw it."
            )
        hyphae = _spec(self.hypha_field, self.hypha_units, "hyphal length density", "hyphae")
        product = _spec(self.product_field, self.product_units, "secreted product field", "product")
        required: list[FieldSpec] = [hyphae]
        changed: list[FieldSpec] = [product]
        parameters: list[ParameterRequirement] = [ParameterRequirement(self.rate_symbol, f"({self.product_units}) / ({self.hypha_units}) / hour", description="secretion rate per unit hyphal density")]
        if self.substrate_field is not None and self.substrate_units is not None and self.half_saturation_symbol is not None:
            required.append(_spec(self.substrate_field, self.substrate_units, "internal substrate density", "internal_substrate"))
            parameters.append(ParameterRequirement(self.half_saturation_symbol, self.substrate_units, description="half-saturation of secretion in the internal substrate"))
        if self.cost_field is not None and self.cost_units is not None and self.cost_symbol is not None:
            cost = _spec(self.cost_field, self.cost_units, "field paying for secretion", "cost")
            changed.append(cost)
            if self.cost_field not in {spec.name for spec in required}:
                required.append(cost)
            parameters.append(ParameterRequirement(self.cost_symbol, f"({self.cost_units}) / ({self.product_units})", description="amount removed from the cost field per unit product secreted"))
        _declare(
            self,
            required=tuple(required),
            changed=tuple(changed),
            parameters=tuple(parameters),
            assumption=_assumption(
                "secretion_proportional_to_hyphae",
                "Hyphae secrete into the external field of their own cell in proportion to the hyphal density, saturating in the internal substrate when one is declared, and pay for it from a declared cost field.",
                "A declared local-secretion law; the continuum literature cited here has no secretion term, so this is an extension named as such.",
                "No regulation, no induction, no secretion from tips specifically, no transport of the product inside the hyphae.",
            ),
            labels=("secretion",),
            limitations=("secretion linear in hyphal density",),
            failure_modes=("negative rate or cost, or non-positive half-saturation, refused at compile time",),
            rate_units=_per_time(self.product_units, "hour"),
        )

    def compile_rate(self, context: FieldKernelContext) -> RateFieldKernel:
        hypha_row, _ = context.field_slot(self.hypha_field, self.hypha_units)
        product_units = context.stored_units(self.product_field)
        rate = _non_negative(context.parameter(self.rate_symbol, f"({product_units}) / ({context.stored_units(self.hypha_field)}) / ({context.time_units})"), name=self.rate_symbol)
        to_rate = context.factor(_per_time(product_units, context.time_units), self.rate_units, name=self.name)
        if self.substrate_field is None or self.substrate_units is None or self.half_saturation_symbol is None:
            return lambda time, fields: to_rate * rate * fields[hypha_row]
        substrate_row, _ = context.field_slot(self.substrate_field, self.substrate_units)
        half = _positive(context.parameter(self.half_saturation_symbol, context.stored_units(self.substrate_field)), name=self.half_saturation_symbol)

        def production(time: float, fields: np.ndarray) -> np.ndarray:
            del time
            substrate = fields[substrate_row]
            return to_rate * rate * fields[hypha_row] * substrate / (half + substrate)

        return production

    def compile_tendency(self, context: FieldKernelContext) -> TendencyKernel:
        production = self.compile_rate(context)
        product_row, _ = context.field_slot(self.product_field, self.product_units)
        to_product = context.factor(self.rate_units, _per_time(context.stored_units(self.product_field), context.time_units), name=self.name)
        if self.cost_field is None or self.cost_units is None or self.cost_symbol is None:
            def tendency(time: float, fields: np.ndarray) -> np.ndarray:
                out = np.zeros_like(fields)
                out[product_row] = to_product * production(time, fields)
                return out

            return tendency
        cost_row, _ = context.field_slot(self.cost_field, self.cost_units)
        cost = _non_negative(
            context.parameter(self.cost_symbol, f"({context.stored_units(self.cost_field)}) / ({context.stored_units(self.product_field)})"),
            name=self.cost_symbol,
        )

        def tendency_with_cost(time: float, fields: np.ndarray) -> np.ndarray:
            out = np.zeros_like(fields)
            produced = to_product * production(time, fields)
            out[product_row] = produced
            out[cost_row] -= cost * produced
            return out

        return tendency_with_cost

    def compile_jacobian(self, context: FieldKernelContext) -> FieldJacobianKernel:
        """``d(k rho s/(K+s))/drho = k s/(K+s)`` and ``d/ds = k rho K/(K+s)^2`` into the product, times ``-cost`` into the cost field."""

        hypha_row, _ = context.field_slot(self.hypha_field, self.hypha_units)
        product_row, _ = context.field_slot(self.product_field, self.product_units)
        product_units = context.stored_units(self.product_field)
        rate = _non_negative(context.parameter(self.rate_symbol, f"({product_units}) / ({context.stored_units(self.hypha_field)}) / ({context.time_units})"), name=self.rate_symbol)
        to_rate = context.factor(_per_time(product_units, context.time_units), self.rate_units, name=self.name)
        to_product = context.factor(self.rate_units, _per_time(product_units, context.time_units), name=self.name)
        coefficient = to_product * to_rate * rate
        if self.substrate_field is None or self.substrate_units is None or self.half_saturation_symbol is None:
            return FieldJacobianKernel(blocks=(StencilBlock(product_row, hypha_row),), values=lambda time, fields: (coefficient,))
        substrate_row, _ = context.field_slot(self.substrate_field, self.substrate_units)
        half = _positive(context.parameter(self.half_saturation_symbol, context.stored_units(self.substrate_field)), name=self.half_saturation_symbol)
        blocks = [StencilBlock(product_row, hypha_row), StencilBlock(product_row, substrate_row)]
        cost = 0.0
        if self.cost_field is not None and self.cost_units is not None and self.cost_symbol is not None:
            cost_row, _ = context.field_slot(self.cost_field, self.cost_units)
            cost = _non_negative(
                context.parameter(self.cost_symbol, f"({context.stored_units(self.cost_field)}) / ({product_units})"),
                name=self.cost_symbol,
            )
            blocks += [StencilBlock(cost_row, hypha_row), StencilBlock(cost_row, substrate_row)]
        charged = len(blocks) == 4

        def values(time: float, fields: np.ndarray) -> list[np.ndarray]:
            del time
            substrate = fields[substrate_row]
            by_hyphae = coefficient * substrate / (half + substrate)
            by_substrate = coefficient * fields[hypha_row] * half / (half + substrate) ** 2
            if not charged:
                return [by_hyphae, by_substrate]
            return [by_hyphae, by_substrate, -cost * by_hyphae, -cost * by_substrate]

        return FieldJacobianKernel(blocks=tuple(blocks), values=values)


def continuum_process_types() -> dict[str, type[FieldProcess]]:
    """The shipped mycelium process classes keyed by their ``process_type``."""

    classes: tuple[type[FieldProcess], ...] = (
        FieldDiffusion, TipExtension, TipMotion, LateralBranching, DichotomousBranching, Anastomosis,
        FirstOrderLoss, LocalUptake, Translocation, LocalSecretion,
    )
    result: dict[str, type[FieldProcess]] = {}
    for cls in classes:
        default: Any = cls.__dataclass_fields__["process_type"].default
        result[str(default)] = cls
    return result


__all__ = [
    "Anastomosis",
    "CONTINUUM_LITERATURE",
    "DichotomousBranching",
    "FieldDiffusion",
    "FirstOrderLoss",
    "LateralBranching",
    "LocalSecretion",
    "LocalUptake",
    "TipExtension",
    "TipMotion",
    "Translocation",
    "continuum_process_types",
]
