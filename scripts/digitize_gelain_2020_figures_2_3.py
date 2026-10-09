"""Digitize Gelain 2020 Figures 2 and 3: held-out cellulose cultures with error bars.

Source: Gelain L, van der Wielen L, van Gulik WM, Pradella JGC, da Costa AC.
Mathematical modelling for the optimization of cellulase production using
glycerol for cell growth and cellulose as the inducer substrate. Chemical
Engineering Science: X 8 (2020) 100085. doi:10.1016/j.cesx.2020.100085.
CC BY 4.0. The article PDF is archived under
``data/experiments/source_intake/gelain_2020/article.pdf`` with its SHA-256 in
the source-intake manifest.

Figure 3A and 3B plot the *T. harzianum* P49P11 batch cultures on 5 and 40 g/L
cellulose and Figure 3C their beta-glucosidase activity. Section 3.4 of the
article states that these two conditions were **not** used for parameter
estimation; the deposited Mendeley workbooks do not contain them. They are the
only held-out cellulose loadings of this strain in the public record. Each
plotted point is the mean of a duplicate culture and each error bar is the
sample standard deviation (article Section 3.2).

Figure 2 plots the 10, 20 and 30 g/L training cultures in the same style. The
deposited workbooks hold the exact means of those points, so Figure 2 is the
calibration check of this digitizer: the script digitizes Figure 2 with the
same code and refuses to write anything unless the digitized means reproduce
the deposited means within the declared tolerance. The Figure 2 standard
deviations, which the deposit does not hold, are written as a separate
evidence table.

Method, per panel: the plot frame and tick marks are detected in the raw JPEG
stream, major ticks are matched to the printed tick labels and fitted with a
straight line (the residual is recorded); markers are segmented by their exact
plotting colour, thin model curves and error bars are removed by a binary
opening, and each marker centre is the centre of its bounding box (Origin
centres symbols on their bounding box). A marker clipped by the frame or
partly hidden by another marker is centred from its visible edge and the
nominal marker size, and flagged. Each error bar is traced along the marker
column to its cap; the half-length is the standard deviation. A bar hidden
inside its marker is recorded as an upper bound, not as zero.

Usage::

    python scripts/digitize_gelain_2020_figures_2_3.py \
        --output-dir data/experiments/literature/gelain_2020_t_harzianum_heldout
    python scripts/digitize_gelain_2020_figures_2_3.py --check \
        --output-dir data/experiments/literature/gelain_2020_t_harzianum_heldout
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, cast

import numpy as np
from PIL import Image
from pypdf import PdfReader
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[1]
ARTICLE = ROOT / "data" / "experiments" / "source_intake" / "gelain_2020" / "article.pdf"
ARTICLE_SHA256 = "38d90f4a90507bf1de76c316dd69a2532af8ffa944a7858ff8e72587a2b533aa"
OBSERVATIONS = ROOT / "data" / "benchmarks" / "gelain_2020_v2" / "observations.json"
PAGE_INDEX = 5  # article page 6
FIGURE_STREAMS = {
    # XObject name -> (figure, SHA-256 of the raw DCT stream, pixel size)
    "/Im4": ("figure_2", "b0cc2f025e70ec6fb089e02ab7884d9550f01052c497101097a4061acb17a463", (1772, 1218)),
    "/Im5": ("figure_3", "b2359e2e9388844c855f29ac78d56413bd508961f6a6aa8cfc6d6f1b03a16a82", (1772, 1272)),
}

SAMPLING_TIMES_H = (8.0, 12.0, 24.0, 32.0, 48.0, 54.0, 72.0, 96.0)
TIME_SNAP_TOLERANCE_H = 1.5

# Plotting colours of the source figures (Origin defaults): marker colour -> RGB.
COLOURS = {
    "black": (0, 0, 0),
    "orange": (255, 128, 0),
    "blue": (0, 0, 255),
    "red": (255, 0, 0),
}
MARKER_SHAPE = {"black": "square", "orange": "circle", "blue": "triangle", "red": "circle"}

# Calibration-check tolerances, declared before the comparison was run: absolute
# error as a fraction of the plotted axis span. 1 % of span is about 5 pixels.
TOLERANCE_MEDIAN_FRACTION = 0.004
TOLERANCE_MAX_FRACTION = 0.010
# Estimated digitization error recorded with every value: two pixels on the
# calibrated axis, about 0.4 % of the axis span.
DIGITIZATION_ERROR_PIXELS = 2.0
# Figure 2 reference points the digitizer may fail to find (hidden symbols) before the check fails.
MAXIMUM_UNFOUND_REFERENCE_POINTS = 6
# An error bar is accepted only if it reaches this far beyond the marker outline.
BAR_MINIMUM_OVERHANG_PIXELS = 4.0


@dataclass(frozen=True)
class Axis:
    """Linear pixel-to-value map fitted to detected major ticks."""

    pixels: tuple[float, ...]
    values: tuple[float, ...]
    slope: float
    intercept: float
    max_residual_pixels: float

    def value(self, pixel: float) -> float:
        return self.slope * pixel + self.intercept

    def per_pixel(self) -> float:
        return abs(self.slope)

    @property
    def span(self) -> float:
        return abs(self.values[-1] - self.values[0])


@dataclass(frozen=True)
class Series:
    observable: str
    colour: str
    axis: str  # "left" or "right"
    condition_g_l: float


@dataclass(frozen=True)
class Panel:
    figure: str
    panel: str
    frame: tuple[int, int, int, int]  # approximate left, right, top, bottom pixel lines
    x_step: float
    left_step: float
    right_step: float | None
    series: tuple[Series, ...]
    exclusion_boxes: tuple[tuple[int, int, int, int], ...] = ()


def _series(condition: float, *, activity_axis: str = "right") -> tuple[Series, ...]:
    return (
        Series("biomass", "black", "left", condition),
        Series("substrate", "orange", "left", condition),
        Series("cellulase_activity", "blue", activity_axis, condition),
    )


# Exclusion boxes (column_min, column_max, row_min, row_max) cover the panel
# letters and legends, read from the rendered figures; no data point lies in them.
PANELS = (
    Panel("figure_2", "A", (80, 731, 13, 497), 20.0, 2.0, 200.0, _series(10.0),
          exclusion_boxes=((100, 150, 35, 85),)),
    Panel("figure_2", "B", (1019, 1671, 10, 496), 20.0, 4.0, 200.0, _series(20.0),
          exclusion_boxes=((1140, 1195, 20, 70),)),
    Panel("figure_2", "C", (80, 729, 647, 1130), 20.0, 4.0, 200.0, _series(30.0),
          exclusion_boxes=((230, 275, 660, 710),)),
    Panel(
        "figure_2",
        "D",
        (1022, 1698, 629, 1132),
        20.0,
        500.0,
        None,
        (
            Series("beta_glucosidase_activity", "black", "left", 10.0),
            Series("beta_glucosidase_activity", "red", "left", 20.0),
            Series("beta_glucosidase_activity", "blue", "left", 30.0),
        ),
        exclusion_boxes=((1040, 1240, 645, 760), (1615, 1665, 655, 705)),
    ),
    Panel("figure_3", "A", (110, 776, 13, 508), 20.0, 2.0, 200.0, _series(5.0),
          exclusion_boxes=((150, 200, 35, 85),)),
    Panel("figure_3", "B", (1027, 1683, 10, 498), 20.0, 10.0, 200.0, _series(40.0),
          exclusion_boxes=((1160, 1215, 20, 70),)),
    Panel(
        "figure_3",
        "C",
        (112, 804, 669, 1184),
        20.0,
        500.0,
        None,
        (
            Series("beta_glucosidase_activity", "black", "left", 5.0),
            Series("beta_glucosidase_activity", "red", "left", 40.0),
        ),
        exclusion_boxes=((130, 290, 685, 765), (700, 750, 680, 730)),
    ),
)

UNITS = {
    "biomass": "gram / liter",
    "substrate": "gram / liter",
    "cellulase_activity": "filter_paper_unit / liter",
    "beta_glucosidase_activity": "beta_glucosidase_assay_unit / liter",
}


# --------------------------------------------------------------------------- source


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_figures(article: Path = ARTICLE) -> dict[str, np.ndarray]:
    """Return the verified raw figure rasters keyed by figure id."""

    if sha256(article.read_bytes()) != ARTICLE_SHA256:
        raise SystemExit(f"{article} does not match the archived SHA-256 {ARTICLE_SHA256}.")
    page = PdfReader(str(article)).pages[PAGE_INDEX]
    xobjects = page["/Resources"]["/XObject"]  # type: ignore[index]
    figures: dict[str, np.ndarray] = {}
    for name, (figure, digest, size) in FIGURE_STREAMS.items():
        stream = xobjects[name].get_object()
        raw = stream._data  # noqa: SLF001 - the raw DCT bytes, not a re-encoded copy
        if sha256(raw) != digest:
            raise SystemExit(f"{figure} stream {name} does not match SHA-256 {digest}.")
        image = Image.open(io.BytesIO(raw)).convert("RGB")
        if image.size != size:
            raise SystemExit(f"{figure} has size {image.size}, expected {size}.")
        figures[figure] = np.asarray(image).astype(int)
    return figures


# --------------------------------------------------------------------------- axes


def _dark(rgb: np.ndarray) -> np.ndarray:
    """Black or dark-grey axis ink; coloured curves and markers are excluded."""

    return rgb.max(axis=-1) < 140


def _refine_line(dark: np.ndarray, approximate: int, span: tuple[int, int], *, vertical: bool) -> int:
    lo, hi = span
    best, best_count = approximate, -1
    for candidate in range(approximate - 6, approximate + 7):
        line = dark[lo:hi, candidate] if vertical else dark[candidate, lo:hi]
        count = int(line.sum())
        if count > best_count:
            best, best_count = candidate, count
    return best


def _tick_runs(lengths: np.ndarray, offset: int) -> list[tuple[float, int]]:
    """Group consecutive positions with outward dark runs into (centre, length) ticks."""

    ticks: list[tuple[float, int]] = []
    positions = np.flatnonzero(lengths >= 3)
    if positions.size == 0:
        return ticks
    groups = np.split(positions, np.flatnonzero(np.diff(positions) > 1) + 1)
    for group in groups:
        if group.size > 6:  # an axis label or frame, not a tick
            continue
        ticks.append((float(group.mean()) + offset, int(lengths[group].max())))
    return ticks


def _outward_lengths(dark: np.ndarray, line: int, span: tuple[int, int], *, side: str) -> np.ndarray:
    lo, hi = span
    lengths = np.zeros(hi - lo, dtype=int)
    for index, position in enumerate(range(lo, hi)):
        run = 0
        for step in range(2, 20):
            if side == "left":
                pixel = dark[position, line - step]
            elif side == "right":
                pixel = dark[position, line + step]
            elif side == "inside_right":
                pixel = dark[position, line - step]
            else:  # below
                pixel = dark[line + step, position]
            if not pixel:
                break
            run += 1
        lengths[index] = run
    return lengths


def _fit_axis(ticks: list[tuple[float, int]], step: float, *, increasing_pixels_increase_value: bool) -> Axis:
    if not ticks:
        raise SystemExit("No ticks detected.")
    lengths = np.array([length for _, length in ticks], dtype=float)
    # Major ticks are about twice as long as minor ticks; the frame corner can run longer.
    threshold = 0.5 * (lengths.min() + np.percentile(lengths, 75))
    major = sorted(position for position, length in ticks if length > threshold)
    if not increasing_pixels_increase_value:
        major = major[::-1]
    values = [index * step for index in range(len(major))]
    slope, intercept = np.polyfit(major, values, 1)
    residual = np.abs(np.polyval([slope, intercept], major) - values) / abs(slope)
    if len(major) < 3 or residual.max() > 1.0:
        raise SystemExit(f"Axis calibration failed: {len(major)} major ticks, residual {residual.max():.2f} px.")
    return Axis(tuple(major), tuple(values), float(slope), float(intercept), float(residual.max()))


@dataclass(frozen=True)
class Frame:
    left: int
    right: int
    top: int
    bottom: int
    x: Axis
    y_left: Axis
    y_right: Axis | None


def calibrate(panel: Panel, rgb: np.ndarray) -> Frame:
    dark = _dark(rgb)
    left0, right0, top0, bottom0 = panel.frame
    left = _refine_line(dark, left0, (top0 + 20, bottom0 - 20), vertical=True)
    right = _refine_line(dark, right0, (top0 + 20, bottom0 - 20), vertical=True)
    bottom = _refine_line(dark, bottom0, (left + 20, right - 20), vertical=False)
    top = top0  # the top frame is a light grey line; it only bounds the marker search
    x_ticks = _tick_runs(_outward_lengths(dark, bottom, (left - 3, right + 4), side="below"), left - 3)
    y_ticks = _tick_runs(_outward_lengths(dark, left, (top - 3, bottom + 4), side="left"), top - 3)
    x_axis = _fit_axis(x_ticks, panel.x_step, increasing_pixels_increase_value=True)
    y_left = _fit_axis(y_ticks, panel.left_step, increasing_pixels_increase_value=False)
    y_right = None
    if panel.right_step is not None:
        # The secondary axis of these figures carries its ticks on the inside of the frame.
        r_ticks = _tick_runs(_outward_lengths(dark, right, (top - 3, bottom + 4), side="inside_right"), top - 3)
        y_right = _fit_axis(r_ticks, panel.right_step, increasing_pixels_increase_value=False)
    return Frame(left, right, top, bottom, x_axis, y_left, y_right)


# --------------------------------------------------------------------------- markers


def colour_mask(rgb: np.ndarray, colour: str, *, loose: bool = False) -> np.ndarray:
    """Pixels of one plotting colour; ``loose`` also accepts anti-aliased thin strokes."""

    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    high = rgb.max(axis=-1)
    low = rgb.min(axis=-1)
    if colour == "black":
        return (high < (170 if loose else 130)) & (high - low < 40)
    if colour == "orange":
        if loose:
            return (r > 200) & (g > 60) & (g < 215) & (r - b > 90) & (g - b > 30)
        return (r > 200) & (g > 85) & (g < 185) & (b < 90)
    if colour == "red":
        if loose:
            return (r > 180) & (r - np.maximum(g, b) > 70) & (np.abs(g - b) < 60)
        return (r > 200) & (g < 80) & (b < 80)
    if colour == "blue":
        if loose:
            return (b > 150) & (b - np.maximum(r, g) > 50)
        return (b > 180) & (r < 110) & (g < 110)
    raise ValueError(colour)


@dataclass
class Marker:
    colour: str
    row_min: int
    row_max: int
    col_min: int
    col_max: int
    area: int
    centre_row: float = 0.0
    centre_col: float = 0.0
    flags: tuple[str, ...] = ()

    @property
    def height(self) -> int:
        return self.row_max - self.row_min + 1

    @property
    def width(self) -> int:
        return self.col_max - self.col_min + 1


def _components(mask: np.ndarray, colour: str, *, min_width: int) -> list[Marker]:
    # Closing bridges the thin error-bar and curve strokes drawn across a marker;
    # opening then removes every stroke thinner than five pixels.
    closed = ndi.binary_closing(mask, structure=np.ones((3, 3), dtype=bool))
    opened = ndi.binary_opening(closed, structure=np.ones((5, 5), dtype=bool))
    labels, _count = cast(tuple[np.ndarray, int], ndi.label(opened))
    markers: list[Marker] = []
    for index, box in enumerate(ndi.find_objects(labels), start=1):
        if box is None:
            continue
        area = int((labels[box] == index).sum())
        rows, cols = box
        marker = Marker(colour, rows.start, rows.stop - 1, cols.start, cols.stop - 1, area)
        if area < 20 or marker.height > 16 or marker.width > 16 or marker.width < min_width:
            continue
        fill = area / (marker.height * marker.width)
        if MARKER_SHAPE[colour] == "square" and fill < 0.6:
            continue
        markers.append(marker)
    return markers


def _interior(panel: Panel, frame: Frame, shape: tuple[int, ...]) -> np.ndarray:
    interior = np.zeros(shape[:2], dtype=bool)
    # Everything strictly between the frame lines; markers on the zero line touch the frame.
    interior[frame.top + 2 : frame.bottom, frame.left + 1 : frame.right] = True
    for c0, c1, r0, r1 in panel.exclusion_boxes:
        interior[r0:r1, c0:c1] = False
    return interior


def find_markers(panel: Panel, frame: Frame, rgb: np.ndarray, colour: str) -> tuple[list[Marker], int]:
    """Return markers of one colour inside the frame and the nominal marker size.

    Complete markers are centred on their bounding box. A marker resting on the
    zero line is flagged ``on_zero_line``: the calibration check shows that the
    source draws values of exactly zero as complete symbols standing on the axis.
    """

    interior = _interior(panel, frame, rgb.shape)
    mask = colour_mask(rgb, colour) & interior
    complete = _components(mask, colour, min_width=6)
    if not complete:
        return [], 0
    nominal = int(round(float(np.median([m.width for m in complete]))))
    markers = _components(mask, colour, min_width=5)
    for marker in markers:
        marker.centre_col = 0.5 * (marker.col_min + marker.col_max)
        flags: list[str] = []
        if marker.row_max >= frame.bottom - 2:
            marker.centre_row = float(frame.bottom)
            flags.append("on_zero_line")
        elif marker.height >= nominal - 2:
            marker.centre_row = 0.5 * (marker.row_min + marker.row_max)
        else:
            marker.centre_row = 0.5 * (marker.row_min + marker.row_max)
            flags.append("partial_marker_ambiguous")
        if marker.width < nominal - 2:
            flags.append("narrow_marker")
        marker.flags = tuple(flags)
    return markers, nominal


def recover_partial_marker(
    panel: Panel, frame: Frame, rgb: np.ndarray, colour: str, nominal: int, column: float
) -> Marker | None:
    """Find a marker partly hidden behind another symbol at an expected sampling column.

    The visible part must span the full marker width over at least three rows
    (thin curves, bars and caps cannot). The hidden side is the side touching
    another plotting colour; the centre is the visible edge plus half the
    nominal marker size. Recovered markers are flagged.
    """

    interior = _interior(panel, frame, rgb.shape)
    band = np.zeros_like(interior)
    c = int(round(column))
    band[:, c - nominal : c + nominal + 1] = True
    mask = colour_mask(rgb, colour) & interior & band
    # A wider closing bridges an error bar of another colour drawn across the symbol.
    closed = ndi.binary_closing(mask, structure=np.ones((1, 5), dtype=bool))
    labels, _count = cast(tuple[np.ndarray, int], ndi.label(closed))
    other = np.zeros(rgb.shape[:2], dtype=bool)
    for other_colour in COLOURS:
        if other_colour != colour:
            other |= colour_mask(rgb, other_colour)
    best: Marker | None = None
    for index, box in enumerate(ndi.find_objects(labels), start=1):
        if box is None:
            continue
        piece = labels[box] == index
        wide_rows = int((piece.sum(axis=1) >= nominal - 3).sum())
        rows, cols = box
        candidate = Marker(colour, rows.start, rows.stop - 1, cols.start, cols.stop - 1, int(piece.sum()))
        if wide_rows < 3 or candidate.width < nominal - 2 or candidate.height > nominal + 2:
            continue
        if abs(0.5 * (candidate.col_min + candidate.col_max) - column) > 3:
            continue
        if best is None or candidate.area > best.area:
            best = candidate
    if best is None:
        return None
    above = other[max(best.row_min - 3, 0) : best.row_min, best.col_min : best.col_max + 1].sum()
    below = other[best.row_max + 1 : best.row_max + 4, best.col_min : best.col_max + 1].sum()
    best.centre_col = 0.5 * (best.col_min + best.col_max)
    if best.row_max >= frame.bottom - 2:
        best.centre_row = float(frame.bottom)
        best.flags = ("recovered_partial_marker", "on_zero_line")
    elif best.height >= nominal - 2:
        best.centre_row = 0.5 * (best.row_min + best.row_max)
        best.flags = ("recovered_partial_marker",)
    elif above > below:
        best.centre_row = best.row_max - 0.5 * (nominal - 1)
        best.flags = ("recovered_partial_marker", "occluded_above")
    elif below > above:
        best.centre_row = best.row_min + 0.5 * (nominal - 1)
        best.flags = ("recovered_partial_marker", "occluded_below")
    else:
        return None
    return best


def _trace_bar(
    mask: np.ndarray, occluder: np.ndarray, column: int, start: int, direction: int, limit: int
) -> tuple[int, bool]:
    """Follow a bar from ``start`` along ``direction``; return the last bar row and whether a cap ends it.

    Pixels of another plotting colour are crossed without ending the bar (a
    symbol or bar of another series drawn over this one), but only the bar's
    own colour moves its end, and the cap must be in the bar's own colour.
    """

    row = start
    last = start
    gap = 0
    while 0 <= row + direction < mask.shape[0] and abs(row - start) < limit:
        row += direction
        if mask[row, column - 1 : column + 2].any():
            last = row
            gap = 0
        elif occluder[row, column - 1 : column + 2].any():
            gap = 0
        else:
            gap += 1
            if gap > 2:
                break
    cap_run = 0
    for offset in (-1, 0, 1):
        r = last + offset
        if 0 <= r < mask.shape[0]:
            segment = mask[r, column - 8 : column + 9]
            cap_run = max(cap_run, int(segment.sum()))
    return last, cap_run >= 6


def error_bar(rgb: np.ndarray, frame: Frame, marker: Marker, nominal: int) -> tuple[float | None, float, str]:
    """Return (half-length in pixels or None, upper bound in pixels, status)."""

    mask = colour_mask(rgb, marker.colour, loose=True)
    occluder = np.zeros_like(mask)
    for other_colour in COLOURS:
        if other_colour != marker.colour:
            occluder |= colour_mask(rgb, other_colour, loose=True)
    column = int(round(marker.centre_col))
    half = 0.5 * (nominal - 1)
    top_edge = int(round(marker.centre_row - half))
    bottom_edge = int(round(marker.centre_row + half))
    limit = frame.bottom - frame.top
    up_end, up_cap = _trace_bar(mask, occluder, column, top_edge, -1, limit)
    down_end, down_cap = _trace_bar(mask, occluder, column, bottom_edge, +1, limit)
    up = marker.centre_row - up_end
    down = down_end - marker.centre_row
    # A bar must reach clearly past the marker outline; shorter traces are the
    # anti-aliased rim of the marker itself.
    up_visible = up >= half + BAR_MINIMUM_OVERHANG_PIXELS and up_cap
    down_visible = down >= half + BAR_MINIMUM_OVERHANG_PIXELS and down_cap and down_end < frame.bottom - 2
    if up_visible and down_visible:
        if abs(up - down) <= 3:
            return 0.5 * (up + down), 0.5 * (up + down), "symmetric_bar"
        return min(up, down), min(up, down), "asymmetric_bar_shorter_side"
    if up_visible:
        return up, up, "upper_bar_only"
    if down_visible:
        return down, down, "lower_bar_only"
    return None, half + BAR_MINIMUM_OVERHANG_PIXELS, "bar_hidden_inside_marker"


# --------------------------------------------------------------------------- digitize


@dataclass(frozen=True)
class Point:
    figure: str
    panel: str
    observable: str
    condition_g_l: float
    time_h: float
    digitized_time_h: float
    mean: float
    sd: float | None
    sd_upper_bound: float
    sd_status: str
    digitization_error: float
    marker_col: float
    marker_row: float
    flags: tuple[str, ...]
    censored_upper_limit: float | None = None


def digitize_panel(panel: Panel, rgb: np.ndarray) -> tuple[Frame, list[Point]]:
    frame = calibrate(panel, rgb)
    points: list[Point] = []
    for series in panel.series:
        axis = frame.y_left if series.axis == "left" else frame.y_right
        assert axis is not None
        markers, nominal = find_markers(panel, frame, rgb, series.colour)
        found_times = set()
        for marker in markers:
            time = frame.x.value(marker.centre_col)
            if time >= 4.0:
                found_times.add(min(SAMPLING_TIMES_H, key=lambda t: abs(t - time)))
        for time in SAMPLING_TIMES_H:
            if time in found_times:
                continue
            column = (time - frame.x.intercept) / frame.x.slope
            recovered = recover_partial_marker(panel, frame, rgb, series.colour, nominal, column)
            if recovered is not None:
                markers.append(recovered)
        for marker in markers:
            time = frame.x.value(marker.centre_col)
            nearest = min(SAMPLING_TIMES_H, key=lambda t: abs(t - time))
            if time < 4.0:
                continue  # t = 0 is the initial condition, not a sample
            if abs(nearest - time) > TIME_SNAP_TOLERANCE_H:
                raise SystemExit(f"{panel.figure}{panel.panel} {series.colour} marker at {time:.2f} h matches no sampling time.")
            per_pixel = axis.per_pixel()
            if "on_zero_line" in marker.flags:
                # Left-censored: the value lies between zero and one marker height.
                value = 0.0
                half_length, upper, status = None, nominal * 1.0, "zero_line_marker_no_bar"
                censor = nominal * per_pixel
            else:
                value = axis.value(marker.centre_row)
                half_length, upper, status = error_bar(rgb, frame, marker, nominal)
                censor = None
            points.append(
                Point(
                    panel.figure,
                    panel.panel,
                    series.observable,
                    series.condition_g_l,
                    nearest,
                    round(time, 3),
                    max(value, 0.0),
                    None if half_length is None else half_length * per_pixel,
                    upper * per_pixel,
                    status,
                    DIGITIZATION_ERROR_PIXELS * per_pixel,
                    marker.centre_col,
                    marker.centre_row,
                    marker.flags,
                    censor,
                )
            )
    return frame, points


def digitize(figures: dict[str, np.ndarray]) -> tuple[dict[str, Frame], list[Point]]:
    frames: dict[str, Frame] = {}
    points: list[Point] = []
    for panel in PANELS:
        frame, panel_points = digitize_panel(panel, figures[panel.figure])
        frames[f"{panel.figure}{panel.panel}"] = frame
        points.extend(panel_points)
    duplicates = {(p.figure, p.observable, p.condition_g_l, p.time_h) for p in points}
    if len(duplicates) != len(points):
        raise SystemExit("Two markers of one series were assigned to one sampling time.")
    return frames, points


# --------------------------------------------------------------------------- calibration check


def deposited_means() -> dict[tuple[str, float, float], float]:
    records = json.loads(OBSERVATIONS.read_text(encoding="utf-8"))
    means: dict[tuple[str, float, float], float] = {}
    for record in records:
        if record["family"] != "cellulose":
            continue
        loading = float(record["initial"]["substrate"]["value"])
        for observable, block in record["observations"].items():
            for time, value in zip(record["times_h"], block["values"], strict=True):
                means[(observable, loading, float(time))] = float(value)
    return means


def calibration_check(points: Iterable[Point], frames: dict[str, Frame]) -> dict[str, object]:
    reference = deposited_means()
    rows = []
    for point in points:
        if point.figure != "figure_2":
            continue
        key = (point.observable, point.condition_g_l, point.time_h)
        if key not in reference:
            raise SystemExit(f"Figure 2 point {key} has no deposited mean.")
        panel = next(p for p in PANELS if p.figure == "figure_2" and any(
            s.observable == point.observable and s.condition_g_l == point.condition_g_l for s in p.series))
        frame = frames[f"figure_2{panel.panel}"]
        series = next(s for s in panel.series if s.observable == point.observable and s.condition_g_l == point.condition_g_l)
        axis = frame.y_left if series.axis == "left" else frame.y_right
        assert axis is not None
        error = point.mean - reference[key]
        censored = point.censored_upper_limit is not None
        rows.append({
            "observable": point.observable,
            "condition_g_l": point.condition_g_l,
            "time_h": point.time_h,
            "digitized": round(point.mean, 4),
            "deposited": round(reference[key], 4),
            "censored_upper_limit": None if not censored else round(float(point.censored_upper_limit or 0.0), 4),
            "censored_consistent": None if not censored else bool(
                0.0 <= reference[key] <= float(point.censored_upper_limit or 0.0)),
            "error": None if censored else round(error, 4),
            "error_fraction_of_axis_span": None if censored else round(abs(error) / axis.span, 5),
            "flags": list(point.flags),
        })
    expected = {k for k in reference if k[2] in SAMPLING_TIMES_H}
    found = {(r["observable"], r["condition_g_l"], r["time_h"]) for r in rows}
    missing = sorted(expected - found)
    fractions = np.array([r["error_fraction_of_axis_span"] for r in rows if r["error_fraction_of_axis_span"] is not None])
    recovered = np.array([r["error_fraction_of_axis_span"] for r in rows
                          if r["error_fraction_of_axis_span"] is not None and "recovered_partial_marker" in r["flags"]])
    censored_rows = [r for r in rows if r["censored_upper_limit"] is not None]
    summary = {
        "points_compared": len(rows),
        "uncensored_points": int(fractions.size),
        "censored_zero_line_points": len(censored_rows),
        "censored_points_consistent": sum(1 for r in censored_rows if r["censored_consistent"]),
        "recovered_partial_markers": int(recovered.size),
        "recovered_max_error_fraction_of_span": float(recovered.max()) if recovered.size else None,
        "deposited_points_not_found": [list(m) for m in missing],
        "median_error_fraction_of_span": float(np.median(fractions)),
        "max_error_fraction_of_span": float(fractions.max()),
        "tolerance_median_fraction": TOLERANCE_MEDIAN_FRACTION,
        "tolerance_max_fraction": TOLERANCE_MAX_FRACTION,
        "passed": bool(
            np.median(fractions) <= TOLERANCE_MEDIAN_FRACTION
            and fractions.max() <= TOLERANCE_MAX_FRACTION
            and all(r["censored_consistent"] for r in censored_rows)
            and len(missing) <= MAXIMUM_UNFOUND_REFERENCE_POINTS
        ),
        "rows": rows,
    }
    return summary


def _point_rows(points: Iterable[Point]) -> list[dict[str, object]]:
    rows = []
    for p in sorted(points, key=lambda q: (q.figure, q.condition_g_l, q.observable, q.time_h)):
        rows.append({
            "figure": p.figure,
            "panel": p.panel,
            "condition_g_l": p.condition_g_l,
            "observable": p.observable,
            "units": UNITS[p.observable],
            "time_h": p.time_h,
            "digitized_time_h": p.digitized_time_h,
            "mean": round(p.mean, 4),
            "censored_upper_limit": "" if p.censored_upper_limit is None else round(p.censored_upper_limit, 4),
            "sd": "" if p.sd is None else round(p.sd, 4),
            "sd_upper_bound": round(p.sd_upper_bound, 4),
            "sd_status": p.sd_status,
            "digitization_error": round(p.digitization_error, 4),
            "marker_center_x_pixel": round(p.marker_col, 1),
            "marker_center_y_pixel": round(p.marker_row, 1),
            "flags": ";".join(p.flags),
        })
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="Verify the committed files instead of writing them.")
    args = parser.parse_args(argv)
    figures = load_figures()
    frames, points = digitize(figures)
    check = calibration_check(points, frames)
    print(json.dumps({k: v for k, v in check.items() if k != "rows"}, indent=1))
    if not check["passed"]:
        print("Calibration check against the deposited Figure 2 means FAILED; nothing written.", file=sys.stderr)
        return 1
    rows = _point_rows(points)
    outputs = {
        "gelain_2020_figure_3_heldout.csv": [r for r in rows if r["figure"] == "figure_3"],
        "gelain_2020_figure_2_training_with_sd.csv": [r for r in rows if r["figure"] == "figure_2"],
    }
    calibration = {
        "article_sha256": ARTICLE_SHA256,
        "figure_streams": {v[0]: {"xobject": k, "sha256": v[1], "size": list(v[2])} for k, v in FIGURE_STREAMS.items()},
        "axes": {
            key: {
                "frame": [f.left, f.right, f.top, f.bottom],
                "x": {"major_tick_pixels": f.x.pixels, "values": f.x.values, "max_residual_pixels": round(f.x.max_residual_pixels, 3)},
                "y_left": {"major_tick_pixels": f.y_left.pixels, "values": f.y_left.values,
                           "max_residual_pixels": round(f.y_left.max_residual_pixels, 3)},
                "y_right": None if f.y_right is None else {
                    "major_tick_pixels": f.y_right.pixels, "values": f.y_right.values,
                    "max_residual_pixels": round(f.y_right.max_residual_pixels, 3)},
            }
            for key, f in frames.items()
        },
        "calibration_check": check,
    }
    rendered = {name: _csv_text(table) for name, table in outputs.items()}
    rendered["digitization_calibration.json"] = json.dumps(calibration, indent=1, default=float) + "\n"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    status = 0
    for name, text in rendered.items():
        path = args.output_dir / name
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                print(f"{path} differs from a fresh digitization.", file=sys.stderr)
                status = 1
        else:
            path.write_text(text, encoding="utf-8")
            print(f"wrote {path}")
    return status


def _csv_text(rows: list[dict[str, object]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


if __name__ == "__main__":
    sys.exit(main())
