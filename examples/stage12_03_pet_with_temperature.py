"""Stage 12 example 3: PET hydrolysis with Arrhenius temperature dependence."""

from __future__ import annotations

from pathlib import Path

from stage12_common import ROOT, load_example_module

SOURCE = load_example_module(
    "04_pet_temperature_ph.py",
    "stage12_source_pet_temperature_ph",
)


def run(output_dir: Path = ROOT / "outputs" / "stage12_03_pet_with_temperature") -> None:
    SOURCE.run(output_dir)


if __name__ == "__main__":
    run()
