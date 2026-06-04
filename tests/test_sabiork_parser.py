from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from fungal_model.data.sabiork import (
    SabioRKParseError,
    curate_reaction_618_parameter_ranges,
    load_sabiork_kinlaw_export,
    select_reaction_618_candidate,
    write_sabiork_parameter_range_report,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "sabiork_reaction_618_selection_fixture.json"
REAL_001_RAW_EXPORT = (
    ROOT
    / "data"
    / "kinetic_records"
    / "sabiork"
    / "case_001_reaction_618_beta_glucosidase"
    / "raw"
    / "kinlaw_entries_reaction_618.json"
)


def test_valid_export_loads() -> None:
    export = load_sabiork_kinlaw_export(FIXTURE)

    assert export.meta["total_count"] == 5
    assert len(export.entries) == 5
    assert export.entries[0]["id"] == "unrelated_enzyme"


def test_missing_meta_or_data_fails(tmp_path: Path) -> None:
    missing_meta = tmp_path / "missing_meta.json"
    missing_meta.write_text(json.dumps({"data": []}), encoding="utf-8")
    missing_data = tmp_path / "missing_data.json"
    missing_data.write_text(json.dumps({"meta": {"total_count": 0}}), encoding="utf-8")

    with pytest.raises(SabioRKParseError, match="meta"):
        load_sabiork_kinlaw_export(missing_meta)
    with pytest.raises(SabioRKParseError, match="data"):
        load_sabiork_kinlaw_export(missing_data)


def test_selector_prefers_beta_glucosidase_over_unrelated_enzyme(tmp_path: Path) -> None:
    export = _export_with_ids(tmp_path, ("unrelated_enzyme", "selected_wildtype"))

    selection = select_reaction_618_candidate(export)

    assert selection.selected_entry_id == "selected_wildtype"
    assert selection.missing_required_fields == ()


def test_selector_prefers_ec_3_2_1_21(tmp_path: Path) -> None:
    export = _export_with_ids(tmp_path, ("wrong_ec", "selected_wildtype"))

    selection = select_reaction_618_candidate(export)

    assert selection.selected_entry_id == "selected_wildtype"


def test_selector_prefers_plain_michaelis_menten_over_ph_dependent(tmp_path: Path) -> None:
    export = _export_with_ids(tmp_path, ("ph_dependent", "selected_wildtype"))

    selection = select_reaction_618_candidate(export)

    assert selection.selected_entry_id == "selected_wildtype"


def test_selector_prefers_wildtype_over_mutant_when_otherwise_equal(tmp_path: Path) -> None:
    export = _export_with_ids(tmp_path, ("mutant_plain", "selected_wildtype"))

    selection = select_reaction_618_candidate(export)

    assert selection.selected_entry_id == "selected_wildtype"


def test_selector_records_missing_kcat_or_vmax(tmp_path: Path) -> None:
    payload = _fixture_payload()
    entry = deepcopy(_entry_by_id(payload, "selected_wildtype"))
    entry["id"] = "missing_kcat"
    entry["kineticlaw"]["parameter"] = [
        parameter
        for parameter in entry["kineticlaw"]["parameter"]
        if parameter["type"]["name"] != "kcat"
    ]
    payload["data"] = [entry]
    export = _write_export(tmp_path, payload)

    selection = select_reaction_618_candidate(export)

    assert selection.selected_entry_id == "missing_kcat"
    assert "kcat_or_clear_Vmax" in selection.missing_required_fields
    assert selection.warnings == (
        "Selected best available candidate has missing required fields; no values were invented.",
    )


def test_selection_report_is_json_safe(tmp_path: Path) -> None:
    export = _export_with_ids(tmp_path, ("unrelated_enzyme", "mutant_plain", "selected_wildtype"))

    selection = select_reaction_618_candidate(export)

    report = selection.to_report()
    assert report["selected_entry_id"] == "selected_wildtype"
    assert report["rejected_candidates"] == [
        {"entry_id": "unrelated_enzyme", "reason": "enzyme_name_not_beta_glucosidase"},
        {"entry_id": "mutant_plain", "reason": "lower_priority_enzyme_type"},
    ]
    json.dumps(report)


def test_saved_reaction_618_export_selects_reproducible_entry() -> None:
    export = load_sabiork_kinlaw_export(REAL_001_RAW_EXPORT)

    selection = select_reaction_618_candidate(export)

    assert selection.selected_entry_id == "35622"
    assert selection.missing_required_fields == ()
    assert selection.warnings == ()


def test_saved_reaction_618_export_curates_literature_km_kcat_ranges() -> None:
    export = load_sabiork_kinlaw_export(REAL_001_RAW_EXPORT)

    report = curate_reaction_618_parameter_ranges(export)

    assert report.included_entry_ids == (
        "35622",
        "38521",
        "38523",
        "38524",
        "38525",
        "38526",
        "38527",
        "39780",
        "39781",
        "39782",
        "39783",
        "39784",
        "44879",
        "44888",
        "60725",
    )
    km_range = report.ranges["Km_cellobiose"]
    kcat_range = report.ranges["kcat_cellobiose"]
    assert km_range.count == 15
    assert km_range.units == "mM"
    assert km_range.lower == pytest.approx(0.68)
    assert km_range.upper == pytest.approx(114.0)
    assert kcat_range.count == 15
    assert kcat_range.units == "s^(-1)"
    assert kcat_range.lower == pytest.approx(0.13)
    assert kcat_range.upper == pytest.approx(7.17)
    assert any(
        entry["entry_id"] == "38522"
        and entry["reason"] == "kinetic_law_not_plain_michaelis_menten"
        for entry in report.excluded_entries
    )
    assert any(
        entry["entry_id"] == "39470"
        and entry["reason"] == "ec_number_not_3_2_1_21"
        for entry in report.excluded_entries
    )


def test_parameter_range_report_write_is_json_safe(tmp_path: Path) -> None:
    export = load_sabiork_kinlaw_export(REAL_001_RAW_EXPORT)
    report = curate_reaction_618_parameter_ranges(export)

    path = write_sabiork_parameter_range_report(report, tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert path.name == "parameter_range_summary.json"
    assert payload["ranges"]["Km_cellobiose"]["lower"] == pytest.approx(0.68)
    assert payload["ranges"]["kcat_cellobiose"]["upper"] == pytest.approx(7.17)
    json.dumps(payload)


def _export_with_ids(tmp_path: Path, entry_ids: tuple[str, ...]):
    payload = _fixture_payload()
    payload["data"] = [_entry_by_id(payload, entry_id) for entry_id in entry_ids]
    payload["meta"]["total_count"] = len(entry_ids)
    return _write_export(tmp_path, payload)


def _write_export(tmp_path: Path, payload: dict[str, Any]):
    path = tmp_path / "export.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return load_sabiork_kinlaw_export(path)


def _fixture_payload() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _entry_by_id(payload: dict[str, Any], entry_id: str) -> dict[str, Any]:
    for entry in payload["data"]:
        if entry["id"] == entry_id:
            return deepcopy(entry)
    raise AssertionError(f"Missing fixture entry {entry_id}")
