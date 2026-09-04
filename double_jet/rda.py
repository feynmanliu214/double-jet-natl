"""The RDA loader: `/glade` hourly archive -> the same per-season raw cache `download.py` writes.

Deviation D3 replaced the CDS derived daily product with the ERA5 hourly archive published on
`/glade/campaign` (`ds633.0`). This module is the whole of that replacement. It owes the pipeline
exactly what `download.py` owed it, and nothing more:

* **Identity, not merely presence** (plan §4.1, addendum §A6) -- a season is skipped only when its
  `.nc` opens with the expected shape, its `.request.json` sidecar exists, and that sidecar equals
  the request that would be issued now, *including* a per-file `(bytes, mtime_ns)` inventory of the
  153 archive days it was built from. A repointed or re-published archive can therefore never be
  silently reused.
* **Atomicity, and a seam check before publication** (§A5.2 steps 5-6, risk DR13) -- every byte
  lands in `<name>.part`, which is opened through `profile.open_normalized` and only then renamed.
  `download._check_shape` -- all `season_is_complete` can apply to bytes on disk -- validates
  *dimension sizes only*. It cannot see a wrong unit string, a drifted grid, a bad time axis, a
  second data variable or a non-finite cell. A season that fails any of those must never be
  published, because the next run would skip it as complete.
* **Two entry points, never one** (§A7.1, risk DR14) -- `ensure_local` materializes and
  `validate_local` only inspects, creating nothing at all. That separation is exactly what
  `--skip-download` means.

What the loader must never do is quietly become a different statistic. The frozen definition is the
unweighted mean of the `cfg.hourly_times` analyses, and three rulings protect it: the four fields
are selected **by timestamp, never by index** (J1, risk DR4); the level is resolved **by value**
against
`cfg.pressure_level` (J6); and every unit string is **copied from the source file and asserted**,
never synthesized (J7). The sector is cut by **assert-then-adopt** (J4) -- exactly what
`open_normalized` step 6 does, applied one stage earlier, so no two of the 47 seasons can differ in
a last float bit and misalign on `concat`.

`season_paths` stays in `download.py` (§A5.3): it is shared addressing, the seam contract names it
there, and a CDS-built and an RDA-built season occupy the same path deliberately -- the sidecar's
`source` key makes them refuse each other. The `["zip"]` entry is meaningless here and is unused.

`check_regression_2018` is the gate between this module and the campaign (§A9): three comparisons of
a smoke-2018 rebuild against the committed CDS baseline in `results/smoke_2018/`. A bit-exact
profile match is impossible -- the CDS operands are int16-packed and this archive is unpacked
float32 (§A1.7) -- and must not be pursued.

Every crossing into `profile.py` is a deferred import inside the function, the pattern
`download.check_r1_equivalence` and `profile.build_intermediate` already use.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import time
from calendar import monthrange
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from datetime import date as date_type
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

from . import download
from .config import Config
from .download import DownloadError, PreflightError

# The archive's granularity (§A1.1): one file per day, `time = 24`, hours 00..23 all present in
# every header inspected across 1979, 2018 and 2025. Asserted per day so a short or resampled file
# is caught where it belongs rather than as a strange seasonal mean.
HOURS_PER_DAY = 24

# The `{YYYYMM}` month directory under `cfg.rda.root` (§A1.1). The *file name* is configured
# (`cfg.rda.file_template`) because a repointed archive must be a config edit with a hash
# consequence (§A4.3); the one archive's directory layout is addressing and lives here.
MONTH_DIR_FORMAT = "%Y%m"

# The wind variable in the archive (§A1.1, risk DR5): `U` uppercase, sharing the file with
# `utc_date(time)`. `profile._resolve_wind` cannot be reused -- it sees two data variables and no
# lowercase `u`, and rejects the file. Resolved by lookup with a hard failure, in `profile.py`'s
# style: a name outside this set is an error, never a guess. The loader's own output carries
# exactly one data variable, named `u`.
ARCHIVE_WIND_NAMES = ("U", "u")

# Half-open selection slack when cutting the sector out of the global grid. Deliberately the same
# 1e-6 the grid assertion uses (`profile.GRID_TOL`): anything this misses is caught immediately
# afterwards by the whole-array comparison, with a message naming the offending point (J4).
SELECT_TOL = 1e-6

_PART_SUFFIX = ".part"

# O3 / §A9.2: the profile allowance of the 2018 regression, in m s-1 max-abs. Deliberately *not* a
# config key -- §A4.1's additive block adds machine addressing only, and this is an operator ruling
# about a one-off gate between the loader and the campaign, not a threshold the science reads.
REGRESSION_TOLERANCE = 0.05

# Sidecar keys that are the file inventory rather than the request spec (§A6.2).
# `_canonical_request` handles the spec; the inventory is compared entry by entry, because
# stringifying 153 dicts and truncating the result to 60 characters is a useless failure for the
# one case it exists to catch.
_INVENTORY_KEYS = ("source_files", "n_source_files")


# -- small helpers, in profile.py's style but raising this module's error types -------------------


def _resolve_variable(ds: xr.Dataset, candidates: Sequence[str], kind: str, path: Path,
                      label: str, error: type = DownloadError) -> str:
    """The one accepted name present, or a failure listing what the file actually has."""
    present = [name for name in candidates if name in ds.variables]
    if len(present) == 1:
        return present[0]
    seen = sorted(map(str, ds.variables))
    if not present:
        raise error(
            f"{label}: {path} has no {kind}; accepted names are {list(candidates)}, "
            f"the file has {seen}"
        )
    raise error(
        f"{label}: {path} has an ambiguous {kind}; {present} are all present and only one may be"
    )


def _read_units(attrs: Mapping[str, Any], what: str, accepted: Sequence[str], path: Path,
                label: str, error: type = DownloadError) -> str:
    """J7: units are COPIED FROM THE SOURCE and asserted, never synthesized.

    A missing `units` attribute fails too -- unstated is not the same as correct -- and a Pa-tagged
    level fails *here*, on the day that carries it, rather than 47 seasons downstream.
    """
    units = attrs.get("units")
    if units is None:
        raise error(
            f"{label}: {path}: {what} carries no 'units' attribute; units are read, not assumed"
        )
    if str(units) not in accepted:
        raise error(
            f"{label}: {path}: {what} units are {units!r}, which is not one of {list(accepted)}"
        )
    return str(units)


def _assert_axis(actual: np.ndarray, expected: np.ndarray, axis: str, path: Path,
                 label: str) -> None:
    """J4's assert half: the WHOLE array against the config, not the count and the two bounds.

    Mirrors `profile._assert_grid` one stage earlier. Count-and-bounds would accept a non-uniform
    axis, and I1's "11 samples = 2.5 deg" boxcar silently depends on the spacing being uniform.
    """
    if actual.size != expected.size:
        raise DownloadError(
            f"{label}: {path}: the {axis} sector cut has {actual.size} points, expected "
            f"{expected.size} ({expected[0]:g}..{expected[-1]:g} at "
            f"{expected[1] - expected[0]:g} deg)"
        )
    diff = np.abs(actual - expected)
    worst = int(np.argmax(diff))
    if diff[worst] > SELECT_TOL:
        raise DownloadError(
            f"{label}: {path}: {axis} does not match the configured grid to {SELECT_TOL:g} deg; "
            f"worst point is index {worst}, file has {actual[worst]!r}, config expects "
            f"{expected[worst]!r} (max |diff| {diff[worst]:.3e})"
        )


def _minutes_of_day(times: np.ndarray) -> np.ndarray:
    """Minutes past midnight of each timestamp. Mirrors `profile._minutes_of_day`."""
    minutes = np.asarray(times).astype("datetime64[m]")
    return (minutes - minutes.astype("datetime64[D]")).astype("timedelta64[m]").astype(np.int64)


def _wanted_minutes(cfg: Config) -> list[int]:
    """`cfg.hourly_times` as minutes past midnight, in the configured order."""
    out = []
    for stamp in cfg.hourly_times:
        hour, minute = stamp.split(":")[:2]
        out.append(int(hour) * 60 + int(minute))
    return out


def _season_dates(cfg: Config, year: int) -> list[date_type]:
    """The season's calendar days, ascending. 153 for MJJAS; computed, never a literal."""
    dates = [date_type(year, month, day)
             for month in sorted(cfg.season_months)
             for day in range(1, monthrange(year, month)[1] + 1)]
    dates.sort()
    if len(dates) != cfg.days_per_season or len(set(dates)) != len(dates):
        raise DownloadError(
            f"season {year}: enumerated {len(dates)} day(s) ({len(set(dates))} unique) from "
            f"months {list(cfg.season_months)}, expected {cfg.days_per_season}"
        )
    return dates


def _source_path(cfg: Config, day: date_type) -> Path:
    """One archive day's path: `<root>/<YYYYMM>/<file_template formatted with ymd>` (§A1.1)."""
    ymd = day.strftime("%Y%m%d")
    try:
        name = cfg.rda.file_template.format(ymd=ymd)
    except (KeyError, IndexError) as exc:
        raise DownloadError(
            f"rda.file_template {cfg.rda.file_template!r} references a field this loader does not "
            f"supply; the only substitution is {{ymd}} (addendum §A4.1): {exc}"
        ) from exc
    return Path(cfg.rda.root) / day.strftime(MONTH_DIR_FORMAT) / name


def _pool_size(cfg: Config) -> tuple[int, str]:
    """(workers, where it came from) -- §A5.2 step 2.

    `$PBS_NCPUS` wins whenever PBS sets it, so the job's requested shape and the parallelism can
    never disagree, and a 1-cpu interactive session cannot silently spawn 8 worker processes. An
    empty value is treated as unset; a non-integer one is a hard error naming the value, because
    guessing a worker count from a malformed job environment is exactly the silent divergence this
    rule exists to prevent.
    """
    raw = os.environ.get("PBS_NCPUS", "").strip()
    if not raw:
        workers, origin = int(cfg.rda.workers), "cfg.rda.workers"
    else:
        try:
            workers = int(raw)
        except ValueError as exc:
            raise DownloadError(
                f"$PBS_NCPUS is {raw!r}, which is not an integer; the loader will not guess a "
                "worker count from a malformed job environment (addendum §A5.2 step 2)"
            ) from exc
        origin = "$PBS_NCPUS"
    if workers < 1:
        raise DownloadError(f"{origin} is {workers}; at least one worker process is required")
    return workers, origin


# -- step 1: enumerate ---------------------------------------------------------------------------


def season_source_files(cfg: Config, year: int) -> list[Path]:
    """The season's archive files, date-ordered (§A5.2 step 1).

    A missing path is a hard error naming the date and the expected filename -- never a silently
    short season. Gate 1 walked MJJAS 1979-2025 by name and found no gaps (§A1.2); this exists so
    that a future gap, or a purge, is loud.
    """
    paths: list[Path] = []
    for day in _season_dates(cfg, year):
        path = _source_path(cfg, day)
        if not path.exists():
            raise DownloadError(
                f"season {year}: the archive has no file for {day.isoformat()}; expected "
                f"{path}. A missing day is a hard error, never a short season "
                "(addendum §A5.2 step 1)."
            )
        paths.append(path)
    return paths


# -- step 2: one day, in a worker process --------------------------------------------------------


def _read_day(task: tuple[Config, Path, str]) -> tuple[str, np.ndarray, dict[str, str]]:
    """One archive day -> (date, float64 sector mean of shape (n_lat, n_lon), units read).

    Module-level and picklable on purpose: this is the `ProcessPoolExecutor` payload. It logs
    nothing (workers have no logger) and raises `DownloadError` naming the date, which the parent
    re-raises with the season attached.

    The order of the checks is the order of their consequences: units before values, so a Pa-tagged
    level fails as a *unit* error rather than as a puzzling "250 not found" (J7); timestamps before
    anything is read, so J1 can never degrade into an index selection.
    """
    from . import profile as profile_mod          # deferred: the only crossing, and no cycle

    cfg, path, date = task
    with xr.open_dataset(path) as raw:
        # -- names, by lookup with a hard failure ---------------------------------------------
        time_name = _resolve_variable(raw, profile_mod.TIME_NAMES, "time coordinate", path, date)
        lat_name = _resolve_variable(raw, profile_mod.LAT_NAMES, "latitude coordinate", path, date)
        lon_name = _resolve_variable(raw, profile_mod.LON_NAMES, "longitude coordinate", path, date)
        level_name = _resolve_variable(raw, profile_mod.LEVEL_NAMES, "pressure level coordinate",
                                       path, date)
        wind_name = _resolve_variable(raw, ARCHIVE_WIND_NAMES, "wind variable", path, date)

        # -- J1 (risk DR4): the four fields are selected BY TIMESTAMP, NEVER BY INDEX ----------
        # `isel(time=[0, 6, 12, 18])` is forbidden even though every file inspected carries 24
        # ordered hourly steps: index selection would silently become a different statistic on any
        # file whose time axis is not the one we saw.
        times = np.asarray(raw[time_name].values)
        if not np.issubdtype(times.dtype, np.datetime64):
            raise DownloadError(
                f"{date}: {path}: time coordinate has dtype {times.dtype}, expected datetime64"
            )
        if np.isnat(times).any():
            raise DownloadError(
                f"{date}: {path}: time coordinate holds {int(np.isnat(times).sum())} NaT value(s)"
            )
        if times.size != HOURS_PER_DAY:
            raise DownloadError(
                f"{date}: {path} carries {times.size} timestamps, expected {HOURS_PER_DAY} "
                f"(one archive file is one day of hourly analyses, addendum §A1.1)"
            )
        minutes = _minutes_of_day(times)
        time_index: list[int] = []
        for wanted, label in zip(_wanted_minutes(cfg), cfg.hourly_times):
            hits = np.flatnonzero(minutes == wanted)
            if hits.size != 1:
                present = sorted({f"{m // 60:02d}:{m % 60:02d}" for m in minutes.tolist()})
                raise DownloadError(
                    f"{date}: {path} carries {hits.size} timestamp(s) at {label} UTC and exactly "
                    f"one is required; the hours present are {present}. The daily mean is the "
                    f"unweighted mean of {list(cfg.hourly_times)}, selected by timestamp and never "
                    "by index (addendum J1)."
                )
            time_index.append(int(hits[0]))
        if len(time_index) != len(cfg.hourly_times):
            raise DownloadError(
                f"{date}: {path} matched {len(time_index)} of {len(cfg.hourly_times)} configured "
                "analysis hours"
            )
        selected_days = times[time_index].astype("datetime64[D]").astype(str).tolist()
        off = sorted({d for d in selected_days if d != date})
        if off:
            raise DownloadError(
                f"{date}: {path} is named for {date} but its selected timestamps fall on {off}; "
                "the archive file and its date must agree"
            )

        # -- J6/J7: the level BY VALUE, its units read from the file first ---------------------
        level_attrs = dict(raw[level_name].attrs)
        level_units = _read_units(level_attrs, f"pressure coordinate {level_name!r}",
                                  (profile_mod.LEVEL_UNITS,), path, date)
        levels = np.atleast_1d(np.asarray(raw[level_name].values, dtype=float))
        hits = np.flatnonzero(np.abs(levels - float(cfg.pressure_level)) <= profile_mod.GRID_TOL)
        if hits.size != 1:
            raise DownloadError(
                f"{date}: {path}: pressure coordinate {level_name!r} holds {hits.size} value(s) "
                f"equal to {cfg.pressure_level} {level_units} among {levels.size} level(s) "
                f"({levels.min():g}..{levels.max():g}); exactly one is required. The level is "
                "resolved by value, never by index (addendum J6)."
            )
        level_index = int(hits[0])

        # -- the slab: four hours at one level, loaded before any coordinate surgery -----------
        wind = raw[wind_name]
        wind_units = _read_units(wind.attrs, f"wind variable {wind_name!r}",
                                 profile_mod.WIND_UNITS, path, date)
        lat_units = _read_units(raw[lat_name].attrs, f"latitude coordinate {lat_name!r}",
                                (profile_mod.LAT_UNITS,), path, date)
        lon_units = _read_units(raw[lon_name].attrs, f"longitude coordinate {lon_name!r}",
                                (profile_mod.LON_UNITS,), path, date)
        selection: dict[str, Any] = {time_name: time_index}
        if level_name in wind.dims:
            selection[level_name] = level_index
        elif levels.size != 1:
            raise DownloadError(
                f"{date}: {path}: {wind_name!r} has dims {tuple(str(d) for d in wind.dims)} and "
                f"does not carry the {level_name!r} dimension, yet the file holds {levels.size} "
                "levels; the level cannot be resolved"
            )
        # `.load()` here and not later: the archive chunk is (1, all levels, all lats, all lons)
        # (§A1.1), so a fancy index applied lazily would re-decompress per axis. One decompress,
        # then everything below is in memory.
        da = wind.isel(selection).load()

    # -- J4: cut the sector by ASSERT-THEN-ADOPT ----------------------------------------------
    # Wrap to [-180, 180), select, sort ascending, assert the WHOLE array against the config; the
    # adopt half happens in `_write_part`, which builds the coordinates from `cfg.sector` itself.
    # This is `open_normalized` step 6 one stage earlier, so no two seasons can differ in a last
    # float bit and misalign on `concat`.
    lon = np.asarray(da[lon_name].values, dtype=float)
    da = da.assign_coords({lon_name: ((lon + 180.0) % 360.0) - 180.0})
    wrapped = np.asarray(da[lon_name].values, dtype=float)
    lon_keep = np.flatnonzero((wrapped >= cfg.sector.lon_min - SELECT_TOL)
                              & (wrapped <= cfg.sector.lon_max + SELECT_TOL))
    da = da.isel({lon_name: lon_keep}).sortby(lon_name)
    _assert_axis(np.asarray(da[lon_name].values, dtype=float), cfg.sector.longitudes(),
                 "longitude", path, date)

    # -- J5: latitude ASCENDING 20 -> 75; the archive is descending ---------------------------
    lat = np.asarray(da[lat_name].values, dtype=float)
    lat_keep = np.flatnonzero((lat >= cfg.sector.lat_min - SELECT_TOL)
                              & (lat <= cfg.sector.lat_max + SELECT_TOL))
    da = da.isel({lat_name: lat_keep}).sortby(lat_name)
    _assert_axis(np.asarray(da[lat_name].values, dtype=float), cfg.sector.latitudes(),
                 "latitude", path, date)

    da = da.transpose(time_name, lat_name, lon_name)
    values = np.asarray(da.values)
    if values.shape != (len(cfg.hourly_times), cfg.sector.n_lat, cfg.sector.n_lon):
        raise DownloadError(
            f"{date}: {path}: the sector slab is {values.shape}, expected "
            f"({len(cfg.hourly_times)}, {cfg.sector.n_lat}, {cfg.sector.n_lon})"
        )

    # -- every value finite, NAMING THE DATE (§A5.2 step 2) -----------------------------------
    # The archive carries `_FillValue = missing_value = 9.999e+20`, which xarray masks to NaN. A
    # masked cell inside our sector must stop the run, not average into a mean.
    finite = np.isfinite(values)
    if not finite.all():
        bad = int((~finite).sum())
        i_t, i_lat, i_lon = (int(i) for i in np.argwhere(~finite)[0])
        raise DownloadError(
            f"{date}: {path} has {bad} non-finite value(s) of {values.size} inside the sector; "
            f"first at {cfg.hourly_times[i_t]} UTC, latitude "
            f"{float(da[lat_name].values[i_lat]):g}, longitude "
            f"{float(da[lon_name].values[i_lon]):g}, value {values[i_t, i_lat, i_lon]!r}. A masked "
            "cell must stop the run, not average into a mean (addendum §A5.2 step 2)."
        )

    # -- J2: accumulate the four-sample mean in float64; float32 is a storage decision --------
    mean = values.astype("float64").mean(axis=0)
    units = {"u": wind_units, "latitude": lat_units, "longitude": lon_units, "level": level_units}
    return date, mean, units


# -- the sidecar (§A6) ---------------------------------------------------------------------------


def build_rda_request(cfg: Config, year: int) -> dict:
    """The sidecar payload for one season, exactly §A6.1.

    Two halves with two jobs. The **subset spec** (`pressure_level`, `area`, `resolution`, `hours`,
    `month`, `year`, `source`) is what makes a sector, level, hour-set or source change refuse the
    cache. The **file inventory** -- `name`, `bytes`, `mtime_ns` for each of the 153 days -- is the
    "archive moved under you" detector: size and mtime, deliberately not a content hash, because
    hashing 153 x 1.6 GB per season is 245 GB of reads to validate a 30 MB output, which would cost
    more than rebuilding it. A migration that preserved content but changed mtimes forces a needless
    rebuild; at ~52 min for the whole campaign that is an accepted false positive, and it fails in
    the safe direction (§A6.3).

    `daily_statistic` is recorded even though this loader computes it, so a sidecar read in
    isolation still states which statistic the bytes are. `area` keeps `[N, W, S, E]` order,
    `download._canonical_request`'s rule: a permuted box is a different box and must mismatch.
    """
    from . import profile as profile_mod          # deferred: LEVEL_UNITS is the seam's own constant

    inventory = []
    for path in season_source_files(cfg, year):
        stat = path.stat()
        inventory.append({"name": path.name, "bytes": int(stat.st_size),
                          "mtime_ns": int(stat.st_mtime_ns)})
    return {
        "source": cfg.source,
        "archive_root": str(cfg.rda.root),
        "file_template": cfg.rda.file_template,
        "variable": cfg.variable,
        "pressure_level": int(cfg.pressure_level),
        "level_units": profile_mod.LEVEL_UNITS,
        "year": str(year),
        "month": cfg.month_strings(),
        "hours": list(cfg.hourly_times),
        "daily_statistic": cfg.daily_statistic,
        "area": cfg.sector.area(),               # [North, West, South, East]
        "resolution": cfg.sector.resolution,
        "n_source_files": len(inventory),
        "source_files": inventory,
    }


def season_is_complete(cfg: Config, year: int) -> tuple[bool, str]:
    """True only when the `.nc` opens with the expected shape, the sidecar exists, and that sidecar
    equals the request that would be issued now (§A6.2). Otherwise (False, reason).

    `download._check_shape` and `download._canonical_request` are reused unchanged -- the same
    three-part contract, the same canonicalization, the same `[N, W, S, E]` rule. The **inventory**
    is compared entry by entry rather than through `_canonical_request`, which would stringify 153
    dicts and truncate the mismatch to 60 characters: a useless failure for the one case the
    inventory exists to catch. The first differing filename is reported with both `(bytes,
    mtime_ns)` pairs.
    """
    paths = download.season_paths(cfg, year)
    nc_path, sidecar = Path(paths["nc"]), Path(paths["request"])

    if not nc_path.exists():
        return False, f"{nc_path} is missing"
    ok, reason = download._check_shape(cfg, nc_path, False)
    if not ok:
        return False, reason
    if not sidecar.exists():
        return False, f"{sidecar} is missing"
    try:
        stored = json.loads(sidecar.read_text())
    except (OSError, ValueError) as exc:
        return False, f"{sidecar} is not readable JSON: {exc}"
    if not isinstance(stored, dict):
        return False, f"{sidecar} does not hold a request mapping"

    try:
        wanted = build_rda_request(cfg, year)
    except DownloadError as exc:
        # The archive can no longer supply every day this season claims to be built from. That is
        # "not complete", reported rather than raised, so `ensure_local` rebuilds and fails there
        # with the full context.
        return False, f"the archive no longer supplies every source day for {year}: {exc}"

    have = download._canonical_request({k: v for k, v in stored.items()
                                        if k not in _INVENTORY_KEYS})
    want = download._canonical_request({k: v for k, v in wanted.items()
                                        if k not in _INVENTORY_KEYS})
    if have != want:
        changed = sorted(k for k in set(have) | set(want) if have.get(k) != want.get(k))
        detail = "; ".join(f"{k}: on disk {repr(have.get(k))[:60]} vs now {repr(want.get(k))[:60]}"
                           for k in changed)
        return False, f"{sidecar} does not match the request that would be issued now -- {detail}"

    stored_files = stored.get("source_files")
    if not isinstance(stored_files, list):
        return False, (f"{sidecar} carries no 'source_files' inventory, so the archive it was "
                       "built from cannot be verified")
    wanted_files = wanted["source_files"]
    if len(stored_files) != len(wanted_files):
        return False, (f"{sidecar} records {len(stored_files)} source file(s), the archive now "
                       f"supplies {len(wanted_files)} for {year}")
    for stored_entry, wanted_entry in zip(stored_files, wanted_files):
        if not isinstance(stored_entry, dict):
            return False, (f"{sidecar}: source_files entry {stored_entry!r} is not a mapping of "
                           "name/bytes/mtime_ns")
        if stored_entry.get("name") != wanted_entry["name"]:
            return False, (f"{sidecar}: source file {stored_entry.get('name')!r} where the archive "
                           f"now supplies {wanted_entry['name']!r}")
        if (stored_entry.get("bytes") != wanted_entry["bytes"]
                or stored_entry.get("mtime_ns") != wanted_entry["mtime_ns"]):
            return False, (
                f"{sidecar}: archive file {wanted_entry['name']} changed since the season was "
                f"built -- sidecar records (bytes {stored_entry.get('bytes')}, mtime_ns "
                f"{stored_entry.get('mtime_ns')}), the archive now has (bytes "
                f"{wanted_entry['bytes']}, mtime_ns {wanted_entry['mtime_ns']})"
            )
    return True, ""


# -- steps 3-6: assemble, write, self-check at the seam, land it ---------------------------------


def _assert_season_dates(got: list[str], expected: list[date_type], cfg: Config,
                         year: int) -> None:
    """§A5.2 step 3: exactly that year's MJJAS days, ascending, no duplicates.

    `profile._assert_time` re-checks the same conditions on the written file; this one fires against
    the season being built, so a defect is reported where it was introduced.
    """
    want = [d.isoformat() for d in expected]
    if len(got) != len(want):
        raise DownloadError(
            f"season {year}: assembled {len(got)} day(s), expected {len(want)} "
            f"({cfg.days_per_season} MJJAS days)"
        )
    if len(set(got)) != len(got):
        duplicated = sorted({d for d in got if got.count(d) > 1})[:5]
        raise DownloadError(
            f"season {year}: duplicated day(s) {duplicated} in the assembled season")
    if got != sorted(got):
        raise DownloadError(f"season {year}: the assembled days are not in ascending date order")
    if got != want:
        offenders = [(g, w) for g, w in zip(got, want) if g != w][:5]
        raise DownloadError(
            f"season {year}: the assembled days are not the configured season; first mismatches "
            f"(assembled vs expected) {offenders}"
        )


def _agree_units(results: list[tuple[str, np.ndarray, dict[str, str]]],
                 year: int) -> dict[str, str]:
    """J7: one unit string per axis for the whole season, or a named disagreement.

    A season assembled from days that disagree about units is not one field, and no downstream
    check would ever see it -- the seam reads the written file's single attribute.
    """
    first_date, _, first_units = results[0]
    for date, _, units in results[1:]:
        if units != first_units:
            differing = sorted(k for k in set(units) | set(first_units)
                               if units.get(k) != first_units.get(k))
            detail = "; ".join(f"{k}: {first_date} says {first_units.get(k)!r}, {date} says "
                               f"{units.get(k)!r}" for k in differing)
            raise DownloadError(
                f"season {year}: the archive days disagree about units -- {detail}. Units are "
                "copied from the source and must be one field for the whole season (addendum J7)."
            )
    return dict(first_units)


def _write_part(cfg: Config, part: Path, dates: list[date_type], data: np.ndarray,
                units: Mapping[str, str], year: int) -> None:
    """§A5.2 step 4: one data variable `u`, float32/zlib-4, latitude ascending, scalar `level`.

    * **J3** -- float32, zlib complevel 4, mirroring the intermediate's encoding. Deliberately not
      int16-packed: the source is unpacked, and re-packing would reintroduce exactly the
      quantization §A1.7 identifies in the CDS path.
    * **J4 (adopt half)** -- the coordinates are `cfg.sector`'s own arrays, now that the archive's
      have been proven equal to them to 1e-6 on every one of the 153 days.
    * **J5** -- latitude ascending 20 -> 75. `open_normalized` would `sortby` either way; writing
      ascending makes the raw season and the intermediate agree by inspection.
    * **J6** -- a *scalar* `level` coordinate: `_resolve_name` finds it in `ds.variables`, it is not
      a dim so nothing squeezes it, `_check_shape`'s `_DIM_CANDIDATES` cannot mistake it for a wrong
      shape, and the seam drops it.
    * **DR5** -- exactly one data variable, named `u`. The archive's `U` + `utc_date` pair cannot be
      handed to `open_normalized`; this can.

    `_FillValue` is suppressed on `u`: the field is proven finite day by day, and an invented fill
    value is noise in the provenance. `TIME_ENCODING` is reused from `profile.py` so a rebuild is
    byte-reproducible rather than xarray-default.
    """
    from . import profile as profile_mod          # deferred: TIME_ENCODING is the seam's own

    times = np.array([np.datetime64(d.isoformat()) for d in dates], dtype="datetime64[ns]")
    ds = xr.Dataset(
        {"u": (("time", "latitude", "longitude"), data)},
        coords={
            "time": times,
            "latitude": cfg.sector.latitudes(),
            "longitude": cfg.sector.longitudes(),
            "level": np.float64(cfg.pressure_level),
        },
    )
    ds["u"].attrs = {
        "long_name": f"{cfg.variable} at {cfg.pressure_level} {units['level']}",
        "units": units["u"],
        "cell_methods": "time: mean",
        "comment": ("unweighted mean of the " + ", ".join(cfg.hourly_times)
                    + " UTC analyses (deviation D3, addendum §A5; the frozen daily-mean "
                      "definition is unchanged)"),
    }
    ds["latitude"].attrs = {"units": units["latitude"], "long_name": "latitude"}
    ds["longitude"].attrs = {"units": units["longitude"], "long_name": "longitude"}
    ds["level"].attrs = {"units": units["level"], "long_name": "pressure level"}
    ds["time"].attrs = {"long_name": "time"}
    ds.attrs = {
        "title": f"MJJAS {year} daily-mean {cfg.variable} at {cfg.pressure_level} "
                 f"{units['level']}, {cfg.sector.lat_min:g}-{cfg.sector.lat_max:g}N "
                 f"{cfg.sector.lon_min:g}-{cfg.sector.lon_max:g}E",
        "source": cfg.source,
        "source_dataset": cfg.rda.dataset_id,
        "archive_root": str(cfg.rda.root),
        "daily_statistic": cfg.daily_statistic,
        "hourly_times": json.dumps(list(cfg.hourly_times)),
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "plan": "wave1-plan-derecho-addendum.md",
    }
    part.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(
        part,
        encoding={
            "u": {"zlib": True, "complevel": 4, "dtype": "float32", "_FillValue": None},
            "time": dict(profile_mod.TIME_ENCODING),
            "latitude": {"_FillValue": None},
            "longitude": {"_FillValue": None},
            "level": {"_FillValue": None},
        },
    )


def write_season(cfg: Config, year: int, log: logging.Logger) -> Path:
    """Build one season from the archive and land it atomically (§A5.2, all six steps).

    The order of steps 5 and 6 is load-bearing (risk DR13). The `.part` is opened through
    `profile.open_normalized` and allowed to throw *before* `os.replace` and *before* the sidecar,
    because `download._check_shape` -- all `season_is_complete` can apply to the bytes -- validates
    dimension sizes only. It cannot see a wrong unit string, a drifted grid, a bad time axis, a
    second data variable or a non-finite cell. A season failing any of those would otherwise sit on
    disk looking complete and the next run would skip it. Validating the `.part` means such a season
    is never published at all.

    The sidecar is written last for the same reason inverted: a job killed between the `.nc` and its
    sidecar rebuilds the season next time, which is merely wasted work, whereas a sidecar written
    first could describe bytes that do not exist.
    """
    from . import profile as profile_mod          # deferred: the seam crossing (§A5.2 step 5)

    paths = download.season_paths(cfg, year)
    nc_path, sidecar = Path(paths["nc"]), Path(paths["request"])
    part = nc_path.with_name(nc_path.name + _PART_SUFFIX)

    # Step 1, and the sidecar's inventory, both before a single byte is read: the request describes
    # the archive state this season is built from, not the state it happens to be in afterwards.
    dates = _season_dates(cfg, year)
    files = season_source_files(cfg, year)
    request = build_rda_request(cfg, year)

    workers, origin = _pool_size(cfg)
    log.info("season %d: building %d archive day(s) from %s, %d worker process(es) (from %s)",
             year, len(files), cfg.rda.root, workers, origin)
    started = time.monotonic()

    nc_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # -- step 2: read each day in a worker process ------------------------------------------
        # `ex.map` and not `submit`/`as_completed`: it preserves input order, so the season is
        # assembled in date order without a sort that could paper over a mis-ordered enumeration.
        tasks = [(cfg, path, day.isoformat()) for path, day in zip(files, dates)]
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_read_day, tasks))

        # -- step 3: assemble ------------------------------------------------------------------
        _assert_season_dates([r[0] for r in results], dates, cfg, year)
        units = _agree_units(results, year)
        data = np.stack([r[1] for r in results]).astype("float32")     # J2's float64 -> J3's store

        # -- step 4: write the .part -----------------------------------------------------------
        _write_part(cfg, part, dates, data, units, year)

        # -- step 5: the seam, ON THE .part, BEFORE it is published (DR13) ---------------------
        log.info("season %d: checking %s against the seam before publishing it", year, part.name)
        try:
            profile_mod.open_normalized(part, cfg)
        except Exception as exc:
            # Let it throw; only annotate the log so the failure names the season, not just a path.
            log.error("season %d: the .part FAILED profile.open_normalized and will NOT be "
                      "published -- %s", year, exc)
            raise

        # -- step 6: land it atomically, then the sidecar. Never the reverse. -------------------
        os.replace(part, nc_path)
        sidecar.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n")
    except BaseException:
        # A killed or failed season must leave nothing a later run could accept as complete.
        part.unlink(missing_ok=True)
        raise

    log.info("season %d: complete (%.1f MB, %.1f s)", year, nc_path.stat().st_size / 1e6,
             time.monotonic() - started)
    return nc_path


# -- the two stage entry points (§A7.1) ----------------------------------------------------------


def ensure_local(cfg: Config, years: list[int], smoke: bool, log: logging.Logger) -> None:
    """**Writes.** Build every requested season that is not already complete (mirrors
    `download.run_download`).

    Per-season exceptions are collected rather than swallowed and re-raised together, so a partial
    campaign exits non-zero with the full list and an identical resubmission completes only the
    gaps. The count skipped is reported because §A10.3 rests on it: "resubmit the same shape until
    complete" is only an authorization if the operator can see that a resubmission did skip.

    `smoke` is accepted for signature parity with `download.run_download` and is a no-op here: the
    CDS path's extra 6-hourly R1 operand does not and cannot exist on this machine (§A9.1), and the
    smoke run's equivalence evidence comes from `check_regression_2018` instead.
    """
    cfg.paths.scratch_raw.mkdir(parents=True, exist_ok=True)
    if smoke:
        log.info("smoke run: the RDA path builds the one season only; the CDS 6-hourly R1 operand "
                 "does not exist here, and the 2018 regression (§A9) is the evidence instead")

    pending: list[int] = []
    skipped = 0
    for year in years:
        ok, reason = season_is_complete(cfg, year)
        if ok:
            log.info("season %d: already complete, skipping", year)
            skipped += 1
        else:
            log.info("season %d: will be built from the archive -- %s", year, reason)
            pending.append(year)

    log.info("%d of %d requested season(s) already complete and skipped; %d to build",
             skipped, len(years), len(pending))
    if not pending:
        return

    failures: list[str] = []
    for year in pending:
        try:
            write_season(cfg, year, log)
        except Exception as exc:
            log.error("season %d failed: %s", year, exc)
            failures.append(f"{year}: {exc}")

    if failures:
        raise DownloadError(
            f"{len(failures)} of {len(pending)} season(s) failed to build from the archive:\n  "
            + "\n  ".join(failures)
        )


def validate_local(cfg: Config, years: list[int], smoke: bool, log: logging.Logger) -> None:
    """**Never writes** -- not one byte, not one directory (risk DR14). Mirrors
    `download.ensure_downloaded`.

    This is `--skip-download`'s entire meaning: inspect what is already in the raw cache, report
    *every* season that is missing or does not match the current request, and raise with the full
    list. A `mkdir` here would make the flag a materializer of the very tree it promises only to
    read, so there is none -- `season_is_complete` stats and opens, and nothing else happens.
    """
    del smoke                    # signature parity only; nothing extra is validated on this path
    missing: list[str] = []
    for year in years:
        ok, reason = season_is_complete(cfg, year)
        if ok:
            log.info("season %d: complete", year)
        else:
            log.error("season %d: NOT usable -- %s", year, reason)
            missing.append(f"{year}: {reason}")

    if missing:
        raise DownloadError(
            f"--skip-download: {len(missing)} of {len(years)} requested season(s) are missing or "
            f"do not match the current request:\n  " + "\n  ".join(missing)
        )
    log.info("--skip-download: all %d requested season(s) are complete", len(years))


def preflight_archive(cfg: Config, years: list[int], log: logging.Logger) -> None:
    """Fail in seconds with a labelled message, before the expensive part (§A7.1, plan §5.0).

    Raises `download.PreflightError`, which `cli.run` already maps to `EXIT_PREFLIGHT`, so the CLI's
    exception handling needs no edit. Reads no wind data: it asserts the archive root exists and is
    readable, and that the *first day of the first requested season* opens and carries
    `cfg.pressure_level` at `hPa`. There is no fixed season to probe -- `--smoke` wants 2018 and
    `--years` wants its own first year -- which is why the years are passed in.
    """
    from . import profile as profile_mod          # deferred: LEVEL_NAMES / LEVEL_UNITS

    if not years:
        raise PreflightError("archive preflight FAILED: no seasons were requested, so there is no "
                             "first day to probe")
    root = Path(cfg.rda.root)
    if not root.exists():
        raise PreflightError(
            f"archive preflight FAILED: the RDA archive root {root} does not exist. Exiting before "
            "any season is read (addendum §A7.1)."
        )
    if not root.is_dir():
        raise PreflightError(f"archive preflight FAILED: {root} is not a directory")
    if not os.access(root, os.R_OK | os.X_OK):
        raise PreflightError(
            f"archive preflight FAILED: the RDA archive root {root} is not readable by this "
            f"process (uid {os.getuid()})"
        )
    log.info("preflight archive root %s -> readable", root)

    first_year = min(years)
    first_day = _season_dates(cfg, first_year)[0]
    first_path = _source_path(cfg, first_day)
    if not first_path.exists():
        raise PreflightError(
            f"archive preflight FAILED: the first day of the first requested season "
            f"({first_day.isoformat()}) is missing; expected {first_path}"
        )
    # Every failure below carries the same label, so a preflight stop is never mistaken for a
    # mid-campaign one: `cli.run` maps this type to EXIT_PREFLIGHT before any season is read.
    label = f"archive preflight FAILED at {first_day.isoformat()}"
    try:
        with xr.open_dataset(first_path) as ds:
            level_name = _resolve_variable(ds, profile_mod.LEVEL_NAMES,
                                           "pressure level coordinate", first_path,
                                           label, error=PreflightError)
            level_units = _read_units(dict(ds[level_name].attrs),
                                      f"pressure coordinate {level_name!r}",
                                      (profile_mod.LEVEL_UNITS,), first_path,
                                      label, error=PreflightError)
            levels = np.atleast_1d(np.asarray(ds[level_name].values, dtype=float))
    except PreflightError:
        raise
    except Exception as exc:
        raise PreflightError(
            f"archive preflight FAILED: {first_path} does not open as netCDF: {exc}"
        ) from exc

    hits = np.flatnonzero(np.abs(levels - float(cfg.pressure_level)) <= profile_mod.GRID_TOL)
    if hits.size != 1:
        raise PreflightError(
            f"archive preflight FAILED: {first_path} holds {hits.size} level(s) equal to "
            f"{cfg.pressure_level} {level_units} among {levels.size} "
            f"({levels.min():g}..{levels.max():g}); exactly one is required"
        )
    log.info("preflight archive %s -> opens, level %g %s present (index %d of %d, resolved by "
             "value)", first_path.name, cfg.pressure_level, level_units, int(hits[0]), levels.size)


# -- the 2018 regression, the gate between this loader and the campaign (§A9) ---------------------


def _run_output(out_paths: Any, field: str) -> Path:
    """One of the run's own artifact paths, from a `cli.OutputNames` or any mapping of it."""
    value = getattr(out_paths, field, None)
    if value is None and isinstance(out_paths, Mapping):
        value = out_paths.get(field)
    if value is None:
        raise DownloadError(
            f"2018 regression: the run's output names carry no {field!r} entry; the check needs "
            "the profile, the states CSV and the summary this run wrote"
        )
    return Path(value)


def _require_operand(path: Path, role: str) -> Path:
    if not path.exists():
        raise DownloadError(
            f"2018 regression: the {role} operand {path} is missing. The check runs after the "
            "figure stage and only when both `profile` and `classify` ran (addendum §A7.3 item 3), "
            "so a missing operand is a wiring fault, not a science result."
        )
    return path


def _core_lat(text: str | None):
    """One core-latitude cell: `None` for the blank CSV field, else the parsed value."""
    if text is None or text.strip() == "":
        return None
    try:
        return float(text)
    except ValueError:
        return text.strip()                       # keep it comparable rather than raising


def _compare_states_csv(cfg: Config, current: Path, baseline: Path,
                        log: logging.Logger) -> dict:
    """§A9.2 comparison 1: state labels and core latitudes match EXACTLY, all 153 rows.

    Row count and the `date` column are aligned *first*, so a short or re-ordered CSV fails rather
    than matching on its prefix.
    """
    def read(path: Path) -> tuple[list[str], list[dict]]:
        with open(path, newline="") as handle:
            reader = csv.DictReader(handle)
            return list(reader.fieldnames or []), list(reader)

    cur_fields, cur_rows = read(current)
    base_fields, base_rows = read(baseline)
    record: dict[str, Any] = {
        "name": "jet_states_csv",
        "current": str(current),
        "baseline": str(baseline),
        "n_rows": len(cur_rows),
        "n_baseline_rows": len(base_rows),
        "n_expected_rows": cfg.days_per_season,
        "compared_fields": ["state", "lat_1", "lat_2"],
        "passed": False,
        "reason": "",
        "mismatches": [],
    }

    needed = ("date", "state", "lat_1", "lat_2")
    for label, fields in (("current", cur_fields), ("baseline", base_fields)):
        absent = [c for c in needed if c not in fields]
        if absent:
            record["reason"] = (f"the {label} CSV is missing column(s) {absent}; it has {fields}")
            return record

    if len(cur_rows) != len(base_rows) or len(cur_rows) != cfg.days_per_season:
        record["reason"] = (
            f"row counts disagree: current {len(cur_rows)}, baseline {len(base_rows)}, expected "
            f"{cfg.days_per_season}. Aligned on row count first so a short CSV cannot match on its "
            "prefix."
        )
        return record

    cur_dates = [r["date"] for r in cur_rows]
    base_dates = [r["date"] for r in base_rows]
    if cur_dates != base_dates:
        offenders = [(c, b) for c, b in zip(cur_dates, base_dates) if c != b][:5]
        record["reason"] = (f"the `date` columns do not align; first mismatches (current vs "
                            f"baseline) {offenders}")
        return record

    mismatches = []
    for cur, base in zip(cur_rows, base_rows):
        cur_state, base_state = cur["state"], base["state"]
        cur_lats = tuple(_core_lat(cur[c]) for c in ("lat_1", "lat_2"))
        base_lats = tuple(_core_lat(base[c]) for c in ("lat_1", "lat_2"))
        if cur_state != base_state or cur_lats != base_lats:
            mismatches.append({
                "date": cur["date"],
                "current": {"state": cur_state, "lat_1": cur_lats[0], "lat_2": cur_lats[1]},
                "baseline": {"state": base_state, "lat_1": base_lats[0], "lat_2": base_lats[1]},
            })

    record["mismatches"] = mismatches
    record["n_mismatched_rows"] = len(mismatches)
    record["passed"] = not mismatches
    if mismatches:
        record["reason"] = (f"{len(mismatches)} of {len(cur_rows)} row(s) differ in state label or "
                            "core latitude; O3 requires an exact match")
        log.error("2018 regression, comparison 1 FAILED: %d of %d row(s) differ. Offending dates "
                  "(current vs baseline):", len(mismatches), len(cur_rows))
        for item in mismatches[:20]:
            log.error("    %s  state %s vs %s   lat_1 %s vs %s   lat_2 %s vs %s",
                      item["date"], item["current"]["state"], item["baseline"]["state"],
                      item["current"]["lat_1"], item["baseline"]["lat_1"],
                      item["current"]["lat_2"], item["baseline"]["lat_2"])
        if len(mismatches) > 20:
            log.error("    ... and %d more", len(mismatches) - 20)
        log.error("This is risk DR1, named in advance (§A9.3): report it to the operator with the "
                  "marginal rule and its margin. Do NOT retune a threshold to make it match (O3).")
    else:
        log.info("2018 regression, comparison 1: %d/%d rows match exactly on state and core "
                 "latitudes -> PASS", len(cur_rows), cfg.days_per_season)
    return record


def _compare_summary(current: Path, baseline: Path, log: logging.Logger) -> dict:
    """§A9.2 comparison 2: the summary block matches exactly, aligned on line count first."""
    cur_text, base_text = current.read_text(), baseline.read_text()
    cur_lines, base_lines = cur_text.splitlines(), base_text.splitlines()
    record: dict[str, Any] = {
        "name": "summary_txt",
        "current": str(current),
        "baseline": str(baseline),
        "n_lines": len(cur_lines),
        "n_baseline_lines": len(base_lines),
        "passed": False,
        "reason": "",
        "differing_lines": [],
    }
    if len(cur_lines) != len(base_lines):
        record["reason"] = (f"line counts disagree: current {len(cur_lines)}, baseline "
                            f"{len(base_lines)}. Aligned on line count first, so a truncated "
                            "summary fails rather than matching on its prefix.")
        log.error("2018 regression, comparison 2 FAILED: %s", record["reason"])
        return record

    differing = [{"line": i + 1, "current": c, "baseline": b}
                 for i, (c, b) in enumerate(zip(cur_lines, base_lines)) if c != b]
    record["differing_lines"] = differing
    if differing:
        record["reason"] = f"{len(differing)} of {len(cur_lines)} summary line(s) differ"
        log.error("2018 regression, comparison 2 FAILED: %d of %d line(s) differ:",
                  len(differing), len(cur_lines))
        for item in differing[:20]:
            log.error("    line %d\n      baseline: %s\n      current : %s",
                      item["line"], item["baseline"], item["current"])
        if len(differing) > 20:
            log.error("    ... and %d more", len(differing) - 20)
        return record
    if cur_text != base_text:
        record["reason"] = ("every summary line matches but the files differ in trailing bytes "
                            "(line endings or a final newline); O3 asks for an exact match")
        log.error("2018 regression, comparison 2 FAILED: %s", record["reason"])
        return record

    record["passed"] = True
    log.info("2018 regression, comparison 2: the %d-line summary block matches exactly -> PASS",
             len(cur_lines))
    return record


def _compare_profile(cfg: Config, current: Path, baseline: Path, log: logging.Logger) -> dict:
    """§A9.2 comparison 3: max |U_rda - U_cds| <= 0.05 m s-1, and the achieved value is reported.

    Both operands are opened with `profile.open_intermediate` and aligned with `join="exact"`
    *before* anything is subtracted, and the compared-point count is then asserted against
    `days_per_season x n_lat` derived from the config. This is not ceremony:
    `download.check_r1_equivalence` documents exactly why a bare `a - b` is unsafe -- xarray
    defaults `arithmetic_join` to `"inner"`, so mismatched coordinates would silently compare only
    the overlap and pass a gate they never tested. A regression check that can pass on 200 of
    33 813 points is worse than none.

    A bit-exact match is impossible and must not be pursued (§A1.7): the CDS operands are int16-
    packed at ~0.003 m s-1 and this archive is unpacked float32. §A1.7's out-of-pipeline probe
    landed at 1.9e-04 m s-1. The number reported here is the one achieved through the real code
    path.
    """
    from . import profile as profile_mod          # deferred: the seam's own reader

    record: dict[str, Any] = {
        "name": "profile_nc",
        "current": str(current),
        "baseline": str(baseline),
        "tolerance": REGRESSION_TOLERANCE,
        "n_expected": cfg.days_per_season * cfg.sector.n_lat,
        "n_compared": 0,
        "max_abs_diff": None,
        "passed": False,
        "reason": "",
    }
    cur_u = profile_mod.open_intermediate(current)["U"]
    base_u = profile_mod.open_intermediate(baseline)["U"]
    try:
        aligned_cur, aligned_base = xr.align(cur_u, base_u, join="exact")
    except ValueError as exc:                     # xarray's AlignmentError subclasses ValueError
        record["reason"] = (
            f"the two operands do not carry identical coordinates, so any comparison would have "
            f"silently tested only their overlap -- current {dict(cur_u.sizes)} vs baseline "
            f"{dict(base_u.sizes)}: {exc}"
        )
        log.error("2018 regression, comparison 3 FAILED: %s", record["reason"])
        return record

    difference = np.abs(aligned_cur.values.astype("float64")
                        - aligned_base.values.astype("float64"))
    max_abs_diff = float(difference.max())
    n_compared = int(difference.size)
    worst = np.unravel_index(int(np.argmax(difference)), difference.shape)
    record.update({
        "n_compared": n_compared,
        "max_abs_diff": max_abs_diff,
        "mean_abs_diff": float(difference.mean()),
        "median_abs_diff": float(np.median(difference)),
        "p99_abs_diff": float(np.percentile(difference, 99)),
        "max_abs_diff_date": str(np.datetime_as_string(
            np.asarray(aligned_cur["time"].values)[worst[0]], unit="D")),
        "max_abs_diff_latitude": float(np.asarray(aligned_cur["latitude"].values)[worst[1]]),
        "n_exceeding_tolerance": int((difference > REGRESSION_TOLERANCE).sum()),
    })

    if n_compared != record["n_expected"]:
        record["reason"] = (
            f"compared {n_compared} points, expected {record['n_expected']} = "
            f"{cfg.days_per_season} days x {cfg.sector.n_lat} latitudes"
        )
        log.error("2018 regression, comparison 3 FAILED: %s", record["reason"])
        return record

    record["passed"] = max_abs_diff <= REGRESSION_TOLERANCE
    log.info("2018 regression, comparison 3: max |U_rda - U_cds| = %.3e m s-1 over %d compared "
             "points (tolerance %.2f, expected %d points; mean |diff| %.3e) -> %s",
             max_abs_diff, n_compared, REGRESSION_TOLERANCE, record["n_expected"],
             record["mean_abs_diff"], "PASS" if record["passed"] else "FAIL")
    if not record["passed"]:
        record["reason"] = (f"max |diff| {max_abs_diff:.3e} m s-1 exceeds the "
                            f"{REGRESSION_TOLERANCE} m s-1 allowance")
        log.error("2018 regression, comparison 3 FAILED: worst point %s at %.2f N, |diff| "
                  "%.4e m s-1; %d of %d points exceed the tolerance. Distribution of |diff|: mean "
                  "%.3e, median %.3e, 99th pct %.3e.",
                  record["max_abs_diff_date"], record["max_abs_diff_latitude"], max_abs_diff,
                  record["n_exceeding_tolerance"], n_compared, record["mean_abs_diff"],
                  record["median_abs_diff"], record["p99_abs_diff"])
        log.error("Do NOT loosen this tolerance (O3). Stop and show the operator the diff.")
    return record


def check_regression_2018(cfg: Config, baseline_dir: str | Path, out_paths: Any,
                          out_json: str | Path, log: logging.Logger) -> dict:
    """The gate between the loader and the campaign (§A9): three comparisons, one evidence file.

    1. `smoke_<year>_jet_states.csv` -- state labels *and* core latitudes match exactly, all 153
       rows, aligned on the `date` column and on row count first.
    2. `smoke_<year>_summary.txt` -- the summary block matches exactly, aligned on line count first.
    3. `smoke_<year>_profile.nc` `U` -- max-abs difference <= 0.05 m s-1, over a point count
       asserted against the config, both operands aligned with `join="exact"` before subtraction.

    **This function does not raise on a comparison failure, and that is deliberate** (§A7.3 item 3,
    ruling O5): the run finishes, the smoke figure is written, the result is reported, and only then
    does the caller set the exit code -- so a mismatch hands the operator a figure and a diff rather
    than a bare traceback, and a simultaneous fraction-gate failure can be reported alongside it in
    one exit. It *does* raise `DownloadError` when an operand file is absent, because that is a
    wiring fault rather than a science result.

    On failure the log carries the diagnosis the operator needs to act: the offending dates with
    both state labels and both core latitudes; the differing summary lines; the max-abs value with
    its day and latitude and the distribution behind it. **Do not loosen a tolerance and do not
    change the loader, the seam or a threshold to make it match** (O3, plan §11).

    The baseline's `results/smoke_<year>/smoke_<year>_profile.nc` carries the *old* `profile_sha256`
    and is a **numeric comparison operand only** -- it must never be fed to `classify.py`.
    """
    baseline_dir = Path(baseline_dir)
    out_json = Path(out_json)
    tag = f"smoke_{cfg.smoke_year}"

    current = {
        "states_csv": _require_operand(_run_output(out_paths, "states_csv"), "current states CSV"),
        "summary": _require_operand(_run_output(out_paths, "summary"), "current summary"),
        "profile": _require_operand(_run_output(out_paths, "profile"), "current profile"),
    }
    baseline = {
        "states_csv": _require_operand(baseline_dir / f"{tag}_jet_states.csv",
                                      "baseline states CSV"),
        "summary": _require_operand(baseline_dir / f"{tag}_summary.txt", "baseline summary"),
        "profile": _require_operand(baseline_dir / f"{tag}_profile.nc", "baseline profile"),
    }

    log.info("2018 regression (§A9): %s rebuilt from %s, against the committed CDS baseline in %s",
             tag, cfg.active_dataset, baseline_dir)
    comparisons = [
        _compare_states_csv(cfg, current["states_csv"], baseline["states_csv"], log),
        _compare_summary(current["summary"], baseline["summary"], log),
        _compare_profile(cfg, current["profile"], baseline["profile"], log),
    ]
    profile_record = comparisons[-1]

    record = {
        "year": cfg.smoke_year,
        "passed": bool(all(c["passed"] for c in comparisons)),
        "source": cfg.source,
        "source_dataset": cfg.active_dataset,
        "baseline_dir": str(baseline_dir),
        "tolerance": REGRESSION_TOLERANCE,
        "max_abs_diff": profile_record["max_abs_diff"],
        "n_compared": profile_record["n_compared"],
        "n_expected": profile_record["n_expected"],
        "comparisons": {c["name"]: c for c in comparisons},
        "passed_by_comparison": {c["name"]: bool(c["passed"]) for c in comparisons},
        "profile_sha256": cfg.profile_sha256,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "plan": "wave1-plan-derecho-addendum.md",
        "note": ("a bit-exact profile match is impossible and must not be pursued: the CDS "
                 "operands are int16-packed and the RDA archive is unpacked float32 "
                 "(addendum §A1.7)"),
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")

    log.info("2018 regression: states_csv %s, summary_txt %s, profile_nc %s (max |diff| %s m s-1, "
             "tolerance %.2f) -> %s",
             *("PASS" if c["passed"] else "FAIL" for c in comparisons),
             "n/a" if profile_record["max_abs_diff"] is None
             else f"{profile_record['max_abs_diff']:.3e}",
             REGRESSION_TOLERANCE, "PASS" if record["passed"] else "FAIL")
    log.info("2018 regression record written to %s", out_json)
    if not record["passed"]:
        failed = [c["name"] for c in comparisons if not c["passed"]]
        log.error("2018 REGRESSION FAILED on %s. STOP and show the operator the diff -- do not "
                  "change the loader, the seam, or a threshold to make it match (O3, §A9.2). "
                  "Nothing runs at 47-season scale until this passes.", ", ".join(failed))
    return record
