"""The De Ligne 2019 colony growth dataset: files, schema, flags, cross-panel agreement, provenance."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest
import yaml

from fungal_model.data import (
    load_dataset_candidate_review,
    load_experiment_dataset,
    validate_literature_dataset_metadata,
)

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "data" / "experiments" / "literature" / "de_ligne_2019_colony_growth"
INTAKE_DIR = ROOT / "data" / "experiments" / "source_intake" / "de_ligne_2019"
SCRIPT = ROOT / "scripts" / "digitize_de_ligne_2019_figures.py"

SPECIES = ("c_puteana", "r_solani")
QUANTITIES = ("area", "tips")
TEMPERATURES = (15, 20, 25, 30)
HUMIDITIES = (65, 70, 75, 80)
HOURS = set(range(1, 63))

SPEC = importlib.util.spec_from_file_location("digitize_de_ligne_2019_figures", SCRIPT)
assert SPEC and SPEC.loader
digitizer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = digitizer  # dataclasses resolve the module's annotations through sys.modules
SPEC.loader.exec_module(digitizer)


def _dataset_files() -> dict[str, list[str]]:
    files: dict[str, list[str]] = {}
    for species in SPECIES:
        for quantity in QUANTITIES:
            key = f"de_ligne_2019_{species}_{quantity}"
            files[key] = [
                f"{key}_{temperature}c_{humidity}rh.csv" for temperature in TEMPERATURES for humidity in HUMIDITIES
            ]
    return files


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _column(row: Mapping[str, str], prefix: str) -> str:
    matches = [name for name in row if name.startswith(prefix)]
    assert len(matches) == 1, (prefix, list(row))
    return matches[0]


def _value_column(row: Mapping[str, str]) -> str:
    return "mycelial_area_cm2" if "mycelial_area_cm2" in row else "tip_count"


def _sd_column(row: Mapping[str, str]) -> str:
    return "mycelial_area_sd_cm2" if "mycelial_area_sd_cm2" in row else "tip_count_sd"


def test_dataset_directory_holds_four_datasets_and_sixty_four_series() -> None:
    expected = set()
    for key, csvs in _dataset_files().items():
        expected.add(f"{key}.yml")
        expected.update(csvs)
    found = {path.name for path in DATASET_DIR.iterdir() if path.is_file()}
    assert found == expected


@pytest.mark.parametrize("key", sorted(_dataset_files()))
def test_each_dataset_passes_the_schema_and_loads_sixteen_conditions(key: str) -> None:
    path = DATASET_DIR / f"{key}.yml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    result = validate_literature_dataset_metadata(data)[0]
    assert result.passed, result.details["issues"]
    assert data["maturity"] == "literature_processed"
    assert data["source"]["license"] == "CC BY 4.0"
    assert data["validation"]["allow_missing_uncertainty"] is True
    assert "not independent replication" in data["source"]["notes"]
    assert data["digitization"]["included_points"] >= 980

    dataset = load_experiment_dataset(path)
    assert len(dataset.measurements) == 16
    conditions = set()
    for series in dataset.measurements:
        times = [point.time for point in series.points]
        assert len(series.points) >= 55
        assert all(time == int(time) and int(time) in HOURS for time in times)
        assert len(set(times)) == len(times)
        assert all(point.value >= 0.0 for point in series.points)
        assert all(point.uncertainty is None or point.uncertainty >= 0.0 for point in series.points)
        assert series.uncertainty_column is not None
        conditions.add(series.measurement_id)
    assert len(conditions) == 16


def test_every_row_is_flagged_where_a_standard_deviation_or_a_panel_is_missing() -> None:
    glossary = set(digitizer.FLAG_GLOSSARY)
    for key, csvs in _dataset_files().items():
        # Values are stored to three decimals (area) or one (tips); the stored mean
        # and difference were computed before rounding, so allow three half-units.
        rounding = 0.0015 if key.endswith("area") else 0.15
        for name in csvs:
            for row in _rows(DATASET_DIR / name):
                flags = set(filter(None, row["flags"].split(";")))
                assert flags <= glossary, (name, flags - glossary)
                if row[_sd_column(row)] == "":
                    assert flags & {"sd_below_marker_radius", "sd_unavailable"}, (name, row["time_h"])
                temperature_value = row[_column(row, "temperature_panel_value")]
                humidity_value = row[_column(row, "humidity_panel_value")]
                difference = row[_column(row, "panel_difference")]
                value = float(row[_value_column(row)])
                if temperature_value == "" or humidity_value == "":
                    assert "single_panel" in flags, (name, row["time_h"])
                    assert difference == ""
                    present = float(temperature_value or humidity_value)
                    assert abs(present - value) <= rounding
                else:
                    assert "single_panel" not in flags
                    assert difference != ""
                    assert abs(float(temperature_value) - float(humidity_value) - float(difference)) <= rounding
                    assert abs(0.5 * (float(temperature_value) + float(humidity_value)) - value) <= rounding


def test_panel_disagreements_are_rare_and_bounded() -> None:
    limits = {"area": 0.2, "tips": 150.0}
    for key, csvs in _dataset_files().items():
        quantity = "area" if key.endswith("area") else "tips"
        disagreements = 0
        largest = 0.0
        single = 0
        rows = 0
        for name in csvs:
            for row in _rows(DATASET_DIR / name):
                rows += 1
                flags = row["flags"].split(";")
                if "panel_disagreement" in flags:
                    disagreements += 1
                if "single_panel" in flags:
                    single += 1
                difference = row[_column(row, "panel_difference")]
                if difference:
                    largest = max(largest, abs(float(difference)))
        assert disagreements <= 8, (key, disagreements)
        assert largest <= limits[quantity], (key, largest)
        assert single <= 0.15 * rows, (key, single, rows)
        assert rows >= 980, (key, rows)


def test_the_panel_table_covers_every_condition_in_two_panels() -> None:
    rows = _rows(INTAKE_DIR / "digitized_panels.csv")
    assert len(rows) >= 7500
    seen: set[tuple[str, str, str, str]] = set()
    families: dict[tuple[str, str, str], set[str]] = {}
    for row in rows:
        marker = (row["figure"], row["panel_index"], row["series_colour"], row["time_h"])
        assert marker not in seen, marker
        seen.add(marker)
        families.setdefault((row["figure"], row["temperature_c"], row["relative_humidity_percent"]), set()).add(
            row["panel_family"]
        )
        assert int(row["time_h"]) in HOURS
        assert row["top_cap_visible"] in {"true", "false"} and row["bottom_cap_visible"] in {"true", "false"}
    assert len(families) == 4 * 16
    assert all(value == {"temperature", "humidity"} for value in families.values())


def _final(name: str) -> float:
    rows = [row for row in _rows(DATASET_DIR / name) if int(row["time_h"]) >= 58]
    return float(rows[-1][_value_column(rows[-1])])


def test_article_statements_hold_on_the_committed_values() -> None:
    """Prose statements of the article, independent of the figures, as in the extractor."""

    for species, allowed in digitizer.STATED_OPTIMA.items():
        for quantity in QUANTITIES:
            finals = {
                (temperature, humidity): _final(f"de_ligne_2019_{species}_{quantity}_{temperature}c_{humidity}rh.csv")
                for temperature in TEMPERATURES
                for humidity in HUMIDITIES
            }
            assert max(finals, key=lambda item: finals[item]) in allowed, (species, quantity)
    cold = _rows(DATASET_DIR / "de_ligne_2019_r_solani_area_15c_65rh.csv")
    mild = _rows(DATASET_DIR / "de_ligne_2019_r_solani_area_20c_65rh.csv")
    cold_final, mild_final = _final("de_ligne_2019_r_solani_area_15c_65rh.csv"), _final("de_ligne_2019_r_solani_area_20c_65rh.csv")
    assert abs(cold_final - mild_final) <= 0.05 * 0.5 * (cold_final + mild_final)
    half_cold = next(int(row["time_h"]) for row in cold if float(row["mycelial_area_cm2"]) >= 0.5 * cold_final)
    half_mild = next(int(row["time_h"]) for row in mild if float(row["mycelial_area_cm2"]) >= 0.5 * mild_final)
    assert half_mild < half_cold


def test_candidate_review_is_approved_with_the_schema_passed() -> None:
    review = load_dataset_candidate_review(
        ROOT / "data" / "experiments" / "candidate_reviews" / "de_ligne_2019_colony_growth_review.yml"
    )
    assert review.validate().passed
    assert review.status == "approved_for_ingestion"
    assert review.review["schema_result"] == "passed"
    assert "de_ligne_2019_colony_growth" in review.review["decision_notes"]


def test_manifest_lists_the_six_source_files_with_matching_digests() -> None:
    manifest = json.loads((ROOT / "data" / "experiments" / "source_intake" / "manifest.json").read_text(encoding="utf-8"))
    sources = [source for source in manifest["sources"] if source["id"] == "de_ligne_2019"]
    assert len(sources) == 1 and sources[0]["article_doi"] == "10.1186/s43008-019-0009-3"
    records = {record["path"]: record for record in manifest["files"] if record["path"].startswith("de_ligne_2019/")}
    assert set(records) == {f"de_ligne_2019/{name}" for name in digitizer.INTAKE_FILES}
    for path, record in records.items():
        content = (ROOT / "data" / "experiments" / "source_intake" / path).read_bytes()
        assert record["bytes"] == len(content)
        assert record["sha256"] == hashlib.sha256(content).hexdigest()
        assert record["sha256"] == digitizer.INTAKE_FILES[path.split("/", 1)[1]]
        assert record["license"] == "CC-BY-4.0"


def test_dataset_metadata_points_at_the_preserved_source_files() -> None:
    for key in _dataset_files():
        data = yaml.safe_load((DATASET_DIR / f"{key}.yml").read_text(encoding="utf-8"))
        file_name = data["supplementary_data"]["file_name"]
        assert file_name.startswith("data/experiments/source_intake/de_ligne_2019/")
        digest = data["supplementary_data"]["checksum"].removeprefix("sha256:")
        assert digest == hashlib.sha256((ROOT / file_name).read_bytes()).hexdigest()
        panels = data["digitization"]["axis_calibration"]["panels"]
        assert len(panels) == 8
        assert {panel["family"] for panel in panels} == {"temperature", "humidity"}
        assert set(data["digitization"]["flag_glossary"]) == set(digitizer.FLAG_GLOSSARY)


def test_documentation_records_the_dataset_and_its_limits() -> None:
    literature = (ROOT / "data" / "experiments" / "literature" / "README.md").read_text(encoding="utf-8")
    assert "de_ligne_2019_colony_growth/" in literature
    assert "scripts/digitize_de_ligne_2019_figures.py" in literature
    assert "not independent" in literature
    intake = (ROOT / "data" / "experiments" / "source_intake" / "README.md").read_text(encoding="utf-8")
    assert "De Ligne" in intake and "de_ligne_2019/digitized_panels.csv" in intake
    spatial = (ROOT / "docs" / "spatial-mycelium.md").read_text(encoding="utf-8")
    assert "de_ligne_2019_colony_growth" in spatial
    assert "observation operator" in spatial


def test_digitizer_reproduces_the_committed_files_from_the_preserved_pdfs() -> None:
    pytest.importorskip("pypdfium2", reason="requires pypdfium2 to decode the supplementary PDFs")
    pytest.importorskip("PIL", reason="requires Pillow to decode the embedded images")
    extraction = digitizer.run_extraction(INTAKE_DIR)
    problems = digitizer.check_extraction(extraction, DATASET_DIR, INTAKE_DIR)
    assert problems == []
    assert extraction.report["stated_optima"]["c_puteana"]["area"] == [20, 75]
