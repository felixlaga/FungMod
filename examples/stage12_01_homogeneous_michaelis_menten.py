"""Stage 12 example 1: homogeneous Michaelis-Menten toy substrate."""

from __future__ import annotations

from pathlib import Path

from stage12_common import ROOT, load_example_module

SOURCE = load_example_module(
    "02_homogeneous_michaelis_menten.py",
    "stage12_source_homogeneous_michaelis_menten",
)


def run(output_dir: Path = ROOT / "outputs" / "stage12_01_homogeneous_michaelis_menten") -> None:
    SOURCE.run(output_dir)


if __name__ == "__main__":
    run()
