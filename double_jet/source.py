"""Stage-1 dispatch: which source supplies the daily mean (deviation D3, addendum §A7.1).

This module is deliberately the *only* place in the pipeline that branches on `cfg.source`.
Everything else -- `cli.py`, `profile.build_intermediate` -- calls a name from here and never learns
which of `download.py` (CDS derived product) or `rda.py` (the RDA hourly archive on `/glade`)
answered it. Adding a third source would touch this file and nothing else.

Two properties are load-bearing and must not be "simplified away":

* **`materialize_seasons` and `validate_seasons` are two functions, never one** (risk DR14).
  `download.run_download` / `rda.ensure_local` *mutate* the raw cache; `download.ensure_downloaded`
  / `rda.validate_local` only *inspect* it and raise listing every unusable season. That separation
  is exactly what `--skip-download` means, and one name covering both meanings would let the flag
  materialize seasons -- the opposite of what it promises.
* **`preflight` takes the years.** There is no fixed season to probe: `--smoke` wants 2018 and
  `--years` wants its own first season. The CDS probe takes only a logger, so the signature
  difference is absorbed here rather than at the call site. It raises `download.PreflightError`,
  the type `cli.run` already maps to `EXIT_PREFLIGHT`, so the CLI's exception handling is unchanged
  by the addition of a second source.

Every import is deferred inside its function -- the pattern `profile.build_intermediate` and
`download.check_r1_equivalence` already use -- so this module can be imported from either side
without creating a cycle, and so the CDS path never pays for importing `rda.py` (or vice versa).
"""

from __future__ import annotations

import logging

from .config import Config, ConfigError

RDA = "rda_hourly"
CDS = "cds_derived"


def _use_rda(cfg: Config) -> bool:
    """True for the RDA archive, False for the CDS derived product; anything else is an error.

    `config.load_config` validates `source` against the same set, so this is defence in depth: a
    `Config` assembled by hand in a test, or a future third source added to the config without a
    dispatch entry here, must fail loudly at the branch rather than quietly taking the CDS path.
    """
    source = getattr(cfg, "source", None)
    if source == RDA:
        return True
    if source == CDS:
        return False
    raise ConfigError(
        f"unknown stage-1 source {source!r}: expected {CDS!r} (the CDS derived daily product) or "
        f"{RDA!r} (the RDA hourly archive). See addendum §A4.1."
    )


def request_for(cfg: Config, year: int) -> dict:
    """The request/sidecar payload for one season, in the configured source's own shape.

    Rebuilt from the config every time (O6) -- never read back off the on-disk sidecar, which is
    the artifact this is compared *against*, not a substitute for it.
    """
    if _use_rda(cfg):
        from .rda import build_rda_request

        return build_rda_request(cfg, year)

    from .download import build_request

    return build_request(cfg, year)


def season_is_complete(cfg: Config, year: int) -> tuple[bool, str]:
    """(ok, one-line reason) for one season's raw cache entry, per the configured source.

    Both implementations enforce the same three-part contract of plan §4.1: the `.nc` opens with
    the expected shape, the `.request.json` sidecar exists, and it equals the request that would be
    issued now. Because the two sidecars differ in their `source` key, a CDS-built and an RDA-built
    season at the same path refuse each other (§A5.3).
    """
    if _use_rda(cfg):
        from .rda import season_is_complete as _impl

        return _impl(cfg, year)

    from .download import season_is_complete as _impl

    return _impl(cfg, year)


def materialize_seasons(cfg: Config, years: list[int], smoke: bool,
                        log: logging.Logger) -> None:
    """**Writes.** Bring every requested season into the raw cache, skipping those already complete.

    The download-stage body. Never call this for `--skip-download`; see `validate_seasons`.
    """
    if _use_rda(cfg):
        from .rda import ensure_local

        ensure_local(cfg, years, smoke, log)
        return

    from .download import run_download

    run_download(cfg, years, smoke, log)


def validate_seasons(cfg: Config, years: list[int], smoke: bool,
                     log: logging.Logger) -> None:
    """**Never writes.** Report every requested season that is missing or does not match, and raise.

    This is `--skip-download`'s entire meaning: inspect the cache, fail loudly with the full list,
    and create nothing. Both implementations report every offender together rather than the first.
    """
    if _use_rda(cfg):
        from .rda import validate_local

        validate_local(cfg, years, smoke, log)
        return

    from .download import ensure_downloaded

    ensure_downloaded(cfg, years, smoke, log)


def preflight(cfg: Config, years: list[int], log: logging.Logger) -> None:
    """Fail in seconds with a labelled message, before the expensive part (plan §5.0).

    CDS: resolve and reach both endpoints. RDA: the archive root is readable and the first day of
    the first requested season opens at the configured level. Either way the failure type is
    `download.PreflightError`, so `cli.run` returns `EXIT_PREFLIGHT` unchanged.

    `years` is passed because there is no fixed season to probe -- it is the run's own first season
    that must be reachable, not some hardcoded one. The CDS probe ignores it (the network is not
    per-season), and that asymmetry is absorbed here.
    """
    if _use_rda(cfg):
        from .rda import preflight_archive

        preflight_archive(cfg, years, log)
        return

    from .download import preflight_network

    preflight_network(log)
