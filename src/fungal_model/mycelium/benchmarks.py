"""Artificial mycelium models for software verification.

Every value here is a framework benchmark: round numbers in millimetres and
hours on abstract fields, chosen to exercise the processes, not measured for
any organism. The models are labelled so by their parameter sources and the
``artificial`` prefix of every parameter name, and the maturity enforcement
refuses them in scientific mode.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_, Quantity
from fungal_model.mycelium.fields import FieldSpec
from fungal_model.mycelium.grid import SpatialGrid
from fungal_model.mycelium.hyphae import (
    Anastomosis,
    DichotomousBranching,
    FirstOrderLoss,
    LateralBranching,
    LocalUptake,
    TipExtension,
    TipMotion,
    Translocation,
)
from fungal_model.mycelium.model import MyceliumModel

ARTIFICIAL_SOURCE = "Artificial mycelium framework benchmark; no organism, substrate or measurement is claimed."
TIP_UNITS = "1 / millimeter ** 2"
HYPHA_UNITS = "1 / millimeter"
SUBSTRATE_UNITS = "microgram / millimeter ** 2"


def artificial_parameter(symbol: str, value: float, units: str) -> Parameter:
    return Parameter(
        name=f"artificial {symbol}",
        symbol=symbol,
        value=value,
        units=units,
        uncertainty=None,
        source=ARTIFICIAL_SOURCE,
        confidence_level="testing",
        notes="Round framework-benchmark value with no empirical meaning.",
    )


def artificial_colony_model(
    *,
    side_mm: float = 10.0,
    cells: int = 40,
    overrides: Mapping[str, float] | None = None,
    geometry: str = "cartesian",
) -> MyceliumModel:
    """A colony with every continuum process on abstract fields.

    Fields: tips (per area), hyphae (length per area), internal and external
    substrate (mass per area). The extension speed saturates in the internal
    substrate and pays for the length it lays down; tips diffuse and drift
    away from dense hyphae; lateral branching needs internal substrate;
    anastomosis and tip death remove tips; hyphae take up external substrate
    where they are; internal substrate diffuses and is carried towards tips.

    ``geometry="cartesian"`` builds the square ``side_mm`` window with
    ``cells`` cells per axis; ``geometry="axisymmetric"`` builds the radial
    grid out to the half-diagonal of that window with ``cells`` cells, the
    same physics on a colony with circular symmetry.
    """

    values = {
        "v": 0.2,  # millimeter / hour
        "Kv": 0.5,  # microgram / millimeter ** 2
        "c_ext": 0.1,  # microgram / millimeter
        "Dn": 0.02,  # millimeter ** 2 / hour
        "chi": 0.001,  # millimeter ** 3 / hour
        "b": 0.02,  # 1 / (millimeter * hour) per microgram / millimeter ** 2
        "a": 0.05,  # millimeter / hour
        "dn": 0.01,  # 1 / hour
        "cu": 0.05,  # millimeter / hour
        "Di": 0.1,  # millimeter ** 2 / hour
        "Da": 0.05,  # millimeter ** 4 / hour
    }
    values.update(overrides or {})
    units = {
        "v": "millimeter / hour",
        "Kv": SUBSTRATE_UNITS,
        "c_ext": "microgram / millimeter",
        "Dn": "millimeter ** 2 / hour",
        "chi": "millimeter ** 3 / hour",
        "b": "1 / (millimeter * hour * microgram / millimeter ** 2)",
        "a": "millimeter / hour",
        "dn": "1 / hour",
        "cu": "millimeter / hour",
        "Di": "millimeter ** 2 / hour",
        "Da": "millimeter ** 4 / hour",
    }
    if geometry == "axisymmetric":
        grid = SpatialGrid.axisymmetric(artificial_parameter("R", side_mm / np.sqrt(2.0), "millimeter"), cells)
    else:
        grid = SpatialGrid.no_flux(
            (artificial_parameter("L_x", side_mm, "millimeter"), artificial_parameter("L_y", side_mm, "millimeter")),
            (cells, cells),
        )
    fields = (
        FieldSpec("tips", TIP_UNITS, "hyphal tip density", "tips"),
        FieldSpec("hyphae", HYPHA_UNITS, "active hyphal length density", "hyphae"),
        FieldSpec("internal", SUBSTRATE_UNITS, "substrate carried inside the mycelium", "internal_substrate"),
        FieldSpec("external", SUBSTRATE_UNITS, "substrate in the medium", "external_substrate"),
    )
    processes = (
        TipExtension(
            name="extension", tip_field="tips", tip_units=TIP_UNITS, hypha_field="hyphae", hypha_units=HYPHA_UNITS,
            speed_symbol="v", substrate_field="internal", substrate_units=SUBSTRATE_UNITS, half_saturation_symbol="Kv",
            cost_field="internal", cost_units=SUBSTRATE_UNITS, cost_symbol="c_ext",
        ),
        TipMotion(
            name="motion", tip_field="tips", tip_units=TIP_UNITS, diffusivity_symbol="Dn",
            drift_field="hyphae", drift_units=HYPHA_UNITS, mobility_symbol="chi", drift_direction=-1,
        ),
        LateralBranching(
            name="branching", tip_field="tips", tip_units=TIP_UNITS, hypha_field="hyphae", hypha_units=HYPHA_UNITS,
            rate_symbol="b", substrate_field="internal", substrate_units=SUBSTRATE_UNITS,
        ),
        Anastomosis(name="anastomosis", tip_field="tips", tip_units=TIP_UNITS, hypha_field="hyphae", hypha_units=HYPHA_UNITS, rate_symbol="a"),
        FirstOrderLoss(name="tip_death", field="tips", field_units=TIP_UNITS, rate_symbol="dn"),
        LocalUptake(
            name="uptake", external_field="external", external_units=SUBSTRATE_UNITS, internal_field="internal",
            internal_units=SUBSTRATE_UNITS, hypha_field="hyphae", hypha_units=HYPHA_UNITS, rate_symbol="cu",
        ),
        Translocation(
            name="translocation", internal_field="internal", internal_units=SUBSTRATE_UNITS, diffusivity_symbol="Di",
            tip_field="tips", tip_units=TIP_UNITS, active_diffusivity_symbol="Da",
        ),
    )
    parameters = ParameterSet([artificial_parameter(symbol, values[symbol], units[symbol]) for symbol in values])
    return MyceliumModel(grid=grid, fields=fields, processes=processes, parameters=parameters, time_units="hour")


def central_inoculum(grid: SpatialGrid, *, radius_mm: float = 0.7, external_mass_per_area: float = 3.0) -> dict[str, Quantity]:
    """Initial fields: tips, hyphae and internal substrate inside a central disc, external substrate everywhere.

    The disc is centred on the window of a cartesian grid and on the axis of
    an axisymmetric one.
    """

    if grid.geometry == "axisymmetric":
        squared = (grid.coordinates[0] * 1e3) ** 2
    else:
        axes = np.meshgrid(*[axis * 1e3 for axis in grid.coordinates], indexing="ij")
        centre = [0.5 * float(length.quantity.to("millimeter").magnitude) for length in grid.axis_lengths if length.quantity is not None]
        squared = sum((axis - origin) ** 2 for axis, origin in zip(axes, centre, strict=True))
    inside = squared < radius_mm**2
    return {
        "tips": Q_(np.where(inside, 1.0, 0.0), TIP_UNITS),
        "hyphae": Q_(np.where(inside, 1.0, 0.0), HYPHA_UNITS),
        "internal": Q_(np.where(inside, 2.0, 0.0), SUBSTRATE_UNITS),
        "external": Q_(np.full(grid.shape, external_mass_per_area), SUBSTRATE_UNITS),
    }


def artificial_front_model(*, length_mm: float = 200.0, cells: int = 800, diffusivity: float = 1.0, branching: float = 0.25, anastomosis: float = 0.5, speed: float = 1.0) -> MyceliumModel:
    """The one-dimensional Edelstein system: tips diffuse, branch dichotomously, anastomose; hyphae are laid down.

    Its leading edge is linear in the tips, ``n_t = D n_xx + alpha n``, so a
    colony started from a compact inoculum spreads as a pulled front whose
    asymptotic speed is ``2 sqrt(D alpha)``.
    """

    grid = SpatialGrid.no_flux((artificial_parameter("L", length_mm, "millimeter"),), (cells,))
    fields = (FieldSpec("tips", TIP_UNITS, "tip density", "tips"), FieldSpec("hyphae", HYPHA_UNITS, "hyphal density", "hyphae"))
    processes = (
        TipExtension(name="extension", tip_field="tips", tip_units=TIP_UNITS, hypha_field="hyphae", hypha_units=HYPHA_UNITS, speed_symbol="v"),
        TipMotion(name="motion", tip_field="tips", tip_units=TIP_UNITS, diffusivity_symbol="Dn"),
        DichotomousBranching(name="branching", tip_field="tips", tip_units=TIP_UNITS, rate_symbol="alpha"),
        Anastomosis(name="anastomosis", tip_field="tips", tip_units=TIP_UNITS, hypha_field="hyphae", hypha_units=HYPHA_UNITS, rate_symbol="a"),
    )
    parameters = ParameterSet([
        artificial_parameter("v", speed, "millimeter / hour"),
        artificial_parameter("Dn", diffusivity, "millimeter ** 2 / hour"),
        artificial_parameter("alpha", branching, "1 / hour"),
        artificial_parameter("a", anastomosis, "millimeter / hour"),
    ])
    return MyceliumModel(grid=grid, fields=fields, processes=processes, parameters=parameters, time_units="hour")


__all__ = ["ARTIFICIAL_SOURCE", "HYPHA_UNITS", "SUBSTRATE_UNITS", "TIP_UNITS", "artificial_colony_model", "artificial_front_model", "artificial_parameter", "central_inoculum"]
