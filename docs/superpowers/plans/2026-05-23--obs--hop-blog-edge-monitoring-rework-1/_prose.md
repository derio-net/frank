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
