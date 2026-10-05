"""Tripwire: nothing in this repo may RECOMMEND `ovms_requests_success` as the
retrieval tier's usage signal.

Contract source of truth:
docs/superpowers/specs/2026-09-19--infer--ovms-pool-watchdog-activity-signal-design.md
(section 5, "The repo's usage query measures readiness probes")

`ovms_requests_success` is what `readinessProbe` moves — it hits
`/v2/models/bge-reranker-v2-m3/ready` every 10s regardless of traffic, so the
reranker accrues ~8,600/day of it whether or not a client exists, while
`bge-m3` (whose probe hit `startupProbe` once and then never again) reads ~0
however much real traffic it serves. Before this phase, three places told a
reader to use exactly that series to answer "is anyone calling this?":
`agents/rules/frank-gotchas.md`, `docs/runbooks/frank-gotchas/igpu-dra.md`,
and the `--metrics_enable` comment in
`apps/ovms-retrieval/manifests/deployment.yaml`. The correct counter is
`ovms_requests_accepted` (paired with `_rejected`/`_fail` for guard refusals).

## Why this is not a bare string ban

`ovms_requests_success` is legitimately NAMED in several places whose whole
point is to warn a reader off it: this docstring, the spec, the plan journal,
test docstrings elsewhere in this suite, and the corrected comments this
phase writes (which say "not `ovms_requests_success`, which..." right next to
the name). Banning the string outright would forbid explaining the mistake,
which is the opposite of what phase 5 exists to do. So the guard is built in
two layers:

1. **Whole-file exemptions** for material whose job is to narrate the
   incident and cannot restructure itself around a contextual check: the
   journal (`docs/superpowers/journals/`), this plan's own phase files
   (`docs/superpowers/plans/2026-09-19--infer--ovms-pool-watchdog-activity-signal/`),
   the spec itself (which quotes the broken advice verbatim, in a blockquote,
   specifically in order to correct it a few lines later), and this test
   suite (`scripts/tests/`, which needs to be able to name the series in
   docstrings and fixtures without tripping its own guard).

2. **A contextual check everywhere else**: flag `ovms_requests_success` when
   it sits within a short reach of an advisory phrase — "ask", "check",
   "compare … via", "query", "use", "run", "the useful series" — with no
   negation ("not"/"never") or a DIFFERENT metric name in between, and
   separately flag the literal PromQL form `increase(ovms_requests_success`
   outright (that function call is never a legitimate thing to write down
   about this series, only ever the wrong recommendation).

## Why not just match `increase(ovms_requests_success`

That was the phase's original plan (see finding f4 in the plan journal): a
runbook line phase 4 shipped read "compare request volume via
ovms_requests_success" — advisory prose recommending the series, with no
PromQL function anywhere near it. A guard scoped to the function-call form
would have missed exactly the shape that already slipped through once on this
branch. The advisory-phrase check below is built to catch that shape
directly: `test_the_advisory_phrase_check_would_have_caught_phase_4s_regression`
pins it against the runbook's own historical (pre-fix) wording.
"""

from __future__ import annotations

import pathlib
import re
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[2]

METRIC = "ovms_requests_success"

# Whole-file/whole-directory exemptions — material that narrates the mistake
# in order to correct it, and cannot be restructured around a per-mention
# contextual check without destroying the narrative. See the module
# docstring's "Why this is not a bare string ban".
_EXEMPT_PREFIXES = (
    "docs/superpowers/journals/",
    "docs/superpowers/plans/2026-09-19--infer--ovms-pool-watchdog-activity-signal/",
    "docs/superpowers/specs/2026-09-19--infer--ovms-pool-watchdog-activity-signal-design.md",
    "scripts/tests/",
)

# The literal PromQL function call. There is no legitimate reason to WRITE
# this down other than recommending it — a doc explaining why the series is
# wrong describes it in prose ("the readiness probe", "counts ModelReady"),
# it does not hand the reader a ready-to-paste query for it.
_PROMQL_FORM = re.compile(r"increase\(\s*" + re.escape(METRIC) + r"\b", re.IGNORECASE)

# An advisory verb/phrase governing the metric name within a short reach,
# with nothing between them that would mark the mention as a warning (a
# negation) or redirect it to a DIFFERENT, correct series name. The lazy
# bounded quantifier keeps the reach short (60 chars) so the check fires on
# "ask ... ovms_requests_success" and "compare ... via ovms_requests_success"
# but not on a sentence that happens to contain both an advisory verb and the
# metric name many words apart for unrelated reasons.
_ADVISORY_TO_METRIC = re.compile(
    r"\b(?:ask|check|compare|query|use|run|useful)\b"
    r"(?:(?!\bnot\b|\bnever\b|ovms_requests_(?:accepted|rejected|fail)\b)[\s\S]){0,60}?"
    + re.escape(METRIC)
    + r"\b",
    re.IGNORECASE,
)


def _tracked_doc_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "*.md", "*.yaml", "*.yml"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [line for line in out.splitlines() if line]


def _recommendations() -> list[tuple[str, str]]:
    """(path, matched snippet) for every tracked doc file that recommends
    `ovms_requests_success`, outside the whole-file exemptions."""
    hits: list[tuple[str, str]] = []
    for rel_path in _tracked_doc_files():
        if any(rel_path.startswith(prefix) for prefix in _EXEMPT_PREFIXES):
            continue
        text = (REPO / rel_path).read_text(encoding="utf-8", errors="ignore")
        if METRIC not in text:
            continue
        match = _PROMQL_FORM.search(text) or _ADVISORY_TO_METRIC.search(text)
        if match:
            hits.append((rel_path, " ".join(match.group(0).split())))
    return hits


def test_no_doc_recommends_the_probe_dominated_usage_query():
    hits = _recommendations()
    assert not hits, (
        "the following tracked files recommend ovms_requests_success as a "
        "usage signal — it is dominated by readinessProbe traffic (~8,600/"
        "day for bge-reranker-v2-m3, ~0 for bge-m3 regardless of real "
        "traffic); the correct counter is ovms_requests_accepted:\n  - "
        + "\n  - ".join(f"{path}: {snippet}" for path, snippet in hits)
    )


def test_the_advisory_phrase_check_would_have_caught_phase_4s_regression():
    """Finding f4 (plan journal, phase 4): the alert runbook this branch added
    told the responder to 'compare request volume via ovms_requests_success'
    — advisory prose, no PromQL function anywhere near it. A guard scoped to
    `increase(ovms_requests_success` alone would not have caught it. Pin the
    historical wording directly so a future narrowing of the advisory check
    cannot quietly stop catching this shape."""
    regression_shape = (
        "runbook: compare request volume via ovms_requests_success against "
        "the pool-watchdog's own result lines."
    )
    assert _PROMQL_FORM.search(regression_shape) or _ADVISORY_TO_METRIC.search(
        regression_shape
    ), (
        "the advisory-phrase check no longer catches phase 4's own "
        "regression shape (an advisory verb governing the metric name with "
        "no PromQL function nearby) — see finding f4 in the plan journal"
    )


def test_the_check_does_not_flag_a_mention_that_warns_against_the_series():
    """The corrected alert runbook (frank#813, finding f4's fix) still NAMES
    `ovms_requests_success` in order to warn a responder off it: 'compare
    request volume via ovms_requests_accepted (NOT ovms_requests_success,
    which counts the readiness probe...)'. That must not flag — a guard that
    forbids naming the series at all forbids explaining the mistake."""
    corrected_shape = (
        "compare request volume via ovms_requests_accepted (NOT "
        "ovms_requests_success, which counts the readiness probe and moves "
        "whether or not a client exists) against the pool-watchdog's own "
        "result lines."
    )
    assert not _PROMQL_FORM.search(corrected_shape)
    assert not _ADVISORY_TO_METRIC.search(corrected_shape)


def test_alert_runbook_is_already_corrected():
    """Lock in frank#813's fix to the live alert runbook — a regression here
    would be caught by the general scan too, but this pins the specific site
    finding f4 named directly."""
    alert_rules = REPO / "apps/grafana-alerting/manifests/alert-rules-cm.yaml"
    text = alert_rules.read_text(encoding="utf-8")
    assert "ovms_requests_accepted" in text
    assert not _PROMQL_FORM.search(text)
    assert not _ADVISORY_TO_METRIC.search(text)
