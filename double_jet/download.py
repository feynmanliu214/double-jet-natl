"""CDS retrieval: the raw `$SCRATCH` season cache, and the R1 equivalence gate (plan §4.1).

Three properties this module owes the rest of the pipeline:

* **Identity, not merely presence** (§4.1, risk R11) -- a season is skipped only when its `.nc` opens
  with the expected shape *and* its `.request.json` sidecar equals, key for key, the request that
  would be issued right now. A file fetched under a different area, level or frequency can therefore
  never be silently reused after a config edit.
* **Atomicity** (§4.1) -- every byte lands in `<name>.part` and is renamed only after the ZIP
  extracts and the shape check passes, so an interrupted job leaves nothing a later run accepts as
  complete.
* **Preflight before request** (§1.8, risk R10) -- `skx-dev` outbound network is unproven, so the
  probe resolves and reaches both CDS endpoints and exits with a labelled message *before* any CDS
  request is issued.

The raw-cache file names under `$SCRATCH` are fixed by the plan's §6 table and are owned here;
`cli.output_names` owns every path under `data/` and `figs/`.
"""

from __future__ import annotations

import http.client
import json
import logging
import os
import shutil
import socket
import threading
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import xarray as xr

from .config import Config

# The §1.8 probe targets: the API the client talks to, and the object store the data itself is
# served from. A failure of either is a partition surprise, not a science failure.
PROBE_HOST = "cds.climate.copernicus.eu"
PROBE_URLS = (
    "https://cds.climate.copernicus.eu/api",
    "https://object-store.os-api.cci2.ecmwf.int/",
)
PROBE_TIMEOUT_S = 10.0

# §4.2 step 1's name lookup, reused here so the shape check never assumes a spelling.
_DIM_CANDIDATES = {
    "time": ("valid_time", "time"),
    "latitude": ("latitude", "lat"),
    "longitude": ("longitude", "lon"),
}

_PART_SUFFIX = ".part"

# One `cdsapi.Client()` per worker thread: the client is not documented thread-safe, and a
# thread-local costs nothing (§4.1).
_thread_state = threading.local()


class PreflightError(RuntimeError):
    """A network probe failed; `cli.run` maps this to exit 2, before any CDS request."""


class DownloadError(RuntimeError):
    """A season could not be retrieved, or what is on disk is not what was asked for."""


# -- requests ------------------------------------------------------------------------------------


def build_request(cfg: Config, year: int) -> dict:
    """The derived daily-statistics request, exactly the §4.1 template.

    Two things that look like omissions and are not:

    * **No `grid` key, ever** (§1.6). Since the 2026-02-25 area-extraction change, a grid-aligned
      `area` with no `grid` crops to native points without interpolating; passing `grid` would
      re-enable interpolation and silently change the data.
    * **No `data_format` / `download_format`** (§1.4). This process exposes neither: it always
      returns a ZIP holding one netCDF per variable.

    `day` runs 01..31 against 30-day months on purpose (§1.5): CDS drops the invalid dates, and the
    measured request cost of 153 is exactly the MJJAS day count.
    """
    return {
        "product_type": "reanalysis",
        "variable": [cfg.variable],
        "year": str(year),
        "month": cfg.month_strings(),
        "day": [f"{d:02d}" for d in range(1, 32)],
        "pressure_level": [str(cfg.pressure_level)],
        "daily_statistic": cfg.daily_statistic,
        "time_zone": cfg.time_zone,
        "frequency": cfg.frequency,
        "area": cfg.sector.area(),          # [North, West, South, East]
    }


def build_hourly_request(cfg: Config, year: int) -> dict:
    """The R1 cross-check request against `cfg.hourly_dataset` (§4.1): the same season, same sector,
    same level, at exactly the hours the derived daily mean is built from. Unarchived netCDF, so
    there is no ZIP to extract. Again no `grid` key, for the reason in `build_request`.
    """
    return {
        "product_type": "reanalysis",
        "variable": [cfg.variable],
        "year": str(year),
        "month": cfg.month_strings(),
        "day": [f"{d:02d}" for d in range(1, 32)],
        "time": list(cfg.hourly_times),
        "pressure_level": [str(cfg.pressure_level)],
        "data_format": "netcdf",
        "download_format": "unarchived",
        "area": cfg.sector.area(),
    }


# -- paths and completeness ----------------------------------------------------------------------


def season_paths(cfg: Config, year: int, hourly: bool = False) -> dict:
    """The three raw-cache paths for one season (§6). `zip` is None for the unarchived 6-hourly
    file, which arrives as netCDF directly.
    """
    stem = f"u250_natl_mjjas_{year}_6hourly" if hourly else f"u250_natl_mjjas_{year}"
    root = cfg.paths.scratch_raw
    return {
        "nc": root / f"{stem}.nc",
        "request": root / f"{stem}.request.json",
        "zip": None if hourly else root / f"{stem}.zip",
    }


def _expected_sizes(cfg: Config, hourly: bool) -> dict[str, int]:
    """Daily 153 x 221 x 361, 6-hourly 612 x 221 x 361 -- both read off the config, never literal."""
    per_day = len(cfg.hourly_times) if hourly else 1
    return {
        "time": cfg.days_per_season * per_day,
        "latitude": cfg.sector.n_lat,
        "longitude": cfg.sector.n_lon,
    }


def _check_shape(cfg: Config, nc_path: Path, hourly: bool) -> tuple[bool, str]:
    """(ok, one-line reason). Dimensions are resolved by name lookup, so a size-1 level dimension or
    a `valid_time` spelling is not mistaken for a wrong shape.
    """
    expected = _expected_sizes(cfg, hourly)
    try:
        with xr.open_dataset(nc_path) as ds:
            sizes = dict(ds.sizes)
    except Exception as exc:                      # any backend failure means "not usable"
        return False, f"{nc_path} does not open as netCDF: {exc}"
    for axis, candidates in _DIM_CANDIDATES.items():
        present = [c for c in candidates if c in sizes]
        if len(present) != 1:
            return False, (f"{nc_path}: expected exactly one {axis} dimension named one of "
                           f"{list(candidates)}, found {present}")
        got = sizes[present[0]]
        if got != expected[axis]:
            return False, (f"{nc_path}: dimension {present[0]} has {got} points, expected "
                           f"{expected[axis]}")
    return True, ""


def _canonical_scalar(value):
    """`250` and `"250"` are the same request value; `"utc+00:00"` is not a number and stays text."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value)
    try:
        return float(text)
    except ValueError:
        return text


def _canonical_request(request: dict) -> dict:
    """Comparable form: list order and int-vs-str never cause a false mismatch, but a genuinely
    different value does. `area` keeps its order, because [N, W, S, E] is positional -- a permuted
    box is a different box and must mismatch.
    """
    out = {}
    for key, value in request.items():
        if isinstance(value, (list, tuple)):
            items = [_canonical_scalar(v) for v in value]
            out[key] = items if key == "area" else sorted(items, key=repr)
        else:
            out[key] = _canonical_scalar(value)
    return out


def season_is_complete(cfg: Config, year: int, hourly: bool = False) -> tuple[bool, str]:
    """True only when the `.nc` opens with the expected shape, the `.request.json` sidecar exists,
    and that sidecar equals the request that would be issued now (§4.1). Otherwise (False, reason).
    """
    paths = season_paths(cfg, year, hourly=hourly)
    nc_path, sidecar = paths["nc"], paths["request"]

    if not nc_path.exists():
        return False, f"{nc_path} is missing"
    ok, reason = _check_shape(cfg, nc_path, hourly)
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

    wanted = build_hourly_request(cfg, year) if hourly else build_request(cfg, year)
    have, want = _canonical_request(stored), _canonical_request(wanted)
    if have != want:
        changed = sorted(k for k in set(have) | set(want) if have.get(k) != want.get(k))
        detail = "; ".join(f"{k}: on disk {repr(have.get(k))[:60]} vs now {repr(want.get(k))[:60]}"
                           for k in changed)
        return False, f"{sidecar} does not match the request that would be issued now -- {detail}"
    return True, ""


# -- retrieval -----------------------------------------------------------------------------------


def preflight_network(log: logging.Logger) -> None:
    """Resolve and reach both CDS endpoints, or raise `PreflightError` (§1.8, risk R10).

    Issues no CDS request itself. Any HTTP status counts as reachable -- the API answers 202, 200 or
    404 depending on the path -- so only a DNS, transport or timeout failure is a failure.
    """
    try:
        addresses = socket.getaddrinfo(PROBE_HOST, 443, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise PreflightError(
            f"network preflight FAILED at the DNS probe of {PROBE_HOST}: {exc}. Exiting before any "
            "CDS request is issued (plan §1.8, risk R10)."
        ) from exc
    log.info("preflight DNS %s -> %s", PROBE_HOST, addresses[0][4][0])

    for url in PROBE_URLS:
        try:
            with urllib.request.urlopen(url, timeout=PROBE_TIMEOUT_S) as response:
                status = response.status
        except urllib.error.HTTPError as exc:
            status = exc.code                     # an answered request: the endpoint is reachable
        except (urllib.error.URLError, http.client.HTTPException, OSError) as exc:
            raise PreflightError(
                f"network preflight FAILED at the HTTPS probe of {url}: {exc}. Exiting before any "
                "CDS request is issued (plan §1.8, risk R10)."
            ) from exc
        log.info("preflight HTTPS %s -> %s", url, status)


def extract_zip(zip_path: Path, dest_nc: Path) -> Path:
    """Extract the derived product's single netCDF member (§1.4) to `dest_nc`.

    Zero members or more than one is a `DownloadError`: the transport container is documented to
    hold one file per variable, and this wave asks for exactly one variable.
    """
    with zipfile.ZipFile(zip_path) as archive:
        members = [n for n in archive.namelist() if n.lower().endswith(".nc")]
        if len(members) != 1:
            raise DownloadError(
                f"{zip_path} holds {len(members)} netCDF members, expected exactly 1: "
                f"{archive.namelist()}"
            )
        with archive.open(members[0]) as src, open(dest_nc, "wb") as dst:
            shutil.copyfileobj(src, dst)
    return dest_nc


def _client():
    """The calling thread's `cdsapi.Client`, created on first use.

    cdsapi is imported here rather than at module scope so `--skip-download` and the unit tests
    never depend on it.
    """
    client = getattr(_thread_state, "client", None)
    if client is None:
        import cdsapi

        client = _thread_state.client = cdsapi.Client()
    return client


def _download_season(cfg: Config, year: int, hourly: bool, log: logging.Logger) -> None:
    """Retrieve one season atomically: `.part` everywhere, rename only once the shape check passes,
    and write the sidecar only once the `.nc` is in place (§4.1).
    """
    paths = season_paths(cfg, year, hourly=hourly)
    request = build_hourly_request(cfg, year) if hourly else build_request(cfg, year)
    dataset = cfg.hourly_dataset if hourly else cfg.dataset
    label = f"{year} 6-hourly" if hourly else f"{year}"

    nc_part = paths["nc"].with_name(paths["nc"].name + _PART_SUFFIX)
    zip_part = None if hourly else paths["zip"].with_name(paths["zip"].name + _PART_SUFFIX)

    log.info("season %s: requesting %s", label, dataset)
    try:
        if hourly:
            _client().retrieve(dataset, request, str(nc_part))
        else:
            # Plan §1.4 recorded, from ECMWF's documentation, that the derived product *always*
            # returns a ZIP. Measured otherwise on 2026-09-03 (smoke job 3466587): the retrieval
            # delivered a bare netCDF and `extract_zip` failed with "File is not a zip file".
            # The container is therefore detected, not assumed. Either form yields the same `.nc`
            # artifact, and §4.1 already treats the ZIP as incidental transport rather than a
            # deliverable, so nothing downstream changes. See docs/deviations.md.
            _client().retrieve(dataset, request, str(zip_part))
            if zipfile.is_zipfile(zip_part):
                extract_zip(zip_part, nc_part)
            else:
                os.replace(zip_part, nc_part)
                zip_part = None          # there was no transport container to keep
        ok, reason = _check_shape(cfg, nc_part, hourly)
        if not ok:
            raise DownloadError(f"season {label}: the retrieved file failed the shape check: "
                                f"{reason}")
        os.replace(nc_part, paths["nc"])
        if zip_part is not None:
            # The ZIP is an incidental transport file, not an artifact (§4.1); it is kept, because
            # the pipeline deletes nothing, but nothing downstream requires it.
            os.replace(zip_part, paths["zip"])
        paths["request"].write_text(json.dumps(request, indent=2, sort_keys=True) + "\n")
    except BaseException:
        # A killed or failed job must leave nothing a later run could accept as complete.
        for partial in (nc_part, zip_part):
            if partial is not None:
                partial.unlink(missing_ok=True)
        raise
    log.info("season %s: complete (%.1f MB)", label, paths["nc"].stat().st_size / 1e6)


def _season_tasks(cfg: Config, years: list[int], smoke: bool) -> list[tuple[int, bool]]:
    """(year, hourly) pairs for one run. `smoke` adds the R1 cross-check file for the smoke year."""
    tasks = [(year, False) for year in years]
    if smoke:
        tasks.append((cfg.smoke_year, True))
    return tasks


def run_download(cfg: Config, years: list[int], smoke: bool, log: logging.Logger) -> None:
    """Fetch every season that is not already complete, at most `cfg.max_in_flight` at once.

    Per-season exceptions are collected rather than swallowed and re-raised together, so a partial
    campaign exits non-zero with the full list and an identical rerun completes only the gaps
    (§4.1, risk R5).
    """
    cfg.paths.scratch_raw.mkdir(parents=True, exist_ok=True)

    tasks = _season_tasks(cfg, years, smoke)
    pending: list[tuple[int, bool]] = []
    for year, hourly in tasks:
        ok, reason = season_is_complete(cfg, year, hourly=hourly)
        label = f"{year} 6-hourly" if hourly else f"{year}"
        if ok:
            log.info("season %s: already complete, skipping", label)
        else:
            log.info("season %s: will be downloaded -- %s", label, reason)
            pending.append((year, hourly))

    if not pending:
        log.info("all %d requested season(s) are already complete", len(tasks))
        return

    log.info("downloading %d season(s) into %s, at most %d in flight",
             len(pending), cfg.paths.scratch_raw, cfg.max_in_flight)
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=cfg.max_in_flight) as pool:
        futures = {pool.submit(_download_season, cfg, year, hourly, log): (year, hourly)
                   for year, hourly in pending}
        for future in as_completed(futures):
            year, hourly = futures[future]
            try:
                future.result()
            except Exception as exc:
                label = f"{year} 6-hourly" if hourly else f"{year}"
                log.error("season %s failed: %s", label, exc)
                failures.append(f"{label}: {exc}")

    if failures:
        raise DownloadError(
            f"{len(failures)} of {len(pending)} season(s) failed to download:\n  "
            + "\n  ".join(failures)
        )


def ensure_downloaded(cfg: Config, years: list[int], smoke: bool, log: logging.Logger) -> None:
    """`--skip-download`: validate what is already on `$SCRATCH` and fail loudly (§4.1).

    Constructs no client and issues no request. Every requested season is checked, and every one
    that is missing or fails any part of the identity check is reported together.
    """
    missing: list[str] = []
    tasks = _season_tasks(cfg, years, smoke)
    for year, hourly in tasks:
        ok, reason = season_is_complete(cfg, year, hourly=hourly)
        label = f"{year} 6-hourly" if hourly else f"{year}"
        if ok:
            log.info("season %s: complete", label)
        else:
            log.error("season %s: NOT usable -- %s", label, reason)
            missing.append(f"{label}: {reason}")

    if missing:
        raise DownloadError(
            f"--skip-download: {len(missing)} of {len(tasks)} requested season(s) are missing or do "
            f"not match the current request:\n  " + "\n  ".join(missing)
        )
    log.info("--skip-download: all %d requested season(s) are complete", len(tasks))


# -- the R1 equivalence gate ---------------------------------------------------------------------


def check_r1_equivalence(cfg: Config, year: int, out_json: Path, log: logging.Logger) -> dict:
    """Hard gate (§4.1, deliverable M2, risk R4): the derived daily mean *is* the mean of the
    configured hours.

    Both operands are read through the one normalizing reader of §4.2, so longitude convention,
    latitude order, units and scalar coordinates are identical by construction before anything is
    subtracted. They are then aligned with `join="exact"`, which raises rather than intersecting:
    xarray defaults `arithmetic_join` to `"inner"`, so a bare `a - b` over mismatched coordinates
    would compare only the overlap and pass a gate it never tested.
    """
    from .profile import open_normalized      # imported here: only this gate crosses to profile.py

    daily_path = season_paths(cfg, year)["nc"]
    hourly_path = season_paths(cfg, year, hourly=True)["nc"]
    for path in (daily_path, hourly_path):
        if not path.exists():
            raise DownloadError(f"R1 gate: {path} is missing; both operands must be downloaded "
                                "before the equivalence check can run")

    derived = open_normalized(daily_path, cfg)
    hourly = open_normalized(hourly_path, cfg, hourly=True)

    # Every day must contribute exactly the configured hours -- a short day would make the local
    # mean a different statistic and quietly weaken the gate.
    days = hourly["time"].dt.floor("D")
    unique_days, counts = np.unique(days.values, return_counts=True)
    expected_samples = len(cfg.hourly_times)
    if not np.all(counts == expected_samples):
        offender = unique_days[counts != expected_samples][0]
        seen = int(counts[counts != expected_samples][0])
        raise DownloadError(
            f"R1 gate: {hourly_path} does not carry {expected_samples} samples on every day "
            f"({np.datetime_as_string(offender, unit='D')} has {seen}); the local daily mean would "
            "not be the statistic the derived product computes"
        )

    local = hourly.groupby(days.rename("day")).mean("time").rename({"day": "time"}).sortby("time")
    local = local.assign_coords(time=local["time"].dt.floor("D"))
    derived = derived.assign_coords(time=derived["time"].dt.floor("D")).sortby("time")

    try:
        aligned_local, aligned_derived = xr.align(local, derived, join="exact")
    except ValueError as exc:                     # xarray's AlignmentError subclasses ValueError
        raise DownloadError(
            f"R1 gate: the two operands do not carry identical coordinates, so any comparison would "
            f"have silently tested only their overlap -- local {dict(local.sizes)} vs derived "
            f"{dict(derived.sizes)}: {exc}"
        ) from exc
    difference = np.abs(aligned_local.values.astype("float64")
                        - aligned_derived.values.astype("float64"))
    max_abs_diff = float(difference.max())
    n_compared = int(difference.size)
    n_expected = cfg.days_per_season * cfg.sector.n_lat * cfg.sector.n_lon

    count_ok = n_compared == n_expected
    tolerance_ok = max_abs_diff < cfg.r1_tolerance
    record = {
        "year": year,
        "passed": bool(count_ok and tolerance_ok),
        "max_abs_diff": max_abs_diff,
        "n_compared": n_compared,
        "n_expected": n_expected,
        "tolerance": cfg.r1_tolerance,
        "hourly_times": list(cfg.hourly_times),
        "derived_daily_path": str(daily_path),
        "hourly_path": str(hourly_path),
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(record, indent=2) + "\n")

    log.info("R1 equivalence %d: max |local(%s) - derived| = %.3e m s-1 over %d compared points "
             "(tolerance %.1e, expected %d points) -> %s",
             year, ",".join(cfg.hourly_times), max_abs_diff, n_compared, cfg.r1_tolerance,
             n_expected, "PASS" if record["passed"] else "FAIL")
    log.info("R1 record written to %s", out_json)

    if not count_ok:
        raise DownloadError(
            f"R1 gate FAILED: compared {n_compared} points, expected "
            f"{n_expected} = {cfg.days_per_season} days x {cfg.sector.n_lat} latitudes x "
            f"{cfg.sector.n_lon} longitudes"
        )
    if not tolerance_ok:
        raise DownloadError(
            f"R1 gate FAILED: max |mean of {','.join(cfg.hourly_times)} - derived daily mean| = "
            f"{max_abs_diff:.3e} m s-1 over {n_compared} points, tolerance {cfg.r1_tolerance:.1e}. "
            "The derived product is not the contract's daily mean; the campaign does not start."
        )
    return record
