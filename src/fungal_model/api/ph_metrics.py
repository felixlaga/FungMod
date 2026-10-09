"""Bounded pH and signed ledger reductions from explicitly declared roles."""

from __future__ import annotations
from collections.abc import Mapping, Sequence
from typing import Any
import numpy as np
from scipy.special import expit
from fungal_model.core.units import Q_


def trajectory_metrics(
    rows: Sequence[Mapping[str, Any]], roles: Mapping[str, str], *, medium_rows: Sequence[Mapping[str, Any]] = ()
) -> list[dict[str, Any]]:
    if not rows or "ph" not in roles:
        return []
    ph = np.array([float(r[roles["ph"]]) for r in rows])
    time = np.array([float(r["time"]) for r in rows])
    time_units = str(rows[0]["time_units"])
    out = []

    def add(name, value, units, status="computed", notes=""):
        out.append(dict(metric_name=name, value=value, units=units, status=status, notes=notes))

    add("final_ph", float(ph[-1]), "dimensionless")
    if "ledger_titrant" in roles:
        name = roles["ledger_titrant"]
        add(
            "total_signed_titrant",
            float(rows[-1][name]) - float(rows[0][name]),
            str(rows[0][name + "_units"]),
            notes="Positive base demand for acid production; negative acid demand for alkalinisation.",
        )
    declared = {str(row["quantity"]): row for row in medium_rows if not row.get("buffer") and not row.get("process")}
    threshold = declared.get("ph_threshold")
    if threshold is None:
        add("time_to_stated_ph_threshold", "", time_units, "unknown", "No explicit pH threshold supplied.")
    else:
        target = float(Q_(threshold["value"], threshold["units"]).to("dimensionless").magnitude)
        crossing = None
        for i, value in enumerate(ph):
            if value == target:
                crossing = float(time[i])
                break
            if i and (ph[i - 1] - target) * (value - target) < 0:
                crossing = float(time[i - 1] + (time[i] - time[i - 1]) * (target - ph[i - 1]) / (value - ph[i - 1]))
                break
        add(
            "time_to_stated_ph_threshold",
            "" if crossing is None else crossing,
            time_units,
            "not_reached" if crossing is None else "computed",
            "Linear interpolation between saved samples; absolute run time.",
        )
    if "proton_excess" in roles and medium_rows:
        standard = float(
            Q_(declared["standard_concentration"]["value"], declared["standard_concentration"]["units"])
            .to("mol/L")
            .magnitude
        )
        kw = float(
            Q_(declared["water_ion_product"]["value"], declared["water_ion_product"]["units"])
            .to("(mol/L)**2")
            .magnitude
        )
        h = standard * np.power(10.0, -ph)
        acid = h - kw / h
        buffers = {str(row["buffer"]) for row in medium_rows if row.get("buffer")}
        for buffer in buffers:
            values = {str(row["quantity"]): row for row in medium_rows if row.get("buffer") == buffer}
            c = values["buffer_concentration"]
            pk = values["buffer_pka"]
            concentration = float(Q_(c["value"], c["units"]).to("mol/L").magnitude)
            pka = float(Q_(pk["value"], pk["units"]).to("dimensionless").magnitude)
            acid += concentration * expit(np.log(10.0) * (pka - ph))
        name = roles["proton_excess"]
        ledger = np.array([float(r[name]) for r in rows]) * float(Q_(1, rows[0][name + "_units"]).to("mol/L").magnitude)
        residual = acid - acid[0] - (ledger - ledger[0])
        add(
            "proton_balance_max_absolute_residual",
            float(np.max(np.abs(residual))),
            "mol/L",
            notes="Analytical integrated buffer acidity minus signed proton ledger at every saved time; no empirical validation.",
        )
    return out
