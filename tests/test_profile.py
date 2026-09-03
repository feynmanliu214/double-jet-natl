"""Every plan §4.2 gate, asserted to *fire* on a synthetic file built to break exactly it (§4.6).

Two rules shape this file:

* **The sector is always the production one** -- 221 latitudes x 361 longitudes. A season is only
  28 x 221 x 361 float32 (~0.1 MB zipped), so there is no reason to shrink the grid the shape
  assertions exist to protect.
* **Time is narrowed with a purpose-built YAML, never a monkeypatch.** Most gates need only two or
  three days of data, but `days_per_season` *is* one of the quantities under test, so patching it
  would disable the very gate the test is checking. `make_cfg` instead rewrites the real YAML's
  `season_months` to February -- the shortest month the calendar offers, 28 days -- and leaves every
  other scientific value exactly as `configs/double_jet.yaml` states it. `test_production_season_*`
  keeps the full MJJAS season, so 153 x 221 x 361 is exercised too.

`make_cfg` also repoints `paths.scratch_raw`, `data_dir` and `figs_dir` into `tmp_path`, so no test
can read or write the real `$SCRATCH` or the repository's `data/`.
"""

from __future__ import annotations

import calendar
import json
import logging
import shutil
import sys
import types
import zipfile
from pathlib import Path

import numpy as np
import pytest
import xarray as xr
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:                    # `pytest tests/...` from anywhere
    sys.path.insert(0, str(REPO_ROOT))

from double_jet import download, profile                      # noqa: E402
from double_jet.config import Config, load_config             # noqa: E402

REAL_YAML = REPO_ROOT / "configs" / "double_jet.yaml"

# The name ERA5's new CDS netCDFs use for each axis (§1.6); tests that vary one say so explicitly.
ERA5_NAMES = {"time": "valid_time", "level": "pressure_level",
              "lat": "latitude", "lon": "longitude"}


# ---------------------------------------------------------------------------------------------
# fixtures and builders
# ---------------------------------------------------------------------------------------------


def make_cfg(tmp_path: Path, name: str = "cfg.yaml", **overrides) -> Config:
    """The real config with only `paths` (always) and the given top-level keys rewritten."""
    raw = yaml.safe_load(REAL_YAML.read_text())
    raw.update(overrides)
    raw["paths"] = {"scratch_raw": str(tmp_path), "data_dir": str(tmp_path / "data"),
                    "figs_dir": str(tmp_path / "figs")}
    path = tmp_path / name
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    return load_config(path)


def feb_cfg(tmp_path: Path) -> Config:
    """A 28-day February season on the production sector (see the module docstring)."""
    return make_cfg(tmp_path, "cfg_feb.yaml", season_months=[2], year_first=2018, year_last=2019,
                    smoke_year=2018)


def season_times(cfg: Config, year: int, hourly: bool = False) -> np.ndarray:
    """One timestamp per configured season day, or `cfg.hourly_times` on each of them."""
    stamps = []
    for month in cfg.season_months:
        for day in range(1, calendar.monthrange(year, month)[1] + 1):
            date = f"{year}-{month:02d}-{day:02d}"
            if hourly:
                stamps += [np.datetime64(f"{date}T{t}") for t in cfg.hourly_times]
            else:
                stamps.append(np.datetime64(date))
    return np.array(stamps, dtype="datetime64[ns]")


def synthetic_wind(nt: int, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """A jet-like field that varies along longitude as well as latitude.

    The longitude dependence is quadratic, so a trapezoidal or endpoint-weighted zonal mean would
    differ from the plain one by O(1) m/s -- the tests compare against `np.mean` and would catch it.
    """
    jet = 30.0 * np.exp(-((lat - 45.0) / 8.0) ** 2)
    x = np.linspace(0.0, 1.0, lon.size)
    field = jet[:, None] + 5.0 * (x**2 - 1.0 / 3.0)[None, :]
    return np.broadcast_to(field[None, :, :], (nt, lat.size, lon.size)).astype("float32").copy()


def write_season(path: Path, cfg: Config, *, year: int = 2018, hourly: bool = False,
                 times: np.ndarray | None = None, lat: np.ndarray | None = None,
                 lon: np.ndarray | None = None, level: float = 250.0, level_units: str = "hPa",
                 wind_units: str = "m s**-1", lat_units: str = "degrees_north",
                 lon_units: str = "degrees_east", scalars: bool = True,
                 level_as_dim: bool = True, names: dict[str, str] | None = None,
                 values: np.ndarray | None = None) -> Path:
    """Write one synthetic raw season as the CDS netCDFs are shaped (§1.6), with one axis broken.

    Defaults reproduce a *good* file: descending latitude, 0-360 longitude, a size-1 level
    dimension, scalar `number`/`expver`. Each test overrides exactly one thing.
    """
    names = {**ERA5_NAMES, **(names or {})}
    if times is None:
        times = season_times(cfg, year, hourly=hourly)
    if lat is None:
        lat = cfg.sector.latitudes()[::-1]                 # ERA5 delivers 90 -> -90
    if lon is None:
        lon = (cfg.sector.longitudes() + 360.0) % 360.0    # ERA5 delivers 0 -> 360
    if values is None:
        values = synthetic_wind(times.size, lat, lon)

    dims = (names["time"], names["lat"], names["lon"])
    coords = {
        names["time"]: times,
        names["lat"]: (names["lat"], np.asarray(lat, dtype=float), {"units": lat_units}),
        names["lon"]: (names["lon"], np.asarray(lon, dtype=float), {"units": lon_units}),
    }
    if level_as_dim:
        dims = (names["time"], names["level"]) + dims[1:]
        values = values[:, None, :, :]
        coords[names["level"]] = (names["level"], np.array([level], dtype=float),
                                  {"units": level_units})
    else:
        coords[names["level"]] = ((), float(level), {"units": level_units})
    if scalars:
        coords["number"] = ((), 0)
        coords["expver"] = ((), "0001")

    ds = xr.Dataset({"u": (dims, values, {"units": wind_units})}, coords=coords)
    path.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(path, encoding={"u": {"zlib": True, "complevel": 1}})
    return path


# ---------------------------------------------------------------------------------------------
# the happy path, at the production shape
# ---------------------------------------------------------------------------------------------


def test_production_season_wrapped_longitudes_pass(tmp_path):
    """R2: longitudes delivered as 300...30 normalize to -60...30, on the real 153 x 221 x 361."""
    cfg = make_cfg(tmp_path, "cfg_full.yaml")            # the campaign config, MJJAS, unmodified
    assert (cfg.days_per_season, cfg.sector.n_lat, cfg.sector.n_lon) == (153, 221, 361)
    path = write_season(tmp_path / "season_2018.nc", cfg, year=2018)

    # the file really was written in the 0-360 convention, wrapping through Greenwich
    with xr.open_dataset(path) as raw:
        assert float(raw["longitude"].min()) == 0.0 and float(raw["longitude"].max()) > 300.0
        assert float(raw["latitude"][0]) > float(raw["latitude"][-1])

    u = profile.open_normalized(path, cfg)
    assert u.dims == ("time", "latitude", "longitude")
    assert u.shape == (153, 221, 361)
    np.testing.assert_allclose(u["longitude"].values, cfg.sector.longitudes(), atol=1e-6)
    np.testing.assert_allclose(u["latitude"].values, cfg.sector.latitudes(), atol=1e-6)
    assert set(u.coords) == {"time", "latitude", "longitude"}       # level/number/expver gone

    profile_da = profile.season_profile(path, cfg)
    assert profile_da.dims == ("time", "latitude")
    assert profile_da.shape == (153, 221)
    # I7: the plain unweighted mean over the 361 longitudes, not a trapezoid and not cos-weighted.
    expected = np.asarray(u.values, dtype="float64").mean(axis=2)
    np.testing.assert_allclose(profile_da.values, expected, atol=1e-4)


def test_accepted_coordinate_aliases_pass_and_unknown_name_fails(tmp_path):
    """Step 1: `lat`/`lon`/`time`/`level` are resolved by lookup; anything else is an error."""
    cfg = feb_cfg(tmp_path)
    good = write_season(tmp_path / "aliases.nc", cfg,
                        names={"time": "time", "lat": "lat", "lon": "lon", "level": "level"})
    u = profile.open_normalized(good, cfg)
    assert u.dims == ("time", "latitude", "longitude")     # renamed to the canonical spelling

    bad = write_season(tmp_path / "unknown_axis.nc", cfg, names={"lat": "latitudes"})
    with pytest.raises(profile.ProfileError) as exc:
        profile.open_normalized(bad, cfg)
    assert "latitude" in str(exc.value) and "latitudes" in str(exc.value)


def test_scalar_number_and_expver_are_dropped(tmp_path):
    """Step 3: the scalar coordinates the CDS files carry never reach a downstream stage."""
    cfg = feb_cfg(tmp_path)
    path = write_season(tmp_path / "scalars.nc", cfg, scalars=True)
    with xr.open_dataset(path) as raw:
        assert {"number", "expver"} <= set(raw.coords)      # they really are in the file

    u = profile.open_normalized(path, cfg)
    assert "number" not in u.coords and "expver" not in u.coords
    assert set(u.coords) == {"time", "latitude", "longitude"}


def test_scalar_level_coordinate_without_a_dimension_passes(tmp_path):
    """Step 2 must read the level's *value* whether or not it is a size-1 dimension."""
    cfg = feb_cfg(tmp_path)
    path = write_season(tmp_path / "scalar_level.nc", cfg, level_as_dim=False)
    u = profile.open_normalized(path, cfg)
    assert u.dims == ("time", "latitude", "longitude")


# ---------------------------------------------------------------------------------------------
# one test per gate, each asserted to fire
# ---------------------------------------------------------------------------------------------


def test_nonuniform_latitude_axis_rejected(tmp_path):
    """Step 5: 221 points with the right bounds is not enough -- the whole array is compared.

    Count-and-bounds would accept this axis, and I1's "11 samples = 2.5 deg" boxcar depends on the
    spacing being uniform.
    """
    cfg = feb_cfg(tmp_path)
    lat = cfg.sector.latitudes()
    lat[110] += 0.1                                     # still ascending, still 221 points, 20..75
    path = write_season(tmp_path / "nonuniform_lat.nc", cfg, lat=lat)
    with pytest.raises(profile.ProfileError) as exc:
        profile.open_normalized(path, cfg)
    message = str(exc.value)
    # names the check, the offending index and both values seen
    assert "latitude" in message and "index 110" in message and "47.5" in message


def test_pressure_coordinate_in_pa_rejected(tmp_path):
    """Step 6: a Pa-tagged coordinate would make step 2's `== 250` wrong by a factor of 100."""
    cfg = feb_cfg(tmp_path)
    path = write_season(tmp_path / "level_pa.nc", cfg, level=250.0, level_units="Pa")
    with pytest.raises(profile.ProfileError) as exc:
        profile.open_normalized(path, cfg)
    assert "units" in str(exc.value) and "Pa" in str(exc.value)


def test_wind_in_kelvin_rejected(tmp_path):
    """Step 6: the config thresholds are in m/s and nothing downstream converts."""
    cfg = feb_cfg(tmp_path)
    path = write_season(tmp_path / "wind_kelvin.nc", cfg, wind_units="K")
    with pytest.raises(profile.ProfileError) as exc:
        profile.open_normalized(path, cfg)
    assert "'K'" in str(exc.value) and "m s**-1" in str(exc.value)


def test_wrong_pressure_level_rejected(tmp_path):
    """Step 2: the level is asserted by VALUE, so a 200 hPa file cannot be indexed into place."""
    cfg = feb_cfg(tmp_path)
    path = write_season(tmp_path / "level_200.nc", cfg, level=200.0)
    with pytest.raises(profile.ProfileError) as exc:
        profile.open_normalized(path, cfg)
    assert "200" in str(exc.value) and "250" in str(exc.value)


def test_positive_infinity_cell_rejected(tmp_path):
    """Step 8: `np.isfinite`, not `~np.isnan` -- a +inf cell would survive a NaN-only check."""
    cfg = feb_cfg(tmp_path)
    lat, lon = cfg.sector.latitudes()[::-1], (cfg.sector.longitudes() + 360.0) % 360.0
    values = synthetic_wind(cfg.days_per_season, lat, lon)
    values[3, 100, 200] = np.inf
    assert not np.isnan(values).any()                   # a NaN-only gate would pass this file
    path = write_season(tmp_path / "inf_cell.nc", cfg, values=values)
    with pytest.raises(profile.ProfileError) as exc:
        profile.open_normalized(path, cfg)
    assert "non-finite" in str(exc.value) and "inf" in str(exc.value)


def test_wrong_day_count_rejected(tmp_path):
    """Step 7: a season short of `days_per_season` never reaches the intermediate."""
    cfg = feb_cfg(tmp_path)
    times = season_times(cfg, 2018)[:-1]
    path = write_season(tmp_path / "short_season.nc", cfg, times=times)
    with pytest.raises(profile.ProfileError) as exc:
        profile.open_normalized(path, cfg)
    assert "27 timestamps" in str(exc.value) and "28" in str(exc.value)


def test_days_outside_the_configured_season_rejected(tmp_path):
    """Step 7: the days must lie in `season_months` of one year, not merely be the right count."""
    cfg = feb_cfg(tmp_path)
    times = season_times(cfg, 2018).copy()
    times[0] = np.datetime64("2018-03-15")              # still 28 unique days, one in March
    path = write_season(tmp_path / "wrong_month.nc", cfg, times=times)
    with pytest.raises(profile.ProfileError) as exc:
        profile.open_normalized(path, cfg)
    assert "month" in str(exc.value) and "3" in str(exc.value)


def test_hourly_reader_accepts_the_configured_hours_and_rejects_others(tmp_path):
    """Step 7, `hourly=True`: the R1 cross-check operand must be exactly 00/06/12/18 on every day."""
    cfg = feb_cfg(tmp_path)
    good = write_season(tmp_path / "hourly_ok.nc", cfg, hourly=True)
    u = profile.open_normalized(good, cfg, hourly=True)
    assert u.shape == (cfg.days_per_season * len(cfg.hourly_times), 221, 361)

    shifted = season_times(cfg, 2018, hourly=True) + np.timedelta64(3, "h")   # 03/09/15/21
    bad = write_season(tmp_path / "hourly_shifted.nc", cfg, times=shifted)
    with pytest.raises(profile.ProfileError) as exc:
        profile.open_normalized(bad, cfg, hourly=True)
    assert "03:00" in str(exc.value) and "00:00" in str(exc.value)

    # ... and the daily reader must not accept a 6-hourly file either
    with pytest.raises(profile.ProfileError):
        profile.open_normalized(good, cfg, hourly=False)


# ---------------------------------------------------------------------------------------------
# the intermediate
# ---------------------------------------------------------------------------------------------


def test_build_intermediate_round_trip(tmp_path):
    """Two seasons -> `U(time, latitude)` with the attributes classify.py's guard reads (M3)."""
    cfg = feb_cfg(tmp_path)
    log = _logger()
    for year in (2018, 2019):
        write_season(Path(download.season_paths(cfg, year)["nc"]), cfg, year=year)

    out_path = tmp_path / "intermediate.nc"
    # Deliberately unsorted: build_intermediate sorts by time, it does not trust the caller's order.
    returned = profile.build_intermediate(cfg, [2019, 2018], out_path, log)
    assert returned == out_path and out_path.exists()

    ds = profile.open_intermediate(out_path)
    assert ds["U"].dims == ("time", "latitude")
    assert ds["U"].shape == (2 * cfg.days_per_season, cfg.sector.n_lat)
    assert ds["U"].dtype == np.float32
    assert ds["latitude"].dtype == np.float64
    lat = ds["latitude"].values
    assert (np.diff(lat) > 0).all()
    np.testing.assert_allclose(lat, cfg.sector.latitudes(), atol=1e-6)

    times = ds["time"].values
    assert times.dtype == np.dtype("datetime64[ns]")
    assert (np.diff(times) > np.timedelta64(0, "ns")).all()          # sorted and unique
    assert str(times[0])[:10] == "2018-02-01" and str(times[-1])[:10] == "2019-02-28"

    # the guard classify.py relies on, and the provenance §4.2 asks for
    assert ds.attrs["profile_sha256"] == cfg.profile_sha256
    assert ds.attrs["config_sha256"] == cfg.config_sha256
    assert ds.attrs["source_dataset"] == cfg.dataset
    assert ds.attrs["pressure_level"] == cfg.pressure_level
    sources = json.loads(ds.attrs["source_files"])
    assert [s["year"] for s in sources] == [2019, 2018]
    for entry in sources:
        on_disk = Path(download.season_paths(cfg, entry["year"])["nc"])
        assert entry["name"] == on_disk.name and entry["bytes"] == on_disk.stat().st_size
        assert len(entry["sha256"]) == 64
    assert json.loads(ds.attrs["request_template"])["pressure_level"] == ["250"]
    assert json.loads(ds.attrs["package_versions"])["xarray"] == xr.__version__
    assert ds.attrs["interpreter"] == sys.executable
    assert ds.attrs["created"].endswith("Z") and ds.attrs["plan"] == "wave1-plan.md"

    # storage contract: float32 with zlib level 4
    with xr.open_dataset(out_path) as stored:
        assert stored["U"].encoding["zlib"] is True
        assert stored["U"].encoding["complevel"] == 4
        assert stored["U"].encoding["dtype"] == np.dtype("float32")

    # the values are the unweighted zonal means of the seasons that went in
    first = profile.season_profile(Path(download.season_paths(cfg, 2018)["nc"]), cfg)
    np.testing.assert_allclose(ds["U"].values[:cfg.days_per_season], first.values, atol=1e-5)


def test_build_intermediate_reports_a_missing_season(tmp_path):
    cfg = feb_cfg(tmp_path)
    write_season(Path(download.season_paths(cfg, 2018)["nc"]), cfg, year=2018)
    with pytest.raises(profile.ProfileError) as exc:
        profile.build_intermediate(cfg, [2018, 2019], tmp_path / "out.nc", _logger())
    assert "2019" in str(exc.value)


# ---------------------------------------------------------------------------------------------
# the two download.py behaviours §4.6 asks this file to cover
# ---------------------------------------------------------------------------------------------


def test_one_member_zip_extracts_to_the_expected_nc(tmp_path):
    """§4.1: the derived product's transport container holds one member; it lands as `<stem>.nc`."""
    cfg = feb_cfg(tmp_path)
    member = write_season(tmp_path / "member.nc", cfg, year=2018)
    zip_path = tmp_path / "u250_natl_mjjas_2018.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.write(member, arcname="data_stream-oper_stepType-avgua.nc")

    dest = Path(download.season_paths(cfg, 2018)["nc"])
    returned = download.extract_zip(zip_path, dest)
    assert returned == dest and dest.exists()
    assert dest.read_bytes() == member.read_bytes()
    # and what came out is still a readable season
    assert profile.open_normalized(dest, cfg).shape == (cfg.days_per_season, 221, 361)


def test_stale_request_sidecar_forces_a_redownload(tmp_path):
    """R11: a `.nc` fetched under a different request is never silently reused.

    The `.nc` is identical in both halves, so the sidecar is provably what flips the answer.
    """
    cfg = feb_cfg(tmp_path)
    year = 2018
    paths = download.season_paths(cfg, year)
    write_season(Path(paths["nc"]), cfg, year=year)
    sidecar = Path(paths["request"])

    sidecar.write_text(json.dumps(download.build_request(cfg, year)))
    ok, reason = download.season_is_complete(cfg, year)
    assert ok is True, reason                       # baseline: a matching sidecar is a valid skip

    stale = download.build_request(cfg, year)
    stale["pressure_level"] = ["500"]               # the file on disk is 250 hPa
    sidecar.write_text(json.dumps(stale))
    ok, reason = download.season_is_complete(cfg, year)
    assert ok is False
    assert reason and "pressure_level" in reason


def _logger() -> logging.Logger:
    log = logging.getLogger("test_profile")
    log.addHandler(logging.NullHandler())
    return log


@pytest.mark.parametrize("as_zip", [True, False])
def test_derived_product_is_accepted_whether_or_not_it_arrives_zipped(tmp_path, monkeypatch, as_zip):
    """The derived product's container is detected, not assumed.

    Plan §1.4 recorded from ECMWF's documentation that this product *always* returns a ZIP.
    Smoke job 3466587 (2026-09-03) measured otherwise: it delivered a bare netCDF, and the
    unconditional `extract_zip` failed with "File is not a zip file". Both forms must now yield
    the same `.nc` artifact plus its request sidecar -- and §4.1 already calls the ZIP incidental
    transport, so no deliverable depends on which arrived. See docs/deviations.md.
    """
    cfg = feb_cfg(tmp_path)
    year = 2018
    payload = write_season(tmp_path / "payload.nc", cfg, year=year)

    def fake_retrieve(dataset, request, target):
        """Stand in for cdsapi: write whichever container this parametrization is testing."""
        if as_zip:
            with zipfile.ZipFile(target, "w") as archive:
                archive.write(payload, arcname="data_stream-oper_stepType-avgua.nc")
        else:
            shutil.copyfile(payload, target)

    monkeypatch.setattr(download, "_client",
                        lambda: types.SimpleNamespace(retrieve=fake_retrieve))
    download._download_season(cfg, year, hourly=False, log=_logger())

    paths = download.season_paths(cfg, year)
    assert Path(paths["nc"]).exists(), "the season's .nc artifact must exist in both cases"
    assert Path(paths["request"]).exists(), "the request sidecar must exist in both cases"
    # The ZIP is kept only when one actually arrived; its absence never makes a season incomplete.
    assert Path(paths["zip"]).exists() is as_zip
    assert download.season_is_complete(cfg, year) == (True, "")
    assert profile.open_normalized(Path(paths["nc"]), cfg).shape == (cfg.days_per_season, 221, 361)
