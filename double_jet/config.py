"""Configuration: the one place every frozen number in the scientific contract enters the code.

`configs/double_jet.yaml` is the only source of thresholds. Nothing downstream may hard-code one.
Two hashes are derived here and both are recorded in the intermediate's attributes:

* `config_sha256`  -- of the YAML file's bytes, for provenance.
* `profile_sha256` -- of the *profile-determining* fields only (sector, level, season months, year
  range, and the retrieval definition that fixes what "daily mean" means). Detection thresholds are
  deliberately excluded, because changing a threshold and re-running against the same cached
  intermediate is exactly what the contract requires to keep working (plan §4.3).
"""

from __future__ import annotations

import calendar
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

# Packages whose versions are recorded with every intermediate, so a rebuild of the shared
# `graphcast` env is detectable rather than silent (plan §1.9, §4.2, risk R9).
PROVENANCE_DISTRIBUTIONS = (
    "cdsapi", "xarray", "netCDF4", "numpy", "scipy", "matplotlib", "pandas", "dask", "pyyaml",
)

PLAN_PATH = "wave1-plan.md"

# Which stage-1 source supplies the daily mean (deviation D3, addendum §A4). `cds_derived` is the
# original CDS path and stays the default for any config that predates the key.
SOURCES = ("cds_derived", "rda_hourly")
DEFAULT_SOURCE = "cds_derived"


class ConfigError(ValueError):
    """The config file is missing a key, or holds a value the contract does not allow."""


def package_versions() -> dict[str, str]:
    """Installed versions of the packages this wave depends on (plan §1.9's table)."""
    from importlib.metadata import PackageNotFoundError, version

    out = {}
    for dist in PROVENANCE_DISTRIBUTIONS:
        try:
            out[dist] = version(dist)
        except PackageNotFoundError:
            out[dist] = "absent"
    return out


@dataclass(frozen=True)
class Sector:
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    resolution: float

    def _n(self, lo: float, hi: float) -> int:
        span = (hi - lo) / self.resolution
        n = round(span)
        if abs(span - n) > 1e-6:
            raise ConfigError(
                f"sector bound {lo}..{hi} is not a whole number of {self.resolution} deg steps"
            )
        return n + 1

    @property
    def n_lat(self) -> int:
        return self._n(self.lat_min, self.lat_max)

    @property
    def n_lon(self) -> int:
        return self._n(self.lon_min, self.lon_max)

    def latitudes(self) -> np.ndarray:
        """Ascending, as the normalized intermediate stores them."""
        return np.linspace(self.lat_min, self.lat_max, self.n_lat)

    def longitudes(self) -> np.ndarray:
        """Ascending, normalized to [-180, 180)."""
        return np.linspace(self.lon_min, self.lon_max, self.n_lon)

    def area(self) -> list[float]:
        """CDS `area` schema is [North, West, South, East] (plan §1.4)."""
        return [self.lat_max, self.lon_min, self.lat_min, self.lon_max]


@dataclass(frozen=True)
class Detection:
    u_core_min: float
    separation_min_deg: float
    prominence_min: float
    smooth_window_deg: float


@dataclass(frozen=True)
class Sanity:
    double_fraction_min: float
    double_fraction_max: float
    core_lat_min: float
    core_lat_max: float
    core_lat_fraction_min: float
    smoke_peak_min: float
    smoke_peak_max: float


@dataclass(frozen=True)
class Rda:
    """Machine addressing for the RDA archive on /glade -- no scientific threshold lives here.

    `root` and `file_template` are configured rather than hard-coded so that a repointed archive is
    a config edit with a hash consequence (addendum §A4.3), not a code edit. Nothing in this class
    is checked against the filesystem at load time; that is `preflight_archive`'s job alone.
    """

    root: Path
    file_template: str
    dataset_id: str
    workers: int


# The stand-in used when a config carries no `rda` block at all -- every CDS-path config, including
# every existing test fixture. It addresses nothing, and nothing on the CDS path reads it.
RDA_ABSENT = Rda(root=Path(""), file_template="", dataset_id="", workers=1)


@dataclass(frozen=True)
class Paths:
    scratch_raw: Path
    data_dir: Path
    figs_dir: Path


@dataclass(frozen=True)
class Config:
    dataset: str
    hourly_dataset: str
    variable: str
    pressure_level: int
    season_months: tuple[int, ...]
    year_first: int
    year_last: int
    smoke_year: int
    daily_statistic: str
    time_zone: str
    frequency: str
    hourly_times: tuple[str, ...]
    r1_tolerance: float
    max_in_flight: int
    source: str
    sector: Sector
    detection: Detection
    sanity: Sanity
    rda: Rda
    paths: Paths
    source_path: Path
    config_sha256: str

    # -- derived quantities ---------------------------------------------------

    @property
    def active_dataset(self) -> str:
        """The dataset the bytes actually came from -- CDS's product, or the RDA collection.

        Provenance that names a dataset the data did not come from is worse than none, so every
        recorded `source_dataset` reads this rather than `dataset` (addendum §A7.2).
        """
        return self.rda.dataset_id if self.source == "rda_hourly" else self.dataset

    @property
    def years(self) -> tuple[int, ...]:
        return tuple(range(self.year_first, self.year_last + 1))

    @property
    def n_seasons(self) -> int:
        return len(self.years)

    @property
    def days_per_season(self) -> int:
        """153 for MJJAS. Computed, not asserted: no configured month contains 29 February."""
        return sum(calendar.monthrange(2001, m)[1] for m in self.season_months)

    @property
    def n_days(self) -> int:
        return self.n_seasons * self.days_per_season

    @property
    def smooth_window_points(self) -> int:
        """2.5 deg at 0.25 deg -> 11 points, the only centerable choice (plan §2 I1)."""
        steps = self.detection.smooth_window_deg / self.sector.resolution
        n = round(steps)
        if abs(steps - n) > 1e-6:
            raise ConfigError(
                f"smooth window {self.detection.smooth_window_deg} deg is not a whole number of "
                f"{self.sector.resolution} deg grid steps"
            )
        if n % 2 != 0:
            raise ConfigError(
                f"smooth window {self.detection.smooth_window_deg} deg spans {n + 1} grid points, "
                "which cannot be centered on a sample"
            )
        return n + 1

    def month_strings(self) -> list[str]:
        return [f"{m:02d}" for m in self.season_months]

    # -- hashes and provenance ------------------------------------------------

    def profile_fields(self) -> dict:
        """Exactly the fields that determine U(phi, t). Detection thresholds are excluded.

        `source` is here so a CDS-built and an RDA-built intermediate can never be silently
        interchanged, and `hourly_times` because on the RDA path the loader reads it directly: it
        *is* the definition of the daily mean there, and a change to it would otherwise alter every
        value of U(phi, t) while leaving this hash identical (addendum §A4.3, O1, DR15).
        """
        fields = {
            "dataset": self.dataset,
            "variable": self.variable,
            "pressure_level": self.pressure_level,
            "season_months": list(self.season_months),
            "year_first": self.year_first,
            "year_last": self.year_last,
            "daily_statistic": self.daily_statistic,
            "time_zone": self.time_zone,
            "frequency": self.frequency,
            "hourly_times": list(self.hourly_times),
            "source": self.source,
            "sector": {
                "lat_min": self.sector.lat_min,
                "lat_max": self.sector.lat_max,
                "lon_min": self.sector.lon_min,
                "lon_max": self.sector.lon_max,
                "resolution": self.sector.resolution,
            },
        }
        if self.source == "rda_hourly":
            # A repointed archive is a different provenance and must not be silently reusable.
            fields["rda_root"] = str(self.rda.root)
            fields["rda_file_template"] = self.rda.file_template
        return fields

    @property
    def profile_sha256(self) -> str:
        blob = json.dumps(self.profile_fields(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()

    def provenance(self) -> dict:
        return {
            "config_path": str(self.source_path),
            "config_sha256": self.config_sha256,
            "profile_sha256": self.profile_sha256,
            "interpreter": sys.executable,
            "package_versions": package_versions(),
            "plan": PLAN_PATH,
        }


def _require(mapping: dict, key: str, where: str):
    if key not in mapping:
        raise ConfigError(f"missing required key '{key}' in {where}")
    return mapping[key]


def _expand(raw: str) -> Path:
    """Expand $VARS in a configured path; an unset variable is an error, not an empty string."""
    expanded = os.path.expandvars(str(raw))
    if "$" in expanded:
        raise ConfigError(f"path '{raw}' references an environment variable that is not set")
    return Path(expanded)


def load_config(path: str | Path) -> Config:
    path = Path(path)
    text = path.read_bytes()
    raw = yaml.safe_load(text)
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} does not parse to a mapping")

    sector = Sector(**{k: float(_require(raw["sector"], k, "sector"))
                       for k in ("lat_min", "lat_max", "lon_min", "lon_max", "resolution")})
    detection = Detection(**{k: float(_require(raw["detection"], k, "detection"))
                             for k in ("u_core_min", "separation_min_deg", "prominence_min",
                                       "smooth_window_deg")})
    sanity = Sanity(**{k: float(_require(raw["sanity"], k, "sanity"))
                       for k in ("double_fraction_min", "double_fraction_max", "core_lat_min",
                                 "core_lat_max", "core_lat_fraction_min", "smoke_peak_min",
                                 "smoke_peak_max")})
    source = str(raw.get("source", DEFAULT_SOURCE))
    if source not in SOURCES:
        raise ConfigError(
            f"source {source!r} in {path.name} is not one of 'rda_hourly', 'cds_derived'"
        )

    # Shape only: keys present, types right. `_expand` resolves $VARS and never stats, so a config
    # naming an archive this host cannot see still loads -- archive existence and readability are
    # `preflight_archive`'s alone (addendum §A4.2, load-bearing: the whole suite loads the shipped
    # YAML and must stay green off-machine).
    rda_raw = raw.get("rda")
    if rda_raw is None:
        rda = RDA_ABSENT
    elif not isinstance(rda_raw, dict):
        raise ConfigError(f"key 'rda' in {path.name} does not parse to a mapping")
    else:
        rda = Rda(
            root=_expand(_require(rda_raw, "root", "rda")),
            file_template=str(_require(rda_raw, "file_template", "rda")),
            dataset_id=str(_require(rda_raw, "dataset_id", "rda")),
            workers=int(_require(rda_raw, "workers", "rda")),
        )

    paths = Paths(
        scratch_raw=_expand(_require(raw["paths"], "scratch_raw", "paths")),
        data_dir=Path(_require(raw["paths"], "data_dir", "paths")),
        figs_dir=Path(_require(raw["paths"], "figs_dir", "paths")),
    )

    cfg = Config(
        dataset=str(_require(raw, "dataset", path.name)),
        hourly_dataset=str(_require(raw, "hourly_dataset", path.name)),
        variable=str(_require(raw, "variable", path.name)),
        pressure_level=int(_require(raw, "pressure_level", path.name)),
        season_months=tuple(int(m) for m in _require(raw, "season_months", path.name)),
        year_first=int(_require(raw, "year_first", path.name)),
        year_last=int(_require(raw, "year_last", path.name)),
        smoke_year=int(_require(raw, "smoke_year", path.name)),
        daily_statistic=str(_require(raw, "daily_statistic", path.name)),
        time_zone=str(_require(raw, "time_zone", path.name)),
        frequency=str(_require(raw, "frequency", path.name)),
        hourly_times=tuple(str(t) for t in _require(raw, "hourly_times", path.name)),
        r1_tolerance=float(_require(raw, "r1_tolerance", path.name)),
        max_in_flight=int(_require(raw, "max_in_flight", path.name)),
        source=source,
        sector=sector,
        detection=detection,
        sanity=sanity,
        rda=rda,
        paths=paths,
        source_path=path,
        config_sha256=hashlib.sha256(text).hexdigest(),
    )

    if cfg.year_first > cfg.year_last:
        raise ConfigError(f"year_first {cfg.year_first} is after year_last {cfg.year_last}")
    if not cfg.year_first <= cfg.smoke_year <= cfg.year_last:
        raise ConfigError(f"smoke_year {cfg.smoke_year} is outside {cfg.year_first}-{cfg.year_last}")
    cfg.smooth_window_points  # validates the window resolves to an odd point count
    return cfg
