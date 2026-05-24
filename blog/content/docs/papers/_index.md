---
title: "The Frank Papers"
weight: 3
sidebar:
  open: true
---

Research-grade landscape reviews for every capability on the cluster. Each
Paper maps the vendor space, grades options against a decision-maker rubric,
and returns to Frank's choice as a worked case study — honest about where
that choice would not generalize.

Papers are written in **decision-weight order** (whichever vendor fight is
most worth reading next) and listed below in **architectural-stack order**.
The cluster is living — layers grow, capabilities surface, and the series
grows with them rather than against a fixed quota. Status updates
automatically as new papers publish.

{{< papers-roadmap >}}

## Deferred / Future Papers

Capabilities where the research substrate exists but the decision-weight
isn't ready to ship. Each lands as a focused single-decision paper once
the soak data justifies it.

- **Self-hosted blog analytics — cookieless vs the rest.** GoatCounter,
  Plausible, Umami, Matomo. *Deferred:* needs ≥6 months of real visitor
  behaviour data on Frank's blog before the cookieless-vs-rich-events
  trade-off can be cited from production rather than from vendor docs.
- **Edge HTTP security at small scale.** CrowdSec, fail2ban, Cloudflare WAF,
  Caddy native rate-limiting. *Deferred:* requires accumulated CrowdSec
  decision data plus at least one real (not synthetic) attack so the
  false-positive rate is comparable against managed-WAF claims rather than
  estimated.
- **Container runtime security on immutable OS.** Falco (modern_ebpf),
  Tetragon, Wazuh agent. *Deferred:* needs broader rule-set tuning experience
  on Talos. The default Falco rules under-fire on `kubectl exec` and
  over-fire on `Contact K8S API Server From Container`; the decision-weight
  emerges only after the tuning surface is mapped, which takes months of
  operational data.

Research substrate for all three lives at
[`docs/investigations/2026-05-24--obs--edge-observability-research.md`](https://github.com/derio-net/frank/blob/main/docs/investigations/2026-05-24--obs--edge-observability-research.md).
