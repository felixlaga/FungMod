"""Re-extract public article tables offline, preserving reported values and roles.

No downloads, spreadsheet formula execution, invented replicate data, or
corrections to suspicious published cells. Input XML must already be present.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "data/benchmarks/lameiras_respiration"
SOURCE_IDS = {"lameiras_2015": ("PMC4559092", "10.1007/s11306-015-0781-z"),
              "lameiras_2017": ("PMC5773628", "10.1007/s00449-017-1854-3")}


def tables(pmc: str, directory: Path) -> dict[str, list[list[str]]]:
    root = ET.parse(directory / f"{pmc}.xml").getroot()
    return {table.attrib["id"]: [[" ".join("".join(cell.itertext()).split()) for cell in row
                                if cell.tag in {"th", "td"}] for row in table.findall(".//tr")]
            for table in root.findall(".//table-wrap")}


def measurement(text: str, scale: float = 1) -> dict:
    parts = text.split(" ± ")
    if len(parts) != 2:
        raise ValueError(f"Expected a reported mean and error: {text!r}")
    return {"value": float(parts[0]) * scale, "reported_error": float(parts[1]) * scale, "verbatim": text}


def extract(directory: Path) -> dict:
    first, second = tables("PMC4559092", directory), tables("PMC5773628", directory)
    raw = first["Tab2"]
    single = []
    for i, dilution in enumerate(raw[0][1:]):
        record = {"id": f"lameiras_2015_D{dilution}", "dilution_per_h": float(dilution),
                  "dilution": measurement(first["Tab1"][0][i + 1]),
                  "biomass_gDW_kg_broth": measurement(first["Tab1"][3][i + 1])}
        for offset, role in ((1, "unreconciled"), (2, "reconciled")):
            record[role] = {key: measurement(raw[row][2 * i + offset], .001)
                for key, row in (("biomass_rate", 4), ("substrate_uptake", 5), ("oxygen_uptake", 6),
                                 ("carbon_dioxide_release", 7), ("unresolved_organic_carbon_release", 8))}
        single.append(record)
    batch = []
    for row in second["Tab1"][1:]:
        batch.append({"substrate": row[0], **{key: measurement(row[index]) for index, key in enumerate(
            ("respiratory_quotient", "carbon_recovery_percent", "redox_recovery_percent", "carbon_yield",
             "growth_rate", "substrate_uptake", "oxygen_uptake", "carbon_dioxide_release"), start=1)}})
    mixed = []
    for i, dilution in enumerate(second["Tab2"][0][1:], start=1):
        mixed.append({"id": f"lameiras_2017_mixed_D{dilution}", "dilution_per_h": float(dilution),
                      "biomass_gDW_L": measurement(second["Tab2"][1][i]),
                      "respiratory_quotient": measurement(second["Tab2"][2][i]),
                      "reconciled": {key: measurement(second["Tab2"][row][i], .001) for key, row in (
                          ("glucose_uptake", 5), ("xylose_uptake", 6), ("arabinose_uptake", 7),
                          ("galacturonic_acid_uptake", 8), ("mannose_uptake", 9), ("rhamnose_uptake", 10),
                          ("oxygen_uptake", 11), ("carbon_dioxide_release", 12), ("biomass_rate", 13),
                          ("unresolved_organic_carbon_release", 14))},
                      "quality_flags": (["Published CO2 3.7 +/- 3.9 contradicts the reported RQ and O2; "
                                         "TOC 1.2 +/- 1.9 is also suspicious. Preserve verbatim, quarantine both "
                                         "from quantitative scoring until primary supplemental verification."]
                                        if dilution == "0.16" else [])})
    return {"schema_version": 1, "organism": "Aspergillus niger NW185",
            "license": "CC-BY-4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "attribution": "Lameiras, Heijnen and van Gulik (2015); Lameiras, Ras, ten Pierick, Heijnen and van Gulik (2017).",
            "transformations": "XML table extraction; mmol to mol and mCmol to Cmol scaled by 0.001; no numerical corrections.",
            "rate_units": "mol species / (Cmol biomass * hour); biomass/TOC rates Cmol / (Cmol biomass * hour)",
            "uncertainty": "Reported errors preserved. Their complete statistical interpretation and covariance are "
                "unavailable here; do not treat them as independent replicate SDs, weights, or confidence intervals.",
            "lameiras_2015": {"doi": SOURCE_IDS["lameiras_2015"][1], "temperature_K": 303.15, "pH": 3.0,
                "basis": "Glucose-limited well-mixed chemostat; dissolved oxygen >50% air saturation.",
                "biomass_composition": {"C": 1., "H": 1.8, "N": .12, "O": .6},
                "biomass_formula_mass_g_per_Cmol": {"value": 27.3, "reported_error": .2},
                "records": single, "role": "Unreconciled rates for primary calibration/holdout; reconciled rates retained as reference only."},
            "lameiras_2017": {"doi": SOURCE_IDS["lameiras_2017"][1], "temperature_K": 303.15, "pH": 2.5,
                "single_substrate_batch": batch, "mixed_substrate_chemostat": mixed,
                "role": "External regime challenge and missing-mechanism diagnostics only. Conversion rates are reconciled "
                    "using conservation and are not independent validation of elemental conservation.",
                "dependence": "Same laboratory/strain; sequential mixed-substrate dilution conditions share a culture. "
                    "This is not an independent laboratory or replicated longitudinal validation."},
            "raw_tables": {"lameiras_2015": first, "lameiras_2017": second}}


def encoded(value: dict) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()


def prepare(directory: Path, *, check: bool) -> dict:
    output = encoded(extract(directory))
    if check:
        if (directory / "observations.json").read_bytes() != output:
            raise ValueError("Frozen observation extract does not match the preserved primary XML.")
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        for entry in manifest["files"]:
            content = (directory / entry["path"]).read_bytes()
            if len(content) != entry["bytes"] or hashlib.sha256(content).hexdigest() != entry["sha256"]:
                raise ValueError(f"Checksum mismatch: {entry['path']}")
        return manifest
    (directory / "observations.json").write_bytes(output)
    files = []
    for name in ("PMC4559092.xml", "PMC5773628.xml", "observations.json"):
        content = (directory / name).read_bytes()
        files.append({"path": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(),
                      "url": f"https://www.ebi.ac.uk/europepmc/webservices/rest/{name[:-4]}/fullTextXML"
                      if name.endswith(".xml") else None, "retrieved_on": "2026-10-03" if name.endswith(".xml") else None,
                      "role": "primary_article_xml" if name.endswith(".xml") else "deterministic_table_extract"})
    manifest = {"schema_version": 1, "files": files,
                "license": "CC-BY-4.0", "sources": SOURCE_IDS,
                "extractor": "scripts/prepare_respiration_data.py",
                "unavailable_sources": ["Springer supplemental DOCX download: URLError, nodename nor servname provided, "
                    "or not known; Europe PMC supplementaryFiles endpoint: read timeout after 45 seconds. "
                    "Unverified supplemental data are not included or inferred."]}
    (directory / "manifest.json").write_bytes(encoded(manifest))
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = prepare(DIRECTORY, check=args.check)
    print(f"{'Verified' if args.check else 'Extracted'} {len(result['files'])} checksummed files.")
