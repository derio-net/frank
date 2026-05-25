# Hop Blog Edge Monitoring — Rework 1: fix the lying digest

Rework plan against `2026-05-23--obs--hop-blog-edge-monitoring` (phase 05, the
`ai-alert-helper` daily digest). See `_meta.yaml` for `parent_plan` and
`origin_items`.

## Why

The "📊 Yesterday on the Frank blog" Telegram digest was wrong in four ways,
all confirmed against live VictoriaLogs/GoatCounter data on 2026-05-25:

1. **Over-broad request count.** `facts.build_for_digest` counts
   `kubernetes.namespace_name:caddy-system AND _msg:"handled request"` with no
   host filter — 15,717/day across *every* Hop vhost (heads, headplane,
   landing, ACME, blog, bots, probes), presented as if it were blog traffic.
2. **Empty top page / referrer.** No GoatCounter query exists anywhere in the
   digest path, despite `GOATCOUNTER_URL` + `OBS_GOATCOUNTER_API_TOKEN` being
   wired into the deployment. The prompt asks the LLM for "top page, top
   referrer" and says "if a fact is missing, say so" → permanently blank.
   (Spec lines 35 + 291 always intended GoatCounter here; it was never built.)
3. **Security blind spots.** The digest counts only `priority:Critical` over the
   *prior calendar day*. A benign Critical event (headscale-backup `sqlite3
   .backup` tripping "Drop and execute new binary in container" at 03:00 UTC)
   is reported ~29h late, and non-Critical events (yesterday's 2 "Read
   sensitive file untrusted" Warnings) never surface at all.
4. **Dead blog surge detection.** `surge.py._hour_count` filters
   `_msg:"blog.derio.net"`, but the vhost lives in field `request.host` — the
   filter always matches zero, so `surge.compute()` never fires for the blog.

**One root cause:** the digest read raw Caddy/Falco logs as a proxy for "blog
activity" without the dimensional filters that data needs (vhost via
`request.host`, priority breadth), while the purpose-built reader source
(GoatCounter) sat wired-but-unused. The tests only asserted the count-*parser*
shape, never the query string or field names — so none of it failed CI.

## Approach

Three phases, TDD-first:

- **Phase 1** rebuilds the fact sheet in pure Python (no deploy): per-vhost +
  per-status edge breakdown scoped to `kubernetes.host:hop-1`, GoatCounter
  pageviews/top-pages/top-referrers, all-priority Falco breakdown + top rules
  over a split window, and the `surge.py` `request.host` fix. New tests assert
  the actual query strings/fields.
- **Phase 2** computes the split window in `api.py` (traffic = calendar day,
  security = through run time), rewrites the digest prompt, rebuilds the image
  to `0.1.1`, redeploys via ArgoCD, and verifies end-to-end against live data
  (dry-run fact dump + a real Telegram message).
- **Phase 3** retro-updates the obs building/operating posts, adds gotchas
  (`request.host` vs `_msg`; Falco Loki-push fields; split-window), and records
  a deviation pointer on the parent plan **without** reopening its closed
  Issues.

## Decisions

- **Split window** (operator choice): traffic/pageviews stay on the prior
  calendar day (matches GoatCounter daily buckets and the "Yesterday" title);
  the security window runs to digest-run-time so overnight Critical events
  surface same-day.
- **Rework plan, not parent amend** (operator choice): avoids the documented
  `vk apply` footgun of reopening the parent's hand-closed phase Issues.
- The `ai_adapter` swap contract is preserved: `summarize(facts: dict) -> str`
  is unchanged; only the fact dict grows richer.

## Phase 2 Deployment Deviations

End-to-end verification against live data (the whole point of P2.T3) surfaced
that the planned fix #2 (GoatCounter readers) was broken in **four** ways the
plan hadn't anticipated — Phase 1 built the query but nothing had ever
exercised it against the real GoatCounter:

1. **URL behind SSO.** `GOATCOUNTER_URL` pointed at the public
   `counter.cluster.derio.net` ingress, which sits behind Authentik
   forward-auth → API token requests `302`-redirect to the SSO login. Fixed:
   point at the in-cluster Service `goatcounter.goatcounter-system.svc:8080`
   (deployment env + code default).
2. **Token missing `stats` permission.** The shared `grafana-readonly` token
   (`OBS_GOATCOUNTER_API_TOKEN`) had permissions `14` (count+export+site_read)
   but the `/api/v0/stats/*` endpoints require `APIPermStats` (bit `64`) →
   `403`. Fixed via the manual-operation below (additive: `14`→`78`).
3. **Wrong referrer endpoint.** Code queried `/api/v0/stats/refs`, which does
   not exist in this GoatCounter build (`400`); the real endpoint is
   `/api/v0/stats/toprefs`, wrapping rows in `stats` not `refs`. Fixed path +
   parse key; test now asserts the real endpoint/shape.
4. **Empty date range.** GoatCounter's API range is `[start, end)` with `end`
   EXCLUSIVE. The code queried `{start: day, end: day}` (empty) → `0` views
   even on days with traffic (2026-05-24 had 16 views; `start==end` returned
   `0`). Fixed: `end = until.date()` (next-day midnight).

Also added a `falco_critical_rules` fact (rules filtered to `priority:Critical`)
+ reprompt so the digest **names** the benign Critical rule instead of guessing
it from `falco_top_rules` (the LLM had mis-attributed it).

**Mechanism deviations:** image built via in-cluster kaniko (no `docker` in the
agent pod) pushing to GHCR with a `write:packages` token; final tag is `0.1.4`
(iterated `0.1.1`→`0.1.2`→`0.1.3` as each verification-driven fix landed, then
`0.1.4` for code-review follow-ups — "direct" referrer label + FastAPI version
sync). ArgoCD tracks `main`, so the branch push does not auto-deploy —
verification ran against a standalone pod with production env; prod rolls to
`0.1.4` when the PR merges.

```yaml
# manual-operation
id: obs-goatcounter-token-stats-permission
layer: obs
app: ai-alert-helper
plan: 2026-05-25--obs--blog-digest-rework-1
when: After deploying the digest's GoatCounter reader integration, or whenever
  the GoatCounter DB is recreated/restored (token permissions are runtime state,
  not GitOps-managed).
why_manual: GoatCounter API tokens and their permission bitfield live in
  GoatCounter's own sqlite DB (runtime object, originally minted via the UI),
  not in Git. The `stats` permission (bit 64) is required for `/api/v0/stats/*`
  but the bundled `goatcounter db ... -perm` CLI does not expose `stats` as a
  name, so the bitfield must be written directly.
commands: |
  DB="sqlite+/home/goatcounter/goatcounter-data/goatcounter.sqlite3"
  # Grant stats (bit 64) additively to the existing token (14 -> 78):
  kubectl -n goatcounter-system exec deploy/goatcounter -- sh -c \
    "goatcounter db query -db '$DB' \"UPDATE api_tokens SET permissions='78' WHERE api_token_id=1\""
  # Token cache is read at boot — restart to apply:
  kubectl -n goatcounter-system rollout restart deploy/goatcounter
verify: |
  kubectl -n goatcounter-system exec deploy/goatcounter -- sh -c \
    "goatcounter db query -db '$DB' 'SELECT name,permissions FROM api_tokens' -format json"
  # expect permissions: "78"; the digest /api/v0/stats/total then returns 200, not 403.
status: done
```
