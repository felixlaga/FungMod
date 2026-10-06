"""The paper's figures are generated from the recorded results and stay consistent with them."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from fungal_model.research import paper_figures
from fungal_model.research.gelain_culture import CultureBenchmarkError

ROOT = Path(__file__).resolve().parents[1]
FIGURES = ROOT / paper_figures.PAPER_FIGURES_DIR


def test_committed_figure_data_and_manifest_match_the_recorded_results() -> None:
    assert paper_figures.check_figures(ROOT) == []


def test_regenerating_the_figures_elsewhere_is_byte_identical_for_the_data(tmp_path: Path) -> None:
    manifest = paper_figures.write_figures(ROOT, tmp_path)
    for name, entry in manifest["figures"].items():
        assert (tmp_path / entry["data_file"]).read_bytes() == (FIGURES / entry["data_file"]).read_bytes(), name
        svg = (tmp_path / entry["file"]).read_text(encoding="utf-8")
        assert svg.startswith("<?xml") and paper_figures.GENERATOR in svg and "<dc:date>" not in svg, name
    assert (tmp_path / paper_figures.MANIFEST_NAME).read_bytes() == (FIGURES / paper_figures.MANIFEST_NAME).read_bytes()


def test_manifest_digests_name_the_files_on_disk() -> None:
    manifest = json.loads((FIGURES / paper_figures.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["generator"] == paper_figures.GENERATOR
    assert set(manifest["figures"]) == {builder(ROOT).name for builder in paper_figures.FIGURE_BUILDERS}
    for entry in manifest["figures"].values():
        assert entry["sources"], entry["file"]
        for source, digest in entry["sources"].items():
            assert hashlib.sha256((ROOT / source).read_bytes()).hexdigest() == digest, source


def test_every_figure_is_cited_by_the_paper() -> None:
    text = (ROOT / "paper" / "paper.md").read_text(encoding="utf-8")
    manifest = json.loads((FIGURES / paper_figures.MANIFEST_NAME).read_text(encoding="utf-8"))
    for entry in manifest["figures"].values():
        assert f"figures/{entry['file']}" in text, entry["file"]


def test_key_numbers_agree_with_the_plotted_data() -> None:
    figures = {figure.name: figure for figure in paper_figures.build_figures(ROOT)}
    holdouts = figures["figure_1_cellulose_holdouts"]
    assert holdouts.key_numbers["conditions"] == len(holdouts.data["conditions"]) == 3
    for entry in holdouts.data["conditions"]:
        for model in holdouts.data["models"]:
            assert holdouts.key_numbers["mean_normalized_mse_by_model"][model][entry["condition"]] == entry["predictions"][model]["normalized_mse"]
            assert len(entry["predictions"][model]["times_h"]) == len(entry["times_h"])
    predictive = figures["figure_2_posterior_predictive"]
    for entry in predictive.data["conditions"]:
        bands = entry["bands"]
        assert predictive.key_numbers["successful_draws"][entry["condition"]] == bands["successful_draws"]
        for observable in predictive.data["observables"]:
            quantiles = bands["quantiles"][observable]
            assert len(quantiles) == len(predictive.data["quantiles"]) == 3
            assert all(len(row) == len(bands["times_h"]) for row in quantiles)
            assert all(low <= mid <= high for low, mid, high in zip(*quantiles, strict=True))
    screen = figures["figure_3_criticism_screen"]
    for scenario, block in screen.data["scenarios"].items():
        for model_id, entry in block["models"].items():
            assert screen.key_numbers["passed"][scenario][model_id] == entry["passed"]
            assert screen.key_numbers["relative_improvement"][scenario][model_id] == entry["relative_improvement"]
    cross = figures["figure_4_cross_solver"]
    assert cross.key_numbers["starts"] == len(cross.data["start_objectives"]) == 10
    assert cross.key_numbers["copasi_best_objective"] <= min(cross.data["start_objectives"] + [cross.data["local_fit_objective"]]) + 1e-12


def test_figure_builders_refuse_missing_results(tmp_path: Path) -> None:
    with pytest.raises(CultureBenchmarkError, match="missing"):
        paper_figures.cross_solver_figure(tmp_path)
    with pytest.raises(CultureBenchmarkError, match="missing"):
        paper_figures.criticism_screen_figure(tmp_path)


def test_check_figures_reports_tampering(tmp_path: Path) -> None:
    paper_figures.write_figures(ROOT, tmp_path)
    assert paper_figures.check_figures(ROOT, tmp_path) == []
    data_file = tmp_path / "figure_4_cross_solver.json"
    data_file.write_text(data_file.read_text(encoding="utf-8").replace("3.97", "3.96", 1), encoding="utf-8")
    problems = paper_figures.check_figures(ROOT, tmp_path)
    assert any("figure_4_cross_solver.json differs" in problem for problem in problems)
    svg = tmp_path / "figure_3_criticism_screen.svg"
    svg.write_text(svg.read_text(encoding="utf-8").replace(paper_figures.GENERATOR, "edited by hand"), encoding="utf-8")
    assert any("generator marker" in problem for problem in paper_figures.check_figures(ROOT, tmp_path))
    shutil.rmtree(tmp_path / "figure_1_cellulose_holdouts.svg", ignore_errors=True)
    (tmp_path / "figure_1_cellulose_holdouts.svg").unlink()
    assert any("figure_1_cellulose_holdouts.svg is missing" in problem for problem in paper_figures.check_figures(ROOT, tmp_path))
    (tmp_path / paper_figures.MANIFEST_NAME).unlink()
    assert any("manifest.json is missing" in problem for problem in paper_figures.check_figures(ROOT, tmp_path))
