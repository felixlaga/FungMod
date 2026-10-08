"""Quick-look figures of cases with several processes: networks, cultures and chains (PLOTS-001).

A case whose ``time_series_long.csv`` holds the rates of more than one process
gets ``<case_id>_state_trajectories.png`` (one panel per simulated state, in its
own units, the substrate panel marked with the degradation-threshold times) and
``<case_id>_process_rates.png`` (one panel per process rate, in its own units,
named with the enzyme class, pool and modifiers ``mechanism_summary.csv``
records). Cases with one process keep exactly the five run-level figures.

The figures are checked through what matplotlib is asked to draw (titles, axis
labels, legend entries, lines, bands), captured at ``savefig``, never through
pixels. The user-data fixtures are illustrative estimates; the hand-written
tables at the end are artificial plotting inputs only.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from fungal_model import virtual_experiment
from fungal_model.api.quicklook import write_quicklook_plots


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"
FIXTURES = ROOT / "tests" / "fixtures" / "user_data"

RUN_LEVEL_FIGURES = (
    "substrate_remaining_vs_time.png",
    "product_release_vs_time.png",
    "degradation_fraction_vs_time.png",
    "degradation_rate_vs_time.png",
    "trajectory_quantile_bands.png",
)
CASE_FIGURES = ("case_0000_state_trajectories.png", "case_0000_process_rates.png")

# (fixture, fungus, substrate, condition) of the user-data cases with several processes.
NETWORK_CASES = {
    "network_chain": ("strain_n1", "polymer_p1", "c30_ph5"),
    "network_parallel": ("strain_q2", "ester_s2", "c25_ph7"),
    "network_solid_chain": ("strain_s3", "solid_c3", "c45_ph5"),
    "network_solid_parallel": ("strain_r4", "solid_k4", "c37_ph6"),
}
CULTURE_CASES = {
    "culture_estimates": ("strain_x1", "xylan_lot_x1", "c25"),
}


def _simulate(output_dir: Path, fixture: str, case: tuple[str, str, str], *, n_samples: int) -> Any:
    fungus, substrate, condition = case
    study = virtual_experiment(
        fungi=[fungus],
        substrates=[substrate],
        environments=[condition],
        registry=REGISTRY_INDEX,
        user_data=FIXTURES / fixture,
    )
    return study.simulate(mode="exploratory", n_samples=n_samples, seed=1, output_dir=output_dir)


@pytest.fixture(scope="module")
def runs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Each fixture simulated once with quick-look figures (two samples, one for the solid chain)."""

    results: dict[str, Any] = {}
    for fixture, case in {**NETWORK_CASES, **CULTURE_CASES}.items():
        samples = 1 if fixture == "network_solid_chain" else 2
        results[fixture] = _simulate(tmp_path_factory.mktemp(fixture), fixture, case, n_samples=samples)
    results["esterase_case"] = _simulate(
        tmp_path_factory.mktemp("esterase_case"),
        "esterase_case",
        ("strain_e1", "p_nitrophenyl_butyrate", "c37_ph7_5"),
        n_samples=2,
    )
    return results


@pytest.fixture()
def capture(monkeypatch: pytest.MonkeyPatch) -> dict[str, dict[str, Any]]:
    """What every figure saved during the test draws, keyed by file name."""

    import matplotlib.figure

    captured: dict[str, dict[str, Any]] = {}
    original = matplotlib.figure.Figure.savefig

    def recording(self: Any, fname: Any, *args: Any, **kwargs: Any) -> Any:
        captured[Path(fname).name] = _describe(self)
        return original(self, fname, *args, **kwargs)

    monkeypatch.setattr(matplotlib.figure.Figure, "savefig", recording)
    return captured


def _describe(figure: Any) -> dict[str, Any]:
    suptitle = figure.get_suptitle()
    axes = []
    for axis in figure.axes:
        legend = axis.get_legend()
        axes.append(
            {
                "title": axis.get_title(),
                "xlabel": axis.get_xlabel(),
                "ylabel": axis.get_ylabel(),
                "legend": [text.get_text() for text in legend.get_texts()] if legend is not None else [],
                "line_labels": [line.get_label() for line in axis.get_lines()],
                "lines": len(axis.get_lines()),
                "bands": len(axis.collections),
            }
        )
    # Figure-level texts other than the title (the footnote); the line breaks of the wrapping are removed.
    texts = [text.get_text().replace("\n", " ") for text in figure.texts if text.get_text() != suptitle]
    return {"suptitle": suptitle.replace("\n", " "), "texts": texts, "axes": axes}


def _replot(result: Any, destination: Path) -> tuple[str, ...]:
    paths = write_quicklook_plots(table_dir=result.output_directory, output_dir=destination)
    return tuple(path.name for path in paths)


def _rows(result: Any, name: str) -> list[dict[str, str]]:
    with (Path(result.output_directory) / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _state_units(result: Any, *, source: str) -> dict[str, set[str]]:
    units: dict[str, set[str]] = {}
    for row in _rows(result, "time_series_long.csv"):
        if row["source"] == source:
            units.setdefault(row["state"], set()).add(row["units"])
    return units


def _json(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _panel_state(title: str) -> str:
    return title.split("\n")[0].split(" (")[0]


def _threshold_summaries(result: Any) -> dict[str, dict[str, str]]:
    return {
        row["metric"]: row
        for row in _rows(result, "summary_metrics.csv")
        if row["metric"].startswith("time_to_") and row["case_id"] == "case_0000"
    }


# ---------------------------------------------------------------------------
# Cases with several processes


@pytest.mark.parametrize("fixture", [*NETWORK_CASES, *CULTURE_CASES])
def test_cases_with_several_processes_get_one_state_and_one_process_figure(
    runs: dict[str, Any], fixture: str, tmp_path: Path, capture: dict[str, dict[str, Any]]
) -> None:
    result = runs[fixture]
    output = Path(result.output_directory)
    assert tuple(Path(path).name for path in result.quicklook_paths) == (*RUN_LEVEL_FIGURES, *CASE_FIGURES)
    manifest = json.loads((output / "output_manifest.json").read_text(encoding="utf-8"))
    assert [Path(path).name for path in manifest["quicklook_paths"]] == [*RUN_LEVEL_FIGURES, *CASE_FIGURES]
    for name in CASE_FIGURES:
        assert (output / "figures" / name).is_file()
        assert f"figures/{name}" in manifest["files"]

    assert _replot(result, tmp_path / "replot") == (*RUN_LEVEL_FIGURES, *CASE_FIGURES)
    states = capture["case_0000_state_trajectories.png"]
    processes = capture["case_0000_process_rates.png"]
    first = _rows(result, "time_series_long.csv")[0]
    for figure in (states, processes):
        assert figure["suptitle"].startswith("case_0000: ")
        assert f"{first['fungus_id']} on {first['substrate_id']}" in figure["suptitle"]
        assert f"({first['process_type']})" in figure["suptitle"]
        assert all(axis["xlabel"] == f"time ({first['time_units']})" for axis in figure["axes"])

    # One panel per simulated state, each labelled with that state's one units text: two units never share an axis.
    state_units = _state_units(result, source="simulation_state")
    assert sorted(_panel_state(axis["title"]) for axis in states["axes"]) == sorted(state_units)
    for axis in states["axes"]:
        (units,) = state_units[_panel_state(axis["title"])]
        assert axis["ylabel"] == f"value ({units})"
    # Entry substrate first, then the intermediates in their order, then the final product.
    roles = [axis["title"].split(" (")[-1].rstrip(")") for axis in states["axes"]]
    assert roles[0] == "substrate"
    pool_roles = [role for role in roles if role == "substrate" or role.startswith("intermediate") or role == "product"]
    assert roles[: len(pool_roles)] == pool_roles

    # One panel per process rate, in its own rate units.
    rate_units = _state_units(result, source="simulation_process_rate")
    assert [f"process_rate.{_panel_state(axis['title'])}" for axis in processes["axes"]] == list(rate_units)
    for axis in processes["axes"]:
        (units,) = rate_units[f"process_rate.{_panel_state(axis['title'])}"]
        assert axis["ylabel"] == f"rate ({units})"

    # The ensemble band of two samples on every panel, read from trajectory_quantiles.csv.
    samples = len({row["sample_id"] for row in _rows(result, "time_series_long.csv")})
    for axis in (*states["axes"], *processes["axes"]):
        if samples > 1:
            assert axis["bands"] >= 1 and f"p05-p95 of {samples} samples" in axis["legend"]
        else:
            assert axis["bands"] == 0 and axis["line_labels"][0] == "sample_0000"
    assert any("not validation" in text for text in states["texts"]) == (samples > 1)


@pytest.mark.parametrize("fixture", list(NETWORK_CASES))
def test_network_process_panels_name_their_enzyme_class_pool_and_modifiers(
    runs: dict[str, Any], fixture: str, tmp_path: Path, capture: dict[str, dict[str, Any]]
) -> None:
    result = runs[fixture]
    _replot(result, tmp_path / "replot")
    titles = {_panel_state(axis["title"]): axis["title"] for axis in capture["case_0000_process_rates.png"]["axes"]}
    mechanism_rows = _rows(result, "mechanism_summary.csv")
    processes = [
        row
        for row in mechanism_rows
        if row["mechanism_kind"] == "process_law" and _json(row["provenance"]).get("enzyme_class")
    ]
    assert processes and sorted(titles) == sorted(row["mechanism_id"] for row in processes)
    for row in processes:
        pool = dict(item.split(":", 1) for item in row["state_variables"].split(";"))["substrate"]
        lines = titles[row["mechanism_id"]].split("\n")
        assert lines[1] == f"enzyme class {row['configured_by']} on pool {pool}"
        modifiers = [
            modifier
            for modifier in mechanism_rows
            if modifier["mechanism_kind"] == "rate_modifier" and modifier["configured_by"] == row["mechanism_id"]
        ]
        assert len(lines) == 2 + len(modifiers)
        for modifier, line in zip(modifiers, lines[2:], strict=True):
            assert line.startswith(f"modifier {modifier['mechanism_id']} (")


def test_cross_basis_network_draws_each_pool_and_rate_in_its_own_units(
    runs: dict[str, Any], tmp_path: Path, capture: dict[str, dict[str, Any]]
) -> None:
    result = runs["network_solid_chain"]
    _replot(result, tmp_path / "replot")
    states = capture["case_0000_state_trajectories.png"]
    assert [(axis["title"], axis["ylabel"]) for axis in states["axes"]] == [
        ("solid_c3_concentration (substrate)", "value (gram / liter)"),
        ("dimer_d3_concentration (intermediate_1)", "value (millimole / liter)"),
        ("monomer_m3_concentration (product)", "value (millimole / liter)"),
        ("solid_cutter_like_concentration (enzyme_solid_cutter_like)", "value (milligram / liter)"),
        ("dimer_hydrolase_like_concentration (enzyme_dimer_hydrolase_like)", "value (millimolar)"),
    ]
    processes = capture["case_0000_process_rates.png"]
    assert [(axis["title"], axis["ylabel"]) for axis in processes["axes"]] == [
        (
            "network_solid_chain__solid_cutter_like__solid_c3__homogeneous_mm\n"
            "enzyme class network_solid_chain__solid_cutter_like on pool solid_c3_concentration",
            "rate (gram / hour / liter)",
        ),
        (
            "network_solid_chain__dimer_hydrolase_like__dimer_d3__homogeneous_mm\n"
            "enzyme class network_solid_chain__dimer_hydrolase_like on pool dimer_d3_concentration\n"
            "modifier competitive_inhibition (competitive_inhibitor: monomer_m3_concentration)",
            "rate (millimole / hour / liter)",
        ),
    ]
    # One sample: its own line, no band; the thresholds of the entry substrate as threshold_times.csv gives them.
    substrate = states["axes"][0]
    summaries = _threshold_summaries(result)
    assert substrate["line_labels"][0] == "sample_0000" and substrate["bands"] == 0
    assert substrate["legend"] == [
        "sample_0000",
        *(
            f"{percent} % degraded at {float(summaries[f'time_to_{percent}_percent_substrate_degradation']['p50']):.4g} hour"
            for percent in (10, 50, 90)
        ),
    ]
    assert all(not axis["legend"][1:] for axis in states["axes"][1:])
    assert "One simulated sample, no ensemble band." in states["texts"][0]


def test_threshold_markers_sit_on_the_entry_substrate_at_the_summarised_times(
    runs: dict[str, Any], tmp_path: Path, capture: dict[str, dict[str, Any]]
) -> None:
    result = runs["network_chain"]
    _replot(result, tmp_path / "replot")
    axes = capture["case_0000_state_trajectories.png"]["axes"]
    summaries = _threshold_summaries(result)
    expected = [
        f"{percent} % degraded: p50 {float(summaries[metric]['p50']):.4g} minute; reached in 2 of 2 samples"
        for percent in (10, 50, 90)
        for metric in (f"time_to_{percent}_percent_substrate_degradation",)
    ]
    assert axes[0]["title"] == "polymer_p1_concentration (substrate)"
    assert axes[0]["legend"] == ["p05-p95 of 2 samples", "p50", *expected]
    # Band, median and three vertical threshold lines on the substrate panel only.
    assert axes[0]["lines"] == 1 + 3
    assert all(axis["lines"] == 1 for axis in axes[1:])


def test_culture_draws_biomass_every_pool_and_both_ledgers(
    runs: dict[str, Any], tmp_path: Path, capture: dict[str, dict[str, Any]]
) -> None:
    result = runs["culture_estimates"]
    _replot(result, tmp_path / "replot")
    states = capture["case_0000_state_trajectories.png"]
    panels = {axis["title"]: axis["ylabel"] for axis in states["axes"]}
    assert panels == {
        "xylan_lot_x1_concentration (substrate)": "value (gram / liter)",
        "endo_xylanase_like_concentration (enzyme)": "value (milligram / liter)",
        "biomass_dry_mass_concentration (biomass)": "value (gram / liter)",
        "consumed_xylan_lot_x1_not_retained_as_biomass (ledger_unassimilated_substrate)": "value (gram / liter)",
        "biomass_dry_mass_lost (ledger_biomass_loss)": "value (gram / liter)",
    }
    assert states["axes"][0]["title"] == "xylan_lot_x1_concentration (substrate)"
    processes = {axis["title"]: axis["ylabel"] for axis in capture["case_0000_process_rates.png"]["axes"]}
    # Each process rate in the units the bundle records, including a different time base: never converted.
    assert processes == {
        "substrate_consumption": "rate (gram / hour / liter)",
        "biomass_loss": "rate (gram / liter / second)",
        "enzyme_synthesis__endo_xylanase_like": "rate (milligram / hour / liter)",
        "enzyme_loss__endo_xylanase_like": "rate (milligram / liter / second)",
    }


def test_report_lists_the_case_figures(runs: dict[str, Any], tmp_path: Path) -> None:
    result = runs["network_parallel"]
    report = Path(result.write_report(tmp_path / "report", include_html=True, include_index=True))
    markdown = report.read_text(encoding="utf-8")
    index = (report.parent / "index.html").read_text(encoding="utf-8")
    for name in CASE_FIGURES:
        assert f"figures/{name}`" in markdown.replace("\\", "/")
        assert f"figures/{name}\"" in index


def test_case_figures_are_deterministic(runs: dict[str, Any], tmp_path: Path) -> None:
    result = runs["network_solid_parallel"]
    first = _replot(result, tmp_path / "first")
    second = _replot(result, tmp_path / "second")
    assert first == second == (*RUN_LEVEL_FIGURES, *CASE_FIGURES)
    for name in first:
        assert (tmp_path / "first" / name).read_bytes() == (tmp_path / "second" / name).read_bytes(), name


# ---------------------------------------------------------------------------
# Cases with one process keep the run-level figures exactly


def test_single_class_case_keeps_the_five_run_level_figures(
    runs: dict[str, Any], tmp_path: Path, capture: dict[str, dict[str, Any]]
) -> None:
    result = runs["esterase_case"]
    assert tuple(Path(path).name for path in result.quicklook_paths) == RUN_LEVEL_FIGURES
    assert sorted(path.name for path in (Path(result.output_directory) / "figures").iterdir()) == sorted(
        RUN_LEVEL_FIGURES
    )
    assert _replot(result, tmp_path / "replot") == RUN_LEVEL_FIGURES
    assert set(capture) == set(RUN_LEVEL_FIGURES)
    single = {
        "substrate_remaining_vs_time.png": "substrate remaining (micromolar)",
        "product_release_vs_time.png": "product formed (micromolar)",
        "degradation_fraction_vs_time.png": "substrate degraded fraction (dimensionless)",
        "degradation_rate_vs_time.png": "degradation rate (micromolar / minute)",
    }
    for name, ylabel in single.items():
        assert capture[name]["suptitle"] == "" and capture[name]["texts"] == []
        assert [(axis["title"], axis["xlabel"], axis["ylabel"]) for axis in capture[name]["axes"]] == [
            ("", "time", ylabel)
        ]
        assert capture[name]["axes"][0]["legend"] == ["sample_0000", "sample_0001"]
    bands = capture["trajectory_quantile_bands.png"]
    assert [(axis["title"], axis["xlabel"], axis["ylabel"]) for axis in bands["axes"]] == [
        ("case_0000: p_nitrophenyl_butyrate_concentration (substrate)", "time (minute)", "value (micromolar)"),
        ("case_0000: product_formed (derived_product_release)", "time (minute)", "value (micromolar)"),
        ("case_0000: substrate_degraded_fraction (derived_substrate_loss)", "time (minute)", "value (dimensionless)"),
    ]


def test_single_class_figures_are_byte_identical_when_replotted(runs: dict[str, Any], tmp_path: Path) -> None:
    result = runs["esterase_case"]
    _replot(result, tmp_path / "replot")
    for name in RUN_LEVEL_FIGURES:
        written = Path(result.output_directory) / "figures" / name
        assert written.read_bytes() == (tmp_path / "replot" / name).read_bytes(), name


def test_registry_grid_in_two_units_separates_them_and_draws_case_figures_for_the_chain_only(
    tmp_path: Path, capture: dict[str, dict[str, Any]]
) -> None:
    """The surface case (one process, kilogram) and the enzyme chain (two processes, millimolar) in one run."""

    study = virtual_experiment(
        fungi="generic_cellulase_source",
        substrates="cellulose_film_generic",
        environments=["bio001_cellulose_surface_pilot_environment", "sabiork_reaction_618_selected_conditions"],
        registry=REGISTRY_INDEX,
    )
    result = study.simulate(mode="exploratory", n_samples=1, seed=3, output_dir=tmp_path / "grid")
    process_types = {row["case_id"]: row["process_type"] for row in _rows(result, "case_summary.csv")}
    assert process_types == {"case_0000": "surface_catalysis", "case_0001": "extracellular_enzyme_chain"}
    assert tuple(Path(path).name for path in result.quicklook_paths) == (
        *RUN_LEVEL_FIGURES,
        "case_0001_state_trajectories.png",
        "case_0001_process_rates.png",
    )
    substrate = capture["substrate_remaining_vs_time.png"]["axes"]
    assert [(axis["title"], axis["xlabel"], axis["ylabel"]) for axis in substrate] == [
        ("case_0000", "time (second)", "substrate remaining (kilogram)"),
        ("case_0001", "time (second)", "substrate remaining (millimolar)"),
    ]
    roles = [axis["title"] for axis in capture["case_0001_state_trajectories.png"]["axes"]]
    assert roles[:3] == [
        "solid_cellulose_equivalent_concentration (substrate)",
        "cellobiose_concentration (intermediate)",
        "beta_D_glucose_concentration (product)",
    ]
    # The chain's processes carry no per-process mechanism rows, so their panels are named by process id only.
    assert sorted(axis["title"] for axis in capture["case_0001_process_rates.png"]["axes"]) == [
        "bio002_cellobiose_to_glucose_mm",
        "bio002_surface_cellulose_to_cellobiose",
    ]


# ---------------------------------------------------------------------------
# Artificial tables: units, thresholds and the several-process rule


TIME_SERIES_COLUMNS = (
    "case_id",
    "fungus_id",
    "substrate_id",
    "environment_id",
    "process_type",
    "sample_id",
    "time",
    "time_units",
    "state",
    "state_role",
    "value",
    "units",
    "source",
)


def _write_csv(path: Path, columns: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns))
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _series(
    case_id: str,
    sample_id: str,
    state: str,
    role: str,
    values: Sequence[float],
    *,
    units: str,
    time_units: str = "hour",
    source: str = "simulation_state",
) -> Iterator[dict[str, Any]]:
    for index, value in enumerate(values):
        yield {
            "case_id": case_id,
            "fungus_id": "artificial_fungus",
            "substrate_id": "artificial_substrate",
            "environment_id": "artificial_condition",
            "process_type": "artificial_process_type",
            "sample_id": sample_id,
            "time": float(index),
            "time_units": time_units,
            "state": state,
            "state_role": role,
            "value": value,
            "units": units,
            "source": source,
        }


def test_run_level_figure_puts_different_units_in_separate_panels(
    tmp_path: Path, capture: dict[str, dict[str, Any]]
) -> None:
    rows = [
        *_series("case_0000", "sample_0000", "pool_a", "substrate", [4.0, 2.0, 1.0], units="gram / liter"),
        *_series(
            "case_0001", "sample_0000", "pool_b", "substrate", [9.0, 3.0, 1.0], units="millimolar", time_units="minute"
        ),
    ]
    _write_csv(tmp_path / "time_series_long.csv", TIME_SERIES_COLUMNS, rows)
    names = tuple(path.name for path in write_quicklook_plots(table_dir=tmp_path))
    assert names == RUN_LEVEL_FIGURES[:4]
    axes = capture["substrate_remaining_vs_time.png"]["axes"]
    assert [(axis["title"], axis["xlabel"], axis["ylabel"]) for axis in axes] == [
        ("case_0000", "time (hour)", "substrate remaining (gram / liter)"),
        ("case_0001", "time (minute)", "substrate remaining (millimolar)"),
    ]
    assert "separate panels" in capture["substrate_remaining_vs_time.png"]["suptitle"]

    # Rows in one units text keep the single-axis figure.
    _write_csv(tmp_path / "time_series_long.csv", TIME_SERIES_COLUMNS, rows[:3])
    write_quicklook_plots(table_dir=tmp_path)
    axes = capture["substrate_remaining_vs_time.png"]["axes"]
    assert [(axis["title"], axis["xlabel"], axis["ylabel"]) for axis in axes] == [
        ("", "time", "substrate remaining (gram / liter)")
    ]


def _artificial_case_tables(tmp_path: Path, *, process_count: int) -> None:
    rows: list[dict[str, Any]] = []
    for sample, values in (("sample_0000", [4.0, 2.0, 1.0, 0.5]), ("sample_0001", [4.0, 3.0, 2.0, 1.5])):
        rows.extend(_series("case_0000", sample, "pool_a", "substrate", values, units="gram / liter"))
    for index in range(process_count):
        for sample in ("sample_0000", "sample_0001"):
            rows.extend(
                _series(
                    "case_0000",
                    sample,
                    f"process_rate.process_{index}",
                    "process_rate",
                    [1.0, 0.5, 0.25, 0.1],
                    units="gram / hour / liter",
                    source="simulation_process_rate",
                )
            )
    _write_csv(tmp_path / "time_series_long.csv", TIME_SERIES_COLUMNS, rows)
    # 50 % reached by both samples, 90 % by neither, 75 % by the first only (artificial values).
    reached = {"sample_0000": {"0.5": "1.0", "0.75": "1.0"}, "sample_0001": {"0.5": "2.0"}}
    thresholds = [
        {
            "case_id": "case_0000",
            "sample_id": sample,
            "threshold_fraction": fraction,
            "metric": f"time_to_{percent}_percent_substrate_degradation",
            "value": reached[sample].get(fraction, ""),
            "units": "hour",
            "status": "computed" if fraction in reached[sample] else "not_reached",
        }
        for sample in reached
        for fraction, percent in (("0.5", 50), ("0.9", 90), ("0.75", 75))
    ]
    _write_csv(
        tmp_path / "threshold_times.csv",
        ("case_id", "sample_id", "threshold_fraction", "metric", "value", "units", "status"),
        thresholds,
    )
    summaries = [
        {"metric": "time_to_50_percent_substrate_degradation", "count": 2, "p05": 1.05, "p50": 1.5, "p95": 1.95},
        {"metric": "time_to_75_percent_substrate_degradation", "count": 1, "p05": 1.0, "p50": 1.0, "p95": 1.0},
    ]
    _write_csv(
        tmp_path / "summary_metrics.csv",
        ("case_id", "metric", "units", "count", "p05", "p50", "p95"),
        [{"case_id": "case_0000", "units": "hour", **summary} for summary in summaries],
    )


def test_one_process_draws_no_case_figures_and_two_do(tmp_path: Path) -> None:
    one = tmp_path / "one"
    one.mkdir()
    _artificial_case_tables(one, process_count=1)
    assert tuple(path.name for path in write_quicklook_plots(table_dir=one)) == RUN_LEVEL_FIGURES[:4]
    two = tmp_path / "two"
    two.mkdir()
    _artificial_case_tables(two, process_count=2)
    assert tuple(path.name for path in write_quicklook_plots(table_dir=two)) == (*RUN_LEVEL_FIGURES[:4], *CASE_FIGURES)


def test_threshold_markers_report_reached_shares_and_unreached_thresholds(
    tmp_path: Path, capture: dict[str, dict[str, Any]]
) -> None:
    _artificial_case_tables(tmp_path, process_count=2)
    write_quicklook_plots(table_dir=tmp_path)
    figure = capture["case_0000_state_trajectories.png"]
    (substrate,) = figure["axes"]
    assert substrate["title"] == "pool_a (substrate)"
    assert substrate["legend"] == [
        # No trajectory_quantiles.csv: the two samples are drawn as lines.
        "sample_0000",
        "sample_0001",
        "50 % degraded: p50 1.5 hour, p05-p95 1.05-1.95 (shaded); reached in 2 of 2 samples",
        "90 % degraded: not reached within the simulated time",
        "75 % degraded: p50 1 hour; reached in 1 of 2 samples",
    ]
    # Two sample lines, two vertical threshold lines and the legend-only entry of the unreached threshold.
    assert substrate["lines"] == 2 + 3
    assert substrate["bands"] == 0
    assert figure["suptitle"].startswith("case_0000: every simulated state")
    assert "One line per sample (2 samples); no trajectory_quantiles.csv rows, so no band." in figure["texts"][0]
    processes = capture["case_0000_process_rates.png"]["axes"]
    assert [(axis["title"], axis["ylabel"]) for axis in processes] == [
        ("process_0", "rate (gram / hour / liter)"),
        ("process_1", "rate (gram / hour / liter)"),
    ]


def test_threshold_times_in_other_units_than_the_axis_are_not_drawn(
    tmp_path: Path, capture: dict[str, dict[str, Any]]
) -> None:
    _artificial_case_tables(tmp_path, process_count=2)
    summary = tmp_path / "summary_metrics.csv"
    summary.write_text(summary.read_text(encoding="utf-8").replace(",hour,", ",minute,"), encoding="utf-8")
    write_quicklook_plots(table_dir=tmp_path)
    (substrate,) = capture["case_0000_state_trajectories.png"]["axes"]
    assert "50 % degraded: time in minute, not drawn on the hour axis" in substrate["legend"]
    assert substrate["lines"] == 2 + 3
