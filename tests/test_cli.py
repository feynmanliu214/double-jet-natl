"""The entry point runs from a clean shell, and stage parsing behaves (plan §4.6, M9, R13).

The two `--help` tests are subprocess tests on purpose. Importing `double_jet.cli` inside pytest
proves nothing about `sys.path`: pytest has already arranged the path. Only spawning a fresh
interpreter from the repository root exercises the failure mode R13 names -- running
`scripts/double_jet.py` puts `scripts/`, not the repo root, on `sys.path`, so `import double_jet`
would fail without that file's shim. `PYTHONPATH` is stripped from the child's environment so the
test cannot pass by inheriting a path this session happened to set.

`cli.py` imports `download`, `profile`, `classify`, `figure` and `explorer` only inside `run()`,
so `--help` must succeed no matter what state those modules are in.
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:                      # `pytest tests/` from any cwd
    sys.path.insert(0, str(REPO_ROOT))

from double_jet import cli                              # noqa: E402
from double_jet import classify as classify_mod         # noqa: E402
from double_jet import explorer, figure, profile, rda, source   # noqa: E402

TIMEOUT_S = 300


def _run(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    return subprocess.run([sys.executable, *args], cwd=REPO_ROOT, env=env,
                          capture_output=True, text=True, timeout=TIMEOUT_S)


# --- the documented invocations (M9, R13) -------------------------------------------------------

def test_module_entry_point_help_exits_zero():
    """`python -m double_jet --help` -- the canonical spelling, and what the job scripts run."""
    proc = _run("-m", "double_jet", "--help")
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert "--config" in proc.stdout
    assert proc.stdout.lower().startswith("usage")


def test_script_shim_help_exits_zero():
    """`python scripts/double_jet.py --help` -- the wave prompt's spelling, via the sys.path shim."""
    proc = _run("scripts/double_jet.py", "--help")
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert "--config" in proc.stdout
    assert proc.stdout.lower().startswith("usage")


def test_both_spellings_print_the_same_help():
    module = _run("-m", "double_jet", "--help")
    shim = _run("scripts/double_jet.py", "--help")
    assert module.stdout == shim.stdout


# --- stage parsing ------------------------------------------------------------------------------

def test_parse_stages_accepts_all():
    assert cli.parse_stages("all") == cli.STAGES
    assert cli.parse_stages(" all ") == cli.STAGES
    assert cli.STAGES == ("download", "profile", "classify", "figure", "explorer")


def test_parse_stages_returns_a_subset_in_canonical_order():
    assert cli.parse_stages("classify,figure") == ("classify", "figure")
    assert cli.parse_stages("figure,classify") == ("classify", "figure")     # order is canonical
    assert cli.parse_stages("figure,download") == ("download", "figure")
    assert cli.parse_stages("classify, classify") == ("classify",)           # deduplicated
    assert cli.parse_stages("profile") == ("profile",)


def test_parse_stages_rejects_an_unknown_stage():
    with pytest.raises(argparse.ArgumentTypeError, match="must be 'all' or a comma-separated"):
        cli.parse_stages("classify,plot")
    with pytest.raises(argparse.ArgumentTypeError):
        cli.parse_stages("")


def test_stage_defaults_are_shape_dependent(tmp_path, monkeypatch):
    """§B12.3 (§B10 item 4, D4): `--stage` defaults to None and `run()` resolves it by run shape.

    Three assertions, and the third is the one that earns its keep. The parser must hand `run()` a
    `None` rather than a stage tuple; `default_stages` must return the two documented tuples -- the
    smoke run keeps the panel figure, which D4 does *not* retire as its M6 deliverable, while the
    campaign ends at the explorer; **and** `cli.run()` must actually dispatch them. Asserting on
    `default_stages` alone would pass while `python -m double_jet --config ...` crashed on `None` at
    the first `"download" in stages`, which is the whole failure mode this test exists to catch.

    All seven stage callables are mocked -- the six-mock pattern of
    `test_rda.test_smoke_without_profile_and_classify_skips_the_regression_and_says_so`, plus
    `explorer.run_explorer` -- so no file is read or written and no CDS or archive access occurs.
    `configure_logging` is replaced because `cli.run` calls `logging.basicConfig(force=True)`, which
    would tear down pytest's handlers. The working directory is moved to `tmp_path` because the
    frozen config's `data_dir`/`figs_dir` and the campaign's `results/season_summary.csv` are all
    relative, and `run` mkdirs them: without the chdir the test would create directories in the
    repository.
    """
    args = cli.build_parser().parse_args(["--config", "configs/double_jet.yaml"])
    assert args.stage is None, "the default is no longer cli.STAGES; run() resolves it (D4)"
    assert args.smoke is False
    assert args.years is None
    assert args.skip_download is False

    assert cli.default_stages(smoke=True) == ("download", "profile", "classify", "figure")
    assert cli.default_stages(smoke=False) == ("download", "profile", "classify", "explorer")

    monkeypatch.setenv("SCRATCH", str(tmp_path / "scratch"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "configure_logging", lambda level: logging.getLogger("double_jet"))

    calls: list[str] = []
    monkeypatch.setattr(source, "preflight", lambda *a, **k: calls.append("preflight"))
    monkeypatch.setattr(source, "materialize_seasons", lambda *a, **k: calls.append("materialize"))
    monkeypatch.setattr(profile, "build_intermediate",
                        lambda *a, **k: calls.append("profile") or Path("x"))
    monkeypatch.setattr(classify_mod, "run_classify",
                        lambda *a, **k: calls.append("classify") or argparse.Namespace(ok=True))
    monkeypatch.setattr(figure, "run_figure", lambda *a, **k: calls.append("figure"))
    monkeypatch.setattr(explorer, "run_explorer", lambda *a, **k: calls.append("explorer"))
    monkeypatch.setattr(rda, "check_regression_2018",
                        lambda *a, **k: calls.append("regression") or {"passed": True})

    def dispatched(smoke: bool) -> list[str]:
        calls.clear()
        ns = argparse.Namespace(config=REPO_ROOT / "configs" / "double_jet.yaml",
                                preflight_network=False, smoke=smoke, years=None, stage=None,
                                skip_download=False, log_level="INFO")
        assert cli.run(ns) == cli.EXIT_OK
        return list(calls)

    # The frozen config is `source: rda_hourly`, so the smoke shape also runs the 2018 regression
    # gate -- it is gated on `profile` and `classify`, both of which the smoke default requests.
    # The campaign shape is not a smoke run, so it never reaches that gate and ends at `explorer`.
    assert dispatched(smoke=True) == ["preflight", "materialize", "profile", "classify", "figure",
                                      "regression"]
    assert dispatched(smoke=False) == ["preflight", "materialize", "profile", "classify",
                                       "explorer"]


# --- flag combinations --------------------------------------------------------------------------

def test_smoke_and_years_are_mutually_exclusive():
    """A smoke run is a fixed single season; asking for both is a contradiction, not a merge."""
    parser = cli.build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--config", "configs/double_jet.yaml", "--smoke", "--years", "2000-2010"])
    assert exc.value.code == 2

    # each alone is fine
    assert parser.parse_args(["--config", "configs/double_jet.yaml", "--smoke"]).smoke is True
    assert parser.parse_args(
        ["--config", "configs/double_jet.yaml", "--years", "2000-2010"]).years == (2000, 2010)


def test_config_is_required():
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args([])
    assert exc.value.code == 2


def test_exit_codes_are_distinct():
    codes = (cli.EXIT_OK, cli.EXIT_SANITY, cli.EXIT_PREFLIGHT, cli.EXIT_ERROR)
    assert codes == (0, 1, 2, 3)
