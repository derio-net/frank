---
title: "Operating the Metrics API — kubectl top, HPAs, and the Silent-Empty Failure"
series: ["operating"]
layer: obs
date: 2026-07-25
draft: false
tags: ["operations", "metrics-server", "metrics-api", "hpa", "kubectl-top", "talos", "obs"]
summary: "How to check the resource Metrics API is healthy, add a CPU/mem HPA, and diagnose the one failure mode where the pod is Ready but top is empty."
weight: 30
reader_goal: "Verify metrics-server health, add a CPU/mem HPA, and diagnose an empty kubectl top."
diataxis: [how-to, reference]
last_updated: 2026-07-25
---

{{< last-updated >}}

metrics-server serves the resource Metrics API (`metrics.k8s.io`) on Frank. It runs as a single Deployment in `kube-system`, managed by ArgoCD. This is the companion reference to *Building Frank — The Metrics API*: the commands you actually run day to day.

## Is it healthy?

Three checks, cheapest first:

```bash
# 1. The APIService must be Available — this is what kubectl top / HPA federate to.
kubectl get apiservice v1beta1.metrics.k8s.io
#   NAME                    SERVICE                      AVAILABLE
#   v1beta1.metrics.k8s.io  kube-system/metrics-server   True

# 2. The pod.
kubectl get pods -n kube-system -l app.kubernetes.io/name=metrics-server

# 3. The actual capability — real numbers, all 7 nodes.
kubectl top nodes
```

If `kubectl top nodes` prints seven rows with non-zero CPU/mem, everything downstream ({{< abbr "HPA" "HPAs" >}}, `kubectl top pods`) works. That is the real health signal — not pod readiness (see the failure mode below).

## Adding a CPU/memory HPA

The common case. The **target Deployment must declare CPU (or memory) `requests`** — the HPA computes utilization as a percentage of the request, so with no request it can't compute anything and `TARGETS` stays `<unknown>`.

```bash
kubectl autoscale deployment <name> -n <ns> --cpu=70% --min=1 --max=4
kubectl get hpa <name> -n <ns>
#   TARGETS should read e.g. 23%/70% — a real number, not <unknown>/70%
```

For anything ArgoCD-managed, declare the HPA in git rather than imperatively, and add an `ignoreDifferences` on `/spec/replicas` for the target Deployment so ArgoCD and the HPA don't fight over the replica count.

> **Note:** this is CPU/memory autoscaling only. Scaling on *custom* metrics (queue depth, {{< abbr "RPS" >}}, tokens/s) needs a separate adapter that Frank does not run yet — tracked in [#701](https://github.com/derio-net/frank/issues/701). metrics-server serves `metrics.k8s.io` and nothing else.

## The failure mode: pod Ready, `top` empty

This is the one that wastes an afternoon. `kubectl top nodes` returns `error: Metrics API not available` or empty rows, **while the metrics-server pod is `Running` and `Ready`.** Ready means the pod's own probe passed — it says nothing about whether kubelet scrapes are succeeding.

Go straight to the logs:

```bash
kubectl logs -n kube-system -l app.kubernetes.io/name=metrics-server --tail=50
```

- **`x509: certificate signed by unknown authority`** → the `--kubelet-insecure-tls` arg is missing or didn't apply. Talos kubelets use self-signed serving certs; without that flag every scrape is rejected. Confirm the flag is live: `kubectl get deploy metrics-server -n kube-system -o jsonpath='{.spec.template.spec.containers[0].args}'`. It is set in `apps/metrics-server/values.yaml`.
- **`unable to fully scrape metrics ... <node>`** for one node → that kubelet is unreachable (node NotReady, {{< abbr "NIC" >}} flap, firewall). Cross-check `kubectl get nodes` and that node's health.
- **Clean logs but `top` empty for ~30s after a restart** → normal. The APIService reads `Available=False` until the first scrape window lands. Wait, don't restart.

## Restart / resync

metrics-server is stateless — restarting is safe and loses only the in-memory scrape window (repopulates in ~15s):

```bash
kubectl rollout restart deployment metrics-server -n kube-system
```

It's ArgoCD-managed, so config changes go through git (edit `apps/metrics-server/values.yaml`, commit, let the App-of-Apps sync). To force a sync after a merge, hard-refresh the root app:

```bash
kubectl annotate application root -n argocd argocd.argoproj.io/refresh=hard --overwrite
```

## One operational caveat

metrics-server runs a **single replica**. It's cheap and stateless, so that's a deliberate footprint choice — but the `metrics.k8s.io` APIService gates the API server's aggregation layer. If metrics-server crashloops (bad flag, unreachable kubelets), an *unavailable* aggregated APIService can make API discovery slow and surface as `ComparisonError` on **other** ArgoCD apps, not just this one. So if several unrelated apps go `ComparisonError` at once, check metrics-server before chasing each app.

## References

- Building companion: *Building Frank — The Metrics API*
- Issue: [#394](https://github.com/derio-net/frank/issues/394) · Deferred adapter: [#701](https://github.com/derio-net/frank/issues/701)
- Gotcha: `agents/rules/frank-gotchas.md` → *Other in-cluster apps* (metrics-server / Talos)
