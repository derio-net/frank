---
name: hop-trace-analysis
description: Analyze scan/attack traces on the Hop edge — "analyse the scan", "who is hitting the blog", "what did this IP do", "are we being scanned", Falco/CrowdSec/Caddy trace analysis in VictoriaLogs.
---

# hop-trace-analysis (registry pointer)

The canonical playbook is **`apps/ai-alert-helper/skill/SKILL.md`** — read it
before answering. It is the single source of truth, shared verbatim with the
ai-alert-helper analyst pod (mounted via ConfigMap), and carries the field
schemas, canonical LogsQL, known-baseline table, and the scan-classification
playbook. It lives there because the kustomize load restrictor requires it
inside the app's root.

Fast paths (full versions + caveats in the canonical file):

```text
# Edge traffic by vhost, probe-excluded (1h)
_time:1h kubernetes.host:hop-1 _msg:"handled request" -`request.headers.User-Agent`:"Frank-Blackbox-Probe" | stats by (request.host) count()

# Falco by priority (24h) — Falco uses Loki-push fields, never kubernetes.namespace_name
_time:24h source:syscall | stats by (priority) count()

# Scan-probe paths (6h) — group the edge filter by request.uri, match the probe list
```

Query endpoint: `http://192.168.55.225:9428/select/logsql/{query,stats_query}`.
The deployed analyst exposes the same data via Telegram `/commands` and
`POST /ask` on the ai-alert-helper Service.
