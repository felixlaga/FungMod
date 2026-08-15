"""Digitize all four cellobiose time-course series in Alvarez-Gonzalez 2022 Figure S1.

The repository already contains a nine-point digitization of the Figure S1A
filled-square (20 g/L, 59.2 mg/L free enzyme) series. That series was extracted
by an earlier exact-colour marker-centre method and is committed as
``alvarez_gonzalez_2022_figure_s1a_filled_squares.csv``.

This script re-extracts that series and additionally extracts the three
previously undigitized series:

- Figure S1A open squares  (70 g/L cellobiose, panel-A enzyme loading);
- Figure S1B filled squares (20 g/L cellobiose, panel-B enzyme loading);
- Figure S1B open squares   (70 g/L cellobiose, panel-B enzyme loading).

The extraction is verified against the committed panel-A filled series before
any new file is written. If the committed series cannot be reproduced within
the declared digitization resolution, the script fails and writes nothing.

This script performs figure digitization only. It assigns no kinetic parameter,
performs no fit, and makes no claim that the extracted series constitute
independent experimental replication: all four series come from one figure in
one publication by one laboratory.

Usage::

    python scripts/digitize_alvarez_gonzalez_2022_figure_s1.py \
        --supplementary-pdf path/to/catalysts-1506763-supplementary.pdf \
        --output-dir data/experiments/literature/alvarez_gonzalez_2022_free_beta_glucosidase
"""

from __future__ import annotations

import argparse
import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from PIL import Image
from scipy import ndimage as ndi

# Provenance constants for the source document and render.
SUPPLEMENTARY_SHA256 = "212683610102dcf0a6200bdad715d2ffc95f5e7802b7f94d20f8330c34401b55"
SOURCE_PAGE_INDEX = 4  # zero-based; supplementary PDF page 5
RENDER_SCALE = 3
EXPECTED_RENDER_SIZE = (1786, 2526)

# Axis calibration, read from the rendered black plot frame. Both panels share
# the same vertical frame rows, so they share one y calibration.
ROW_AT_0_MM = 724.0
ROW_AT_240_MM = 284.0
MM_PER_ROW = 240.0 / (ROW_AT_0_MM - ROW_AT_240_MM)

# Sampling times are taken from the source Methods section 3.6.1 and assigned to
# markers in left-to-right order. They are not derived from an x-axis fit.
SAMPLING_TIMES_MIN = (0, 5, 10, 15, 20, 30, 40, 50, 60)

# Estimated digitization error: approximately one rendered pixel on the
# calibrated y axis. This is extraction resolution, not experimental uncertainty.
DIGITIZATION_ERROR_MM = 0.6

PANEL_COLUMN_BOUNDS = {"A": (365, 869), "B": (1014, 1519)}

COMMITTED_PANEL_A_FILLED_MM = (
    62.455,
    37.364,
    27.545,
    22.091,
    18.000,
    12.273,
    9.000,
    6.818,
    5.182,
)


@dataclass(frozen=True)
class Marker:
    """One extracted plot marker."""

    column: float
    row: float
    kind: str

    @property
    def millimolar(self) -> float:
        return (ROW_AT_0_MM - self.row) * MM_PER_ROW


def render_page(pdf_path: Path) -> np.ndarray:
    """Render the supplementary figure page after verifying the source bytes."""

    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    if digest != SUPPLEMENTARY_SHA256:
        raise SystemExit(
            f"Supplementary PDF SHA-256 mismatch.\n  expected {SUPPLEMENTARY_SHA256}\n  found    {digest}"
        )
    document = pdfium.PdfDocument(str(pdf_path))
    image = document[SOURCE_PAGE_INDEX].render(scale=RENDER_SCALE).to_pil().convert("RGB")
    if image.size != EXPECTED_RENDER_SIZE:
        raise SystemExit(f"Unexpected render size {image.size}; expected {EXPECTED_RENDER_SIZE}.")
    return np.array(image).astype(int)


def extract_markers(page: np.ndarray, panel: str) -> tuple[Marker, ...]:
    """Extract the filled and open square markers of one panel.

    Open-square outlines are anti-aliased on one edge, so an exact-colour mask
    leaves them open and hole filling fails. A tolerant green mask closes the
    outline; erosion then removes the plotted curve and the error bars, which
    are thinner than the markers.
    """

    red, green, blue = page[..., 0], page[..., 1], page[..., 2]
    greenish = (green > red + 20) & (green > blue + 20)
    exact_green = np.all(page == (0, 128, 0), axis=-1)

    first_column, last_column = PANEL_COLUMN_BOUNDS[panel]
    panel_mask = greenish[:, first_column : last_column + 1]
    solid = ndi.binary_erosion(ndi.binary_fill_holes(panel_mask), np.ones((5, 5)))

    labels, count = ndi.label(solid)
    markers: list[Marker] = []
    for index in range(1, count + 1):
        component = labels == index
        if int(component.sum()) < 20:  # reject residual curve fragments
            continue
        row, column = ndi.center_of_mass(component)
        absolute_column = float(column) + first_column
        centre_row, centre_column = int(round(row)), int(round(absolute_column))
        interior = exact_green[centre_row - 1 : centre_row + 2, centre_column - 1 : centre_column + 2]
        markers.append(
            Marker(
                column=absolute_column,
                row=float(row),
                kind="filled" if interior.mean() > 0.5 else "open",
            )
        )
    return tuple(markers)


def series(markers: tuple[Marker, ...], kind: str) -> tuple[Marker, ...]:
    """Return one marker series ordered by increasing time."""

    selected = tuple(sorted((m for m in markers if m.kind == kind), key=lambda m: m.column))
    if len(selected) != len(SAMPLING_TIMES_MIN):
        raise SystemExit(
            f"Expected {len(SAMPLING_TIMES_MIN)} {kind} markers but extracted {len(selected)}."
        )
    return selected


def verify_against_committed(panel_a_filled: tuple[Marker, ...]) -> float:
    """Fail unless this method reproduces the committed panel-A filled series."""

    deviations = [
        abs(marker.millimolar - committed)
        for marker, committed in zip(panel_a_filled, COMMITTED_PANEL_A_FILLED_MM, strict=True)
    ]
    worst = max(deviations)
    if worst > DIGITIZATION_ERROR_MM:
        raise SystemExit(
            "Re-extraction does not reproduce the committed panel-A filled series within "
            f"the declared {DIGITIZATION_ERROR_MM} mM digitization resolution; worst |delta| = {worst:.4f} mM."
        )
    return worst


def write_series_csv(path: Path, markers: tuple[Marker, ...]) -> None:
    """Write one digitized series with its pixel evidence."""

    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "time_min",
                "cellobiose_millimolar",
                "digitization_uncertainty_millimolar",
                "marker_center_x_pixel",
                "marker_center_y_pixel",
            ]
        )
        for time_min, marker in zip(SAMPLING_TIMES_MIN, markers, strict=True):
            writer.writerow(
                [
                    time_min,
                    f"{marker.millimolar:.3f}",
                    f"{DIGITIZATION_ERROR_MM:.3f}",
                    f"{marker.column:.1f}",
                    f"{marker.row:.1f}",
                ]
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--supplementary-pdf", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    arguments = parser.parse_args()

    page = render_page(arguments.supplementary_pdf)
    panel_a = extract_markers(page, "A")
    panel_b = extract_markers(page, "B")

    panel_a_filled = series(panel_a, "filled")
    worst = verify_against_committed(panel_a_filled)
    print(f"Reproduced committed panel-A filled series; worst |delta| = {worst:.4f} mM.")

    outputs = {
        "alvarez_gonzalez_2022_figure_s1a_open_squares.csv": series(panel_a, "open"),
        "alvarez_gonzalez_2022_figure_s1b_filled_squares.csv": series(panel_b, "filled"),
        "alvarez_gonzalez_2022_figure_s1b_open_squares.csv": series(panel_b, "open"),
    }
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    for name, markers in outputs.items():
        write_series_csv(arguments.output_dir / name, markers)
        values = ", ".join(f"{m.millimolar:.2f}" for m in markers)
        print(f"wrote {name}: {values}")


if __name__ == "__main__":
    main()
