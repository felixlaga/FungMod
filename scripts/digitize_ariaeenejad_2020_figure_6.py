"""Digitize the PersiBGL1 cellobiose hydrolysis time course in Ariaeenejad 2020 Figure 6.

This is FungMod's second literature source and the first from a different
laboratory, enzyme, and assay regime than Alvarez-Gonzalez 2022. It was
previously blocked in `data/experiments/candidate_reviews/` because the source
text conflicts about the time axis. That conflict is resolved here from the
figure itself rather than from the prose.

Resolved source defects, all recorded rather than silently corrected:

1. Time axis. The Results text says "the rate of conversion reaches to zero
   after 380 min", but the Methods say samples were "measured in 24-h time
   intervals ... until 380 h", the same Results paragraph says "from 1 h
   (0.44 micromole/ml) to 380 h" and "did not decrease significantly after
   300 h", and the figure's own x-axis is labelled "Biodegradation period (h)"
   with ticks at 1 and 24-hour multiples. The axis label is decisive: the
   series is in hours and the single "380 min" is a typo.

2. Y-axis unit. The axis is labelled "Glucose liberated mmol/ml", which would be
   15850 mM at the final point. The Results state the final concentration twice,
   as "15.85 mM" and as "15.85 micromole/ml". Both agree at 15.85 mM, so the
   printed axis unit is a typo for micromole/ml, which equals millimolar.

3. Tick label. Ticks run 1, 24, 48, ..., 168, 188, 212, ..., 380. Every interval
   is 24 h except 168 -> 188, which is 20. The label 188 is most likely a typo
   for 192. Times are stored exactly as printed and the anomaly is recorded.

The y calibration is verified against two values the source states in prose,
independently of the figure. The script refuses to write unless both are
reproduced within the declared resolution.

Usage::

    python scripts/digitize_ariaeenejad_2020_figure_6.py \
        --pdf ariaeenejad2020.pdf \
        --output-dir data/experiments/literature/ariaeenejad_2020_persibgl1_cellobiose
"""

from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from PIL import Image
from scipy import ndimage as ndi

SOURCE_PAGE_INDEX = 10  # zero-based; article page 11
RENDER_SCALE = 3
EXPECTED_RENDER_SIZE = (1786, 2339)

BAR_RGB = (91, 156, 214)
BAR_TOLERANCE = 40

# Y calibration read from the rendered axis tick marks.
ROW_AT_0 = 806.5
ROWS_PER_UNIT = 32.75

# Sampling times exactly as printed on the figure x axis.
SAMPLING_TIMES_H = (1, 24, 48, 72, 96, 120, 144, 168, 188, 212, 236, 260, 284, 308, 332, 356, 380)

# Values the source states in prose, used to verify the calibration.
STATED_FIRST_MM = 0.44
STATED_FINAL_MM = 15.85
DIGITIZATION_ERROR_MM = 0.10
VERIFY_TOLERANCE_MM = 0.15


def render_page(pdf_path: Path) -> tuple[np.ndarray, str]:
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    document = pdfium.PdfDocument(str(pdf_path))
    image = document[SOURCE_PAGE_INDEX].render(scale=RENDER_SCALE).to_pil().convert("RGB")
    if image.size != EXPECTED_RENDER_SIZE:
        raise SystemExit(f"Unexpected render size {image.size}; expected {EXPECTED_RENDER_SIZE}.")
    return np.array(image).astype(int), digest


def extract_bars(page: np.ndarray) -> tuple[tuple[float, float], ...]:
    """Return (column, top_row) for each bar, ordered left to right."""

    mask = np.abs(page - np.array(BAR_RGB)).sum(axis=-1) < BAR_TOLERANCE
    labels, count = ndi.label(mask)
    bars: list[tuple[float, float]] = []
    for index, slices in enumerate(ndi.find_objects(labels), start=1):
        height = slices[0].stop - slices[0].start
        width = slices[1].stop - slices[1].start
        if height < 5 or width < 5:
            continue
        bars.append((float((slices[1].start + slices[1].stop) / 2.0), float(slices[0].start)))
    bars.sort()
    if len(bars) != len(SAMPLING_TIMES_H):
        raise SystemExit(f"Expected {len(SAMPLING_TIMES_H)} bars but found {len(bars)}.")
    return tuple(bars)


def to_millimolar(top_row: float) -> float:
    return (ROW_AT_0 - top_row) / ROWS_PER_UNIT


def verify(values: tuple[float, ...]) -> tuple[float, float]:
    """Fail unless the calibration reproduces both prose-stated values."""

    first_deviation = abs(values[0] - STATED_FIRST_MM)
    final_deviation = abs(values[-1] - STATED_FINAL_MM)
    if first_deviation > VERIFY_TOLERANCE_MM or final_deviation > VERIFY_TOLERANCE_MM:
        raise SystemExit(
            "Axis calibration does not reproduce the values stated in the source text.\n"
            f"  first point {values[0]:.4f} vs stated {STATED_FIRST_MM} (deviation {first_deviation:.4f})\n"
            f"  final point {values[-1]:.4f} vs stated {STATED_FINAL_MM} (deviation {final_deviation:.4f})\n"
            f"  tolerance {VERIFY_TOLERANCE_MM}"
        )
    return first_deviation, final_deviation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    arguments = parser.parse_args()

    page, digest = render_page(arguments.pdf)
    bars = extract_bars(page)
    values = tuple(to_millimolar(top) for _, top in bars)
    first_deviation, final_deviation = verify(values)
    print(f"source PDF sha256 = {digest}")
    print(
        f"calibration verified against prose: first {values[0]:.3f} vs {STATED_FIRST_MM} "
        f"(dev {first_deviation:.3f}), final {values[-1]:.3f} vs {STATED_FINAL_MM} (dev {final_deviation:.3f})"
    )

    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    target = arguments.output_dir / "ariaeenejad_2020_figure_6_glucose.csv"
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            ["time_h", "glucose_millimolar", "digitization_uncertainty_millimolar", "bar_center_x_pixel", "bar_top_y_pixel"]
        )
        for time_h, (column, top), value in zip(SAMPLING_TIMES_H, bars, values, strict=True):
            writer.writerow([time_h, f"{value:.3f}", f"{DIGITIZATION_ERROR_MM:.3f}", f"{column:.1f}", f"{top:.1f}"])
    print(f"wrote {target}")
    print("  " + ", ".join(f"{v:.2f}" for v in values))


if __name__ == "__main__":
    main()
