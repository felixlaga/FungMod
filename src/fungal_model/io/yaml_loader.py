"""YAML loaders for FungMod entities and parameter sets."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.entities import Enzyme, Environment
from fungal_model.fungi import EnzymeCapability, EnzymeProfile, Fungus, make_fungal_parameter_set
from fungal_model.fungi.metabolism import ProductAssimilation
from fungal_model.geometry import Film1DGeometry, WellMixedGeometry
from fungal_model.io.schema import validate_config
from fungal_model.substrates.pet import PETSubstrate, make_pet_parameter_set


def load_yaml_config(path: str | Path, *, validate: bool = True) -> dict[str, Any]:
    """Load a YAML config file and optionally validate its minimal schema."""

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"YAML config {path} did not produce a mapping.")
    if validate:
        validate_config(data)
    return data


def parameter_from_config(data: Mapping[str, Any]) -> Parameter:
    """Create a Parameter from a config parameter mapping."""

    return Parameter(
        name=str(data["name"]),
        symbol=str(data["symbol"]),
        value=data.get("value"),
        units=str(data["units"]),
        uncertainty=data.get("uncertainty"),
        source=data.get("source"),
        confidence_level=data.get("confidence_level", "unknown"),
        notes=str(data.get("notes", "")),
        measurement_method=data.get("measurement_method"),
    )


def parameter_set_from_config(data: Mapping[str, Any]) -> ParameterSet:
    return ParameterSet(parameter_from_config(parameter) for parameter in data.get("parameters", []) or [])


def load_parameter_set(path: str | Path) -> ParameterSet:
    return parameter_set_from_config(load_yaml_config(path))


def load_environment(path: str | Path) -> Environment:
    data = load_yaml_config(path)
    conditions = data.get("conditions", {})
    provenance = data["provenance"]
    return Environment(
        name=data["name"],
        temperature=_quantity(conditions.get("temperature")),
        ph=_quantity(conditions.get("ph")),
        oxygen_concentration=_quantity(conditions.get("oxygen_concentration")),
        oxygen_available=_quantity(conditions.get("oxygen_available")),
        water_activity=_quantity(conditions.get("water_activity")),
        source=provenance["source"],
        notes=provenance.get("notes", ""),
        validity_labels=tuple(data.get("validity_labels", ())),
    )


def load_enzyme(path: str | Path) -> Enzyme:
    data = load_yaml_config(path)
    provenance = data["provenance"]
    return Enzyme(
        name=data["name"],
        enzyme_class=data["enzyme_class"],
        target_bond_types=tuple(data.get("target_bond_types", ())),
        target_substrate_classes=tuple(data.get("target_substrate_classes", ())),
        target_substrate_names=tuple(data.get("target_substrate_names", ())),
        catalytic_parameters=parameter_set_from_config({"parameters": data.get("catalytic_parameters", [])}),
        adsorption_parameters=parameter_set_from_config({"parameters": data.get("adsorption_parameters", [])}),
        validity_labels=tuple(data.get("validity_labels", ())),
        source=provenance["source"],
        notes=provenance.get("notes", ""),
    )


def load_substrate(path: str | Path) -> PETSubstrate:
    data = load_yaml_config(path)
    if data.get("substrate_type") != "pet":
        raise ValueError("Only PET substrate config loading is implemented in this milestone.")
    return PETSubstrate(
        geometry_type=data.get("geometry_type", "unknown"),
        parameters=make_pet_parameter_set(parameter_from_config(item) for item in data.get("parameters", []) or []),
        notes=data.get("provenance", {}).get("notes", ""),
    )


def load_geometry(path: str | Path):
    data = load_yaml_config(path)
    geometry_type = data.get("geometry_type")
    provenance = data["provenance"]
    if geometry_type == "well_mixed":
        return WellMixedGeometry(
            volume=_quantity(data["volume"]),
            surface_area=_quantity(data.get("surface_area")),
            source=provenance["source"],
            notes=provenance.get("notes", ""),
        )
    if geometry_type == "film_1d":
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
    raise ValueError(f"Unsupported geometry_type: {geometry_type}")


def load_fungus(path: str | Path) -> Fungus:
    data = load_yaml_config(path)
    provenance = data["provenance"]
    capabilities = tuple(
        EnzymeCapability(
            name=item["name"],
            enzyme_class=item["enzyme_class"],
            target_substrate=item["target_substrate"],
            target_bond_type=item["target_bond_type"],
            evidence=item.get("evidence", ""),
            source=item.get("source", provenance["source"]),
            notes=item.get("notes", ""),
        )
        for item in data.get("enzyme_capabilities", ())
    )
    uptake = tuple(
        ProductAssimilation(
            product=item["product"],
            assimilable=bool(item["assimilable"]),
            source=item.get("source", provenance["source"]),
            notes=item.get("notes", ""),
        )
        for item in data.get("uptake_capabilities", ())
    )
    return Fungus(
        species_name=data["name"],
        enzyme_profile=EnzymeProfile(capabilities=capabilities, source=provenance["source"]),
        parameters=make_fungal_parameter_set(parameter_from_config(item) for item in data.get("parameters", []) or []),
        known_substrates=tuple(data.get("known_substrates", ())),
        uptake_capabilities=uptake,
        oxygen_requirement=data.get("oxygen_requirement", "unknown"),
        moisture_requirement=data.get("moisture_requirement", "unknown"),
        notes=provenance.get("notes", ""),
        references=(provenance["source"],),
    )


def _quantity(data: Mapping[str, Any] | None):
    if data is None:
        return None
    return Q_(data["value"], data["units"])


__all__ = [
    "load_enzyme",
    "load_environment",
    "load_fungus",
    "load_geometry",
    "load_parameter_set",
    "load_substrate",
    "load_yaml_config",
    "parameter_from_config",
    "parameter_set_from_config",
]
