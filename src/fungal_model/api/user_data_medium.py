"""Evidence-bearing medium.csv input for configured buffered pH balances.

Every number is explicit. This adapter copies the input configuration and
binds buffers and process proton coefficients; it never guesses acid yields.
"""

from __future__ import annotations
from collections.abc import Mapping, Sequence
from copy import deepcopy
import csv
import math
from pathlib import Path
from typing import Any
from fungal_model.core.units import Q_, assert_compatible

MEDIUM_QUANTITIES = frozenset(
    {
        "buffer_concentration",
        "buffer_pka",
        "initial_ph",
        "minimum_ph",
        "maximum_ph",
        "water_ion_product",
        "standard_concentration",
        "temperature",
        "proton_coefficient",
        "ph_stat_setpoint",
        "ph_threshold",
    }
)


def read_medium_csv(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        return validate_medium_rows(list(csv.DictReader(stream)))


def validate_medium_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for index, raw in enumerate(rows, 2):
        row = dict(raw)
        quantity = str(row.get("quantity", ""))
        if quantity not in MEDIUM_QUANTITIES:
            raise ValueError(f"medium.csv:{index}:quantity: unsupported quantity {quantity!r}.")
        for field in ("units", "evidence_type", "source", "measurement_method", "notes"):
            if not str(row.get(field, "")).strip():
                raise ValueError(f"medium.csv:{index}:{field}: explicit evidence is required.")
        if row["evidence_type"] not in {"measured", "literature", "design", "estimate"}:
            raise ValueError(f"medium.csv:{index}:evidence_type: unsupported evidence type.")
        try:
            value = float(row["value"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"medium.csv:{index}:value: finite numeric value required.") from exc
        if not math.isfinite(value):
            raise ValueError(f"medium.csv:{index}:value: finite value required.")
        Q_(value, str(row["units"]))
        buffer = str(row.get("buffer", "")).strip()
        process = str(row.get("process", "")).strip()
        if (quantity.startswith("buffer_")) != bool(buffer):
            raise ValueError(f"medium.csv:{index}:buffer: only buffer quantities require a buffer id.")
        if (quantity == "proton_coefficient") != bool(process):
            raise ValueError(f"medium.csv:{index}:process: only proton coefficients require a driver id.")
        key = (quantity, buffer, process)
        if key in seen:
            raise ValueError(f"medium.csv:{index}:quantity: duplicate medium quantity.")
        seen.add(key)
        row.update(value=value, buffer=buffer, process=process)
        result.append(row)
    if not result:
        raise ValueError("medium.csv must contain evidence-bearing rows.")
    by_key = {(r["quantity"], r["buffer"], r["process"]): r for r in result}
    required = {"initial_ph", "minimum_ph", "maximum_ph", "water_ion_product", "standard_concentration", "temperature"}
    missing = sorted(q for q in required if (q, "", "") not in by_key)
    if missing:
        raise ValueError(f"medium.csv missing quantities: {missing}.")
    buffers = {r["buffer"] for r in result if r["buffer"]}
    if not buffers or any((q, b, "") not in by_key for b in buffers for q in ("buffer_concentration", "buffer_pka")):
        raise ValueError("Each medium buffer requires both concentration and pKa.")
    if not any(r["quantity"] == "proton_coefficient" for r in result):
        raise ValueError("medium.csv requires at least one explicit process proton coefficient.")
    unit_by_quantity = {
        "buffer_concentration": "mol/L",
        "water_ion_product": "(mol/L)**2",
        "standard_concentration": "mol/L",
        "temperature": "kelvin",
    }
    for row in result:
        q = row["quantity"]
        if q != "proton_coefficient":
            unit = unit_by_quantity.get(q, "dimensionless")
            numeric = float(assert_compatible(Q_(row["value"], row["units"]), unit, name=q).magnitude)
            if (
                q in {"buffer_concentration", "water_ion_product", "standard_concentration", "temperature"}
                and numeric <= 0
            ):
                raise ValueError(f"medium.csv:{q}: positive value required.")
        if q == "ph_stat_setpoint" and not str(row.get("titrant", "")).strip():
            raise ValueError("pH-stat requires an explicit titrant identity.")
    return result


def augment_config_with_medium(mapping: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Return a complete configured model with explicit pH and signed ledgers."""
    rows = validate_medium_rows(rows)
    config = deepcopy(dict(mapping))
    by_key = {(str(r["quantity"]), str(r.get("buffer", "")), str(r.get("process", ""))): r for r in rows}
    required = ("initial_ph", "minimum_ph", "maximum_ph", "water_ion_product", "standard_concentration", "temperature")
    missing = [key for key in required if (key, "", "") not in by_key]
    if missing:
        raise ValueError(f"medium.csv missing quantities: {missing}.")

    def scalar(key: str, units: str) -> float:
        row = by_key[(key, "", "")]
        return float(assert_compatible(Q_(row["value"], str(row["units"])), units, name=key).magnitude)

    initial = scalar("initial_ph", "dimensionless")
    bounds = (scalar("minimum_ph", "dimensionless"), scalar("maximum_ph", "dimensionless"))
    if not 0 <= bounds[0] <= initial <= bounds[1] <= 14 or bounds[0] == bounds[1]:
        raise ValueError("medium.csv requires initial pH inside ordered bounds within 0 to 14.")
    buffers = sorted({str(row["buffer"]) for row in rows if row["buffer"]})
    if not buffers or any(
        (key, b, "") not in by_key for b in buffers for key in ("buffer_concentration", "buffer_pka")
    ):
        raise ValueError("Each medium buffer requires both concentration and pKa.")
    stat = ("ph_stat_setpoint", "", "") in by_key
    if stat and (
        scalar("ph_stat_setpoint", "dimensionless") != initial
        or not str(by_key[("ph_stat_setpoint", "", "")].get("titrant", "")).strip()
    ):
        raise ValueError("pH-stat requires setpoint equal to initial pH and an explicit titrant identity.")
    processes = {str(p["id"]): p for p in config["processes"]}
    coefficients = [row for row in rows if row["quantity"] == "proton_coefficient"]
    if not coefficients or any(row["process"] not in processes for row in coefficients):
        raise ValueError("Proton coefficients must reference existing process ids.")
    initial_states = config["initial_state"].get("states", config["initial_state"])
    if "ph" in initial_states or "proton_ledger" in initial_states or "titrant_ledger" in initial_states:
        raise ValueError("Medium state ids conflict with existing initial states.")
    initial_states["ph"] = {
        "value": initial,
        "units": "dimensionless",
        "domain": "signed",
        "lower_bound": bounds[0],
        "upper_bound": bounds[1],
    }
    ledger = "titrant_ledger" if stat else "proton_ledger"
    initial_states[ledger] = {"value": 0.0, "units": "mol/L", "domain": "signed"}
    # Zero ledger is the definition of accumulation since start, not a biological constant.
    parameters = []
    symbols = {}
    existing = {p["symbol"] for group in config["parameters"] for p in group.get("parameters", [])}
    for index, row in enumerate(rows):
        symbol = f"medium_{index}"
        if symbol in existing:
            raise ValueError("Medium parameter ids conflict with existing parameters.")
        symbols[(row["quantity"], row["buffer"], row["process"])] = symbol
        parameters.append(
            {
                "name": row["quantity"],
                "symbol": symbol,
                "value": row["value"],
                "units": row["units"],
                "uncertainty": None,
                "source": row["source"],
                "confidence_level": "low" if row["evidence_type"] in {"estimate", "design"} else "medium",
                "measurement_method": row["measurement_method"],
                "validity_range": "Only the supplied medium, initial pH and bounds, temperature and driver; "
                + row["notes"],
                "notes": row["notes"] + f"; evidence_type={row['evidence_type']}",
            }
        )
    config["parameters"].append({"id": "medium_parameters", "parameters": parameters})
    # Static pH becomes solely the initial value; environment cannot be a second authority.
    env = config["entities"].get("environment")
    if env:
        if "data" not in env:
            raise ValueError(
                "Medium composition requires an inline environment so static pH can be explicitly removed."
            )
        conditions = env["data"].get("conditions", {})
        static_ph = conditions.get("ph")
        if (
            static_ph is not None
            and float(Q_(static_ph["value"], static_ph["units"]).to("dimensionless").magnitude) != initial
        ):
            raise ValueError("Medium initial pH must agree with conditions.csv / environment initial pH.")
        temperature = conditions.get("temperature")
        if temperature is not None and not math.isclose(
            float(Q_(temperature["value"], temperature["units"]).to("kelvin").magnitude),
            scalar("temperature", "kelvin"),
            rel_tol=1e-12,
        ):
            raise ValueError("Buffer pKa temperature must match the configured environment temperature.")
        env["data"].get("conditions", {}).pop("ph", None)
        env["data"].pop("ph", None)
        env["data"].pop("pH", None)
    for process in config["processes"]:
        if process["process_type"] == "ph_ionization_michaelis_menten":
            process["states"]["ph"] = "ph"
        for modifier in process.get("modifiers", []):
            if modifier.get("type", modifier.get("modifier_type")) in {"ph_gaussian", "ph_cardinal_rosso"}:
                modifier["state_source"] = "ph"
    for row in coefficients:
        driver = processes[row["process"]]
        common = {
            "buffers": [
                {"concentration": symbols[("buffer_concentration", b, "")], "pka": symbols[("buffer_pka", b, "")]}
                for b in buffers
            ],
            "proton_coefficient": symbols[("proton_coefficient", "", row["process"])],
            "water_ion_product": symbols[("water_ion_product", "", "")],
            "standard_concentration": symbols[("standard_concentration", "", "")],
            "temperature": symbols[("temperature", "", "")],
        }
        options = {
            "concentration_units": "mol/L",
            "time_units": config["time"]["start"]["units"],
            "ph_bounds": list(bounds),
            "source": "doi:10.1021/ed074p937; proton coefficient: " + str(row["source"]),
        }
        for mode, output in (("held_ph" if stat else "ph", "ph"), ("titrant" if stat else "proton_ledger", ledger)):
            config["processes"].append(
                {
                    "id": f"medium_{mode}_{row['process']}",
                    "process_type": "proton_balance_ph",
                    "states": {"ph": "ph", "output": output},
                    "parameters": dict(common),
                    "balance": dict(options, mode=mode),
                    "driver": deepcopy(driver),
                }
            )
    if "case_template" in config:
        roles = config["case_template"].setdefault("output_state_roles", {})
        roles["ph"] = "ph"
        roles["ledger_titrant" if stat else "proton_excess"] = ledger
    config.setdefault("provenance", {})["medium"] = {
        "maturity": "software_tested",
        "validated": False,
        "rows": rows,
        "limitations": [
            "Fixed volume and temperature; independent ideal monoprotic buffers; no full speciation.",
            "Proton production comes exclusively from explicit driver coefficients.",
        ],
    }
    if any(row["evidence_type"] == "estimate" for row in rows) and config["mode"] == "scientific":
        raise ValueError("Estimated medium inputs require explicit exploratory mode.")
    return config
