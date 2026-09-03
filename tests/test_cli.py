"""The entry point runs from a clean shell, and stage parsing behaves (plan §4.6, M9, R13).

The two `--help` tests are subprocess tests on purpose. Importing `double_jet.cli` inside pytest
proves nothing about `sys.path`: pytest has already arranged the path. Only spawning a fresh
interpreter from the repository root exercises the failure mode R13 names -- running
`scripts/double_jet.py` puts `scripts/`, not the repo root, on `sys.path`, so `import double_jet`
would fail without that file's shim. `PYTHONPATH` is stripped from the child's environment so the
test cannot pass by inheriting a path this session happened to set.

`cli.py` imports `download`, `profile`, `classify` and `figure` only inside `run()`, so `--help`
must succeed no matter what state those modules are in.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:                      # `pytest tests/` from any cwd
    sys.path.insert(0, str(REPO_ROOT))

from double_jet import cli                              # noqa: E402

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
    assert cli.STAGES == ("download", "profile", "classify", "figure")


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


def test_stage_defaults_to_all():
    args = cli.build_parser().parse_args(["--config", "configs/double_jet.yaml"])
    assert args.stage == cli.STAGES
    assert args.smoke is False
    assert args.years is None
    assert args.skip_download is False


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
