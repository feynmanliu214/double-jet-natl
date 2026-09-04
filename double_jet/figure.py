"""Panels: the smoothed zonal-mean profile as a background, the classified jet cores on top.

Plan §4.5 and interpretation I6. Two instances, both named by `cli.output_names` (plan §4.2's
table) and never by this module:

* smoke -- one panel, one `.png`.
* campaign -- 47 seasons in an 8 x 6 grid (48 cells, the last blank), saved to a `.pdf` and a
  `.png`.

Two decisions this module is the sole owner of, both recorded here because they are not obvious:

* **The x axis is a day-of-season index 0..152, not a calendar day-of-year** (I6). 1 May's
  day-of-year is 121 in a common year and 122 in a leap year, so a day-of-year axis would smear
  the 47 seasons against each other by one day; counting from 1 May makes the axis identical for
  every season, because no configured month contains 29 February.
* **Every `pcolormesh` is `rasterized=True`** (risk R6). The campaign figure draws
  47 x 153 x 221 ~ 1.6 M quads; as vector paths that is a PDF no reader will open, and M7 requires
  it under 20 MB. Rasterizing only the background keeps the axes, cores, labels and legend vector.

The background is the **smoothed** profile -- the same array `classify.py` detects on -- so that a
core sits on the maximum the eye sees. The cached intermediate stays unsmoothed (plan §4.2), so the
smoothing is redone here rather than read.
"""

from __future__ import annotations

import calendar
import logging
from pathlib import Path

import matplotlib

# Before pyplot: these run inside a Slurm job with no DISPLAY, where the default interactive
# backend would fail at import time rather than at draw time (plan §4.5).
matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402  -- must follow matplotlib.use
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from .config import Config  # noqa: E402

# 47 seasons -> ceil(47 / 6) = 8 rows, i.e. §4.5's 8 x 6 grid. The column count is the constant and
# the row count follows from the seasons actually present, so a --years subset still lays out.
MAX_PANEL_COLS = 6

# Sequential greys: the background must stay visually subordinate to the coloured cores.
BACKGROUND_CMAP = "Greys"

# Colour-blind-safe pair (Dark2); `none` days are deliberately absent, so they draw blank.
STATE_COLORS = {"single": "#d95f02", "double": "#1b9e77"}

# The rasterized background is resampled at the save dpi, so this fixes both the PNG's resolution
# and the PDF's embedded image size. 150 keeps the campaign PDF an order of magnitude under M7's
# limit while a single panel still reads at 100% zoom.
SAVE_DPI = 150

PDF_SIZE_LIMIT_MB = 20.0  # deliverable M7

# Exactly the columns classify.py writes (§4.3); read here so a silent schema drift is caught.
STATES_COLUMNS = ("date", "state", "lat_1", "u_1", "lat_2", "u_2", "interjet_min")
STATES_NUMERIC_COLUMNS = ("lat_1", "u_1", "lat_2", "u_2", "interjet_min")


def _grid_shape(n_seasons: int) -> tuple[int, int]:
    """(nrows, ncols) for `n_seasons` panels: 47 -> (8, 6), the shape §4.5 names."""
    if n_seasons < 1:
        raise ValueError(f"figure: no seasons to plot (found {n_seasons})")
    ncols = min(MAX_PANEL_COLS, n_seasons)
    nrows = -(-n_seasons // ncols)  # ceiling division
    return nrows, ncols


def _month_ticks(cfg: Config) -> tuple[list[int], list[str]]:
    """Day-of-season index of the 1st of each configured month, with its abbreviation.

    Uses a non-leap reference year: no configured month is February, so the lengths -- and hence
    the tick positions -- are the same for every season (I6).
    """
    positions: list[int] = []
    labels: list[str] = []
    day = 0
    for month in cfg.season_months:
        positions.append(day)
        labels.append(calendar.month_abbr[month])
        day += calendar.monthrange(2001, month)[1]
    return positions, labels


def _day_of_season(dates: pd.DatetimeIndex, cfg: Config) -> np.ndarray:
    """Days elapsed since the 1st of the season's first month, 0..`days_per_season`-1 (I6)."""
    first_month = cfg.season_months[0]
    starts = pd.to_datetime(
        pd.DataFrame({"year": np.asarray(dates.year), "month": first_month, "day": 1})
    )
    index = (dates - pd.DatetimeIndex(starts)).days.to_numpy()
    bad_month = ~np.isin(np.asarray(dates.month), np.asarray(cfg.season_months))
    out_of_range = (index < 0) | (index >= cfg.days_per_season)
    if bad_month.any() or out_of_range.any():
        offender = dates[bad_month | out_of_range][0]
        raise ValueError(
            f"figure: day-of-season index check failed -- {offender:%Y-%m-%d} is not within the "
            f"configured season (months {list(cfg.season_months)}, "
            f"{cfg.days_per_season} days from the 1st of month {first_month})"
        )
    return index


def _cell_edges(centres: np.ndarray) -> np.ndarray:
    """Quad edges for `pcolormesh` from cell centres, half a step beyond at each end."""
    mid = 0.5 * (centres[:-1] + centres[1:])
    return np.concatenate(([2 * centres[0] - mid[0]], mid, [2 * centres[-1] - mid[-1]]))


def run_figure(
    cfg: Config,
    profile_path: Path,
    csv_path: Path,
    panels: tuple[Path, ...],
    smoke: bool,
    log: logging.Logger,
) -> None:
    """Draw one panel per season and save the same figure to every path in `panels`.

    `panels` comes from `cli.output_names`; this module never builds an output path (plan §4.2).
    """
    # Imported here, not at module scope: `cli` imports every stage module up front, and the
    # figure stage must not fail to load because an unrelated stage's dependency is missing.
    from .classify import smooth
    from .profile import open_intermediate

    if not panels:
        raise ValueError("figure: run_figure was given no output paths")
    outputs = tuple(Path(p) for p in panels)

    with open_intermediate(profile_path) as ds:
        lat = np.asarray(ds["latitude"].values, dtype=float)
        times = pd.DatetimeIndex(np.asarray(ds["time"].values))
        u_smooth = smooth(np.asarray(ds["U"].values, dtype=float), cfg.smooth_window_points)

    if u_smooth.shape != (times.size, lat.size):
        raise ValueError(
            f"figure: smoothed profile shape check failed -- got {u_smooth.shape}, expected "
            f"{(times.size, lat.size)} from {profile_path}"
        )

    day = _day_of_season(times, cfg)
    season = np.asarray(times.year)
    seasons = np.unique(season)
    if smoke and seasons.size != 1:
        log.warning("figure: --smoke expects one season, %s holds %d (%s)",
                    profile_path, seasons.size, ", ".join(str(y) for y in seasons))

    # Declared dtypes, not inferred: an all-blank `lat_2` (a season with no double day) would
    # otherwise arrive as a string column and the scatter would fail on a file that is correct.
    states = pd.read_csv(csv_path, dtype={c: float for c in STATES_NUMERIC_COLUMNS})
    missing = [c for c in STATES_COLUMNS if c not in states.columns]
    if missing:
        raise ValueError(
            f"figure: states CSV column check failed -- {csv_path} is missing {missing}; "
            f"expected exactly {list(STATES_COLUMNS)}"
        )
    state_dates = pd.DatetimeIndex(pd.to_datetime(states["date"], format="%Y-%m-%d"))
    states = states.assign(_day=_day_of_season(state_dates, cfg), _season=np.asarray(
        state_dates.year))
    unknown = sorted(set(states["state"].dropna().unique()) - set(STATE_COLORS) - {"none"})
    if unknown:
        log.warning("figure: states CSV holds unplotted state(s) %s", unknown)
    if len(states) != times.size:
        log.warning("figure: %s holds %d rows but %s holds %d days; the background is drawn "
                    "from the profile and the cores from the CSV, so a day present in only "
                    "one of them shows only that half", csv_path, len(states), profile_path,
                    times.size)

    nrows, ncols = _grid_shape(seasons.size)
    single = seasons.size == 1
    cell_w, cell_h = (9.5, 5.6) if single else (2.7, 1.9)
    title_size, tick_size, marker_size = (12, 10, 14) if single else (7, 6, 2.0)

    fig, axes = plt.subplots(
        nrows, ncols,
        figsize=(cell_w * ncols, cell_h * nrows),
        sharex=True, sharey=True,       # M7: one axis for all panels, so seasons compare by eye
        squeeze=False, layout="constrained",
    )
    flat = axes.ravel()

    x_edges = _cell_edges(np.arange(cfg.days_per_season, dtype=float))
    y_edges = _cell_edges(lat)
    vmin, vmax = float(np.nanmin(u_smooth)), float(np.nanmax(u_smooth))
    tick_positions, tick_labels = _month_ticks(cfg)

    mesh = None
    for ax, year in zip(flat, seasons):
        # A NaN-filled block indexed by day-of-season, not by row order: a season with a missing
        # day then leaves that column blank instead of shifting the rest of the season sideways.
        block = np.full((cfg.days_per_season, lat.size), np.nan)
        rows = season == year
        block[day[rows], :] = u_smooth[rows, :]
        mesh = ax.pcolormesh(
            x_edges, y_edges, block.T,
            cmap=BACKGROUND_CMAP, vmin=vmin, vmax=vmax, shading="flat",
            rasterized=True,            # risk R6 -- see the module docstring
        )

        panel = states[states["_season"] == year]
        for state, colour in STATE_COLORS.items():
            sub = panel[panel["state"] == state]
            if sub.empty:
                continue
            # Both cores are drawn on a double day; lat_2 is blank (NaN) on a single day and
            # matplotlib simply does not draw a NaN point, so one call covers both.
            xs = np.concatenate([sub["_day"].to_numpy(), sub["_day"].to_numpy()])
            ys = np.concatenate([sub["lat_1"].to_numpy(dtype=float),
                                 sub["lat_2"].to_numpy(dtype=float)])
            ax.scatter(xs, ys, s=marker_size, c=colour, marker="o", linewidths=0, zorder=3)

        ax.set_title(str(year), fontsize=title_size, pad=2)
        ax.set_xlim(x_edges[0], x_edges[-1])
        ax.set_ylim(cfg.sector.lat_min, cfg.sector.lat_max)
        ax.set_xticks(tick_positions)
        ax.set_xticklabels(tick_labels)
        ax.set_yticks(np.arange(cfg.sector.lat_min, cfg.sector.lat_max + 1e-9, 10.0))
        ax.tick_params(labelsize=tick_size, length=2, pad=1)

    for ax in flat[seasons.size:]:
        ax.set_visible(False)           # 47 seasons in 48 cells: the last stays blank (§4.5)

    cbar = fig.colorbar(mesh, ax=axes, location="right", shrink=0.9 if single else 0.3,
                        pad=0.01, aspect=30 if single else 40)
    cbar.set_label(f"smoothed zonal-mean $u$ at {cfg.pressure_level} hPa (m s$^{{-1}}$)",
                   fontsize=tick_size + 2)
    cbar.ax.tick_params(labelsize=tick_size)
    cbar.solids.set_rasterized(True)    # R6 again: the colorbar is a gradient, not line art

    handles = [Line2D([], [], marker="o", linestyle="none", markersize=5, color=colour,
                      label=f"{state} jet" + (" (both cores)" if state == "double" else ""))
               for state, colour in STATE_COLORS.items()]
    # Bottom band, and the x axis is described in the suptitle instead of by `fig.supxlabel`:
    # constrained layout gives an outside legend and a supxlabel the same strip and they overlap.
    fig.legend(handles=handles, loc="outside lower center", ncols=len(handles), frameon=False,
               fontsize=tick_size + 3)
    fig.supylabel("latitude (°N)", fontsize=tick_size + 2)

    det = cfg.detection
    first_month = calendar.month_name[cfg.season_months[0]]
    fig.suptitle(
        f"{cfg.pressure_level} hPa zonal-mean $u$ and jet-core states, "
        f"{seasons.size} season{'' if single else 's'} "
        f"({'-'.join(calendar.month_abbr[m] for m in cfg.season_months)})\n"
        f"source: {cfg.active_dataset} · {cfg.sector.lon_min:g}–{cfg.sector.lon_max:g}°E · "
        f"{times.min():%Y-%m-%d} to {times.max():%Y-%m-%d}\n"
        f"core $u\\geq${det.u_core_min:g} m s$^{{-1}}$ · "
        f"separation $\\geq${det.separation_min_deg:g}° · "
        f"prominence $\\geq${det.prominence_min:g} m s$^{{-1}}$ · "
        f"boxcar {det.smooth_window_deg:g}° = {cfg.smooth_window_points} points\n"
        f"x: day of season 0–{cfg.days_per_season - 1} from 1 {first_month}, ticked at month "
        f"starts; background: smoothed profile",
        fontsize=(tick_size + 4) if single else (tick_size + 3),
    )

    log.info("figure: %d season(s) in a %dx%d grid, %d blank cell(s), background %s smoothed "
             "profile %.1f to %.1f m s-1", seasons.size, nrows, ncols,
             nrows * ncols - seasons.size, BACKGROUND_CMAP, vmin, vmax)

    try:
        for path in outputs:
            path.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(path, dpi=SAVE_DPI)
            size_mb = path.stat().st_size / 1024 ** 2
            log.info("wrote %s (%.2f MB)", path, size_mb)
            if path.suffix.lower() == ".pdf" and size_mb > PDF_SIZE_LIMIT_MB:
                # Not fatal: the figure is still the deliverable, but M7's < 20 MB has failed and
                # the operator has to see it (lower SAVE_DPI, or check nothing lost rasterized=True).
                log.warning("M7: %s is %.2f MB, over the %g MB limit", path, size_mb,
                            PDF_SIZE_LIMIT_MB)
    finally:
        plt.close(fig)
