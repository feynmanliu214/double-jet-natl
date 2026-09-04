"""Every §A8 row, asserted to *fire* on a synthetic archive built to break exactly it.

Two rules shape this file, and they are the mirror image of `test_profile.py`'s:

* **The grid here is deliberately NOT the production one.** `test_profile.py` keeps 221 x 361
  because the shape assertions are what it is testing. This file tests a *reader*, so the fixture
  config is coarser (5 deg) and its sector smaller (8 x 5) than anything the contract mentions, and
  the synthetic archive is a reduced *global* grid (37 x 72 x 4 levels). A loader that hard-coded
  the archive's real 721 x 1440 x 37, or the sector's real 221 x 361, cannot pass a single test
  below. The one test that does use the production numbers reads the *real* archive, and skips when
  it is absent (addendum §A8).
* **The synthetic day mimics the real one's structure, not its size** (§A1.1): the wind variable is
  `U` **uppercase**, a second `utc_date(time)` variable shares the file, `level` is in **hPa** with
  250 present at an index that is neither first nor last, latitude runs **descending 90 -> -90**,
  longitude **0 -> 355 ascending** so the wrap is required and the meridian is straddled, time is
  24 hourly steps stored as hours since 1900-01-01. Each test overrides exactly one of those.

`make_cfg` repoints `paths.scratch_raw`, `data_dir` and `figs_dir` into `tmp_path` and `rda.root` at
a synthetic archive, so no test can read or write the real `$SCRATCH`, the real archive, or the
repository's `data/`. `rda.workers` is 1 and `$PBS_NCPUS` is unset by an autouse fixture, so no test
silently spawns eight processes; one test sets `$PBS_NCPUS` on purpose to pin the override.

The synthetic field is `30 exp(-((lat-40)/12)^2) + 4 cos(lon) + 0.5*hour + 0.02*level`. Every term
earns its place: the `hour` term makes an index-selected daily mean numerically different from a
timestamp-selected one (J1), the `level` term makes an index-selected level different from a
value-selected one (J6), and `cos(lon)` varies across the sector so a mis-wrapped longitude cut
lands on visibly wrong values (J4).
"""

from __future__ import annotations

import argparse
import calendar
import csv
import datetime as dt
import json
import logging
import os
import shutil
import sys
from pathlib import Path

import netCDF4
import numpy as np
import pytest
import xarray as xr
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:                    # `pytest tests/...` from anywhere
    sys.path.insert(0, str(REPO_ROOT))

from double_jet import cli, download, figure, profile, rda, source   # noqa: E402
from double_jet import classify as classify_mod                      # noqa: E402
from double_jet.config import Config, load_config                    # noqa: E402
from double_jet.download import DownloadError                        # noqa: E402

REAL_YAML = REPO_ROOT / "configs" / "double_jet.yaml"

# The real archive, for the one integration test. `skipif` when it is absent so the suite stays
# runnable off-machine (addendum §A8).
REAL_ARCHIVE = Path("/glade/campaign/collections/rda/data/d633000/e5.oper.an.pl")

# The real file template, kept verbatim so the "missing day" message names a realistic filename.
FILE_TEMPLATE = "e5.oper.an.pl.128_131_u.ll025uv.{ymd}00_{ymd}23.nc"

# --- the reduced *global* grid the synthetic archive is written on -----------------------------
GLOBAL_RESOLUTION = 5.0
GLOBAL_LAT = np.arange(90.0, -90.0 - 1e-9, -GLOBAL_RESOLUTION)      # 37, DESCENDING, as ERA5 is
GLOBAL_LON = np.arange(0.0, 360.0, GLOBAL_RESOLUTION)               # 72, 0..355 ASCENDING
# 250 sits at index 2 of 4: neither first nor last, so an index-selected level is a wrong answer.
ARCHIVE_LEVELS = (100.0, 200.0, 250.0, 500.0)
ARCHIVE_HOURS = tuple(range(24))

# The wave prompt's deliverable names, reproduced as literals (test_config.py's rule: deriving them
# from the code under test would assert nothing). Test 24 checks the evidence slot stays clear of
# them on *both* sources.
CONTRACT_NAMES = {
    Path("data/u250_natl_mjjas_1979-2025.nc"),
    Path("data/jet_states_mjjas_1979-2025.csv"),
    Path("data/jet_states_summary.txt"),
    Path("figs/double_jet_natl_panels.pdf"),
    Path("figs/double_jet_natl_panels.png"),
}


# ---------------------------------------------------------------------------------------------
# fixtures and builders
# ---------------------------------------------------------------------------------------------


def _logger() -> logging.Logger:
    log = logging.getLogger("test_rda")
    if not log.handlers:
        log.addHandler(logging.NullHandler())
    return log


@pytest.fixture(autouse=True)
def _no_pbs(monkeypatch):
    """`$PBS_NCPUS` wins over `cfg.rda.workers` (§A5.2 step 2); unset it so tests are deterministic.

    Without this a suite run *inside* a PBS job would size every pool from the job's shape.
    """
    monkeypatch.delenv("PBS_NCPUS", raising=False)


def season_days(cfg: Config, year: int) -> list[dt.date]:
    """The season's calendar days, enumerated from the calendar rather than from `rda._season_dates`.

    Deliberately independent of the module under test: a fixture that generated its days from the
    loader's own enumerator could not catch the loader enumerating the wrong ones.
    """
    return [dt.date(year, month, day)
            for month in sorted(cfg.season_months)
            for day in range(1, calendar.monthrange(year, month)[1] + 1)]


def archive_field(hours, levels, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """`(time, level, latitude, longitude)` -- see the module docstring for why each term is here."""
    jet = 30.0 * np.exp(-((lat - 40.0) / 12.0) ** 2)
    wave = 4.0 * np.cos(np.deg2rad(lon))
    base = jet[:, None] + wave[None, :]
    h = np.asarray(hours, dtype="float64")
    lv = np.asarray(levels, dtype="float64")
    field = (base[None, None, :, :]
             + 0.5 * h[:, None, None, None]
             + 0.02 * lv[None, :, None, None])
    return field.astype("float32")


def expected_daily_mean(cfg: Config, hours=(0, 6, 12, 18), level: float = 250.0) -> np.ndarray:
    """The daily mean the contract defines, computed independently of `rda.py`, on `cfg`'s sector.

    Ascending latitude and ascending [-180, 180) longitude -- the orientation J4/J5 require, which
    is *not* the orientation the archive is written in.
    """
    lat, lon = cfg.sector.latitudes(), cfg.sector.longitudes()
    jet = 30.0 * np.exp(-((lat - 40.0) / 12.0) ** 2)
    wave = 4.0 * np.cos(np.deg2rad(lon))          # cos is even and 360-periodic: cos(345) = cos(-15)
    base = jet[:, None] + wave[None, :]
    return base + 0.5 * float(np.mean(hours)) + 0.02 * level


def write_archive_day(root: Path, day: dt.date, *, hours=ARCHIVE_HOURS, levels=ARCHIVE_LEVELS,
                      lat: np.ndarray | None = None, lon: np.ndarray | None = None,
                      values: np.ndarray | None = None, wind_name: str = "U",
                      wind_units: str = "m s**-1", level_units: str = "hPa",
                      lat_units: str = "degrees_north", lon_units: str = "degrees_east",
                      utc_date: bool = True, template: str = FILE_TEMPLATE) -> Path:
    """One synthetic archive day, shaped as §A1.1 measured the real ones, with one thing broken.

    Defaults reproduce a *good* day. The layout under `root` is `<YYYYMM>/<template with ymd>`,
    which is `rda.MONTH_DIR_FORMAT` plus `cfg.rda.file_template`.
    """
    lat = GLOBAL_LAT if lat is None else np.asarray(lat, dtype=float)
    lon = GLOBAL_LON if lon is None else np.asarray(lon, dtype=float)
    levels = np.asarray(levels, dtype=float)
    if values is None:
        values = archive_field(hours, levels, lat, lon)
    times = np.array([np.datetime64(f"{day.isoformat()}T{int(h):02d}:00:00") for h in hours],
                     dtype="datetime64[ns]")

    wind_attrs = {} if wind_units is None else {"units": wind_units}
    ds = xr.Dataset(
        {wind_name: (("time", "level", "latitude", "longitude"), values, wind_attrs)},
        coords={
            "time": times,
            "level": ("level", levels, {"units": level_units}),
            "latitude": ("latitude", lat, {"units": lat_units}),
            "longitude": ("longitude", lon, {"units": lon_units}),
        },
    )
    if utc_date:
        # The second data variable the real files carry (§A1.1, risk DR5): `open_normalized` would
        # refuse a file holding both it and `U`, which is why the loader emits its own single `u`.
        ds["utc_date"] = ("time", np.array(
            [int(f"{day.strftime('%Y%m%d')}{int(h):02d}") for h in hours], dtype="int32"))

    path = Path(root) / day.strftime(rda.MONTH_DIR_FORMAT) / template.format(
        ymd=day.strftime("%Y%m%d"))
    path.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(path, encoding={
        wind_name: {"zlib": True, "complevel": 1, "_FillValue": 9.999e20},
        "time": {"units": "hours since 1900-01-01 00:00:00", "calendar": "gregorian",
                 "dtype": "int32"},
    })
    return path


def build_archive(root: Path, year: int = 2018, **day_kwargs) -> Path:
    """A whole season of synthetic archive days (28 for the February fixture season)."""
    for day in [dt.date(year, 2, d) for d in range(1, 29)]:
        write_archive_day(root, day, **day_kwargs)
    return root


@pytest.fixture(scope="session")
def archive(tmp_path_factory) -> Path:
    """The pristine synthetic archive: February 2018, 28 good days. **Never mutated by a test.**

    Session-scoped because it is read-only and building it 20 times would be waste; tests that need
    to move a file's mtime or delete a day take a `private_archive` copy instead.
    """
    return build_archive(tmp_path_factory.mktemp("rda") / "e5.oper.an.pl")


@pytest.fixture
def private_archive(tmp_path, archive) -> Path:
    """A per-test copy, for the tests that mutate the archive under a finished season."""
    dest = tmp_path / "archive"
    shutil.copytree(archive, dest)
    return dest


def make_cfg(tmp_path: Path, archive_root: Path, name: str = "cfg.yaml", **overrides) -> Config:
    """The reduced-grid test config: 5 deg resolution, a 8 x 5 sector straddling the meridian.

    Every scientific number here is a *test* number, unrelated to the frozen contract, and that is
    the point (see the module docstring). February is the season because it is the shortest month
    the calendar offers, and 2017-2019 are all non-leap so `days_per_season` (28, computed from
    2001) and the loader's own calendar enumeration agree for every year the tests use.
    """
    raw = {
        "dataset": "derived-era5-pressure-levels-daily-statistics",
        "hourly_dataset": "reanalysis-era5-pressure-levels",
        "variable": "u_component_of_wind",
        "pressure_level": 250,
        "season_months": [2],
        "year_first": 2017,
        "year_last": 2019,
        "smoke_year": 2018,
        "daily_statistic": "daily_mean",
        "time_zone": "utc+00:00",
        "frequency": "6_hourly",
        "hourly_times": ["00:00", "06:00", "12:00", "18:00"],
        "r1_tolerance": 1.0e-3,
        "sector": {"lat_min": 30.0, "lat_max": 50.0, "lon_min": -15.0, "lon_max": 20.0,
                   "resolution": GLOBAL_RESOLUTION},
        "detection": {"u_core_min": 15.0, "separation_min_deg": 10.0, "prominence_min": 5.0,
                      "smooth_window_deg": 10.0},
        "sanity": {"double_fraction_min": 0.05, "double_fraction_max": 0.90, "core_lat_min": 25.0,
                   "core_lat_max": 70.0, "core_lat_fraction_min": 0.95, "smoke_peak_min": 20.0,
                   "smoke_peak_max": 40.0},
        "paths": {"scratch_raw": str(tmp_path / "scratch"), "data_dir": str(tmp_path / "data"),
                  "figs_dir": str(tmp_path / "figs")},
        "max_in_flight": 3,
        "source": "rda_hourly",
        "rda": {"root": str(archive_root), "file_template": FILE_TEMPLATE,
                "dataset_id": "ds633.0-test", "workers": 1},
    }
    raw.update(overrides)
    path = tmp_path / name
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    return load_config(path)


def read_one_day(cfg: Config, path: Path, date: str = "2018-02-01"):
    """`rda._read_day`'s worker payload, called in-process so a failure is a plain exception."""
    return rda._read_day((cfg, Path(path), date))


# ---------------------------------------------------------------------------------------------
# 1-2. the four fields are selected BY TIMESTAMP, never by index (J1, risk DR4)
# ---------------------------------------------------------------------------------------------


def test_daily_mean_selects_the_four_hours_by_timestamp_not_by_index(tmp_path, archive):
    """§A8 row 1 (J1): the isel trap, on a file whose 24 hours are written in reverse order.

    `isel(time=[0, 6, 12, 18])` on this file selects hours 23/17/11/05, whose mean differs from the
    contract's 00/06/12/18 mean by 2.5 m/s. The test asserts both halves: that the loader lands on
    the timestamp answer, and that it does *not* land on the index answer.
    """
    cfg = make_cfg(tmp_path, archive)
    shuffled = tuple(range(23, -1, -1))
    path = write_archive_day(tmp_path / "shuffled", dt.date(2018, 2, 1), hours=shuffled)

    # the file really is out of order, and index selection really would pick different hours
    with xr.open_dataset(path) as raw:
        hours = raw["time"].dt.hour.values
        assert list(hours) == list(shuffled)
        assert [int(hours[i]) for i in (0, 6, 12, 18)] == [23, 17, 11, 5]

    date, mean, _ = read_one_day(cfg, path)
    assert date == "2018-02-01"
    assert mean.shape == (cfg.sector.n_lat, cfg.sector.n_lon)

    by_timestamp = expected_daily_mean(cfg, hours=(0, 6, 12, 18))
    by_index = expected_daily_mean(cfg, hours=(23, 17, 11, 5))
    assert np.abs(by_timestamp - by_index).max() == pytest.approx(2.5, abs=1e-9)
    np.testing.assert_allclose(mean, by_timestamp, atol=1e-4)
    assert np.abs(mean - by_index).max() > 2.0, "the loader selected the four fields by index"


def test_a_day_missing_an_analysis_hour_is_rejected_naming_the_date(tmp_path, archive):
    """§A8 row 2 (J1): 23 hours is a hard error, and so is 24 hours with one of ours missing.

    The second arm matters more than the first: a file that still carries 24 timestamps passes any
    count check, and only a per-hour match catches that 12:00 has been replaced by a duplicate.
    """
    cfg = make_cfg(tmp_path, archive)

    short = write_archive_day(tmp_path / "short", dt.date(2018, 2, 3),
                              hours=tuple(h for h in range(24) if h != 18))
    with pytest.raises(DownloadError) as exc:
        read_one_day(cfg, short, "2018-02-03")
    message = str(exc.value)
    assert "2018-02-03" in message, "the failure must name the date"
    assert "23 timestamps" in message and "24" in message

    # 24 timestamps, but 12:00 is gone and 13:00 appears twice -- a count check would accept it.
    hours = [h if h != 12 else 13 for h in range(24)]
    swapped = write_archive_day(tmp_path / "swapped", dt.date(2018, 2, 4), hours=tuple(hours))
    with pytest.raises(DownloadError) as exc:
        read_one_day(cfg, swapped, "2018-02-04")
    message = str(exc.value)
    assert "2018-02-04" in message
    assert "12:00" in message and "exactly" in message
    assert "0 timestamp(s) at 12:00" in message


# ---------------------------------------------------------------------------------------------
# 3. a missing archive day is loud (§A5.2 step 1)
# ---------------------------------------------------------------------------------------------


def test_a_day_absent_from_the_archive_is_rejected_naming_date_and_filename(tmp_path,
                                                                           private_archive):
    """§A8 row 3: never a silently short season -- and a day that vanishes *after* the season was
    built makes the cached season incomplete rather than quietly stale."""
    cfg = make_cfg(tmp_path, private_archive)
    log = _logger()
    rda.write_season(cfg, 2018, log)
    assert rda.season_is_complete(cfg, 2018) == (True, "")

    victim = rda._source_path(cfg, dt.date(2018, 2, 14))
    expected_name = FILE_TEMPLATE.format(ymd="20180214")
    assert victim.name == expected_name
    victim.unlink()

    with pytest.raises(DownloadError) as exc:
        rda.season_source_files(cfg, 2018)
    message = str(exc.value)
    assert "2018-02-14" in message, "the failure must name the date"
    assert expected_name in message, "the failure must name the expected filename"
    assert str(private_archive) in message

    ok, reason = rda.season_is_complete(cfg, 2018)
    assert ok is False
    assert "no longer supplies every source day" in reason and "2018-02-14" in reason


# ---------------------------------------------------------------------------------------------
# 4-5. the level, BY VALUE, with its units read from the file (J6, J7)
# ---------------------------------------------------------------------------------------------


def test_level_is_resolved_by_value_and_a_pa_tagged_level_is_rejected(tmp_path, archive):
    """§A8 row 4 (J6, J7): 250 hPa sits at index 2 of 4, so an index-selected level is wrong by
    3 m/s in this field; and a Pa-tagged coordinate fails as a *unit* error on the day that carries
    it, not 47 seasons later."""
    cfg = make_cfg(tmp_path, archive)
    good = write_archive_day(tmp_path / "levels", dt.date(2018, 2, 1))
    _, mean, units = read_one_day(cfg, good)

    np.testing.assert_allclose(mean, expected_daily_mean(cfg, level=250.0), atol=1e-4)
    assert units["level"] == "hPa"
    for wrong in (100.0, 200.0, 500.0):
        assert np.abs(mean - expected_daily_mean(cfg, level=wrong)).max() > 0.5, (
            f"the loader appears to have taken level {wrong}, not the configured 250")

    # A Pa-tagged coordinate would make "== 250" wrong by a factor of 100.
    pa = write_archive_day(tmp_path / "level_pa", dt.date(2018, 2, 1), level_units="Pa")
    with pytest.raises(DownloadError) as exc:
        read_one_day(cfg, pa)
    message = str(exc.value)
    assert "units" in message and "'Pa'" in message and "hPa" in message
    assert "2018-02-01" in message


def test_a_level_set_without_250_is_rejected(tmp_path, archive):
    """§A8 row 5 (J6): four levels, none of them the configured one -- resolved by value, so there
    is no index to fall back on."""
    cfg = make_cfg(tmp_path, archive)
    path = write_archive_day(tmp_path / "no_250", dt.date(2018, 2, 1),
                             levels=(100.0, 200.0, 300.0, 500.0))
    with pytest.raises(DownloadError) as exc:
        read_one_day(cfg, path)
    message = str(exc.value)
    assert "0 value(s) equal to 250" in message
    assert "4 level(s)" in message and "by value, never by index" in message
    assert "2018-02-01" in message


# ---------------------------------------------------------------------------------------------
# 6-7. the sector cut: assert-then-adopt, wrapped and ascending (J4, J5)
# ---------------------------------------------------------------------------------------------


def test_longitude_wrap_lands_on_the_configured_sector_across_the_meridian(tmp_path, archive):
    """§A8 row 6 (J4): the archive is 0..355; the sector is -15..20 and straddles the meridian, so
    the written longitudes are only right if the wrap happened *and* the two halves were rejoined
    in ascending order."""
    cfg = make_cfg(tmp_path, archive)
    nc = rda.write_season(cfg, 2018, _logger())

    # the source really is 0..360 and really does need a wrap to yield this sector
    with xr.open_dataset(rda._source_path(cfg, dt.date(2018, 2, 1))) as raw:
        src_lon = raw["longitude"].values
        assert src_lon.min() == 0.0 and src_lon.max() == 355.0
        assert (np.diff(src_lon) > 0).all()

    with xr.open_dataset(nc) as ds:
        lon = ds["longitude"].values
        assert lon.size == cfg.sector.n_lon == 8
        np.testing.assert_array_equal(lon, cfg.sector.longitudes())    # adopted, not merely close
        assert lon.min() < 0.0 < lon.max(), "the sector must straddle the meridian"
        assert (np.diff(lon) > 0).all()
        assert ds["longitude"].attrs["units"] == "degrees_east"

        # the columns are the wrapped ones, not the file's leading 0..35: -15 must carry the
        # value the source stored at 345.
        row = ds["u"].isel(time=0).sel(latitude=40.0).values
        np.testing.assert_allclose(row, expected_daily_mean(cfg)[cfg.sector.latitudes() == 40.0][0],
                                   atol=1e-4)


def test_latitude_is_written_ascending_and_equal_to_the_configured_grid(tmp_path, archive):
    """§A8 row 7 (J4, J5): the archive is descending 90 -> -90; the season is written ascending
    20 -> 75 (here 30 -> 50) so the raw season and the intermediate agree by inspection."""
    cfg = make_cfg(tmp_path, archive)
    nc = rda.write_season(cfg, 2018, _logger())

    with xr.open_dataset(rda._source_path(cfg, dt.date(2018, 2, 1))) as raw:
        assert (np.diff(raw["latitude"].values) < 0).all(), "the source must be descending"

    with xr.open_dataset(nc) as ds:
        lat = ds["latitude"].values
        assert lat.size == cfg.sector.n_lat == 5
        assert (np.diff(lat) > 0).all(), "J5: latitude is written ASCENDING"
        np.testing.assert_array_equal(lat, cfg.sector.latitudes())     # adopted, not merely close
        assert ds["latitude"].attrs["units"] == "degrees_north"
        # the rows really were re-ordered, not just relabelled: the jet peak sits at 40 N.
        column = ds["u"].isel(time=0).sel(longitude=0.0).values
        assert lat[int(np.argmax(column))] == 40.0


# ---------------------------------------------------------------------------------------------
# 8. units are COPIED FROM THE SOURCE and asserted, never synthesized (J7)
# ---------------------------------------------------------------------------------------------


def test_units_are_copied_from_the_source_and_kelvin_or_pa_is_rejected(tmp_path, archive):
    """§A8 row 8 (J7): a season built from a source that says `m/s` is written saying `m/s`.

    `m/s` and `m s**-1` are both accepted by the seam, which is exactly what makes this test
    possible: a loader that synthesized the canonical spelling would still pass `open_normalized`
    and would still be wrong. A source in `K` (wind) or `Pa` (level) is refused outright.
    """
    ms_archive = build_archive(tmp_path / "ms_archive", wind_units="m/s")
    cfg = make_cfg(tmp_path, ms_archive)
    nc = rda.write_season(cfg, 2018, _logger())

    with xr.open_dataset(nc) as ds:
        assert ds["u"].attrs["units"] == "m/s", "the unit string must be copied, not synthesized"
        assert ds["level"].attrs["units"] == "hPa"
        assert ds["latitude"].attrs["units"] == "degrees_north"
        assert ds["longitude"].attrs["units"] == "degrees_east"
    # ... and what was copied is still something the seam accepts
    assert profile.open_normalized(nc, cfg).shape == (28, 5, 8)

    kelvin = write_archive_day(tmp_path / "kelvin", dt.date(2018, 2, 1), wind_units="K")
    with pytest.raises(DownloadError) as exc:
        read_one_day(cfg, kelvin)
    assert "'K'" in str(exc.value) and "m s**-1" in str(exc.value)

    unstated = write_archive_day(tmp_path / "unstated", dt.date(2018, 2, 1), wind_units=None)
    with pytest.raises(DownloadError) as exc:
        read_one_day(cfg, unstated)
    assert "units are read, not assumed" in str(exc.value)


# ---------------------------------------------------------------------------------------------
# 9. a masked cell must stop the run, not average into a mean (§A5.2 step 2)
# ---------------------------------------------------------------------------------------------


def test_a_non_finite_cell_inside_the_sector_is_rejected_naming_the_date(tmp_path, archive):
    """§A8 row 9: the archive carries `_FillValue = 9.999e+20`, which xarray masks to NaN.

    Three arms: a NaN inside the sector fails, a `+inf` inside the sector fails too (`np.isfinite`,
    not `~np.isnan`), and a NaN *outside* the sector is none of our business -- proving the check is
    scoped to the cut rather than to the global field.
    """
    cfg = make_cfg(tmp_path, archive)
    lat_i, lon_i = 10, 1                     # 40 N, 5 E -- inside the sector
    level_i = ARCHIVE_LEVELS.index(250.0)

    # the directory names deliberately carry neither "nan" nor "inf": the needle must be found
    # in the loader's message, not in the path it happens to echo back.
    for case, bad_value, needle in ((0, np.nan, "nan"), (1, np.inf, "inf")):
        values = archive_field(ARCHIVE_HOURS, ARCHIVE_LEVELS, GLOBAL_LAT, GLOBAL_LON)
        values[12, level_i, lat_i, lon_i] = bad_value
        path = write_archive_day(tmp_path / f"masked{case}", dt.date(2018, 2, 7), values=values)
        with pytest.raises(DownloadError) as exc:
            read_one_day(cfg, path, "2018-02-07")
        message = str(exc.value)
        assert "2018-02-07" in message, "the failure must name the date"
        assert "non-finite" in message and needle in message.lower()
        assert "12:00" in message and "latitude 40," in message

    outside = archive_field(ARCHIVE_HOURS, ARCHIVE_LEVELS, GLOBAL_LAT, GLOBAL_LON)
    outside[12, level_i, 26, 36] = np.nan        # 40 S, 180 E -- far outside the sector
    path = write_archive_day(tmp_path / "outside", dt.date(2018, 2, 8), values=outside)
    _, mean, _ = read_one_day(cfg, path, "2018-02-08")
    assert np.isfinite(mean).all()


# ---------------------------------------------------------------------------------------------
# 10. THE SEAM CONTRACT -- the one test the rest of the loader exists to satisfy
# ---------------------------------------------------------------------------------------------


def test_the_written_season_survives_open_normalized_unmodified(tmp_path, archive):
    """§A8 row 10: the season the loader writes is handed to `profile.open_normalized` with **no
    fixing up of any kind**, and comes back as the pipeline's canonical `u(time, latitude,
    longitude)`.

    This is the whole contract of §A5/HANDOFF §5.1 in one assertion. It also pins the two things
    `_check_shape` cannot see and that a raw archive file would fail on (risk DR5): exactly one
    data variable, named `u`, and a *scalar* `level` the seam drops.
    """
    cfg = make_cfg(tmp_path, archive)
    nc = rda.write_season(cfg, 2018, _logger())
    assert nc == Path(download.season_paths(cfg, 2018)["nc"])

    with xr.open_dataset(nc) as ds:
        assert list(ds.data_vars) == ["u"], "DR5: one data variable, named u"
        assert "level" in ds.variables and ds["level"].shape == ()   # J6: scalar, not a dimension
        assert float(ds["level"]) == 250.0
        assert ds["u"].encoding["dtype"] == np.dtype("float32")      # J3
        assert ds["u"].encoding["zlib"] is True and ds["u"].encoding["complevel"] == 4
        assert ds["u"].encoding.get("_FillValue") is None

    u = profile.open_normalized(nc, cfg)                             # <- unmodified, no arguments
    assert u.name == "u"
    assert u.dims == ("time", "latitude", "longitude")
    assert u.shape == (cfg.days_per_season, cfg.sector.n_lat, cfg.sector.n_lon) == (28, 5, 8)
    assert set(u.coords) == {"time", "latitude", "longitude"}        # level dropped by the seam
    np.testing.assert_allclose(u["latitude"].values, cfg.sector.latitudes(), atol=1e-6)
    np.testing.assert_allclose(u["longitude"].values, cfg.sector.longitudes(), atol=1e-6)

    times = u["time"].values
    assert times.dtype == np.dtype("datetime64[ns]")
    assert (np.diff(times) > np.timedelta64(0, "ns")).all()
    assert [str(t)[:10] for t in times] == [d.isoformat() for d in season_days(cfg, 2018)]

    # and the values are the contract's daily mean, on every one of the 28 days
    expected = expected_daily_mean(cfg)
    for i in range(cfg.days_per_season):
        np.testing.assert_allclose(u.values[i], expected, atol=1e-4)

    # step 9 works on it too, which is what stage 2 actually calls
    assert profile.season_profile(nc, cfg).shape == (28, 5)


# ---------------------------------------------------------------------------------------------
# 11-16. the sidecar, and the idempotence properties of §A6.3
# ---------------------------------------------------------------------------------------------


def test_sidecar_round_trip_marks_the_season_complete(tmp_path, archive):
    """§A8 row 11 (§A6.1): the three-part contract -- shape, sidecar present, sidecar equal to the
    request that would be issued now -- and the sidecar's own payload."""
    cfg = make_cfg(tmp_path, archive)
    rda.write_season(cfg, 2018, _logger())
    paths = download.season_paths(cfg, 2018)
    sidecar = Path(paths["request"])

    assert rda.season_is_complete(cfg, 2018) == (True, "")
    assert source.season_is_complete(cfg, 2018) == (True, "")

    stored = json.loads(sidecar.read_text())
    assert stored == rda.build_rda_request(cfg, 2018)
    assert stored["source"] == "rda_hourly"
    assert stored["archive_root"] == str(archive)
    assert stored["file_template"] == FILE_TEMPLATE
    assert stored["pressure_level"] == 250 and stored["level_units"] == "hPa"
    assert stored["year"] == "2018" and stored["month"] == ["02"]
    assert stored["hours"] == list(cfg.hourly_times)
    assert stored["daily_statistic"] == "daily_mean"
    assert stored["area"] == [50.0, -15.0, 30.0, 20.0]       # [N, W, S, E], positional
    assert stored["resolution"] == 5.0
    assert stored["n_source_files"] == 28 == len(stored["source_files"])
    assert sorted(stored["source_files"][0]) == ["bytes", "mtime_ns", "name"]

    # remove the sidecar and the same bytes stop being a valid skip
    sidecar.unlink()
    ok, reason = rda.season_is_complete(cfg, 2018)
    assert ok is False and str(sidecar) in reason and "missing" in reason


def test_a_detection_threshold_change_leaves_the_season_complete(tmp_path, archive):
    """§A8 row 12 (§A6.3): the free re-run. A threshold is not in the sidecar and not in
    `profile_sha256`, so changing one re-runs classification without re-reading a single archive
    file. This is the property `test_config.py` pins on the CDS path, held across the new source."""
    cfg = make_cfg(tmp_path, archive)
    rda.write_season(cfg, 2018, _logger())
    assert rda.season_is_complete(cfg, 2018) == (True, "")

    retuned = make_cfg(tmp_path, archive, "cfg_threshold.yaml",
                       detection={"u_core_min": 16.0, "separation_min_deg": 10.0,
                                  "prominence_min": 5.0, "smooth_window_deg": 10.0})
    assert retuned.detection.u_core_min == 16.0
    assert retuned.profile_sha256 == cfg.profile_sha256
    assert retuned.config_sha256 != cfg.config_sha256
    assert rda.season_is_complete(retuned, 2018) == (True, ""), (
        "a threshold-only change must not invalidate the raw cache")


def test_a_sector_change_refuses_the_cache(tmp_path, archive):
    """§A8 row 13 (§A6.3): both halves of the refusal.

    A sector *shift* keeps the shape identical, so `_check_shape` is happy and only the sidecar's
    `area` can catch it -- that is the arm that proves the subset spec is doing work. A sector
    *extension* is caught earlier, by the shape check.
    """
    cfg = make_cfg(tmp_path, archive)
    rda.write_season(cfg, 2018, _logger())

    shifted = make_cfg(tmp_path, archive, "cfg_shift.yaml",
                       sector={"lat_min": 30.0, "lat_max": 50.0, "lon_min": -10.0,
                               "lon_max": 25.0, "resolution": GLOBAL_RESOLUTION})
    assert (shifted.sector.n_lat, shifted.sector.n_lon) == (cfg.sector.n_lat, cfg.sector.n_lon)
    ok, reason = rda.season_is_complete(shifted, 2018)
    assert ok is False
    assert "area" in reason and "does not match the request that would be issued now" in reason

    extended = make_cfg(tmp_path, archive, "cfg_extend.yaml",
                        sector={"lat_min": 30.0, "lat_max": 55.0, "lon_min": -15.0,
                                "lon_max": 20.0, "resolution": GLOBAL_RESOLUTION})
    ok, reason = rda.season_is_complete(extended, 2018)
    assert ok is False
    assert "latitude" in reason and "5 points, expected 6" in reason


def test_a_source_change_refuses_the_cache(tmp_path, archive):
    """§A8 row 14 (§A6.3, O1): a CDS-built and an RDA-built season occupy the same path on purpose,
    and the sidecar's `source` key makes them refuse each other -- in both directions."""
    cfg = make_cfg(tmp_path, archive)
    rda.write_season(cfg, 2018, _logger())
    sidecar = Path(download.season_paths(cfg, 2018)["request"])
    rda_sidecar = sidecar.read_text()

    cds = make_cfg(tmp_path, archive, "cfg_cds.yaml", source="cds_derived")
    ok, reason = source.season_is_complete(cds, 2018)          # CDS dispatch, RDA sidecar on disk
    assert ok is False
    assert "source" in reason and "rda_hourly" in reason

    sidecar.write_text(json.dumps(download.build_request(cds, 2018)))
    ok, reason = source.season_is_complete(cfg, 2018)          # RDA dispatch, CDS sidecar on disk
    assert ok is False
    assert "source" in reason and "archive_root" in reason

    sidecar.write_text(rda_sidecar)                            # ... and the RDA one still fits
    assert rda.season_is_complete(cfg, 2018) == (True, "")


def test_a_changed_archive_mtime_refuses_the_cache_naming_the_file(tmp_path, private_archive):
    """§A8 row 15 (§A6.2): the "archive moved under you" detector, and it names the offending file.

    `_canonical_request` alone would stringify 28 (in the campaign, 153) inventory dicts and
    truncate the difference to 60 characters; the entry-by-entry comparison reports the filename and
    both `(bytes, mtime_ns)` pairs instead.
    """
    cfg = make_cfg(tmp_path, private_archive)
    rda.write_season(cfg, 2018, _logger())
    assert rda.season_is_complete(cfg, 2018) == (True, "")

    victim = rda._source_path(cfg, dt.date(2018, 2, 14))
    stat = victim.stat()
    os.utime(victim, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    ok, reason = rda.season_is_complete(cfg, 2018)
    assert ok is False
    assert victim.name in reason, "the failure must name the file"
    assert "mtime_ns" in reason and str(stat.st_mtime_ns) in reason
    assert "changed since the season was built" in reason

    os.utime(victim, ns=(stat.st_atime_ns, stat.st_mtime_ns))     # put it back; bytes now differ
    assert rda.season_is_complete(cfg, 2018) == (True, "")
    with open(victim, "ab") as handle:
        handle.write(b"\0")
    os.utime(victim, ns=(stat.st_atime_ns, stat.st_mtime_ns))     # size alone must be enough
    ok, reason = rda.season_is_complete(cfg, 2018)
    assert ok is False and victim.name in reason and "bytes" in reason


def test_an_interrupted_write_leaves_a_part_and_no_complete_looking_season(tmp_path, archive):
    """§A8 row 16 (§A6.3): a job killed mid-write leaves a `.part` orphan and nothing else.

    The Stampede3 run was SIGKILLed mid-flight and left zero orphans that looked complete, because
    every byte lands in `<name>.part` and only `os.replace` publishes it. A SIGKILL runs no cleanup
    handler, so the `.part` really is left behind -- what must not happen is that anything treats it
    as a season.
    """
    cfg = make_cfg(tmp_path, archive)
    paths = download.season_paths(cfg, 2018)
    nc_path = Path(paths["nc"])
    part = nc_path.with_name(nc_path.name + rda._PART_SUFFIX)

    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(b"CDF\x01truncated half-written season")
    assert not nc_path.exists() and not Path(paths["request"]).exists()

    ok, reason = rda.season_is_complete(cfg, 2018)
    assert ok is False and str(nc_path) in reason and "missing" in reason
    with pytest.raises(DownloadError):
        rda.validate_local(cfg, [2018], smoke=True, log=_logger())

    # the next run rebuilds over the orphan and publishes atomically
    rda.ensure_local(cfg, [2018], smoke=True, log=_logger())
    assert rda.season_is_complete(cfg, 2018) == (True, "")
    assert not part.exists(), "os.replace must consume the .part, never leave it beside the season"
    assert profile.open_normalized(nc_path, cfg).shape == (28, 5, 8)


# ---------------------------------------------------------------------------------------------
# 17, 20. the two stage entry points: one writes, one never does (§A7.1, risk DR14)
# ---------------------------------------------------------------------------------------------


def test_validate_local_reports_every_missing_season_together(tmp_path, archive):
    """§A8 row 17: `--skip-download` must report *every* unusable season, not stop at the first --
    the behaviour `download.ensure_downloaded` has and that a resubmission depends on."""
    cfg = make_cfg(tmp_path, archive)
    rda.write_season(cfg, 2018, _logger())

    with pytest.raises(DownloadError) as exc:
        rda.validate_local(cfg, [2017, 2018, 2019], smoke=False, log=_logger())
    message = str(exc.value)
    assert "2 of 3 requested season(s)" in message
    assert "2017" in message and "2019" in message, "every offender, together"
    assert "u250_natl_mjjas_2017.nc" in message and "u250_natl_mjjas_2019.nc" in message
    assert message.count("is missing") == 2

    # the complete one is not reported as a failure, and validating it alone passes
    rda.validate_local(cfg, [2018], smoke=False, log=_logger())


def test_validate_local_never_writes(tmp_path, archive):
    """§A8 row 20 (risk DR14): pointed at an empty cache, `--skip-download` raises and creates
    nothing -- not the season, not the sidecar, not even the raw-cache directory.

    A `mkdir` here would make the flag a materializer of the very tree it promises only to read.
    `ensure_local` on the same config is the control: it *does* create the tree.
    """
    cfg = make_cfg(tmp_path, archive)
    raw_cache = cfg.paths.scratch_raw
    assert not raw_cache.exists()
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))

    with pytest.raises(DownloadError) as exc:
        rda.validate_local(cfg, [2018], smoke=True, log=_logger())
    assert "--skip-download" in str(exc.value)

    assert not raw_cache.exists(), "validate_local created the raw cache directory"
    assert sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*")) == before

    rda.ensure_local(cfg, [2018], smoke=True, log=_logger())      # the control: this one writes
    assert raw_cache.is_dir() and rda.season_is_complete(cfg, 2018) == (True, "")


# ---------------------------------------------------------------------------------------------
# 18-19. provenance: the hash and the intermediate's attributes (O1, §A4.3, §A7.2)
# ---------------------------------------------------------------------------------------------


def test_profile_sha256_separates_cds_from_rda_and_two_rda_roots(tmp_path, archive):
    """§A8 row 18 (O1, risk DR6): a CDS-built and an RDA-built intermediate must never be silently
    interchangeable, and neither must two RDA builds that read different archive roots."""
    rda_cfg = make_cfg(tmp_path, archive)
    cds_cfg = make_cfg(tmp_path, archive, "cfg_cds.yaml", source="cds_derived")
    other_root = make_cfg(tmp_path, archive, "cfg_other_root.yaml",
                          rda={"root": str(tmp_path / "elsewhere"),
                               "file_template": FILE_TEMPLATE,
                               "dataset_id": "ds633.0-test", "workers": 1})
    other_template = make_cfg(tmp_path, archive, "cfg_other_template.yaml",
                              rda={"root": str(archive),
                                   "file_template": "e5.oper.an.pl.128_131_u.{ymd}.nc",
                                   "dataset_id": "ds633.0-test", "workers": 1})

    hashes = {c.profile_sha256 for c in (rda_cfg, cds_cfg, other_root, other_template)}
    assert len(hashes) == 4, "each of these is a different provenance"

    fields = rda_cfg.profile_fields()
    assert fields["source"] == "rda_hourly"
    assert fields["rda_root"] == str(archive)
    assert fields["hourly_times"] == list(rda_cfg.hourly_times)      # risk DR15
    assert "rda_root" not in cds_cfg.profile_fields()
    assert "u_core_min" not in fields                                # thresholds stay excluded

    # a change to the hour set redefines the statistic on this path, so it must move the hash
    other_hours = make_cfg(tmp_path, archive, "cfg_hours.yaml",
                           hourly_times=["00:00", "12:00"])
    assert other_hours.profile_sha256 != rda_cfg.profile_sha256

    assert rda_cfg.active_dataset == "ds633.0-test"
    assert cds_cfg.active_dataset == cds_cfg.dataset


def test_build_intermediate_records_the_rda_request_template_and_dataset(tmp_path, archive):
    """§A8 row 19 (§A7.2): provenance that names a dataset the bytes did not come from is worse
    than none. The intermediate must carry the RDA request template and `ds633.0`, not a CDS
    request that was never issued."""
    cfg = make_cfg(tmp_path, archive)
    rda.write_season(cfg, 2018, _logger())
    out_path = tmp_path / "intermediate.nc"
    profile.build_intermediate(cfg, [2018], out_path, _logger())

    ds = profile.open_intermediate(out_path)
    assert ds["U"].dims == ("time", "latitude")
    assert ds["U"].shape == (28, 5)
    assert ds.attrs["source_dataset"] == cfg.active_dataset == "ds633.0-test"
    assert ds.attrs["profile_sha256"] == cfg.profile_sha256

    template = json.loads(ds.attrs["request_template"])
    assert template == rda.build_rda_request(cfg, 2018)          # O6: rebuilt from config
    assert template["source"] == "rda_hourly"
    assert template["archive_root"] == str(archive)
    assert template["file_template"] == FILE_TEMPLATE
    assert template["n_source_files"] == 28
    assert template["level_units"] == "hPa"
    assert "product_type" not in template, "this is not a CDS request"

    fields = json.loads(ds.attrs["profile_fields"])
    assert fields["source"] == "rda_hourly" and fields["rda_root"] == str(archive)


# ---------------------------------------------------------------------------------------------
# 21. the seam check runs on the .part, BEFORE publication (§A5.2 step 5, risk DR13)
# ---------------------------------------------------------------------------------------------


def test_a_season_failing_the_seam_is_never_published(tmp_path, archive, monkeypatch, caplog):
    """§A8 row 21: the failure `_check_shape` cannot see.

    `download._check_shape` -- all `season_is_complete` can apply to the bytes -- validates
    dimension sizes only. A wrong unit string leaves the dimensions perfect, so a season carrying
    one would sit on disk looking **complete** and the next run would skip it forever. The writer is
    monkeypatched to emit exactly that defect (a `.part` whose `u` says `K`) so the *ordering* of
    steps 5 and 6 is what is under test: the seam check must run on the `.part` and the season must
    never be published.
    """
    cfg = make_cfg(tmp_path, archive)
    paths = download.season_paths(cfg, 2018)
    nc_path, sidecar = Path(paths["nc"]), Path(paths["request"])
    part = nc_path.with_name(nc_path.name + rda._PART_SUFFIX)

    real_write_part = rda._write_part

    def write_a_bad_part(cfg_, part_path, dates, data, units, year):
        real_write_part(cfg_, part_path, dates, data, units, year)
        with netCDF4.Dataset(part_path, "a") as handle:
            handle["u"].setncattr("units", "K")

    monkeypatch.setattr(rda, "_write_part", write_a_bad_part)
    with caplog.at_level(logging.INFO):
        with pytest.raises(profile.ProfileError) as exc:
            rda.write_season(cfg, 2018, _logger())
    assert "'K'" in str(exc.value)
    assert any("will NOT be published" in r.getMessage() for r in caplog.records)

    # the defect that `_check_shape` alone would have missed
    assert not nc_path.exists(), "a season that fails the seam must never be published"
    assert not sidecar.exists(), "the sidecar must never describe bytes that were rejected"
    assert not part.exists(), "the failed .part must not be left behind by a handled failure"
    ok, reason = rda.season_is_complete(cfg, 2018)
    assert ok is False and "missing" in reason

    # and the next run rebuilds it, rather than skipping a season that "looks complete"
    monkeypatch.setattr(rda, "_write_part", real_write_part)
    rda.ensure_local(cfg, [2018], smoke=True, log=_logger())
    assert rda.season_is_complete(cfg, 2018) == (True, "")
    assert profile.open_normalized(nc_path, cfg).attrs["units"] == "m s**-1"


# ---------------------------------------------------------------------------------------------
# 22-23. the 2018 regression, the gate between the loader and the campaign (§A9)
# ---------------------------------------------------------------------------------------------


STATES_FIELDS = ("date", "state", "lat_1", "u_1", "lat_2", "u_2", "interjet_min")


def write_states_csv(path: Path, cfg: Config, *, flip_date: str | None = None) -> Path:
    """A `smoke_<year>_jet_states.csv` in `classify.py`'s column shape, one row per season day."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(STATES_FIELDS))
        writer.writeheader()
        for i, day in enumerate(season_days(cfg, cfg.smoke_year)):
            date = day.isoformat()
            double = i % 3 != 0
            state = "double" if double else "single"
            if date == flip_date:
                state = "single" if double else "double"
            writer.writerow({
                "date": date, "state": state,
                "lat_1": f"{30.0 + 0.25 * i:.2f}", "u_1": f"{28.0 + 0.01 * i:.6f}",
                "lat_2": f"{55.0 + 0.25 * i:.2f}" if double else "",
                "u_2": f"{26.0 + 0.01 * i:.6f}" if double else "",
                "interjet_min": f"{5.0 + 0.01 * i:.6f}" if double else "",
            })
    return path


SUMMARY_TEXT = (
    "=" * 78 + "\n"
    "double-jet classification -- sanity block (plan §4.4)\n"
    + "=" * 78 + "\n"
    "days classified : 28\n"
    "  double        :     18  ( 64.3 %)\n"
    "  single        :     10  ( 35.7 %)\n"
    "\n"
    "[GATE]     double-jet fraction 0.6429 against band 0.0500-0.9000 -> PASS\n"
    + "=" * 78 + "\n"
)


def write_profile_nc(path: Path, cfg: Config, *, offset: float = 0.0,
                     times: np.ndarray | None = None) -> Path:
    """A `U(time, latitude)` intermediate in `profile.open_intermediate`'s shape."""
    if times is None:
        times = np.array([np.datetime64(d.isoformat())
                          for d in season_days(cfg, cfg.smoke_year)], dtype="datetime64[ns]")
    lat = cfg.sector.latitudes()
    base = 20.0 + 10.0 * np.exp(-((lat - 40.0) / 8.0) ** 2)
    drift = np.linspace(0.0, 1.0, times.size)[:, None]
    values = (base[None, :] + drift + offset).astype("float32")
    ds = xr.Dataset({"U": (("time", "latitude"), values)},
                    coords={"time": times, "latitude": lat})
    path.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(path, encoding={"U": {"zlib": True, "complevel": 4, "dtype": "float32"}})
    return path


def regression_operands(tmp_path: Path, cfg: Config, *, flip_date: str | None = None,
                        summary_line: int | None = None, profile_offset: float = 0.0,
                        current_times: np.ndarray | None = None):
    """A baseline directory and a matching set of "current" run outputs, differing where asked.

    Building them synthetically rather than from `results/smoke_2018/` keeps the test self-contained
    and fast -- and the committed baseline profile carries the *old* `profile_sha256`, so it is a
    numeric comparison operand only and must never be fed to a stage (§A4.3).
    """
    tag = f"smoke_{cfg.smoke_year}"
    baseline = tmp_path / "baseline"
    current = tmp_path / "current"
    write_states_csv(baseline / f"{tag}_jet_states.csv", cfg)
    (baseline / f"{tag}_summary.txt").write_text(SUMMARY_TEXT)
    write_profile_nc(baseline / f"{tag}_profile.nc", cfg)

    write_states_csv(current / f"{tag}_jet_states.csv", cfg, flip_date=flip_date)
    text = SUMMARY_TEXT
    if summary_line is not None:
        lines = text.splitlines()
        lines[summary_line] = "  double        :     19  ( 67.9 %)"
        text = "\n".join(lines) + "\n"
    (current / f"{tag}_summary.txt").write_text(text)
    write_profile_nc(current / f"{tag}_profile.nc", cfg, offset=profile_offset,
                     times=current_times)

    out_paths = cli.OutputNames(
        profile=current / f"{tag}_profile.nc",
        states_csv=current / f"{tag}_jet_states.csv",
        summary=current / f"{tag}_summary.txt",
        panels=(current / f"{tag}.png",),
        evidence=current / f"{tag}_regression.json",
    )
    return baseline, out_paths


def test_check_regression_2018_passes_and_each_arm_fails_independently(tmp_path, archive):
    """§A8 row 22 (§A9.2, all three arms): identical operands pass, and each of the three
    comparisons is shown to fail *alone* -- a flipped state, an altered summary line, and a profile
    offset by 0.06 m/s, just past the 0.05 m/s allowance.

    The function returns a record and does **not** raise on a comparison failure (O5): the run
    finishes, the figure is written, and only then does the caller set the exit code.
    """
    cfg = make_cfg(tmp_path, archive)
    log = _logger()
    n_expected = cfg.days_per_season * cfg.sector.n_lat
    assert n_expected == 140

    # -- arm 0: identical operands ---------------------------------------------------------
    baseline, out = regression_operands(tmp_path / "same", cfg)
    record = rda.check_regression_2018(cfg, baseline, out, tmp_path / "same.json", log)
    assert record["passed"] is True
    assert record["passed_by_comparison"] == {"jet_states_csv": True, "summary_txt": True,
                                              "profile_nc": True}
    assert record["n_compared"] == record["n_expected"] == n_expected
    assert record["max_abs_diff"] == pytest.approx(0.0)
    assert record["tolerance"] == rda.REGRESSION_TOLERANCE == 0.05
    assert record["source"] == "rda_hourly" and record["profile_sha256"] == cfg.profile_sha256
    written = json.loads((tmp_path / "same.json").read_text())
    assert written["passed"] is True and written["comparisons"]["profile_nc"]["n_compared"] == 140

    # -- arm 1: one flipped state label ----------------------------------------------------
    baseline, out = regression_operands(tmp_path / "state", cfg, flip_date="2018-02-11")
    record = rda.check_regression_2018(cfg, baseline, out, tmp_path / "state.json", log)
    assert record["passed"] is False
    assert record["passed_by_comparison"] == {"jet_states_csv": False, "summary_txt": True,
                                              "profile_nc": True}
    states = record["comparisons"]["jet_states_csv"]
    assert states["n_mismatched_rows"] == 1
    offender = states["mismatches"][0]
    assert offender["date"] == "2018-02-11"
    assert offender["current"]["state"] != offender["baseline"]["state"]

    # -- arm 2: one altered summary line ---------------------------------------------------
    baseline, out = regression_operands(tmp_path / "summary", cfg, summary_line=4)
    record = rda.check_regression_2018(cfg, baseline, out, tmp_path / "summary.json", log)
    assert record["passed"] is False
    assert record["passed_by_comparison"] == {"jet_states_csv": True, "summary_txt": False,
                                              "profile_nc": True}
    summary = record["comparisons"]["summary_txt"]
    assert [d["line"] for d in summary["differing_lines"]] == [5]
    assert "19" in summary["differing_lines"][0]["current"]

    # -- arm 3: the profile offset past the allowance --------------------------------------
    baseline, out = regression_operands(tmp_path / "profile", cfg, profile_offset=0.06)
    record = rda.check_regression_2018(cfg, baseline, out, tmp_path / "profile.json", log)
    assert record["passed"] is False
    assert record["passed_by_comparison"] == {"jet_states_csv": True, "summary_txt": True,
                                              "profile_nc": False}
    prof = record["comparisons"]["profile_nc"]
    assert prof["max_abs_diff"] == pytest.approx(0.06, abs=1e-4)
    assert prof["n_compared"] == n_expected
    assert prof["n_exceeding_tolerance"] == n_expected
    assert "exceeds" in prof["reason"]

    # a difference *inside* the allowance is a pass, and the achieved value is still reported
    baseline, out = regression_operands(tmp_path / "within", cfg, profile_offset=0.004)
    record = rda.check_regression_2018(cfg, baseline, out, tmp_path / "within.json", log)
    assert record["passed"] is True
    assert record["max_abs_diff"] == pytest.approx(0.004, abs=1e-4)


def test_check_regression_2018_refuses_misaligned_operands(tmp_path, archive):
    """§A8 row 23 (§A9.2): the `join="exact"` trap.

    xarray defaults `arithmetic_join` to `"inner"`, so a bare `a - b` on operands whose time axes
    only overlap would silently compare the intersection and **pass a gate it never tested**. The
    current profile here is shifted one day forward, so an inner join would have compared 27 of the
    28 days and reported a clean zero. The check must refuse instead.
    """
    cfg = make_cfg(tmp_path, archive)
    days = season_days(cfg, cfg.smoke_year)
    shifted = np.array([np.datetime64(d.isoformat()) for d in days[1:]]
                       + [np.datetime64("2018-03-01")], dtype="datetime64[ns]")
    baseline, out = regression_operands(tmp_path / "misaligned", cfg, current_times=shifted)

    # the trap is real: there IS a 27-day intersection an inner join would have compared
    aligned = xr.align(profile.open_intermediate(out.profile)["U"],
                       profile.open_intermediate(baseline / "smoke_2018_profile.nc")["U"],
                       join="inner")
    assert aligned[0].sizes["time"] == 27

    record = rda.check_regression_2018(cfg, baseline, out, tmp_path / "misaligned.json", _logger())
    assert record["passed"] is False
    prof = record["comparisons"]["profile_nc"]
    assert prof["passed"] is False
    assert prof["n_compared"] == 0, "nothing may be compared once the operands disagree"
    assert prof["max_abs_diff"] is None
    assert "do not carry identical coordinates" in prof["reason"]
    assert "overlap" in prof["reason"]
    # the other two comparisons are untouched, so the failure is attributed where it belongs
    assert record["passed_by_comparison"] == {"jet_states_csv": True, "summary_txt": True,
                                              "profile_nc": False}

    # a short CSV likewise fails on row count rather than matching on its prefix
    rows = (out.states_csv).read_text().splitlines()
    out.states_csv.write_text("\n".join(rows[:-1]) + "\n")
    record = rda.check_regression_2018(cfg, baseline, out, tmp_path / "short.json", _logger())
    states = record["comparisons"]["jet_states_csv"]
    assert states["passed"] is False and "row counts disagree" in states["reason"]
    assert states["n_rows"] == 27 and states["n_expected_rows"] == 28


# ---------------------------------------------------------------------------------------------
# 24-25. the CLI: one evidence slot, and a gate that is never silently absent (§A7.3)
# ---------------------------------------------------------------------------------------------


def test_smoke_evidence_path_resolves_source_dependently(tmp_path, monkeypatch):
    """§A8 row 24 (§A7.3 item 4, plan §8 R12, risk DR17): one slot, named for the check the
    configured source can actually run -- and all three `all_paths()` lengths stay 5.

    A second field would have made a smoke run six paths long and broken the disjointness assertion
    that enforces R12. This test holds both configs to the same standard the frozen one is held to.
    """
    monkeypatch.setenv("SCRATCH", str(tmp_path / "scratch"))
    text = REAL_YAML.read_text()
    assert text.count("source: rda_hourly") == 1, "not a unique anchor in the frozen YAML"
    cds_path = tmp_path / "cds.yaml"
    cds_path.write_text(text.replace("source: rda_hourly", "source: cds_derived"))

    rda_cfg = load_config(REAL_YAML)
    cds_cfg = load_config(cds_path)
    assert rda_cfg.source == "rda_hourly" and cds_cfg.source == "cds_derived"

    for cfg, expected in ((rda_cfg, Path("data/smoke_2018_regression.json")),
                          (cds_cfg, Path("data/smoke_2018_r1_validation.json"))):
        campaign = cli.output_names(cfg, (cfg.year_first, cfg.year_last))
        smoke = cli.output_names(cfg, (cfg.smoke_year, cfg.smoke_year), smoke=True)
        subset = cli.output_names(cfg, (2000, 2010))

        assert smoke.evidence == expected
        assert campaign.evidence is None and subset.evidence is None
        assert (len(campaign.all_paths()) == len(smoke.all_paths())
                == len(subset.all_paths()) == 5)
        assert set(campaign.all_paths()) == CONTRACT_NAMES
        assert set(smoke.all_paths()) & CONTRACT_NAMES == set()
        assert set(subset.all_paths()) & CONTRACT_NAMES == set()
        for a, b in ((campaign, smoke), (campaign, subset), (smoke, subset)):
            assert not (set(a.all_paths()) & set(b.all_paths()))

    # the two evidence names are different files: neither source can overwrite the other's record
    rda_smoke = cli.output_names(rda_cfg, (2018, 2018), smoke=True)
    cds_smoke = cli.output_names(cds_cfg, (2018, 2018), smoke=True)
    assert rda_smoke.evidence != cds_smoke.evidence
    assert (rda_smoke.profile, rda_smoke.states_csv, rda_smoke.summary, rda_smoke.panels) == (
        cds_smoke.profile, cds_smoke.states_csv, cds_smoke.summary, cds_smoke.panels)


def test_smoke_without_profile_and_classify_skips_the_regression_and_says_so(tmp_path, archive,
                                                                            monkeypatch, caplog):
    """§A8 row 25 (§A7.3 item 3, risk DR12): the stale/missing-operand trap.

    `--stage` accepts arbitrary subsets, so an unconditionally placed regression check would make
    `--smoke --stage download` compare three files that do not exist and `--smoke --stage figure`
    compare **stale** ones from an earlier invocation. Both must skip -- and a silently absent gate
    is the failure mode this test exists to catch, so the skip must be announced *and* must name
    the stages that were missing. The last case is the control: with `profile` and `classify`
    present, the check really does run.

    `configure_logging` is replaced because `cli.run` calls `logging.basicConfig(force=True)`, which
    would tear down pytest's capture handler; nothing else about the run is altered.
    """
    cfg = make_cfg(tmp_path, archive)
    monkeypatch.setattr(cli, "configure_logging", lambda level: logging.getLogger("double_jet"))

    calls: list[str] = []
    monkeypatch.setattr(source, "preflight", lambda *a, **k: calls.append("preflight"))
    monkeypatch.setattr(source, "materialize_seasons", lambda *a, **k: calls.append("materialize"))
    monkeypatch.setattr(profile, "build_intermediate",
                        lambda *a, **k: calls.append("profile") or Path("x"))
    monkeypatch.setattr(classify_mod, "run_classify",
                        lambda *a, **k: calls.append("classify") or argparse.Namespace(ok=True))
    monkeypatch.setattr(figure, "run_figure", lambda *a, **k: calls.append("figure"))
    monkeypatch.setattr(rda, "check_regression_2018",
                        lambda *a, **k: calls.append("regression") or {"passed": True})

    def smoke_run(stages: tuple[str, ...]) -> int:
        calls.clear()
        caplog.clear()
        args = argparse.Namespace(config=cfg.source_path, preflight_network=False, smoke=True,
                                  years=None, stage=stages, skip_download=False, log_level="INFO")
        with caplog.at_level(logging.INFO):
            return cli.run(args)

    for stages in (("download",), ("figure",)):
        assert smoke_run(stages) == cli.EXIT_OK
        assert "regression" not in calls, f"--smoke --stage {stages} must not run the regression"
        messages = [r.getMessage() for r in caplog.records]
        skipped = [m for m in messages if "regression check is SKIPPED" in m]
        assert len(skipped) == 1, f"the skip must be announced exactly once for {stages}"
        assert "profile,classify" in skipped[0], "the skip must name the missing stages"
        assert str(cli.REGRESSION_BASELINE) in skipped[0]
        assert "NOT gated" in skipped[0]

    # the control: the gate is not vacuous -- with its operands' stages present, it runs.
    assert smoke_run(cli.STAGES) == cli.EXIT_OK
    assert calls == ["preflight", "materialize", "profile", "classify", "figure", "regression"]
    assert not [r for r in caplog.records if "regression check is SKIPPED" in r.getMessage()]


# ---------------------------------------------------------------------------------------------
# beyond the table: the pool size, and two real archive days
# ---------------------------------------------------------------------------------------------


def test_pbs_ncpus_overrides_the_configured_worker_count(tmp_path, archive, monkeypatch):
    """§A5.2 step 2: the job's requested shape and the parallelism can never disagree.

    Also the cheapest exercise of the multi-worker path there is -- two processes over a 28-day
    season -- so `ex.map`'s order preservation is not taken on trust.
    """
    cfg = make_cfg(tmp_path, archive)
    assert rda._pool_size(cfg) == (1, "cfg.rda.workers")

    monkeypatch.setenv("PBS_NCPUS", "2")
    assert rda._pool_size(cfg) == (2, "$PBS_NCPUS")
    nc = rda.write_season(cfg, 2018, _logger())
    u = profile.open_normalized(nc, cfg)
    assert [str(t)[:10] for t in u["time"].values] == [d.isoformat()
                                                       for d in season_days(cfg, 2018)]
    np.testing.assert_allclose(u.values[0], expected_daily_mean(cfg), atol=1e-4)

    monkeypatch.setenv("PBS_NCPUS", "   ")          # an empty value is "unset", not an error
    assert rda._pool_size(cfg) == (1, "cfg.rda.workers")
    monkeypatch.setenv("PBS_NCPUS", "eight")
    with pytest.raises(DownloadError, match="not an integer"):
        rda._pool_size(cfg)


@pytest.mark.skipif(not REAL_ARCHIVE.is_dir(),
                    reason=f"the RDA archive {REAL_ARCHIVE} is not mounted on this host")
def test_two_real_archive_days_load_at_the_production_shape(tmp_path, monkeypatch):
    """The one integration test: **two** real archive days, at the frozen 221 x 361 sector.

    Deliberately two days and not a season -- 1.6 GB apiece, and §A1.3 measured 4.69 s each. It
    pins the three things a synthetic fixture cannot: that the real headers are what §A1.1 says,
    that the loader cuts the contract's sector out of the real 721 x 1440 x 37 grid, and that
    `preflight_archive` passes against the archive the campaign will actually read.
    """
    monkeypatch.setenv("SCRATCH", str(tmp_path / "scratch"))
    monkeypatch.delenv("PBS_NCPUS", raising=False)
    cfg = load_config(REAL_YAML)
    assert cfg.source == "rda_hourly" and Path(cfg.rda.root) == REAL_ARCHIVE
    assert (cfg.sector.n_lat, cfg.sector.n_lon) == (221, 361)

    rda.preflight_archive(cfg, [cfg.smoke_year], _logger())

    days = season_days(cfg, cfg.smoke_year)[:2]
    means = []
    for day in days:
        path = rda._source_path(cfg, day)
        assert path.exists(), path
        with xr.open_dataset(path) as raw:                  # §A1.1, header only
            sizes = dict(raw.sizes)
            assert (sizes["time"], sizes["level"]) == (24, 37)
            assert (sizes["latitude"], sizes["longitude"]) == (721, 1440)
            assert "U" in raw.data_vars and "utc_date" in raw.data_vars
            assert raw["level"].attrs["units"] == "hPa"
            assert (np.diff(raw["latitude"].values) < 0).all()
            assert raw["longitude"].values[0] == 0.0 and raw["longitude"].values[-1] == 359.75

        date, mean, units = rda._read_day((cfg, path, day.isoformat()))
        assert date == day.isoformat()
        assert mean.shape == (221, 361) and mean.dtype == np.dtype("float64")
        assert np.isfinite(mean).all()
        assert units == {"u": "m s**-1", "latitude": "degrees_north",
                         "longitude": "degrees_east", "level": "hPa"}
        assert 5.0 < float(np.abs(mean).max()) < 150.0      # 250 hPa zonal wind, m s-1
        means.append(mean)

    assert np.abs(means[0] - means[1]).max() > 0.0, "two different days must not be identical"
