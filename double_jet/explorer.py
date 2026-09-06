"""The interactive explorer: one self-contained HTML file, a season table, a static annual chart.

Addendum §B (deviation D4). This module replaces the 47-panel figure as the campaign's visual
deliverable. It reads the intermediate's attributes and the states CSV and writes three files whose
paths `cli.output_names` owns and this module never builds (plan §4.2):

* `explorer_path`  -- the approved mockup, `docs/mockup/double_jet_explorer_v2.html`, transcribed
  with exactly the changes §B3 enumerates, its data embedded as two JSON blocks.
* `summary_path`   -- `results/season_summary.csv`, §B7's eight columns.
* `annual_path`    -- a static PNG of the explorer's top chart.

Six decisions this module owns, recorded here because none of them is obvious:

* **The template is substituted with sentinels and `str.replace`, never `str.format`.** The
  mockup's CSS and JavaScript are full of `{`, `}` and `${...}`; `format` would have to escape
  every one of them and the diff against `docs/mockup/` would stop being readable. The mockup's own
  `// ---------- ... ----------` comment markers are kept for the same reason.
* **The payload is columnar; the renderers consume per-day objects** (§B1.5). Hydration in the
  page converts one to the other, and `v === null ? NaN : v` in that step is load-bearing rather
  than defensive: `isFinite(null)` is `true` in JavaScript, so a `null` latitude passed straight
  through would draw a core at 0 °N instead of drawing nothing.
* **State ships as a `days_per_season`-character string of `d`/`s`/`n`,** with the code table in
  the payload: 153 bytes a season instead of ~1 000, and the HTML then holds no literal state name
  that could drift from the CSV's.
* **`date` is not embedded.** MJJAS contains no 29 February, so day-of-season <-> calendar date is
  a bijection within a season -- the identity `figure._day_of_season` already rests on -- and
  deriving it in the page drops 7 191 strings from the file.
* **The `profile_sha256` check below is duplicated from `classify.py:343-352` on purpose** (§B9).
  Factoring it into a shared helper would mean editing `classify.py`, which D3's addendum and this
  one both hold untouched; eight duplicated lines is the cheaper price.
* **The PNG is rendered by reading `summary_path` back,** not from a parallel in-memory
  computation, so "the chart and the table carry the same numbers" is literal rather than argued.
  `figsize=(11, 2.5)` maps the mockup's 1100 x 250 viewBox to exactly 100 SVG units per inch, which
  is what turns its margins into an exact `add_axes` rectangle and its 11 px type into 7.92 pt.

Every check in §B11 is a hard failure that names the offender. There is no warning and no fallback:
a discrepancy in the artifacts is this module's to make visible, not to render around (§B17).
"""

from __future__ import annotations

import calendar
import json
import logging
import math
from pathlib import Path
from typing import Sequence

import matplotlib

# Before pyplot: the campaign runs inside a batch job with no DISPLAY, where the default
# interactive backend would fail at import time rather than at draw time (as `figure.py` records).
matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402  -- must follow matplotlib.use
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .config import Config  # noqa: E402

# ---------------------------------------------------------------------------------------------
# the contract with the artifacts
# ---------------------------------------------------------------------------------------------

# Global attributes the method block and the gates read. G4 raises naming any that is absent.
REQUIRED_ATTRS: tuple[str, ...] = (
    "source_dataset", "variable", "pressure_level", "pressure_level_units", "sector",
    "season_months", "years", "days_per_season", "profile_fields", "profile_sha256",
)

# The subset of those written as JSON strings (`profile._intermediate_attrs`: netCDF takes no
# dicts). G4 raises naming any that does not parse.
JSON_ATTRS: tuple[str, ...] = ("sector", "season_months", "years", "profile_fields")

SECTOR_KEYS: tuple[str, ...] = ("lat_min", "lat_max", "lon_min", "lon_max", "resolution")
PROFILE_FIELD_KEYS: tuple[str, ...] = ("source", "daily_statistic", "hourly_times")

# Exactly `classify.CSV_COLUMNS` minus `date` and `state`, duplicated at module scope the way
# `figure.STATES_NUMERIC_COLUMNS` is so the helpers below need no import. G7 asserts the pair still
# agree with `classify`'s own tuple, so a schema drift cannot go unnoticed here.
NUMERIC_COLUMNS: tuple[str, ...] = ("lat_1", "u_1", "lat_2", "u_2", "interjet_min")

# Which numeric columns each state must carry, and which it must leave blank (§B11 G8).
STATE_NULL_CONTRACT: dict[str, dict[str, bool]] = {
    "double": {"lat_1": True, "u_1": True, "lat_2": True, "u_2": True, "interjet_min": True},
    "single": {"lat_1": True, "u_1": True, "lat_2": False, "u_2": False, "interjet_min": False},
    "none": {"lat_1": False, "u_1": False, "lat_2": False, "u_2": False, "interjet_min": False},
}

# The payload's state alphabet. Shipped to the page as `state_codes` so no state name is written
# into the HTML by hand (§B5.1).
STATE_CODES: dict[str, str] = {"double": "d", "single": "s", "none": "n"}

# §B5.1's rounding. Latitudes sit on the 0.25° grid, so 2 decimals is lossless; winds and the
# interjet minimum are rounded to 1 decimal, which is what "round-trips at the stated rounding"
# means for them.
LAT_DECIMALS = 2
WIND_DECIMALS = 1

SUMMARY_COLUMNS: tuple[str, ...] = (
    "year", "n_days", "n_double", "n_single", "n_none", "pct_double",
    "n_double_runs", "longest_double_run",
)
PCT_FORMAT = "%.4f"          # §B7: `pct_double` is written to four decimals

GRID_TOL = 1e-6              # `profile.GRID_TOL`, the tolerance G3's axis comparison inherits
THRESHOLD_TOL = 1e-9         # §B11 G6: the CSV carries full float precision, thresholds are exact

DATE_FORMAT = "%Y-%m-%d"     # `classify.DATE_FORMAT`; the CSV's `date` column is compared as text

SENTINEL_DATA = "__DJET_DATA_JSON__"
SENTINEL_META = "__DJET_META_JSON__"

# ---------------------------------------------------------------------------------------------
# the static chart: the mockup's annual axis, transcribed (§B8)
# ---------------------------------------------------------------------------------------------

SVG_W, SVG_H = 1100.0, 250.0
SVG_LEFT, SVG_RIGHT, SVG_TOP, SVG_BOTTOM = 46.0, 16.0, 14.0, 30.0
FIG_SIZE = (11.0, 2.5)
SAVE_DPI = 200

# 1100 units across 11 inches: one SVG user unit is 1/100 inch, hence 0.72 pt. Every stroke width,
# offset and font size below is the mockup's number times this factor, so the PNG is the SVG at a
# different resolution rather than a redrawing of it.
SVG_UNITS_PER_INCH = SVG_W / FIG_SIZE[0]
SVG_PT = 72.0 / SVG_UNITS_PER_INCH

LABEL_FONT_PT = 11.0 * SVG_PT       # `.axis text { font-size: 11px }`
RULE_WIDTH_PT = 1.0 * SVG_PT        # `.axis line`, SVG's default stroke width
SERIES_WIDTH_PT = 1.6 * SVG_PT      # `.series .ln { stroke-width: 1.6 }`
POINT_SIZE_PT = 2.0 * 3.5 * SVG_PT  # `.series .pt { r: 3.5 }`, as a marker diameter
Y_LABEL_GAP_PT = 8.0 * SVG_PT       # `x="${left - 8}"`
X_LABEL_DROP_PT = (SVG_BOTTOM - 8.0) * SVG_PT   # `y="${H - 8}"`, below the axes
TITLE_INSET_PT = 2.0 * SVG_PT       # the title sits in the 14-unit top margin

COLOR_BG = "#ffffff"        # --bg
COLOR_INK = "#1f2320"       # --ink
COLOR_MUTE = "#6f766f"      # --mute
COLOR_RULE = "#d9dcd8"      # --rule
COLOR_DOUBLE = "#1b9e77"    # --double


# ---------------------------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------------------------


def _attr(attrs: dict, name: str, path: Path):
    """One global attribute, or G4 naming it."""
    if name not in attrs:
        raise ValueError(
            f"explorer: {path} is missing the global attribute {name!r}; the method block and the "
            f"gates read {list(REQUIRED_ATTRS)} and none of them has a fallback"
        )
    return attrs[name]


def _json_attr(attrs: dict, name: str, path: Path):
    """One JSON-encoded global attribute, parsed, or G4 naming it."""
    raw = _attr(attrs, name, path)
    try:
        return json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"explorer: {path} records the global attribute {name!r} as {raw!r}, which is not the "
            f"JSON the intermediate's contract says it is ({exc})"
        ) from exc


def _key(mapping, key: str, attr_name: str, path: Path):
    """One key of a parsed JSON attribute, or G4 naming `attr.key`."""
    if not isinstance(mapping, dict) or key not in mapping:
        raise ValueError(
            f"explorer: {path} records the global attribute {attr_name!r} without the key "
            f"{key!r}; the method block reads {attr_name}.{key} and has no fallback"
        )
    return mapping[key]


def _hemisphere(value: float, negative: str, positive: str) -> str:
    """`-60 -> 60°W`, `30 -> 30°E`: sign becomes a hemisphere letter, never a minus sign."""
    if value == 0:
        return "0°"
    return f"{abs(value):g}°{negative if value < 0 else positive}"


def _lat_range(lat_min: float, lat_max: float) -> str:
    """`20–75°N`: one hemisphere letter when the band does not straddle the equator."""
    if lat_min >= 0 and lat_max >= 0:
        return f"{lat_min:g}–{lat_max:g}°N"
    if lat_min <= 0 and lat_max <= 0:
        return f"{abs(lat_max):g}–{abs(lat_min):g}°S"
    return f"{_hemisphere(lat_min, 'S', 'N')}–{_hemisphere(lat_max, 'S', 'N')}"


def _season_dates(year: int, months: Sequence[int]) -> list[str]:
    """That year's season as `YYYY-MM-DD` strings, ascending -- the vector G1 compares against."""
    out: list[str] = []
    for month in months:
        for day in range(1, calendar.monthrange(year, month)[1] + 1):
            out.append(f"{year:04d}-{month:02d}-{day:02d}")
    return out


def _month_ticks(months: Sequence[int]) -> tuple[list[int], list[str]]:
    """Day-of-season index of the 1st of each configured month, with its abbreviation.

    A non-leap reference year, exactly as `figure._month_ticks` does it: no configured month is
    February, so the offsets are the same for every season (I6, §B5.1). `run_explorer` asserts that
    premise per season rather than assuming it.
    """
    starts: list[int] = []
    labels: list[str] = []
    day = 0
    for month in months:
        starts.append(day)
        labels.append(calendar.month_abbr[month])
        day += calendar.monthrange(2001, month)[1]
    return starts, labels


def _runs(states: Sequence[str]) -> list[tuple[str, int, int, int]]:
    """Maximal runs of equal consecutive states as `(state, start, end, length)`.

    The mockup's `runs()`, transcribed: same maximality, same within-season scope, no wrap.
    """
    out: list[list] = []
    for i, state in enumerate(states):
        if out and out[-1][0] == state:
            out[-1][2] = i
        else:
            out.append([state, i, i])
    return [(state, start, end, end - start + 1) for state, start, end in out]


def _round_or_none(value, decimals: int):
    """`NaN -> None` (JSON has no NaN); everything else rounded and left to G9 to police.

    An infinity is deliberately *not* mapped to `None`: it reaches `json.dumps(allow_nan=False)`
    and raises there, rather than being silently written as a blank cell.
    """
    number = float(value)
    if math.isnan(number):
        return None
    return round(number, decimals)


# ---------------------------------------------------------------------------------------------
# the gates (§B11)
# ---------------------------------------------------------------------------------------------


def _assert_latitude_grid(lat: np.ndarray, sector: dict, path: Path) -> None:
    """G3: the recorded resolution is the coordinate's own step, and the whole axis matches (O6).

    Spacing alone would accept a shifted axis and `profile.open_intermediate` verifies only
    dimension names, so the endpoints are checked too -- the same comparison `profile._assert_grid`
    applies upstream, re-applied here against the file actually in hand.
    """
    resolution = float(_key(sector, "resolution", "sector", path))
    lat_min = float(_key(sector, "lat_min", "sector", path))
    lat_max = float(_key(sector, "lat_max", "sector", path))

    if lat.size < 2:
        raise ValueError(
            f"explorer: {path} has {lat.size} latitude(s); no grid step can be measured against "
            f"the recorded sector.resolution {resolution:g}"
        )
    steps = np.diff(lat)
    measured = float(steps[0])
    worst_step = int(np.argmax(np.abs(steps - measured)))
    if abs(steps[worst_step] - measured) > GRID_TOL:
        raise ValueError(
            f"explorer: {path}'s latitude coordinate is not uniformly spaced -- first step "
            f"{measured!r}, but step {worst_step} is {float(steps[worst_step])!r} "
            f"(sector.resolution records {resolution:g})"
        )
    if abs(measured - resolution) > GRID_TOL:
        raise ValueError(
            f"explorer: {path} records sector.resolution {resolution!r} but its latitude "
            f"coordinate steps by {measured!r} (first differing index 1: "
            f"{float(lat[0])!r} -> {float(lat[1])!r})"
        )

    expected = np.arange(lat_min, lat_max + resolution / 2, resolution)
    if expected.size != lat.size:
        raise ValueError(
            f"explorer: {path} has {lat.size} latitude(s) but sector {lat_min:g}..{lat_max:g} at "
            f"{resolution:g}° is {expected.size} point(s); first differing index "
            f"{min(lat.size, expected.size)}"
        )
    diff = np.abs(lat - expected)
    worst = int(np.argmax(diff))
    if diff[worst] > GRID_TOL:
        raise ValueError(
            f"explorer: {path}'s latitude coordinate is not the recorded sector's grid; first "
            f"differing index {int(np.argmax(diff > GRID_TOL))}, file has "
            f"{float(lat[int(np.argmax(diff > GRID_TOL))])!r}, sector "
            f"{lat_min:g}..{lat_max:g} at {resolution:g}° expects "
            f"{float(expected[int(np.argmax(diff > GRID_TOL))])!r} (max |diff| {diff[worst]:.3e})"
        )


def _assert_season_dates(got: Sequence[str], year: int, months: Sequence[int],
                         days_per_season: int, csv_path: Path) -> None:
    """G1: exactly that year's season, ascending, no duplicates.

    Modelled on `rda._assert_season_dates` and `profile._assert_time`. A bare row count would
    accept a duplicated, missing or reordered day, and every day index, tooltip and run length
    downstream of here is positional.
    """
    want = _season_dates(year, months)
    if len(want) != days_per_season:
        # Not a CSV defect: the configured season does not have a constant length in this year,
        # which the payload's per-season day indexing assumes (§B5.1, risk BR7).
        raise ValueError(
            f"explorer: season {year} of months {list(months)} is {len(want)} day(s) long, but "
            f"{csv_path}'s intermediate records days_per_season={days_per_season}"
        )
    got = list(got)
    if len(got) != len(want):
        raise ValueError(
            f"explorer: season {year} in {csv_path} holds {len(got)} day(s), expected {len(want)} "
            f"({want[0]} .. {want[-1]})"
        )
    if len(set(got)) != len(got):
        duplicated = sorted({d for d in got if got.count(d) > 1})[:5]
        raise ValueError(
            f"explorer: season {year} in {csv_path} holds {len(got)} day(s) with duplicate "
            f"date(s) {duplicated}"
        )
    if got != sorted(got):
        offender = next(b for a, b in zip(got, got[1:]) if b <= a)
        raise ValueError(
            f"explorer: season {year} in {csv_path} holds {len(got)} day(s) that are not in "
            f"ascending date order; first out-of-order date {offender}"
        )
    if got != want:
        first = next(g for g, w in zip(got, want) if g != w)
        expected = want[got.index(first)] if first in got else want[0]
        offenders = [(g, w) for g, w in zip(got, want) if g != w][:5]
        raise ValueError(
            f"explorer: season {year} in {csv_path} holds {len(got)} day(s) that are not the "
            f"configured season; first differing date {first} where {expected} was expected "
            f"(first mismatches, found vs expected: {offenders})"
        )


def _assert_states_and_nulls(states: pd.DataFrame, csv_path: Path) -> None:
    """G8: the state names are the classifier's three, and each one's blanks are exact."""
    state = states["state"]
    known = state.isin(tuple(STATE_CODES))
    if not known.all():
        row = int(np.argmax(~known.to_numpy()))
        raise ValueError(
            f"explorer: {csv_path} row {row + 2} ({states['date'].iloc[row]}) records state "
            f"{state.iloc[row]!r}, which is not one of {sorted(STATE_CODES)}"
        )
    present = {column: states[column].notna().to_numpy() for column in NUMERIC_COLUMNS}
    for name, contract in STATE_NULL_CONTRACT.items():
        rows = (state == name).to_numpy()
        for column, must_be_present in contract.items():
            wrong = rows & (present[column] != must_be_present)
            if wrong.any():
                row = int(np.argmax(wrong))
                verb = "is blank but must carry a value" if must_be_present else \
                       "carries a value but must be blank"
                raise ValueError(
                    f"explorer: {csv_path} fails the state/null contract at "
                    f"{states['date'].iloc[row]} -- state {name!r}, column {column!r} {verb} "
                    f"(a {name} day carries "
                    f"{sorted(c for c, keep in contract.items() if keep) or 'no core columns'})"
                )


def _assert_thresholds(states: pd.DataFrame, cfg: Config, csv_path: Path) -> None:
    """G6: every row still satisfies the detection thresholds in the config in hand.

    The three arms are `classify.py:124`, `:147` and `:153` read back off the CSV. They catch a
    *tightened* threshold; a loosened one leaves no inequality to violate, which is what §B15 BR1
    records and does not work around.
    """
    detection = cfg.detection
    date = states["date"]

    for column in ("u_1", "u_2"):
        values = states[column].to_numpy(dtype=float)
        violating = np.isfinite(values) & (values < detection.u_core_min - THRESHOLD_TOL)
        if violating.any():
            row = int(np.argmax(violating))
            raise ValueError(
                f"explorer: {csv_path} records a core below the configured threshold at "
                f"{date.iloc[row]} -- {column}={float(values[row])!r} < u_core_min "
                f"{detection.u_core_min:g} ({cfg.source_path})"
            )

    is_double = (states["state"] == "double").to_numpy()
    lat_1 = states["lat_1"].to_numpy(dtype=float)
    lat_2 = states["lat_2"].to_numpy(dtype=float)
    u_1 = states["u_1"].to_numpy(dtype=float)
    u_2 = states["u_2"].to_numpy(dtype=float)
    inter = states["interjet_min"].to_numpy(dtype=float)

    separation = lat_2 - lat_1
    violating = is_double & (separation < detection.separation_min_deg - THRESHOLD_TOL)
    if violating.any():
        row = int(np.argmax(violating))
        raise ValueError(
            f"explorer: {csv_path} records a double day whose cores are closer than the "
            f"configured separation at {date.iloc[row]} -- lat_2 - lat_1 = "
            f"{float(separation[row])!r} < separation_min_deg "
            f"{detection.separation_min_deg:g} ({cfg.source_path})"
        )

    ceiling = np.minimum(u_1, u_2) - detection.prominence_min
    violating = is_double & (inter > ceiling + THRESHOLD_TOL)
    if violating.any():
        row = int(np.argmax(violating))
        raise ValueError(
            f"explorer: {csv_path} records a double day whose interjet minimum is not prominent "
            f"enough at {date.iloc[row]} -- interjet_min={float(inter[row])!r} > "
            f"min(u_1, u_2) - prominence_min = {float(ceiling[row])!r} (prominence_min "
            f"{detection.prominence_min:g}, {cfg.source_path})"
        )


# ---------------------------------------------------------------------------------------------
# the two embedded blocks (§B5, §B6)
# ---------------------------------------------------------------------------------------------


def _method_block(cfg: Config, attrs: dict, sector: dict, profile_fields: dict,
                  months: Sequence[int], days_per_season: int,
                  year_first: int, year_last: int, path: Path) -> list[list]:
    """§B6's six rows as `[label, [parts]]` pairs -- the shape the mockup's renderer consumes.

    Every value is read from the intermediate's attributes, the config or the CSV. Nothing here is
    a literal standing in for a measured quantity, which is why the variable row renders the
    recorded `u_component_of_wind` rather than the mockup's prose "zonal wind u" (§B6, risk BR2).
    """
    source = _key(profile_fields, "source", "profile_fields", path)
    dataset_id = _attr(attrs, "source_dataset", path)
    if source == "rda_hourly":
        collection = f"ERA5, NCAR RDA {dataset_id}"
    elif source == "cds_derived":
        collection = f"ERA5, CDS {dataset_id}"
    else:
        raise ValueError(
            f"explorer: {path} records profile_fields.source {source!r}, which is neither "
            f"'rda_hourly' nor 'cds_derived'; the Data row has no phrasing for it"
        )

    variable = _attr(attrs, "variable", path)
    level = int(_attr(attrs, "pressure_level", path))
    level_units = _attr(attrs, "pressure_level_units", path)
    resolution = float(_key(sector, "resolution", "sector", path))

    statistic = str(_key(profile_fields, "daily_statistic", "profile_fields", path))
    hourly_times = list(_key(profile_fields, "hourly_times", "profile_fields", path))
    if not hourly_times:
        raise ValueError(
            f"explorer: {path} records profile_fields.hourly_times as empty; the Time row states "
            f"which analyses the {statistic} is taken over and has no fallback"
        )
    hours = ", ".join(str(t).split(":")[0] for t in hourly_times)

    detection = cfg.detection
    return [
        ["Data", [
            collection,
            f"{variable} at {level} {level_units}",
            f"{resolution:g}° grid",
        ]],
        ["Sector", [
            f"{_hemisphere(float(_key(sector, 'lon_min', 'sector', path)), 'W', 'E')}–"
            f"{_hemisphere(float(_key(sector, 'lon_max', 'sector', path)), 'W', 'E')} zonal mean",
            _lat_range(float(_key(sector, "lat_min", "sector", path)),
                       float(_key(sector, "lat_max", "sector", path))),
        ]],
        ["Time", [
            f"{calendar.month_name[months[0]]}–{calendar.month_name[months[-1]]}, "
            f"{year_first}–{year_last}",
            f"{statistic.replace('_', ' ')} of the {hours} UTC analyses",
        ]],
        ["Profile", [
            f"{detection.smooth_window_deg:g}° boxcar smoothing in latitude",
        ]],
        ["Double jet", [
            f"core u ≥ {detection.u_core_min:g} m s⁻¹",
            f"two cores ≥ {detection.separation_min_deg:g}° apart",
            f"minimum between them ≥ {detection.prominence_min:g} m s⁻¹ below the weaker core",
        ]],
        ["Each point", [
            f"share of the season's {days_per_season} days classified double jet",
        ]],
    ]


def _render_html(data_json: str, meta_json: str) -> str:
    """The mockup with its two data slots filled.

    Sentinels and `str.replace`, never `str.format`: the CSS and the script are full of braces and
    `${...}` and escaping every one of them would make the diff against `docs/mockup/` unreadable.
    """
    for sentinel in (SENTINEL_DATA, SENTINEL_META):
        if EXPLORER_TEMPLATE.count(sentinel) != 1:
            raise ValueError(
                f"explorer: the HTML template holds {EXPLORER_TEMPLATE.count(sentinel)} copies of "
                f"the sentinel {sentinel!r}, expected exactly one"
            )
    return EXPLORER_TEMPLATE.replace(SENTINEL_DATA, data_json).replace(SENTINEL_META, meta_json)


def _dumps(payload: dict, what: str) -> str:
    """§B5.1's encoding: compact, no bare `NaN` (G9), and `<` escaped so it cannot leave the tag."""
    try:
        text = json.dumps(payload, allow_nan=False, separators=(",", ":"))
    except ValueError as exc:
        raise ValueError(
            f"explorer: the {what} payload holds a value JSON cannot represent ({exc}); "
            f"NaN is mapped to null at build time, so this is an infinity in the CSV"
        ) from exc
    # `<` is a valid escape inside a JSON string and cannot terminate the <script> element,
    # whatever a path or a dataset id happens to contain (risk BR6).
    return text.replace("<", "\\u003c")


# ---------------------------------------------------------------------------------------------
# the static chart (§B8)
# ---------------------------------------------------------------------------------------------


def _render_annual_png(summary_path: Path, annual_path: Path, title: str,
                       log: logging.Logger) -> None:
    """`renderAnnual`'s top chart, from the summary CSV this build has just written.

    Geometry is the mockup's, converted once through `SVG_PT`. No trend line, no running mean, no
    second series, no grid beyond the 10 % rules -- the explorer's annual axis and nothing else.
    """
    summary = pd.read_csv(summary_path)
    years = [int(v) for v in summary["year"]]
    pct = [float(v) for v in summary["pct_double"]]
    if not years:
        raise ValueError(f"explorer: {summary_path} holds no seasons; the annual chart is empty")

    y0, y1 = min(years), max(years)
    span = max(1, y1 - y0)                                    # the mockup's Math.max(1, y1 - y0)
    ymax = min(100, math.ceil((max(pct) + 5) / 10) * 10)

    fig = plt.figure(figsize=FIG_SIZE)
    try:
        fig.patch.set_facecolor(COLOR_BG)
        ax = fig.add_axes([
            SVG_LEFT / SVG_W,
            SVG_BOTTOM / SVG_H,
            (SVG_W - SVG_LEFT - SVG_RIGHT) / SVG_W,
            (SVG_H - SVG_TOP - SVG_BOTTOM) / SVG_H,
        ])
        ax.set_xlim(y0, y0 + span)
        ax.set_ylim(0, ymax)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_facecolor("none")
        for spine in ax.spines.values():
            spine.set_visible(False)

        for p in range(0, ymax + 1, 10):
            ax.axhline(p, color=COLOR_RULE, linewidth=RULE_WIDTH_PT, zorder=1, clip_on=False)
            ax.annotate(f"{p}%", xy=(0.0, p), xycoords=("axes fraction", "data"),
                        xytext=(-Y_LABEL_GAP_PT, 0.0), textcoords="offset points",
                        ha="right", va="center", color=COLOR_MUTE, fontsize=LABEL_FONT_PT)
        for year in range(math.ceil(y0 / 5) * 5, y1 + 1, 5):
            ax.annotate(f"{year}", xy=(year, 0.0), xycoords=("data", "axes fraction"),
                        xytext=(0.0, -X_LABEL_DROP_PT), textcoords="offset points",
                        ha="center", va="baseline", color=COLOR_MUTE, fontsize=LABEL_FONT_PT)

        ax.plot(years, pct, color=COLOR_DOUBLE, linewidth=SERIES_WIDTH_PT,
                solid_joinstyle="round", zorder=2, clip_on=False)
        ax.plot(years, pct, linestyle="none", marker="o", markersize=POINT_SIZE_PT,
                markerfacecolor=COLOR_BG, markeredgecolor=COLOR_DOUBLE,
                markeredgewidth=SERIES_WIDTH_PT, zorder=3, clip_on=False)

        # The h1 sits above the chart in the HTML; the PNG travels alone, so the same sentence goes
        # into the mockup's 14-unit top margin at the axes' left edge.
        fig.text(SVG_LEFT / SVG_W, 1.0 - TITLE_INSET_PT / (SVG_H * SVG_PT), title,
                 ha="left", va="top", color=COLOR_INK, fontsize=LABEL_FONT_PT)

        annual_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(annual_path, dpi=SAVE_DPI, facecolor=fig.get_facecolor())
    finally:
        plt.close(fig)
    log.info("wrote %s (%.1f KB, %d season(s), y axis 0-%d%%)", annual_path,
             annual_path.stat().st_size / 1024, len(years), ymax)


# ---------------------------------------------------------------------------------------------
# the stage
# ---------------------------------------------------------------------------------------------


def run_explorer(
    cfg: Config,
    profile_path: Path,
    csv_path: Path,
    explorer_path: Path,
    summary_path: Path,
    annual_path: Path,
    log: logging.Logger,
) -> None:
    """Intermediate + states CSV -> the explorer, the season table and the annual chart (§B9).

    Every path is handed in; this module never builds one (plan §4.2). The summary table is written
    *before* the PNG, and the PNG is rendered by reading it back.
    """
    # Imported here, not at module scope: `cli` imports every stage module up front, and this stage
    # must not fail to load because an unrelated stage's dependency is missing (as `figure.py`
    # records). `classify` pulls in scipy for exactly that reason.
    from .classify import CSV_COLUMNS, ProfileMismatchError
    from .profile import open_intermediate

    profile_path = Path(profile_path)
    csv_path = Path(csv_path)
    explorer_path, summary_path, annual_path = (
        Path(explorer_path), Path(summary_path), Path(annual_path))

    # -- 1. the intermediate: G2, G3, G4 --------------------------------------------------------
    with open_intermediate(profile_path) as dataset:
        attrs = dict(dataset.attrs)
        lat = np.asarray(dataset["latitude"].values, dtype=float)

    for name in REQUIRED_ATTRS:
        _attr(attrs, name, profile_path)
    parsed = {name: _json_attr(attrs, name, profile_path) for name in JSON_ATTRS}
    sector, profile_fields = parsed["sector"], parsed["profile_fields"]
    for name, keys in (("sector", SECTOR_KEYS), ("profile_fields", PROFILE_FIELD_KEYS)):
        for key in keys:
            _key(parsed[name], key, name, profile_path)

    # G2. These eight lines are `classify.py:343-352` repeated on purpose (§B9): factoring them
    # into a shared helper would mean editing the classifier, which D3's addendum and this one both
    # hold untouched. Detection thresholds are outside this hash by design (plan §4.3), so a
    # threshold change never lands here -- G6 below is what checks those.
    recorded = attrs.get("profile_sha256")
    if recorded != cfg.profile_sha256:
        raise ProfileMismatchError(
            "profile hash check failed: "
            f"{profile_path} records profile_sha256={recorded!r}, but {cfg.source_path} "
            f"hashes to {cfg.profile_sha256!r}. The intermediate was built from a different "
            "sector, level, season or year range -- rebuild it with the `profile` stage, or "
            "build the explorer with the config it was built from. Detection thresholds are "
            "excluded from this hash by design (plan §4.3), so a threshold change never lands here."
        )

    _assert_latitude_grid(lat, sector, profile_path)          # G3

    months = [int(m) for m in parsed["season_months"]]
    attr_years = [int(y) for y in parsed["years"]]
    days_per_season = int(_attr(attrs, "days_per_season", profile_path))
    if not months:                                            # G5
        raise ValueError(
            f"explorer: {profile_path} records season_months as empty; the month ticks and the "
            f"day-of-season index have no definition without it")
    gaps = [(a, b) for a, b in zip(months, months[1:]) if b != a + 1]
    if gaps:
        raise ValueError(
            f"explorer: {profile_path} records season_months {months}, which is not consecutive "
            f"(first gap {gaps[0][0]} -> {gaps[0][1]}); the day-of-season index assumes the "
            f"season is one unbroken run of whole months")

    # -- 2. the CSV: G7 -------------------------------------------------------------------------
    columns = tuple(str(c) for c in pd.read_csv(csv_path, nrows=0).columns)
    if columns != tuple(CSV_COLUMNS):
        missing = [c for c in CSV_COLUMNS if c not in columns]
        extra = [c for c in columns if c not in CSV_COLUMNS]
        raise ValueError(
            f"explorer: {csv_path} column check failed -- missing {missing}, unexpected {extra}; "
            f"expected exactly {list(CSV_COLUMNS)} in that order, found {list(columns)}"
        )
    if tuple(c for c in CSV_COLUMNS if c not in ("date", "state")) != NUMERIC_COLUMNS:
        raise ValueError(
            f"explorer: classify.CSV_COLUMNS is {list(CSV_COLUMNS)}, whose numeric columns are no "
            f"longer {list(NUMERIC_COLUMNS)}; this module's payload schema has drifted from it"
        )
    # Declared dtypes, not inferred: an all-blank `lat_2` (a season with no double day) would
    # otherwise arrive as a string column -- `figure.py`'s lesson.
    states = pd.read_csv(csv_path, dtype={c: float for c in NUMERIC_COLUMNS})
    states["date"] = states["date"].astype(str)
    try:
        dates = pd.to_datetime(states["date"], format=DATE_FORMAT)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"explorer: {csv_path} holds a date that is not {DATE_FORMAT} ({exc})"
        ) from exc
    season_of_row = np.asarray(pd.DatetimeIndex(dates).year, dtype=int)
    csv_years = sorted(set(int(y) for y in season_of_row))

    if csv_years != sorted(attr_years):                       # G5
        difference = sorted(set(csv_years) ^ set(attr_years))
        raise ValueError(
            f"explorer: {csv_path} holds seasons {csv_years[:3]}..{csv_years[-3:]} "
            f"({len(csv_years)}) but {profile_path} records years "
            f"{sorted(attr_years)[:3]}..{sorted(attr_years)[-3:]} ({len(attr_years)}); "
            f"symmetric difference {difference}"
        )

    # -- 3. seasons: G1, G8 ---------------------------------------------------------------------
    blocks: dict[int, pd.DataFrame] = {}
    for year in csv_years:
        block = states[season_of_row == year]
        _assert_season_dates(block["date"].tolist(), year, months, days_per_season, csv_path)
        blocks[year] = block
    _assert_states_and_nulls(states, csv_path)

    # -- 4. the thresholds: G6 ------------------------------------------------------------------
    _assert_thresholds(states, cfg, csv_path)

    # -- 5. the summary table (§B7) -------------------------------------------------------------
    rows = []
    for year in csv_years:
        block = blocks[year]
        day_states = block["state"].tolist()
        counts = {name: day_states.count(name) for name in STATE_CODES}
        if sum(counts.values()) != len(day_states):
            raise ValueError(
                f"explorer: season {year} in {csv_path} has {len(day_states)} day(s) but its "
                f"state counts sum to {sum(counts.values())} {counts}"
            )
        double_runs = [run for run in _runs(day_states) if run[0] == "double"]
        rows.append({
            "year": year,
            "n_days": len(day_states),
            "n_double": counts["double"],
            "n_single": counts["single"],
            "n_none": counts["none"],
            "pct_double": 100.0 * counts["double"] / len(day_states),
            "n_double_runs": len(double_runs),
            "longest_double_run": max((run[3] for run in double_runs), default=0),
        })
    summary = pd.DataFrame(rows, columns=list(SUMMARY_COLUMNS))
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(summary_path, index=False, float_format=PCT_FORMAT)
    log.info("wrote %s (%d season(s), columns %s)", summary_path, len(summary),
             ",".join(SUMMARY_COLUMNS))

    # -- 6. the two JSON blocks and the HTML (§B5, §B6, §B3) ------------------------------------
    month_starts, month_labels = _month_ticks(months)
    payload = {
        "days_per_season": days_per_season,
        "first_month": months[0],
        "month_starts": month_starts,
        "month_labels": month_labels,
        "lat_range": [float(sector["lat_min"]), float(sector["lat_max"])],
        "state_codes": {code: name for name, code in STATE_CODES.items()},
        "seasons": [],
    }
    for year in csv_years:
        block = blocks[year]
        payload["seasons"].append({
            "year": year,
            "state": "".join(STATE_CODES[s] for s in block["state"]),
            "lat_1": [_round_or_none(v, LAT_DECIMALS) for v in block["lat_1"]],
            "u_1": [_round_or_none(v, WIND_DECIMALS) for v in block["u_1"]],
            "lat_2": [_round_or_none(v, LAT_DECIMALS) for v in block["lat_2"]],
            "u_2": [_round_or_none(v, WIND_DECIMALS) for v in block["u_2"]],
            "interjet_min": [_round_or_none(v, WIND_DECIMALS) for v in block["interjet_min"]],
        })

    year_first, year_last = csv_years[0], csv_years[-1]
    meta = {
        # The mockup's h1 prose with only the year range substituted (§B3 item 4): "North
        # Atlantic–Europe" and "extended summer" are layout prose, not method-block fields.
        "title": "Double-jet frequency over the North Atlantic–Europe sector, extended summer "
                 f"{year_first}–{year_last}",
        "source_csv": csv_path.name,
        "method": _method_block(cfg, attrs, sector, profile_fields, months, days_per_season,
                                year_first, year_last, profile_path),
    }

    data_json = _dumps(payload, "djet-data")                  # G9
    meta_json = _dumps(meta, "djet-meta")                     # G9
    html = _render_html(data_json, meta_json)
    explorer_path.parent.mkdir(parents=True, exist_ok=True)
    explorer_path.write_text(html, encoding="utf-8")
    log.info("wrote %s (%.1f KB)", explorer_path, explorer_path.stat().st_size / 1024)

    # -- 7. the annual chart, from the table just written (§B8) ---------------------------------
    _render_annual_png(summary_path, annual_path, meta["title"], log)

    # -- 8. the log (§B9) -----------------------------------------------------------------------
    totals = {name: int((states["state"] == name).sum()) for name in STATE_CODES}
    log.info("explorer: %d season(s) x %d day(s) = %d rows -- double %d, single %d, none %d",
             len(csv_years), days_per_season, len(states),
             totals["double"], totals["single"], totals["none"])
    log.info("explorer: djet-data %d bytes, djet-meta %d bytes, HTML %d bytes",
             len(data_json.encode("utf-8")), len(meta_json.encode("utf-8")),
             len(html.encode("utf-8")))
    log.info("explorer: wrote %s, %s and %s", explorer_path, summary_path, annual_path)


# ---------------------------------------------------------------------------------------------
# `docs/mockup/double_jet_explorer_v2.html`, transcribed with exactly §B3's changes.
#
# Kept verbatim: every CSS rule and custom property, the DOM skeleton, `runs`, `stat`,
# `renderAnnual`, `renderDetail`, both tooltip formats, the legend, the `.foot` sentence, the
# prev/next buttons and the arrow-key handlers, the initial selection of 2018, and the mockup's own
# `// ---------- ... ----------` markers, so a diff against `docs/mockup/` stays readable.
#
# Changed: the data arrives in two `<script type="application/json">` blocks; `META`, the h1 and
# `#srcname` are filled from them; `NDAYS`, `MONTH_STARTS`, `MONTHS` and `LAT` come from the
# payload; `renderDetail`'s latitude gridlines run `LAT[0]..LAT[1]`; the `<title>` drops the mockup
# suffix. Removed, not hidden: `#file`, `#regen`, their handlers and CSS, `parseCSV`, `genToy`,
# `rng`, `gauss` and `seed`.
# ---------------------------------------------------------------------------------------------

EXPLORER_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Double-jet frequency, North Atlantic–Europe</title>
<style>
  :root{
    --bg:#ffffff; --ink:#1f2320; --mute:#6f766f; --rule:#d9dcd8; --hover:#f2f4f1;
    --double:#1b9e77; --single:#d95f02; --none:#ebece9;
    --sans: "Inter", -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  }
  *{ box-sizing:border-box; }
  body{ margin:0; background:var(--bg); color:var(--ink); font:14px/1.45 var(--sans); }
  main{ max-width:1180px; margin:0 auto; padding:28px 24px 60px; }
  h1{ font-size:20px; font-weight:600; margin:0 0 6px; letter-spacing:-0.01em; }
  .method{ display:grid; grid-template-columns:max-content 1fr; gap:2px 14px; margin:0 0 10px; max-width:96ch; }
  .method dt{ color:var(--mute); }
  .method dd{ margin:0; }
  .method dd span{ white-space:nowrap; }
  .method dd span + span::before{ content:"·"; color:var(--mute); margin:0 8px; }
  .src{ color:var(--mute); margin:0 0 14px; display:flex; gap:14px; align-items:center; flex-wrap:wrap; }

  svg{ display:block; width:100%; height:auto; font-family:var(--sans); }
  .axis line{ stroke:var(--rule); }
  .axis text, .series text{ fill:var(--mute); font-size:11px; }
  .series .ln{ fill:none; stroke:var(--double); stroke-width:1.6; stroke-linejoin:round; }
  .series .pt{ fill:#fff; stroke:var(--double); stroke-width:1.6; cursor:pointer; }
  .series .pt:hover{ fill:var(--double); }
  .series .pt.sel{ fill:var(--double); r:5; }
  .series .hit{ fill:transparent; cursor:pointer; }
  .series .hit:hover + .pt{ fill:var(--double); }

  h2{ font-size:16px; font-weight:600; margin:30px 0 2px; display:flex; align-items:baseline; gap:12px; }
  h2 .nav{ display:inline-flex; gap:4px; }
  h2 .nav button{ font:inherit; font-size:12px; padding:2px 8px; border:1px solid var(--rule); border-radius:4px; background:#fff; cursor:pointer; }
  h2 .nav button:hover{ background:var(--hover); }
  .detail-note{ color:var(--mute); margin:0 0 10px; }
  .legend{ display:flex; gap:18px; align-items:center; color:var(--mute); margin:0 0 6px; }
  .sw{ display:inline-block; width:12px; height:12px; border-radius:50%; vertical-align:-1px; margin-right:6px; }
  .detail .core{ stroke:#fff; stroke-width:0.8; }
  .detail .link{ fill:none; stroke-width:1.2; stroke-linecap:round; }
  .detail .bridge{ stroke:var(--double); stroke-opacity:0.35; stroke-width:1; }

  #tip{ position:fixed; pointer-events:none; background:var(--ink); color:#fff; padding:6px 9px; border-radius:4px;
        font-size:12px; line-height:1.4; white-space:nowrap; display:none; z-index:10; }
  #tip b{ font-weight:600; }
  .foot{ color:var(--mute); margin-top:34px; font-size:13px; max-width:72ch; }
</style>
</head>
<body>
<main>
  <h1 id="title"></h1>
  <dl class="method" id="method"></dl>
  <p class="src"><span id="srcname"></span></p>

  <svg id="annual" role="img" aria-label="Percentage of season days classified double jet, per season"></svg>

  <h2><span id="dtitle">Season</span>
    <span class="nav"><button id="prev" type="button" aria-label="previous season">◀</button><button id="next" type="button" aria-label="next season">▶</button></span>
  </h2>
  <p class="detail-note" id="dnote"></p>
  <div class="legend">
    <span><i class="sw" style="background:var(--double)"></i>double jet, both cores</span>
    <span><i class="sw" style="background:var(--single)"></i>single jet</span>
    <span>no marker: no core above threshold</span>
  </div>
  <svg id="detail" class="detail" role="img" aria-label="Core latitudes for the selected season"></svg>

  <p class="foot">Click a point in the top chart, or use ← → to step through seasons. Lines join consecutive days in the same state; vertical ties join the two cores of one day.</p>
</main>
<div id="tip"></div>

<script id="djet-data" type="application/json">__DJET_DATA_JSON__</script>
<script id="djet-meta" type="application/json">__DJET_META_JSON__</script>

<script>
(() => {
  // ---------- the embedded payload: double_jet/explorer.py writes it, nothing here loads ----------
  const DATA = JSON.parse(document.getElementById("djet-data").textContent);
  const METADATA = JSON.parse(document.getElementById("djet-meta").textContent);
  document.getElementById("title").textContent = METADATA.title;
  document.getElementById("srcname").textContent = METADATA.source_csv;

  // ---------- metadata: production fills this from the intermediate's attributes ----------
  const META = METADATA.method;   // label → parts; explorer.py read every value, none is a literal
  document.getElementById("method").innerHTML =
    META.map(([k, parts]) => `<dt>${k}</dt><dd>${parts.map(t => `<span>${t}</span>`).join("")}</dd>`).join("");

  const NDAYS = DATA.days_per_season, MONTH_STARTS = DATA.month_starts, MONTHS = DATA.month_labels;
  const COLOR = { double: "var(--double)", single: "var(--single)" };
  const LAT = DATA.lat_range;

  // ---------- hydration: the columnar payload → the per-day objects the renderers consume ----------
  // `v === null ? NaN : v` is load-bearing, not defensive: isFinite(null) is TRUE in JavaScript,
  // so a null latitude passed straight through would draw a core at 0 °N instead of drawing
  // nothing. Every isFinite guard in renderDetail depends on this one line.
  const num = v => v === null ? NaN : v;
  const seasons = DATA.seasons.map(s => ({
    year: s.year,
    days: Array.from({ length: NDAYS }, (_, d) => ({
      d,
      date: new Date(Date.UTC(s.year, DATA.first_month - 1, 1 + d)).toISOString().slice(0, 10),
      state: DATA.state_codes[s.state[d]],
      lat1: num(s.lat_1[d]), u1: num(s.u_1[d]),
      lat2: num(s.lat_2[d]), u2: num(s.u_2[d]), inter: num(s.interjet_min[d]),
    })),
  }));

  function runs(states) {
    const out = [];
    for (let i = 0; i < states.length; i++) {
      const last = out[out.length - 1];
      if (last && last.state === states[i]) last.end = i; else out.push({ state: states[i], start: i, end: i });
    }
    for (const r of out) r.len = r.end - r.start + 1;
    return out;
  }

  // ---------- state ----------
  let selected = 2018;
  const $ = id => document.getElementById(id), tip = $("tip");
  const stat = s => {
    const st = s.days.map(x => x.state), rs = runs(st).filter(r => r.state === "double");
    const nD = st.filter(x => x === "double").length;
    return { nD, pct: 100 * nD / NDAYS, nRuns: rs.length, longest: rs.length ? Math.max(...rs.map(r => r.len)) : 0 };
  };

  // ---------- annual line chart ----------
  function renderAnnual() {
    const left = 46, right = 16, top = 14, bottom = 30, W = 1100, H = 250, plotH = H - top - bottom;
    const ys = seasons.map(s => s.year), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const x = yr => left + (yr - y0) / Math.max(1, y1 - y0) * (W - left - right);
    const vals = seasons.map(stat);
    const ymax = Math.min(100, Math.ceil((Math.max(...vals.map(v => v.pct)) + 5) / 10) * 10);
    const y = p => top + (1 - p / ymax) * plotH;
    let out = `<g class="axis">`;
    for (let p = 0; p <= ymax; p += 10) out += `<line x1="${left}" x2="${W - right}" y1="${y(p)}" y2="${y(p)}"/><text x="${left - 8}" y="${y(p) + 4}" text-anchor="end">${p}%</text>`;
    for (let yr = Math.ceil(y0 / 5) * 5; yr <= y1; yr += 5) out += `<text x="${x(yr)}" y="${H - 8}" text-anchor="middle">${yr}</text>`;
    out += `</g><g class="series">`;
    out += `<path class="ln" d="${seasons.map((s, i) => (i ? "L" : "M") + x(s.year) + " " + y(vals[i].pct)).join("")}"/>`;
    seasons.forEach((s, i) => {
      out += `<circle class="hit" data-year="${s.year}" cx="${x(s.year)}" cy="${y(vals[i].pct)}" r="9"/>`;
      out += `<circle class="pt${s.year === selected ? " sel" : ""}" data-year="${s.year}" cx="${x(s.year)}" cy="${y(vals[i].pct)}" r="${s.year === selected ? 5 : 3.5}"/>`;
    });
    out += `</g>`;
    const svg = $("annual");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.innerHTML = out;
    svg.querySelectorAll("circle").forEach(c => {
      const yr = +c.dataset.year, v = vals[seasons.findIndex(s => s.year === yr)];
      c.addEventListener("click", () => { selected = yr; renderAnnual(); renderDetail(); });
      c.addEventListener("mousemove", ev => {
        tip.innerHTML = `<b>${yr}</b> · ${v.pct.toFixed(1)}% · ${v.nD} double-jet days in ${v.nRuns} runs, longest ${v.longest} d`;
        tip.style.display = "block"; tip.style.left = (ev.clientX + 14) + "px"; tip.style.top = (ev.clientY + 14) + "px";
      });
      c.addEventListener("mouseleave", () => tip.style.display = "none");
    });
  }

  // ---------- detail: core latitudes for one season ----------
  function renderDetail() {
    const s = seasons.find(v => v.year === selected) || seasons[0]; selected = s.year;
    const left = 46, top = 14, right = 16, bottom = 26, plotH = 250, W = 1100, H = top + plotH + bottom;
    const cw = (W - left - right) / NDAYS, x = d => left + (d + 0.5) * cw;
    const y = lat => top + (LAT[1] - lat) / (LAT[1] - LAT[0]) * plotH;
    let out = `<g class="axis">`;
    for (let lat = LAT[0]; lat <= LAT[1]; lat += 10) out += `<line x1="${left}" x2="${W - right}" y1="${y(lat)}" y2="${y(lat)}"/><text x="${left - 6}" y="${y(lat) + 4}" text-anchor="end">${lat}°N</text>`;
    MONTH_STARTS.forEach((d, k) => { out += `<line x1="${left + d * cw}" x2="${left + d * cw}" y1="${top}" y2="${top + plotH}"/><text x="${left + d * cw + 4}" y="${H - 8}">${MONTHS[k]}</text>`; });
    out += `</g>`;
    const pt = (day, k) => { const lat = k === 1 ? day.lat1 : day.lat2; return isFinite(lat) ? { x: x(day.d), y: y(lat) } : null; };
    const cores = day => day.state === "double" ? [1, 2] : day.state === "single" && isFinite(day.lat1) ? [1] : [];
    let links = "", bridges = "", dots = "";
    s.days.forEach((day, d) => {
      const st = day.state, ks = cores(day);
      if (ks.length === 2) { const a = pt(day, 1), b = pt(day, 2); if (a && b) bridges += `<line class="bridge" x1="${a.x}" x2="${b.x}" y1="${a.y}" y2="${b.y}"/>`; }
      for (const k of ks) {
        const p = pt(day, k); if (!p) continue;
        dots += `<circle class="core" cx="${p.x}" cy="${p.y}" r="2.6" fill="${COLOR[st]}"/>`;
        const nd = s.days[d + 1];
        if (nd && nd.state === st) { const q = pt(nd, k); if (q) links += `<line class="link" x1="${p.x}" y1="${p.y}" x2="${q.x}" y2="${q.y}" stroke="${COLOR[st]}"/>`; }
      }
    });
    const svg = $("detail");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.innerHTML = out + bridges + links + dots;
    // hover: day readout
    svg.onmousemove = ev => {
      const r = svg.getBoundingClientRect(), d = Math.floor(((ev.clientX - r.left) * W / r.width - left) / cw);
      if (d < 0 || d >= NDAYS) { tip.style.display = "none"; return; }
      const day = s.days[d], lat = v => isFinite(v) ? v.toFixed(1) + "°N" : "–";
      tip.innerHTML = `<b>${day.date || s.year + " day " + d}</b> · ${day.state}<br>` +
        (day.state === "double" ? `cores ${lat(day.lat1)} / ${lat(day.lat2)} · min between ${isFinite(day.inter) ? day.inter.toFixed(0) : "–"} m/s` :
         day.state === "single" ? `core ${lat(day.lat1)}` : "no core");
      tip.style.display = "block"; tip.style.left = (ev.clientX + 14) + "px"; tip.style.top = (ev.clientY + 14) + "px";
    };
    svg.onmouseleave = () => tip.style.display = "none";
    const v = stat(s);
    $("dtitle").textContent = `${s.year}`;
    $("dnote").textContent = `${v.nD} double-jet days (${v.pct.toFixed(0)}% of the season) in ${v.nRuns} runs; longest ${v.longest} d.`;
  }

  // ---------- wiring ----------
  const rerender = () => { renderAnnual(); renderDetail(); };
  const step = k => { const i = seasons.findIndex(s => s.year === selected); selected = seasons[Math.min(seasons.length - 1, Math.max(0, i + k))].year; rerender(); };
  $("prev").addEventListener("click", () => step(-1));
  $("next").addEventListener("click", () => step(1));
  document.addEventListener("keydown", e => { if (e.key === "ArrowLeft") step(-1); if (e.key === "ArrowRight") step(1); });
  rerender();
})();
</script>
</body>
</html>
"""
