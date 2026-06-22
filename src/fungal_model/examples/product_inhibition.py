"""Example fixture setup for reversible product-inhibition virtual experiments."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, cast

import yaml


def prepare_reversible_product_inhibition_example_registry(
    destination: str | Path,
    *,
    source_registry: str | Path = "data_registry/registry_index.yml",
    inhibition_constant_mM: float = 2.0,
    overwrite: bool = True,
) -> Path:
    """Copy the local registry and add an explicit BIO-003 example K_i record.

    The returned registry is an exploratory software-test example. It is useful
    for demonstrating how the public virtual-experiment API exposes configured
    reversible product inhibition in standard output tables, but it is not
    validation data and must not be interpreted as a calibrated biological
    record.
    """

    if inhibition_constant_mM <= 0:
        raise ValueError("The example product-inhibition K_i must be positive.")

    source_index = Path(source_registry)
    source_dir = source_index.parent
    target_dir = Path(destination)
    if target_dir.exists():
        if not overwrite:
            raise FileExistsError(f"Example registry destination already exists: {target_dir}")
        shutil.rmtree(target_dir)
    shutil.copytree(source_dir, target_dir)

    _add_chain_template_modifier(target_dir / "case_templates" / "case_templates.yml")
    _add_example_inhibition_parameter(
        target_dir / "parameters" / "parameter_records.yml",
        inhibition_constant_mM=inhibition_constant_mM,
    )
    return target_dir / source_index.name


def _add_chain_template_modifier(template_path: Path) -> None:
    template_data = _yaml_mapping(template_path)
    records = cast(list[dict[str, Any]], template_data["records"])
    for record in records:
        if record["record_id"] != "bio002_extracellular_enzyme_chain_template":
            continue
        metadata = record["process_state_metadata"]
        metadata["parameter_record_ids"]["product_inhibition_constant"] = (
            "bio003_example_product_inhibition_constant"
        )
        metadata["process_templates"][1]["modifiers"] = [
            {
                "type": "product_inhibition",
                "product_state_role": "product",
                "inhibition_constant_role": "product_inhibition_constant",
            }
        ]
        record.setdefault("limitations", []).append(
            "BIO-003 example product inhibition uses an explicit exploratory K_i fixture only; "
            "it is not validation data."
        )
        template_path.write_text(yaml.safe_dump(template_data, sort_keys=False), encoding="utf-8")
        return
    raise ValueError("Missing BIO-002 extracellular enzyme-chain template in copied registry.")


def _add_example_inhibition_parameter(parameter_path: Path, *, inhibition_constant_mM: float) -> None:
    parameter_data = _yaml_mapping(parameter_path)
    records = cast(list[dict[str, Any]], parameter_data["records"])
    records.insert(
        0,
        {
            "record_id": "bio003_example_product_inhibition_constant",
            "name": "BIO-003 example reversible product inhibition K_i",
            "maturity": "exploratory_example_fixture",
            "provenance": {
                "source": "FungMod BIO-003 reversible product-inhibition public example fixture.",
                "confidence_level": "exploratory_example",
                "bio_milestone": "BIO-003",
                "notes": (
                    "Explicit artificial K_i used only to demonstrate configured reversible "
                    "product-inhibition outputs; not validation data."
                ),
            },
            "parameter_symbol": "K_i_bio003_product_example",
            "process_type": "homogeneous_michaelis_menten",
            "enzyme_class": None,
            "substrate_class": None,
            "fungus_id": None,
            "substrate_id": None,
            "environment_id": None,
            "value": {
                "kind": "exact",
                "value": inhibition_constant_mM,
                "units": "mM",
                "source": "FungMod BIO-003 reversible product-inhibition public example fixture.",
                "confidence_level": "exploratory_example",
                "notes": "Artificial example value; not measured, calibrated, or validated.",
            },
            "range_scope": "researcher_facing_example_fixture",
            "range_interpretation": "configured mechanics only",
            "allowed_use": "exploratory_example_only_not_scientific_validation",
            "notes": (
                "Fixture K_i for demonstrating explicit registry-backed product-inhibition "
                "assembly and output inspection."
            ),
        },
    )
    parameter_path.write_text(yaml.safe_dump(parameter_data, sort_keys=False), encoding="utf-8")


def _yaml_mapping(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML mapping in {path}")
    return data
