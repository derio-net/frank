# Frank Gotchas — Archive

Long-form companion to `agents/rules/frank-gotchas.md`. That hot file is auto-loaded into every Claude Code session and gets the one-line summary of each gotcha. The files here are **not auto-loaded** — agents and operators read whichever section is relevant.

## Contents

| File | Topic |
|---|---|
| [argocd.md](argocd.md) | ArgoCD: notifications, sync, root App-of-Apps, out-of-bounds symlinks |
| [storage-secrets-ssa.md](storage-secrets-ssa.md) | RWO PVCs, ServerSideApply, SOPS, ESO, strategy transitions |
| [tekton.md](tekton.md) | CRD schema, `$(tasks.status)`, fsGroup, HOME, Gitea webhook header |
| [argo-rollouts.md](argo-rollouts.md) | Canary mechanics, AnalysisTemplate, workloadRef, Prometheus provider |
| [authentik.md](authentik.md) | Blueprints, outpost assignment, API shape (Bearer + 2026.x) |
| [grafana.md](grafana.md) | Provisioning, alert SSE format, dashboards, false-positive queries |
| [obs-digest.md](obs-digest.md) | AI digest: Falco Loki-push field names, traffic/security split window, dry-run audit |
| [networking.md](networking.md) | Cilium L2 IPAM, FQDN policies, MixedProtocolLBService, mosh |
| [gpu-1.md](gpu-1.md) | Node-pinning idiom, port-forward CNI flake, Ollama cgroup memory |
| [agent-shells.md](agent-shells.md) | s6-overlay v3, sshd env, `cont-init.d`, tmux-continuum |
| [paperclip-ruflo.md](paperclip-ruflo.md) | PVC sizing, app-vs-shell container split, ruvocal RVF/liveness |
| [omni.md](omni.md) | Cert renewal path (NOT the snap timer) + recovery |
| [other-apps.md](other-apps.md) | Sympozium, Zot, Gitea, n8n, VK/VibeKanban, curlimages |

## When to add a new gotcha

1. Add a one-liner to the relevant section in `agents/rules/frank-gotchas.md`.
2. If the gotcha needs more than two lines (recovery commands, repro steps, dated incident notes), add the full entry to the corresponding file here under a `## <short title>` heading. If no file matches the topic, add a new file and update this index.
3. Cross-references in the hot file's section header already point at the directory — no need to update them per-entry.

When a gotcha gets stale (resolved upstream, no longer applies after a refactor), it's fine to delete it from both the hot file and the section file rather than leaving a stale "do not do this" note.
