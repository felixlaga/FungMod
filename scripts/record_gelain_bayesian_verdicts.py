"""Copy the recorded posterior-sampling verdicts into the registry record provenance.

Provenance only: the nine calibrated T. harzianum records keep their frozen
point values. Each gains (or replaces) a ``bayesian_identifiability`` block
naming the artifact, its digest, the class, the credible interval and the
evidence of the error model. Run from the repository root:

    python scripts/record_gelain_bayesian_verdicts.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "data" / "benchmarks" / "gelain_2020_bayesian" / "results"
PLAN = ROOT / "data" / "benchmarks" / "gelain_2020_bayesian" / "plan.json"
ARTIFACT = "data/benchmarks/gelain_2020_bayesian/results/bayesian_calibration.json"
BLOCK_KEY = "bayesian_identifiability"


def provenance_block(symbol: str, summary: dict, digest: str, benchmark_id: str) -> str:
    verdict = summary["identifiability"][symbol]
    scale_evidence = ", ".join(summary["noise_evidence"])
    lower, upper = verdict["credible_interval"]
    lines = [
        f"      {BLOCK_KEY}:",
        f"        artifact: {ARTIFACT}",
        f"        artifact_sha256: {digest}",
        f"        benchmark_id: {benchmark_id}",
        f"        class: {verdict['class']}",
        "        credible_interval:",
        f"          - {lower!r}",
        f"          - {upper!r}",
        f"        credible_mass: {verdict['credible_mass']!r}",
        f"        units: {verdict['units']}",
        f"        converged: {str(bool(summary['converged'])).lower()}",
        f"        error_model_evidence: {scale_evidence}",
        "        meaning: >-",
        "          Posterior credible interval and identifiability class from the recorded",
        "          ensemble-sampling study, conditional on the declared log-uniform prior box and",
        "          an assumed error model with estimated scale multipliers; the data constrain",
        f"          {verdict['data_constrain']}. The exact point value above is unchanged; a class",
        "          other than identified means the constant should be read as this range.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    summary = json.loads((RESULTS / "bayesian_calibration.json").read_text(encoding="utf-8"))
    artifacts = json.loads((RESULTS / "artifacts.json").read_text(encoding="utf-8"))
    digest = artifacts["bayesian_calibration.json"]
    benchmark_id = str(json.loads(PLAN.read_text(encoding="utf-8"))["benchmark_id"])
    path = ROOT / "data_registry" / "parameters" / "parameter_records.yml"
    text = path.read_text(encoding="utf-8")
    for symbol in summary["parameters"]:
        record_id = f"{symbol}_calibrated"
        start = text.index(f"record_id: {record_id}\n")
        end = text.index("    parameter_symbol:", start)
        block = text[start:end]
        block = re.sub(rf"      {BLOCK_KEY}:\n(?:        .*\n|          .*\n)*", "", block)
        anchor = "      uncertainty: unknown_no_measurement_sd_no_confidence_interval\n"
        if anchor not in block:
            raise SystemExit(f"{record_id}: provenance anchor not found")
        block = block.replace(anchor, anchor + provenance_block(symbol, summary, digest, benchmark_id))
        text = text[:start] + block + text[end:]
    path.write_text(text, encoding="utf-8")
    print(f"updated {len(summary['parameters'])} records in {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
