"""Explicit table-to-config route for structural synergy and peroxide kinetics.

These inputs use their own manifest and precise physical state roles; they do
not reinterpret ordinary enzyme-network CSV rows. Every concentration,
kinetic constant, structural convention and product yield is supplied and
sourced. Generated zero-valued cumulative ledgers are bookkeeping identities.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from fungal_model.core.units import Q_, assert_compatible
from fungal_model.io.model_config import ModelConfig
from fungal_model.workflows.configured_model import (
    ConfiguredInputLoader,
    ConfiguredProcessAssembler,
    require_runnable_config,
)


class MechanismTablesError(ValueError):
    """A source, value, unit, binding or structural input is missing or invalid."""


def _rows(folder: Path, filename: str, columns: set[str], *, optional: bool = False) -> list[dict[str, str]]:
    path = folder / filename
    if optional and not path.exists():
        return []
    if not path.exists():
        raise MechanismTablesError(f"{filename}: required input file is missing.")
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not columns <= set(reader.fieldnames or ()):
            raise MechanismTablesError(f"{filename}: missing columns {sorted(columns - set(reader.fieldnames or ()))}.")
        result = []
        for line, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                raise MechanismTablesError(f"{filename} row {line}: malformed CSV row.")
            cleaned = {key: value.strip() for key, value in row.items()}
            for key in columns:
                if not cleaned[key]:
                    raise MechanismTablesError(f"{filename} row {line}: {key} must be explicit.")
            result.append(cleaned)
        return result


def _number(value: str, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise MechanismTablesError(f"{field}: expected a finite non-negative number.") from exc
    if not np.isfinite(result) or result < 0:
        raise MechanismTablesError(f"{field}: expected a finite non-negative number.")
    return result


def assemble_mechanism_tables(folder: str | Path) -> dict[str, Any]:
    """Build and preflight a complete configuration from explicit user tables.

    ``mechanism.yml`` requires name, mechanism, mode, maturity, source, time.
    ``states.csv``: state,role,value,units,source[,chain_length].
    ``kinetics.csv``: quantity,value,units,source.
    ``feeds.csv`` (peroxide only): state,rate,units,source.
    An optional initial peroxide pool plus no feed is a stated batch experiment.
    Chain manifest additionally requires solid_min_length, exo_fragment_length,
    and structure_source. Parameter quantity names are demonstrated in the
    shipped ``data/user_mechanisms`` examples.
    """
    folder = Path(folder)
    manifest_path = folder / "mechanism.yml"
    if not manifest_path.exists():
        raise MechanismTablesError("mechanism.yml is required.")
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise MechanismTablesError("mechanism.yml must contain a mapping.")
    for key in ("name", "mechanism", "mode", "maturity", "source", "time"):
        if key not in manifest or not str(manifest[key]).strip():
            raise MechanismTablesError(f"mechanism.yml: {key} must be explicit.")
    mechanism = manifest["mechanism"]
    if mechanism not in ("chain_scission", "peroxide_oxidation"):
        raise MechanismTablesError("mechanism must be chain_scission or peroxide_oxidation.")
    states = _rows(folder, "states.csv", {"state", "role", "value", "units", "source"})
    kinetics = _rows(folder, "kinetics.csv", {"quantity", "value", "units", "source"})
    feeds = _rows(folder, "feeds.csv", {"state", "rate", "units", "source"}, optional=True)
    if len({r["state"] for r in states}) != len(states) or len({r["quantity"] for r in kinetics}) != len(kinetics):
        raise MechanismTablesError("State identifiers and kinetic quantity names must be unique.")
    initial = {r["state"]: {"value": _number(r["value"], "states.csv value"), "units": r["units"]} for r in states}
    for state in initial.values():
        assert_compatible(Q_(state["value"], state["units"]), "mole/liter", name="states.csv concentration")
    roles: dict[str, list[dict[str, str]]] = {}
    for row in states:
        roles.setdefault(row["role"], []).append(row)

    def role(name: str) -> str:
        if len(roles.get(name, [])) != 1:
            raise MechanismTablesError(f"states.csv: exactly one {name!r} role is required.")
        return roles[name][0]["state"]

    parameters = [
        {
            "name": r["quantity"],
            "symbol": r["quantity"],
            "value": _number(r["value"], "kinetics.csv value"),
            "units": r["units"],
            "uncertainty": None,
            "source": r["source"],
            "confidence_level": "user_supplied",
            "notes": "Explicit mechanism table input; uncertainty not supplied.",
        }
        for r in kinetics
    ]
    parameter_rows = {p["symbol"]: p for p in parameters}
    processes: list[dict[str, Any]] = []
    validators: list[dict[str, Any]] = []

    def require(names: set[str]) -> None:
        missing = names - set(parameter_rows)
        extra = set(parameter_rows) - names
        if missing or extra:
            raise MechanismTablesError(
                f"kinetics.csv: missing quantities {sorted(missing)}; unsupported quantities {sorted(extra)}."
            )

    def balance(identifier: str, weights: dict[str, float]) -> None:
        validators.append({"id": identifier, "validator_type": "mass_balance", "conserved_weights": weights})

    if mechanism == "chain_scission":
        require({"endo_kcat", "endo_km", "exo_kcat", "exo_km", "accessible_fraction"})
        if feeds:
            raise MechanismTablesError("feeds.csv: feeds are supported for peroxide_oxidation only.")
        if set(roles) != {"chain", "endo_enzyme", "exo_enzyme"}:
            raise MechanismTablesError("states.csv: chain scission roles must be chain, endo_enzyme and exo_enzyme.")
        for key in ("solid_min_length", "exo_fragment_length", "structure_source"):
            if key not in manifest or not str(manifest[key]).strip():
                raise MechanismTablesError(f"mechanism.yml: {key} is required.")
        threshold, fragment = manifest["solid_min_length"], manifest["exo_fragment_length"]
        if type(threshold) is not int or type(fragment) is not int or not 1 <= fragment < threshold:
            raise MechanismTablesError(
                "Structural lengths must be explicit integers with 1 <= fragment < solid_min_length."
            )
        chains = {}
        for row in roles["chain"]:
            try:
                length = int(row.get("chain_length", ""))
            except ValueError as exc:
                raise MechanismTablesError("states.csv: every chain requires an integer chain_length.") from exc
            if length in chains:
                raise MechanismTablesError("states.csv: chain_length values must be unique.")
            chains[length] = row["state"]
        if not chains or set(chains) != set(range(1, max(chains) + 1)) or max(chains) < threshold:
            raise MechanismTablesError("states.csv: supply all chain populations from 1 through a solid maximum.")
        for mode in ("endo", "exo"):
            enzyme = role(mode + "_enzyme")
            for i in sorted(chains):
                if i < threshold:
                    continue
                for j in range(1, i) if mode == "endo" else (fragment,):
                    processes.append(
                        {
                            "id": f"{mode}_{i}_{j}",
                            "process_type": f"chain_{mode}_scission",
                            "states": {"enzyme": enzyme, "chains": chains},
                            "parameters": {
                                "kcat": mode + "_kcat",
                                "km": mode + "_km",
                                "accessible_fraction": "accessible_fraction",
                            },
                            "chain_structure": {
                                "parent_length": i,
                                "fragment_length": j,
                                "solid_min_length": threshold,
                                "source": manifest["structure_source"],
                            },
                        }
                    )
        # Coefficients express monomers per chain and are structural identities.
        balance("material_equivalents", {n: float(i) for i, n in chains.items()})
    else:
        require(
            {
                "kcat",
                "peroxide_km",
                "substrate_km",
                "substrate_binding",
                "inactivation_constant",
                "peroxide_decay_rate",
                "product_yield",
            }
        )
        if set(roles) != {"substrate", "peroxide", "enzyme", "product", "inactive_enzyme"}:
            raise MechanismTablesError(
                "states.csv: peroxide roles must be substrate, peroxide, enzyme, product, inactive_enzyme."
            )
        s, h, e, p, inactive = (role(k) for k in ("substrate", "peroxide", "enzyme", "product", "inactive_enzyme"))
        if len(feeds) > 1 or any(row["state"] != h for row in feeds):
            raise MechanismTablesError("feeds.csv: at most one constant feed, naming the peroxide state, is supported.")
        ledger_names = {"mechanism_cuts", "mechanism_peroxide_decay", "mechanism_peroxide_feed"}
        if ledger_names.intersection(initial):
            raise MechanismTablesError("states.csv: mechanism_* ledger state names are reserved.")
        for name in ledger_names:
            initial[name] = {"value": 0.0, "units": initial[h]["units"]}
        product_yield = parameter_rows["product_yield"]
        assert_compatible(Q_(product_yield["value"], product_yield["units"]), "dimensionless", name="product_yield")
        processes.extend(
            [
                {
                    "id": "oxidative_cleavage",
                    "process_type": "peroxide_oxidative_cleavage",
                    "states": {"substrate": s, "peroxide": h, "enzyme": e, "product": p, "cuts": "mechanism_cuts"},
                    "parameters": {key: key for key in ("kcat", "peroxide_km", "substrate_km", "substrate_binding")},
                    "oxidative_yield": {key: product_yield[key] for key in ("value", "units", "source")},
                },
                {
                    "id": "peroxide_inactivation",
                    "process_type": "peroxide_inactivation",
                    "states": {"substrate": s, "peroxide": h, "enzyme": e, "inactive": inactive},
                    "parameters": {"inactivation_constant": "inactivation_constant", "substrate_km": "substrate_km"},
                },
                {
                    "id": "peroxide_decay",
                    "process_type": "first_order",
                    "states": {"source": h, "product": "mechanism_peroxide_decay"},
                    "parameters": {"rate_constant": "peroxide_decay_rate"},
                },
            ]
        )
        # A zero feed is still explicit; the cumulative feed pool must be part of the model.
        feed = (
            feeds[0]
            if feeds
            else {
                "rate": "0",
                "units": f"{initial[h]['units']}/second",
                "source": "Batch experiment: no feeds.csv supplied; zero feed is a bookkeeping boundary.",
            }
        )
        feed_units = f"{initial[h]['units']}/second"
        feed_value = float(
            assert_compatible(
                Q_(_number(feed["rate"], "feeds.csv rate"), feed["units"]),
                feed_units,
                name="feeds.csv concentration/time",
            ).magnitude
        )
        parameters.append(
            {
                "name": "peroxide_feed",
                "symbol": "peroxide_feed",
                "value": feed_value,
                "units": feed_units,
                "source": feed["source"],
                "confidence_level": "user_supplied",
                "uncertainty": None,
                "notes": "Explicit constant feed; no hidden generation.",
            }
        )
        processes.append(
            {
                "id": "peroxide_feed",
                "process_type": "mass_action",
                "states": {"reactants": {}, "products": {h: 1, "mechanism_peroxide_feed": 1}},
                "parameters": {
                    "rate_constant": "peroxide_feed",
                    "rate_constant_units": feed_units,
                    "rate_units": feed_units,
                },
            }
        )
        balance("material_equivalents", {s: 1, p: 1})
        balance("enzyme", {e: 1, inactive: 1})
        balance("peroxide", {h: 1, "mechanism_cuts": 1, "mechanism_peroxide_decay": 1, "mechanism_peroxide_feed": -1})
    validators.append({"id": "nonnegative", "validator_type": "non_negative", "species": list(initial)})
    digests = {
        name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
        for name in ("mechanism.yml", "states.csv", "kinetics.csv", "feeds.csv")
        if (folder / name).exists()
    }
    config = {
        "kind": "model_config",
        "name": manifest["name"],
        "mode": manifest["mode"],
        "maturity": manifest["maturity"],
        "provenance": {
            "source": manifest["source"],
            "confidence_level": "user_supplied",
            "measurement_method": "explicit mechanism tables",
            "units": "explicit per-state and per-parameter units",
            "validity_range": "supplied parameter conditions only; software_tested mechanism",
            "notes": "No calibration or validation is inferred. Initial state sources: "
            + "; ".join(r["state"] + ": " + r["source"] for r in states),
            "input_sha256": digests,
        },
        "entities": {},
        "parameters": [{"id": "user_mechanism_parameters", "parameters": parameters}],
        "processes": processes,
        "initial_state": {"states": initial},
        "time": manifest["time"],
        "validators": validators,
        "outputs": {
            "directory": "outputs/explicit_mechanism",
            "save": ["record", "validation_report"],
            "plots": ["state_trajectories"],
        },
    }
    if mechanism == "peroxide_oxidation":
        config["metric_definitions"] = {"peroxide_ledgers": {role("peroxide"): {
            "feed": "mechanism_peroxide_feed", "decay": "mechanism_peroxide_decay",
        }}}
    parsed = ModelConfig.from_mapping(config)
    require_runnable_config(parsed)
    inputs = ConfiguredInputLoader().load(parsed)
    model = ConfiguredProcessAssembler().assemble(parsed, inputs).model
    # Building the numeric kernels also validates constant domains before writing a runnable-looking file.
    from fungal_model.solvers import ProcessODESolver, RunRequest

    ProcessODESolver(model).compile(
        RunRequest(initial_state=inputs.initial_state, t_span=inputs.t_span, t_eval=inputs.t_eval)
    )
    return config


def write_mechanism_config(folder: str | Path, output: str | Path) -> Path:
    """Preflight the tables and save a standard configuration without overwriting."""
    config = assemble_mechanism_tables(folder)
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as stream:
        yaml.safe_dump(config, stream, sort_keys=False)
    return destination
