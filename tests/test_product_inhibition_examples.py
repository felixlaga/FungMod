from __future__ import annotations

import csv
import json
import socket
from pathlib import Path
from typing import Any

from fungal_model import virtual_experiment
from fungal_model.examples import prepare_reversible_product_inhibition_example_registry


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"


def test_product_inhibition_example_registry_runs_through_public_api(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def blocked_connect(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("BIO-003 example simulation must not call live external APIs.")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect)
    inhibited_registry = prepare_reversible_product_inhibition_example_registry(
        tmp_path / "bio003_product_inhibition_registry",
        source_registry=REGISTRY_INDEX,
    )

    uninhibited = _run_example_study(
        registry=REGISTRY_INDEX,
        output_dir=tmp_path / "uninhibited",
        seed=31,
    )
    inhibited = _run_example_study(
        registry=inhibited_registry,
        output_dir=tmp_path / "inhibited",
        seed=31,
    )

    mechanism_rows = _csv_rows(tmp_path / "inhibited" / "mechanism_summary.csv")
    limitation_rows = _csv_rows(tmp_path / "inhibited" / "limitations_table.csv")
    metadata_path = next((tmp_path / "inhibited").glob("*/sample_0000/bundle/configured_metadata.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert not any(row["mechanism_id"] == "product_inhibition" for row in uninhibited.mechanism_summary())
    assert any(
        row["mechanism_kind"] == "rate_modifier"
        and row["mechanism_id"] == "product_inhibition"
        and row["equation_or_law"] == "rate_multiplier = 1 / (1 + product / K_i)"
        and row["parameters"] == "inhibition_constant:K_i_bio003_product_example"
        for row in mechanism_rows
    )
    assert metadata["configured_process_modifiers"] == [
        {
            "process_id": "bio002_cellobiose_to_glucose_mm",
            "modifier_index": 0,
            "type": "product_inhibition",
            "product_state": "beta_D_glucose_concentration",
            "inhibition_constant": "K_i_bio003_product_example",
            "maturity": "exploratory_configured_mechanism",
            "limitation": (
                "Single-product reversible inhibition only; configured only when product_state "
                "and positive unit-compatible K_i are explicit."
            ),
        }
    ]
    assert any("not validation data" in row["limitation"] for row in limitation_rows)

    uninhibited_product = _metric_value(uninhibited.final_metrics(), "final_product_concentration")
    inhibited_product = _metric_value(inhibited.final_metrics(), "final_product_concentration")
    assert inhibited_product < uninhibited_product


def _run_example_study(*, registry: str | Path, output_dir: Path, seed: int):
    study = virtual_experiment(
        fungi="generic cellulase source",
        substrates="cellulose film",
        environments="30 C pH 5 assay",
        registry=registry,
    )
    return study.simulate(mode="exploratory", n_samples=1, seed=seed, output_dir=output_dir, quicklook=False)


def _metric_value(rows: list[dict[str, str]], metric: str) -> float:
    for row in rows:
        if row["metric"] == metric and row["status"] == "computed":
            return float(row["value"])
    raise AssertionError(f"Missing computed metric {metric!r}")


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
