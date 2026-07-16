# Operating Series Rewrite — Per-Post Changelog

All 28 operating posts rewritten with the educational methodology: set-the-stage openings, Mermaid diagrams, real Missteps from git history, "What Healthy Looks Like" sections, and Frank's voice focused on teaching.

## Conventions Applied to Every Post

| Category | Items |
|----------|-------|
| Added | `reader_goal`, `diataxis: [how-to, reference]`, `last_updated`, `last_updated_commit` frontmatter fields |
| Added | `tags: ["troubleshooting"]` to every post (except those where it was already present) |
| Added | `{{< last-updated >}}` shortcode immediately after frontmatter |
| Added | Mermaid `flowchart LR` / `graph TB` / `sequenceDiagram` showing architecture, data flow, or lifecycle |
| Added | "What Healthy Looks Like" section — concise health baseline |
| Added | "Verify" subsection — terse check criteria with commands |
| Added | "Missteps" table (real incidents from git history with commit SHAs and PR references) |
| Added | "Recovery Path" or "Runbook" section with symptom → cause → fix entries |
| Added | `file:line` annotations citing specific config files and gotcha docs |
| Added | Source preamble (`source .env` / `source .env_devops` / `source .env_hop`) |
| Removed | Verbose narrative prose and session diary — condensed to "A was wrong, B was the fix" |
| Removed | ASCII architecture diagrams (replaced with Mermaid) |
| Removed | Redundant command commentary and inline admonition boxes |
| Removed | Full console output captures (replaced with excerpts or descriptions) |
| Modified | Chronological narrative restructured to tutorial flow (Overview → What Healthy Looks Like → Verify → Steps → Recover → Missteps → Quick Reference → References) |
| Modified | Verbose session narrative condensed |
|  | long-form gotcha descriptions → Missteps table |
### 01-cluster-nodes

| Category | Items |
|----------|-------|
| Added | Mermaid topology diagram (7-node cluster + Cilium CNI overlay) |
|  | "What Healthy Looks Like" section |
|  | "Verify" subsection |
|  | Runbook Recovery Paths (DNS boot hang, Cilium agent restart, NIC link-flap, Omni cert expiry, wedged reconcile) |
|  | Missteps table (4 entries: ConfigPatches UKI inert, Omni cert auto-renew, clock-jump freeze, DNS fallback boot hang) |
|  | Quick Reference table (22 commands) |
|  | "Explanation" section |
|  | "References" section with 7 links |
|  | `file:line` annotations |
| Removed | Verbose block commenting on commands |
|  | Hubble UI tip paragraph |
|  | Cilium verbose status output with hash-pinned versions |
|  | "Stale pod" explanatory paragraph chain |
| Modified | Section headings: "What 'Healthy' Looks Like" → "What Healthy Looks Like", "Debugging" → "Runbook" |
|  | stale pods section condensed |
|  | Node NotReady checklist streamlined from 5 to 4 steps |
|  | Cilium Agent section split into diagnosis + recovery |

### 02-storage-backups

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (Longhorn → 3 replicas → R2 backup) |
|  | "What Healthy Looks Like" section |
|  | "Verify" subsection |
|  | Recovery Paths (volume degraded, backup failed, stuck attachment) |
|  | Missteps table (5 entries: fsGroup, `/var/lib/longhorn` disk, 6-day rebuild, gpu-local data locality, backup target re-auth) |
|  | Quick Reference table (12 commands) |
|  | `file:line` annotations to `apps/longhorn/values.yaml` |
| Removed | Full 30-line Longhorn volume list from console output |
|  | verbose "Why Longhorn" re-justification |
|  | the full `backupTarget` creation YAML (→ excerpt) |
| Modified | StorageClass descriptions condensed into table |
|  | backup schedules clearly delineated |
|  | Recovery Paths restructured from narrative to Symptom → Cause → Fix |

### 03-gitops

| Category | Items |
|----------|-------|
| Added | Mermaid App-of-Apps diagram |
|  | Key configuration bullet list with `file:line` refs |
|  | "Verify" subsection with jq health checks |
|  | Recovery Paths (6 entries: stale appTree health, manual sync drops syncOptions, root re-templates leaf specs, out-of-bounds symlink, notifications silent, controller-normalized fields) |
|  | Missteps table (6 entries) |
|  | Quick Reference table (14 commands) |
| Removed | Full 30-line console output of app listings (→ `# ... (76 total applications)`) |
|  | ArgoCD UI screenshot ref |
|  | "The fix I tried first" narrative |
|  | Orphaned resources 3-paragraph explanation (→ 2 sentences) |
| Modified | Overview restructured from 1 paragraph → 4-bullet configuration cite + 2 Verify commands |
|  | OutOfSync narrative → concise "Fix:" statement |
|  | Summary updated to reference "gotchas that have bitten Frank" |

### 04-gpu-compute

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (GPU Operator + DRA) |
|  | "What Healthy Looks Like" section |
|  | "Verify" subsection |
|  | Recovery Paths (GPU not allocating, containerd config corruption, stale allocations, reboot loops) |
|  | Missteps table (6 entries: `nvidia` in name, Intel DRA vendoring, NFD→NodeFeature, GFD race, TimeSlider, MCP split) |
|  | Quick Reference table (8 commands) |
| Removed | Verbose narrative comparing Talos vs standard GPU Operator config |
|  | full `nvidia-driver` DaemonSet YAML |
| Modified | Restructured from single long narrative to "NVIDIA → Intel → DRA → Missteps → Recovery" |
|  | error states given distinct sub-headings |
### 05-observability

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (VM → VL → Grafana → Fluent Bit) |
|  | "What Healthy Looks Like" section (4 moving parts) |
|  | "Verify" subsection |
|  | Recovery Paths (missing metrics, alert not firing, logs missing) |
|  | Missteps table (8 entries: etcd PV default, `honorLabels`, S3 endpoint, streaming parser, vmauth routing, installImage, PVC growth, `-search.maxQueryDuration`) |
|  | Quick Reference table (15 commands) |
| Removed | Full 50-line `vmcluster.yaml` (→ excerpt) |
|  | 4 `{{< relref >}}` to building posts |
|  | long-form Grafana 11→12 upgrade section |
|  | cardinality explosion narrative (→ Missteps) |
| Modified | Restructured to "Metrics → Logs → Grafana → Alerts → Missteps" |
|  | cardinality explosion gotcha elevated to its own section with PromQL examples |

### 06-secrets

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (Infisical → ESO → ExternalSecret → Pod) |
|  | "What Healthy Looks Like" section (2-layer model) |
|  | "Verify" subsection |
|  | Recovery Paths (SecretSyncedError, rotated credential not picked up, SOPS decrypt failure) |
|  | Missteps table (5 entries: Infisical Helm broken on install, ESO CRD v1, 5-app split, project slug, LB race) |
|  | `file:line` annotations |
| Removed | Full Secrets YAML table for each app (→ 1 generic flow) |
|  | SOPS encryption/decryption tutorial (→ reference only) |
| Modified | "Bootstrap vs Runtime" distinction elevated to section heading with inline rule |
|  | gotcha entries condensed from paragraph to table row |

### 07-inference

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (Ollama → LiteLLM → OpenRouter → apps) |
|  | "What Healthy Looks Like" section (end-to-end probe, GPU time-share model) |
|  | "Verify" subsection |
|  | Recovery Paths (model won't load, LiteLLM 404, cgroup OOM confusion) |
|  | Missteps table (5 entries: Ollama keep_alive, `ollama_chat/` prefix, canary Cilium plugin, model pinning, OpenRouter API key location) |
|  | file:line annotations |
| Removed | Full model ranking table (→ condensed to 5 chosen models) |
|  | Ollama "deciding to use" justification |
| Modified | cgroup OOM vs real OOM distinction given dedicated sub-section with diagnostic steps |
|  | GPU time-share probe explanation rewritten for clarity |

### 08-auth

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (forward-auth flow) |
|  | "What Healthy Looks Like" section (redirect-loop-free criteria) |
|  | "Verify" subsection |
|  | Missteps table (3 entries: `AUTHENTIK_HOST` 0.0.0.0 redirect bug, Grafana secret key name mismatch, Hermes dashboard basic-auth workaround — with commit SHAs `abaae01d`, `7b3ad79f`, `8438ec39`) |
|  | Quick Reference table (7 commands) |
| Removed | Verbose code comments in Django shell commands |
|  | "Or use the Authentik admin UI" redundancy |
|  | OIDC Login Loop placed after the more impactful 0.0.0.0 incident |
| Modified | Section headings: "Routine Operations" → "Steps", "Debugging" → "Recover" |
|  | 0.0.0.0 redirect fix: generic "Set AUTHENTIK_HOST" → references specific commit and file |
|  | Rotate Client Secrets: paragraph → imperative list |
|  | Summary references "the forward-auth redirect loop that redirects to 0.0.0.0" |
### 09-multi-tenancy

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (vCluster → host cluster → tenant namespaces) |
|  | "What Healthy Looks Like" section |
|  | "Verify" subsection |
|  | Recovery Paths (API server not responding, resources not syncing, quota hit) |
|  | Missteps table (5 entries: template pattern, `syncBackend`, chart schema, CNI conflict, ArgoCD RBAC) |
| Removed | Full vcluster values.yaml (→ excerpts) |
|  | 3 MEDIA/screenshot placeholders |
|  | "Why vCluster" re-justification (→ 1 sentence) |
| Modified | Restructured from "Why → Install → Template → Users → Gotchas" to "Architecture → Deploy → Template → Chart schema → Persistent volumes → Users → Missteps → Recovery" |

### 10-media-generation

| Category | Items |
|----------|-------|
| Added | 2 Mermaid diagrams (GPU time-sharing, Switcher API) |
|  | "What Healthy Looks Like" section (3 health criteria) |
|  | "Verify" subsection |
|  | Recovery Paths (ComfyUI won't start, Switcher probe fails, workflow 500s) |
|  | Missteps table (4 entries: Go cross-compile QEMU crash, image manifest platform, ArgoCD self-heal fight, model folder paths) |
|  | inline verify console output |
| Removed | GPU Switcher build narrative with full `docker buildx` command history |
|  | ASCII architecture (→ Mermaid) |
|  | redundant "What's Running" paragraph |
| Modified | Restructured from "Constraint → Architecture → 3 apps → Model Downloads" to "Architecture → 3 Apps → Model Downloads → Missteps → Recovery" |

### 11-public-edge

| Category | Items |
|----------|-------|
| Added | Frank vs Hop comparison table (7 rows) |
|  | Mermaid diagram (Hop topology) |
|  | "What Healthy Looks Like" section (6-bullet checklist) |
|  | "Verify" subsection (5 clusters of checks) |
|  | "Steps" section (4 operations) |
|  | "Recover" section (5 paths) |
|  | Missteps table (5 entries: CrowdSec log parsing, LAPI PVC, Caddy log rotation, hcloud volume flag, secretKeyRef env var staleness — with PR refs #584, #583, #574, #594) |
|  | Quick Reference table (8 commands) |
| Removed | Entire "Environment Setup" section (~50 lines) |
|  | entire "Observing State" section (~120 lines) |
|  | entire "Headscale Operations" section (~200 lines) with subnet router / exit node config |
|  | "Key Differences from Frank" narrative paragraphs (→ 7-row table) |
|  | full console captures (talosctl health, kubectl get nodes, headscale nodes list) |
| Modified | Structure completely overhauled from 9-section chronological narrative to "Comparison table → Mermaid → Source + Verify → What Healthy → Steps → Recover → Missteps → Quick Reference → References" |
|  | all prose condensed ~60% (580→280 lines) |
### 12-progressive-delivery

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (canary + blue-green flow) |
|  | "What Healthy Looks Like" section |
|  | "Verify" subsection |
|  | Recovery Paths (stuck rollout, analysis run failed, sparse-traffic pause) |
|  | Missteps table (5 entries: Cilium plugin 404, workloadRef scaleDown, 5xx-only query, missing metric source, documented failure as happy path) |
|  | 2026-05-04 update note about LiteLLM canary rewrite |
| Removed | Full postmortem with multi-agent collaboration analysis (→ 3-bullet summary) |
|  | 3 screenshot refs (→ concise description) |
|  | minute-by-minute event log |
| Modified | Canary promotion steps condensed |
|  | pause-only LiteLLM canary pattern clearly delineated from full canary |
|  | "The canary that wasn't" given its own callout |

### 13-workflow-automation

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (n8n → PostgreSQL → PVCs) |
|  | "What Healthy Looks Like" section |
|  | "Verify" subsection |
|  | Recovery Paths (database failure, runtime crash, OIDC login broken) |
|  | Missteps table (3 entries: OIDC init unworkable, encryption key not set, RollingUpdate deadlock) |
| Removed | ASCII architecture (→ Mermaid) |
|  | 2 screenshot refs |
|  | full `N8N_SECURE_COOKIE=false` gotcha (now uses TLS) |
|  | explicit "What's Running" section |
| Modified | Per-user instance model explained more clearly |
|  | upgrade procedure streamlined |
|  | encryption key recovery as a distinct sub-section |

### 14-secure-agent-pod

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (s6-overlay supervision tree) |
|  | "Process Supervision Model" section |
|  | "Verify" subsection |
|  | Recovery Paths (SSH won't connect, cron went quiet, VibeKanban unreachable, OOM-killed sidecar) |
|  | Missteps table (5 entries: PVC mount hiding image, `wait -n` supervision, Cilium FQDN LRU, non-root sshd, `/run/secrets` conflict) |
|  | `file:line` annotations |
| Removed | 7-manifest table (redundant) |
|  | bump alerts YAML block |
|  | full verification checklist table |
|  | GitHub App install-coverage edge cases |
|  | "What's Next" bullet list |
| Modified | s6-overlay supervision model elevated to dedicated section |
|  | SSH key rotation procedure clarified |
|  | Cilium FQDN LRU gotcha given its own sub-section with diagnostic steps |
### 15-health-monitoring

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (Blackbox Exporter + Pushgateway → VM → Grafana → Telegram) |
|  | "What Healthy Looks Like" section |
|  | "Verify" subsection |
|  | Recovery Paths (probe shows down, heartbeat stale, Telegram silent) |
|  | Missteps table (5 entries: ALERTS{}, SSE format, VMOperator webhook cert, honorLabels, Telegram dedup) |
| Removed | ASCII architecture (→ Mermaid) |
|  | MEDIA placeholder for Telegram screenshot |
|  | repeated justification paragraphs |
|  | full probe output (→ trimmed) |
|  | "What's Next" M2 discussion |
| Modified | Probe types (Blackbox vs Pushgateway) given distinct sub-sections |
|  | alert rule file-provisioning model explained |
|  | silent delivery failures emphasized |

### 16-health-bridge

| Category | Items |
|----------|-------|
| Added | Mermaid lifecycle diagram (fire → webhook → GitHub Issue → board) |
|  | "The Lifecycle in One Diagram" section |
|  | "Verify" subsection |
|  | Recovery Paths (webhook not firing, duplicate issues, stranded board tiles) |
|  | Missteps table (5 entries: public repo leak, bug close by alertname, label format, power outage corpses, dead bugs on restart) |
| Removed | 2 MEDIA placeholders |
|  | three chronological "Pass" sections (→ v0.x.y feature-increment sections) |
|  | Caddy-Hop-Tailscale relay discussion (→ post 27) |
|  | github-pull-sync design (→ post 27) |
| Modified | Restructured from chronological "v0.1.0 → Pass 3 → Closing loop → Power outage" to "Architecture → v0.1.0 → v0.2.0 → v0.3.0 → v0.4.0 → Missteps → Recovery → References" |

### 17-ingress

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (Traefik → entrypoints → IngressRoutes → services) |
|  | "What Healthy Looks Like" section (4 criteria) |
|  | "Verify" subsection |
|  | Recovery Paths (route broken, certificate expiring, Homepage blank) |
|  | Missteps table (6 entries: acme.json perms, DNS-01 NXDOMAIN, invalidation_flow, outpost assignment, ping ICMP, ALLOWED_HOSTS) |
| Removed | 16-service IngressRoute list (→ 13) |
|  | full Dockerfile excerpt |
|  | 3-paragraph outpost assignment explanation |
|  | ASCII architecture (→ Mermaid) |
| Modified | Gotchas table (7 rows) → Missteps table (6 rows, consolidated) |
|  | PVC permissions section given more prominence |
|  | internal vs external entrypoint split emphasized |

### 18-paperclip

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (Paperclip + PostgreSQL + Shell sidecar + PVCs + secrets) |
|  | "What Healthy Looks Like" section |
|  | "Verify" subsection |
|  | Recovery Paths (probe deadlock, PVC rollout deadlock, memory tuning) |
|  | Missteps table (5 entries: probe deadlock, PVC rollout deadlock, fsGroup, memory tuning, shell sidecar) |
| Removed | Full "company setup" walkthrough (→ operating post) |
|  | SSH key copy instructions (→ operating post) |
|  | 3 screenshot refs |
| Modified | Restructured from "Architecture → Deploy → Company → Operating → Gotchas" to "Architecture → Health → DB Ops → Shell Sidecar → Secrets → Missteps → Recovery" |
|  | RWO PVC constraint on gpu-1 clearly called out |
### 19-git-credentials-without-a-shell

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (PID 1 → sshd/vscode/cron env inheritance) |
|  | "Why It Happens" section |
|  | "The Credential Helper" section with full solution |
|  | Recovery Paths (helper not working, VS Code still failing) |
|  | "How To Verify" section with 2 check commands |
| Removed | Long-form shell environment exploration narrative |
|  | the "ssh -t vs ssh -T" aside |
|  | the `GITHUB_TOKEN` in `.bashrc` workaround (→ conditional `.envrc` approach) |
| Modified | Restructured from narrative investigation to "Problem → Root Cause → Fix → Verify → Edge Cases" |
|  | `/proc/1/environ` trick given distinct solution block |

### 20-vk-relay

| Category | Items |
|----------|-------|
| Added | Mermaid sequence diagram (Browser → Traefik → Relay → Local VK → Agent) |
|  | "What Healthy Looks Like" section |
|  | "Verify" subsection |
|  | Recovery Paths (502s, missing workspace data, tunnel dropped) |
|  | Missteps table (3 entries: forward-auth block, separate pod attempt, rule order) |
| Removed | ASCII architecture (→ sequence diagram) |
|  | "What Changed" file-change table |
|  | yamux multiplexing explanation (6 paragraphs → 3 sentences + data flow) |
|  | SPAKE2 background (2 paragraphs → 1 sentence) |
| Modified | Re-pairing procedure made step-by-step |
|  | tunnel health checks consolidated |

### 21-vk-remote

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (PostgreSQL → ElectricSQL → VK Remote API) |
|  | "What Healthy Looks Like" section |
|  | "Verify" subsection |
|  | Recovery Paths (sync failure, init job needs re-run, API unreachable) |
|  | Missteps table (5 entries: wal_level, PostSync backoff, outpost assignment, no data migration, cross-namespace DNS) |
| Removed | Full Secrets table with YAML |
|  | "What Changed" file-change table |
|  | 3-paragraph data migration gotcha narrative |
| Modified | Gotchas section (4 items) → Missteps table (5 rows with real commits) |
|  | PostgreSQL config (wal_level) given dedicated sub-section |

### 22-cicd-platform

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (GitHub → Hop → Frank CI/CD flow) |
|  | "What Healthy Looks Like" section (5 components) |
|  | "Verify" subsection |
|  | Recovery Paths (webhook delivery failed, pipeline stuck, image verification failed) |
|  | Missteps table (10 entries: computeResources, ClusterInterceptor, webhook allowlist, HOME=/, Completed vs Succeeded, Kaniko config naming, sharing-key, SSH port unreachable, GIT_SSH_COMMAND, PodSecurity restricted) |
| Removed | 8-app ArgoCD table |
|  | full cosign verify output |
|  | Gitea CI Pipeline YAML (→ described in prose) |
|  | secondary EventListener YAML |
|  | ASCII architecture (→ Mermaid) |
| Modified | Gotchas section (7 items) → Missteps table (10 rows) |
|  | webhook delivery flow (GitHub → Caddy → Hop → Tekton) given dedicated sub-section |
### 23-argocd-drift-detective

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (drift masking: Git → API Server → ArgoCD three-way diff) |
|  | "What Healthy Looks Like" section (target: ≤2 OutOfSync) |
|  | "Verify" subsection |
|  | "Recover" section (was class A–G under no parent heading) |
|  | Missteps table (5 entries: false positives are 7 classes, CRD schema defaults safe-to-omit assumption, explicit `prune: false` phantom diff, aspirational Cilium plugin crashloop, `Progressing` masking signal) |
|  | condensed takeaways (4 bullet points) |
| Removed | Entire "The Problem" narrative (~30 lines) |
|  | all long-form console captures |
|  | Class before/after YAML (→ concise 4-line fix) |
|  | verbose Class C CRD analysis |
|  | full Class D deletion sequence (10 `kubectl delete`) |
|  | Class E "fix I tried first" narrative |
|  | Class F "If I'd stopped at one delete" narrative |
| Modified | Section structure: "The Problem → How to Actually Diagnose → Class A–G → Takeaways → References" → "Overview → Mermaid → What Healthy → Diagnose → Recover (A–G) → The Unmasked Bug → Takeaways → Missteps → References" |
|  | every class condensed 50%+ |
|  | Opening paragraph reframed from personal ("my 52 apps") → editorial ("20 of 52 apps") |

### 24-ruflo

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (ruflo + shell + 3 PVCs + LiteLLM) |
|  | "What Healthy Looks Like" section |
|  | "Verify" subsection |
|  | Recovery Paths (wrong LiteLLM key, upload 500s, SSH key bootstrap) |
|  | Missteps table (6 entries: PostgreSQL unused, RVF shim broken, LiteLLM virtual key, shareProcessNamespace crash, SSR probes, npm EACCES) |
| Removed | Full ruvocal Dockerfile |
|  | recursive "pile of process failures" section (PRs #48–#53 chain) |
|  | full SSH config for ruflo (→ operating post) |
|  | Zero Frontier Keys principle (→ inline note) |
| Modified | Restructured from chronological narrative with 6 sub-sections to "Architecture → Two Images → MongoDB misdirection → RVF shim → LiteLLM key → shareProcessNamespace → Probes → Inventory → Install trap → Missteps → Recovery" |
|  | recursive failure chain condensed from 8 PR descriptions to 1 paragraph |

### 25-frank-papers

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (scaffold → dossier gate → Hugo → publish) |
|  | "What Healthy Looks Like" section |
|  | "Verify" subsection |
|  | Recovery Paths (dossier gate fails, cover image broken, cross-link broken) |
|  | Missteps table (5 entries: Paper 00 landed before Phase 0, banner blending, dossier link double-render, spec path rebase, landing cards refactor) |
| Removed | Full `validate-dossier.py` pre-commit hook YAML (→ excerpt) |
|  | full `mermaid-frank.js` (→ excerpt without color pairs) |
|  | full `landscape` shortcode template (→ snippet) |
|  | speculative paper numbers for future papers |
| Modified | Restructured from "Why third series → Dossier gate → Scaffold → Hugo → Visual → Shortcodes → Cross-linking → Banners → Reverts → Rebases → Next" to "Architecture → Dossier gate → Scaffold → Hugo → Visual → Shortcodes → Cross-linking → Banners → Reverts → Missteps → Recovery" |
|  | banner iteration condensed from 3 SHAs to 1 paragraph |
### 26-edge-observability

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (Hop → Frank cross-cluster flow) |
|  | "What Healthy Looks Like" section (5 components) |
|  | "Verify" subsection |
|  | Recovery Paths (DatasourceError, IP banned wrong, Falco noise) |
|  | Missteps table (9 entries: _msg_field, GoatCOUNTER_PORT, Caddy access logs, CrowdSec persistence, container_runtime, DatasourceError, digest wrong filter, surge false positive, agent SKILL.md) |
| Removed | 4 screenshot refs (never captured) |
|  | full "agentic rewrite" deep dive (7 root causes → 3 paragraphs) |
|  | full `crowdsec-bouncer` Caddyfile (→ excerpt) |
|  | full GoatCounter bootstrapping with `kubectl exec` (→ operating post) |
|  | "What I would do differently" section |
|  | "What this enables" conclusion |
|  | Falco `kubectl exec` investigation (condensed) |
| Modified | Restructured from chronological "Problem → Architecture → Phase 1/2/3/4/5 → Deviations → What's different → What this enables" to "Architecture → Phase 1 (Logs) → Phase 2 (Analytics) → Phase 3 (Security) → Phase 4 (Falco) → Phase 5 (AI helper) → Missteps → Recovery → References" |

### 27-automation

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (AWX → web/task → PostgreSQL → EE pods) |
|  | "What Healthy Looks Like" section |
|  | "Verify" subsection |
|  | Recovery Paths (SSO down, job failed, OIDC secret stale) |
|  | Missteps table (6 entries: extra_settings quotes, PG volume init, Authentik blueprint 2026.x, settings category, wrong SSH key, extra_vars denylist) |
| Removed | 3 screenshot refs (→ operating post) |
|  | full "What I would do differently" checklist (→ Missteps notes) |
|  | "What this enables" future section |
|  | 7-line "one-word reply" SSH session narrative quotes |
| Modified | Restructured from two-operator metaphor narrative → "Architecture → Operators → CrashLoop 1 (quotes) → CrashLoop 2 (PG volume) → Login page (blueprint) → Secret (settings category) → Gate (ping) → Missteps → Recovery" |
|  | break-glass SSO procedure given dedicated section |

### 28-hermes-shell

| Category | Items |
|----------|-------|
| Added | `draft: false` (was not published) |
|  | Mermaid diagram (3 containers + 4 PVCs + memory flow) |
|  | "What Healthy Looks Like" section (3-container model) |
|  | "Verify" subsection |
|  | Recovery Paths (memory DB corrupt, sidecar crash, model revision issues) |
|  | Missteps table (5 entries: root-owned data, sidecar CrashLoop, model revision, fsGroup restart, exec probes) |
|  | "Next" link back to 00-overview |
| Removed | Hermes-brain git mirror and Obsidian memory layers (speculative, not yet deployed) |
|  | full `PGDATA` path discussion with `initdb` ownership details |
|  | original "I ran it on my own agent-shell-base lineage" opening (condensed) |
| Modified | Restructured from "Why rebuild → Architecture → 5 failures → Memory → Retired → What's next" to "Architecture → Why memory sidecar → Failure 1–5 → Memory continuity → Retired → Missteps → Recovery" |
|  | each failure condensed from narrative paragraph to problem → root cause → fix |
|  | published post (was draft) |
