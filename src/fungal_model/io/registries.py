"""Registry-based loading for generic config sections."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast, get_args

from fungal_model.chemistry.stoichiometry import ElementalComposition, StoichiometricReactionMetadata, StoichiometricTerm
from fungal_model.chemistry.thermodynamics import GibbsFreeEnergyEstimate
from fungal_model.core.parameters import Parameter
from fungal_model.core.units import Q_, Quantity
from fungal_model.core.validators import (
    validate_charge_balance,
    validate_condition_specific_gibbs_feasibility,
    validate_electron_balance,
    validate_elemental_balance,
    validate_entropy_production_rate,
    validate_mass_balance,
    validate_non_negative,
    validate_reaction_quotient_gibbs_feasibility,
)
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
        registry.register("elemental_balance", load_elemental_balance_validator)
        registry.register("charge_balance", load_charge_balance_validator)
        registry.register("redox_balance", load_redox_balance_validator)
        registry.register("thermodynamic_metadata", load_thermodynamic_metadata_validator)
        registry.register("reaction_quotient_thermodynamic_metadata", load_reaction_quotient_thermodynamic_validator)
        registry.register("entropy_production_rate_metadata", load_entropy_production_rate_validator)
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


def load_elemental_balance_validator(data: Mapping[str, Any]) -> Callable[[Any], Any]:
    reaction = _reaction_metadata_from_config(_mapping(data.get("reaction", data), field_name="reaction"))
    absolute_tolerance = _optional_float(data.get("absolute_tolerance"))
    required = bool(data.get("required", True))
    allow_unsourced_for_testing = bool(data.get("allow_unsourced_for_testing", False))

    def validator(result: Any) -> Any:
        del result
        return validate_elemental_balance(
            reaction,
            absolute_tolerance=absolute_tolerance,
            required=required,
            allow_unsourced_for_testing=allow_unsourced_for_testing,
        )

    return validator


def load_charge_balance_validator(data: Mapping[str, Any]) -> Callable[[Any], Any]:
    reaction = _reaction_metadata_from_config(_mapping(data.get("reaction", data), field_name="reaction"))
    absolute_tolerance = _optional_float(data.get("absolute_tolerance"))
    required = bool(data.get("required", True))
    allow_unsourced_for_testing = bool(data.get("allow_unsourced_for_testing", False))

    def validator(result: Any) -> Any:
        del result
        return validate_charge_balance(
            reaction,
            absolute_tolerance=absolute_tolerance,
            required=required,
            allow_unsourced_for_testing=allow_unsourced_for_testing,
        )

    return validator


def load_redox_balance_validator(data: Mapping[str, Any]) -> Callable[[Any], Any]:
    reaction = _reaction_metadata_from_config(_mapping(data.get("reaction", data), field_name="reaction"))
    absolute_tolerance = _optional_float(data.get("absolute_tolerance"))
    required = bool(data.get("required", True))
    allow_unsourced_for_testing = bool(data.get("allow_unsourced_for_testing", False))

    def validator(result: Any) -> Any:
        del result
        return validate_electron_balance(
            reaction,
            absolute_tolerance=absolute_tolerance,
            required=required,
            allow_unsourced_for_testing=allow_unsourced_for_testing,
        )

    return validator


def load_thermodynamic_metadata_validator(data: Mapping[str, Any]) -> Callable[[Any], Any]:
    estimate = _gibbs_estimate_from_config(_mapping(data.get("estimate", data), field_name="estimate"))
    tolerance = _quantity(data.get("absolute_tolerance"))
    required = bool(data.get("required", True))
    allow_unsourced_for_testing = bool(data.get("allow_unsourced_for_testing", False))

    def validator(result: Any) -> Any:
        del result
        return validate_condition_specific_gibbs_feasibility(
            estimate,
            absolute_tolerance=tolerance,
            required=required,
            allow_unsourced_for_testing=allow_unsourced_for_testing,
        )

    return validator


def load_reaction_quotient_thermodynamic_validator(data: Mapping[str, Any]) -> Callable[[Any], Any]:
    estimate = _gibbs_estimate_from_config(_mapping(data.get("estimate", data), field_name="estimate"))
    reaction_quotient = Parameter.from_dict(_mapping(data.get("reaction_quotient"), field_name="reaction_quotient"))
    temperature = Parameter.from_dict(_mapping(data.get("temperature"), field_name="temperature"))
    tolerance = _quantity(data.get("absolute_tolerance"))
    required = bool(data.get("required", True))
    allow_unsourced_for_testing = bool(data.get("allow_unsourced_for_testing", False))

    def validator(result: Any) -> Any:
        del result
        return validate_reaction_quotient_gibbs_feasibility(
            standard_estimate=estimate,
            reaction_quotient=reaction_quotient,
            temperature=temperature,
            absolute_tolerance=tolerance,
            required=required,
            allow_unsourced_for_testing=allow_unsourced_for_testing,
        )

    return validator


def load_entropy_production_rate_validator(data: Mapping[str, Any]) -> Callable[[Any], Any]:
    condition_specific_delta_gibbs = Parameter.from_dict(
        _mapping(data.get("condition_specific_delta_gibbs"), field_name="condition_specific_delta_gibbs")
    )
    reaction_extent_rate = Parameter.from_dict(
        _mapping(data.get("reaction_extent_rate"), field_name="reaction_extent_rate")
    )
    temperature = Parameter.from_dict(_mapping(data.get("temperature"), field_name="temperature"))
    tolerance = _quantity(data.get("absolute_tolerance"))
    required = bool(data.get("required", True))
    allow_unsourced_for_testing = bool(data.get("allow_unsourced_for_testing", False))

    def validator(result: Any) -> Any:
        del result
        return validate_entropy_production_rate(
            condition_specific_delta_gibbs=condition_specific_delta_gibbs,
            reaction_extent_rate=reaction_extent_rate,
            temperature=temperature,
            absolute_tolerance=tolerance,
            required=required,
            allow_unsourced_for_testing=allow_unsourced_for_testing,
        )

    return validator


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


def _reaction_metadata_from_config(data: Mapping[str, Any]) -> StoichiometricReactionMetadata:
    return StoichiometricReactionMetadata(
        name=str(data.get("name") or data.get("reaction_name") or "configured static reaction"),
        reactants=_terms_from_config(data.get("reactants", ()), field_name="reactants"),
        products=_terms_from_config(data.get("products", ()), field_name="products"),
        source=_source_from_mapping(data),
        notes=str(data.get("notes", "")),
    )


def _terms_from_config(value: Any, *, field_name: str) -> tuple[StoichiometricTerm, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise ValueError(f"{field_name} must be a sequence of stoichiometric term mappings.")
    terms: list[StoichiometricTerm] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ValueError(f"{field_name}[{index}] must be a mapping.")
        terms.append(_term_from_config(item))
    return tuple(terms)


def _term_from_config(data: Mapping[str, Any]) -> StoichiometricTerm:
    return StoichiometricTerm(
        species=str(data["species"]),
        coefficient=float(data.get("coefficient", 1.0)),
        composition=_composition_from_config(data),
        charge=None if data.get("charge") is None else float(data["charge"]),
        charge_source=_optional_text(data.get("charge_source")),
        electron_equivalents=(
            None
            if data.get("electron_equivalents") is None
            else float(data["electron_equivalents"])
        ),
        electron_source=_optional_text(data.get("electron_source")),
        notes=str(data.get("notes", "")),
    )


def _composition_from_config(data: Mapping[str, Any]) -> ElementalComposition | None:
    composition_data = data.get("composition")
    if isinstance(composition_data, Mapping):
        source = _optional_text(composition_data.get("source"))
        notes = str(composition_data.get("notes", ""))
        if "elements" in composition_data:
            return ElementalComposition.from_elements(
                {str(key): float(value) for key, value in _mapping(composition_data["elements"], field_name="elements").items()},
                source=source,
                formula=str(composition_data.get("formula", "structured_element_counts")),
                notes=notes,
            )
        if "formula" in composition_data:
            return ElementalComposition.from_formula(
                str(composition_data["formula"]),
                source=source,
                notes=notes,
            )
    if "elements" in data:
        return ElementalComposition.from_elements(
            {str(key): float(value) for key, value in _mapping(data["elements"], field_name="elements").items()},
            source=_optional_text(data.get("composition_source")),
            formula=str(data.get("formula", "structured_element_counts")),
            notes=str(data.get("composition_notes", "")),
        )
    if data.get("formula") is not None:
        return ElementalComposition.from_formula(
            str(data["formula"]),
            source=_optional_text(data.get("composition_source")),
            notes=str(data.get("composition_notes", "")),
        )
    return None


def _gibbs_estimate_from_config(data: Mapping[str, Any]) -> GibbsFreeEnergyEstimate:
    delta_data = _mapping(data.get("delta_gibbs"), field_name="delta_gibbs")
    return GibbsFreeEnergyEstimate(
        reaction_name=str(data.get("reaction_name") or data.get("name") or "configured static reaction"),
        delta_gibbs=Parameter.from_dict(delta_data),
        conditions=_parameter_set_from_condition_config(data.get("conditions")),
        source=_source_from_mapping(data),
        notes=str(data.get("notes", "")),
    )


def _parameter_set_from_condition_config(value: Any) -> Any:
    if value is None:
        return parameter_set_from_config({"parameters": []})
    if isinstance(value, Mapping):
        if "parameters" in value:
            return parameter_set_from_config(value)
        return parameter_set_from_config({"parameters": [dict(value)]})
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return parameter_set_from_config({"parameters": list(value)})
    raise ValueError("conditions must be a parameter mapping, parameters mapping, or sequence of parameter mappings.")


def _source_from_mapping(data: Mapping[str, Any]) -> str | None:
    provenance = data.get("provenance")
    if isinstance(provenance, Mapping) and provenance.get("source") is not None:
        return str(provenance["source"])
    return _optional_text(data.get("source"))


def _mapping(value: Any, *, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping.")
    return value


def _optional_text(value: Any) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    return str(value)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


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
    "load_charge_balance_validator",
    "load_elemental_balance_validator",
    "load_entropy_production_rate_validator",
    "load_redox_balance_validator",
    "load_non_negative_validator",
    "load_one_to_one_product_map",
    "load_stoichiometric_product_map",
    "load_thermodynamic_metadata_validator",
    "load_reaction_quotient_thermodynamic_validator",
    "load_well_mixed_geometry",
]
