"""Stage 12 example 5: fungal growth only from assimilable products."""

from __future__ import annotations

from pathlib import Path

from stage12_common import ROOT, load_example_module

SOURCE = load_example_module(
    "05_fungal_enzyme_secretion_and_growth.py",
    "stage12_source_fungal_growth_from_assimilable_products",
)


def run(output_dir: Path = ROOT / "outputs" / "stage12_05_fungal_growth_from_assimilable_products") -> None:
    SOURCE.run(output_dir)


if __name__ == "__main__":
    run()
