from __future__ import annotations

import csv
import socket
from pathlib import Path
from typing import Any

from fungal_model import virtual_experiment


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"


def test_case001_researcher_names_run_bio002_chain_and_standard_outputs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def blocked_connect(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("CASE-001 simulation must not call live external APIs.")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect)
    output_dir = tmp_path / "case001"

    study = virtual_experiment(
        fungi="generic cellulase source",
        substrates="cellulose film",
        environments="30 C pH 5 assay",
        registry=REGISTRY_INDEX,
    )

    assert study.fungus_ids == ("generic_cellulase_source",)
    assert study.substrate_ids == ("cellulose_film_generic",)
    assert study.environment_ids == ("sabiork_reaction_618_selected_conditions",)

    report = study.preflight(mode="exploratory")[0]
    assert report.status == "modelable"
    assert report.required_processes == ("extracellular_enzyme_chain",)
    assert "surface_catalysis" in report.candidate_processes
    assert "extracellular_enzyme_chain" in report.candidate_processes

    result = study.simulate(
        mode="exploratory",
        n_samples=1,
        seed=17,
        output_dir=output_dir,
        quicklook=False,
    )

    assert result.screen_result.case_results[0].process_type == "extracellular_enzyme_chain"
    for filename in (
        "time_series_long.csv",
        "final_metrics.csv",
        "threshold_times.csv",
        "summary_metrics.csv",
        "limitations_table.csv",
        "suggested_experiments.csv",
        "output_manifest.json",
        "virtual_experiment_summary.json",
    ):
        assert (output_dir / filename).exists(), filename

    time_rows = _csv_rows(output_dir / "time_series_long.csv")
    final_rows = _csv_rows(output_dir / "final_metrics.csv")
    threshold_rows = _csv_rows(output_dir / "threshold_times.csv")
    limitation_rows = _csv_rows(output_dir / "limitations_table.csv")
    suggestion_rows = _csv_rows(output_dir / "suggested_experiments.csv")
    sampled_rows = _csv_rows(output_dir / "sampled_parameters.csv")

    assert {
        "solid_cellulose_equivalent_concentration",
        "cellobiose_concentration",
        "beta_D_glucose_concentration",
        "cellulase_concentration",
        "beta_glucosidase_concentration",
        "substrate_degraded_fraction",
        "degradation_rate",
        "product_release_rate",
    } <= {row["state"] for row in time_rows}
    assert {"final_substrate_remaining", "final_product_concentration", "final_product_yield"} <= {
        row["metric"] for row in final_rows
    }
    assert {row["threshold_fraction"] for row in threshold_rows} == {"0.1", "0.5", "0.9"}
    assert {row["source_record_id"] for row in sampled_rows} >= {
        "bio002_initial_solid_cellulose_equivalent_concentration",
        "bio002_cellulose_to_cellobiose_surface_rate",
        "sabiork_reaction_618_Km_cellobiose",
        "sabiork_reaction_618_kcat_cellobiose",
    }

    limitations_text = " ".join(row["limitation"] for row in limitation_rows)
    assert "not whole-fungus growth, secretion, uptake, or biomass" in limitations_text
    assert "No PET, lignin, full lignocellulose" in limitations_text
    assert "experimental validation" in limitations_text
    assert {row["suggestion_id"] for row in suggestion_rows} == {
        "bio002_timecourse_cellobiose_glucose",
        "bio002_accessible_surface_area",
    }

    emitted_states_and_metrics = " ".join(
        [*(row["state"] for row in time_rows), *(row["metric"] for row in final_rows)]
    ).casefold()
    assert not any(
        unsupported in emitted_states_and_metrics
        for unsupported in ("fungal_biomass", "uptake_flux", "secretion_rate", "pet", "lignin")
    )


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
