#!/usr/bin/env bash
# Assert the GPU-time-share alerting contract in alert-rules-cm.yaml +
# notification-policy-cm.yaml. Parses the embedded provisioning YAML (PyYAML via
# uv) rather than grepping, so structure — not just substrings — is checked.
# Plan: 2026-06-15--obs--gpu-timeshare-health-probes (Phases 4 + 5).
set -euo pipefail
cd "$(dirname "$0")/../../.."   # repo root

uv run --quiet --with pyyaml python3 - <<'PY'
import sys, yaml

rules_cm = yaml.safe_load(open("apps/grafana-alerting/manifests/alert-rules-cm.yaml"))
# alert rules live in one or more data keys; concat all *.yaml values
groups = []
for v in rules_cm["data"].values():
    doc = yaml.safe_load(v)
    groups += doc.get("groups", [])
rules = {r["title"]: r for g in groups for r in g.get("rules", [])}
gnames = {g["name"] for g in groups}

def expr_of(rule):
    for d in rule["data"]:
        m = d.get("model", {})
        if m.get("expr"):
            return m["expr"]
    return ""

errs = []
l11 = rules.get("Layer 11 Local Inference Degraded")
l16 = rules.get("Layer 16 Media Generation Degraded")
if not l11: errs.append("Layer 11 rule missing")
if not l16: errs.append("Layer 16 rule missing")

for name, rule in (("L11", l11), ("L16", l16)):
    if not rule: continue
    e = expr_of(rule)
    if "probe_success" not in e: errs.append(f"{name} expr not probe_success: {e}")
    if "kube_pod_status_ready" in e: errs.append(f"{name} still uses kube_pod_status_ready")
    if "replicas_unavailable" in e: errs.append(f"{name} still uses replicas_unavailable")
    labs = rule.get("labels", {})
    if labs.get("gpu_timeshare") != "true": errs.append(f"{name} missing gpu_timeshare=true")
    if labs.get("severity") != "warning": errs.append(f"{name} severity!=warning")
    if rule.get("noDataState") != "Alerting": errs.append(f"{name} noDataState!=Alerting")

# combined paging rule
if "gpu-node-both-down" not in gnames:
    errs.append("rule group gpu-node-both-down missing")
both = rules.get("GPU Node Serving Neither Inference Nor Media") or \
       next((r for g in groups if g["name"]=="gpu-node-both-down" for r in g["rules"]), None)
if both:
    e = expr_of(both)
    if "sum(probe_success" not in e.replace(" ", ""): errs.append(f"both-down expr not sum(probe_success): {e}")
    if both.get("labels", {}).get("severity") != "critical": errs.append("both-down severity!=critical")
    if "gpu_timeshare" in both.get("labels", {}): errs.append("both-down must NOT carry gpu_timeshare")
    if both.get("noDataState") != "OK": errs.append("both-down noDataState!=OK")
else:
    errs.append("both-down rule not found")

# notification route ordering: gpu_timeshare route precedes first severity route
pol = yaml.safe_load(open("apps/grafana-alerting/manifests/notification-policy-cm.yaml"))
routes = pol["data"]["notification-policy.yaml"]
routes = yaml.safe_load(routes)["policies"][0]["routes"]
def has_matcher(r, needle):
    return any(needle in m for m in r.get("matchers", []))
gi = next((i for i,r in enumerate(routes) if has_matcher(r, "gpu_timeshare")), None)
si = next((i for i,r in enumerate(routes) if has_matcher(r, "severity=critical")), None)
fhi = next((i for i,r in enumerate(routes) if has_matcher(r, 'grafana_folder="feature-health"')), None)
if gi is None: errs.append("gpu_timeshare route missing")
elif si is not None and gi >= si: errs.append(f"gpu_timeshare route (idx {gi}) must precede severity route (idx {si})")
elif routes[gi].get("continue") is not False:
    errs.append("gpu_timeshare route must be continue:false")
# the feature-health catch-all must come AFTER the gpu_timeshare route, else a
# time-share alert would hit health-bridge via the catch-all and stop early in
# the wrong place (and a moved route could re-expose the Telegram path).
if fhi is not None and gi is not None and fhi <= gi:
    errs.append(f"feature-health route (idx {fhi}) must come AFTER gpu_timeshare route (idx {gi})")
# positive-pager path: the both-down rule (severity=critical, NO gpu_timeshare
# label) must reach a severity=critical → Telegram route. Assert such a route
# exists and that the both-down rule carries no gpu_timeshare label (else it
# would be swallowed by the quiet route and never page).
if si is None:
    errs.append("no severity=critical route — gpu-node-both-down could not page")
if both and "gpu_timeshare" in both.get("labels", {}):
    errs.append("gpu-node-both-down carries gpu_timeshare — would be routed quiet and never page")

if errs:
    print("FAIL:")
    for e in errs: print("  -", e)
    sys.exit(1)
print("OK: L11/L16 probe_success + quiet labels; gpu-node-both-down paging; route ordering")
PY
