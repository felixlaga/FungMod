"""Deterministically extract the preserved Jorgensen 2009 primary table offline."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "data/benchmarks/jorgensen_2009_secretion"


def encoded(value: dict) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()


def measurement(text: str) -> dict:
    match = re.fullmatch(r"([0-9.]+) ± ([0-9.]+)(\*?)", text)
    if match is None:
        raise ValueError(f"Expected a published mean +/- SD: {text!r}")
    return {"value": float(match[1]), "sd": float(match[2]), "verbatim": text,
            "published_significance_marker": match[3] or None}


def extract(directory: Path) -> dict:
    root = ET.parse(directory / "PMC2639373.xml").getroot()
    table = root.find(".//table-wrap[@id='T1']")
    if table is None:
        raise ValueError("Primary Table 1 is missing.")
    rows = [[" ".join("".join(c.itertext()).split()) for c in row] for row in table.findall(".//tr")]
    records = []
    carbon = ""
    fields = ("biomass_gDW_kg", "residual_substrate_uM", "biomass_yield_gDW_g_substrate",
              "biomass_yield_gDW_g_carbon", "carbon_dioxide_mmol_gDW_h", "oxygen_mmol_gDW_h",
              "respiratory_quotient", "extracellular_protein_mg_gDW_h", "carbon_recovery_percent")
    for row in rows[1:]:
        carbon = row[0] or carbon
        if not carbon or len(row) != 11:
            raise ValueError("Unexpected primary table layout.")
        records.append({"id": f"jorgensen_2009_{row[1]}_{carbon.lower()}", "strain": row[1],
                        "carbon_source": carbon.lower(), "growth_rate_per_h": .16, "replicates": 3,
                        **{key: measurement(cell) for key, cell in zip(fields, row[2:], strict=True)}})
    return {"schema_version": 1, "doi": "10.1186/1471-2164-10-44", "organism": "Aspergillus niger",
            "attribution": "Jorgensen, Goosen, van den Hondel, Ram and Iversen (2009), BMC Genomics 10:44, Table 1.",
            "license": "CC-BY-2.0", "license_url": "https://creativecommons.org/licenses/by/2.0/",
            "conditions": {"temperature_K": 303.15, "pH": 3., "nominal_dilution_per_h": .16,
                           "dissolved_oxygen": ">40% air saturation", "morphology": "Dispersed filamentous hyphae"},
            "uncertainty": "Reported SD of triplicate independent steady-state measurements, not SEM or confidence intervals. "
                           "Raw replicates and cross-condition covariances are unavailable.",
            "dependence": "Three cultures per strain; xylose then maltose sequentially in each culture. "
                          "Four group means summarize 12 steady states in six culture runs, not 12 independent culture runs.",
            "role": "Retrospective strain-held-out test of total extracellular protein output conditional on supplied growth rate "
                    "and carbon source. Not validation of enzyme activity, secretion dynamics or whole-culture degradation.",
            "limitations": ["One growth rate cannot identify growth-associated versus non-growth-associated secretion.",
                "Protein mass is not catalytic activity. Protein composition, active fraction and biosynthetic yield are unresolved.",
                "Net extracellular protein output need not equal biosynthesis if unmeasured degradation/retention occurs.",
                "Residual maltose is in glucose equivalents; no conversion to maltose concentration is silently applied.",
                "Published significance markers are preserved; no significance test is rerun from group means."],
            "transformations": "Table 1 XML text to numeric means and SDs. Blank carbon-source cells inherit preceding source. "
                               "Growth rate 0.16/h is nominal dilution from Methods; no reported units are changed.",
            "records": records, "raw_table": rows,
            "table_footnotes": [" ".join("".join(p.itertext()).split()) for p in table.findall("./table-wrap-foot/p")]}


def prepare(directory: Path, *, check: bool) -> dict:
    output = encoded(extract(directory))
    if check:
        if (directory / "observations.json").read_bytes() != output:
            raise ValueError("Frozen observations differ from the preserved primary XML.")
        manifest = json.loads((directory / "manifest.json").read_text())
        for entry in manifest["files"]:
            relative = Path(entry["path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Manifest path must remain within the dataset.")
            content = (directory / relative).read_bytes()
            if len(content) != entry["bytes"] or hashlib.sha256(content).hexdigest() != entry["sha256"]:
                raise ValueError(f"Checksum mismatch: {relative}")
        return manifest
    (directory / "observations.json").write_bytes(output)
    entries = []
    for name in ("PMC2639373.xml", "observations.json"):
        content = (directory / name).read_bytes()
        entries.append({"path": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(),
                        "role": "primary_article_xml" if name.endswith(".xml") else "deterministic_table_extract"})
    manifest = {"schema_version": 1, "doi": "10.1186/1471-2164-10-44", "license": "CC-BY-2.0",
                "retrieved_on": "2026-10-03", "files": entries, "extractor": "scripts/prepare_secretion_data.py",
                "primary_xml_url": "https://www.ebi.ac.uk/europepmc/webservices/rest/PMC2639373/fullTextXML"}
    (directory / "manifest.json").write_bytes(encoded(manifest))
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = prepare(DIRECTORY, check=args.check)
    print(f"{'Verified' if args.check else 'Wrote'} {len(result['files'])} source/extract checksums.")
