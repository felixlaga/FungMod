"""Reproduce the reviewed Gelain/Novy extracts from checksum-pinned sources.

This is a source-specific extraction script, not a generic Excel importer.
No deposited MATLAB code, workbook formulas, or simulation files are executed.
Run with --check to verify committed extracts without writing them.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import posixpath
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import yaml

ROOT = Path(__file__).resolve().parents[1]
INTAKE = Path("data/experiments/source_intake")
LITERATURE = Path("data/experiments/literature/gelain_2020_t_harzianum")
NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
TIMES = [0, 8, 12, 24, 32, 48, 54, 72, 96]
CASES = [("glycerol", n) for n in (5, 10, 20)] + [("cellulose", n) for n in (10, 20, 30)]


def sheet_cells(path: Path, name: str) -> dict[str, str]:
    """Read stored source text/numbers and reject formulas in these source sheets."""
    with ZipFile(path) as archive:
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = [
                "".join(element.itertext())
                for element in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall("x:si", NS)
            ]
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheet = next(s for s in workbook.findall("x:sheets/x:sheet", NS) if s.attrib["name"] == name)
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = next(r.attrib["Target"] for r in relationships if r.attrib["Id"] == sheet.attrib[f"{{{REL}}}id"])
        member = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
        cells = {}
        for cell in ET.fromstring(archive.read(member)).findall(".//x:sheetData/x:row/x:c", NS):
            if cell.find("x:f", NS) is not None:
                raise ValueError(f"Unexpected formula in {path.name}:{name}!{cell.attrib['r']}")
            value = cell.findtext("x:v", default="", namespaces=NS)
            if cell.attrib.get("t") == "s":
                value = strings[int(value)]
            elif cell.attrib.get("t") == "inlineStr":
                value = "".join(cell.find("x:is", NS).itertext())  # type: ignore[union-attr]
            elif cell.attrib.get("t") == "e":
                raise ValueError(f"Source error in {path.name}:{cell.attrib['r']}: {value}")
            if value:
                cells[cell.attrib["r"]] = value
        return cells


def csv_bytes(fields: list[str], rows: list[dict[str, object]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def verify_sources(root: Path) -> dict[str, dict]:
    manifest = json.loads((root / INTAKE / "manifest.json").read_text())
    entries = {}
    for record in manifest["files"]:
        content = (root / INTAKE / record["path"]).read_bytes()
        if len(content) != record["bytes"] or hashlib.sha256(content).hexdigest() != record["sha256"]:
            raise ValueError(f"Source checksum mismatch: {record['path']}")
        entries[record["path"]] = record
    return entries


def prepare(root: Path = ROOT) -> dict[Path, bytes]:
    sources = verify_sources(root)
    outputs: dict[Path, bytes] = {}
    long_rows: list[dict[str, object]] = []
    for substrate, concentration in CASES:
        original = f"gelain_2020/originals/{substrate}/{concentration}gL.xlsx"
        cells = sheet_cells(root / INTAKE / original, "Plan1")
        is_cellulose = substrate == "cellulose"
        columns = {"biomass": "E" if is_cellulose else "B", "substrate": "F" if is_cellulose else "C"}
        if is_cellulose:
            columns.update(cellulase_activity="B", beta_glucosidase_activity="C")
        expected_headers = (
            {"A1": "time (h)", "B1": "Fpase (FPU/L)", "C1": "Beta (U/L)",
             "E1": "Cells (g/L)", "F1": "Cellulose (g/L)"}
            if is_cellulose else
            {"A1": "Time (h)", "B1": "Cell (g/L)", "C1": "Glycerol  (g/L)"}
        )
        if any(cells.get(address) != label for address, label in expected_headers.items()):
            raise ValueError(f"Unexpected source headers: {original}")
        wide_rows: list[dict[str, object]] = []
        stem = f"gelain_2020_{substrate}_{concentration}gl"
        for row, time in enumerate(TIMES, start=2):
            if float(cells[f"A{row}"]) != time:
                raise ValueError(f"Unexpected sampling time: {original}!A{row}")
            wide: dict[str, object] = {"time_h": cells[f"A{row}"], "source_row": row}
            for observable, column in columns.items():
                value = cells[f"{column}{row}"]
                units = {"cellulase_activity": "FPU/L", "beta_glucosidase_activity": "U/L"}.get(observable, "g/L")
                long_rows.append({
                    "condition_id": stem, "substrate": substrate, "nominal_initial_g_l": concentration,
                    "time_h": cells[f"A{row}"], "observable": observable, "value": value, "source_units": units,
                    "record_role": "source_initial_condition" if time == 0 else "published_mean",
                    "uncertainty": "", "replicate_id": "", "source_file": original,
                    "source_sheet": "Plan1", "source_cell": f"{column}{row}",
                })
                if observable in ("biomass", "substrate"):
                    wide[f"{observable}_g_l"] = value
            if time != 0:
                wide_rows.append(wide)
        outputs[LITERATURE / f"{stem}.csv"] = csv_bytes(
            ["time_h", "source_row", "biomass_g_l", "substrate_g_l"], wide_rows
        )
        metadata = {
            "kind": "experiment_dataset", "dataset_id": stem + "_v1",
            "name": f"Gelain 2020 T. harzianum P49P11 on {concentration} g/L {substrate}",
            "maturity": "literature_processed",
            "source": {
                "type": "literature",
                "citation": "Gelain L, van der Wielen L, van Gulik WM, Pradella JGC, da Costa AC. "
                "Mathematical modelling for the optimization of cellulase production using glycerol for "
                "cell growth and cellulose as the inducer substrate. Chemical Engineering Science X 8 (2020), 100085.",
                "doi": "10.1016/j.cesx.2020.100085", "url": "https://data.mendeley.com/datasets/shd3wcczsr/2",
                "authors": ["Lucas Gelain", "Luuk van der Wielen", "Walter M. van Gulik",
                            "Jose Geraldo da Cruz Pradella", "Aline Carvalho da Costa"],
                "year": 2020, "figure_or_table": f"Deposited {substrate.title()} model/{concentration}gL.xlsx, Plan1",
                "extraction_method": "Direct extraction of stored XLSX numeric cells; initial conditions separated",
                "extraction_tool": "scripts/prepare_public_experimental_data.py; Python XML/ZIP reader",
                "extracted_by": "Codex for FungMod", "extraction_date": "2026-09-28",
                "raw_units": {"time": "h", "biomass": "g/L", "substrate": "g/L"},
                "notes": "CC BY 4.0. Dataset DOI 10.17632/shd3wcczsr.2. Deposited Information.docx identifies "
                "the concentration-specific workbooks as experimental and data.xlsx as simulation results.",
            },
            "system": {"organism": "Trichoderma harzianum P49P11", "enzyme": None,
                       "substrate": substrate, "product": None, "environment": "Controlled submerged batch culture",
                       "geometry": "stirred bioreactor", "notes": "Whole culture; no enzyme concentration inferred."},
            "conditions": {
                "temperature": {"value": 29, "units": "degree_Celsius"},
                "ph": {"value": 5, "units": "dimensionless"},
                "working_volume": {"value": 1.9, "units": "liter"},
                "nominal_initial_substrate": {"value": concentration, "units": "gram / liter"},
                "source_initial_biomass": {"value": float(cells["E2" if is_cellulose else "B2"]), "units": "gram / liter"},
                "sampling_times": {"values": TIMES[1:], "units": "hour"},
                "notes": "Methods 2.2: pH controlled at 5.0 +/- 0.5; oxygen maintained above 30%. "
                "Batch cultures performed in duplicate with different inocula. Methods 2.3 omit 54 h, "
                "but all six source workbooks explicitly contain it; retained without silently changing time.",
            },
            "measurements": [{
                "id": observable, "measured_quantity": f"{substrate if observable == 'substrate' else 'biomass'} concentration",
                "observable_type": "state", "data_file": stem + ".csv", "time_column": "time_h",
                "value_column": observable + "_g_l", "uncertainty_column": None,
                "units": {"time": "hour", "value": "gram / liter", "uncertainty": None},
                "uncertainty_type": "unknown: individual duplicates and SD not deposited",
                "censoring": "unknown; recorded zeros retained", "replicate_id_column": None,
                "notes": "Published duplicate means, not individual replicates. See source_row for cell traceability.",
            } for observable in ("biomass", "substrate")],
            "measurement_definitions": {
                "measured_quantity": "Culture biomass and remaining substrate concentration",
                "units": "gram / liter", "uncertainty_definition": "Unavailable in deposited experimental workbooks; "
                "paper uses duplicate means and plots sample SD. No SD or replicate measurements invented.",
                "measurement_method": "Article Methods 2.3: glycerol by HPLC; cellulose and mycelium according "
                "to Ahamed and Vermette (2009). Biomass/substrate separation and assay details require review before fitting.",
            },
            "preprocessing": {
                "status": "machine_readable_mean_extraction", "raw_data_available": False,
                "steps": ["Verify source SHA-256", "Read Plan1 stored cells without executing formulas",
                          "Retain numeric values and time labels", "Separate t=0 source initial conditions",
                          "Import only biomass and substrate into ExperimentDataset"],
                "unit_conversions": ["None; h to hour and g/L to gram / liter are unit-label expansions only"],
                "excluded_points": ["t=0 entries are source initial conditions, retained in source intake, not fitting observations"],
                "notes": "No smoothing, error reconstruction, inferred replicates, or fitting. Activity values remain "
                "in source intake in FPU/L and U/L, pending assay-specific observation operators. All six conditions "
                "were used for estimation in the source publication; none is independent external validation.",
            },
            "supplementary_data": {
                "file_name": original, "source_url_or_doi": "https://doi.org/10.17632/shd3wcczsr.2",
                "checksum": "sha256:" + sources[original]["sha256"], "access_date": "2026-09-28",
                "notes": "Original file preserved under data/experiments/source_intake; full archive and article also preserved.",
            },
            "validation": {"expected_columns": ["time_h", "source_row", "biomass_g_l", "substrate_g_l"],
                           "allow_missing_uncertainty": True},
            "notes": "Exploratory whole-culture data for one strain, not a validated fungal model. "
            "Cannot pass the independent raw-replicate evidence gate. Source zeros are not assumed exact measurements.",
        }
        outputs[LITERATURE / f"{stem}.yml"] = yaml.safe_dump(metadata, sort_keys=False, width=100).encode()
    outputs[INTAKE / "gelain_2020/recorded_values.csv"] = csv_bytes(list(long_rows[0]), long_rows)
    secretome = sheet_cells(root / INTAKE / "novy_2021/secretome.xlsx", "Proteins_All")
    secretome_rows = []
    for row in range(3, 235):
        secretome_rows.append(dict(zip(
            ["source_index", "protein", "TRIRE2", "source_mass_label", "source_CAZy", "NBSK", "LPP-STEX", "LPP- ALK-OX"],
            [secretome.get(f"{column}{row}", "") for column in "ABCDEFGH"], strict=True,
        ), source_row=row))
    outputs[INTAKE / "novy_2021/proteins_all.csv"] = csv_bytes(list(secretome_rows[0]), secretome_rows)
    # These are explicitly software reproduction references, NEVER observations.
    benchmark = Path("data/benchmarks/gelain_2020")
    parameter_rows = {}
    simulation_rows = []
    shared = [("mu", "1/hour"), ("K", "gram/liter"), ("Xmax", "gram/liter"),
              ("d", "1/hour"), ("Kd", "gram/liter"), ("alpha", "liter/gram")]
    induction = [("mue", "1/hour"), ("Ke", "gram/liter"), ("Amax", "gram/liter"),
                 ("kda", "1/hour"), ("beta", "liter/gram")]
    for family, doses in (("glycerol", (5, 10, 20)), ("cellulose", (10, 20, 30))):
        relative = f"gelain_2020/simulation_reference/{family}.xlsx"
        original = root / INTAKE / relative
        cells = sheet_cells(original, "Parameters")
        mapping = list(zip(range(2, 8), shared, strict=True))
        if family == "cellulose":
            mapping += list(zip(range(11, 16), induction, strict=True))
        parameter_rows[family] = [
            {"symbol": symbol, "value": float(cells[f"A{row}"]), "units": units,
             "source_file": relative, "source_cell": f"Parameters!A{row}",
             "source": "doi:10.17632/shd3wcczsr.2; published fit to ALL available conditions",
             "uncertainty": None}
            for row, (symbol, units) in mapping
        ]
        for dose in doses:
            sheet = f"Assay {dose} gL"
            cells = sheet_cells(original, sheet)
            for row in range(2, 195 if family == "glycerol" else 99):
                simulation_rows.append({
                    "family": family, "initial_substrate_g_l": dose, "time_h": cells[f"A{row}"],
                    "biomass_g_l": cells[f"B{row}"], "substrate_g_l": cells[f"C{row}"],
                    "induced_proxy_g_l": "" if family == "glycerol" else cells[f"F{row}"],
                    "role": "source_simulation_not_measurement", "source_file": relative,
                    "source_sheet": sheet, "source_row": row,
                })
    outputs[benchmark / "source_parameters.json"] = (json.dumps(parameter_rows, indent=2) + "\n").encode()
    outputs[benchmark / "source_simulations.csv"] = csv_bytes(list(simulation_rows[0]), simulation_rows)
    outputs.update(prepare_culture_v2(root, long_rows))
    return outputs


def prepare_culture_v2(root: Path, recorded: list[dict[str, object]]) -> dict[Path, bytes]:
    """Preserve activity assay units and the full deposited simulation separately."""
    target = Path("data/benchmarks/gelain_2020_v2")
    conditions = []
    for family, dose in CASES:
        name = f"gelain_2020_{family}_{dose}gl"
        records = [r for r in recorded if r["condition_id"] == name]
        names = ["biomass", "substrate"] + (["cellulase_activity", "beta_glucosidase_activity"] if family == "cellulose" else [])
        observations = {}
        for observable in names:
            rows = [r for r in records if r["observable"] == observable and r["record_role"] == "published_mean"]
            observations[observable] = {"values": [float(str(r["value"])) for r in rows],
                "units": rows[0]["source_units"], "uncertainty": None, "censoring_limits": None,
                "source_file": rows[0]["source_file"], "source_sheet": "Plan1",
                "source_cells": [r["source_cell"] for r in rows]}
        initial = {str(r["observable"]): {"value": float(str(r["value"])), "units": r["source_units"],
                   "source_cell": r["source_cell"]} for r in records if r["record_role"] == "source_initial_condition"}
        conditions.append({"condition_id": name, "family": family, "times_h": TIMES[1:],
            "initial": initial, "observations": observations,
            "source": "doi:10.17632/shd3wcczsr.2; stored experimental duplicate means",
            "maturity": "literature_processed", "raw_replicates_available": False})
    originals = root / INTAKE / "gelain_2020/simulation_reference/cellulose.xlsx"
    cells = sheet_cells(originals, "Parameters")
    raw = [float(cells[f"A{i}"]) for i in range(2, 23)]
    # z=A/Amax is dimensionless: an exact change of coordinates removes the
    # unobservable A-scale and absorbs the fixed inhibition coefficient in KI.
    values = {"mu": raw[0], "K": raw[1], "Xmax": raw[2], "d": raw[3], "Kd": raw[4], "alpha": raw[5],
              "k_ind": raw[9]/raw[11], "Ke": raw[10], "kda": raw[12], "b_ind": raw[13]*raw[11]**2,
              "qF": raw[6]*raw[11], "kF": raw[7], "KI_F": raw[8]/0.15, "Fmax": raw[14], "SI_F": raw[19],
              "qB": raw[15]*raw[11], "kB": raw[16], "KI_B": raw[17]/0.15, "Bmax": raw[18], "SI_B": raw[20]}
    units = {"mu":"1/hour", "K":"gram/liter", "Xmax":"gram/liter", "d":"1/hour", "Kd":"gram/liter",
             "alpha":"liter/gram", "k_ind":"liter/gram/hour", "Ke":"gram/liter", "kda":"1/hour", "b_ind":"gram/liter",
             "qF":"gelain_fpu/liter/hour", "kF":"1/hour", "KI_F":"(gram/liter)**2", "Fmax":"gelain_fpu/liter", "SI_F":"gram/liter",
             "qB":"gelain_beta_u/liter/hour", "kB":"1/hour", "KI_B":"(gram/liter)**2", "Bmax":"gelain_beta_u/liter", "SI_B":"gram/liter"}
    simulations = []
    for dose in (10, 20, 30):
        cells = sheet_cells(originals, f"Assay {dose} gL")
        for row in range(2, 99):
            simulations.append({"initial_substrate_g_l": dose, "time_h": cells[f"A{row}"],
                                "biomass_g_l": cells[f"B{row}"], "substrate_g_l": cells[f"C{row}"],
                                "cellulase_fpu_l": cells[f"D{row}"], "beta_u_l": cells[f"E{row}"],
                                "role": "source_simulation_not_measurement"})
    parameters = {"role": "software_parity_only_never_fit_initialization", "source": "doi:10.17632/shd3wcczsr.2",
                  "coordinate_change": "z=A/Amax; k_ind=mue/Amax; b_ind=beta*Amax^2; q*=q*Amax; KI=ki/0.15",
                  "fixed_coefficient_source": "Gelain 2020 Eq 9-10 a=b=0.15 when S exceeds SI; manually chosen in source",
                  "parameters": [{"symbol": k, "value": v, "units": units[k], "uncertainty": None,
                    "source": "doi:10.17632/shd3wcczsr.2; ALL-condition published fit, transformed algebraically"} for k,v in values.items()]}
    return {target / "observations.json": (json.dumps(conditions, indent=2)+"\n").encode(),
            target / "source_parameters.json": (json.dumps(parameters, indent=2)+"\n").encode(),
            target / "source_simulations.csv": csv_bytes(list(simulations[0]), simulations)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    outputs = prepare()
    for relative, content in outputs.items():
        path = ROOT / relative
        if args.check:
            if not path.exists() or path.read_bytes() != content:
                raise SystemExit(f"Stale or missing extract: {relative}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    print(f"{'Verified' if args.check else 'Wrote'} {len(outputs)} extracts from checksum-pinned sources.")


if __name__ == "__main__":
    main()
