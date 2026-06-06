# Health Bridge — Auto-Close Healed Bug Issues — Design

**Date:** 2026-06-06
**Status:** Spec
**Repo:** frank (deploy + docs) · derio-net/health-bridge (code)
**Layer:** obs
**Related:**
- `docs/superpowers/implemented/plans/2026-04-04--obs--health-bridge-service/` (built the bridge; established the frank-hosts-the-plan / code-lives-in-health-bridge split this spec reuses)
- `docs/superpowers/specs/2026-05-31--obs--feature-health-alert-resilience-design.md` (complementary: prevents *false* dead transitions at the Grafana layer; this spec closes *legitimate* bug issues after heal at the bridge layer — no file overlap)
- `blog/content/docs/operating/16-health-bridge/index.md`, `blog/content/docs/building/23-health-bridge/index.md`
- Evidence: `derio-net/frank-ops` issues #38, #39, #40

## Problem

When a feature-health alert transitions to `dead`, health-bridge files a
`[Bug] <alertname> is dead — <summary>` issue in the tracker's repo
(`frank-ops`, `willikins`). When the alert later **resolves**, the bridge
flips the Lifecycle tile back to `healthy` and comments on the tracker —
but **never touches the bug issue it created**. Transient incidents leave
permanently-open bugs that the operator must close by hand.

Evidence (frank-ops, tracker comment history):

| Bug | Created (dead) | Alert resolved | Bug state today |
|-----|----------------|----------------|-----------------|
| #38 (L24 Traefik) | 2026-06-04 16:52:58 | 2026-06-04 16:55:59 (+3 min) | **still open** |
| #39 (L8 fluent-bit) | 2026-06-04 16:53:04 | 2026-06-04 17:38:03 (+45 min) | **still open** |
| #40 (L24 DatasourceError) | 2026-06-05 20:43:43 | 2026-06-05 20:46:34 (+3 min) | closed manually 2026-06-06 |

Key observation: in **every** recent incident the `resolved` webhook
reliably reached the bridge (the `healthy` tracker comments prove
delivery, minutes after each dead transition). The gap is purely a missing
code path, not missing signal.

### Latent bug discovered en route: shared-alertname collision

Grafana's synthetic `DatasourceError` alertname is shared across layers —
L8 and L24 have both produced `[Bug] DatasourceError is dead — …` issues.
The existing creation-dedup `HasOpenBug(repo, alertName)` matches **title
prefix only** (`[Bug] DatasourceError is dead`), so:

- an open L24 DatasourceError bug **suppresses creation** of a legitimate
  L8 DatasourceError bug, and
- a naive close-by-alertname would close the *wrong layer's* bug.

Both creation-dedup and close must disambiguate by the **feature issue
ref** already embedded in every bug body
(`**Feature Issue:** derio-net/frank-ops#24`).

## Goal

When an alert resolves, the bridge automatically closes the open bug
issue(s) it created for that alert — with a heal comment carrying the
resolution time and outage duration — so transient incidents are
self-cleaning end to end: dead → bug filed → healed → bug closed.

## Decisions Captured (operator Q&A, 2026-06-06)

1. **Mechanism: webhook-close only.** On each `resolved` alert, find and
   close matching open bugs. No Grafana-state reconciler, no new
   credentials — evidence shows resolved webhooks arrive reliably. Stale
   #38/#39 get a one-time manual close in the post-merge Test Plan.
2. **Flap handling: new issue per incident.** Creation logic unchanged;
   each dead transition files a fresh bug. Auto-close keeps the open
   count at zero between incidents.
3. **health-bridge working copy:** clone at
   `~/Docs/projects/DERIO_NET/health-bridge`.
4. **Post-merge Test Plan: full smoke + cleanup** (synthetic dead →
   bug created → resolved → bug auto-closed, then close #38/#39).

## Design

### health-bridge (Go) — v0.3.0

All changes in `bridge.go` / `github.go` / `bridge_test.go`, following the
existing httptest-mock + `setGitHubURLs` test pattern.

**1. `FindOpenBugs(repo, alertName string, featureNumber int) ([]int, error)`**
(github.go) — replaces `HasOpenBug` as the single bug-matching primitive:

- `GET /repos/{org}/{repo}/issues?labels=bug&state=open&per_page=50`
  (same call `HasOpenBug` makes today), parsing `number`, `title`, `body`.
- An issue matches when **both**:
  - title has prefix `[Bug] <alertName> is dead`, and
  - body contains the exact line fragment
    `**Feature Issue:** <org>/<repo>#<number>\n` — **newline-terminated**,
    because `…#2` is a substring of `…#24`; the trailing `\n` is
    guaranteed by `CreateBugIssue`'s body template (`#%d\n**Alert:**`).
- Returns all matching issue numbers (closing all catches historical
  duplicates from the pre-dedup era).

**2. Creation dedup uses the same primitive** — the `newState == "dead"`
path calls `FindOpenBugs` (exists ⇔ len > 0) instead of `HasOpenBug`,
fixing the shared-alertname suppression bug. `HasOpenBug` is removed.

**3. `CloseBugIssue(repo string, number int, comment string) error`**
(github.go):

- posts the heal comment via the existing `AddIssueComment`,
- then `PATCH /repos/{org}/{repo}/issues/{number}` with
  `{"state": "closed", "state_reason": "completed"}`.
- Comment failure logs a warning but does not abort the close (mirrors
  the existing comment-failure tolerance on the tracker path).

**4. `FormatHealComment(alert Alert) string`** (bridge.go) — markdown:
alert name, resolved time (`EndsAt`), outage duration computed from
RFC3339 `StartsAt`→`EndsAt` (omitted if either fails to parse), and the
standard `*Automated by health-bridge*` footer.

**5. Wire into `processAlert`** (bridge.go): immediately after the
lifecycle update — **before** the `lastState` dedup early-return — when
`alert.Status == "resolved"`:

```go
for _, n := range FindOpenBugs(repo, alertName, number) {
    CloseBugIssue(repo, n, FormatHealComment(alert))
}
```

- **Not gated by the `lastState` dedup**: dedup is keyed per *tracker*
  (multiple alerts share one tracker), and a deduped repeat-resolved must
  still close. The operation is naturally idempotent — no open bugs ⇒
  no-op.
- **Not gated by severity**: only critical alerts create bugs, but gating
  the close on `severity == "critical"` would leave a stale bug if a
  rule's severity label is edited between fire and resolve. The cost of
  no gate is one GET per resolved alert (rare — a few per day at worst).
- Errors in the close path log warnings and do not fail the alert
  (lifecycle update already succeeded — same posture as comment/bug
  creation failures today).

**Out of scope (documented, deliberate):**
- No reconciler/startup sweep (Q&A decision 1 — YAGNI given webhook
  reliability; revisit only if a stale bug recurs).
- No reopen-recent-issue flap handling (Q&A decision 2).
- The pre-existing overlapping-alerts dedup limitation (two alerts on the
  same tracker both going dead in the same window suppresses the second
  bug's creation via `lastState`) is unchanged — separate concern, noted
  for the record.

### frank (deploy + docs)

- `apps/health-bridge/manifests/deployment.yaml` — image
  `ghcr.io/derio-net/health-bridge:v0.2.0` → `v0.3.0`.
- `blog/content/docs/operating/16-health-bridge/index.md` — document the
  auto-close behavior (new section), update the "Duplicate bug issues"
  troubleshooting entry (`HasOpenBug` → `FindOpenBugs` semantics,
  shared-alertname fix).
- `blog/content/docs/building/23-health-bridge/index.md` — short
  retroactive addendum noting the v0.3.0 close-the-loop fix (fix/extension
  workflow: update existing posts, no new post).

### Release flow (unchanged, tag-driven)

PR to `derio-net/health-bridge` → operator merges → tag `v0.3.0` pushed →
GitHub Actions builds `ghcr.io/derio-net/health-bridge:v0.3.0` → frank PR
(image bump + docs) merges → ArgoCD syncs.

## Test Plan (post-merge — operator-driven)

After both PRs merge and ArgoCD rolls the new image:

- [ ] Pod healthy on v0.3.0: `kubectl get pods -n monitoring -l app=health-bridge`
- [ ] Smoke — fire: direct webhook (`status: firing`, `severity: critical`,
      `github_issue: frank-ops#13`, alertname `smoke-auto-close`) →
      verify a `[Bug] smoke-auto-close is dead — …` issue is created in
      frank-ops.
- [ ] Smoke — heal: same alert with `status: resolved` + `endsAt` →
      verify the bug issue is **closed** with a heal comment (resolved
      time + duration), `state_reason: completed`.
- [ ] Tracker side-effects normal: frank-ops#13 Lifecycle back to
      `healthy`, dead/healthy comments present.
- [ ] One-time cleanup: close stale #38 and #39 with a manual healed
      comment referencing this spec.
- [ ] Bridge logs show `Closed bug issue` lines, no errors.

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Resolved webhook missed during bridge downtime → bug stays open | Accepted (Q&A): evidence shows reliable delivery; manual close remains possible; reconciler is the documented follow-up if it recurs. |
| Shared alertname closes wrong layer's bug | Feature-ref body match, newline-terminated to avoid `#2`/`#24` prefix collision. |
| Close fires on flapping alert that immediately re-fires | New dead transition files a fresh bug (Q&A decision 2) — nothing lost. |
| GitHub API close fails | Logged warning; alert processing unaffected; next resolved event retries naturally. |
| >50 open bugs paginate past the search | Open-bug count is single digits in practice; per_page=50 retained from `HasOpenBug`. |

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|------------|
| 2026-06-06--obs--health-bridge-bug-auto-close | `derio-net/frank` (hosts plan; phases target both repos) | `2026-06-06--obs--health-bridge-bug-auto-close` | — |
