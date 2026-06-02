---
name: falco-triage
description: Triage a Falco security-event notification on Hop — classify false-positive vs real, then fix by image-bake or rule exception
user-invocable: true
disable-model-invocation: false
arguments:
  - name: rule
    description: The Falco rule name from the Telegram alert (e.g. "Drop and execute new binary in container")
    required: false
---

# Triage a Falco Security Event

A Falco **Critical** event pages via Telegram (`@agent_zero_cc_bot`). This skill
walks the alert from notification → classification → fix → verify. Falco runs on
the **Hop** edge cluster.

> **Environment (critical):** Falco is on Hop. `source .env_hop` — **never**
> `source .env` first (it overrides KUBECONFIG to Frank). See `hop-gotchas.md`.
> Read first: `agents/rules/hop-gotchas.md` (Falco lines) and
> `docs/runbooks/frank-gotchas/obs-digest.md` (the Falco→VictoriaLogs field shape).

## Alert pipeline (so you know where to look)

Falco (eBPF, Hop) → falcosidekick → **Critical** = Telegram; **≥ notice** =
VictoriaLogs (Frank LB `192.168.55.225:9428`) via Loki-push. Floor is `notice`.

## Steps

### 1. Pull the raw event from VictoriaLogs (LogsQL)

Falco events carry fields `source` / `priority` / `rule` / `k8s_ns_name` — **not**
`kubernetes.namespace_name` (that's the fluent-bit/Caddy path). Always filter
`source:syscall`; never filter Falco by `kubernetes.namespace_name` (matches zero).

```bash
source .env          # Frank — VictoriaLogs lives on Frank
kubectl -n monitoring port-forward svc/victoria-logs-victoria-logs-single-server 9428:9428 &
# Recent Critical events:
curl -s 'http://localhost:9428/select/logsql/query' \
  --data-urlencode 'query=_time:24h source:syscall priority:critical | sort by (_time desc)' | jq .
# Audit what a rule is firing (without paging):
#   _time:24h source:syscall rule:"<rule>" | stats by (k8s_ns_name) count()
```

Extract: `rule`, `priority`, `k8s_ns_name`, `k8s_pod_name`, `container`,
`syscall`, `exe_path`, `_time`.

### 2. Classify: benign-true-positive vs real

Falco events are usually *true* (the syscall happened); the question is whether
it's **legitimate**. Check the known baseline first:

- **"Contact K8S API Server From Container" (Notice)** — high-volume benign
  (ArgoCD reconcile). Expected; not paged.
- **"Drop and execute new binary in container" (Critical, `EXE_UPPER_LAYER`)** —
  almost always a container installing a tool at runtime (`apk add` / `pip
  install` / `npm i -g`). Benign-true-positive. First seen: headscale-backup's
  `apk add sqlite` at 03:00.
- **Read sensitive file / Suspicious outbound** — check `exe_path` + destination
  against the app's normal behavior.

A real positive = an executable/connection the workload has no business making.
When unsure, treat as real and escalate to a security review.

### 3. Fix — prefer image-bake over muting

In priority order (narrowest, most honest first):

1. **Bake the tool into a digest-pinned image** (preferred for runtime-install
   events). The binary then lives in the read-only base layer and Falco won't
   fire. Example: headscale-backup switched `apk add sqlite` → `alpine/sqlite`
   pinned by digest. Edit the workload's chart/manifest, pin the digest.
2. **Add a scoped rule/macro exception** in
   `clusters/hop/apps/falco/values.yaml` → `customRules`. Re-declare the macro
   with a narrowed condition, or append `and not (<benign match>)` to the rule.
   Keep the scope as tight as possible (namespace + exe_path).
3. **Suppress the rule** — last resort, only with strong evidence.

Never mute a rule just to stop the page — that's hiding a true positive.

### 4. Deploy & watch (Hop)

```bash
source .env_hop
git add clusters/hop/apps/falco/values.yaml   # (and/or the workload image bump)
git commit -m "falco: bake <tool> into image" # or "falco: scope exception for <rule> in <ns>"
# ArgoCD (Hop) auto-syncs; Falco pod restarts on config change:
kubectl -n falco-system get pods -w
kubectl -n falco-system logs -l app.kubernetes.io/name=falco -f --tail=50
```

### 5. Verify suppression

Re-trigger the activity (e.g. `kubectl -n <ns> create job --from=cronjob/<name>
manual-test`), wait for the pod, then re-query VictoriaLogs (step 1) for the same
`rule` over `_time:5m` — expect an empty result.

### 6. Document

- One-liner in `agents/rules/hop-gotchas.md` (Falco section).
- Full prose / recovery in the matching `docs/runbooks/frank-gotchas/<topic>.md`.
- If a new recurring benign job is found, add it to the baseline list above.

## Summary

Show: the event (rule, ns, pod, exe), your classification + why, the fix chosen
(image-bake vs exception) with scope, the verify result, and the gotcha line you
added.
