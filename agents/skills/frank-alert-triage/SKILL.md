---
name: frank-alert-triage
description: Triage firing Grafana alerts on the Frank cluster — fetch the firing set, classify each (muted-canary / by-design / false-positive / unexplained), and print a compact verdict table. Use when "Grafana is alerting", "what is firing on Frank", "investigate this alert", "triage the alerts", "is this alert real". Classify-and-recommend only — never mutates the cluster.
user-invocable: true
disable-model-invocation: false
arguments:
  - name: alertname
    description: Optional — a single alertname to focus on. Omit to triage the whole firing set.
    required: false
---

# Triage Frank Grafana Alerts

Investigate what is firing on Frank and classify each alert against the known
decision tree, so the operator sees signal (what is real) instead of a wall of
warnings. **Read-only: this skill classifies and recommends — it never mutates
the cluster** (no pod deletes, no acks, no restarts). A genuinely-unexplained
alert is handed off to `superpowers:systematic-debugging` / `fr-debugging`.

The classification logic lives in `classify.py` (pure, unit-tested in
`test_classify.py`) alongside this file. The alert-agent (`apps/alert-agent`)
documents the same tree in its own SKILL.md — keep the two in sync.

## Step 0 — cluster context

```bash
cd <frank-repo-root> && source .env      # relative KUBECONFIG — MUST cd first
kubectl get nodes -o wide                 # sanity: are nodes actually Ready?
```

## Step 1 — fetch the firing set

Grafana is the VictoriaMetrics stack instance on the `192.168.55.203`
LoadBalancer (plain HTTP). Admin creds come from its secret.

```bash
PW=$(kubectl -n monitoring get secret victoria-metrics-grafana \
       -o jsonpath='{.data.admin-password}' | base64 -d)
curl -s -u "admin:$PW" \
  "http://192.168.55.203/api/prometheus/grafana/api/v1/alerts" -o /tmp/frank-alerts.json
```

The rule state to filter on is **`Alerting`** (this Grafana prometheus-compat
endpoint reports `Normal` / `Alerting` / `Normal (NoData)`, not `firing`).

## Step 2 — resolve pod state for readiness alerts

An alert whose `__name__` is `kube_pod_status_ready` fires on a pod being
NotReady — but a **terminal or absent** pod (graceful-shutdown `Succeeded`
tombstone left by a node reboot) holds a *stale* series and reads NotReady
forever. So for each such alert, resolve the live pod phase:

```bash
kubectl -n <namespace-label> get pod <pod-label> \
  -o jsonpath='{.status.phase}' 2>/dev/null   # empty ⇒ pod is gone (absent)
```

Pass the phase (or `None` when absent) as `pod_state` to `classify()`. For any
non-readiness alert, `pod_state` is `None`.

## Step 3 — classify and print the table

Feed each alert's `labels` (+ resolved `pod_state`) through `classify.py` and
print a compact PLAIN-TEXT verdict table (same column style as the alert-agent
report): `alert | severity | verdict | reason/action`. Example driver:

```bash
cd <this-skill-dir>   # so `import classify` resolves
python3 - "$@" <<'PY'
import json, subprocess
from classify import classify

alerts = json.load(open("/tmp/frank-alerts.json"))["data"]["alerts"]
rows = []
for a in alerts:
    if a.get("state") != "Alerting":
        continue
    lbl = a["labels"]
    pod_state = None
    if lbl.get("__name__") == "kube_pod_status_ready" and lbl.get("pod"):
        out = subprocess.run(
            ["kubectl", "-n", lbl.get("namespace", ""), "get", "pod", lbl["pod"],
             "-o", "jsonpath={.status.phase}"],
            capture_output=True, text=True)
        pod_state = out.stdout.strip() or None
    v = classify(lbl, pod_state)
    rows.append((lbl.get("alertname", "?"), lbl.get("severity", "?"), v))

w = max((len(r[0]) for r in rows), default=5)
for name, sev, v in rows:
    print(f"{name:<{w}}  {sev:<8}  {v.kind:<14}  {v.reason}")
PY
```

## Step 4 — the decision tree (shared contract)

| Signal (label) | Verdict | Meaning |
|---|---|---|
| `canary: true` | `muted` | Deliberately-firing canary (e.g. expired-cert canary #251) — never paged |
| `gpu_timeshare: true` | `by-design` | gpu-1 hosts one of Ollama/ComfyUI at a time; one probe is always down. The only real pager is `gpu-node-both-down` |
| `__name__: kube_pod_status_ready` + pod `Succeeded`/`Completed`/absent | `false-positive` | Stale kube-state-metrics series held by a graceful-shutdown tombstone. Recommend (do NOT run) deleting the terminal pod to clear it |
| none of the above | `unexplained` | No known-benign pattern — **escalate** to `fr-debugging` |

`github_issue: frank-ops#N` is captured as an orthogonal **tracker** annotation
on any verdict — it links the alert to its tracker, but it is NOT a benign
signal (a live NotReady pod carries it too).

## Step 5 — recommend, never act

- `muted` / `by-design` → note as expected; no action.
- `false-positive` → state the safe cleanup (e.g. `kubectl delete pod <tombstone>`)
  as a **recommendation for the operator to run** — this skill does not delete.
- `unexplained` → hand off to `fr-debugging` with the alert + evidence gathered.

## Notes

- The `victoria-metrics-grafana` service is plain HTTP on `.203` — a `https://`
  URL gets a TLS reset. Use `http://`.
- `state == "Alerting"` on this endpoint is the rule state, distinct from the
  Alertmanager instance `firing`.
- Verify the fix worked by re-fetching after any operator cleanup: a deleted
  tombstone's readiness series ages out of VictoriaMetrics on its ~5-min
  staleness window, so the alert resolves on a short delay, not instantly.
