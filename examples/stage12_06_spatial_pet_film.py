"""Stage 12 example 6: 1D spatial PET film with enzyme diffusion."""

from __future__ import annotations

from pathlib import Path

from stage12_common import ROOT, load_example_module

SOURCE = load_example_module(
    "06_spatial_pet_film_enzyme_diffusion.py",
    "stage12_source_spatial_pet_film",
)


def run(output_dir: Path = ROOT / "outputs" / "stage12_06_spatial_pet_film") -> None:
    SOURCE.run(output_dir)


if __name__ == "__main__":
    run()
