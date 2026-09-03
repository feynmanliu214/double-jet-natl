"""Day-by-day jet states, the states CSV, and the sanity block (plan §4.3, §4.4, §2 I1-I5).

Everything here except `run_classify` is a pure function of `(U, latitude, thresholds)`: no file is
opened, and no threshold is hard-coded -- every number is read off `cfg`.

Four interpretations the plan fixed and this module implements literally. None is re-decided here;
changing any of them is an escalation (plan §11), not a code edit:

* **I1 / I2** -- the boxcar is `cfg.smooth_window_points` (= 11 samples = 2.5 deg at 0.25 deg) and is
  *truncated and renormalized* at 20 N and 75 N: the mean divides by the number of samples actually
  inside the domain. Not edge replication, not NaN.
* **I3** -- a core is `scipy.signal.find_peaks` **at its defaults**: an interior sample strictly
  above both neighbours, or the midpoint of an exact flat top. No `plateau_size`, no `prominence`,
  no `height` -- verified on the installed scipy 1.17.1 that `plateau_size=(None, 1)` *discards* a
  flat-topped maximum rather than locating it, so the apparent "tightening" would silently drop a
  core. `tests/test_classify.py` locks this in. A consequence is that the domain endpoints can never
  be cores; that is deliberate and is recorded as risk R7.
* **I4** -- the pair rule: order the surviving cores by descending U, scan pairs in that order, and
  accept the *first* pair satisfying both the separation and the prominence rule. That is the
  strongest core that has any valid partner, paired with its strongest valid partner.
* **I5** -- the smoke "peak 20-40 m/s" plausibility check is the **season median** of the daily
  maximum of the smoothed profile, printed for the operator and never a gate.

Of the checks in the §4.4 block, only the double-jet fraction is a gate: it sets `ok=False`, which
`cli.run` maps to `EXIT_SANITY`. The 25-70 N core-latitude check is **reported, never enforced** --
operator ruling R2 -- so this module must never let it set `ok=False` and must never move the band.
Both are the operator's to judge (plan §10 E2, E3).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from .config import Config, Detection

# The CSV's columns, in order, exactly as the wave contract names them (plan §4.3 step 4).
CSV_COLUMNS: tuple[str, ...] = ("date", "state", "lat_1", "u_1", "lat_2", "u_2", "interjet_min")
_NUMERIC_COLUMNS: tuple[str, ...] = ("lat_1", "u_1", "lat_2", "u_2", "interjet_min")

STATE_NONE = "none"
STATE_SINGLE = "single"
STATE_DOUBLE = "double"
STATES: tuple[str, ...] = (STATE_DOUBLE, STATE_SINGLE, STATE_NONE)

DATE_FORMAT = "%Y-%m-%d"

# How many out-of-band cores the R2 diagnostic names individually. Enough for the operator to see
# whether the misses are subtropical, polar, or both (plan §1.7 found both), not a full listing.
WORST_OFFENDERS_SHOWN = 8


class ProfileMismatchError(RuntimeError):
    """The intermediate was built from a different profile-determining config (plan §4.3).

    A `RuntimeError` subclass so `cli.run`'s blanket handler still maps it to `EXIT_ERROR`.
    """


@dataclass(frozen=True)
class SanityResult:
    """Outcome of the §4.4 block: `ok` is the hard gate, `text` is what was written and logged."""

    ok: bool
    text: str
    stats: dict = field(default_factory=dict)


def smooth(U: np.ndarray, window_points: int) -> np.ndarray:
    """Centered boxcar of `window_points` samples along the LAST axis (plan §2 I1, I2).

    Works on a single `(n_lat,)` profile and on an `(n_time, n_lat)` stack. At the two domain ends
    the window is **truncated and renormalized**: each output divides by the count of samples
    actually inside the domain, so a constant field is reproduced exactly at 20 N and 75 N. Zero
    padding would bias the edges downward and edge replication would invent data; I2 chose neither.
    """
    w = int(window_points)
    if w < 1 or w % 2 == 0:
        raise ValueError(
            f"boxcar window must be a positive odd sample count so it can be centered on a "
            f"sample, got {window_points!r}"
        )
    arr = np.asarray(U, dtype=np.float64)
    if arr.ndim < 1 or arr.shape[-1] == 0:
        raise ValueError(f"smooth needs a non-empty last axis, got shape {arr.shape}")

    n = arr.shape[-1]
    half = w // 2
    # One cumulative sum gives every window sum. Clipping the window edges to the domain and
    # dividing by the *clipped* width is exactly I2's truncated, renormalized boxcar.
    csum = np.concatenate([np.zeros(arr.shape[:-1] + (1,)), np.cumsum(arr, axis=-1)], axis=-1)
    idx = np.arange(n)
    lo = np.maximum(idx - half, 0)
    hi = np.minimum(idx + half, n - 1) + 1          # exclusive
    return (csum[..., hi] - csum[..., lo]) / (hi - lo)


def find_cores(
    u_smooth_1d: np.ndarray, lat: np.ndarray, u_core_min: float
) -> list[tuple[int, float, float]]:
    """Jet cores in one smoothed profile as `(index, latitude, u)`, ordered south to north.

    `find_peaks` is called **at its defaults** (plan §2 I3). Passing `plateau_size`, `prominence` or
    `height` here would not tighten the definition -- on scipy 1.17.1 `plateau_size=(None, 1)`
    returns nothing for a flat-topped maximum -- so a core would be dropped, not located. The
    threshold is applied afterwards, on the smoothed value, so `u_core_min` never interacts with the
    peak-finding itself.
    """
    u = np.asarray(u_smooth_1d, dtype=np.float64)
    latitude = np.asarray(lat, dtype=np.float64)
    if u.ndim != 1:
        raise ValueError(f"find_cores takes one profile at a time, got shape {u.shape}")
    if latitude.shape != u.shape:
        raise ValueError(
            f"latitude axis {latitude.shape} does not match the profile {u.shape}"
        )

    peaks, _ = find_peaks(u)          # I3: defaults, deliberately. See the module docstring.
    return [(int(i), float(latitude[i]), float(u[i])) for i in peaks if u[i] >= u_core_min]


def classify_day(u_smooth_1d: np.ndarray, lat: np.ndarray, detection: Detection) -> dict:
    """State of one day: `none`, `single` or `double` (plan §4.3 step 3, §2 I4).

    Returns the CSV's core columns with `None` where the plan says blank. On a `double` day the two
    cores are recorded **ordered south to north** in `(lat_1, u_1)` and `(lat_2, u_2)` -- the
    ordering is geographic, not by strength, so the columns mean the same thing on every row.
    """
    cores = find_cores(u_smooth_1d, lat, detection.u_core_min)
    day: dict = {"state": STATE_NONE, "lat_1": None, "u_1": None,
                 "lat_2": None, "u_2": None, "interjet_min": None}
    if not cores:
        return day

    u = np.asarray(u_smooth_1d, dtype=np.float64)
    # I4: descending U, and the FIRST pair passing both rules wins. The index breaks ties so the
    # answer never depends on sort stability or on the order find_peaks happened to return.
    ranked = sorted(cores, key=lambda core: (-core[2], core[0]))
    for rank, first in enumerate(ranked):
        for second in ranked[rank + 1:]:
            south, north = sorted((first, second), key=lambda core: core[1])
            if north[1] - south[1] < detection.separation_min_deg:
                continue
            between = u[south[0] + 1:north[0]]
            if between.size == 0:
                continue        # adjacent samples: there is no interjet minimum to test
            interjet_min = float(between.min())
            if interjet_min <= min(south[2], north[2]) - detection.prominence_min:
                return {"state": STATE_DOUBLE,
                        "lat_1": south[1], "u_1": south[2],
                        "lat_2": north[1], "u_2": north[2],
                        "interjet_min": interjet_min}

    strongest = ranked[0]
    day.update(state=STATE_SINGLE, lat_1=strongest[1], u_1=strongest[2])
    return day


def classify_all(
    U_smooth: np.ndarray, lat: np.ndarray, detection: Detection, times
) -> pd.DataFrame:
    """One row per day, columns exactly `CSV_COLUMNS`, `date` as `YYYY-MM-DD`."""
    profiles = np.asarray(U_smooth, dtype=np.float64)
    if profiles.ndim != 2:
        raise ValueError(f"classify_all expects (n_time, n_lat), got shape {profiles.shape}")
    dates = pd.to_datetime(np.asarray(times)).strftime(DATE_FORMAT)
    if len(dates) != profiles.shape[0]:
        raise ValueError(
            f"{len(dates)} times do not match {profiles.shape[0]} profiles"
        )

    records = [{"date": date, **classify_day(profile, lat, detection)}
               for date, profile in zip(dates, profiles)]
    df = pd.DataFrame.from_records(records, columns=list(CSV_COLUMNS))
    # Blank core columns must land in the CSV as empty fields, not the string "None": force the
    # numeric columns to float so `None` becomes NaN and `to_csv`'s default na_rep applies.
    for column in _NUMERIC_COLUMNS:
        df[column] = df[column].astype("float64")
    return df


def sanity_report(
    cfg: Config, df: pd.DataFrame, U_smooth: np.ndarray, lat: np.ndarray, smoke: bool
) -> SanityResult:
    """The §4.4 sanity block, as text plus the numbers behind it.

    Only the double-jet fraction gates. The core-latitude fraction is printed against its 95 %
    target verbatim and can never set `ok=False` (operator ruling R2); the smoke peak statistic is
    printed for an eyeball check and is not a gate either (I5).
    """
    sanity = cfg.sanity
    profiles = np.asarray(U_smooth, dtype=np.float64)
    latitude = np.asarray(lat, dtype=np.float64)
    if profiles.ndim == 2 and profiles.shape[-1] != latitude.size:
        raise ValueError(
            f"profile latitude axis {profiles.shape[-1]} does not match {latitude.size} latitudes"
        )

    n_days = int(len(df))
    counts = {state: int((df["state"] == state).sum()) for state in STATES}
    double_fraction = counts[STATE_DOUBLE] / n_days if n_days else float("nan")
    # The gate, and the only thing that may set ok=False (§4.4, risk R8, escalation E2).
    fraction_ok = bool(
        n_days > 0
        and sanity.double_fraction_min <= double_fraction <= sanity.double_fraction_max
    )

    # Every recorded core: lat_1 on any classified day, lat_2 additionally on double days. Reading
    # the columns' non-null entries rather than the state keeps this true by construction.
    recorded = [df.loc[df[column].notna(), ["date", column]].rename(columns={column: "lat"})
                for column in ("lat_1", "lat_2")]
    cores = pd.concat(recorded, ignore_index=True) if recorded else pd.DataFrame(
        columns=["date", "lat"])
    n_cores = int(len(cores))
    in_band = cores["lat"].between(sanity.core_lat_min, sanity.core_lat_max)
    n_in_band = int(in_band.sum())
    core_lat_fraction = n_in_band / n_cores if n_cores else float("nan")
    outside = cores.loc[~in_band].copy() if n_cores else cores.assign(excess=[])
    if n_cores:
        outside["excess"] = np.maximum(sanity.core_lat_min - outside["lat"],
                                       outside["lat"] - sanity.core_lat_max)
        outside = outside.sort_values(["excess", "date"], ascending=[False, True])
    worst = [(str(row.date), float(row.lat))
             for row in outside.head(WORST_OFFENDERS_SHOWN).itertuples()]

    stats: dict = {
        "n_days": n_days,
        "n_double": counts[STATE_DOUBLE],
        "n_single": counts[STATE_SINGLE],
        "n_none": counts[STATE_NONE],
        "double_fraction": double_fraction,
        "double_fraction_min": sanity.double_fraction_min,
        "double_fraction_max": sanity.double_fraction_max,
        "double_fraction_ok": fraction_ok,
        "n_cores": n_cores,
        "n_cores_in_band": n_in_band,
        "n_cores_out_of_band": n_cores - n_in_band,
        "core_lat_fraction": core_lat_fraction,
        "core_lat_fraction_min": sanity.core_lat_fraction_min,
        "core_lat_min": sanity.core_lat_min,
        "core_lat_max": sanity.core_lat_max,
        "core_lat_worst": worst,
    }

    rule = "=" * 78
    lines = [
        rule,
        "double-jet classification -- sanity block (plan §4.4)",
        rule,
        f"days classified : {n_days}",
        f"  double        : {counts[STATE_DOUBLE]:>6}  ({_pct(counts[STATE_DOUBLE], n_days)})",
        f"  single        : {counts[STATE_SINGLE]:>6}  ({_pct(counts[STATE_SINGLE], n_days)})",
        f"  none          : {counts[STATE_NONE]:>6}  ({_pct(counts[STATE_NONE], n_days)})",
        "",
        "[GATE]     double-jet fraction "
        f"{double_fraction:.4f} against band "
        f"{sanity.double_fraction_min:.4f}-{sanity.double_fraction_max:.4f} -> "
        f"{'PASS' if fraction_ok else 'FAIL'}",
    ]
    if not fraction_ok:
        lines.append(
            "           the run completed and is reporting; thresholds are not retuned without an "
            "operator ruling (plan §10 E2)."
        )
    lines += [
        "",
        f"[REPORT]   core latitudes within {sanity.core_lat_min:g}-{sanity.core_lat_max:g} N : "
        f"{_pct(n_in_band, n_cores)} of {n_cores} recorded cores "
        f"(target >= {100.0 * sanity.core_lat_fraction_min:g} %)",
        f"           out-of-band cores : {n_cores - n_in_band}",
    ]
    if worst:
        lines.append(f"           worst offenders (up to {WORST_OFFENDERS_SHOWN}):")
        lines += [f"             {date}  {value:7.2f} N" for date, value in worst]
    lines.append(
        "           REPORTED, NOT A GATE -- operator ruling R2. The band and the 95 % target are "
        "printed verbatim;"
    )
    lines.append(
        "           the run finishes and the operator judges. No band is moved here (plan §0 R2, "
        "§10 E3)."
    )

    if smoke:
        if profiles.ndim != 2 or profiles.shape[0] == 0:
            raise ValueError(
                f"the smoke plausibility check needs a (n_time, n_lat) stack, got {profiles.shape}"
            )
        daily_max = profiles.max(axis=-1)
        peak_median = float(np.median(daily_max))
        peak_min, peak_max = float(daily_max.min()), float(daily_max.max())
        stats.update(smoke_peak_median=peak_median, smoke_peak_min=peak_min,
                     smoke_peak_max=peak_max,
                     smoke_peak_band_min=sanity.smoke_peak_min,
                     smoke_peak_band_max=sanity.smoke_peak_max)
        lines += [
            "",
            "[REPORT]   smoke profile, daily maximum of the smoothed profile (m s-1): "
            f"median {peak_median:.2f}, min {peak_min:.2f}, max {peak_max:.2f}",
            f"           configured plausibility band {sanity.smoke_peak_min:g}-"
            f"{sanity.smoke_peak_max:g} m s-1, read as the SEASON MEDIAN (plan §2 I5)",
            "           printed for the operator's eyeball check -- never a gate.",
        ]
    lines.append(rule)

    return SanityResult(ok=fraction_ok, text="\n".join(lines) + "\n", stats=stats)


def _pct(part: int, whole: int) -> str:
    return f"{100.0 * part / whole:5.1f} %" if whole else "    n/a"


def run_classify(
    cfg: Config,
    profile_path: Path,
    csv_path: Path,
    summary_path: Path,
    smoke: bool,
    log: logging.Logger,
) -> SanityResult:
    """Intermediate -> states CSV + sanity block (plan §4.3, §4.4).

    Before anything is classified, the intermediate's recorded `profile_sha256` is compared with the
    config in hand. That catches "I changed the sector and reused the old intermediate", which is
    otherwise completely silent. Detection thresholds are deliberately outside that hash: changing a
    threshold and re-running against the same cached intermediate is exactly what the contract
    requires to keep working, so it must not trip this check.
    """
    # Deferred so the pure functions above import without xarray/netCDF present, matching the way
    # cli.run imports its stages.
    from .profile import open_intermediate

    profile_path = Path(profile_path)
    csv_path, summary_path = Path(csv_path), Path(summary_path)

    dataset = open_intermediate(profile_path)
    try:
        recorded = dataset.attrs.get("profile_sha256")
        if recorded != cfg.profile_sha256:
            raise ProfileMismatchError(
                "profile hash check failed: "
                f"{profile_path} records profile_sha256={recorded!r}, but {cfg.source_path} "
                f"hashes to {cfg.profile_sha256!r}. The intermediate was built from a different "
                "sector, level, season or year range -- rebuild it with the `profile` stage, or "
                "classify it with the config it was built from. Detection thresholds are excluded "
                "from this hash by design (plan §4.3), so a threshold change never lands here."
            )
        U = np.asarray(dataset["U"].values, dtype=np.float64)
        latitude = np.asarray(dataset["latitude"].values, dtype=np.float64)
        times = np.asarray(dataset["time"].values)
    finally:
        dataset.close()

    log.info("classifying %d days x %d latitudes from %s", U.shape[0], U.shape[-1], profile_path)
    U_smooth = smooth(U, cfg.smooth_window_points)
    log.info("boxcar smoothing: %d points (%g deg), truncated and renormalized at the domain ends",
             cfg.smooth_window_points, cfg.detection.smooth_window_deg)

    df = classify_all(U_smooth, latitude, cfg.detection, times)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    log.info("wrote %d rows to %s", len(df), csv_path)

    result = sanity_report(cfg, df, U_smooth, latitude, smoke=smoke)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(result.text)
    for line in result.text.rstrip("\n").splitlines():
        log.info("%s", line)
    log.info("sanity block written to %s", summary_path)
    return result
