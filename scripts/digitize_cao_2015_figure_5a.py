"""Digitize the Bgl6 and M3 cellobiose hydrolysis series in Cao 2015 Figure 5a.

This is FungMod's third literature source. It contributes a third distinct
kinetic regime: a very high initial substrate charge of 10 % w/v cellobiose
(292.1 mM) driven to near-complete conversion in 10 h by a glucose-tolerant
beta-glucosidase and an engineered mutant.

Source: Cao L-C, Wang Z-J, Ren G-H, Kong W, Li L, Xie W, Liu Y-H. Engineering a
novel glucose-tolerant beta-glucosidase as supplementation to enhance the
hydrolysis of sugarcane bagasse at high glucose concentration. Biotechnol
Biofuels. 2015;8:202. doi:10.1186/s13068-015-0383-z. CC BY 4.0.

Two limitations are recorded rather than hidden:

1. Resolution. The publisher serves this figure at only 709 x 276 px, which is
   the largest available rendition. The calibrated y scale is 1.97 px per
   percentage point, so the extraction resolution is about 0.5 percentage
   points and the declared uncertainty is set conservatively to 1.0.

2. Uncertainty type. The source plots real experimental error bars, described as
   the standard deviation of three experiments. Those error bars are NOT
   extracted here; the uncertainty recorded in the output is extraction
   resolution only. Genuine experimental uncertainty is available in the source
   and could be digitized later.

The y calibration is verified against two statements the source makes in prose,
independently of the figure: that M3 completely converted cellobiose and that
Bgl6 reached 80 % conversion. The script refuses to write unless both are
reproduced within tolerance.

Usage::

    python scripts/digitize_cao_2015_figure_5a.py \
        --figure cao_fig5.png \
        --output-dir data/experiments/literature/cao_2015_bgl6_cellobiose
"""

from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

EXPECTED_SIZE = (709, 276)
EXPECTED_SHA256 = "f875db462491e496730d1aa7bcc5fe292a558426936810fdb391789efd647d06"
SOURCE_URL = (
    "https://media.springernature.com/full/springer-static/image/"
    "art%3A10.1186%2Fs13068-015-0383-z/MediaObjects/13068_2015_383_Fig5_HTML.gif"
)

# Panel a plot interior, read from the rendered frame.
PANEL_ROWS = (14, 229)
PANEL_COLS = (43, 339)

# Axis calibration read from the rendered tick marks.
ROW_AT_0_PERCENT = 229.0
ROWS_PER_PERCENT = 1.970
COL_AT_0_HOURS = 40.0
COLS_PER_HOUR = 27.42

SAMPLING_TIMES_H = (1.0, 2.0, 3.5, 5.0, 7.0, 10.0)

# 10 % w/v cellobiose at 342.30 g/mol.
INITIAL_CELLOBIOSE_MM = 100.0 / 342.30 * 1000.0

# Values the source states in prose, used to verify the calibration.
STATED_M3_FINAL_PERCENT = 100.0
STATED_BGL6_FINAL_PERCENT = 80.0
M3_TOLERANCE = 3.0     # "completely converted"
BGL6_TOLERANCE = 2.0   # "a conversion of 80 %"

DIGITIZATION_ERROR_PERCENT = 1.0


def load_figure(path: Path) -> np.ndarray:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA256:
        raise SystemExit(f"Figure SHA-256 mismatch.\n  expected {EXPECTED_SHA256}\n  found    {digest}")
    image = Image.open(path).convert("RGB")
    if image.size != EXPECTED_SIZE:
        raise SystemExit(f"Unexpected figure size {image.size}; expected {EXPECTED_SIZE}.")
    return np.array(image).astype(int)


def extract_markers(figure: np.ndarray) -> tuple[tuple[float, float], ...]:
    """Return (column, row) centroids of the panel-a markers.

    Erosion removes the connecting curve and the error-bar whiskers, which are
    thinner than the markers at this resolution.
    """

    dark = figure.mean(axis=-1) < 128
    panel = np.zeros_like(dark)
    panel[PANEL_ROWS[0]:PANEL_ROWS[1], PANEL_COLS[0]:PANEL_COLS[1]] = (
        dark[PANEL_ROWS[0]:PANEL_ROWS[1], PANEL_COLS[0]:PANEL_COLS[1]]
    )
    labels, _ = ndi.label(ndi.binary_erosion(panel, np.ones((3, 3))))
    markers: list[tuple[float, float]] = []
    for index in range(1, int(labels.max()) + 1):
        mask = labels == index
        if int(mask.sum()) < 3:
            continue
        row, column = ndi.center_of_mass(mask)
        markers.append((float(column), float(row)))
    expected = 2 * len(SAMPLING_TIMES_H)
    if len(markers) != expected:
        raise SystemExit(f"Expected {expected} markers but found {len(markers)}.")
    return tuple(sorted(markers))


def split_series(markers: tuple[tuple[float, float], ...]) -> tuple[list[float], list[float]]:
    """Split into the upper (M3) and lower (Bgl6) series at each sampling time.

    The two series never cross in this panel, so the higher-conversion marker at
    each time is always M3.
    """

    m3: list[float] = []
    bgl6: list[float] = []
    for pair_index in range(len(SAMPLING_TIMES_H)):
        pair = markers[2 * pair_index : 2 * pair_index + 2]
        values = sorted(to_percent(row) for _, row in pair)
        bgl6.append(values[0])
        m3.append(values[1])
    return m3, bgl6


def to_percent(row: float) -> float:
    return (ROW_AT_0_PERCENT - row) / ROWS_PER_PERCENT


def verify(m3: list[float], bgl6: list[float]) -> tuple[float, float]:
    m3_deviation = abs(m3[-1] - STATED_M3_FINAL_PERCENT)
    bgl6_deviation = abs(bgl6[-1] - STATED_BGL6_FINAL_PERCENT)
    if m3_deviation > M3_TOLERANCE or bgl6_deviation > BGL6_TOLERANCE:
        raise SystemExit(
            "Calibration does not reproduce the conversions stated in the source text.\n"
            f"  M3 final   {m3[-1]:.2f} % vs stated ~{STATED_M3_FINAL_PERCENT} (deviation {m3_deviation:.2f})\n"
            f"  Bgl6 final {bgl6[-1]:.2f} % vs stated {STATED_BGL6_FINAL_PERCENT} (deviation {bgl6_deviation:.2f})"
        )
    return m3_deviation, bgl6_deviation


def write_series(path: Path, values: list[float], columns: list[float], rows: list[float]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "time_h",
                "conversion_percent",
                "cellobiose_millimolar",
                "digitization_uncertainty_percent",
                "digitization_uncertainty_millimolar",
                "marker_center_x_pixel",
                "marker_center_y_pixel",
            ]
        )
        for time_h, percent, column, row in zip(SAMPLING_TIMES_H, values, columns, rows, strict=True):
            remaining = INITIAL_CELLOBIOSE_MM * (1.0 - percent / 100.0)
            uncertainty_mM = INITIAL_CELLOBIOSE_MM * DIGITIZATION_ERROR_PERCENT / 100.0
            writer.writerow(
                [
                    time_h,
                    f"{percent:.2f}",
                    f"{remaining:.3f}",
                    f"{DIGITIZATION_ERROR_PERCENT:.2f}",
                    f"{uncertainty_mM:.3f}",
                    f"{column:.1f}",
                    f"{row:.1f}",
                ]
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--figure", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    arguments = parser.parse_args()

    figure = load_figure(arguments.figure)
    markers = extract_markers(figure)
    m3, bgl6 = split_series(markers)
    m3_deviation, bgl6_deviation = verify(m3, bgl6)
    print(f"source figure: {SOURCE_URL}")
    print(f"initial cellobiose = {INITIAL_CELLOBIOSE_MM:.3f} mM (10 % w/v at 342.30 g/mol)")
    print(
        f"calibration verified against prose: M3 {m3[-1]:.2f} % (dev {m3_deviation:.2f}), "
        f"Bgl6 {bgl6[-1]:.2f} % (dev {bgl6_deviation:.2f})"
    )

    columns = [markers[2 * i][0] for i in range(len(SAMPLING_TIMES_H))]
    m3_rows = [ROW_AT_0_PERCENT - value * ROWS_PER_PERCENT for value in m3]
    bgl6_rows = [ROW_AT_0_PERCENT - value * ROWS_PER_PERCENT for value in bgl6]

    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    write_series(arguments.output_dir / "cao_2015_figure_5a_m3.csv", m3, columns, m3_rows)
    write_series(arguments.output_dir / "cao_2015_figure_5a_bgl6.csv", bgl6, columns, bgl6_rows)
    print("  M3   conversion %: " + ", ".join(f"{v:.1f}" for v in m3))
    print("  Bgl6 conversion %: " + ", ".join(f"{v:.1f}" for v in bgl6))
    print(f"wrote 2 series to {arguments.output_dir}")


if __name__ == "__main__":
    main()
