"""Command line: argument parsing, stage dispatch, and the one owner of every derived output path.

    python -m double_jet --config configs/double_jet.yaml [--smoke] [--years F-L]
                         [--stage all|download,profile,classify,figure] [--skip-download]
                         [--preflight-network]

`output_names` is the *only* place in the package that builds a path under `data/` or `figs/`
(plan §4.2). Raw-cache names under $SCRATCH stay with download.py; Slurm log paths stay in the job
headers.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import Config, load_config

STAGES = ("download", "profile", "classify", "figure")

EXIT_OK = 0
EXIT_SANITY = 1          # a hard sanity gate fired; the run completed and reported
EXIT_PREFLIGHT = 2       # network preflight failed before any CDS request was issued
EXIT_ERROR = 3           # anything else


@dataclass(frozen=True)
class OutputNames:
    """Derived-output paths for one run. Construct only via `output_names`."""

    profile: Path
    states_csv: Path
    summary: Path
    panels: tuple[Path, ...]
    r1_validation: Path | None

    def all_paths(self) -> tuple[Path, ...]:
        rest = (self.r1_validation,) if self.r1_validation is not None else ()
        return (self.profile, self.states_csv, self.summary) + self.panels + rest


def output_names(cfg: Config, years: tuple[int, int], smoke: bool = False) -> OutputNames:
    """Every path this pipeline writes under `data/` or `figs/`, for one run.

    Three mutually exclusive shapes (plan §4.2's table):

    * ``smoke``                       -- `smoke_<year>_*`, named apart so it can never be confused
                                         with the campaign, and carrying the R1 validation record.
    * the full campaign               -- selected by *exact equality* to the configured year range;
                                         these and only these are the wave prompt's contract names.
    * any other contiguous ``--years`` -- suffixed `<first>-<last>`, so a subset can never overwrite
                                         a campaign artifact.
    """
    data, figs = cfg.paths.data_dir, cfg.paths.figs_dir
    if smoke:
        tag = f"smoke_{cfg.smoke_year}"
        return OutputNames(
            profile=data / f"{tag}_profile.nc",
            states_csv=data / f"{tag}_jet_states.csv",
            summary=data / f"{tag}_summary.txt",
            panels=(figs / f"{tag}.png",),
            r1_validation=data / f"{tag}_r1_validation.json",
        )
    first, last = years
    if (first, last) == (cfg.year_first, cfg.year_last):
        return OutputNames(
            profile=data / f"u250_natl_mjjas_{first}-{last}.nc",
            states_csv=data / f"jet_states_mjjas_{first}-{last}.csv",
            summary=data / "jet_states_summary.txt",
            panels=(figs / "double_jet_natl_panels.pdf", figs / "double_jet_natl_panels.png"),
            r1_validation=None,
        )
    return OutputNames(
        profile=data / f"u250_natl_mjjas_{first}-{last}.nc",
        states_csv=data / f"jet_states_mjjas_{first}-{last}.csv",
        summary=data / f"jet_states_summary_{first}-{last}.txt",
        panels=(figs / f"double_jet_natl_panels_{first}-{last}.pdf",
                figs / f"double_jet_natl_panels_{first}-{last}.png"),
        r1_validation=None,
    )


def parse_years(text: str) -> tuple[int, int]:
    """`--years` is a validated inclusive contiguous range `FIRST-LAST`, and nothing else.

    An arbitrary year list such as `1979,2025` is rejected here rather than downstream, because a
    gappy set sharing the campaign's endpoints would otherwise claim the campaign's filenames
    (plan §4.2, risk R12).
    """
    parts = text.split("-")
    if len(parts) != 2 or not all(p.strip().isdigit() for p in parts):
        raise argparse.ArgumentTypeError(
            f"--years must be an inclusive contiguous range 'FIRST-LAST' (got {text!r}); "
            "a year list is not accepted"
        )
    first, last = int(parts[0]), int(parts[1])
    if first > last:
        raise argparse.ArgumentTypeError(f"--years {text}: first year is after last year")
    return first, last


def parse_stages(text: str) -> tuple[str, ...]:
    if text.strip() == "all":
        return STAGES
    wanted = [s.strip() for s in text.split(",") if s.strip()]
    unknown = [s for s in wanted if s not in STAGES]
    if unknown or not wanted:
        raise argparse.ArgumentTypeError(
            f"--stage must be 'all' or a comma-separated subset of {','.join(STAGES)} (got {text!r})"
        )
    return tuple(s for s in STAGES if s in wanted)   # canonical order, deduplicated


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m double_jet",
        description="ERA5 250 hPa double-jet vs single-jet classification, North Atlantic-Europe.",
    )
    p.add_argument("--config", required=True, type=Path, help="path to configs/double_jet.yaml")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--smoke", action="store_true",
                       help="single smoke season: both CDS products, the R1 equivalence gate, "
                            "and one panel")
    group.add_argument("--years", type=parse_years, metavar="FIRST-LAST",
                       help="inclusive contiguous year range (default: the configured campaign)")
    p.add_argument("--stage", type=parse_stages, default=STAGES, metavar="STAGES",
                   help="'all' (default) or a subset of " + ",".join(STAGES))
    p.add_argument("--skip-download", action="store_true",
                   help="never issue a CDS request; validate what is already on $SCRATCH and fail "
                        "loudly if any season is missing or does not match the current request")
    p.add_argument("--preflight-network", action="store_true",
                   help="probe CDS reachability and exit; issues no CDS request")
    p.add_argument("--log-level", default="INFO")
    return p


def configure_logging(level: str) -> logging.Logger:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
    return logging.getLogger("double_jet")


def run(args: argparse.Namespace) -> int:
    from . import classify as classify_mod
    from . import download as download_mod
    from . import figure as figure_mod
    from . import profile as profile_mod

    log = configure_logging(args.log_level)
    cfg = load_config(args.config)

    if args.preflight_network:
        try:
            download_mod.preflight_network(log)
        except download_mod.PreflightError as exc:
            log.error("%s", exc)
            return EXIT_PREFLIGHT
        log.info("network preflight OK")
        return EXIT_OK

    smoke = args.smoke
    years = (cfg.smoke_year, cfg.smoke_year) if smoke else (args.years or (cfg.year_first,
                                                                          cfg.year_last))
    if not smoke and args.years is not None:
        if not (cfg.year_first <= years[0] <= years[1] <= cfg.year_last):
            log.error("--years %d-%d lies outside the configured campaign %d-%d; changing the "
                      "year range is an escalation, not a flag", years[0], years[1],
                      cfg.year_first, cfg.year_last)
            return EXIT_ERROR

    out = output_names(cfg, years, smoke=smoke)
    season_years = list(range(years[0], years[1] + 1))
    cfg.paths.data_dir.mkdir(parents=True, exist_ok=True)
    cfg.paths.figs_dir.mkdir(parents=True, exist_ok=True)

    log.info("config %s (sha %s)", cfg.source_path, cfg.config_sha256[:12])
    log.info("run: %s, seasons %d-%d (%d), stages %s%s",
             "smoke" if smoke else "campaign" if years == (cfg.year_first, cfg.year_last)
             else "subset",
             years[0], years[1], len(season_years), ",".join(args.stage),
             " (--skip-download)" if args.skip_download else "")

    if "download" in args.stage:
        try:
            download_mod.preflight_network(log)
        except download_mod.PreflightError as exc:
            log.error("%s", exc)
            return EXIT_PREFLIGHT
        if args.skip_download:
            download_mod.ensure_downloaded(cfg, season_years, smoke=smoke, log=log)
        else:
            download_mod.run_download(cfg, season_years, smoke=smoke, log=log)
        if smoke:
            download_mod.check_r1_equivalence(cfg, cfg.smoke_year, out.r1_validation, log=log)

    if "profile" in args.stage:
        profile_mod.build_intermediate(cfg, season_years, out.profile, log=log)

    sanity_ok = True
    if "classify" in args.stage:
        result = classify_mod.run_classify(cfg, out.profile, out.states_csv, out.summary,
                                           smoke=smoke, log=log)
        sanity_ok = result.ok

    if "figure" in args.stage:
        figure_mod.run_figure(cfg, out.profile, out.states_csv, out.panels, smoke=smoke, log=log)

    if not sanity_ok:
        log.error("a hard sanity gate failed -- see %s. Reporting and stopping; thresholds are not "
                  "retuned without an operator ruling (plan §10 E2).", out.summary)
        return EXIT_SANITY
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except Exception:
        logging.getLogger("double_jet").exception("run failed")
        return EXIT_ERROR
