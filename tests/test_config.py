"""Config round-trip, sector arithmetic, output naming and the two hashes (plan §4.6, R12).

`configs/double_jet.yaml` is the frozen config block: every number asserted here is a contract
value, so this file is the tripwire that fires if one of them is edited without an escalation
(plan §11).

`cfg.paths.scratch_raw` expands `$SCRATCH`, and `load_config` raises `ConfigError` by design when
that variable is unset. Every test that loads a config therefore pins `$SCRATCH` with
`monkeypatch.setenv`, so the suite does not depend on the shell it was launched from.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:                      # `pytest tests/` from any cwd
    sys.path.insert(0, str(REPO_ROOT))

from double_jet import cli                              # noqa: E402
from double_jet.config import ConfigError, load_config  # noqa: E402

CONFIG_PATH = REPO_ROOT / "configs" / "double_jet.yaml"

# The wave prompt's deliverable names, reproduced as literals. Only the full campaign may use
# them (plan §4.2's table); asserting them by literal is the point -- deriving them from the code
# under test would assert nothing.
CONTRACT_NAMES = {
    Path("data/u250_natl_mjjas_1979-2025.nc"),
    Path("data/jet_states_mjjas_1979-2025.csv"),
    Path("data/jet_states_summary.txt"),
    Path("figs/double_jet_natl_panels.pdf"),
    Path("figs/double_jet_natl_panels.png"),
    # The explorer addendum's three (§B12.4). `results/season_summary.csv` is the first contract
    # name outside `data/`/`figs/`; it is a *relative* literal because `output_names` anchors it
    # relatively, exactly as it anchors the configured `data_dir`/`figs_dir` (§B10 item 2).
    Path("results/season_summary.csv"),
    Path("figs/double_jet_natl_explorer.html"),
    Path("figs/double_jet_natl_annual.png"),
}


@pytest.fixture
def scratch(monkeypatch, tmp_path):
    """Pin `$SCRATCH` so `paths.scratch_raw` expands identically regardless of the shell."""
    root = tmp_path / "scratch"
    monkeypatch.setenv("SCRATCH", str(root))
    return root


@pytest.fixture
def cfg(scratch):
    return load_config(CONFIG_PATH)


def _variant(tmp_path: Path, name: str, old: str, new: str) -> Path:
    """A copy of the frozen YAML differing from it in exactly one value, and nothing else.

    The single-occurrence assertion is what makes the resulting `config_sha256` comparison
    meaningful: the two files differ in one number, not in whitespace or key order.
    """
    text = CONFIG_PATH.read_text()
    assert text.count(old) == 1, f"{old!r} is not a unique anchor in {CONFIG_PATH}"
    path = tmp_path / name
    path.write_text(text.replace(old, new))
    return path


# --- the YAML round-trips into the dataclass ---------------------------------------------------

def test_yaml_round_trips_to_the_contract_numbers(cfg):
    assert cfg.dataset == "derived-era5-pressure-levels-daily-statistics"
    assert cfg.variable == "u_component_of_wind"
    assert cfg.pressure_level == 250

    assert (cfg.sector.lat_min, cfg.sector.lat_max) == (20.0, 75.0)
    assert (cfg.sector.lon_min, cfg.sector.lon_max) == (-60.0, 30.0)
    assert cfg.sector.resolution == 0.25

    assert cfg.season_months == (5, 6, 7, 8, 9)                 # MJJAS
    assert cfg.month_strings() == ["05", "06", "07", "08", "09"]
    assert (cfg.year_first, cfg.year_last) == (1979, 2025)
    assert cfg.years == tuple(range(1979, 2026))
    assert cfg.n_seasons == 47
    assert cfg.days_per_season == 153
    assert cfg.n_days == 7191
    assert cfg.smoke_year == 2018

    d = cfg.detection
    assert (d.u_core_min, d.separation_min_deg, d.prominence_min, d.smooth_window_deg) == (
        15.0, 10.0, 5.0, 2.5)

    s = cfg.sanity
    assert (s.double_fraction_min, s.double_fraction_max) == (0.05, 0.90)
    assert (s.core_lat_min, s.core_lat_max) == (25.0, 70.0)
    assert s.core_lat_fraction_min == 0.95
    assert (s.smoke_peak_min, s.smoke_peak_max) == (20.0, 40.0)


def test_scratch_raw_expands_and_an_unset_variable_is_an_error(scratch, monkeypatch):
    cfg = load_config(CONFIG_PATH)
    assert cfg.paths.scratch_raw == scratch / "double-jet-natl" / "era5_raw"
    assert cfg.paths.data_dir == Path("data")
    assert cfg.paths.figs_dir == Path("figs")

    monkeypatch.delenv("SCRATCH")
    with pytest.raises(ConfigError, match="environment variable that is not set"):
        load_config(CONFIG_PATH)


# --- sector arithmetic --------------------------------------------------------------------------

def test_sector_arithmetic_is_221_by_361(cfg):
    assert cfg.sector.n_lat == 221
    assert cfg.sector.n_lon == 361


def test_latitudes_and_longitudes_are_ascending_with_the_right_endpoints(cfg):
    lat = cfg.sector.latitudes()
    assert lat.shape == (221,)
    assert lat[0] == pytest.approx(20.0)
    assert lat[-1] == pytest.approx(75.0)
    assert np.all(np.diff(lat) > 0)
    np.testing.assert_allclose(np.diff(lat), 0.25, atol=1e-9)

    lon = cfg.sector.longitudes()
    assert lon.shape == (361,)
    assert lon[0] == pytest.approx(-60.0)
    assert lon[-1] == pytest.approx(30.0)
    assert np.all(np.diff(lon) > 0)
    np.testing.assert_allclose(np.diff(lon), 0.25, atol=1e-9)


def test_area_is_cds_north_west_south_east(cfg):
    """CDS's `area` is [N, W, S, E] -- the one ordering it is easy to get wrong (plan §1.4)."""
    assert cfg.sector.area() == [75.0, -60.0, 20.0, 30.0]


# --- the boxcar window --------------------------------------------------------------------------

def test_boxcar_window_resolves_to_eleven_points(cfg):
    """2.5 deg at 0.25 deg spacing -> 11 samples, first centre to last centre (plan §2 I1)."""
    assert cfg.smooth_window_points == 11


def test_uncenterable_window_is_rejected(tmp_path, scratch):
    """2.25 deg spans 10 points, so it has no centre sample; the loader must refuse it."""
    path = _variant(tmp_path, "uncenterable.yaml",
                    "smooth_window_deg: 2.5", "smooth_window_deg: 2.25")
    with pytest.raises(ConfigError, match="cannot be centered"):
        load_config(path)


def test_window_off_the_grid_is_rejected(tmp_path, scratch):
    """A window that is not a whole number of grid steps is refused rather than rounded."""
    path = _variant(tmp_path, "offgrid.yaml",
                    "smooth_window_deg: 2.5", "smooth_window_deg: 2.6")
    with pytest.raises(ConfigError, match="whole number"):
        load_config(path)


# --- output naming (plan §4.2's table, risk R12) ------------------------------------------------

def test_output_names_are_pairwise_disjoint(cfg):
    """No run shape can overwrite another's artifact -- the collision is removed at its root."""
    campaign = cli.output_names(cfg, (cfg.year_first, cfg.year_last)).all_paths()
    smoke = cli.output_names(cfg, (cfg.smoke_year, cfg.smoke_year), smoke=True).all_paths()
    subset = cli.output_names(cfg, (2000, 2010)).all_paths()

    assert len(campaign) == 8 and len(smoke) == 8 and len(subset) == 8
    everything = list(campaign) + list(smoke) + list(subset)
    assert len(set(everything)) == len(everything), sorted(
        p for p in everything if everything.count(p) > 1)

    for a, b in ((campaign, smoke), (campaign, subset), (smoke, subset)):
        assert not (set(a) & set(b))


def test_only_the_full_campaign_produces_the_contract_names(cfg):
    campaign = cli.output_names(cfg, (cfg.year_first, cfg.year_last))
    assert campaign.profile == Path("data/u250_natl_mjjas_1979-2025.nc")
    assert campaign.states_csv == Path("data/jet_states_mjjas_1979-2025.csv")
    assert campaign.summary == Path("data/jet_states_summary.txt")
    assert campaign.panels == (Path("figs/double_jet_natl_panels.pdf"),
                               Path("figs/double_jet_natl_panels.png"))
    assert campaign.explorer == Path("figs/double_jet_natl_explorer.html")
    assert campaign.season_summary == Path("results/season_summary.csv")
    assert campaign.annual == Path("figs/double_jet_natl_annual.png")
    assert campaign.evidence is None
    assert set(campaign.all_paths()) == CONTRACT_NAMES

    smoke = cli.output_names(cfg, (cfg.smoke_year, cfg.smoke_year), smoke=True)
    assert set(smoke.all_paths()) & CONTRACT_NAMES == set()
    assert smoke.evidence == Path("data/smoke_2018_regression.json")   # source: rda_hourly (§A7.3)
    assert smoke.panels == (Path("figs/smoke_2018.png"),)

    # A subset that shares an endpoint with the campaign must not borrow its names either.
    for years in ((2000, 2010), (1979, 2024), (1980, 2025), (2018, 2018)):
        subset = cli.output_names(cfg, years)
        assert set(subset.all_paths()) & CONTRACT_NAMES == set(), years
        assert f"{years[0]}-{years[1]}" in subset.summary.name


def test_noncontiguous_years_are_rejected_at_parse_time():
    """`1979,2025` must not silently become the campaign's endpoints (risk R12)."""
    import argparse

    with pytest.raises(argparse.ArgumentTypeError, match="contiguous range"):
        cli.parse_years("1979,2025")
    with pytest.raises(argparse.ArgumentTypeError):
        cli.parse_years("1979 2025")
    with pytest.raises(argparse.ArgumentTypeError, match="first year is after last year"):
        cli.parse_years("2025-1979")

    assert cli.parse_years("1979-2025") == (1979, 2025)
    assert cli.parse_years("2000-2010") == (2000, 2010)

    # And the rejection reaches the operator as a parse failure, not a silent campaign run.
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(["--config", str(CONFIG_PATH), "--years", "1979,2025"])
    assert exc.value.code == 2


# --- the two hashes -----------------------------------------------------------------------------

def test_profile_hash_ignores_a_threshold_and_reacts_to_the_sector(tmp_path, scratch):
    """Changing a threshold must not invalidate the cached intermediate; changing the sector must.

    This is the structural guarantee behind "changing a threshold and re-running touches no raw
    file" (plan §4.2, §4.3).
    """
    base = load_config(CONFIG_PATH)

    threshold = load_config(_variant(tmp_path, "threshold.yaml",
                                     "u_core_min: 15.0", "u_core_min: 16.0"))
    assert threshold.detection.u_core_min == 16.0
    assert threshold.profile_sha256 == base.profile_sha256
    assert threshold.config_sha256 != base.config_sha256

    sector = load_config(_variant(tmp_path, "sector.yaml", "lon_min: -60.0", "lon_min: -55.0"))
    assert sector.sector.lon_min == -55.0
    assert sector.profile_sha256 != base.profile_sha256
    assert sector.config_sha256 != base.config_sha256

    assert "u_core_min" not in base.profile_fields()
    assert base.provenance()["profile_sha256"] == base.profile_sha256
