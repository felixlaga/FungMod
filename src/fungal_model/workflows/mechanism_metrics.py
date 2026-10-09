"""Optional mechanism reductions; no default metrics or thresholds for legacy models."""

from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from fungal_model.io.model_config import ModelConfig
from fungal_model.results import SimulationResult
from fungal_model.api.ph_metrics import trajectory_metrics as ph_metrics


def summarize_mechanisms(config: ModelConfig, result: SimulationResult) -> list[dict[str, Any]]:
    from fungal_model.api.culture_metrics import trajectory_metrics as culture_metrics
    from fungal_model.api.mechanism_reductions import trajectory_metrics as kinetic_metrics

    kinetic = kinetic_metrics(config, result)

    template = config.raw.get("case_template")
    declared_roles = (
        template.get("output_state_roles") or template.get("state_roles")
        if isinstance(template, Mapping) else None
    )
    roles = (
        {str(role): name for role, name in declared_roles.items() if isinstance(name, str) and name}
        if isinstance(declared_roles, Mapping) else {}
    )
    for process in config.processes:
        if process.process_type == "proton_balance_ph":
            roles["ph"] = str(process.states["ph"])
            mode = (process.raw or {})["balance"]["mode"]
            if mode in {"proton_ledger", "titrant"}:
                roles["ledger_titrant" if mode == "titrant" else "proton_excess"] = str(process.states["output"])
    if not any(role in roles for role in ("ph", "soluble_product", "dissolved_oxygen")):
        return kinetic
    rows = []
    for index, time in enumerate(result.time.magnitude):
        row: dict[str, Any] = {"time": float(time), "time_units": str(result.time.units)}
        for name, quantity in result.states.items():
            row[name] = float(quantity.magnitude[index])
            row[name + "_units"] = str(quantity.units)
        rows.append(row)
    threshold = config.raw.get("metric_definitions", {}).get("oxygen_threshold")
    medium = config.raw.get("provenance", {}).get("medium", {}).get("rows", ())
    return [*culture_metrics(rows, roles, oxygen_threshold=threshold), *ph_metrics(rows, roles, medium_rows=medium), *kinetic]
