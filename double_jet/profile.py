"""Raw ERA5 season files -> the cached, unsmoothed zonal-mean intermediate (plan §4.2).

This module is the pipeline's only reader of raw ERA5. `open_normalized` implements steps 1-8 of
plan §4.2 **in order**, each one a hard failure whose message names the check and the value seen, so
that coordinate names, level, longitude convention, latitude order, units and missing data are
settled in exactly one place. Both operands of the R1 equivalence gate (§4.1) and every season of
the intermediate go through it, which is what makes them comparable by construction rather than by
hope.

`season_profile` is step 9 -- the plain unweighted zonal mean of I7. `build_intermediate`
concatenates the seasons, writes `U(time, latitude)` as float32/zlib-4, and records the provenance
attributes M3 is verified against (including `profile_sha256`, which `classify.py` compares with the
config it was handed). `open_intermediate` is the single reader used by `classify.py` and
`figure.py`; after it, nothing downstream ever touches a raw file.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

from .config import PLAN_PATH, Config

# Accepted spellings, plan §4.2 step 1. Resolution is by lookup with a hard failure; a name outside
# these sets is an error, never a guess.
LAT_NAMES = ("latitude", "lat")
LON_NAMES = ("longitude", "lon")
TIME_NAMES = ("valid_time", "time")
LEVEL_NAMES = ("pressure_level", "level", "isobaricInhPa")

# Scalar coordinates the new CDS netCDFs carry (§1.6); dropped, never carried downstream.
SCALAR_COORDS_DROPPED = ("number", "expver")

# Units, read not assumed (§4.2 step 6). The thresholds in configs/double_jet.yaml are in m s-1 and
# nothing downstream converts, so an unexpected unit is a stop, not a conversion.
LAT_UNITS = "degrees_north"
LON_UNITS = "degrees_east"
LEVEL_UNITS = "hPa"
WIND_UNITS = ("m s**-1", "m s-1", "m/s")

# Tolerance of the whole-array grid comparison (§4.2 steps 4 and 5).
GRID_TOL = 1e-6

# Fixed time encoding for the intermediate: integer seconds are exact for any ERA5 timestamp and
# decode back to datetime64[ns], so a rebuild is byte-reproducible rather than xarray-default.
TIME_ENCODING = {"units": "seconds since 1970-01-01 00:00:00", "calendar": "proleptic_gregorian",
                 "dtype": "int64"}


class ProfileError(ValueError):
    """A plan §4.2 gate fired: the raw file is not what the contract says it must be."""


# ---------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------


def _resolve_name(ds: xr.Dataset, candidates: Sequence[str], kind: str, path: Path) -> str:
    """Step 1: the one accepted name present, or a failure listing what the file actually has."""
    present = [name for name in candidates if name in ds.variables]
    if len(present) == 1:
        return present[0]
    seen = sorted(map(str, ds.variables))
    if not present:
        raise ProfileError(
            f"{path}: no {kind} coordinate found; accepted names are {list(candidates)}, "
            f"the file has {seen}"
        )
    raise ProfileError(
        f"{path}: ambiguous {kind} coordinate; {present} are all present and only one may be"
    )


def _resolve_wind(ds: xr.Dataset, cfg: Config, path: Path) -> str:
    """The wind variable. One data variable is the normal case; `u` disambiguates a fuller file."""
    data_vars = [str(v) for v in ds.data_vars]
    if len(data_vars) == 1:
        return data_vars[0]
    if "u" in data_vars:
        return "u"
    raise ProfileError(
        f"{path}: cannot identify the {cfg.variable} field; expected a single data variable or one "
        f"named 'u', the file has {sorted(data_vars)}"
    )


def _replace_coord(obj: xr.DataArray, name: str, values: np.ndarray) -> xr.DataArray:
    """`assign_coords` drops the coordinate's attrs, and step 6 must still read the file's units."""
    attrs = dict(obj[name].attrs)
    obj = obj.assign_coords({name: values})
    obj[name].attrs = attrs
    return obj


def _check_units(attrs: Mapping[str, Any], name: str, accepted: Sequence[str], path: Path) -> str:
    """Step 6. A missing `units` attribute is a failure too: unstated is not the same as correct."""
    units = attrs.get("units")
    if units is None:
        raise ProfileError(
            f"{path}: {name} carries no 'units' attribute; units are read, not assumed"
        )
    if str(units) not in accepted:
        raise ProfileError(
            f"{path}: {name} units are {units!r}, which is not one of {list(accepted)}"
        )
    return str(units)


def _assert_grid(actual: np.ndarray, expected: np.ndarray, axis: str, path: Path) -> None:
    """Steps 4 and 5: the WHOLE array, not the count and the two bounds.

    Count-and-bounds would accept a non-uniform axis, and I1's "11 samples = 2.5 deg" boxcar
    silently depends on the spacing being uniform.
    """
    if actual.size != expected.size:
        raise ProfileError(
            f"{path}: {axis} has {actual.size} points, expected {expected.size} "
            f"({expected[0]:g}..{expected[-1]:g} at {expected[1] - expected[0]:g} deg)"
        )
    diff = np.abs(actual - expected)
    worst = int(np.argmax(diff))
    if diff[worst] > GRID_TOL:
        raise ProfileError(
            f"{path}: {axis} does not match the configured grid to {GRID_TOL:g} deg; worst point "
            f"is index {worst}, file has {actual[worst]!r}, config expects {expected[worst]!r} "
            f"(max |diff| {diff[worst]:.3e})"
        )


def _minutes_of_day(times: np.ndarray) -> np.ndarray:
    minutes = times.astype("datetime64[m]")
    return (minutes - minutes.astype("datetime64[D]")).astype("timedelta64[m]").astype(np.int64)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------------------------
# step 1-8: the normalizing reader
# ---------------------------------------------------------------------------------------------


def open_normalized(path: str | Path, cfg: Config, hourly: bool = False) -> xr.DataArray:
    """Open one raw season file and return `u` with dims exactly ("time", "latitude", "longitude").

    Steps 1-8 of plan §4.2, in order. `hourly=True` reads the R1 cross-check file, which differs
    from the daily one only in step 7's time expectation.
    """
    path = Path(path)
    with xr.open_dataset(path) as raw:
        ds = raw.load()      # small (30 MB/season); loading here closes the handle for the caller

    # -- step 1: resolve coordinate names by lookup ------------------------------------------
    lat_name = _resolve_name(ds, LAT_NAMES, "latitude", path)
    lon_name = _resolve_name(ds, LON_NAMES, "longitude", path)
    time_name = _resolve_name(ds, TIME_NAMES, "time", path)
    wind_name = _resolve_wind(ds, cfg, path)

    # -- step 2: assert the level by VALUE, never by index ------------------------------------
    level_name = _resolve_name(ds, LEVEL_NAMES, "pressure level", path)
    levels = np.atleast_1d(np.asarray(ds[level_name].values))
    if levels.size != 1:
        raise ProfileError(
            f"{path}: pressure coordinate {level_name!r} holds {levels.size} levels {levels!r}; "
            f"exactly one ({cfg.pressure_level}) is required"
        )
    level_value = float(levels[0])
    # The units check itself is step 6; the attributes are captured here because the coordinate is
    # squeezed and finally dropped, and because a file may store it as a variable, not a coordinate.
    level_attrs = dict(ds[level_name].attrs)
    if abs(level_value - cfg.pressure_level) > GRID_TOL:
        raise ProfileError(
            f"{path}: pressure level read from {level_name!r} is {level_value:g}, "
            f"config requires {cfg.pressure_level}"
        )
    if level_name in ds.dims:
        # Squeeze only now that the value has been asserted; drop=False keeps the scalar coordinate
        # so step 6 can still read its units.
        ds = ds.squeeze(level_name, drop=False)

    # -- step 3: drop the scalar number / expver coordinates ----------------------------------
    ds = ds.drop_vars([c for c in SCALAR_COORDS_DROPPED if c in ds.variables])

    da = ds[wind_name]

    # -- step 4: longitude -> [-180, 180), ascending, whole array asserted --------------------
    lon = np.asarray(da[lon_name].values, dtype=float)
    da = _replace_coord(da, lon_name, ((lon + 180.0) % 360.0) - 180.0)
    da = da.sortby(lon_name)
    _assert_grid(np.asarray(da[lon_name].values, dtype=float), cfg.sector.longitudes(),
                 "longitude", path)

    # -- step 5: latitude ascending, whole array asserted -------------------------------------
    da = da.sortby(lat_name)
    _assert_grid(np.asarray(da[lat_name].values, dtype=float), cfg.sector.latitudes(),
                 "latitude", path)

    # -- step 6: units, read not assumed ------------------------------------------------------
    _check_units(da[lat_name].attrs, f"latitude coordinate {lat_name!r}", (LAT_UNITS,), path)
    _check_units(da[lon_name].attrs, f"longitude coordinate {lon_name!r}", (LON_UNITS,), path)
    # A Pa-tagged coordinate would make step 2's "= 250" wrong by a factor of 100.
    _check_units(level_attrs, f"pressure coordinate {level_name!r}", (LEVEL_UNITS,), path)
    _check_units(da.attrs, f"wind variable {wind_name!r}", WIND_UNITS, path)

    # The grids are now proven equal to the config to 1e-6, so adopt the config's own values: two
    # seasons whose coordinates differ in the last float bit would otherwise misalign on concat.
    da = _replace_coord(da, lon_name, cfg.sector.longitudes())
    da = _replace_coord(da, lat_name, cfg.sector.latitudes())

    # -- step 7: time -------------------------------------------------------------------------
    _assert_time(da[time_name].values, cfg, hourly, path)

    # -- step 8: everywhere finite, so +/-inf is caught as well as NaN ------------------------
    values = np.asarray(da.values)
    finite = np.isfinite(values)
    if not finite.all():
        bad = int((~finite).sum())
        first = np.argwhere(~finite)[0]
        raise ProfileError(
            f"{path}: wind field has {bad} non-finite value(s) of {values.size}; first at index "
            f"{tuple(int(i) for i in first)} with value {values[tuple(first)]!r}"
        )

    # -- canonical shape: one name and one dim order for every caller -------------------------
    da = da.drop_vars(level_name, errors="ignore")
    renames = {time_name: "time", lat_name: "latitude", lon_name: "longitude"}
    da = da.rename({old: new for old, new in renames.items() if old != new})
    extra = [str(d) for d in da.dims if d not in ("time", "latitude", "longitude")]
    if extra:
        raise ProfileError(
            f"{path}: wind field keeps unexpected dimension(s) {extra} after normalization; "
            f"dims are {tuple(str(d) for d in da.dims)}"
        )
    da = da.transpose("time", "latitude", "longitude")
    da.name = "u"
    return da


def _assert_time(times: np.ndarray, cfg: Config, hourly: bool, path: Path) -> None:
    """Step 7. Daily: one timestamp per season day. Hourly: `cfg.hourly_times` on each of them."""
    times = np.asarray(times)
    if not np.issubdtype(times.dtype, np.datetime64):
        raise ProfileError(f"{path}: time coordinate has dtype {times.dtype}, expected datetime64")
    if np.isnat(times).any():
        raise ProfileError(f"{path}: time coordinate holds {int(np.isnat(times).sum())} NaT values")

    per_day = len(cfg.hourly_times) if hourly else 1
    expected = cfg.days_per_season * per_day
    if times.size != expected:
        raise ProfileError(
            f"{path}: {times.size} timestamps, expected {expected} "
            f"({cfg.days_per_season} season days x {per_day} per day)"
        )

    days, counts = np.unique(times.astype("datetime64[D]"), return_counts=True)
    if days.size != cfg.days_per_season:
        raise ProfileError(
            f"{path}: {days.size} unique days, expected {cfg.days_per_season} "
            f"({days[0]} .. {days[-1]})"
        )
    if not (counts == per_day).all():
        offending = days[counts != per_day][:5]
        raise ProfileError(
            f"{path}: {int((counts != per_day).sum())} day(s) do not carry exactly {per_day} "
            f"timestamp(s); first offenders {[str(d) for d in offending]}"
        )

    years = np.unique(days.astype("datetime64[Y]").astype(int) + 1970)
    if years.size != 1:
        raise ProfileError(f"{path}: days span {years.size} years {years.tolist()}, expected one")
    months = np.unique(days.astype("datetime64[M]").astype(int) % 12 + 1)
    unwanted = sorted(int(m) for m in months if int(m) not in cfg.season_months)
    if unwanted:
        raise ProfileError(
            f"{path}: days fall in month(s) {unwanted} of {int(years[0])}, outside the configured "
            f"season {list(cfg.season_months)}"
        )

    if hourly:
        want = sorted(int(t.split(":")[0]) * 60 + int(t.split(":")[1]) for t in cfg.hourly_times)
        got = sorted(set(_minutes_of_day(times).tolist()))
        if got != want:
            fmt = [f"{m // 60:02d}:{m % 60:02d}" for m in got]
            raise ProfileError(
                f"{path}: hours present are {fmt}, config requires {list(cfg.hourly_times)}"
            )


# ---------------------------------------------------------------------------------------------
# step 9 and the intermediate
# ---------------------------------------------------------------------------------------------


def season_profile(path: str | Path, cfg: Config) -> xr.DataArray:
    """Step 9: `U(time, latitude)`, the plain unweighted mean over the 361 longitudes (I7).

    Equal weight per longitude, as the contract states -- no trapezoid, no cos(phi) weighting (the
    average is along longitude at fixed latitude, where the metric factor is constant).
    """
    u = open_normalized(path, cfg, hourly=False)
    units = u.attrs.get("units")
    profile = u.mean("longitude", skipna=False)      # step 8 proved every value finite
    profile.name = "U"
    profile.attrs = {
        "long_name": f"zonal-mean {cfg.variable} at {cfg.pressure_level} hPa",
        "units": units,
        "cell_methods": "longitude: mean",
        "comment": "unsmoothed; equal weight per longitude (plan §2 I7)",
    }
    return profile


def build_intermediate(cfg: Config, years: list[int], out_path: Path, log) -> Path:
    """Concatenate the requested seasons into the cached intermediate (plan §4.2, deliverable M3).

    Every downstream stage reads only this file, so its attributes carry the whole provenance chain:
    what was requested, which bytes answered, and which code and config produced it.
    """
    # Imported here, not at module scope: download.check_r1_equivalence imports open_normalized from
    # this module, and a top-level import in both directions is a cycle.
    from .download import build_request, season_paths

    if not years:
        raise ProfileError("build_intermediate was given no years to concatenate")

    out_path = Path(out_path)
    profiles: list[xr.DataArray] = []
    sources: list[dict[str, Any]] = []
    for year in years:
        nc = Path(season_paths(cfg, year, hourly=False)["nc"])
        if not nc.exists():
            raise ProfileError(
                f"season {year}: {nc} does not exist; run the download stage (or --skip-download "
                "will report every missing season)"
            )
        log.info("profile: reading season %d from %s", year, nc)
        profiles.append(season_profile(nc, cfg))
        sources.append({"year": year, "name": nc.name, "bytes": nc.stat().st_size,
                        "sha256": _sha256(nc)})

    # join="exact" rather than the default outer join: a season whose latitudes drifted would
    # otherwise be padded with NaN instead of stopping the run.
    combined = xr.concat(profiles, dim="time", join="exact").sortby("time")

    expected_days = len(years) * cfg.days_per_season
    times = np.asarray(combined["time"].values)
    if times.size != expected_days or np.unique(times).size != expected_days:
        raise ProfileError(
            f"{out_path}: concatenated {times.size} days ({np.unique(times).size} unique), "
            f"expected {expected_days} = {len(years)} seasons x {cfg.days_per_season} days"
        )

    ds = xr.Dataset({"U": combined.astype("float32")})
    ds = ds.assign_coords(latitude=ds["latitude"].astype("float64"))
    ds["latitude"].attrs = {"units": LAT_UNITS, "long_name": "latitude"}
    ds.attrs = _intermediate_attrs(cfg, years, sources, build_request(cfg, years[0]))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(
        out_path,
        encoding={"U": {"zlib": True, "complevel": 4, "dtype": "float32"},
                  "time": dict(TIME_ENCODING)},
    )
    log.info("profile: wrote %s -- %d days x %d latitudes from %d season(s) %d-%d, %.1f MB",
             out_path, ds.sizes["time"], ds.sizes["latitude"], len(years), min(years), max(years),
             out_path.stat().st_size / 1e6)
    return out_path


def _intermediate_attrs(cfg: Config, years: list[int], sources: list[dict[str, Any]],
                        request: dict) -> dict[str, Any]:
    """Plan §4.2's attribute list. Structured values are JSON strings; netCDF takes no dicts."""
    provenance = cfg.provenance()
    return {
        "title": f"Unsmoothed zonal-mean {cfg.variable} at {cfg.pressure_level} hPa, "
                 f"{cfg.sector.lat_min:g}-{cfg.sector.lat_max:g}N "
                 f"{cfg.sector.lon_min:g}-{cfg.sector.lon_max:g}E",
        "source_dataset": cfg.dataset,
        "variable": cfg.variable,
        "pressure_level": int(cfg.pressure_level),
        "pressure_level_units": LEVEL_UNITS,
        "sector": json.dumps(cfg.profile_fields()["sector"], sort_keys=True),
        "season_months": json.dumps(list(cfg.season_months)),
        "years": json.dumps(list(years)),
        "days_per_season": int(cfg.days_per_season),
        "source_files": json.dumps(sources),
        "request_template": json.dumps(request, sort_keys=True),
        "request_template_year": int(years[0]),
        "profile_fields": json.dumps(cfg.profile_fields(), sort_keys=True),
        "config_path": provenance["config_path"],
        "config_sha256": provenance["config_sha256"],
        # classify.py compares this against the config it was handed, so a reused intermediate from
        # a different sector or level fails loudly instead of silently (plan §4.3).
        "profile_sha256": provenance["profile_sha256"],
        "interpreter": provenance["interpreter"],
        "package_versions": json.dumps(provenance["package_versions"], sort_keys=True),
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "plan": PLAN_PATH,
    }


def open_intermediate(path: str | Path) -> xr.Dataset:
    """The one reader `classify.py` and `figure.py` use; nothing downstream opens a raw file."""
    path = Path(path)
    with xr.open_dataset(path) as raw:
        ds = raw.load()
    if "U" not in ds.data_vars:
        raise ProfileError(
            f"{path}: not a double-jet intermediate; expected a variable 'U', found "
            f"{sorted(str(v) for v in ds.data_vars)}"
        )
    dims = tuple(str(d) for d in ds["U"].dims)
    if dims != ("time", "latitude"):
        raise ProfileError(f"{path}: U has dims {dims}, expected ('time', 'latitude')")
    return ds
