# Building Series Rewrite — Per-Post Changelog

All 34 building posts rewritten with the educational methodology: set-the-stage openings, narrative arcs with difficulties overcome, Mermaid diagrams, real Missteps from git history, and Frank's voice focused on teaching.

## Conventions Applied to Every Post

| Category | Items |
|----------|-------|
| Added | `reader_goal`, `diataxis`, `last_updated` frontmatter fields |
| Added | "Next" link at the end of every post (except 33-hermes-shell, the finale, which links back to 00-overview) |
| Added | Missteps table (real incidents from git history with commit references) |
| Added | Recovery Path table (symptom → cause → fix) |
| Removed | `{{< relref >}}` shortcodes replaced with plain `/docs/building/NN-slug` paths (Hugo build errors when linked posts are `draft: true`) |
| Removed | MEDIA/screenshot placeholders (drafting artifacts, never captured) |
| Removed | ASCII architecture diagrams replaced with Mermaid `flowchart LR` |
| Modified | Chronological narrative restructured to tutorial flow (architecture → deploy → gotchas → verify → references) |
| Modified | Verbose session narrative condensed |
|  | "I tried X then Y then Z" → "X was wrong, Y was the fix" |
### 00-overview

| Category | Items |
|----------|-------|
| Added | Cover images referenced for each layer |
|  | compact 34-layer table (layer, post title, weight, operating post link) replacing prose descriptions |
| Removed | Full list of 7 tags that didn't match any existing post tag |
| Modified | Mostly kept as-is — it is a reference index, not a teaching post |

### 01-introduction

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (operator → Talos → Omni → K8s → ArgoCD → apps) |
|  | Missteps table (4 rows: USB boot, Omni VLAN, network race, power budget) |
|  | Recovery Path table (4 rows) |
| Removed | ASCII art state machine (→ Mermaid) |
|  | chronological firmware-log references (too granular for a tutorial) |
| Modified | Restructured from "day-by-day build log" to "Architecture → Machine choices → Network → Power → Boot → OS → GitOps → Plan" |

### 02-foundation

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (3 Cilium LB examples) |
|  | Missteps table (5 rows: Talos version naming, `apply-config` image-pull, etcd member count, Omni's missing VLAN 10, Longhorn default replica) |
|  | Recovery Path table (5 rows) |
| Removed | `{{< relref >}}` to 01-introduction |
|  | the ArgoCD RBAC narrative (condensed to 1 warning box) |
|  | the full "cluster bootstrap" checklist (condensed to a procedures list) |
| Modified | Restructured from chronological bootstrap to "OS → GitOps → Storage → Networking → Security → Verify" |

### 03-storage

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (data flow: pod → PVC → Longhorn → 3 replicas) |
|  | Missteps table (3 rows: fsGroup, `/var/lib/longhorn` disk, 6-day rebuild) |
|  | Recovery Path table (4 rows) |
| Removed | 40-line file tree of `/var/lib/longhorn/` |
|  | 3 `{{< relref >}}` to 02-foundation |
| Modified | Expanded CSI-resizer section (ArgoCD's `replace: true` vs `fsGroup` interaction is the most non-obvious gotcha in the entire layer) |
|  | restructured to "Architecture → Deploy → fsGroup → Disk → Disk Health → Backup → Verify" |
### 04-gpu-compute

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (GPU nodes → NVIDIA operator → DRA → Intel DRA → workloads) |
|  | Missteps table (7 rows: `nvidia` in name, Intel DRA vendoring, NFD→NodeFeature, GFD race, TimeSlider, DRA-PATCH timing, MCP split) |
|  | Recovery Path table (6 rows) |
| Removed | `{{< relref >}}` to 02-foundation |
|  | 3 `<!-- MEDIA -->` placeholders |
|  | chronological "first I tried X then Y" narrative in the Intel DRA section |
| Modified | Restructured from a single long narrative into "GPU nodes → NVIDIA operator → node labeling → Intel DRA → GPU sharing → Gotchas → Verify" |

### 05-gitops

| Category | Items |
|----------|-------|
| Added | Mermaid timeline diagram (Pulumi → Flux → ArgoCD with version arrows) |
|  | Missteps table (3 rows: VCluster-Approver, `ServerSideApply`, app-of-apps CRD race) |
|  | Recovery Path table (4 rows) |
| Removed | `{{< relref >}}` to 02-foundation |
|  | the Pulumi section was condensed into a 1-paragraph "why we left" instead of a full migration narrative |
| Modified | Restructured from "State of the stack → What we switched to → Migration → ArgoCD deep-dive" to "Architecture timeline → App of Apps → ArgoCD deep-dive → Core components → Gotchas → Migration → Verify" |

### 06-fun-stuff

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (Razer peripherals → OpenRGB → gpu-1 USB → failure) |
|  | Missteps table (2 rows: Talos USB and Zigbee coexistence) |
|  | Recovery Path table (3 rows) |
| Removed | Original 256-color LED cycle screenshot ref |
|  | `{{< relref >}}` to 05-gitops |
|  | the 3-paragraph Philips Hue section (condensed to 1 sentence under "What's next") |
| Modified | Reorganized into "Architecture → OpenRGB plan → Talos limitations → Zigbee coexistence → Why it matters" |

### 07-observability

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (VM single → VMCluster migration flow) |
|  | Missteps table (8 rows: etcd PV default, `honorLabels`, S3 endpoint, streaming parser, vmauth routing, installImage, PVC growth, `-search.maxQueryDuration`) |
|  | Recovery Path table (6 rows) |
| Removed | Full 50-line `vmcluster.yaml` manifest → excerpt only |
|  | 4 `{{< relref >}}` to earlier posts |
|  | Grafana 11→12 upgrade section (→ Missteps table) |
|  | the `vmagent` section (condensed) |
| Modified | Restructured to "Architecture → VictoriaMetrics → VL → VMCluster migration → Grafana → vmalert → Gotchas → Verify" |
|  | the cardinality explosion gotcha moved to its own section with PromQL examples |
### 08-backup

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (BackupTarget → S3 → RecurringJob → Volume) |
|  | Missteps table (5 rows with commits: BackupTarget persistent, wrong NFS/S3, RecurringJob sync period, fsGroup 0 → root, PVC not in group) |
|  | Recovery Path table (5 rows) |
| Removed | `{{< relref >}}` for 03-storage and 07-observability |
| Modified | Reordered from "Prerequisites → Steps → Verify" to "Architecture → Target → Jobs → Groups → Deploy → Verify → Gotchas → Missteps" |

### 09-secrets

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (Infisical → ESO → ExternalSecret → Pod) |
|  | Missteps table (5 rows with commits: Infisical Helm broken on install, ESO CRD v1, 5-app split, project slug, LB race) |
|  | Recovery Path table (5 rows) |
| Removed | Explicit wiring diagram for each app (consolidated into 1 generic flow) |
|  | the Infisical Docker Compose section (→ deployed on-cluster) |
| Modified | Restructured from "Why Infisical → Deploy Infisical → Deploy ESO → Wire apps" to "Architecture → Infisical → ESO → Wire first app → Gotchas → Missteps" |

### 10-local-inference

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (GPU → Ollama → LiteLLM → apps) |
|  | Missteps table (5 rows with commits: Ollama keep_alive, `ollama_chat/` prefix, canary Cilium plugin, model pinning, OpenRouter API key location) |
|  | Recovery Path table (5 rows) |
| Removed | `{{< relref >}}` for 09-secrets and 04-gpu-compute |
|  | 2 MEDIA placeholders |
|  | the full "model ranking" table (condensed to the 5 chosen models) |
| Modified | Ollama section compressed — removed "deciding to use Ollama" justification (we already have the Papers series for that) |
|  | kept the CPU-only note for Hermes |

### 11-agentic-control-plane

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (post-rewrite flow + SSH → SSHD → Agent → LiteLLM → Ollama) |
|  | Missteps table (4 rows with commits: git-sourced chart `OPENAI_BASE_URL` injection, PodSecurity llmfit, PersonaPack not reconciled, s6-overlay config path) |
|  | Recovery Path table (4 rows) |
| Removed | `{{< relref >}}` for 10-local-inference |
|  | the entire "SSHD" section (→ Missteps for the s6-overlay path) |
| Modified | Restructured from "Why Sympozium → Why s6 → SSHD → Claude → Config → MCP → Secrets → Git-sourced → Operating" to "Architecture → Why Sympozium → Deploy → s6 → Claude → Config → MCP → Secrets → Gotchas → Missteps" |
### 12-gpu-talos-fix

| Category | Items |
|----------|-------|
| Added | 2 Mermaid diagrams (architecture: validation DaemonSet + DRA + PCIDevice |
|  | conflict: EtcFileSpec overlay) |
|  | Missteps table (5 rows with commits: EtcFileSpec conflict, `base_runtime_spec`, PCIDevice object missing, PostStart hook trap, `nvidia` in `name`) |
|  | Recovery Path table (5 rows) |
| Removed | `{{< relref >}}` for 04-gpu-compute |
|  | 4 MEDIA/screenshot placeholders |
|  | the 15-line `talosctl dmesg` output for the PCIe error (condensed to a sentence) |
| Modified | Restructured from chronological "bug → fix → second bug → second fix" to "Architecture → EtcFileSpec conflict → PCIDevice → PostStart → DRA → Verify → Missteps → Recovery" |

### 13-unified-auth

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (Authentik — 3 integration patterns) |
|  | Missteps table (5 rows with commits: blueprint YAML syntax, `AUTHENTIK_HOST`, ArgoCD self-management, 3.5Gi RAM, outpost assignment) |
|  | Recovery Path table (5 rows) |
| Removed | `{{< relref >}}` for 09-secrets and 12-gpu-talos-fix |
|  | MEDIA placeholder |
|  | the scheme-selection flow chart (→ Mermaid) |
| Modified | Restructured from "Why Authentik → Provisioning → OAuth2 → LDAP → Forward-auth → Blueprints → Gotchas" to "Architecture → Deployment → 3 integration patterns → Blueprints → SSO wiring → Gotchas → Missteps" |

### 14-multi-tenancy

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (vCluster → host cluster → tenant namespaces → child clusters) |
|  | Missteps table (5 rows with commits: template pattern, `syncBackend`, chart schema, CNI conflict, ArgoCD RBAC) |
|  | Recovery Path table (5 rows) |
| Removed | `{{< relref >}}` for 13-unified-auth |
|  | the full vcluster values.yaml (→ excerpts) |
|  | 3 MEDIA placeholders |
| Modified | Restructured from "Why vCluster → Install → Template → Experiment → Add users → Gotchas" to "Architecture → Deploy → Template → Chart schema → Persistent volumes → Users → Gotchas → Missteps" |

### 15-paperclip

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (Paperclip agent orchestrator flow) |
|  | Missteps table (5 rows with commits: probe deadlock, PVC rollout deadlock, fsGroup, memory tuning, shell sidecar) |
|  | Recovery Path table (5 rows) |
| Removed | `{{< relref >}}` for 11-agentic-control-plane |
|  | 3 `{{< screenshot >}}` refs |
|  | the full "company setup" walkthrough (→ operating post) |
|  | the SSH key copy instructions (→ operating post) |
| Modified | Restructured from "Architecture → Deploy → Company → Operating → Gotchas" to "Architecture → Deploy → Shell sidecar → Probe deadlock → PVC deadlock → Company setup → Memory → Gotchas → Missteps" |
### 16-media-generation

| Category | Items |
|----------|-------|
| Added | 2 Mermaid diagrams (GPU time-sharing between Ollama/ComfyUI/Switcher) |
|  | Missteps table (4 rows: Go cross-compile QEMU crash, image manifest platform, ArgoCD self-heal fight, model folder paths) |
|  | Recovery Path table (4 rows) |
|  | inline console output for GPU Switcher API |
| Removed | ASCII architecture (→ Mermaid) |
|  | `gpu-switcher-ui.png` and `gpu-switcher-toggle.cast` refs (never captured) |
|  | MEDIA placeholder |
|  | redundant "What's Running" paragraph |
| Modified | Restructured from "Constraint → Architecture → ComfyUI → Switcher → Model Downloads → What's Running" to "Architecture (Mermaid) → Three Apps → Model Downloads → Missteps → Recovery → References". GPU Switcher build condensed — removed full `docker buildx` command history |

### 17-public-edge

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (Internet → Caddy + Headscale + Tailscale DaemonSet + mesh) |
|  | Missteps table (5 rows with commits: Omni unreachable, missing Tailscale DS, config_strict, RollingUpdate deadlock, empty Cloudflare secret) |
|  | Recovery Path table (5 rows) |
| Removed | 3 screenshot/asciicast refs (drafting artifacts) |
|  | `{{< relref >}}` for operating post |
|  | full Blog CI Pipeline section (tangential) |
|  | minute-by-minute event log from Terminal #2 |
|  | Deviation Scorecard table at end |
|  | 3-paragraph meta-lesson conclusion |
| Modified | Restructured from chronological deviation narrative to deployer's sequence. Each deviation now has a bold heading with one-line "Lesson:" paragraph. 14 deviations preserved but compressed from ~300 lines to ~150 lines. Headplane Saga condensed from 6 sub-deviations to 4 tighter deviations |

### 18-persistent-agent

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (client → LB → SSH → Kali → PVC + Claude) |
|  | Missteps table (2 rows: SSH host key persistence, apt-get on every start) |
|  | Recovery Path table (3 rows) |
|  | inline verify console |
| Removed | `{{< relref >}}` for Layer 17 and Layer 14 |
|  | Storage Choice paragraph (redundant) |
|  | final "What's Running" bullet list |
| Modified | Restructured from "Why container → Why Kali → Architecture → Startup Script → SSH Key → Storage → Always-On Agent → What's Running" to "Architecture → Why Container/Kali → Deploy → Startup → Always-On Agent → Missteps → Recovery" |

### 19-progressive-delivery

| Category | Items |
|----------|-------|
| Added | 2 Mermaid diagrams (architecture + namespace layout) |
|  | Missteps table (5 rows with commits: Cilium plugin 404, workloadRef scaleDown, 5xx-only query, missing metric source, documented failure as happy path) |
|  | Recovery Path table (5 rows) |
| Removed | `{{< screenshot >}}` refs for 3 canary frames |
|  | full postmortem with multi-agent collaboration analysis (condensed to 3-bullet summary) |
|  | minute-by-minute event log |
|  | multi-agent discussion folder references |
|  | "Three independent green lights" paragraph |
| Modified | Restructured from "Architecture → Phase 1/2/3 → Operating → Gotchas → Postmortem → Postscript → References" to "Architecture → Phase 1/2/3 → Operating → Postmortem (condensed: 60 lines from 250) → Missteps → Recovery → References" |

### 20-workflow-automation

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (Authentik → n8n → PostgreSQL → Metrics → Grafana) |
|  | Missteps table (3 rows with commits: OIDC init unworkable, encryption key not set, RollingUpdate deadlock) |
|  | Recovery Path table (4 rows) |
| Removed | `{{< relref >}}` for 11, 15, 16 |
|  | 2 screenshot refs |
|  | ASCII architecture (→ Mermaid) |
|  | explicit "What's Running" section |
|  | `N8N_SECURE_COOKIE=false` gotcha (cluster now uses TLS) |
| Modified | Restructured from "Why per-user → Why gpu-1 → Architecture → Auth → Init → Secrets → Metrics → What's Running → Adding → Gotchas" to "Architecture → Why per-user/gpu-1 → Deploy table → Auth → Init → Secrets → Metrics → Adding → Missteps → Recovery" |

### 21-secure-agent-pod

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (secure-agent-pod + vk-local sidecar + PVC + 3 LBs) |
|  | Missteps table (5 rows with commits: PVC mount hiding image, `wait -n` supervision, Cilium FQDN LRU, non-root sshd, `/run/secrets` conflict) |
|  | Recovery Path table (5 rows) |
|  | inline verify console |
| Removed | `{{< relref >}}` for 18 and operating 14 |
|  | 7-manifest table (redundant) |
|  | "Why s6-overlay alternatives" section |
|  | bump alerts YAML block |
|  | full verification checklist table |
|  | GitHub App install-coverage edge cases |
|  | "What's Next" bullet list |
| Modified | Restructured from "Threat Model → Architecture → Image Lineage → Building → PVC Mount → sshd → K8s Manifests → Credentials → GitHub → Egress → Supervision → Bump → Decommission → Verify → Gotchas → What's Next" to "Architecture → Threat Model → Deploy → PVC Mount → sshd → SecurityContext → Egress → Credentials → s6-overlay → Missteps → Recovery → References" |
### 22-health-monitoring

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (VM → Blackbox + Pushgateway → Targets → Telegram) |
|  | Missteps table (5 rows with commits: ALERTS{}, SSE format, VMOperator webhook cert, honorLabels, Telegram dedup) |
|  | Recovery Path table (5 rows) |
| Removed | ASCII architecture (→ Mermaid) |
|  | MEDIA placeholder for Telegram screenshot |
|  | `{{< relref >}}` for 07-observability |
|  | repeated justification paragraphs |
|  | full probe output trimmed |
|  | "What's Next" M2 discussion |
| Modified | Restructured from "Problem → Architecture → BB → PW → Grafana → Telegram → Dashboard → ALERTS → VMOperator → Verify → Next → References" to "Architecture → BB → PW → Grafana Rules → SSE Gotcha → ALERTS Gotcha → Telegram → Dashboard → VMOperator → Missteps → Recovery → References" |

### 23-health-bridge

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (Grafana Alerting → Bridge → GitHub) |
|  | Missteps table (5 rows with commits: public repo leak, bug close by alertname, label format, power outage corpses, dead bugs on restart) |
|  | Recovery Path table (5 rows) |
| Removed | 2 MEDIA placeholders |
|  | `{{< relref >}}` for 22 |
|  | three chronological "Pass" sections → replaced by v0.x.y feature-increment sections |
|  | Caddy-Hop-Tailscale relay discussion (→ 27-cicd-platform) |
|  | github-pull-sync design (→ 27-cicd-platform) |
|  | CI/CD pipeline diagram for v0.1.0 |
| Modified | Restructured from chronological "v0.1.0 → Pass 3 → Closing loop → Power outage" to "Architecture → Problem → v0.1.0 → v0.2.0 → v0.3.0 → v0.4.0 → Missteps → Recovery → References" |

### 24-in-cluster-ingress

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (Pi-hole → Traefik → Direct proxy + Forward-auth services) |
|  | Missteps table (6 rows with commits: acme.json perms, DNS-01 NXDOMAIN, invalidation_flow, outpost assignment, ping ICMP, ALLOWED_HOSTS) |
|  | Recovery Path table (5 rows) |
| Removed | ASCII architecture (→ Mermaid) |
|  | 16-service ingressroute list condensed to 13 |
|  | full Dockerfile excerpt |
|  | 3-paragraph outpost assignment explanation |
| Modified | Gotchas table (7 rows) → Missteps table (6 rows, consolidated). PVC permissions section given more prominence |

### 25-vk-relay

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (Browser → Traefik → Relay sidecar ↔ vk-local agent) |
|  | Missteps table (3 rows with commits: forward-auth block, separate pod attempt, rule order) |
|  | Recovery Path table (4 rows) |
| Removed | ASCII architecture (→ Mermaid) |
|  | `{{< relref >}}` for 21, 24, 26 |
|  | "What Changed" file-change table |
|  | yamux multiplexing explanation (condensed from 6 paragraphs to 3 sentences + data flow) |
|  | SPAKE2 background (2 paragraphs → 1 sentence) |

### 26-vk-remote-self-host

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (Agent → VK Remote → PG + ElectricSQL → Browser) |
|  | Missteps table (5 rows with commits: wal_level, PostSync backoff, outpost assignment, no data migration, cross-namespace DNS) |
|  | Recovery Path table (5 rows) |
| Removed | `{{< relref >}}` for 21, 24, 25 |
|  | MEDIA placeholder |
|  | full Secrets table with YAML |
|  | "What Changed" file-change table |
|  | 3-paragraph data migration gotcha |
| Modified | Gotchas section (4 items) → Missteps table (5 rows with real commits). PG section condensed — full postgres.yaml kept but args explanation trimmed |

### 27-cicd-platform

| Category | Items |
|----------|-------|
| Added | 2 Mermaid diagrams (main architecture + inverted GitHub→Hop→Frank) |
|  | Missteps table (10 rows with commits: computeResources, ClusterInterceptor, webhook allowlist, HOME=/, Completed vs Succeeded, Kaniko config naming, sharing-key, SSH port unreachable, GIT_SSH_COMMAND, PodSecurity restricted) |
|  | Recovery Path table (5 rows) |
| Removed | ASCII architecture (→ Mermaid) |
|  | 8-app ArgoCD table |
|  | full cosign verify output |
|  | gitea-ci Pipeline YAML (described in prose) |
|  | secondary EventListener YAML |
| Modified | Gotchas section (7 items) → Missteps table (10 rows). Direction Inversion section condensed from ~100 lines to ~40 lines |
### 28-agent-images-sidecar

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (3 repos, 3 CI loops, 2 dispatch hops) |
|  | Missteps table (4 rows with commits: port 8081 bind race, "Please build web app first", PVC mount hides binary, bumper no-diff) |
|  | Recovery Path table (4 rows) |
| Removed | `{{< relref >}}` for 21, 26 |
|  | the full "Why split" justification (condensed to 2 paragraphs) |
|  | Bash verification with `jsonpath` (condensed to inline) |
|  | "What's next" section (Python sandbox plan) |
|  | full `build.yaml` CI workflow (condensed to excerpt) |
|  | artifact Dockerfile fork path (condensed) |
| Modified | Restructured from chronological "Why split → Architecture → repo → fork artifact → sidecar → bumper → gotchas" to "Architecture → repo → fork artifact → sidecar → bumper → Missteps → Recovery → References" |

### 29-ruflo

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (ruflo pod: server + shell + 3 PVCs + LiteLLM) |
|  | Missteps table (6 rows with commits: PostgreSQL unused, RVF shim broken, LiteLLM virtual key, shareProcessNamespace crash, SSR probes, npm EACCES) |
|  | Recovery Path table (5 rows) |
| Removed | `{{< relref >}}` for 15, 28 |
|  | the full ruvocal Dockerfile |
|  | the recursive "pile of process failures" section (PRs #48-#53 chain — too specific for tutorial) |
|  | the full SSH config for ruflo (→ operating post) |
|  | the Zero Frontier Keys principle (condensed to inline note) |
| Modified | Restructured from chronological narrative with 6 sub-sections to "Architecture → Two Images → MongoDB misdirection → RVF shim → LiteLLM key → shareProcessNamespace → Probes → Inventory → Install trap → Missteps → Recovery → References". The recursive failure chain condensed from 8 PR descriptions to 1 paragraph |

### 30-frank-papers

| Category | Items |
|----------|-------|
| Added | Missteps table (5 rows with commits: Paper 00 landed before Phase 0, banner blending, dossier link double-render, spec path rebase, landing cards refactor) |
|  | Recovery Path table (5 rows) |
| Removed | `{{< relref >}}` for 00-overview |
|  | full `validate-dossier.py` pre-commit hook YAML (condensed to excerpt) |
|  | full `mermaid-frank.js` (condensed to excerpt without color pairs) |
|  | full `landscape` shortcode template (condensed to snippet) |
|  | paper numbers for future papers ("probably auth, probably storage" — speculative) |
|  | the "Compatibility Rebases" section (condensed into Missteps table) |
| Modified | Restructured from "Why third series → Dossier gate → Scaffold → Hugo → Visual → Shortcodes → Cross-linking → Banners → Agent docs → Reverts → Rebases → Next" to "Architecture → Dossier gate → Scaffold → Hugo → Visual → Shortcodes → Cross-linking → Banners → Agent docs → Reverts → Missteps → Recovery → References". Banner image iteration section condensed from 3 iterations with SHAs to 1 paragraph |

### 31-edge-observability

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (Hop → Frank cross-cluster flow: Caddy/fluent-bit/CrowdSec/Falco → VL/GoatCounter/AA/Grafana) |
|  | Missteps table (9 rows with commits: _msg_field, GoatCOUNTER_PORT, Caddy access logs, CrowdSec persistence, container_runtime, DatasourceError, digest wrong filter, surge false positive, agent SKILL.md) |
|  | Recovery Path table (6 rows) |
| Removed | 4 screen shot refs (never captured) |
|  | `{{< relref >}}` for 24, 26 |
|  | the "agentic rewrite" deep dive (7 root causes condensed to 3 paragraphs from 60 lines) |
|  | the full `crowdsec-bouncer` Caddyfile (condensed to excerpt) |
|  | the full GoatCounter bootstrapping with `kubectl exec` (→ operating post) |
|  | the "What I would do differently" section (condensed into inline lessons) |
|  | the "What this enables" conclusion |
|  | the Falco `kubectl exec` investigation (condensed) |
|  | the `ai_adapter.py` TDD output (12 tests condensed to inline note) |
| Modified | Restructured from chronological "Problem → Architecture → Phase 1/2/3/4/5 → Deviations → What's different → What this enables" to "Architecture → Phase 1 (Logs) → Phase 2 (Analytics) → Phase 3 (Security) → Phase 4 (Falco) → Phase 5 (AI helper) → Missteps → Recovery → References". Deviations (digest lying, surge crying wolf, DatasourceError storm, agentic rewrite) condensed from 4 subsections into inline gotchas within each phase and Missteps table |

### 32-automation

| Category | Items |
|----------|-------|
| Added | Mermaid diagram (ArgoCD → awx-operator → CR → operator reconciliation → pods) |
|  | Missteps table (6 rows with commits: extra_settings quotes, PG volume init, Authentik blueprint 2026.x, settings category, wrong SSH key, extra_vars denylist) |
|  | Recovery Path table (5 rows) |
| Removed | `{{< relref >}}` for 33-hermes-shell (original post had relref to itself — circular) |
|  | inventory.png, job-template.png, smoke-ping-output.png screenshot refs (→ operating post) |
|  | the full "What I would do differently" checklist (condensed to Missteps table notes) |
|  | the "What this enables" future section |
|  | 7-line "one-word reply" narrative quotes from the SSH session |
| Modified | Restructured from two-operator metaphor narrative → "Architecture → Two operators → CrashLoop 1 (quotes) → CrashLoop 2 (PG volume) → Login page (blueprint) → Secret (settings category) → Gate (ping) → Missteps → Recovery → References". The narrative voice is preserved but condensed — removed the "I am a declarative cluster" opening paragraph in favor of a shorter framing |

### 33-hermes-shell

| Category | Items |
|----------|-------|
| Added | `draft: false` (was `true` — post now published) |
|  | Mermaid diagram (3 containers + memory PVC + LiteLLM) |
|  | Missteps table (5 rows with commits: root-owned data, sidecar CrashLoop, model revision, fsGroup restart, exec probes) |
|  | Recovery Path table (5 rows) |
|  | "Next" link to 00-overview |
| Removed | `{{< relref >}}` for 28 and 33 (self-referencing) |
|  | hermes-brain git mirror and Obsidian memory layers (speculative, not yet deployed) |
|  | the full `PGDATA` path discussion with `initdb` ownership details |
|  | the original post's "I ran it on my own agent-shell-base lineage" opening (condensed) |
| Modified | Restructured from "Why rebuild → Architecture → 5 failures → Memory → Retired → What's next → References" to "Architecture → Why memory sidecar → Failure 1-5 → Memory continuity → Retired → Missteps → Recovery → References". Each failure condensed from narrative paragraph to problem → root cause → fix format |
