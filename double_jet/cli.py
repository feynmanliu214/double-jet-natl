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

from . import source as source_mod       # stage-1 dispatch; it defers its own heavy imports
from .config import Config, load_config

STAGES = ("download", "profile", "classify", "figure")

EXIT_OK = 0
EXIT_SANITY = 1          # a hard sanity gate fired; the run completed and reported
EXIT_PREFLIGHT = 2       # network preflight failed before any CDS request was issued
EXIT_ERROR = 3           # anything else

# The committed CDS baseline an RDA smoke run is regressed against (addendum §A9.1). It is a
# tracked repository artifact, not a derived output, so it is anchored to the package rather than
# to the working directory, and `output_names` stays the only owner of paths under `data/`/`figs/`.
REGRESSION_BASELINE = Path(__file__).resolve().parents[1] / "results" / "smoke_2018"


@dataclass(frozen=True)
class OutputNames:
    """Derived-output paths for one run. Construct only via `output_names`.

    `evidence` is the *one* source-equivalence record a smoke run writes, and there is exactly one
    slot for it (addendum §A7.3 item 4, risk DR17): *which* check wrote it -- the CDS R1
    equivalence gate or the RDA 2018 regression -- is a property of `cfg.source`, not a second
    artifact. A second field would make a smoke run's `all_paths()` six long and break the
    disjointness test that enforces plan §8 R12.
    """

    profile: Path
    states_csv: Path
    summary: Path
    panels: tuple[Path, ...]
    evidence: Path | None

    def all_paths(self) -> tuple[Path, ...]:
        rest = (self.evidence,) if self.evidence is not None else ()
        return (self.profile, self.states_csv, self.summary) + self.panels + rest


def output_names(cfg: Config, years: tuple[int, int], smoke: bool = False) -> OutputNames:
    """Every path this pipeline writes under `data/` or `figs/`, for one run.

    Three mutually exclusive shapes (plan §4.2's table):

    * ``smoke``                       -- `smoke_<year>_*`, named apart so it can never be confused
                                         with the campaign, and carrying the one evidence record of
                                         whichever source-equivalence check `cfg.source` selects.
    * the full campaign               -- selected by *exact equality* to the configured year range;
                                         these and only these are the wave prompt's contract names.
    * any other contiguous ``--years`` -- suffixed `<first>-<last>`, so a subset can never overwrite
                                         a campaign artifact.
    """
    data, figs = cfg.paths.data_dir, cfg.paths.figs_dir
    if smoke:
        tag = f"smoke_{cfg.smoke_year}"
        # One slot, named for the check the configured source actually runs (§A7.3 item 4): the
        # CDS path keeps the legacy `_r1_validation.json` unchanged, the RDA path -- where the R1
        # gate's 6-hourly operand cannot exist (§A9.1) -- writes the 2018 regression record.
        stem = "regression" if cfg.source == source_mod.RDA else "r1_validation"
        return OutputNames(
            profile=data / f"{tag}_profile.nc",
            states_csv=data / f"{tag}_jet_states.csv",
            summary=data / f"{tag}_summary.txt",
            panels=(figs / f"{tag}.png",),
            evidence=data / f"{tag}_{stem}.json",
        )
    first, last = years
    if (first, last) == (cfg.year_first, cfg.year_last):
        return OutputNames(
            profile=data / f"u250_natl_mjjas_{first}-{last}.nc",
            states_csv=data / f"jet_states_mjjas_{first}-{last}.csv",
            summary=data / "jet_states_summary.txt",
            panels=(figs / "double_jet_natl_panels.pdf", figs / "double_jet_natl_panels.png"),
            evidence=None,
        )
    return OutputNames(
        profile=data / f"u250_natl_mjjas_{first}-{last}.nc",
        states_csv=data / f"jet_states_mjjas_{first}-{last}.csv",
        summary=data / f"jet_states_summary_{first}-{last}.txt",
        panels=(figs / f"double_jet_natl_panels_{first}-{last}.pdf",
                figs / f"double_jet_natl_panels_{first}-{last}.png"),
        evidence=None,
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
                       help="single smoke season end to end, one panel, and the evidence check the "
                            "configured source can actually run: on 'cds_derived' both CDS "
                            "products and the R1 equivalence gate; on 'rda_hourly' the 2018 "
                            "regression against results/smoke_2018/")
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
        # The probe belongs to the source, not to the network: an unconditional CDS reachability
        # check would abort the RDA campaign at EXIT_PREFLIGHT before reading a single file, on
        # compute nodes that need not reach CDS at all (§A7.3 item 1, risk DR2). Both
        # implementations raise `download.PreflightError`, so the handler below is unchanged.
        try:
            source_mod.preflight(cfg, season_years, log)
        except download_mod.PreflightError as exc:
            log.error("%s", exc)
            return EXIT_PREFLIGHT
        # Two calls, two names (§A7.1, risk DR14): `--skip-download` inspects and never writes.
        if args.skip_download:
            source_mod.validate_seasons(cfg, season_years, smoke=smoke, log=log)
        else:
            source_mod.materialize_seasons(cfg, season_years, smoke=smoke, log=log)
        # The R1 gate compares two *raw* season files, so it stays exactly here -- and stays CDS
        # only: its 6-hourly operand does not and cannot exist on the RDA path (§A9.1). The RDA
        # analogue is the 2018 regression, which runs after `figure` because its operands do not
        # exist until `profile` and `classify` have written them.
        if smoke and cfg.source == source_mod.CDS:
            download_mod.check_r1_equivalence(cfg, cfg.smoke_year, out.evidence, log=log)

    if "profile" in args.stage:
        profile_mod.build_intermediate(cfg, season_years, out.profile, log=log)

    sanity_ok = True
    if "classify" in args.stage:
        result = classify_mod.run_classify(cfg, out.profile, out.states_csv, out.summary,
                                           smoke=smoke, log=log)
        sanity_ok = result.ok

    if "figure" in args.stage:
        figure_mod.run_figure(cfg, out.profile, out.states_csv, out.panels, smoke=smoke, log=log)

    # The RDA smoke run's evidence gate (§A7.3 item 3, §A9). It runs *here*, after `figure` and
    # immediately before the final return, for two reasons. Its operands -- the profile, the CSV
    # and the summary -- do not exist until `profile` and `classify` have written them, so in the
    # R1 gate's position a clean run would fail on missing files and a dirty one would silently
    # compare stale ones from an earlier invocation (risk DR12). And it matches O5's shape: the run
    # finishes, the figure is written, the result is reported, and only then does a failure set the
    # exit code -- a mismatch hands the operator a figure and a diff, not a bare traceback.
    regression_ok = True
    if smoke and cfg.source == source_mod.RDA:
        # Gated on the stages that produce its operands, exactly as the R1 gate is gated on
        # `"download" in args.stage`. `--stage` accepts arbitrary subsets, so an unconditional
        # placement would make `--smoke --stage download` compare three files that do not exist and
        # `--smoke --stage figure` compare stale ones -- the identical defect, merely moved.
        missing = [stage for stage in ("profile", "classify") if stage not in args.stage]
        if missing:
            # Never silent: a gate that is absent without saying so is the failure mode here.
            log.warning("--smoke: the 2018 regression check is SKIPPED because stage(s) %s were "
                        "not requested. Its operands (%s, %s, %s) would be missing, or stale from "
                        "an earlier invocation. This build is NOT gated against %s; re-run with "
                        "--stage all before trusting it.",
                        ",".join(missing), out.profile, out.states_csv, out.summary,
                        REGRESSION_BASELINE)
        else:
            from . import rda as rda_mod        # deferred: the CDS path never imports the loader

            record = rda_mod.check_regression_2018(cfg, REGRESSION_BASELINE, out, out.evidence,
                                                   log=log)
            regression_ok = bool(record["passed"])

    # Both gates are reported before either sets the exit code, and the run exits 1 once.
    if not sanity_ok:
        log.error("a hard sanity gate failed -- see %s. Reporting and stopping; thresholds are not "
                  "retuned without an operator ruling (plan §10 E2).", out.summary)
    if not regression_ok:
        log.error("the 2018 regression check FAILED -- see %s and the diff above. Reporting and "
                  "stopping; the loader, the seam and the thresholds are not changed to make it "
                  "match (addendum O3).", out.evidence)
    if not (sanity_ok and regression_ok):
        return EXIT_SANITY
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except Exception:
        logging.getLogger("double_jet").exception("run failed")
        return EXIT_ERROR
