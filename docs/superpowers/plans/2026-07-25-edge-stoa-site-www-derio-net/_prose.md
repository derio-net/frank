# agentic-stoa/site → www.derio.net

## What this plan does

`www.derio.net` currently answers with twelve bytes of Caddy string literal.
This plan replaces that with a real, versioned, container-delivered page built
from the new private `agentic-stoa/site` repo, and brings the vhost up to the
same standard the blog already enjoys — access logging into VictoriaLogs, a
CrowdSec bouncer, an uptime probe wired to Layer 17, analytics, and (new for
both sites) hardened response headers.

Spec: `docs/superpowers/specs/2026-07-25--edge--stoa-site-www-derio-net-design.md`.

## Shape of the work

Six phases. Five are agentic; the last collects every operator-only action.

- **Phase 1** scaffolds and publishes the site repo — Astro, a Dockerfile whose
  runtime stage matches the blog's proven `caddy:2.9-alpine` shape, and one CI
  workflow that serves both forges. Authored in a scratch directory and pushed
  directly, because the repo is empty and there is no base branch to PR against.
- **Phase 2** stands up the `www` app on Hop and rewrites the Caddy vhost.
- **Phase 3** wires automated delivery: the mirror trigger and the
  `site-promotion` pipeline that moves an image tag into this repo.
- **Phase 4** adds the uptime probe and widens the Layer 17 alert.
- **Phase 5** writes the docs, gotchas and runbook entries.
- **Phase 6** is the operator's single pass.

Phases 1 and 2 are independent roots and can proceed in either order.

## The two decisions worth understanding before reading the phases

### The Caddy fallback is what makes the ordering safe

The obvious sequencing problem: merging a vhost that proxies to `www-system`
would break `www.derio.net` outright, because the first image cannot exist until
the operator has finished enrolling the repo in the mirror — and that is phase
6, after the merge.

Rather than choreograph the merge around that, the vhost carries a
`handle_errors` block that responds `"Coming soon." 200` whenever the backend is
unreachable. The site therefore degrades to *exactly today's behaviour* instead
of to a 502, the PR can merge at any time, and the ordering dependency
disappears. The fallback keeps earning its place afterwards: a crashed `www` pod
shows a holding page rather than a gateway error.

This is why phase 2 does not depend on phase 1.

### A broken credential was found, not created

While verifying the design against the live cluster, `frank-gitops-push` turned
out to have been in `SecretSyncedError` since 2026-07-18 — 1477 consecutive
failures. `github-app-derio-key` is missing from `tekton-pipelines`, and the ESO
`GithubAccessToken` generator resolves `auth.privateKey.secretRef` in the
*consuming* namespace. Its sibling `github-app-stoa-key` is in the right place,
which is why the mirror token syncs and this one does not.

This predates the plan, but it matters twice over: `site-promotion` cannot push
without it, and **`cnc-promotion` — the existing consumer — cannot push either**,
so CNC tag promotion into `derio-net/frank` is silently broken right now. The
repair needs SOPS and the age key, neither of which exists in the agent pod, so
it opens phase 6. Fixing it for this plan fixes CNC as a side effect.

## Testing approach

Each agentic phase is red-green. The tests are static assertions over manifests
and config under `scripts/tests/`, in the same style as the repo's existing
tripwires (`test_tekton_ignore_rules_no_arrays.py`,
`test_crowdsec_lapi_persistence.py`) — they encode the traps this estate has
already paid for, so a future edit that reintroduces one fails loudly:

- the image pin carries the CI-owned marker and a real sha
- HSTS ships **without** `preload` (a one-way door across every `*.derio.net`)
- the CSP admits `counter.derio.net` and nothing else, so analytics survives
- the promotion loop is the idempotent race-safe shape, not `pull --rebase`
- no array-item `jqPathExpressions` freeze the EventListener triggers array

Phase 2 additionally runs `caddy validate` before the config can reach the
public edge, and phase 4 parses the alert-rules ConfigMap.

## What this plan deliberately does not do

The conversion funnel. Astro was chosen so the funnel can land later without a
re-platform, but nothing in this plan builds forms, tracking beyond pageviews,
or a CMS. The apex `derio.net` also stays untouched — it is Cloudflare-hosted
and out of scope; only `www` is ours.
