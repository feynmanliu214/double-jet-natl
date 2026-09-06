"""The explorer: the payload round-trips, the table recomputes, and every gate fires (D4 §B12).

Two things this file is deliberately built to avoid.

**Fixtures that cannot catch the module.** The synthetic intermediate's global attributes are
written out **explicitly** here rather than through `profile._intermediate_attrs`, so this file is
itself the record of the attribute contract the explorer depends on: if `profile.py` ever stops
writing one of them, `test_a_missing_attribute_fails_naming_it` still says which. For the same
reason `_recompute_summary` is a second, independently written run-length pass rather than a call
into `explorer._runs` -- a recomputation that shares the implementation recomputes nothing.

**Claiming more than a payload test proves.** `json.loads` on the embedded block verifies the
*payload* -- that a blank CSV cell became `null` and a number stayed a number. It does not execute
the JavaScript that maps `null -> NaN` before the mockup's `isFinite` guards, and a browser harness
would be disproportionate for a zero-compute change (§B12.1). So the round-trip test additionally
pins the hydration statement as a **string**: the payload half is proven, the JS half is held
against silent deletion, and neither is called a browser test.

`isFinite(null)` is `true` in JavaScript, which is why that one line is load-bearing: a `null`
latitude reaching `renderDetail` would draw a core at 0 °N instead of drawing nothing (risk BR3).
"""

from __future__ import annotations

import calendar
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:                      # `pytest tests/` from any cwd
    sys.path.insert(0, str(REPO_ROOT))

from double_jet import explorer                         # noqa: E402
from double_jet.classify import CSV_COLUMNS, ProfileMismatchError   # noqa: E402
from double_jet.config import Config, load_config       # noqa: E402

# --- the synthetic season -----------------------------------------------------------------------
#
# June + July: two whole months, so `month_starts` has two entries and a wrong month offset shows;
# neither is February, so `days_per_season` is the same in every year (I6, risk BR7). 2001-2003 are
# three consecutive seasons, enough for a run-length pass to have somewhere to go wrong.

SEASON_MONTHS = (6, 7)
DAYS_PER_SEASON = 61                                    # 30 + 31
YEAR_FIRST, YEAR_LAST = 2001, 2003
SEASON_YEARS = tuple(range(YEAR_FIRST, YEAR_LAST + 1))

# A 0.5° band, 41 points. Every scientific number in this file is a *test* number and unrelated to
# the frozen contract -- `tests/test_config.py` is the tripwire for those.
LAT_MIN, LAT_MAX, RESOLUTION = 30.0, 50.0, 0.5
LON_MIN, LON_MAX = -15.0, 20.0

U_CORE_MIN, SEPARATION_MIN, PROMINENCE_MIN = 15.0, 10.0, 5.0
SMOOTH_WINDOW_DEG = 2.0                                 # 4 steps at 0.5° -> 5 points, centerable

HYDRATION = "const num = v => v === null ? NaN : v;"


def season_dates(year: int) -> list[str]:
    """The season's calendar days, enumerated here rather than by the module under test.

    `explorer._season_dates` does the same job; a fixture built from it could not catch it
    enumerating the wrong days (`tests/test_rda.py:108`'s rule).
    """
    return [f"{year:04d}-{month:02d}-{day:02d}"
            for month in SEASON_MONTHS
            for day in range(1, calendar.monthrange(year, month)[1] + 1)]


def day_record(year: int, index: int, position: int) -> dict:
    """One CSV row. `position` cycles 0..4, giving 3 double, 1 single and 1 none day in five.

    Every value satisfies the three detection thresholds with room to spare, so a test that
    perturbs one arm perturbs only that arm. The winds carry more decimals than the payload keeps,
    so `round(x, 1)` is genuinely lossy and the round-trip asserts the *stated* rounding rather
    than trivial equality.
    """
    date = season_dates(year)[index]
    drift = 0.0123456789 * index + 0.7 * (year - YEAR_FIRST)
    if position == 4:
        return {"date": date, "state": "none", "lat_1": "", "u_1": "",
                "lat_2": "", "u_2": "", "interjet_min": ""}
    if position == 3:
        return {"date": date, "state": "single",
                "lat_1": f"{40.0 + 0.5 * (index % 8):.2f}", "u_1": f"{30.0 + drift:.10f}",
                "lat_2": "", "u_2": "", "interjet_min": ""}
    return {"date": date, "state": "double",
            "lat_1": f"{32.0 + 0.5 * (index % 4):.2f}", "u_1": f"{20.0 + drift:.10f}",
            "lat_2": f"{46.0 + 0.5 * (index % 4):.2f}", "u_2": f"{25.0 + drift:.10f}",
            "interjet_min": f"{10.0 + 0.1 * (index % 3):.10f}"}


def states_frame() -> pd.DataFrame:
    """The whole synthetic CSV as a frame, in `classify.CSV_COLUMNS` order."""
    rows = [day_record(year, index, index % 5)
            for year in SEASON_YEARS
            for index in range(DAYS_PER_SEASON)]
    return pd.DataFrame.from_records(rows, columns=list(CSV_COLUMNS))


def write_states_csv(path: Path, frame: pd.DataFrame | None = None) -> Path:
    frame = states_frame() if frame is None else frame
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return path


def make_cfg(tmp_path: Path, **overrides) -> Config:
    """The reduced-grid test config. `overrides` are applied to the top-level mapping."""
    raw = {
        "dataset": "derived-era5-pressure-levels-daily-statistics",
        "hourly_dataset": "reanalysis-era5-pressure-levels",
        "variable": "u_component_of_wind",
        "pressure_level": 250,
        "season_months": list(SEASON_MONTHS),
        "year_first": YEAR_FIRST,
        "year_last": YEAR_LAST,
        "smoke_year": YEAR_FIRST,
        "daily_statistic": "daily_mean",
        "time_zone": "utc+00:00",
        "frequency": "6_hourly",
        "hourly_times": ["00:00", "06:00", "12:00", "18:00"],
        "r1_tolerance": 1.0e-3,
        "max_in_flight": 3,
        "source": "rda_hourly",
        "sector": {"lat_min": LAT_MIN, "lat_max": LAT_MAX, "lon_min": LON_MIN,
                   "lon_max": LON_MAX, "resolution": RESOLUTION},
        "detection": {"u_core_min": U_CORE_MIN, "separation_min_deg": SEPARATION_MIN,
                      "prominence_min": PROMINENCE_MIN, "smooth_window_deg": SMOOTH_WINDOW_DEG},
        "sanity": {"double_fraction_min": 0.05, "double_fraction_max": 0.90, "core_lat_min": 25.0,
                   "core_lat_max": 70.0, "core_lat_fraction_min": 0.95, "smoke_peak_min": 20.0,
                   "smoke_peak_max": 40.0},
        "rda": {"root": str(tmp_path / "archive"), "file_template": "e5.{ymd}.nc",
                "dataset_id": "ds633.0-test", "workers": 1},
        "paths": {"scratch_raw": str(tmp_path / "scratch"), "data_dir": str(tmp_path / "data"),
                  "figs_dir": str(tmp_path / "figs")},
    }
    raw.update(overrides)
    path = tmp_path / "cfg.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    return load_config(path)


def intermediate_attrs(cfg: Config, **overrides) -> dict:
    """Exactly the global attributes the explorer reads, spelled out.

    Written by hand, not through `profile._intermediate_attrs` (§B12): this dict *is* the contract
    the module depends on, and a test that generated it from the writer could not detect the writer
    and the reader drifting together.
    """
    attrs = {
        "source_dataset": cfg.active_dataset,
        "variable": cfg.variable,
        "pressure_level": int(cfg.pressure_level),
        "pressure_level_units": "hPa",
        "sector": json.dumps({"lat_min": cfg.sector.lat_min, "lat_max": cfg.sector.lat_max,
                              "lon_min": cfg.sector.lon_min, "lon_max": cfg.sector.lon_max,
                              "resolution": cfg.sector.resolution}, sort_keys=True),
        "season_months": json.dumps(list(cfg.season_months)),
        "years": json.dumps(list(SEASON_YEARS)),
        "days_per_season": DAYS_PER_SEASON,
        "profile_fields": json.dumps(cfg.profile_fields(), sort_keys=True),
        "profile_sha256": cfg.profile_sha256,
    }
    attrs.update(overrides)
    return attrs


def write_profile_nc(path: Path, cfg: Config, *, lat: np.ndarray | None = None,
                     drop: str | None = None, **attr_overrides) -> Path:
    """A `U(time, latitude)` intermediate in `profile.open_intermediate`'s shape."""
    latitude = cfg.sector.latitudes() if lat is None else np.asarray(lat, dtype=float)
    times = np.array([np.datetime64(d) for year in SEASON_YEARS for d in season_dates(year)],
                     dtype="datetime64[ns]")
    base = 20.0 + 10.0 * np.exp(-((latitude - 40.0) / 5.0) ** 2)
    values = np.tile(base, (times.size, 1)).astype("float32")
    ds = xr.Dataset({"U": (("time", "latitude"), values)},
                    coords={"time": times, "latitude": latitude})
    ds.attrs = intermediate_attrs(cfg, **attr_overrides)
    if drop is not None:
        ds.attrs.pop(drop, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(path)
    return path


class _Log:
    """A logger stand-in that records nothing and asserts nothing; the tests read files, not logs."""

    def info(self, *args, **kwargs) -> None:
        pass

    warning = error = debug = info


def build(tmp_path: Path, *, frame: pd.DataFrame | None = None, cfg: Config | None = None,
          lat: np.ndarray | None = None, drop: str | None = None, **attr_overrides):
    """Run the explorer over a synthetic pair and return `(cfg, out_dir)`."""
    cfg = make_cfg(tmp_path) if cfg is None else cfg
    out = tmp_path / "out"
    out.mkdir(parents=True, exist_ok=True)
    profile_path = write_profile_nc(tmp_path / "profile.nc", cfg, lat=lat, drop=drop,
                                    **attr_overrides)
    csv_path = write_states_csv(tmp_path / "states.csv", frame)
    explorer.run_explorer(cfg, profile_path, csv_path, out / "explorer.html",
                          out / "season_summary.csv", out / "annual.png", log=_Log())
    return cfg, out


def embedded(html_path: Path, block: str) -> dict:
    """One `<script type="application/json">` block, parsed."""
    text = html_path.read_text(encoding="utf-8")
    match = re.search(
        rf'<script id="{block}" type="application/json">(.*?)</script>', text, re.S)
    assert match is not None, f"{block} is not in {html_path}"
    return json.loads(match.group(1))


def _recompute_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """§B12.2: all eight columns, recomputed from the CSV by a pass written independently.

    `groupby` on the year and `value_counts` for the three states; the run length is a plain
    accumulate rather than `explorer._runs`, so the two implementations can disagree.
    """
    dates = pd.to_datetime(frame["date"], format="%Y-%m-%d")
    rows = []
    for year, block in frame.assign(_y=dates.dt.year).groupby("_y", sort=True):
        counts = block["state"].value_counts()
        lengths, current = [], 0
        for state in block["state"]:
            if state == "double":
                current += 1
            elif current:
                lengths.append(current)
                current = 0
        if current:
            lengths.append(current)
        n_days = len(block)
        n_double = int(counts.get("double", 0))
        rows.append({"year": int(year), "n_days": n_days, "n_double": n_double,
                     "n_single": int(counts.get("single", 0)),
                     "n_none": int(counts.get("none", 0)),
                     "pct_double": 100.0 * n_double / n_days,
                     "n_double_runs": len(lengths),
                     "longest_double_run": max(lengths, default=0)})
    return pd.DataFrame(rows, columns=list(explorer.SUMMARY_COLUMNS))


def assert_round_trip(payload: dict, frame: pd.DataFrame) -> None:
    """§B12.1, factored so `test_against_the_real_artifacts` runs the identical assertions."""
    frame = frame.copy()
    frame["_year"] = pd.to_datetime(frame["date"], format="%Y-%m-%d").dt.year
    codes = payload["state_codes"]
    years = [int(s["year"]) for s in payload["seasons"]]
    assert years == sorted(years), "seasons must be ascending by year (§B5.1)"
    assert years == sorted(frame["_year"].unique().tolist())

    for season in payload["seasons"]:
        year = int(season["year"])
        block = frame[frame["_year"] == year].reset_index(drop=True)
        assert len(season["state"]) == payload["days_per_season"] == len(block)
        for column in ("lat_1", "u_1", "lat_2", "u_2", "interjet_min"):
            assert len(season[column]) == len(block), (year, column)

        first_month = payload["first_month"]
        for d in range(len(block)):
            row = block.iloc[d]
            assert codes[season["state"][d]] == row["state"], (year, d)

            # the day index maps to the CSV's own date
            expected = (np.datetime64(f"{year:04d}-{first_month:02d}-01") + np.timedelta64(d, "D"))
            assert str(expected) == row["date"], (year, d)

            for column, decimals in (("lat_1", 2), ("u_1", 1), ("lat_2", 2),
                                     ("u_2", 1), ("interjet_min", 1)):
                got, raw = season[column][d], row[column]
                blank = raw == "" or (isinstance(raw, float) and np.isnan(raw))
                # BOTH directions: a null that should be a number, and a number that should be a
                # null, each fail here. That is the assertion risk BR3 rests on.
                if blank:
                    assert got is None, (year, d, column, got)
                else:
                    assert got is not None, (year, d, column)
                    assert got == round(float(raw), decimals), (year, d, column, got, raw)


# --- B12.1: the round trip ------------------------------------------------------------------


def test_the_payload_round_trips_every_day_of_every_season(tmp_path):
    """§B12.1 (the brief's test): every day of every season, in both null directions."""
    _, out = build(tmp_path)
    payload = embedded(out / "explorer.html", "djet-data")
    assert_round_trip(payload, states_frame())


def test_the_payload_header_matches_the_configured_season(tmp_path):
    """§B12.1's second half. A **test** assertion, not a runtime gate.

    The payload is constructed from these very values, so comparing them at runtime would be
    tautological -- G3 is what actually proves the coordinate and the recorded sector agree. What
    this pins is that the module derives the month offsets the way `figure._month_ticks` does, from
    a non-leap reference year, and ships the sector's own endpoints rather than the mockup's.
    """
    _, out = build(tmp_path)
    payload = embedded(out / "explorer.html", "djet-data")

    assert payload["days_per_season"] == DAYS_PER_SEASON
    assert payload["lat_range"] == [LAT_MIN, LAT_MAX]
    assert payload["first_month"] == SEASON_MONTHS[0]
    assert payload["month_starts"] == [0, calendar.monthrange(2001, SEASON_MONTHS[0])[1]]
    assert payload["month_labels"] == [calendar.month_abbr[m] for m in SEASON_MONTHS]
    assert payload["state_codes"] == {"d": "double", "s": "single", "n": "none"}


def test_the_hydration_maps_null_to_nan(tmp_path):
    """§B12.1: the JS half, pinned as a string against silent deletion -- not a browser test.

    `isFinite(null)` is `true`, so a `null` passed through unmapped would draw a core at 0 °N
    (risk BR3). This asserts the statement is present *and* that it maps, rather than merely that
    the word `NaN` appears somewhere in the file.
    """
    _, out = build(tmp_path)
    html = (out / "explorer.html").read_text(encoding="utf-8")
    assert HYDRATION in html, "the null -> NaN hydration statement has gone"
    assert html.count(HYDRATION) == 1
    for field in ("lat1: num(", "u1: num(", "lat2: num(", "u2: num(", "inter: num("):
        assert field in html, f"{field} is not routed through the hydration map"


# --- B12.2: the summary table ---------------------------------------------------------------


def test_the_summary_recomputes_independently(tmp_path):
    """§B12.2 (the brief's test): all eight columns, row for row, against a separate pass."""
    _, out = build(tmp_path)
    written = pd.read_csv(out / "season_summary.csv")
    expected = _recompute_summary(states_frame())

    assert list(written.columns) == list(explorer.SUMMARY_COLUMNS)
    assert len(written) == len(SEASON_YEARS)
    assert written["year"].tolist() == sorted(written["year"].tolist())

    for column in ("year", "n_days", "n_double", "n_single", "n_none",
                   "n_double_runs", "longest_double_run"):
        assert written[column].tolist() == expected[column].tolist(), column

    # `pct_double` is written at four decimals, so the tolerance is half of the last digit.
    assert np.abs(written["pct_double"] - expected["pct_double"]).max() <= 5e-5
    assert np.abs(written["pct_double"]
                  - 100.0 * written["n_double"] / written["n_days"]).max() <= 5e-5
    assert (written["n_double"] + written["n_single"] + written["n_none"]
            == written["n_days"]).all()


def test_summary_and_embedded_json_agree(tmp_path):
    """The HTML and the table cannot drift: the counts are derived from the embedded strings."""
    _, out = build(tmp_path)
    written = pd.read_csv(out / "season_summary.csv")
    payload = embedded(out / "explorer.html", "djet-data")

    assert [int(s["year"]) for s in payload["seasons"]] == written["year"].tolist()
    for season, (_, row) in zip(payload["seasons"], written.iterrows()):
        assert season["state"].count("d") == row["n_double"]
        assert season["state"].count("s") == row["n_single"]
        assert season["state"].count("n") == row["n_none"]
        assert len(season["state"]) == row["n_days"]


# --- B12.3: the gates ------------------------------------------------------------------------


def test_a_short_season_fails_naming_it(tmp_path):
    """G1: a dropped day. A bare row count is what this proves the module does not use."""
    frame = states_frame()
    short = frame.drop(index=frame.index[10]).reset_index(drop=True)
    with pytest.raises(ValueError) as exc:
        build(tmp_path, frame=short)
    message = str(exc.value)
    assert str(YEAR_FIRST) in message
    assert str(DAYS_PER_SEASON - 1) in message


@pytest.mark.parametrize("attribute", explorer.REQUIRED_ATTRS)
def test_a_missing_attribute_fails_naming_it(tmp_path, attribute):
    """G4: every required attribute, one at a time, and the message names the one that is gone."""
    with pytest.raises(ValueError, match=re.escape(repr(attribute))):
        build(tmp_path, drop=attribute)


@pytest.mark.parametrize("attribute", explorer.JSON_ATTRS)
def test_an_unparseable_json_attribute_fails_naming_it(tmp_path, attribute):
    """G4's second half: present but not JSON is as fatal as absent, and names the attribute."""
    with pytest.raises(ValueError, match=re.escape(repr(attribute))):
        build(tmp_path, **{attribute: "not json at all"})


def test_a_profile_hash_mismatch_fails(tmp_path):
    """G2: the check `classify.py:343-352` performs, repeated here on purpose (§B9)."""
    with pytest.raises(ProfileMismatchError, match="profile hash check failed"):
        build(tmp_path, profile_sha256="0" * 64)


def test_a_resolution_disagreeing_with_the_latitude_axis_fails(tmp_path):
    """G3 (O6): the recorded resolution against the coordinate's own step, both values named."""
    cfg = make_cfg(tmp_path)
    sector = json.loads(intermediate_attrs(cfg)["sector"])
    sector["resolution"] = 1.0                       # the coordinate still steps by 0.5
    with pytest.raises(ValueError) as exc:
        build(tmp_path, cfg=cfg, sector=json.dumps(sector, sort_keys=True))
    message = str(exc.value)
    assert "1.0" in message and "0.5" in message


def test_a_shifted_latitude_axis_fails(tmp_path):
    """G3: right spacing, wrong endpoints. Spacing alone would accept this axis."""
    shifted = np.arange(LAT_MIN + 0.25, LAT_MAX + 0.25 + RESOLUTION / 2, RESOLUTION)
    with pytest.raises(ValueError, match="not the recorded sector's grid") as exc:
        build(tmp_path, lat=shifted)
    assert "first differing index 0" in str(exc.value)


def test_a_non_uniform_latitude_axis_fails(tmp_path):
    """G3: `profile.open_intermediate` verifies only dimension names, so this is checked here."""
    lat = np.array(list(np.arange(LAT_MIN, LAT_MAX + RESOLUTION / 2, RESOLUTION)))
    lat[7] += 0.1
    with pytest.raises(ValueError, match="uniformly spaced"):
        build(tmp_path, lat=lat)


@pytest.mark.parametrize("arm,target,state,column,value,needle", [
    ("core", 3, "single", "u_1", 14.0, "u_core_min"),
    ("separation", 0, "double", "lat_2", 32.0 + 9.0, "separation_min_deg"),
    ("prominence", 0, "double", "interjet_min", 19.0, "prominence_min"),
])
def test_each_threshold_arm_fails_alone(tmp_path, arm, target, state, column, value, needle):
    """G6, all three arms of `classify.py:124`, `:147` and `:153`. One arm tested is one proven.

    Each perturbation moves one row of one column and leaves the **other two arms satisfied**, so
    each failure is attributable rather than merely first past the post:

    * the core case lands on a `single` day, where the separation and prominence rules do not apply
      at all -- putting it on a `double` day would drag the prominence arm down with it, since
      `min(u_1, u_2) - 5` moves with the core;
    * the separation case sets `lat_2` 9° above the row's `lat_1` of 32.00, still far enough apart
      for the recorded minimum to be prominent;
    * the prominence case raises `interjet_min` above `min(u_1, u_2) - 5` while both cores stay
      over threshold and the cores stay 14° apart.
    """
    frame = states_frame()
    assert frame.loc[target, "state"] == state
    frame.loc[target, column] = f"{value:.10f}"

    with pytest.raises(ValueError) as exc:
        build(tmp_path, frame=frame)
    message = str(exc.value)
    assert needle in message, message
    assert frame.loc[target, "date"] in message, message
    # the arm that fired is the one perturbed, not a second one knocked over by the same edit
    for other in {"u_core_min", "separation_min_deg", "prominence_min"} - {needle}:
        assert other not in message, f"{arm} also tripped {other}: {message}"


def test_a_reordered_or_duplicated_date_fails(tmp_path):
    """G1: order and uniqueness, not just the count -- every index downstream is positional."""
    frame = states_frame()
    swapped = frame.copy()
    swapped.loc[[3, 4], "date"] = frame.loc[[4, 3], "date"].to_numpy()
    with pytest.raises(ValueError) as exc:
        build(tmp_path, frame=swapped)
    assert str(YEAR_FIRST) in str(exc.value)
    assert "ascending" in str(exc.value) or frame.loc[3, "date"] in str(exc.value)

    duplicated = frame.copy()
    duplicated.loc[4, "date"] = duplicated.loc[3, "date"]
    with pytest.raises(ValueError) as exc:
        build(tmp_path, frame=duplicated)
    assert str(YEAR_FIRST) in str(exc.value)
    assert "duplicate" in str(exc.value)


def test_a_season_of_the_wrong_dates_fails(tmp_path):
    """G1's last arm: the right *number* of ascending, unique days that are the wrong days.

    August + September 2002 is also 61 days, so a count check passes, an order check passes and a
    uniqueness check passes. Only comparing against the configured season's own date vector catches
    it -- and it must, because every day index, tooltip and run length downstream is positional.
    """
    frame = states_frame()
    wrong = [f"2002-{month:02d}-{day:02d}"
             for month in (8, 9)
             for day in range(1, calendar.monthrange(2002, month)[1] + 1)]
    assert len(wrong) == DAYS_PER_SEASON
    rows = frame.index[frame["date"].str.startswith("2002")]
    frame.loc[rows, "date"] = wrong

    with pytest.raises(ValueError) as exc:
        build(tmp_path, frame=frame)
    message = str(exc.value)
    assert "2002" in message
    assert "2002-08-01" in message, message           # the first differing date, named


def test_a_markup_character_in_the_payload_cannot_leave_the_script_tag(tmp_path):
    """Risk BR6: `<` is escaped at insertion, so no attribute value can terminate the element.

    The synthetic payload holds no `<` of its own, which is exactly why this test supplies one:
    without it, dropping the escape is invisible. `source_dataset` reaches `djet-meta` through the
    method block's Data row, so a dataset id is a real path for hostile text to arrive on.
    """
    hostile = "ds633.0</script><script>alert(1)</script>"
    _, out = build(tmp_path, source_dataset=hostile)
    text = (out / "explorer.html").read_text(encoding="utf-8")

    block = re.search(r'<script id="djet-meta" type="application/json">(.*?)</script>',
                      text, re.S).group(1)
    assert "</script>" not in block
    assert "<" not in block
    assert block.count("\\u003c") == hostile.count("<"), "the '<' escaping has gone (BR6)"
    # and it still round-trips: escaped, not mangled
    assert json.loads(block)["method"][0][1][0] == f"ERA5, NCAR RDA {hostile}"
    # exactly the two payload blocks and the one code block, not four
    assert text.count("<script") == 3


@pytest.mark.parametrize("mutate,needle", [
    (lambda f: f.drop(columns=["interjet_min"]), "interjet_min"),
    (lambda f: f.assign(extra=1.0), "extra"),
    (lambda f: _set(f, 3, {"lat_2": "44.00"}), "lat_2"),
    (lambda f: _set(f, 0, {"interjet_min": ""}), "interjet_min"),
    (lambda f: _set(f, 4, {"lat_1": "40.00"}), "lat_1"),
    (lambda f: _set(f, 3, {"u_1": ""}), "u_1"),
    (lambda f: _set(f, 0, {"state": "triple"}), "triple"),
])
def test_malformed_csv_shapes_fail(tmp_path, mutate, needle):
    """G7 (a missing and an extra column) and G8 (each arm of the state/null contract).

    Rows 0 and 3 and 4 of the fixture are a `double`, a `single` and a `none` day respectively, so
    the six G8 cases are: a `single` carrying `lat_2`, a `double` missing `interjet_min`, a `none`
    carrying `lat_1`, a `single` missing `u_1`, and a state name the classifier never writes.
    """
    with pytest.raises(ValueError, match=re.escape(needle)):
        build(tmp_path, frame=mutate(states_frame()))


def _set(frame: pd.DataFrame, row: int, values: dict) -> pd.DataFrame:
    frame = frame.copy()
    for column, value in values.items():
        frame.loc[row, column] = value
    return frame


def test_the_csv_seasons_must_match_the_recorded_years(tmp_path):
    """G5: the symmetric difference is in the message, so the operator sees *which* season."""
    cfg = make_cfg(tmp_path)
    with pytest.raises(ValueError, match="symmetric difference"):
        build(tmp_path, cfg=cfg, years=json.dumps([YEAR_FIRST, YEAR_LAST, 2099]))


def test_a_non_consecutive_season_fails(tmp_path):
    """G5: the day-of-season index assumes one unbroken run of whole months."""
    with pytest.raises(ValueError, match="not consecutive"):
        build(tmp_path, season_months=json.dumps([6, 8]))


# --- B12.3: the artifact's own properties ----------------------------------------------------


def test_method_block_is_config_driven_not_literal(tmp_path):
    """Change a threshold and a level; the new values appear and the frozen ones do not.

    This is the assertion behind the brief's "no string literal for a measured value": a method
    block hard-coded from the mockup would still read `15` and `250 hPa` here.
    """
    cfg = make_cfg(tmp_path, pressure_level=500,
                   detection={"u_core_min": 17.0, "separation_min_deg": SEPARATION_MIN,
                              "prominence_min": PROMINENCE_MIN,
                              "smooth_window_deg": SMOOTH_WINDOW_DEG})
    _, out = build(tmp_path, cfg=cfg)
    parts = [part for _, group in embedded(out / "explorer.html", "djet-meta")["method"]
             for part in group]

    assert "core u ≥ 17 m s⁻¹" in parts
    assert "core u ≥ 15 m s⁻¹" not in parts
    assert any(p.endswith("at 500 hPa") for p in parts)
    assert not any(p.endswith("at 250 hPa") for p in parts)

    # and the rest of §B6's rows are read, not written
    assert f"{RESOLUTION:g}° grid" in parts
    assert "15°W–20°E zonal mean" in parts
    assert f"{LAT_MIN:g}–{LAT_MAX:g}°N" in parts
    assert f"June–July, {YEAR_FIRST}–{YEAR_LAST}" in parts
    assert "daily mean of the 00, 06, 12, 18 UTC analyses" in parts
    assert f"share of the season's {DAYS_PER_SEASON} days classified double jet" in parts


def test_the_html_has_no_external_references(tmp_path):
    """§B3: it must open from `file://` with no network access and no external scripts."""
    _, out = build(tmp_path)
    html = (out / "explorer.html").read_text(encoding="utf-8")
    for pattern in ("http://", "https://", "<link", "@import", "src="):
        assert pattern not in html, f"{pattern!r} is in the generated explorer"


def test_the_embedded_json_is_valid_and_finite(tmp_path):
    """G9 and risk BR6: both blocks parse, nothing non-finite, nothing that can leave the tag."""
    _, out = build(tmp_path)
    text = (out / "explorer.html").read_text(encoding="utf-8")
    for block in ("djet-data", "djet-meta"):
        raw = re.search(rf'<script id="{block}" type="application/json">(.*?)</script>',
                        text, re.S).group(1)
        json.loads(raw)
        assert "</script>" not in raw
        assert "<" not in raw, "an unescaped '<' can terminate the script element (BR6)"
        assert not re.search(r"(?<![\"\w])(NaN|Infinity|-Infinity)(?![\"\w])", raw)


def test_an_infinity_raises_rather_than_becoming_a_blank(tmp_path):
    """G9: `NaN` is mapped to `null` at build time, so a non-finite left over is a real defect."""
    frame = states_frame()
    frame.loc[3, "u_1"] = "inf"                      # a `single` day, so G6's arms still pass
    with pytest.raises(ValueError, match="JSON cannot represent"):
        build(tmp_path, frame=frame)


def test_the_annual_png_is_written(tmp_path):
    """§B8: the file exists, is a PNG by its magic bytes, and is not a blank canvas."""
    _, out = build(tmp_path)
    png = out / "annual.png"
    assert png.exists()
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert png.stat().st_size > 5_000


def test_the_summary_is_written_before_the_png(tmp_path, monkeypatch):
    """§B7/§B8: the chart is rendered *from* the table, so "the same numbers" is literal.

    The renderer is intercepted rather than inspected after the fact. At the moment it is called
    the summary file must already be on disk and already hold the finished table -- which is what
    makes "same numbers by construction" a statement about the code path and not an argument. A
    build that computed the percentages a second time for the chart would pass a mtime check and
    fail this one.
    """
    seen: dict = {}
    real = explorer._render_annual_png

    def spy(summary_path, annual_path, title, log):
        seen["summary_path"] = Path(summary_path)
        seen["table"] = pd.read_csv(summary_path)    # read at call time, not afterwards
        return real(summary_path, annual_path, title, log)

    monkeypatch.setattr(explorer, "_render_annual_png", spy)
    _, out = build(tmp_path)

    assert seen["summary_path"] == out / "season_summary.csv"
    pd.testing.assert_frame_equal(seen["table"], pd.read_csv(out / "season_summary.csv"))
    pd.testing.assert_frame_equal(
        seen["table"][["year", "n_double", "n_days"]],
        _recompute_summary(states_frame())[["year", "n_double", "n_days"]])


# --- B12.3: the real artifacts ---------------------------------------------------------------

REAL_CSV = REPO_ROOT / "data" / "jet_states_mjjas_1979-2025.csv"
REAL_PROFILE = REPO_ROOT / "data" / "u250_natl_mjjas_1979-2025.nc"
REAL_CONFIG = REPO_ROOT / "configs" / "double_jet.yaml"


@pytest.mark.skipif(not (REAL_CSV.exists() and REAL_PROFILE.exists()),
                    reason="the campaign artifacts are gitignored; this runs where they exist")
def test_against_the_real_artifacts(tmp_path, monkeypatch):
    """§B12.1 + §B12.2 against the deliverable itself, not merely its synthetic analogue.

    `data/` is gitignored, so a fresh clone skips this; on the machine that ran the campaign it is
    the only test that proves the artifact the operator opens is the one the suite describes.
    """
    monkeypatch.setenv("SCRATCH", str(tmp_path / "scratch"))
    cfg = load_config(REAL_CONFIG)
    out = tmp_path / "real"
    out.mkdir()
    explorer.run_explorer(cfg, REAL_PROFILE, REAL_CSV, out / "explorer.html",
                          out / "season_summary.csv", out / "annual.png", log=_Log())

    frame = pd.read_csv(REAL_CSV, dtype=str).fillna("")
    assert_round_trip(embedded(out / "explorer.html", "djet-data"), frame)

    written = pd.read_csv(out / "season_summary.csv")
    expected = _recompute_summary(pd.read_csv(REAL_CSV))
    for column in ("year", "n_days", "n_double", "n_single", "n_none",
                   "n_double_runs", "longest_double_run"):
        assert written[column].tolist() == expected[column].tolist(), column
    assert np.abs(written["pct_double"] - expected["pct_double"]).max() <= 5e-5

    # the frozen contract: 47 seasons of 153 days, and `data/jet_states_summary.txt`'s totals
    assert len(written) == 47
    assert set(written["n_days"]) == {153}
    assert written["n_double"].sum() == 3246
    assert written["n_single"].sum() == 3932
    assert written["n_none"].sum() == 13
