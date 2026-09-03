"""Classification tests: synthetic latitude profiles whose answers are known (plan §4.6).

Every case §4.6 names is here, and each one isolates exactly one rule so a failure says which rule
broke:

* one Gaussian -> `single`
* two Gaussians 20 deg apart over a deep trough -> `double`, at the expected core latitudes
* the same pair 8 deg apart -> `single` (the separation rule, and only that rule)
* the same pair 20 deg apart over a ~3 m/s trough -> `single` (the prominence rule, and only that)
* a flat 10 m/s profile -> `none`
* three cores whose strongest pair fails separation while another pair passes -> `double` on the
  right pair, which is what pins I4's ordering
* a monotone ramp to the domain edge -> no core at the edge (I3, risk R7)
* an above-threshold exact flat top -> one core at the plateau midpoint (I3's lock-in)

plus the boxcar's end behaviour (I2), the window's 11-point resolution on the real config (I1), and
the two sanity behaviours the operator ruled on: the double-jet fraction gates, the core-latitude
diagnostic does not (R2).

The profiles are handed to `classify_day` unsmoothed on purpose: its argument is *already* a smoothed
profile, and analytic Gaussians are smooth. `smooth` is tested separately.
"""

from __future__ import annotations

import dataclasses
import logging
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr
from scipy.signal import find_peaks

from double_jet import profile as profile_module
from double_jet.classify import (
    CSV_COLUMNS,
    ProfileMismatchError,
    classify_all,
    classify_day,
    find_cores,
    run_classify,
    sanity_report,
    smooth,
)
from double_jet.config import Detection, load_config

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "configs" / "double_jet.yaml"

# The contract's thresholds, restated here so a test failure is traceable to one number. They are
# asserted against the real config below, so this block cannot silently drift from it.
DETECTION = Detection(
    u_core_min=15.0, separation_min_deg=10.0, prominence_min=5.0, smooth_window_deg=2.5
)

LOG = logging.getLogger("test_classify")


@pytest.fixture(scope="session")
def cfg():
    # The config expands $SCRATCH; supply a stand-in if the test host has none, since none of these
    # tests touch the raw cache.
    os.environ.setdefault("SCRATCH", tempfile.gettempdir())
    return load_config(CONFIG_PATH)


@pytest.fixture
def lat() -> np.ndarray:
    """The real 221-point sector axis, 20-75 N at 0.25 deg."""
    return np.arange(20.0, 75.0 + 1e-9, 0.25)


CORE_SIGMA = 1.5      # deg; narrow enough that even a pair 8 deg apart stays two resolved maxima


def gaussian(lat: np.ndarray, center: float, amplitude: float, sigma: float) -> np.ndarray:
    return amplitude * np.exp(-0.5 * ((lat - center) / sigma) ** 2)


def jet_pair(lat: np.ndarray, south: float, north: float) -> np.ndarray:
    """The §4.6 pair: a 30 m/s southern core and a 25 m/s northern one, over a deep trough.

    The same two Gaussians are used at 20 deg and at 8 deg apart, so only the separation changes
    between those two cases.
    """
    return gaussian(lat, south, 30.0, CORE_SIGMA) + gaussian(lat, north, 25.0, CORE_SIGMA)


def test_detection_constants_match_the_shipped_config(cfg):
    """Guard against this file's thresholds drifting away from configs/double_jet.yaml."""
    assert cfg.detection == DETECTION


# --------------------------------------------------------------------------------------------
# §4.6 core cases
# --------------------------------------------------------------------------------------------

def test_one_gaussian_is_single(lat):
    u = gaussian(lat, 45.0, 30.0, 4.0)

    day = classify_day(u, lat, DETECTION)

    assert day["state"] == "single"
    assert day["lat_1"] == pytest.approx(45.0)
    assert day["u_1"] == pytest.approx(30.0)
    # A single day leaves the second core and the interjet minimum blank (plan §4.3 step 3).
    assert day["lat_2"] is None and day["u_2"] is None and day["interjet_min"] is None


def test_two_gaussians_20deg_apart_over_a_deep_trough_are_double(lat):
    u = jet_pair(lat, 40.0, 60.0)

    day = classify_day(u, lat, DETECTION)

    assert day["state"] == "double"
    # Recorded south to north, not by strength: lat_1 is the southern core even though both here
    # happen to agree, and u_1 is its wind.
    assert day["lat_1"] == pytest.approx(40.0)
    assert day["u_1"] == pytest.approx(30.0)
    assert day["lat_2"] == pytest.approx(60.0)
    assert day["u_2"] == pytest.approx(25.0)
    # The trough between two narrow Gaussians 20 deg apart is essentially zero, far below the
    # weaker core minus 5 m/s.
    assert day["interjet_min"] < 1.0


def test_the_same_pair_8deg_apart_is_single_by_the_separation_rule(lat):
    u = jet_pair(lat, 46.0, 54.0)         # the same two cores, moved to 8 deg apart

    cores = find_cores(u, lat, DETECTION.u_core_min)
    assert len(cores) == 2, "the two maxima must still be resolved; only separation may fail"
    south, north = cores
    trough = u[south[0] + 1:north[0]].min()
    # The prominence rule is comfortably satisfied here, so `single` can only come from separation.
    assert trough <= min(south[2], north[2]) - DETECTION.prominence_min
    assert north[1] - south[1] < DETECTION.separation_min_deg

    day = classify_day(u, lat, DETECTION)

    assert day["state"] == "single"
    assert day["lat_1"] == pytest.approx(46.0)      # the stronger of the two
    assert day["u_1"] == pytest.approx(30.0)
    assert day["lat_2"] is None and day["interjet_min"] is None


def test_the_same_pair_20deg_apart_with_a_3ms_trough_is_single_by_the_prominence_rule(lat):
    # Same 20 deg geometry, but broad Gaussians: the two maxima stay resolved and well separated,
    # while the valley between them only sinks a few m/s below the weaker core. A shallow trough is
    # necessarily a different profile shape, so this is the one case that cannot reuse `jet_pair`.
    u = gaussian(lat, 40.0, 24.0, 7.8) + gaussian(lat, 60.0, 22.0, 7.8)

    cores = find_cores(u, lat, DETECTION.u_core_min)
    assert len(cores) == 2
    south, north = cores
    depth = min(south[2], north[2]) - u[south[0] + 1:north[0]].min()
    # Separation passes, so `single` can only come from the prominence rule.
    assert north[1] - south[1] >= DETECTION.separation_min_deg
    assert 2.0 < depth < DETECTION.prominence_min, f"trough depth {depth:.2f} m/s"

    assert classify_day(u, lat, DETECTION)["state"] == "single"


def test_a_flat_10ms_profile_has_no_core(lat):
    u = np.full(lat.size, 10.0)

    assert find_cores(u, lat, DETECTION.u_core_min) == []

    day = classify_day(u, lat, DETECTION)
    assert day["state"] == "none"
    assert all(day[column] is None for column in CSV_COLUMNS[2:])


def test_three_cores_pick_the_pair_that_passes_not_the_strongest_pair(lat):
    """I4's ordering: the strongest core pairs with its strongest *valid* partner.

    Cores at 35 N (40 m/s), 40 N (35 m/s) and 60 N (30 m/s). A naive "keep the two strongest" would
    take 35 N + 40 N, which are 5 deg apart and would make the day `single`. The plan's rule scans
    pairs by descending strength and accepts the first that passes both tests, which is 35 N + 60 N.
    """
    u = (gaussian(lat, 35.0, 40.0, 1.5)
         + gaussian(lat, 40.0, 35.0, 1.5)
         + gaussian(lat, 60.0, 30.0, 1.5))

    cores = find_cores(u, lat, DETECTION.u_core_min)
    assert [round(core[1], 2) for core in cores] == [35.0, 40.0, 60.0]
    # The two strongest cores really are the ones that fail separation.
    assert 40.0 - 35.0 < DETECTION.separation_min_deg

    day = classify_day(u, lat, DETECTION)

    assert day["state"] == "double"
    assert day["lat_1"] == pytest.approx(35.0)
    assert day["u_1"] == pytest.approx(40.0, abs=0.2)
    assert day["lat_2"] == pytest.approx(60.0)
    assert day["u_2"] == pytest.approx(30.0, abs=0.2)


def test_a_monotone_ramp_has_no_core_at_the_domain_edge(lat):
    """I3 / risk R7: the endpoints are unrepresentable as cores, by construction and on purpose."""
    u = np.linspace(10.0, 35.0, lat.size)

    # The profile's maximum is at the northern boundary and is far above the 15 m/s threshold, so
    # nothing but the endpoint exclusion can be keeping it out of the core list.
    assert u.argmax() == lat.size - 1 and u[-1] > DETECTION.u_core_min

    assert find_cores(u, lat, DETECTION.u_core_min) == []
    assert classify_day(u, lat, DETECTION)["state"] == "none"


def test_an_exact_flat_top_gives_one_core_at_the_plateau_midpoint(lat):
    """I3's lock-in: `find_peaks` at its DEFAULTS locates a flat-topped core at its midpoint.

    Tightening to `plateau_size=(None, 1)` looks like a stricter reading of "local maximum" but on
    scipy 1.17.1 it returns *nothing* for this profile -- it would DISCARD the core rather than
    locate it. The second assertion below states that behaviour explicitly, so anyone who adds
    `plateau_size` (or any other narrowing argument) to `find_cores` fails this test instead of
    silently dropping cores from the archive.
    """
    u = np.full(lat.size, 10.0)
    u[97:108] = [12.0, 14.0, 17.0, 20.0, 25.0, 25.0, 25.0, 20.0, 17.0, 14.0, 12.0]
    midpoint = 102                  # middle sample of the three-wide plateau at indices 101-103

    cores = find_cores(u, lat, DETECTION.u_core_min)

    assert len(cores) == 1
    assert cores[0] == (midpoint, pytest.approx(lat[midpoint]), pytest.approx(25.0))
    assert find_peaks(u)[0].tolist() == [midpoint]
    assert find_peaks(u, plateau_size=(None, 1))[0].size == 0, (
        "scipy discards flat-topped maxima under plateau_size; I3 keeps the defaults for this reason"
    )

    assert classify_day(u, lat, DETECTION)["state"] == "single"


# --------------------------------------------------------------------------------------------
# smooth: I1 (11 points) and I2 (truncated, renormalized ends)
# --------------------------------------------------------------------------------------------

def test_smooth_preserves_a_constant_field_exactly_including_the_domain_ends(lat):
    """I2: the truncated window is renormalized. Zero padding would pull the two ends down."""
    u = np.full(lat.size, 7.0)

    smoothed = smooth(u, 11)

    np.testing.assert_allclose(smoothed, 7.0, rtol=0.0, atol=1e-12)
    assert smoothed[0] == pytest.approx(7.0, abs=1e-12)
    assert smoothed[-1] == pytest.approx(7.0, abs=1e-12)


def test_smooth_divides_by_the_number_of_samples_inside_the_domain():
    u = np.arange(20.0, dtype=float)

    smoothed = smooth(u, 11)

    # First sample: only indices 0-5 lie inside the domain, so the divisor is 6, not 11.
    assert smoothed[0] == pytest.approx(u[:6].mean())
    assert smoothed[1] == pytest.approx(u[:7].mean())
    # Last sample: indices 14-19, divisor 6 again.
    assert smoothed[-1] == pytest.approx(u[-6:].mean())
    # An interior sample uses the full 11-point window.
    assert smoothed[10] == pytest.approx(u[5:16].mean())


def test_smooth_handles_a_2d_stack_row_by_row(lat):
    """figure.py smooths the whole (n_time, n_lat) stack; it must equal per-day smoothing."""
    rng = np.random.default_rng(0)
    stack = rng.normal(25.0, 5.0, size=(4, lat.size))

    smoothed = smooth(stack, 11)

    assert smoothed.shape == stack.shape
    for row, expected in zip(smoothed, (smooth(day, 11) for day in stack)):
        np.testing.assert_allclose(row, expected)


def test_smooth_rejects_a_window_it_cannot_center():
    with pytest.raises(ValueError, match="odd"):
        smooth(np.zeros(10), 10)


def test_the_boxcar_window_resolves_to_eleven_points_on_the_real_config(cfg):
    """I1: 2.5 deg at 0.25 deg is 11 samples, the only centerable choice."""
    assert cfg.smooth_window_points == 11


# --------------------------------------------------------------------------------------------
# classify_all: the CSV's shape
# --------------------------------------------------------------------------------------------

def test_classify_all_yields_the_contract_columns_and_iso_dates(lat, tmp_path):
    double_day = gaussian(lat, 40.0, 30.0, 3.0) + gaussian(lat, 60.0, 25.0, 3.0)
    single_day = gaussian(lat, 45.0, 30.0, 4.0)
    none_day = np.full(lat.size, 10.0)
    times = pd.to_datetime(["2018-05-01", "2018-05-02", "2018-05-03"])

    df = classify_all(np.vstack([double_day, single_day, none_day]), lat, DETECTION, times)

    assert list(df.columns) == list(CSV_COLUMNS)
    assert df["date"].tolist() == ["2018-05-01", "2018-05-02", "2018-05-03"]
    assert df["state"].tolist() == ["double", "single", "none"]

    csv_path = tmp_path / "states.csv"
    df.to_csv(csv_path, index=False)
    rows = csv_path.read_text().splitlines()
    assert rows[0] == ",".join(CSV_COLUMNS)
    # Blank core columns must be empty fields, not "None" or "nan" (contract, plan §4.3 step 4).
    assert rows[2].split(",")[4:] == ["", "", ""]
    assert rows[3].split(",")[2:] == ["", "", "", "", ""]


# --------------------------------------------------------------------------------------------
# sanity_report: one gate, two diagnostics (§4.4, ruling R2, I5)
# --------------------------------------------------------------------------------------------

def _frame(states: list[str], lat_1: float = 45.0, lat_2: float = 60.0) -> pd.DataFrame:
    """A minimal states frame: `double` rows carry two cores, `single` one, `none` none."""
    dates = pd.date_range("2018-05-01", periods=len(states)).strftime("%Y-%m-%d")
    rows = []
    for date, state in zip(dates, states):
        if state == "double":
            rows.append((date, state, lat_1, 30.0, lat_2, 25.0, 8.0))
        elif state == "single":
            rows.append((date, state, lat_1, 30.0, None, None, None))
        else:
            rows.append((date, state, None, None, None, None, None))
    df = pd.DataFrame(rows, columns=list(CSV_COLUMNS))
    for column in CSV_COLUMNS[2:]:
        df[column] = df[column].astype("float64")
    return df


def _dummy_stack(n_days: int, lat: np.ndarray) -> np.ndarray:
    return np.zeros((n_days, lat.size))


def test_sanity_report_fails_when_the_double_jet_fraction_is_out_of_band(cfg, lat):
    """The one hard gate in §4.4: outside 5-90 %, `ok` is False and cli exits EXIT_SANITY."""
    df = _frame(["single"] * 20)          # 0 % double, below the 5 % floor

    result = sanity_report(cfg, df, _dummy_stack(len(df), lat), lat, smoke=False)

    assert result.ok is False
    assert result.stats["double_fraction"] == pytest.approx(0.0)
    assert "FAIL" in result.text
    # Every core sits inside 25-70 N, so nothing but the fraction can be failing.
    assert result.stats["core_lat_fraction"] == pytest.approx(1.0)


def test_sanity_report_passes_when_the_double_jet_fraction_is_in_band(cfg, lat):
    df = _frame(["double"] * 10 + ["single"] * 10)

    result = sanity_report(cfg, df, _dummy_stack(len(df), lat), lat, smoke=False)

    assert result.ok is True
    assert result.stats["double_fraction"] == pytest.approx(0.5)
    assert "PASS" in result.text


def test_sanity_report_reports_but_never_gates_on_core_latitudes(cfg, lat):
    """Operator ruling R2: the 25-70 N check is reported, the run finishes, no band is moved."""
    # Cores at 23 N and 73 N: exactly the subtropical/polar misses the §1.7 probe found. All 20 are
    # out of band, so the diagnostic misses its 95 % target by the widest possible margin.
    df = _frame(["double"] * 10 + ["single"] * 10, lat_1=23.0, lat_2=73.0)

    result = sanity_report(cfg, df, _dummy_stack(len(df), lat), lat, smoke=False)

    assert result.stats["core_lat_fraction"] == pytest.approx(0.0)
    assert result.stats["n_cores_out_of_band"] == result.stats["n_cores"] == 30
    assert result.ok is True, "R2: the core-latitude diagnostic must never set ok=False"
    # The band and the target are printed verbatim, and the worst offenders are named with dates.
    assert "25-70 N" in result.text and "95 %" in result.text
    assert "REPORTED, NOT A GATE" in result.text
    assert result.stats["core_lat_worst"][0][0].startswith("2018-05-")
    # The band itself is untouched.
    assert (cfg.sanity.core_lat_min, cfg.sanity.core_lat_max) == (25.0, 70.0)


def test_sanity_report_bands_are_read_from_the_config_not_hard_coded(cfg, lat):
    """A 40 % double fraction passes the shipped 5-90 % band and fails a narrowed one."""
    df = _frame(["double"] * 4 + ["single"] * 6)
    stack = _dummy_stack(len(df), lat)
    narrowed = dataclasses.replace(
        cfg, sanity=dataclasses.replace(cfg.sanity, double_fraction_max=0.30)
    )

    assert sanity_report(cfg, df, stack, lat, smoke=False).ok is True
    assert sanity_report(narrowed, df, stack, lat, smoke=False).ok is False


def test_smoke_block_reports_the_season_median_peak_and_never_gates(cfg, lat):
    """I5: 'peak 20-40 m/s' is the season median of the daily maximum, printed, not enforced."""
    df = _frame(["double"] * 5 + ["single"] * 5)
    stack = np.zeros((len(df), lat.size))
    # Daily maxima whose MEDIAN lands inside the configured 20-40 band while the smallest and the
    # largest day sit far outside it: I5 reads the check as the season median, not the extremes.
    stack[:, 100] = [10.0, 12.0, 14.0, 16.0, 18.0, 60.0, 62.0, 64.0, 66.0, 68.0]

    result = sanity_report(cfg, df, stack, lat, smoke=True)

    assert result.stats["smoke_peak_median"] == pytest.approx(39.0)
    assert result.stats["smoke_peak_min"] == pytest.approx(10.0)
    assert result.stats["smoke_peak_max"] == pytest.approx(68.0)
    assert "median 39.00" in result.text
    assert result.ok is True

    # And a season whose median is far outside the band is reported, not gated.
    implausible = sanity_report(cfg, df, stack + 50.0, lat, smoke=True)
    assert implausible.stats["smoke_peak_median"] == pytest.approx(89.0)
    assert implausible.ok is True
    assert "never a gate" in implausible.text


# --------------------------------------------------------------------------------------------
# run_classify: the profile-hash guard (§4.3) and the two output files
# --------------------------------------------------------------------------------------------

def _intermediate(lat: np.ndarray, profile_sha256: str) -> xr.Dataset:
    """A stand-in for `profile.open_intermediate`'s return value: U(time, latitude) plus attrs."""
    double_day = gaussian(lat, 40.0, 30.0, 3.0) + gaussian(lat, 60.0, 25.0, 3.0)
    single_day = gaussian(lat, 45.0, 30.0, 4.0)
    stack = np.vstack([double_day] * 6 + [single_day] * 4).astype("float32")
    return xr.Dataset(
        {"U": (("time", "latitude"), stack)},
        coords={"time": pd.date_range("2018-05-01", periods=stack.shape[0]), "latitude": lat},
        attrs={"profile_sha256": profile_sha256},
    )


@pytest.fixture
def fake_intermediate(monkeypatch, lat):
    """Route `run_classify` at an in-memory dataset; profile.py's own I/O is agent B's to test."""
    def install(profile_sha256: str) -> None:
        monkeypatch.setattr(
            profile_module, "open_intermediate",
            lambda path: _intermediate(lat, profile_sha256), raising=False,
        )
    return install


def test_run_classify_rejects_an_intermediate_built_from_another_config(cfg, tmp_path,
                                                                       fake_intermediate):
    """§4.3's silent-failure guard: a stale intermediate must stop the run, not be classified."""
    fake_intermediate("0" * 64)

    with pytest.raises(ProfileMismatchError) as excinfo:
        run_classify(cfg, tmp_path / "profile.nc", tmp_path / "states.csv",
                     tmp_path / "summary.txt", smoke=False, log=LOG)

    message = str(excinfo.value)
    assert "0" * 64 in message and cfg.profile_sha256 in message
    assert not (tmp_path / "states.csv").exists()


def test_run_classify_accepts_a_threshold_change_against_the_same_intermediate(cfg, tmp_path,
                                                                              fake_intermediate):
    """Detection thresholds are outside the profile hash, so re-running with a new one must work."""
    fake_intermediate(cfg.profile_sha256)
    retuned = dataclasses.replace(
        cfg, detection=dataclasses.replace(cfg.detection, u_core_min=20.0)
    )
    assert retuned.profile_sha256 == cfg.profile_sha256

    result = run_classify(retuned, tmp_path / "profile.nc", tmp_path / "states.csv",
                          tmp_path / "summary.txt", smoke=False, log=LOG)

    assert result.stats["n_days"] == 10


def test_run_classify_writes_the_csv_and_the_summary(cfg, tmp_path, fake_intermediate):
    fake_intermediate(cfg.profile_sha256)
    csv_path, summary_path = tmp_path / "states.csv", tmp_path / "summary.txt"

    result = run_classify(cfg, tmp_path / "profile.nc", csv_path, summary_path,
                          smoke=True, log=LOG)

    df = pd.read_csv(csv_path)
    assert list(df.columns) == list(CSV_COLUMNS)
    assert len(df) == 10
    assert df["state"].value_counts().to_dict() == {"double": 6, "single": 4}
    assert result.ok is True
    assert result.stats["double_fraction"] == pytest.approx(0.6)
    assert summary_path.read_text() == result.text
    assert "smoke profile" in result.text          # the I5 block, requested by smoke=True
