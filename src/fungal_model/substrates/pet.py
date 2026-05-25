"""Polyethylene terephthalate (PET) substrate description.

This module describes PET as a solid polyester substrate. It deliberately does
not implement a hydrolysis rate law. PET should not be treated as an ordinary
dissolved substrate by default; later kinetics should consume its accessible
surface metadata through a heterogeneous surface model.

Numeric material properties are represented as ``Parameter`` objects. The
default constructor marks them as explicitly unknown so callers cannot
accidentally run a scientific PET simulation with guessed values.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.provenance import UnknownParameterError
from fungal_model.core.units import Q_, Quantity, UnitError, assert_compatible
from fungal_model.substrates.base import DegradationProduct, Substrate

PETGeometryType = Literal["film", "powder", "fiber", "bead", "unknown"]

PET_REFERENCE_NOTE = (
    "Common polymer chemistry identity for polyethylene terephthalate and its "
    "ester-hydrolysis products; parameter values are not supplied by this note."
)

TOTAL_FRACTION = Parameter(
    name="complete material fraction",
    symbol="fraction_total",
    value=1.0,
    units="dimensionless",
    uncertainty=None,
    source="Mathematical definition of a complete fraction; not a measured PET property.",
    confidence_level="high",
    notes="Used to derive amorphous fraction as 1 - crystallinity when no explicit amorphous fraction is provided.",
    measurement_method="definition",
)

ZERO_FRACTION = Parameter(
    name="minimum physical fraction",
    symbol="fraction_zero",
    value=0.0,
    units="dimensionless",
    uncertainty=None,
    source="Mathematical lower bound for a physical fraction; not a measured PET property.",
    confidence_level="high",
    notes="Used only for parameter validation.",
    measurement_method="definition",
)

MINIMUM_ROUGHNESS_FACTOR = Parameter(
    name="minimum roughness factor",
    symbol="roughness_min",
    value=1.0,
    units="dimensionless",
    uncertainty=None,
    source="Definition of roughness factor as actual area divided by projected area.",
    confidence_level="high",
    notes="A perfectly smooth surface has roughness factor 1 by definition.",
    measurement_method="definition",
)

PET_PARAMETER_UNITS = {
    "rho_pet": "kilogram / meter ** 3",
    "chi_c": "dimensionless",
    "phi_amorphous": "dimensionless",
    "A_surface": "meter ** 2",
    "L_thickness": "meter",
    "d_particle": "meter",
    "r_rough": "dimensionless",
    "A_accessible": "meter ** 2",
}

PET_PARAMETER_NAMES = {
    "rho_pet": "PET density",
    "chi_c": "PET crystallinity fraction",
    "phi_amorphous": "PET amorphous fraction",
    "A_surface": "PET geometric surface area",
    "L_thickness": "PET film or fiber thickness",
    "d_particle": "PET particle or bead characteristic size",
    "r_rough": "PET surface roughness factor",
    "A_accessible": "PET accessible surface area",
}


def _unknown_pet_parameter(symbol: str) -> Parameter:
    return Parameter(
        name=PET_PARAMETER_NAMES[symbol],
        symbol=symbol,
        value=None,
        units=PET_PARAMETER_UNITS[symbol],
        uncertainty=None,
        source="Not provided; explicitly marked unknown by PET substrate construction.",
        confidence_level="unknown",
        notes=(
            "Stage 3 records this PET material property but does not invent a "
            "value. Supply a sourced Parameter before scientific simulation."
        ),
        measurement_method=None,
    )


def make_pet_parameter_set(overrides: Iterable[Parameter] | None = None) -> ParameterSet:
    """Create a complete PET parameter set with optional sourced overrides."""

    parameters = {
        symbol: _unknown_pet_parameter(symbol)
        for symbol in PET_PARAMETER_UNITS
    }
    for override in overrides or ():
        if override.symbol not in PET_PARAMETER_UNITS:
            raise KeyError(f"{override.symbol!r} is not a recognized PET parameter symbol.")
        expected_units = PET_PARAMETER_UNITS[override.symbol]
        try:
            Q_(1, override.units).to(expected_units)
        except Exception as exc:
            raise UnitError(
                f"PET parameter {override.symbol} must use units compatible with {expected_units}."
            ) from exc
        parameters[override.symbol] = override
    return ParameterSet(parameters.values())


def pet_surface_assumption() -> Assumption:
    """Return the default PET modelling assumption for downstream kinetics."""

    return Assumption(
        name="PET is a solid surface-limited substrate",
        description=(
            "PET is represented as a solid polyester substrate whose enzymatic "
            "hydrolysis should depend on accessible surface area, morphology, "
            "and amorphous accessibility."
        ),
        justification=(
            "PET degradation occurs at polymer-water/enzyme interfaces rather "
            "than as homogeneous dissolved-substrate turnover."
        ),
        known_limitations=(
            "The substrate object stores material metadata only. Surface "
            "kinetics are implemented separately; dynamic morphology changes, "
            "surface renewal, crystallinity evolution, and transport remain "
            "outside this substrate definition."
        ),
        source=PET_REFERENCE_NOTE,
    )


def default_pet_degradation_products() -> tuple[DegradationProduct, ...]:
    """Return common PET hydrolysis products without assigning assimilation."""

    source = PET_REFERENCE_NOTE
    return (
        DegradationProduct(
            name="MHET",
            formula="C10H10O5",
            assimilable=None,
            notes="Mono(2-hydroxyethyl) terephthalate; product uptake and metabolism are not assumed.",
            source=source,
        ),
        DegradationProduct(
            name="BHET",
            formula="C12H14O6",
            assimilable=None,
            notes="Bis(2-hydroxyethyl) terephthalate; product uptake and metabolism are not assumed.",
            source=source,
        ),
        DegradationProduct(
            name="terephthalic acid",
            formula="C8H6O4",
            assimilable=None,
            notes="Assimilation requires organism-specific transport and metabolism evidence.",
            source=source,
        ),
        DegradationProduct(
            name="ethylene glycol",
            formula="C2H6O2",
            assimilable=None,
            notes="Assimilation requires organism-specific transport and metabolism evidence.",
            source=source,
        ),
    )


def _known_quantity(parameter: Parameter, expected_units: str) -> Quantity | None:
    if parameter.quantity is None:
        return None
    return assert_compatible(parameter.quantity, expected_units, name=parameter.symbol)


def _validate_fraction(parameter: Parameter) -> None:
    value = _known_quantity(parameter, "dimensionless")
    if value is None:
        return
    values = np.asarray(value.magnitude, dtype=float)
    lower = float(ZERO_FRACTION.quantity.to("dimensionless").magnitude)
    upper = float(TOTAL_FRACTION.quantity.to("dimensionless").magnitude)
    if np.any(values < lower) or np.any(values > upper):
        raise ValueError(f"{parameter.symbol} must be between {lower} and {upper}.")


def _validate_non_negative(parameter: Parameter, expected_units: str) -> None:
    value = _known_quantity(parameter, expected_units)
    if value is None:
        return
    if np.any(np.asarray(value.magnitude, dtype=float) < 0):
        raise ValueError(f"{parameter.symbol} must be non-negative.")


@dataclass(frozen=True, init=False)
class PETSubstrate(Substrate):
    """PET substrate metadata with provenance-backed physical properties."""

    geometry_type: PETGeometryType
    polymer_type: str
    repeating_unit: str
    dominant_cleavable_bond_type: str

    def __init__(
        self,
        *,
        geometry_type: PETGeometryType = "unknown",
        parameters: ParameterSet | None = None,
        notes: str = "",
        references: tuple[str, ...] = (PET_REFERENCE_NOTE,),
    ) -> None:
        if geometry_type not in ("film", "powder", "fiber", "bead", "unknown"):
            raise ValueError(f"Unsupported PET geometry_type: {geometry_type}")
        parameter_set = parameters or make_pet_parameter_set()
        assumptions = (pet_surface_assumption(),)
        Substrate.__init__(
            self,
            name="polyethylene terephthalate",
            chemical_class="synthetic polyester",
            physical_state="solid_polymer",
            bond_types=("ester",),
            accessible_bonds=("ester",),
            required_enzyme_classes=(
                "PETase-like hydrolase",
                "cutinase",
                "esterase",
            ),
            degradation_products=default_pet_degradation_products(),
            parameters=parameter_set,
            assumptions=assumptions,
            completeness="partial",
            default_degradation_model="heterogeneous_surface",
            notes=(
                notes
                or "Stage 3 PET metadata only; no PET hydrolysis kinetics are implemented here."
            ),
            references=references,
        )
        object.__setattr__(self, "geometry_type", geometry_type)
        object.__setattr__(self, "polymer_type", "polyester")
        object.__setattr__(self, "repeating_unit", "C10H8O4")
        object.__setattr__(self, "dominant_cleavable_bond_type", "ester")
        self.validate(require_parameter_values=False)

    @property
    def density(self) -> Parameter:
        return self.parameters.get("rho_pet")

    @property
    def crystallinity(self) -> Parameter:
        return self.parameters.get("chi_c")

    @property
    def amorphous_fraction(self) -> Parameter:
        return self.parameters.get("phi_amorphous")

    @property
    def surface_area(self) -> Parameter:
        return self.parameters.get("A_surface")

    @property
    def thickness(self) -> Parameter:
        return self.parameters.get("L_thickness")

    @property
    def particle_size(self) -> Parameter:
        return self.parameters.get("d_particle")

    @property
    def roughness_factor(self) -> Parameter:
        return self.parameters.get("r_rough")

    @property
    def accessible_surface_area_parameter(self) -> Parameter:
        return self.parameters.get("A_accessible")

    @property
    def is_dissolved_by_default(self) -> bool:
        return False

    @property
    def uses_surface_degradation_by_default(self) -> bool:
        return self.default_degradation_model == "heterogeneous_surface"

    def validate(
        self,
        *,
        allow_unsourced_for_testing: bool = False,
        require_parameter_values: bool = False,
    ) -> None:
        for symbol, expected_units in PET_PARAMETER_UNITS.items():
            parameter = self.parameters.get(symbol)
            try:
                Q_(1, parameter.units).to(expected_units)
            except Exception as exc:
                raise UnitError(
                    f"PET parameter {symbol} must use units compatible with {expected_units}."
                ) from exc
        super().validate(
            allow_unsourced_for_testing=allow_unsourced_for_testing,
            require_parameter_values=require_parameter_values,
        )
        _validate_fraction(self.crystallinity)
        _validate_fraction(self.amorphous_fraction)
        _validate_non_negative(self.density, "kilogram / meter ** 3")
        _validate_non_negative(self.surface_area, "meter ** 2")
        _validate_non_negative(self.thickness, "meter")
        _validate_non_negative(self.particle_size, "meter")
        _validate_non_negative(self.accessible_surface_area_parameter, "meter ** 2")
        roughness = _known_quantity(self.roughness_factor, "dimensionless")
        if roughness is not None:
            minimum = float(MINIMUM_ROUGHNESS_FACTOR.quantity.to("dimensionless").magnitude)
            if np.any(np.asarray(roughness.magnitude, dtype=float) < minimum):
                raise ValueError(f"r_rough must be at least {minimum}.")

    def effective_amorphous_fraction(self) -> Quantity | None:
        """Return explicit amorphous fraction, or derive it from crystallinity."""

        explicit = _known_quantity(self.amorphous_fraction, "dimensionless")
        if explicit is not None:
            return explicit
        crystallinity = _known_quantity(self.crystallinity, "dimensionless")
        if crystallinity is None:
            return None
        return (
            TOTAL_FRACTION.quantity.to("dimensionless")
            - crystallinity.to("dimensionless")
        )

    def accessible_surface_area(self) -> Quantity | None:
        """Return explicit or metadata-derived accessible PET surface area.

        If `A_accessible` is supplied, it is treated as an explicit material
        parameter. Otherwise, this Stage 3 helper derives a provisional
        accessible area as:

        ``A_surface * r_rough * effective_amorphous_fraction``

        This is metadata bookkeeping, not a validated PET hydrolysis model.
        """

        explicit = _known_quantity(self.accessible_surface_area_parameter, "meter ** 2")
        if explicit is not None:
            return explicit
        surface_area = _known_quantity(self.surface_area, "meter ** 2")
        roughness = _known_quantity(self.roughness_factor, "dimensionless")
        amorphous_fraction = self.effective_amorphous_fraction()
        if surface_area is None or roughness is None or amorphous_fraction is None:
            return None
        return assert_compatible(
            surface_area * roughness * amorphous_fraction,
            "meter ** 2",
            name="derived accessible PET surface area",
        )

    def require_accessible_surface_area(self) -> Quantity:
        """Return accessible surface area or raise if inputs remain unknown."""

        area = self.accessible_surface_area()
        if area is None:
            raise UnknownParameterError(
                "Accessible PET surface area is unknown. Supply A_accessible, "
                "or supply A_surface, r_rough, and phi_amorphous/chi_c."
            )
        return area

    def to_dict(self) -> dict[str, object]:
        data = super().to_dict()
        data.update(
            {
                "geometry_type": self.geometry_type,
                "polymer_type": self.polymer_type,
                "repeating_unit": self.repeating_unit,
                "dominant_cleavable_bond_type": self.dominant_cleavable_bond_type,
                "is_dissolved_by_default": self.is_dissolved_by_default,
                "uses_surface_degradation_by_default": self.uses_surface_degradation_by_default,
            }
        )
        accessible_area = self.accessible_surface_area()
        if accessible_area is not None:
            data["accessible_surface_area_effective"] = {
                "value": accessible_area.magnitude,
                "units": str(accessible_area.units),
            }
        else:
            data["accessible_surface_area_effective"] = None
        return data


__all__ = [
    "MINIMUM_ROUGHNESS_FACTOR",
    "PETGeometryType",
    "PETSubstrate",
    "PET_PARAMETER_NAMES",
    "PET_PARAMETER_UNITS",
    "TOTAL_FRACTION",
    "ZERO_FRACTION",
    "default_pet_degradation_products",
    "make_pet_parameter_set",
    "pet_surface_assumption",
]
