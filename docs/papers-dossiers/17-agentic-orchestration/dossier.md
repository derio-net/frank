---
paper: 17-agentic-orchestration
status: ready
---

## Vendors in scope (≥3, typically 4–6)
- name: secure-agent-pod (Frank)
  positioning: "Frank — per-PV Kubernetes pod running s6-overlay v3 in non-root mode with sshd, mosh, tmux-resurrect, and an agent-CLI of choice; isolation by namespace + cgroup, state on a Longhorn PV. The 'safe workstation' Frank actually runs."
  primary_url: "https://github.com/just-containers/s6-overlay"
- name: VibeKanban (+ vk-issue-bridge)
  positioning: "Multi-agent task fan-out — a Kanban board with vk-ready labels on GitHub issues drives an MCP bridge that spawns vk-local execution sessions inside secure-agent-pod. The orchestrator/dispatcher layer above the workstation."
  primary_url: "https://modelcontextprotocol.io/introduction"
- name: Paperclip + Sympozium (Frank)
  positioning: "Paperclip is Frank's company-runner / heartbeat orchestrator; Sympozium is the control-plane web UI. Together they assign tasks to agents, capture cost events, and present a board view of in-flight work."
  primary_url: "https://github.com/derio-net/frank/blob/main/agents/rules/frank-gotchas.md"
- name: Coder.com
  positioning: "Commercial cloud-workspace platform — VS-Code-in-browser plus Terraform-managed Kubernetes/VM workstations with policy-as-code, RBAC, audit logs. The managed answer to 'where does the agent run?'."
  primary_url: "https://coder.com/docs"
- name: GitPod (Cloud devcontainers)
  positioning: "Commercial cloud devcontainer platform — ephemeral browser-based VS Code workspaces backed by `.devcontainer.json`, run on GitPod's infra or self-hosted Flex. Auto-prebuilds, OIDC, prebuilt images."
  primary_url: "https://www.gitpod.io/docs"
- name: Plain devcontainers / GitHub Codespaces
  positioning: "The null hypothesis — `.devcontainer.json` running on your laptop (VS Code Remote-Containers) or on Microsoft's Codespaces infra. No fleet, no orchestrator, no per-agent isolation beyond container boundaries."
  primary_url: "https://containers.dev/implementors/spec/"

## Primary sources (≥5, ≥3 distinct type values)
- title: "s6-overlay — README and architecture"
  type: vendor-docs
  url: "https://github.com/just-containers/s6-overlay"
  quoted_passages:
    - "s6-overlay is a series of init scripts and utilities meant to ease the creation of Docker images using s6 as a process supervisor."
    - "s6-overlay can run a container as a non-root user, but with caveats: the supervision tree still expects PID 1 to be its own pid1 process."
  relevance: "Vendor's authoritative description of how s6-overlay v3 supervises non-root container processes. Grounds the §3 architecture description of secure-agent-pod and the §5 scar on shareProcessNamespace fighting s6's PID 1 requirement. The 'non-root with caveats' wording is exactly the constraint Frank stepped on."

- title: "Coder.com — Platform documentation"
  type: vendor-docs
  url: "https://coder.com/docs"
  quoted_passages:
    - "Coder is a self-hosted cloud development environment platform that runs developer workspaces in your infrastructure."
    - "Workspaces are defined as code using Terraform, giving you policy-as-code, audit logs, and centralized control over development environments."
  relevance: "Definitive statement of the managed-platform value proposition. Anchors the §2 axis 'self-hostable vs managed' and the §6 decision-tree leaf for teams that need policy + audit + RBAC but don't want to build it from secure-agent-pod primitives themselves."

- title: "Development Containers Specification (containers.dev)"
  type: vendor-docs
  url: "https://containers.dev/implementors/spec/"
  quoted_passages:
    - "A development container is a running container with a well-defined tool/runtime stack and its prerequisites."
    - "The development container specification (devcontainer.json) is a metadata format used to configure development containers."
  relevance: "The upstream spec that Codespaces, GitPod, and VS Code Remote-Containers all implement. Underwrites the §2 'null hypothesis' positioning of plain devcontainers — they ARE the baseline, and every fancier vendor in the landscape extends this same JSON schema."

- title: "Model Context Protocol — Introduction"
  type: paper
  url: "https://modelcontextprotocol.io/introduction"
  quoted_passages:
    - "The Model Context Protocol (MCP) is an open protocol that standardizes how applications provide context to LLMs."
    - "MCP follows a client-server architecture where a host application can connect to multiple servers."
  relevance: "Anthropic's specification of the protocol that vk-issue-bridge and Paperclip's heartbeat orchestrator both speak. Anchors the §7 roadmap claim that MCP and the agent-control-plane are converging — orchestrator-vs-workstation may collapse into a single MCP deployment with two endpoints."

- title: "Claude Code — Security and isolation"
  type: vendor-docs
  url: "https://docs.anthropic.com/en/docs/claude-code/security"
  quoted_passages:
    - "Claude Code includes safeguards to help prevent destructive operations, but users are ultimately responsible for the code Claude writes and the commands it runs."
    - "We recommend running Claude Code in a sandboxed environment when granting auto-accept permissions."
  relevance: "Vendor's own statement on why a safe workstation matters — Anthropic explicitly recommends sandboxing for auto-accept flows. The 'ultimately responsible' wording is the exact framing for §1 (the capability) and §5 (Frank's choice to pay the per-PV pod tuition rather than auto-accept on a laptop)."

- title: "Agentic Misalignment — Anthropic Research"
  type: paper
  url: "https://www.anthropic.com/research/agentic-misalignment"
  quoted_passages:
    - "In our experiments, models from every developer we tested took actions like blackmailing fictional executives or leaking sensitive information when faced with goals that conflicted with their continued operation."
    - "Our findings underscore the importance of caution when deploying current models in roles with minimal human oversight and access to sensitive information."
  relevance: "Foundational paper on why agent isolation is not paranoia. Even frontier models from every vendor exhibit instrumental-goal-preserving misalignment under realistic deployment conditions. Anchors §1's framing of *blast radius* as the capability question and underwrites §6's branch from 'shared workstation' to 'per-agent isolation'."

- title: "Frank — Agent shells + Paperclip/Ruflo gotchas registry"
  type: postmortem
  url: "https://github.com/derio-net/frank/blob/main/agents/rules/frank-gotchas.md"
  quoted_passages:
    - "s6-overlay v3 in non-root mode needs `S6_KEEP_ENV=1`, `S6_VERBOSITY=2`, `with-contenv` shebangs (`#!/command/with-contenv bash` — `/command/`, NOT `/usr/bin/`), and `/run` chown'd to AGENT_UID at image build time."
    - "vk-issue-bridge's 30 s MCP timeout cascades to zombie execution_processes: bridge crash on timeout → vk-local request handler future drops → `Child::wait()` cancelled → setup/cleanup shell scripts exit but never reaped → DB rows stuck `status='running'` forever, UI shows workspaces stuck active with no output."
    - "`shareProcessNamespace: true` is incompatible with s6-overlay v3 (suexec must be PID 1) — use shared workspace volume + `kubectl exec -c <other>` for cross-container debugging."
    - "vk-local `limits.memory: 4Gi` is too tight in practice — `VK_MAX_CONCURRENT_EXECUTIONS=4` does NOT bound the cgroup once the bridge feeds 8+ cards (queued sessions retain memory; new images drift baseline)."
    - "Paperclip's \"Test environment\" runs in the `paperclip` app container, NOT the `paperclip-shell` sidecar — agent-CLIs installed via the shell PVC are invisible. Wire through the shared `/paperclip` PVC."
  relevance: "Frank's own running postmortem registry — concrete operational scars accumulated while running secure-agent-pod + VibeKanban + Paperclip + Sympozium in production for this learning platform. Provides source-of-truth dates and recovery commands for every §5 scar callout and underwrites the §6 decision-tree branches."

## Frank artefacts (≥3, ≥2 distinct kind values)
- kind: yaml
  path_or_url: "apps/secure-agent-pod/manifests/"
  date: 2026-04-15
  demonstrates: "Frank's canonical per-PV pod manifest — s6-overlay v3 in non-root mode (S6_KEEP_ENV=1, S6_VERBOSITY=2, with-contenv shebangs, /run chown'd at image build time), sshd at port 22 with cont-init.d/30-authorized-keys copying SOPS-managed keys, Mosh at UDP 60000-60015, tmux-resurrect for session restore, Longhorn-backed PVC mounted at /home/claude. The full surface of a safe agent workstation, expressed declaratively."

- kind: incident
  path_or_url: "agents/rules/frank-gotchas.md"
  date: 2026-03-30
  demonstrates: "shareProcessNamespace + s6 PID 1 incompatibility — we set `shareProcessNamespace: true` on a pod with s6-overlay v3 for cross-container debugging. s6's suexec must be PID 1; sharing the namespace fights that requirement. The pod failed to start in a non-obvious way. Replaced with a shared workspace volume + `kubectl exec -c <other>` for cross-container debugging."

- kind: incident
  path_or_url: "agents/rules/frank-gotchas.md"
  date: 2026-04-22
  demonstrates: "vk-issue-bridge 30s MCP timeout cascading to zombie execution_processes — bridge crash on timeout → vk-local request handler future drops → Child::wait() cancelled → setup/cleanup shell scripts exit but never reaped → DB rows stuck status='running' forever, UI shows workspaces stuck active with no output. Recovery: `kubectl exec -c vk-local -- kill -TERM 1` triggers vk-local-only restart whose startup orphan-cleanup marks rows failed. Durable fix lives in `superpowers-for-vk`."

- kind: incident
  path_or_url: "agents/rules/frank-gotchas.md"
  date: 2026-05-08
  demonstrates: "vk-local 4Gi cgroup drift under sustained bridge feeding. `VK_MAX_CONCURRENT_EXECUTIONS=4` does NOT bound the cgroup once the bridge feeds 8+ cards — queued sessions retain memory, new images drift baseline. Concurrency limit doesn't bound the cgroup; only image-side resource reservation does. Keep at 8Gi until the bridge slot count is bound below the executor cap AND a soak under busy load proves the floor."

- kind: incident
  path_or_url: "agents/rules/frank-gotchas.md"
  date: 2026-05-12
  demonstrates: "Paperclip's 'Test environment' container-boundary surprise — runs in the paperclip app container, NOT the paperclip-shell sidecar. Agent-CLIs installed via the shell PVC are invisible at runtime; wire through the shared /paperclip PVC (`npm install --prefix /paperclip/agent-bin <pkg>` from the shell, PATH-suffix on the paperclip container). The 'shell sidecar' is for humans; the 'app container' is for the test runner — they share storage but not PATH."

- kind: yaml
  path_or_url: "apps/vibekanban/values.yaml"
  date: 2026-05-08
  demonstrates: "The orchestrator side — vk-local executor with VK_MAX_CONCURRENT_EXECUTIONS, relay sidecar (PORT=8081, HOST=0.0.0.0, image with /usr/local/bin/relay-server), SPAKE2 enrollment-code semantics (one-time use), resource limits at 8Gi after the cgroup-drift soak. Companion to the secure-agent-pod manifest — the workstation is what runs; this is what dispatches."

## Diagrams planned
- landscape:
    x_axis: "Shared workstation ↔ Per-agent pod"
    y_axis: "Single shell ↔ Fleet orchestrated"
    vendors_plotted: ["secure-agent-pod", "VibeKanban", "Paperclip + Sympozium", "Coder.com", "GitPod", "devcontainers / Codespaces"]
- architecture_comparison:
    vendors: ["secure-agent-pod", "VibeKanban", "Paperclip + Sympozium", "Coder.com", "GitPod"]
- decision_tree:
    leaves: 4
    description: "Question: how many agents run concurrently and who pays the orchestration tax? Branches on solo-vs-fleet and needs-policy-and-audit, terminating in: laptop devcontainer/Codespaces, Coder.com (managed), secure-agent-pod + VibeKanban + Paperclip (Frank's pick), or GitPod (shared cloud IDE)."

## Named gaps (≥1)
- "No apples-to-apples 'agent-workstation safety tax' benchmark exists in the public literature — i.e., a measurement of per-agent CPU/RAM overhead, network egress per agent-hour, supervisor blast-radius probability (what fraction of agent runs need human intervention?), and debugging time on long-tail failures (s6 cont-init boot-only behaviour, cgroup-not-bounding-cgroup, PID-namespace-fights-PID-1, container-vs-sidecar PATH surprises). Published comparisons cover either single-dimension benchmarks (cold-start latency on Codespaces vs GitPod vs local) or feature checklists (Coder.com vs GitPod table on the vendor sites). The single most useful number for a decision-maker — 'how many hours per month will running agents on this platform cost you in ops time?' — does not exist as published work, and the second-most-useful number ('what fraction of an autonomous agent's runs need supervisor intervention?') is at best anecdotal in vendor case studies."

## Counter-arguments considered (≥1)
- "For a solo developer running one Claude session in a devcontainer on their laptop, plain VS Code Remote-Containers is the rational choice — why doesn't that win for Frank? Answer: same shape as Paper 04. Frank is a learning platform AND a fleet — multiple agents, multiple humans, multiple time zones, multiple Frank-owned repos being touched concurrently. The reason to run secure-agent-pod + VibeKanban + Paperclip + Sympozium is to encounter the s6-overlay v3 PID-1 fight with shareProcessNamespace, the vk-issue-bridge 30s timeout zombie cascade, the vk-local 4Gi cgroup drift, the cont-init.d boot-only authorized_keys behaviour, the Paperclip Test-environment container-boundary surprise — first-hand. A team that has internalized these lessons can rationally pick Coder.com or GitPod and pay the vendor instead; a team that has not will reinvent the same scars at production scale, where the cost of discovery is measured in 'an agent committed a credential to a public repo at 2am' rather than a Telegram alert in a private channel. The counter-argument wins for the team that has already paid the tuition; for Frank, paying the tuition is the point."
