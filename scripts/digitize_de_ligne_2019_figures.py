"""Digitize the De Ligne 2019 colony growth curves (Additional files 2 to 5).

Source: De Ligne L, Vidal-Diez de Ulzurrun G, Baetens JM, Van den Bulcke J,
Van Acker J, De Baets B (2019). Analysis of spatio-temporal fungal growth
dynamics under different environmental conditions. IMA Fungus 10:7.
doi:10.1186/s43008-019-0009-3. CC BY 4.0.

Each additional file is a one-page PDF carrying eight raster panels and two
legend images. Every panel plots one quantity (mycelial area in cm2 or the
number of hyphal tips) of one species against time in hours as the mean of
four replicates with standard-deviation bars, for four series: the four
relative humidities at one temperature, or the four temperatures at one
relative humidity. Every one of the sixteen conditions therefore appears
twice, once in a temperature panel and once in a humidity panel, drawn from
the same numbers. Both appearances are extracted independently, compared, and
merged; their disagreement is stored with every observation.

What the extractor declares and what it verifies:

- The SHA-256 of every source PDF, the number and pixel sizes of the embedded
  images, and which panel plots which condition family (transcribed from the
  panel titles) are declared below. The series colours are transcribed from
  the two legend images of each file; the extractor verifies that the legend
  rows carry the four hues in the declared order.
- Axis calibration uses the gridlines at the declared tick values, selected
  as the equally spaced subset of the grey-line candidates. The x frame is
  padded beyond zero and carries no value; the y axis starts at zero on the
  frame bottom, which is verified for every panel. The extractor refuses a
  panel whose fit residual exceeds one pixel or whose fitted y zero misses the
  frame bottom.
- Markers are filled discs. The four series are horizontally staggered by a
  fraction of an hour, so each series' stagger is estimated from its own
  markers and the hour is assigned from the de-staggered position; a marker
  whose position does not fit the stagger is excluded, never guessed.
- Markers partly hidden behind another series are located by a disc template
  that penalises background under the template, so a crescent still yields
  the disc centre; the visible fraction is recorded and the position
  uncertainty is widened to two pixels below 85 percent visibility.
- Error bars are read along the marker column through whatever hides them;
  each end counts only when its cap is visible. A bar with one visible cap is
  read one-sided, a bar shorter than the marker radius is unresolvable, and a
  bar with neither cap visible is unavailable; every case is flagged and no
  standard deviation is invented.
- Three statements the article makes in prose, independent of the figures,
  are checked before anything is written: the largest final area and tip
  count of C. puteana occur at 20 C and 75 percent RH, and for R. solani at
  20 C and 75 percent RH or 25 C and 80 percent RH; and the R. solani area at
  65 percent RH ends at the same value at 15 C and 20 C, reached earlier at
  20 C.

Usage::

    python scripts/digitize_de_ligne_2019_figures.py \
        --intake-dir data/experiments/source_intake/de_ligne_2019 \
        --output-dir data/experiments/literature/de_ligne_2019_colony_growth

    python scripts/digitize_de_ligne_2019_figures.py --check

Requires numpy, scipy, Pillow and pypdfium2.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import numpy as np
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INTAKE_DIR = ROOT / "data" / "experiments" / "source_intake" / "de_ligne_2019"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "experiments" / "literature" / "de_ligne_2019_colony_growth"
PANEL_TABLE_NAME = "digitized_panels.csv"
EXTRACTION_DATE = "2026-10-06"

SOURCE_DOI = "10.1186/s43008-019-0009-3"
SOURCE_URL = "https://imafungus.biomedcentral.com/articles/10.1186/s43008-019-0009-3"
SOURCE_CITATION = (
    "De Ligne L, Vidal-Diez de Ulzurrun G, Baetens JM, Van den Bulcke J, Van Acker J, "
    "De Baets B. Analysis of spatio-temporal fungal growth dynamics under different "
    "environmental conditions. IMA Fungus. 2019;10:7."
)
SOURCE_AUTHORS = (
    "Liselotte De Ligne",
    "Guillermo Vidal-Diez de Ulzurrun",
    "Jan M. Baetens",
    "Jan Van den Bulcke",
    "Joris Van Acker",
    "Bernard De Baets",
)

INTAKE_FILES: dict[str, str] = {
    "article.pdf": "79e1c9e0b084abd459b2ac5b5e8bf379e807a92aff65e4fded5402434f0b435e",
    "additional_file_1.pdf": "8dcb791857116292fdb2e9fe7a529bb824687e2e905917fb7b25d19b07654aee",
    "additional_file_2.pdf": "44f840a853a0888758fa866eceaaf2e45340d648ed5c88ebc5553b2121c016ac",
    "additional_file_3.pdf": "dd31afc5e8a86b182cf949754f1870ee8caa5edc168ce6010bd6dace1f91c3f3",
    "additional_file_4.pdf": "b84b44a34ffa4c6450e54ac146c107bcc0563245147c903add0c4b9d0614c208",
    "additional_file_5.pdf": "ac322f7857eb8a9d5719b7120dcd29d0aabe9fd5f264801356497c96b6c5d081",
}

HOURS = tuple(range(1, 63))
TEMPERATURES_C = (15, 20, 25, 30)
HUMIDITIES_PERCENT = (65, 70, 75, 80)
X_FIRST_LINE, X_LINE_STEP, X_LINE_COUNT = 10.0, 10.0, 6
# A marker may sit this far from its de-staggered hour (series are an hour apart,
# and the stagger between series is only 0.15 h, so colour decides the series).
STAGGER_MISFIT_MAX_H = 0.35
BAR_GAP_MAX_PX = 2  # faint bars may break for a pixel or two

# Series colours in legend order (top to bottom), transcribed from the legend
# images, and the hue intervals (degrees) that classify them.
SERIES_ORDER = ("light_blue", "navy", "orange", "green")
HUE_BINS: dict[str, tuple[float, float]] = {
    "orange": (8.0, 50.0),
    "green": (60.0, 170.0),
    "light_blue": (185.0, 225.0),
    "navy": (225.0, 360.0),  # JPEG colour bleeding carries dark navy pixels towards magenta
}
SATURATION_MIN, VALUE_MIN, CHROMA_MIN = 0.25, 0.12, 0.10  # saturated cores: the markers
TINT_SATURATION_MIN, TINT_CHROMA_MIN = 0.06, 0.03  # lighter tints: the error bars and fringes
DARK_VALUE_MAX = 0.5  # below this value a pixel counts as a dark disc pixel on a relaxed chroma floor


@dataclass(frozen=True)
class PanelSpec:
    index: int
    family: str  # "temperature" (fixed temperature, humidity series) or "humidity"
    fixed_value: int


@dataclass(frozen=True)
class FigureSpec:
    label: str
    file_name: str
    species: str
    species_tag: str
    quantity: str
    quantity_tag: str
    value_units: str
    value_column: str
    sd_column: str
    y_top: float
    y_step: float
    y_line_count: int
    image_sizes: tuple[tuple[int, int], ...]
    panels: tuple[PanelSpec, ...]
    legend_humidity_index: int
    legend_temperature_index: int
    value_decimals: int


def _panels(*items: tuple[int, str, int]) -> tuple[PanelSpec, ...]:
    return tuple(PanelSpec(index, family, value) for index, family, value in items)


FIGURES: tuple[FigureSpec, ...] = (
    FigureSpec(
        label="S2",
        file_name="additional_file_2.pdf",
        species="Coniophora puteana MUCL 11662",
        species_tag="c_puteana",
        quantity="mycelial area",
        quantity_tag="area",
        value_units="centimeter ** 2",
        value_column="mycelial_area_cm2",
        sd_column="mycelial_area_sd_cm2",
        y_top=10.0,
        y_step=2.0,
        y_line_count=5,
        image_sizes=(
            (1000, 800), (1000, 800), (1000, 800), (1000, 800), (1000, 800),
            (1000, 800), (278, 332), (1000, 800), (1000, 758), (278, 308),
        ),
        panels=_panels(
            (0, "humidity", 80), (1, "humidity", 75), (2, "humidity", 65), (3, "temperature", 15),
            (4, "temperature", 20), (5, "temperature", 25), (7, "temperature", 30), (8, "humidity", 70),
        ),
        legend_humidity_index=6,
        legend_temperature_index=9,
        value_decimals=3,
    ),
    FigureSpec(
        label="S3",
        file_name="additional_file_3.pdf",
        species="Rhizoctonia solani AG4-HG-I S010-1",
        species_tag="r_solani",
        quantity="mycelial area",
        quantity_tag="area",
        value_units="centimeter ** 2",
        value_column="mycelial_area_cm2",
        sd_column="mycelial_area_sd_cm2",
        y_top=15.0,
        y_step=5.0,
        y_line_count=3,
        image_sizes=(
            (613, 465), (613, 465), (613, 466), (614, 466), (614, 466),
            (614, 466), (614, 466), (614, 466), (131, 157), (142, 157),
        ),
        panels=_panels(
            (0, "temperature", 15), (1, "temperature", 20), (2, "temperature", 25), (3, "humidity", 80),
            (4, "humidity", 65), (5, "humidity", 70), (6, "humidity", 75), (7, "temperature", 30),
        ),
        legend_humidity_index=8,
        legend_temperature_index=9,
        value_decimals=3,
    ),
    FigureSpec(
        label="S4",
        file_name="additional_file_4.pdf",
        species="Coniophora puteana MUCL 11662",
        species_tag="c_puteana",
        quantity="number of hyphal tips",
        quantity_tag="tips",
        value_units="dimensionless",
        value_column="tip_count",
        sd_column="tip_count_sd",
        y_top=2000.0,
        y_step=500.0,
        y_line_count=4,
        image_sizes=(
            (645, 490), (645, 490), (645, 490), (645, 465), (645, 490),
            (645, 490), (645, 464), (645, 494), (131, 157), (142, 157),
        ),
        panels=_panels(
            (0, "temperature", 30), (1, "humidity", 65), (2, "humidity", 70), (3, "humidity", 75),
            (4, "temperature", 15), (5, "temperature", 25), (6, "temperature", 20), (7, "humidity", 80),
        ),
        legend_humidity_index=8,
        legend_temperature_index=9,
        value_decimals=1,
    ),
    FigureSpec(
        label="S5",
        file_name="additional_file_5.pdf",
        species="Rhizoctonia solani AG4-HG-I S010-1",
        species_tag="r_solani",
        quantity="number of hyphal tips",
        quantity_tag="tips",
        value_units="dimensionless",
        value_column="tip_count",
        sd_column="tip_count_sd",
        y_top=8000.0,
        y_step=2000.0,
        y_line_count=4,
        image_sizes=(
            (645, 489), (645, 489), (645, 461), (645, 489), (645, 489),
            (645, 489), (645, 464), (645, 489), (131, 157), (142, 157),
        ),
        panels=_panels(
            (0, "temperature", 30), (1, "temperature", 25), (2, "temperature", 20), (3, "temperature", 15),
            (4, "humidity", 80), (5, "humidity", 75), (6, "humidity", 70), (7, "humidity", 65),
        ),
        legend_humidity_index=8,
        legend_temperature_index=9,
        value_decimals=1,
    ),
)

# Statements the article makes in prose, used as calibration-independent checks
# of the panel mapping: the conditions with the largest area and tip count at
# 62 h ("optimal growth conditions ... defined as the conditions where the
# largest area and highest number of tips were reached after 62 h").
STATED_OPTIMA: dict[str, tuple[tuple[int, int], ...]] = {
    "c_puteana": ((20, 75),),
    "r_solani": ((20, 75), (25, 80)),
}


class DigitizationError(RuntimeError):
    """Raised when the source files or the extraction fail a declared check."""


# --------------------------------------------------------------------------- #
# Source files
# --------------------------------------------------------------------------- #


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_intake(intake_dir: Path) -> None:
    for name, expected in INTAKE_FILES.items():
        path = intake_dir / name
        if not path.exists():
            raise DigitizationError(f"Missing source file {path}.")
        found = sha256_of(path)
        if found != expected:
            raise DigitizationError(
                f"SHA-256 mismatch for {path.name}: expected {expected}, found {found}."
            )


def extract_images(pdf_path: Path) -> list[np.ndarray]:
    """Return the embedded raster images of the single page, in object order."""

    import pypdfium2 as pdfium
    import pypdfium2.raw as pdfium_c

    document = pdfium.PdfDocument(str(pdf_path))
    if len(document) != 1:
        raise DigitizationError(f"{pdf_path.name} has {len(document)} pages; expected one.")
    page = document[0]
    images: list[np.ndarray] = []
    for item in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE]):
        if not isinstance(item, pdfium.PdfImage):
            raise DigitizationError(f"{pdf_path.name}: unexpected page object {type(item).__name__}.")
        bitmap = item.get_bitmap()
        images.append(np.asarray(bitmap.to_pil().convert("RGB"), dtype=np.uint8))
    return images


def pixel_digest(image: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(image).tobytes()).hexdigest()


# --------------------------------------------------------------------------- #
# Axis calibration
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class AxisCalibration:
    slope: float  # pixels per value unit
    intercept: float  # pixel at value zero
    residual: float
    line_count: int

    def value_at(self, pixel: float) -> float:
        return (pixel - self.intercept) / self.slope

    def pixel_at(self, value: float) -> float:
        return self.intercept + self.slope * value


def _groups(hits: np.ndarray) -> list[np.ndarray]:
    if hits.size == 0:
        return []
    return [g for g in np.split(hits, np.flatnonzero(np.diff(hits) > 1) + 1) if g.size]


def frame_lines(image: np.ndarray) -> tuple[float, float, float, float]:
    """Centre rows of the top and bottom frame lines and columns of the sides.

    The frame is a solid line that is dark in the large panels and light grey in
    the small ones, so it is found as the outermost rows that are not white
    across most of the width, and the outermost columns that are not white
    across most of the height between those rows. Dotted gridlines fall short
    of the coverage threshold.
    """

    dim = image.mean(axis=-1) < 230.0
    rows = _groups(np.flatnonzero(dim.mean(axis=1) > 0.8))
    if len(rows) < 2:
        raise DigitizationError("Could not find the top and bottom frame lines.")
    top = float(rows[0].mean())
    # A dark border at the image edge can masquerade as the bottom line; the
    # true bottom is the lowest row group between which the side lines are solid.
    for candidate in reversed(rows[1:]):
        bottom = float(candidate.mean())
        between = dim[int(round(top)) : int(round(bottom)) + 1]
        cols = _groups(np.flatnonzero(between.mean(axis=0) > 0.8))
        if len(cols) >= 2:
            return top, bottom, float(cols[0].mean()), float(cols[-1].mean())
    raise DigitizationError("Could not find the left and right frame lines.")


def gridline_candidates(
    image: np.ndarray, frame: tuple[float, float, float, float], axis: str
) -> tuple[np.ndarray, np.ndarray]:
    """Candidate gridline centres along one axis with their grey coverage.

    A gridline is neutral grey (dotted in the large panels, a faint solid line
    in the small ones). The frame is neutral grey too, and its chroma spread
    (JPEG noise in some panels) sets how neutral a gridline pixel must be and
    how little tint marks a pixel as belonging to a series. Where the series
    cover a line, only the uncovered pixels are judged, so a line hidden behind
    most of the data is still found as long as a tenth of it is free. Faint
    error bars can still pass this test, so the candidates are resolved into
    the equally spaced pattern by :func:`fit_line_pattern`.
    """

    top, bottom, left, right = (int(round(v)) for v in frame)
    gray = image.mean(axis=-1)
    chroma = image.max(axis=-1).astype(int) - image.min(axis=-1).astype(int)
    frame_chroma = np.concatenate((chroma[top, left:right], chroma[bottom, left:right]))
    noise = int(np.percentile(frame_chroma, 95))
    grey = (gray > 150.0) & (gray < 253.0) & (chroma <= noise + 1)
    covered = np.asarray(ndi.binary_dilation(chroma > noise + 1, structure=np.ones((5, 5), dtype=bool)), dtype=bool)
    rows, cols = slice(top + 5, bottom - 4), slice(left + 5, right - 4)
    grey_interior = grey[rows, cols]
    free_interior = ~covered[rows, cols]
    if axis == "y":
        grey_interior, free_interior = grey_interior.T, free_interior.T
    offset = left + 5 if axis == "x" else top + 5
    free_count = free_interior.sum(axis=0)
    grey_free = (grey_interior & free_interior).sum(axis=0)
    fraction = np.where(free_count > 0, grey_free / np.maximum(free_count, 1), 0.0)
    hits = np.flatnonzero((fraction > 0.3) & (free_count >= 0.1 * free_interior.shape[0]))
    # Contiguous rows or columns only: faint resampling echoes two pixels from a
    # line stay separate candidates and lose to the line in the pattern fit.
    groups = _groups(hits)
    positions = np.array([np.average(g, weights=fraction[g]) + offset for g in groups])
    weights = np.array([fraction[g].mean() for g in groups])
    return positions, weights


def fit_line_pattern(
    positions: np.ndarray,
    weights: np.ndarray,
    expected_lines: int,
    minimum_lines: int,
    minimum_spacing: float,
    name: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Pick the equally spaced subset of the candidates with the most members.

    Every pair of candidates proposes a spacing (or a multiple of it); the
    pattern anchored at the first candidate with the most inliers within one
    pixel wins, ties going to the heavier (greyer) set. Returns the inlier
    positions and their integer indices from the first inlier.
    """

    order = np.argsort(positions)
    positions, weights = positions[order], weights[order]
    best: tuple[int, float, np.ndarray, np.ndarray] | None = None
    for i in range(positions.size):
        for j in range(i + 1, positions.size):
            for k in range(1, expected_lines):
                spacing = (positions[j] - positions[i]) / k
                if spacing < minimum_spacing:
                    continue
                index = np.round((positions - positions[i]) / spacing).astype(int)
                fitted = positions[i] + index * spacing
                inlier = (np.abs(fitted - positions) <= 1.0) & (index >= 0) & (index <= expected_lines - 1)
                # One inlier per index: keep the heaviest.
                chosen: dict[int, int] = {}
                for m in np.flatnonzero(inlier):
                    current = chosen.get(int(index[m]))
                    if current is None or weights[m] > weights[current]:
                        chosen[int(index[m])] = int(m)
                members = np.array(sorted(chosen.values()))
                count, weight = members.size, float(weights[members].sum())
                if best is None or (count, weight) > (best[0], best[1]):
                    best = (count, weight, positions[members], index[members])
    if best is None or best[0] < minimum_lines:
        found = 0 if best is None else best[0]
        raise DigitizationError(f"{name}: candidates at {np.round(positions, 1)} give {found} equally spaced lines; need {minimum_lines}.")
    return best[2], best[3] - best[3].min()


def calibrate_axis(
    lines: np.ndarray,
    index: np.ndarray,
    first_value: float,
    step: float,
    name: str,
) -> AxisCalibration:
    """Fit pixel = intercept + slope * value through the gridlines.

    The first inlier carries ``first_value`` and every later one is ``index``
    steps further. A fit residual above one pixel refuses the panel.
    """

    values = first_value + index * step
    slope, intercept = np.polyfit(values, lines, 1)
    residual = float(np.abs(np.polyval([slope, intercept], values) - lines).max())
    if residual > 1.0:
        raise DigitizationError(f"{name}: calibration residual {residual:.2f} px exceeds one pixel.")
    return AxisCalibration(float(slope), float(intercept), residual, int(lines.size))


def calibrate_panel_axes(
    image: np.ndarray, frame: tuple[float, float, float, float], figure: FigureSpec, name: str
) -> tuple[AxisCalibration, AxisCalibration, float]:
    """Both axes of a panel, with the frame bottom verified as the y zero.

    The x axis is padded beyond zero, so only its gridlines carry values and the
    leftmost line is the first declared tick. The y axis starts at zero on the
    frame bottom in every panel of these figures, which is used as a check: if
    the top line assignment puts zero elsewhere, the top gridline coincides with
    the frame and the first visible line is one step lower. Returns the two
    calibrations and the offset between the fitted y zero and the frame bottom.
    """

    top, bottom, left, right = frame
    x_candidates, x_weights = gridline_candidates(image, frame, "x")
    x_lines, x_index = fit_line_pattern(
        x_candidates, x_weights, X_LINE_COUNT, 4, 0.5 * (right - left) / (X_LINE_COUNT + 1), f"{name} x axis"
    )
    x_axis = calibrate_axis(x_lines, x_index, X_FIRST_LINE, X_LINE_STEP, f"{name} x axis")
    y_candidates, y_weights = gridline_candidates(image, frame, "y")
    # Two gridlines suffice for y because the frame bottom supplies the zero check.
    y_lines, y_index = fit_line_pattern(
        y_candidates, y_weights, figure.y_line_count, 2,
        0.5 * (bottom - top) / (figure.y_line_count + 1), f"{name} y axis",
    )
    offsets: list[float] = []
    for first_value in (figure.y_top, figure.y_top - figure.y_step):
        y_axis = calibrate_axis(y_lines, y_index, first_value, -figure.y_step, f"{name} y axis")
        offset = y_axis.pixel_at(0.0) - bottom
        offsets.append(offset)
        if abs(offset) <= 2.5:
            return x_axis, y_axis, offset
    raise DigitizationError(
        f"{name} y axis: the fitted zero misses the frame bottom by {offsets[0]:.1f} px "
        f"(or {offsets[1]:.1f} px with the top line on the frame)."
    )


# --------------------------------------------------------------------------- #
# Colour classification and marker detection
# --------------------------------------------------------------------------- #


def hue_masks(
    image: np.ndarray,
    *,
    saturation_min: float = SATURATION_MIN,
    chroma_min: float = CHROMA_MIN,
) -> dict[str, np.ndarray]:
    """Pixels of each series colour, by hue, above the given saturation and chroma."""

    rgb = image.astype(float) / 255.0
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(axis=-1), rgb.min(axis=-1)
    chroma = mx - mn
    d = np.maximum(chroma, 1e-9)
    hue = np.where(
        mx == r,
        (60.0 * ((g - b) / d)) % 360.0,
        np.where(mx == g, 60.0 * ((b - r) / d) + 120.0, 60.0 * ((r - g) / d) + 240.0),
    )
    saturation = np.where(mx > 0, chroma / np.maximum(mx, 1e-9), 0.0)
    coloured = (saturation > saturation_min) & (mx > VALUE_MIN) & (chroma > chroma_min)
    # Dark pixels carry little chroma by construction; JPEG smearing of the dark
    # navy and green discs lowers it further, so they are admitted on a relaxed
    # chroma floor scaled to the requested one.
    dark = (mx < DARK_VALUE_MAX) & (saturation > 0.6 * saturation_min) & (chroma > 0.6 * chroma_min)
    coloured |= dark
    return {name: coloured & (hue >= lo) & (hue < hi) for name, (lo, hi) in HUE_BINS.items()}


def interior_masks(
    image: np.ndarray,
    frame: tuple[float, float, float, float],
    *,
    saturation_min: float = SATURATION_MIN,
    chroma_min: float = CHROMA_MIN,
) -> dict[str, np.ndarray]:
    top, bottom, left, right = (int(round(v)) for v in frame)
    masks = hue_masks(image, saturation_min=saturation_min, chroma_min=chroma_min)
    keep = np.zeros(image.shape[:2], dtype=bool)
    keep[top + 2 : bottom - 1, left + 2 : right - 1] = True
    return {name: mask & keep for name, mask in masks.items()}


def legend_order(image: np.ndarray) -> tuple[str, ...]:
    """Series colours of a legend image from top to bottom."""

    masks = hue_masks(image)
    rows: list[tuple[float, str]] = []
    # The legend lines span a good part of the width; the anti-aliased fringes of
    # the black labels contribute only a few coloured pixels per row.
    minimum = max(10, int(0.12 * image.shape[1]))
    for name, mask in masks.items():
        counts = mask.sum(axis=1)
        hit = np.flatnonzero(counts >= minimum)
        if hit.size:
            rows.append((float(hit.mean()), name))
    return tuple(name for _, name in sorted(rows))


def marker_radius(masks: Mapping[str, np.ndarray]) -> float:
    """Disc radius shared by the four series, from the unoccluded markers."""

    diameters: list[float] = []
    for mask in masks.values():
        opened = ndi.binary_opening(mask, structure=np.ones((1, 3), dtype=bool))
        labels, count = cast(tuple[np.ndarray, int], ndi.label(opened))
        if count == 0:
            continue
        slices = ndi.find_objects(labels)
        for region in slices:
            if region is None:
                continue
            height = region[0].stop - region[0].start
            width = region[1].stop - region[1].start
            if abs(height - width) <= 1 and height >= 4:
                diameters.append(0.5 * (height + width))
    if len(diameters) < 20:
        raise DigitizationError(f"Only {len(diameters)} round markers found; cannot estimate the marker radius.")
    return float(np.median(diameters)) / 2.0


@dataclass(frozen=True)
class Marker:
    column: float
    row: float
    visible_fraction: float
    position_uncertainty_px: float


def detect_markers(own: np.ndarray, background: np.ndarray, radius: float) -> list[Marker]:
    r = int(np.ceil(radius))
    yy, xx = np.mgrid[-r : r + 1, -r : r + 1]
    disc = ((yy**2 + xx**2) <= radius**2).astype(float)
    area = float(disc.sum())
    own_score = ndi.correlate(own.astype(float), disc, mode="constant")
    background_score = ndi.correlate(background.astype(float), disc, mode="constant")
    score = own_score - background_score
    peaks = (score >= ndi.maximum_filter(score, size=2 * r + 1)) & (score >= 0.35 * area) & (own_score >= 0.3 * area)
    labels, count = cast(tuple[np.ndarray, int], ndi.label(peaks))
    markers: list[Marker] = []
    for index in range(1, count + 1):
        rows, cols = np.nonzero(labels == index)
        row, col = float(rows.mean()), float(cols.mean())
        visible = float(own_score[int(round(row)), int(round(col))] / area)
        if visible >= 0.85:
            # Unoccluded: refine with the centroid of the series pixels under the disc.
            r0, c0 = int(round(row)), int(round(col))
            top, left = max(r0 - r, 0), max(c0 - r, 0)
            window = own[top : r0 + r + 1, left : c0 + r + 1]
            rows_local, cols_local = np.nonzero(window)
            rows_abs, cols_abs = rows_local + top, cols_local + left
            inside = (rows_abs - r0) ** 2 + (cols_abs - c0) ** 2 <= radius**2
            if inside.any():
                row = float(rows_abs[inside].mean())
                col = float(cols_abs[inside].mean())
            uncertainty = 1.0
        else:
            uncertainty = 2.0
        markers.append(Marker(col, row, visible, uncertainty))
    return markers


@dataclass(frozen=True)
class BarSide:
    end_row: int
    capped: bool
    within_marker: bool


def bar_side(own: np.ndarray, others: np.ndarray, column: int, centre_row: int, radius: float, direction: int) -> BarSide:
    """Follow one half of an error bar from the marker centre.

    The walk continues through pixels of this series or of any other series
    (which may hide the bar) and across gaps of at most ``BAR_GAP_MAX_PX``
    background pixels, and stops at the last pixel of this series. That end
    counts as a cap when at least three series pixels sit on its row and it
    lies beyond the marker disc.
    """

    rows = own.shape[0]
    # In the small panels the series are staggered by little more than a pixel,
    # so the band is the bar column alone; the large panels afford a pixel each side.
    half = 1 if radius >= 3.5 else 0
    c0, c1 = max(column - half, 0), column + half + 1
    row = centre_row
    last_own = centre_row
    gap = 0
    while True:
        nxt = row + direction
        if nxt < 0 or nxt >= rows:
            break
        is_own = bool(own[nxt, c0:c1].any())
        is_other = bool(others[nxt, c0:c1].any())
        if is_own or is_other:
            gap = 0
            if is_own:
                last_own = nxt
        else:
            gap += 1
            if gap > BAR_GAP_MAX_PX:
                break
        row = nxt
    distance = abs(last_own - centre_row)
    within_marker = distance <= radius + 1.0
    cap_width = int(own[last_own, max(column - 2, 0) : column + 3].sum())
    capped = (not within_marker) and cap_width >= 3
    return BarSide(last_own, capped, within_marker)


# --------------------------------------------------------------------------- #
# Panel extraction
# --------------------------------------------------------------------------- #


@dataclass
class PanelReading:
    figure: str
    panel_index: int
    family: str
    fixed_value: int
    series_colour: str
    temperature_c: int
    humidity_percent: int
    hour: int
    marker_x_px: float
    marker_y_px: float
    marker_visible_fraction: float
    position_uncertainty_px: float
    value: float
    digitization_uncertainty: float
    sd: float | None
    bar_top_px: int
    bar_bottom_px: int
    top_capped: bool
    bottom_capped: bool
    flags: tuple[str, ...]


@dataclass
class PanelCalibration:
    figure: str
    panel_index: int
    family: str
    fixed_value: int
    width: int
    height: int
    pixel_digest: str
    x: AxisCalibration
    y: AxisCalibration
    marker_radius_px: float
    y_zero_offset_px: float
    stagger_hours: dict[str, float] = field(default_factory=dict)
    series_counts: dict[str, int] = field(default_factory=dict)
    excluded: list[dict[str, Any]] = field(default_factory=list)


def series_conditions(spec: PanelSpec, colour: str) -> tuple[int, int]:
    position = SERIES_ORDER.index(colour)
    if spec.family == "temperature":
        return spec.fixed_value, HUMIDITIES_PERCENT[position]
    return TEMPERATURES_C[position], spec.fixed_value


def digitize_panel(figure: FigureSpec, spec: PanelSpec, image: np.ndarray) -> tuple[PanelCalibration, list[PanelReading]]:
    name = f"{figure.label} panel {spec.index}"
    try:
        frame = frame_lines(image)
    except DigitizationError as error:
        raise DigitizationError(f"{name}: {error}") from error
    x_axis, y_axis, zero_offset = calibrate_panel_axes(image, frame, figure, name)
    if x_axis.slope <= 0 or y_axis.slope >= 0:
        raise DigitizationError(f"{figure.label} panel {spec.index}: axis orientation is wrong.")
    masks = interior_masks(image, frame)
    tints = interior_masks(image, frame, saturation_min=TINT_SATURATION_MIN, chroma_min=TINT_CHROMA_MIN)
    radius = marker_radius(masks)
    union = np.zeros(image.shape[:2], dtype=bool)
    for mask in tints.values():
        union |= mask
    background = ~np.asarray(ndi.binary_dilation(union, structure=np.ones((3, 3), dtype=bool)), dtype=bool)
    calibration = PanelCalibration(
        figure.label, spec.index, spec.family, spec.fixed_value, image.shape[1], image.shape[0],
        pixel_digest(image), x_axis, y_axis, radius, zero_offset,
    )
    readings: list[PanelReading] = []
    for colour in SERIES_ORDER:
        own = masks[colour]
        own_tint = tints[colour]
        others = np.zeros_like(own)
        for name, mask in tints.items():
            if name != colour:
                others |= mask
        markers = detect_markers(own, background, radius)
        if not markers:
            raise DigitizationError(f"{figure.label} panel {spec.index}: no {colour} markers found.")
        times = np.array([x_axis.value_at(m.column) for m in markers])
        fractional = times - np.round(times)
        stagger = float(np.median(fractional))
        calibration.stagger_hours[colour] = stagger
        temperature, humidity = series_conditions(spec, colour)
        by_hour: dict[int, tuple[Marker, float]] = {}
        for marker, t in zip(markers, times, strict=True):
            shifted = t - stagger
            hour = int(round(shifted))
            misfit = abs(shifted - hour)
            if misfit > STAGGER_MISFIT_MAX_H or hour not in HOURS:
                calibration.excluded.append(
                    {"series": colour, "time_h": round(float(t), 3), "reason": "marker position does not fit the series stagger"}
                )
                continue
            previous = by_hour.get(hour)
            if previous is None or marker.visible_fraction > previous[0].visible_fraction:
                if previous is not None:
                    calibration.excluded.append(
                        {"series": colour, "time_h": hour, "reason": "duplicate detection at the same hour; the more visible marker was kept"}
                    )
                by_hour[hour] = (marker, misfit)
        calibration.series_counts[colour] = len(by_hour)
        for hour in sorted(by_hour):
            marker, _misfit = by_hour[hour]
            column, row = int(round(marker.column)), int(round(marker.row))
            upper = bar_side(own_tint, others, column, row, radius, -1)
            lower = bar_side(own_tint, others, column, row, radius, +1)
            flags: list[str] = []
            if marker.visible_fraction < 0.85:
                flags.append("marker_partially_hidden")
            up = row - upper.end_row
            down = lower.end_row - row
            sd: float | None
            if upper.capped and lower.capped:
                if abs(up - down) > 2:
                    flags.append("sd_asymmetric_bar")
                sd_px = 0.5 * (up + down)
                sd = sd_px / abs(y_axis.slope)
            elif upper.capped or lower.capped:
                flags.append("sd_one_sided")
                sd = (up if upper.capped else down) / abs(y_axis.slope)
            elif upper.within_marker and lower.within_marker:
                flags.append("sd_below_marker_radius")
                sd = None
            else:
                flags.append("sd_unavailable")
                sd = None
            readings.append(
                PanelReading(
                    figure=figure.label,
                    panel_index=spec.index,
                    family=spec.family,
                    fixed_value=spec.fixed_value,
                    series_colour=colour,
                    temperature_c=temperature,
                    humidity_percent=humidity,
                    hour=hour,
                    marker_x_px=round(marker.column, 2),
                    marker_y_px=round(marker.row, 2),
                    marker_visible_fraction=round(marker.visible_fraction, 3),
                    position_uncertainty_px=marker.position_uncertainty_px,
                    value=y_axis.value_at(marker.row),
                    digitization_uncertainty=marker.position_uncertainty_px / abs(y_axis.slope),
                    sd=sd,
                    bar_top_px=upper.end_row,
                    bar_bottom_px=lower.end_row,
                    top_capped=upper.capped,
                    bottom_capped=lower.capped,
                    flags=tuple(flags),
                )
            )
    return calibration, readings


# --------------------------------------------------------------------------- #
# Merging the two appearances of every condition
# --------------------------------------------------------------------------- #


@dataclass
class Observation:
    time_h: int
    value: float
    sd: float | None
    panel_difference: float | None
    digitization_uncertainty: float
    temperature_panel_value: float | None
    humidity_panel_value: float | None
    flags: tuple[str, ...]


ConditionKey = tuple[str, str, int, int]  # species_tag, quantity_tag, temperature, humidity


def merge_readings(
    figure: FigureSpec,
    readings: Sequence[PanelReading],
    calibrations: Sequence[PanelCalibration],
) -> tuple[dict[ConditionKey, list[Observation]], dict[ConditionKey, list[dict[str, Any]]]]:
    coarsest = max(1.0 / abs(c.y.slope) for c in calibrations)
    tolerance = 3.0 * coarsest
    grouped: dict[tuple[int, int, int], dict[str, PanelReading]] = {}
    for reading in readings:
        grouped.setdefault((reading.temperature_c, reading.humidity_percent, reading.hour), {})[reading.family] = reading
    observations: dict[ConditionKey, list[Observation]] = {}
    excluded: dict[ConditionKey, list[dict[str, Any]]] = {}
    for temperature in TEMPERATURES_C:
        for humidity in HUMIDITIES_PERCENT:
            key: ConditionKey = (figure.species_tag, figure.quantity_tag, temperature, humidity)
            rows: list[Observation] = []
            missing: list[dict[str, Any]] = []
            for hour in HOURS:
                pair = grouped.get((temperature, humidity, hour), {})
                t_read = pair.get("temperature")
                h_read = pair.get("humidity")
                if t_read is None and h_read is None:
                    missing.append({"time_h": hour, "reason": "marker not found in either panel"})
                    continue
                flags: list[str] = []
                present = [r for r in (t_read, h_read) if r is not None]
                for r in present:
                    flags.extend(r.flags)
                if t_read is None or h_read is None:
                    flags.append("single_panel")
                    difference = None
                else:
                    difference = t_read.value - h_read.value
                    if abs(difference) > tolerance:
                        flags.append("panel_disagreement")
                value = float(np.mean([r.value for r in present]))
                sds = [r.sd for r in present if r.sd is not None]
                sd = float(np.mean(sds)) if sds else None
                if sd is not None and len(sds) == 1 and len(present) == 2:
                    flags.append("sd_from_one_panel")
                rows.append(
                    Observation(
                        time_h=hour,
                        value=value,
                        sd=sd,
                        panel_difference=difference,
                        digitization_uncertainty=max(r.digitization_uncertainty for r in present),
                        temperature_panel_value=None if t_read is None else t_read.value,
                        humidity_panel_value=None if h_read is None else h_read.value,
                        flags=tuple(dict.fromkeys(flags)),
                    )
                )
            observations[key] = rows
            excluded[key] = missing
    return observations, excluded


STATED_EQUAL_FINAL_AREA = ("r_solani", (15, 65), (20, 65))
STATED_EQUAL_TOLERANCE_FRACTION = 0.05


def verify_stated_equal_final_area(observations: Mapping[ConditionKey, Sequence[Observation]]) -> dict[str, float]:
    """Check the article's statement that the R. solani area at 65 percent RH reaches the same value at 15 and 20 C.

    "For an RH of 65 percent the mycelial area of R. solani after 62 h was the same at
    15 C and 20 C, but at 20 C it reached this value earlier" (Discussion). The two
    final areas must agree within five percent of their mean, and the 20 C curve must
    reach half of the final value earlier than the 15 C curve.
    """

    species, first, second = STATED_EQUAL_FINAL_AREA
    series = {
        cond: observations[(species, "area", cond[0], cond[1])] for cond in (first, second)
    }
    finals = {cond: [row for row in rows if row.time_h >= 58][-1].value for cond, rows in series.items()}
    mean = 0.5 * (finals[first] + finals[second])
    if abs(finals[first] - finals[second]) > STATED_EQUAL_TOLERANCE_FRACTION * mean:
        raise DigitizationError(
            f"{species} area at 65 percent RH after 62 h: {finals[first]:.3f} at {first[0]} C and "
            f"{finals[second]:.3f} at {second[0]} C; the article states they are the same."
        )
    half_times = {
        cond: next(row.time_h for row in rows if row.value >= 0.5 * finals[cond]) for cond, rows in series.items()
    }
    if not half_times[second] < half_times[first]:
        raise DigitizationError(
            f"{species} area at 65 percent RH reaches half its final value at {half_times[second]} h ({second[0]} C) "
            f"and {half_times[first]} h ({first[0]} C); the article states the {second[0]} C curve is earlier."
        )
    return {
        f"final_area_{first[0]}c": round(finals[first], 3),
        f"final_area_{second[0]}c": round(finals[second], 3),
        f"half_time_{first[0]}c_h": half_times[first],
        f"half_time_{second[0]}c_h": half_times[second],
    }


def verify_stated_optima(observations: Mapping[ConditionKey, Sequence[Observation]]) -> dict[str, dict[str, list[int]]]:
    """Check the article's prose statement of the optimal conditions at 62 h."""

    report: dict[str, dict[str, list[int]]] = {}
    for species_tag, allowed in STATED_OPTIMA.items():
        for quantity_tag in ("area", "tips"):
            finals: dict[tuple[int, int], float] = {}
            for (s, q, t, h), rows in observations.items():
                if s != species_tag or q != quantity_tag:
                    continue
                # The last reading at or after 58 h stands in where hour 62 itself is missing.
                late = [row for row in rows if row.time_h >= 58]
                if late:
                    finals[(t, h)] = late[-1].value
            if len(finals) != 16:
                raise DigitizationError(
                    f"{species_tag} {quantity_tag}: {len(finals)} conditions have a reading at 58 h or later; expected 16."
                )
            best = max(finals, key=lambda k: finals[k])
            if best not in allowed:
                raise DigitizationError(
                    f"{species_tag} {quantity_tag}: largest 62 h value at {best}, but the article states {allowed}."
                )
            report.setdefault(species_tag, {})[quantity_tag] = list(best)
    return report


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #


def _fmt(value: float | None, decimals: int) -> str:
    return "" if value is None else f"{value:.{decimals}f}"


def condition_file_name(figure: FigureSpec, temperature: int, humidity: int) -> str:
    return f"de_ligne_2019_{figure.species_tag}_{figure.quantity_tag}_{temperature}c_{humidity}rh.csv"


def dataset_file_name(figure: FigureSpec) -> str:
    return f"de_ligne_2019_{figure.species_tag}_{figure.quantity_tag}.yml"


def csv_columns(figure: FigureSpec) -> list[str]:
    unit = "_cm2" if figure.quantity_tag == "area" else ""
    return [
        "time_h",
        figure.value_column,
        figure.sd_column,
        f"panel_difference{unit}",
        f"digitization_uncertainty{unit}",
        f"temperature_panel_value{unit}",
        f"humidity_panel_value{unit}",
        "flags",
    ]


def render_condition_csv(figure: FigureSpec, rows: Sequence[Observation]) -> str:
    decimals = figure.value_decimals
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(csv_columns(figure))
    for row in rows:
        writer.writerow(
            [
                row.time_h,
                _fmt(row.value, decimals),
                _fmt(row.sd, decimals),
                _fmt(row.panel_difference, decimals),
                _fmt(row.digitization_uncertainty, decimals),
                _fmt(row.temperature_panel_value, decimals),
                _fmt(row.humidity_panel_value, decimals),
                ";".join(row.flags),
            ]
        )
    return buffer.getvalue()


PANEL_TABLE_COLUMNS = [
    "figure", "panel_index", "panel_family", "panel_fixed_value", "series_colour", "temperature_c",
    "relative_humidity_percent", "time_h", "marker_x_px", "marker_y_px", "marker_visible_fraction",
    "position_uncertainty_px", "value", "digitization_uncertainty", "sd", "bar_top_px", "bar_bottom_px",
    "top_cap_visible", "bottom_cap_visible", "flags",
]


def render_panel_table(readings: Iterable[tuple[FigureSpec, PanelReading]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(PANEL_TABLE_COLUMNS)
    for figure, r in readings:
        d = figure.value_decimals
        writer.writerow(
            [
                r.figure, r.panel_index, r.family, r.fixed_value, r.series_colour, r.temperature_c,
                r.humidity_percent, r.hour, f"{r.marker_x_px:.2f}", f"{r.marker_y_px:.2f}",
                f"{r.marker_visible_fraction:.3f}", f"{r.position_uncertainty_px:.1f}", _fmt(r.value, d),
                _fmt(r.digitization_uncertainty, d), _fmt(r.sd, d), r.bar_top_px, r.bar_bottom_px,
                str(r.top_capped).lower(), str(r.bottom_capped).lower(), ";".join(r.flags),
            ]
        )
    return buffer.getvalue()


FLAG_GLOSSARY: dict[str, str] = {
    "marker_partially_hidden": "less than 85 percent of the marker disc is visible behind another series; position uncertainty widened to two pixels",
    "sd_asymmetric_bar": "both bar caps visible but their distances from the marker centre differ by more than two pixels; the mean half-length is stored",
    "sd_one_sided": "only one bar cap is visible; the standard deviation is that half-length",
    "sd_below_marker_radius": "the bar does not reach beyond the marker disc, so the standard deviation is smaller than the marker radius and is left empty",
    "sd_unavailable": "neither bar cap is visible; the standard deviation is left empty",
    "single_panel": "the marker was found in only one of the two panels that plot this condition",
    "panel_disagreement": "the two panels differ by more than three pixels of the coarser panel; the mean is stored and the difference is recorded",
    "sd_from_one_panel": "the standard deviation could be read in only one of the two panels",
}


def _software_versions() -> str:
    from importlib.metadata import version

    parts = [f"numpy {np.__version__}", f"scipy {version('scipy')}", f"Pillow {version('pillow')}", f"pypdfium2 {version('pypdfium2')}"]
    return ", ".join(parts)


def dataset_metadata(
    figure: FigureSpec,
    observations: Mapping[ConditionKey, Sequence[Observation]],
    excluded: Mapping[ConditionKey, Sequence[Mapping[str, Any]]],
    calibrations: Sequence[PanelCalibration],
    intake_dir_relative: str,
) -> dict[str, Any]:
    measurements: list[dict[str, Any]] = []
    excluded_points: list[dict[str, Any]] = []
    total_points = 0
    flag_counts: dict[str, int] = {}
    for temperature in TEMPERATURES_C:
        for humidity in HUMIDITIES_PERCENT:
            key: ConditionKey = (figure.species_tag, figure.quantity_tag, temperature, humidity)
            rows = observations[key]
            total_points += len(rows)
            for row in rows:
                for flag in row.flags:
                    flag_counts[flag] = flag_counts.get(flag, 0) + 1
            for item in excluded[key]:
                excluded_points.append({"temperature_c": temperature, "relative_humidity_percent": humidity, **item})
            measurements.append(
                {
                    "id": f"{figure.quantity_tag}_{temperature}c_{humidity}rh",
                    "measured_quantity": figure.quantity,
                    "observable_type": "state",
                    "data_file": condition_file_name(figure, temperature, humidity),
                    "time_column": "time_h",
                    "value_column": figure.value_column,
                    "uncertainty_column": figure.sd_column,
                    "units": {"time": "hour", "value": figure.value_units, "uncertainty": figure.value_units},
                    "uncertainty_type": "standard deviation of four replicates as plotted by the source; empty where the bar could not be read (see flags)",
                    "censoring": "none",
                    "replicate_id_column": None,
                    "conditions": {
                        "temperature": {"value": float(temperature), "units": "degree_Celsius"},
                        "relative_humidity": {"value": float(humidity), "units": "percent"},
                    },
                    "notes": (
                        f"{temperature} C and {humidity} percent RH; mean of four replicates per hour. "
                        "Read twice, from the temperature panel and from the humidity panel of the same figure."
                    ),
                }
            )
    panel_calibrations = [
        {
            "panel_index": c.panel_index,
            "family": c.family,
            "fixed_value": c.fixed_value,
            "image_size_pixels": f"{c.width} x {c.height}",
            "decoded_pixel_sha256": c.pixel_digest,
            "x_axis": f"zero at column {c.x.intercept:.2f}, {c.x.slope:.3f} px per hour, residual {c.x.residual:.2f} px over {c.x.line_count} gridlines",
            "y_axis": f"zero at row {c.y.intercept:.2f}, {abs(c.y.slope):.4f} px per {figure.value_units} upward, residual {c.y.residual:.2f} px over {c.y.line_count} gridlines; fitted zero {c.y_zero_offset_px:+.2f} px from the frame bottom",
            "marker_radius_px": round(c.marker_radius_px, 2),
            "series_stagger_hours": {k: round(v, 3) for k, v in c.stagger_hours.items()},
            "markers_per_series": dict(c.series_counts),
            "excluded_detections": list(c.excluded),
        }
        for c in calibrations
    ]
    coarsest = max(1.0 / abs(c.y.slope) for c in calibrations)
    finest_radius = min(c.marker_radius_px / abs(c.y.slope) for c in calibrations)
    coarsest_radius = max(c.marker_radius_px / abs(c.y.slope) for c in calibrations)
    return {
        "kind": "experiment_dataset",
        "dataset_id": f"de_ligne_2019_{figure.species_tag}_{figure.quantity_tag}_v1",
        "name": f"De Ligne 2019 {figure.quantity} of {figure.species} under sixteen temperature and humidity conditions, Figure {figure.label}",
        "maturity": "literature_processed",
        "source": {
            "type": "literature",
            "citation": SOURCE_CITATION,
            "doi": SOURCE_DOI,
            "url": SOURCE_URL,
            "authors": list(SOURCE_AUTHORS),
            "year": 2019,
            "figure_or_table": f"Additional file {figure.file_name[-5]}: Figure {figure.label}, eight panels",
            "extraction_method": "Raster figure digitization of the panels embedded in the supplementary PDF",
            "extraction_tool": f"scripts/digitize_de_ligne_2019_figures.py with {_software_versions()}",
            "extracted_by": "Claude (Anthropic) for FungMod",
            "extraction_date": EXTRACTION_DATE,
            "raw_units": {"time": "hour", "value": figure.value_units, "uncertainty": figure.value_units},
            "license": "CC BY 4.0",
            "notes": (
                "Open access under CC BY 4.0. The article's additional files were downloaded by the "
                "repository owner and preserved under data/experiments/source_intake/de_ligne_2019 with their "
                "SHA-256 digests; the development container cannot reach the publisher. The source plots the "
                "mean of four replicates with standard-deviation bars at every hour; individual replicates are "
                "not published (data available from the authors on request). LITERATURE_PROCESSED: these are "
                "the authors' per-condition means read from figures, not raw replicate measurements. All "
                "sixteen conditions of one species come from one laboratory, one experiment and one figure; "
                "agreement between them is within-study transfer, not independent replication."
            ),
        },
        "system": {
            "organism": figure.species,
            "enzyme": None,
            "substrate": "inert surface: the bottom lid of a polystyrene Petri dish, inoculated with a 1 cm agar disc cut from the periphery of a 3-day mother culture on malt extract agar; the lids restrict the height to 0.6 mm",
            "product": None,
            "environment": "climate cabinet at the stated temperature and relative humidity; imaged hourly on a flatbed scanner",
            "geometry": "two-dimensional colony on a flat surface, 2125 x 2125 pixel scans of about 4 x 4 cm around the inoculum",
            "notes": (
                "The quantity is extracted by the authors' image analysis (Vidal-Diez de Ulzurrun et al. 2015): "
                "a line-detection ridge map converted to a graph whose nodes are hyphal junctions and tips. "
                "Mycelial area and tip count are graph-derived colony measures, not biomass; the inoculum disc "
                "was removed digitally, so growth on the agar disc is not captured. The scan window limits the "
                "measurable colony; the authors report that expansion was limited after 62 h."
            ),
        },
        "conditions": {
            "temperature_grid": {"values": [float(t) for t in TEMPERATURES_C], "units": "degree_Celsius"},
            "relative_humidity_grid": {"values": [float(h) for h in HUMIDITIES_PERCENT], "units": "percent"},
            "sampling_times": {"values": [float(h) for h in HOURS], "units": "hour"},
            "replicates_per_condition": {"value": 4, "units": "dimensionless"},
            "notes": (
                "Sixteen combinations of four temperatures and four relative humidities, one condition per "
                "measurement series; the per-series conditions are recorded on each measurement entry. Six "
                "Petri dishes were prepared per condition and four replicates were retained after excluding "
                "contaminated dishes. The series conditions are transcribed from the panel titles and the "
                "legend labels; the extractor verifies the legend colour order and the article's statement of "
                "the optimal conditions at 62 h."
            ),
        },
        "measurements": measurements,
        "measurement_definitions": {
            "measured_quantity": figure.quantity,
            "units": figure.value_units,
            "uncertainty_definition": (
                "Standard deviation of the four replicates as plotted by the source, read from the error-bar "
                "caps; empty where the bar could not be read (flags sd_below_marker_radius, sd_unavailable). "
                f"Digitization resolution: one pixel is {coarsest:.4g} {figure.value_units} in the coarsest "
                f"panel; a standard deviation smaller than the marker radius ({finest_radius:.4g} to "
                f"{coarsest_radius:.4g} {figure.value_units}) is hidden behind the marker and cannot be read."
            ),
            "measurement_method": (
                "Hourly flatbed scans of Petri dishes in a climate cabinet for 62 h; the colony network was "
                "extracted by line detection and converted to a graph from which the mycelial area and the "
                "number of tips were computed (Vidal-Diez de Ulzurrun et al. 2015); the mean of four replicates "
                "is plotted per hour."
            ),
        },
        "preprocessing": {
            "status": "raw_figure_digitization_with_panel_cross_check",
            "raw_data_available": False,
            "steps": [
                "verified the SHA-256 of the article and the five additional files",
                "extracted the embedded raster images of the supplementary PDF page in object order and verified their count and pixel sizes",
                "verified that the two legend images carry the four series hues in the declared label order",
                "located the plot frame and the grey gridlines inside it, kept the equally spaced subset of the candidates, fitted each axis through them at the declared tick values with a residual below one pixel, and verified that the fitted y zero lies on the frame bottom",
                "classified pixels into the four series by hue, estimated the shared marker radius from unoccluded discs",
                "located markers with a disc template that penalises background under the template, so partly hidden discs still yield their centre",
                "estimated each series' horizontal stagger from its own markers and assigned hours from the de-staggered position, excluding markers that fit no hour",
                "read each error bar along the marker column through occluding series, accepting an end only where its cap is visible",
                "converted pixel positions to values with the fitted axes, without smoothing, interpolation or fitting",
                "merged the two appearances of every condition (temperature panel and humidity panel) as their mean, storing both values and their difference",
                "checked the article's prose statements against the merged values: the optimal conditions at 62 h, and the equal final R. solani area at 65 percent RH for 15 and 20 C reached earlier at 20 C",
            ],
            "unit_conversions": [
                "time_h = (marker_x_px - x_zero_px) / x_px_per_hour, then de-staggered and rounded to the hour",
                f"{figure.value_column} = (y_zero_px - marker_y_px) / y_px_per_unit, averaged over the two panels",
                f"{figure.sd_column} = half the distance between the visible bar caps / y_px_per_unit",
            ],
            "excluded_points": excluded_points,
            "notes": (
                "No value was interpolated, smoothed or filled. Hours at which no marker could be located in "
                "either panel are listed under excluded_points and are absent from the CSV. Flags on every row "
                "name the reading limitations; the flag glossary is under digitization.flag_glossary. The "
                "value stored is the mean of the two panel readings; the two readings and their difference are "
                "kept as columns."
            ),
        },
        "digitization": {
            "software": _software_versions(),
            "source_page": f"{figure.file_name}, page 1, embedded raster images",
            "source_series": f"Figure {figure.label}: eight panels, four series each, 62 hourly markers per series",
            "axis_calibration": {
                "method": "equally spaced grey gridlines at the declared tick values, least-squares line per axis; the x frame is padded and carries no value, the y zero is verified against the frame bottom",
                "x_ticks": "10 to 60 h in steps of 10 h",
                "y_ticks": f"{figure.y_step:g} to {figure.y_top:g} {figure.value_units} in steps of {figure.y_step:g}",
                "panels": panel_calibrations,
            },
            "estimated_digitization_error": {
                "value": round(coarsest, 4),
                "units": figure.value_units,
                "basis": (
                    "One pixel of marker position at the calibrated scale of the coarsest panel; the per-row "
                    "column records one pixel (unoccluded marker) or two pixels (partly hidden marker) at the "
                    "panel's own scale. The difference between the two panel readings of the same value is "
                    "stored per row as an empirical check."
                ),
            },
            "included_points": total_points,
            "excluded_points": [dict(item) for item in excluded_points],
            "exclusion_reason": (
                "Hours at which no marker was located in either panel; see preprocessing.excluded_points. "
                "The t = 0 inoculation is not plotted."
                if excluded_points
                else "No points excluded. The t = 0 inoculation is not plotted."
            ),
            "flag_counts": flag_counts,
            "flag_glossary": FLAG_GLOSSARY,
            "series_colours": {
                "legend_order": list(SERIES_ORDER),
                "temperature_labels_c": list(TEMPERATURES_C),
                "relative_humidity_labels_percent": list(HUMIDITIES_PERCENT),
                "note": "Legend labels transcribed from the legend images; the hue order of the legend rows is machine-verified.",
            },
        },
        "supplementary_data": {
            "file_name": f"{intake_dir_relative}/{figure.file_name}",
            "source_url_or_doi": f"https://doi.org/{SOURCE_DOI}",
            "checksum": f"sha256:{INTAKE_FILES[figure.file_name]}",
            "access_date": EXTRACTION_DATE,
            "notes": "Downloaded by the repository owner from the article page; preserved verbatim under source_intake with the article PDF.",
        },
        "validation": {
            "expected_columns": csv_columns(figure),
            "allow_missing_uncertainty": True,
        },
        "notes": (
            f"Literature-processed colony growth curves of {figure.species} ({figure.quantity}) over a "
            "temperature-humidity grid, extracted for the spatial mycelium core. They support calibration and "
            "held-out prediction across conditions within one study under a frozen plan; they do not validate "
            "any model on their own, do not transfer to submerged culture or other strains, and the area and "
            "tip count need a declared observation operator before comparison with hyphal density fields."
        ),
    }


def _yaml_dump(data: Mapping[str, Any]) -> str:
    import yaml

    return yaml.safe_dump(dict(data), sort_keys=False, allow_unicode=True, width=100)


@dataclass
class Extraction:
    panel_rows: list[tuple[FigureSpec, PanelReading]]
    files: dict[str, str]  # relative output path -> content
    panel_table: str
    report: dict[str, Any]


def run_extraction(intake_dir: Path) -> Extraction:
    verify_intake(intake_dir)
    intake_relative = "data/experiments/source_intake/de_ligne_2019"
    panel_rows: list[tuple[FigureSpec, PanelReading]] = []
    files: dict[str, str] = {}
    report: dict[str, Any] = {"figures": {}}
    all_observations: dict[ConditionKey, list[Observation]] = {}
    for figure in FIGURES:
        images = extract_images(intake_dir / figure.file_name)
        sizes = tuple((img.shape[1], img.shape[0]) for img in images)
        if sizes != figure.image_sizes:
            raise DigitizationError(
                f"{figure.file_name}: embedded images {sizes} differ from the declared {figure.image_sizes}."
            )
        for legend_index in (figure.legend_humidity_index, figure.legend_temperature_index):
            order = legend_order(images[legend_index])
            if order != SERIES_ORDER:
                raise DigitizationError(
                    f"{figure.label} legend image {legend_index}: colour order {order} is not {SERIES_ORDER}."
                )
        calibrations: list[PanelCalibration] = []
        readings: list[PanelReading] = []
        for spec in figure.panels:
            calibration, panel_readings = digitize_panel(figure, spec, images[spec.index])
            calibrations.append(calibration)
            readings.extend(panel_readings)
            panel_rows.extend((figure, r) for r in panel_readings)
        observations, excluded = merge_readings(figure, readings, calibrations)
        all_observations.update(observations)
        metadata = dataset_metadata(figure, observations, excluded, calibrations, intake_relative)
        files[dataset_file_name(figure)] = _yaml_dump(metadata)
        for (_species, _quantity, temperature, humidity), rows in observations.items():
            files[condition_file_name(figure, temperature, humidity)] = render_condition_csv(figure, rows)
        differences = [
            abs(r.panel_difference) for rows in observations.values() for r in rows if r.panel_difference is not None
        ]
        report["figures"][figure.label] = {
            "panels": len(calibrations),
            "readings": len(readings),
            "observations": sum(len(rows) for rows in observations.values()),
            "excluded": sum(len(items) for items in excluded.values()),
            "max_panel_difference": max(differences) if differences else None,
            "median_panel_difference": float(np.median(differences)) if differences else None,
            "flag_counts": metadata["digitization"]["flag_counts"],
            "marker_radius_px": [round(c.marker_radius_px, 2) for c in calibrations],
            "stagger_hours": [c.stagger_hours for c in calibrations],
            "series_counts": [c.series_counts for c in calibrations],
            "excluded_detections": sum(len(c.excluded) for c in calibrations),
        }
    report["stated_optima"] = verify_stated_optima(all_observations)
    report["stated_equal_final_area"] = verify_stated_equal_final_area(all_observations)
    return Extraction(panel_rows, files, render_panel_table(panel_rows), report)


def write_extraction(extraction: Extraction, output_dir: Path, intake_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, content in extraction.files.items():
        (output_dir / name).write_text(content, encoding="utf-8", newline="\n")
    (intake_dir / PANEL_TABLE_NAME).write_text(extraction.panel_table, encoding="utf-8", newline="\n")


def check_extraction(extraction: Extraction, output_dir: Path, intake_dir: Path) -> list[str]:
    problems: list[str] = []
    for name, content in extraction.files.items():
        path = output_dir / name
        if not path.exists():
            problems.append(f"missing {path}")
        elif path.read_text(encoding="utf-8") != content:
            problems.append(f"differs {path}")
    table = intake_dir / PANEL_TABLE_NAME
    if not table.exists() or table.read_text(encoding="utf-8") != extraction.panel_table:
        problems.append(f"differs {table}")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--intake-dir", type=Path, default=DEFAULT_INTAKE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--check", action="store_true", help="verify the committed files instead of writing")
    parser.add_argument("--report", type=Path, default=None, help="write the extraction report as JSON")
    args = parser.parse_args(argv)
    extraction = run_extraction(args.intake_dir)
    print(json.dumps(extraction.report, indent=2, default=str))
    if args.report is not None:
        args.report.write_text(json.dumps(extraction.report, indent=2, default=str), encoding="utf-8")
    if args.check:
        problems = check_extraction(extraction, args.output_dir, args.intake_dir)
        if problems:
            print("\n".join(problems))
            return 1
        print(f"check passed: {len(extraction.files)} files match {args.output_dir}")
        return 0
    write_extraction(extraction, args.output_dir, args.intake_dir)
    print(f"wrote {len(extraction.files)} files to {args.output_dir} and {PANEL_TABLE_NAME} to {args.intake_dir}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DigitizationError as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(2)
