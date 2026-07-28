"""Tripwire: one declared python toolchain, usable in every environment.

THE FAILURE. `pyproject.toml` declared only the *runtime* deps of the blog and
image scripts (google-genai, pillow, pyyaml, ruamel.yaml). `pytest` appeared in
neither it nor `uv.lock`, so `uv run pytest` failed on the host AND inside the
devcontainer. The only thing that made the tripwire suite runnable anywhere was
a hand-rolled `python -m pip install pytest pyyaml` line inside
repo-tripwires.yml — with two more `pip install pyyaml` lines in blog-ci.yml and
deploy-blog.yml, each an independent, undeclared copy of the dependency set.

The result was the shape this suite exists to catch: CI was green because CI
installed its own deps, while the ONE environment the fr-isolation contract
designates for running checks could not run them at all. `.devcontainer/
fr-profiles.yaml` made it worse by *documenting* `pytest scripts/tests/` as a
dev-profile check — a prescription no environment could satisfy, which nothing
compared against reality and which therefore survived indefinitely.

This is the same class the dev profile's own notes already record for kustomize
and helm ("GitHub's ubuntu runners ship both preinstalled, so CI stayed green
while only isolation failed"), one layer up: there the binary was missing, here
the *declaration* was.

These guards are deliberately offline and structural. They assert that the
declaration exists, that the lock agrees with it, that the container installs
it, and that no workflow quietly reintroduces a second source of truth.
"""

from __future__ import annotations

import pathlib
import re
import tomllib

import pytest

yaml = pytest.importorskip("yaml")

ROOT = pathlib.Path(__file__).resolve().parents[2]
PYPROJECT = ROOT / "pyproject.toml"
LOCK = ROOT / "uv.lock"
PROFILES = ROOT / ".devcontainer" / "fr-profiles.yaml"
DEVCONTAINER = ROOT / ".devcontainer" / "dev" / "devcontainer.json"
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))

# Packages pyproject.toml owns. A workflow that `pip install`s any of these has
# forked the dependency set: the lock stops being authoritative, and the two
# copies drift silently because nothing compares them.
OWNED = ("pyyaml", "pytest", "ruamel.yaml", "pillow", "google-genai")


def _pyproject() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def test_dev_group_declares_pytest() -> None:
    groups = _pyproject().get("dependency-groups", {})
    dev = " ".join(groups.get("dev", []))
    assert "pytest" in dev, (
        "pyproject.toml declares no `dev` dependency group containing pytest, so "
        "`uv run pytest` cannot work in any environment. CI's own `pip install "
        "pytest` would then be the only place the test runner is named — a "
        "dependency that exists solely inside a workflow file."
    )


def test_lock_is_in_step_with_the_dev_group() -> None:
    assert LOCK.exists(), "uv.lock is missing; `uv sync --frozen` cannot resolve."
    assert 'name = "pytest"' in LOCK.read_text(encoding="utf-8"), (
        "pytest is declared in pyproject.toml but absent from uv.lock — run "
        "`uv lock`. CI syncs with --frozen, so an unlocked declaration fails the "
        "run rather than silently installing something unpinned."
    )


def test_pytest_testpaths_are_configured() -> None:
    opts = _pyproject().get("tool", {}).get("pytest", {}).get("ini_options", {})
    testpaths = " ".join(opts.get("testpaths", []))
    assert "scripts/tests" in testpaths, (
        "[tool.pytest.ini_options] testpaths does not name scripts/tests. Without "
        "it a bare `pytest` collects from the repo root, which walks blog/public "
        "and the vendored .venv — slow, and it can collect files that are not "
        "this repo's tests."
    )


def test_devcontainer_installs_the_declared_deps() -> None:
    post = DEVCONTAINER.read_text(encoding="utf-8")
    assert "uv sync" in post, (
        "The dev devcontainer never syncs the project's python deps, so a shell "
        "inside fr-isolation has uv but no pytest and no pyyaml. That is the "
        "environment the isolation contract says to run checks in."
    )


def test_profile_prescribes_a_command_that_can_actually_run() -> None:
    purpose = yaml.safe_load(PROFILES.read_text(encoding="utf-8"))["profiles"]["dev"]["purpose"]
    if "pytest" not in purpose:
        pytest.skip("dev profile no longer prescribes pytest")
    assert "uv run pytest" in purpose, (
        "The dev profile documents a bare `pytest scripts/tests/`, but the "
        "container installs pytest into the project venv, where it is reachable "
        "as `uv run pytest`. A prescribed command that cannot run is worse than "
        "no prescription: it reads as a supported workflow and fails only for "
        "whoever tries it."
    )


def hand_rolled_deps(text: str) -> list[str]:
    """Lines that pip-install a package pyproject.toml owns.

    Comment lines are excluded, and that exclusion is load-bearing rather than
    cosmetic: each replaced step is DOCUMENTED in a comment sitting directly
    above its replacement ("this used to be `pip install pytest pyyaml`").
    Scanning raw lines made this guard fail on the very explanation of the fix
    — a detector that cannot tell code from prose about code, which is the
    failure class this suite exists to catch. It was caught by this test
    failing on its own first green run.
    """
    return [
        line.strip()
        for line in text.splitlines()
        if not line.lstrip().startswith("#")
        # `pip install uv` is the bootstrap, not a dependency — only flag the
        # packages pyproject.toml is supposed to own.
        and re.search(r"\bpip\s+install\b", line)
        and any(pkg in line.lower() for pkg in OWNED)
    ]


def test_the_detector_can_actually_fail() -> None:
    """A guard that cannot fire is worse than no guard — it reads as coverage.

    Narrowing `hand_rolled_deps` to fix its false positive risks narrowing it
    into uselessness, and the repo-wide assertion below would stay green either
    way. So pin both directions explicitly.
    """
    assert hand_rolled_deps("        run: pip install --quiet pyyaml")
    assert hand_rolled_deps("        run: python -m pip install pytest pyyaml")
    assert not hand_rolled_deps("      # this used to be `pip install pytest pyyaml`")
    assert not hand_rolled_deps("        run: pip install uv")


@pytest.mark.parametrize("wf", WORKFLOWS, ids=lambda p: p.name)
def test_no_workflow_hand_rolls_owned_deps(wf: pathlib.Path) -> None:
    offenders = hand_rolled_deps(wf.read_text(encoding="utf-8"))
    assert not offenders, (
        f"{wf.name} installs deps that pyproject.toml owns: {offenders}. "
        "Use `uv sync --group dev --frozen` so the lock is the single source of "
        "truth; a second copy drifts without any signal."
    )
