"""Stage 12 example 2: surface-limited PET hydrolysis by fixed enzyme."""

from __future__ import annotations

from pathlib import Path

from stage12_common import ROOT, load_example_module

SOURCE = load_example_module(
    "03_pet_surface_hydrolysis.py",
    "stage12_source_pet_surface_hydrolysis",
)


def run(output_dir: Path = ROOT / "outputs" / "stage12_02_pet_surface_model") -> None:
    SOURCE.run(output_dir)


if __name__ == "__main__":
    run()
