"""YAML loaders for FungMod entities and parameter sets."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Q_
from fungal_model.entities import Enzyme, Environment
from fungal_model.fungi import EnzymeCapability, EnzymeProfile, Fungus, make_fungal_parameter_set
from fungal_model.fungi.metabolism import ProductAssimilation
from fungal_model.io.parameters import parameter_from_config, parameter_set_from_config
from fungal_model.io.registries import GeometryLoaderRegistry, SubstrateLoaderRegistry
from fungal_model.io.schema import validate_config


def load_yaml_config(path: str | Path, *, validate: bool = True) -> dict[str, Any]:
    """Load a YAML config file and optionally validate its minimal schema."""

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"YAML config {path} did not produce a mapping.")
    if validate:
        validate_config(data)
    return data


def load_parameter_set(path: str | Path) -> ParameterSet:
    return parameter_set_from_config(load_yaml_config(path))


def load_environment(path: str | Path) -> Environment:
    data = load_yaml_config(path)
    return environment_from_config(data)


def environment_from_config(data: Mapping[str, Any]) -> Environment:
    """Build an environment entity from an already-loaded config mapping."""

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
    return enzyme_from_config(data)


def enzyme_from_config(data: Mapping[str, Any]) -> Enzyme:
    """Build an enzyme entity from an already-loaded config mapping."""

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


def load_substrate(path: str | Path, *, registry: SubstrateLoaderRegistry | None = None):
    data = load_yaml_config(path)
    return (registry or SubstrateLoaderRegistry.default()).load(data)


def load_geometry(path: str | Path, *, registry: GeometryLoaderRegistry | None = None):
    data = load_yaml_config(path)
    return (registry or GeometryLoaderRegistry.default()).load(data)


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
    "enzyme_from_config",
    "environment_from_config",
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
