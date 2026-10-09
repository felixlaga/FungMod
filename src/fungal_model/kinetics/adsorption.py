"""Single-site Langmuir partition with finite enzyme depletion (BIO-004 M1).

Law form: Jaeger et al. (2010), equation (1), DOI 10.1186/1754-6834-3-18.
The quadratic and its derivatives follow by imposing total = free + bound.
There are no parameter defaults or constants imported from that paper.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity


@dataclass(frozen=True)
class EnzymePartition:
    free: Quantity
    bound: Quantity


def partition_magnitudes(total: float, capacity: float, dissociation: float) -> tuple[float, float]:
    """Stable positive quadratic root, in one common enzyme-concentration unit.

    Scaling avoids squaring dimensional concentrations and the two root forms
    avoid cancellation when capacity is either above or below total enzyme.
    Bound enzyme uses its own rationalized quadratic root, avoiding both
    total-minus-free cancellation and loss when free enzyme underflows.
    """
    for name, value in (("total enzyme", total), ("binding capacity", capacity), ("dissociation constant", dissociation)):
        if not math.isfinite(value) or value < 0.0:
            raise ValueError(f"{name} must be finite and non-negative.")
    if dissociation <= 0.0:
        raise ValueError("dissociation constant must be positive.")
    if total == 0.0 or capacity == 0.0:
        return total, 0.0
    scale = max(total, capacity, dissociation)
    t, c, d = total / scale, capacity / scale, dissociation / scale
    b = (c - t) + d
    geometric_mean = math.sqrt(dissociation) * math.sqrt(total)
    cross = 2.0 * (geometric_mean / scale)
    discriminant = math.hypot(b, cross)
    free = (cross / (b + discriminant)) * geometric_mean if b >= 0.0 else ((discriminant - b) / 2.0) * scale
    bound = min(total, capacity) * ((2.0 * max(t, c)) / (t + c + d + discriminant))
    return free, bound


def partition_derivatives(total: float, capacity: float, dissociation: float) -> tuple[float, float]:
    """Return derivatives of bound enzyme with respect to total and capacity."""
    free, _ = partition_magnitudes(total, capacity, dissociation)
    scale = max(dissociation, free)
    denominator = dissociation / scale + free / scale
    coverage = (free / scale) / denominator
    feedback = ((capacity / scale) / denominator) * ((dissociation / scale) / denominator)
    if math.isinf(feedback):
        return 1.0, 0.0
    return feedback / (1.0 + feedback), coverage / (1.0 + feedback)


def enzyme_partition(
    *, total_enzyme: Quantity, solid_substrate: Quantity, binding_capacity: Quantity,
    adsorption_constant: Quantity | None = None,
    adsorption_dissociation_constant: Quantity | None = None,
) -> EnzymePartition:
    """Partition enzyme on a dry-mass solid; require exactly one of K or Kd."""
    total = require_quantity(total_enzyme, name="total_enzyme")
    substrate = assert_compatible(require_quantity(solid_substrate, name="solid_substrate"), "g/L", name="solid_substrate dry mass")
    if not math.isfinite(float(substrate.magnitude)) or float(substrate.magnitude) < 0.0:
        raise ValueError("solid_substrate must be finite and non-negative.")
    capacity = assert_compatible(require_quantity(binding_capacity, name="binding_capacity") * substrate, str(total.units), name="binding_capacity times solid_substrate")
    if (adsorption_constant is None) == (adsorption_dissociation_constant is None):
        raise ValueError("Give exactly one of adsorption_constant and adsorption_dissociation_constant.")
    if adsorption_constant is not None:
        association = assert_compatible(require_quantity(adsorption_constant, name="adsorption_constant"), f"1/({total.units})", name="adsorption_constant")
        if not math.isfinite(float(association.magnitude)) or float(association.magnitude) <= 0.0:
            raise ValueError("adsorption_constant must be finite and positive.")
        dissociation = assert_compatible(1 / association, str(total.units), name="adsorption dissociation constant")
    else:
        dissociation = assert_compatible(require_quantity(adsorption_dissociation_constant, name="adsorption_dissociation_constant"), str(total.units), name="adsorption_dissociation_constant")
    free, bound = partition_magnitudes(float(total.magnitude), float(capacity.magnitude), float(dissociation.magnitude))
    return EnzymePartition(Q_(free, total.units), Q_(bound, total.units))
