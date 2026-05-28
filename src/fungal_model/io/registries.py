"""Registry-based loading for generic config sections."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast, get_args

from fungal_model.core.parameters import Parameter
from fungal_model.core.units import Q_, Quantity
from fungal_model.core.validators import validate_mass_balance, validate_non_negative
from fungal_model.geometry import Film1DGeometry, WellMixedGeometry
from fungal_model.processes import ProductReleaseMap
from fungal_model.substrates.base import (
    CompletenessLevel,
    DegradationModelPreference,
    DegradationProduct,
    PhysicalState,
    Substrate,
)

from .parameters import parameter_set_from_config


class RegistryLookupError(ValueError):
    """Raised when no registered loader can handle a config entry."""


@dataclass(frozen=True)
class RegistryEntry:
    """Named loader entry."""

    name: str
    loader: Callable[[Mapping[str, Any]], Any]


class _LoaderRegistry:
    key_field: str
    entry_label: str

    def __init__(self) -> None:
        self._loaders: dict[str, Callable[[Mapping[str, Any]], Any]] = {}

    def register(self, name: str, loader: Callable[[Mapping[str, Any]], Any]) -> None:
        key = _clean_name(name, field_name=f"{self.entry_label} name")
        if key in self._loaders:
            raise ValueError(f"Duplicate {self.entry_label} loader: {key}")
        self._loaders[key] = loader

    def load(self, data: Mapping[str, Any]) -> Any:
        key = _clean_name(data.get(self.key_field), field_name=self.key_field)
        try:
            loader = self._loaders[key]
        except KeyError as exc:
            available = ", ".join(sorted(self._loaders)) or "none"
            raise RegistryLookupError(
                f"Unsupported {self.entry_label} {key!r}. Registered loaders: {available}."
            ) from exc
        return loader(data)

    def registered_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._loaders))

    def to_dict(self) -> dict[str, Any]:
        return {
            "key_field": self.key_field,
            "entry_label": self.entry_label,
            "registered_names": list(self.registered_names()),
        }


class SubstrateLoaderRegistry(_LoaderRegistry):
    """Registry for substrate config loaders."""

    key_field = "substrate_type"
    entry_label = "substrate"

    @classmethod
    def default(cls) -> "SubstrateLoaderRegistry":
        registry = cls()
        registry.register("generic_solid", load_generic_solid_substrate)
        registry.register("generic_dissolved", load_generic_dissolved_substrate)
        return registry


class GeometryLoaderRegistry(_LoaderRegistry):
    """Registry for geometry config loaders."""

    key_field = "geometry_type"
    entry_label = "geometry"

    @classmethod
    def default(cls) -> "GeometryLoaderRegistry":
        registry = cls()
        registry.register("well_mixed", load_well_mixed_geometry)
        registry.register("film_1d", load_film_1d_geometry)
        return registry


class ProductMapRegistry(_LoaderRegistry):
    """Registry for product-map config loaders."""

    key_field = "product_map_type"
    entry_label = "product map"

    @classmethod
    def default(cls) -> "ProductMapRegistry":
        registry = cls()
        registry.register("one_to_one", load_one_to_one_product_map)
        registry.register("stoichiometric", load_stoichiometric_product_map)
        return registry


class ValidatorRegistry(_LoaderRegistry):
    """Registry for result-validator config loaders."""

    key_field = "validator_type"
    entry_label = "validator"

    @classmethod
    def default(cls) -> "ValidatorRegistry":
        registry = cls()
        registry.register("non_negative", load_non_negative_validator)
        registry.register("mass_balance", load_mass_balance_validator)
        return registry


_PHYSICAL_STATES = {"dissolved", "solid_polymer", "solid_biomass", "mixed_solid", "unknown"}
_COMPLETENESS_LEVELS = set(get_args(CompletenessLevel))
_DEGRADATION_MODELS = {"homogeneous_dissolved", "heterogeneous_surface", "reaction_diffusion", "unknown"}


def load_generic_solid_substrate(data: Mapping[str, Any]) -> Substrate:
    return _load_generic_substrate(data, physical_state="mixed_solid")


def load_generic_dissolved_substrate(data: Mapping[str, Any]) -> Substrate:
    return _load_generic_substrate(data, physical_state="dissolved")


def _load_generic_substrate(data: Mapping[str, Any], *, physical_state: PhysicalState) -> Substrate:
    provenance = data.get("provenance", {})
    return Substrate(
        name=str(data["name"]),
        chemical_class=str(data.get("chemical_class", "generic benchmark material")),
        physical_state=cast(
            PhysicalState,
            _choice(data, "physical_state", physical_state, _PHYSICAL_STATES),
        ),
        bond_types=tuple(data.get("bond_types", ()) or ()),
        accessible_bonds=tuple(data.get("accessible_bonds", ()) or ()),
        required_enzyme_classes=tuple(data.get("required_enzyme_classes", ()) or ()),
        degradation_products=tuple(
            DegradationProduct(
                name=str(product["name"]),
                formula=product.get("formula"),
                assimilable=product.get("assimilable"),
                notes=str(product.get("notes", "")),
                source=product.get("source", provenance.get("source")),
            )
            for product in data.get("degradation_products", ()) or ()
        ),
        parameters=parameter_set_from_config(data),
        completeness=cast(
            CompletenessLevel,
            _choice(data, "completeness", "partial", _COMPLETENESS_LEVELS),
        ),
        default_degradation_model=cast(
            DegradationModelPreference,
            _choice(data, "default_degradation_model", "unknown", _DEGRADATION_MODELS),
        ),
        water_activity_dependence=str(data.get("water_activity_dependence", "unknown")),
        notes=str(provenance.get("notes", data.get("notes", ""))),
        references=(str(provenance["source"]),) if provenance.get("source") else (),
    )


def load_well_mixed_geometry(data: Mapping[str, Any]) -> WellMixedGeometry:
    provenance = data["provenance"]
    return WellMixedGeometry(
        volume=_required_quantity(data["volume"], name="well_mixed.volume"),
        surface_area=_quantity(data.get("surface_area")),
        source=provenance["source"],
        notes=provenance.get("notes", ""),
    )


def load_film_1d_geometry(data: Mapping[str, Any]) -> Film1DGeometry:
    provenance = data["provenance"]
    length_data = data["length"]
    length_parameter = Parameter(
        name="1D film length",
        symbol=str(length_data.get("symbol", "L_film")),
        value=length_data["value"],
        units=length_data["units"],
        uncertainty=length_data.get("uncertainty"),
        source=provenance["source"],
        confidence_level=provenance["confidence_level"],
        notes=provenance.get("notes", ""),
        measurement_method=provenance.get("measurement_method"),
    )
    return Film1DGeometry(
        length=length_parameter,
        n_cells=int(data["n_cells"]),
        surface_area=_quantity(data.get("surface_area")),
        volume=_quantity(data.get("volume")),
        source=provenance["source"],
        notes=provenance.get("notes", ""),
    )


def load_one_to_one_product_map(data: Mapping[str, Any]) -> ProductReleaseMap:
    provenance = data.get("provenance", {})
    return ProductReleaseMap.one_to_one(
        substrate_state=str(data["substrate_state"]),
        product_state=str(data["product_state"]),
        notes=str(data.get("notes", "")),
        name=None if data.get("name") is None else str(data["name"]),
        maturity=None if data.get("maturity") is None else str(data["maturity"]),
        source=provenance.get("source"),
    )


def load_stoichiometric_product_map(data: Mapping[str, Any]) -> ProductReleaseMap:
    provenance = data.get("provenance", {})
    return ProductReleaseMap(
        reactants={str(name): float(value) for name, value in data["reactants"].items()},
        products={str(name): float(value) for name, value in data["products"].items()},
        notes=str(data.get("notes", "")),
        name=None if data.get("name") is None else str(data["name"]),
        maturity=None if data.get("maturity") is None else str(data["maturity"]),
        source=provenance.get("source"),
    )


def load_non_negative_validator(data: Mapping[str, Any]) -> Callable[[Any], Any]:
    species = tuple(data.get("species", ()) or ()) or None
    return lambda result: validate_non_negative(result, species=species)


def load_mass_balance_validator(data: Mapping[str, Any]) -> Callable[[Any], Any]:
    weights = data.get("conserved_weights")
    closed_system = bool(data.get("closed_system", True))
    return lambda result: validate_mass_balance(
        result,
        conserved_weights=None if weights is None else dict(weights),
        closed_system=closed_system,
    )


def _quantity(data: Mapping[str, Any] | None) -> Quantity | None:
    if data is None:
        return None
    return Q_(data["value"], data["units"])


def _required_quantity(data: Mapping[str, Any] | None, *, name: str) -> Quantity:
    quantity = _quantity(data)
    if quantity is None:
        raise ValueError(f"{name} must be provided.")
    return quantity


def _choice(data: Mapping[str, Any], field: str, default: str, allowed: set[str]) -> str:
    value = str(data.get(field, default))
    if value not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise ValueError(f"{field} must be one of {allowed_values}; got {value!r}.")
    return value


def _clean_name(value: Any, *, field_name: str) -> str:
    if value is None or str(value).strip() == "":
        raise RegistryLookupError(f"{field_name} must be provided.")
    return str(value)


__all__ = [
    "GeometryLoaderRegistry",
    "ProductMapRegistry",
    "RegistryEntry",
    "RegistryLookupError",
    "SubstrateLoaderRegistry",
    "ValidatorRegistry",
    "load_film_1d_geometry",
    "load_generic_dissolved_substrate",
    "load_generic_solid_substrate",
    "load_mass_balance_validator",
    "load_non_negative_validator",
    "load_one_to_one_product_map",
    "load_stoichiometric_product_map",
    "load_well_mixed_geometry",
]
