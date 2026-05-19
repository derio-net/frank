---
paper: 14-progressive-delivery
status: draft
---

## Vendors in scope (≥3, typically 4–6)
- name: Argo Rollouts
  positioning: "Argo project — Kubernetes-native controller for canary and blueGreen Deployments, workloadRef integration with existing Deployments, replica-count fallback when no traffic router is wired."
  primary_url: "https://argo-rollouts.readthedocs.io/en/stable/"
- name: Flagger
  positioning: "Flux ecosystem — operator-driven canary with first-class multi-mesh traffic routing (Istio, Linkerd, App Mesh, NGINX, Contour, Gloo, Cilium)."
  primary_url: "https://docs.flagger.app/"
- name: Linkerd (built-in traffic split)
  positioning: "Buoyant — service mesh with SMI/HTTPRoute traffic-split primitives; canary as a mesh-native feature, not a separate controller."
  primary_url: "https://linkerd.io/2.16/features/traffic-split/"
- name: Spinnaker (Kayenta)
  positioning: "Netflix/Google heritage CD — automated canary analysis with Kayenta, multi-cloud pipelines, the most mature canary-analysis engine in the space."
  primary_url: "https://spinnaker.io/docs/guides/user/canary/"
- name: Istio + Flagger
  positioning: "The 'service-mesh tax' case study — Flagger as canary controller on top of a full Istio mesh; per-request traffic routing at the cost of mesh complexity."
  primary_url: "https://istio.io/latest/docs/tasks/traffic-management/"
- name: Vanilla Deployments + manual promotion
  positioning: "The null hypothesis — `kubectl rollout restart` plus a human watching dashboards; no controller, no metric gate, no traffic split."
  primary_url: "https://kubernetes.io/docs/concepts/workloads/controllers/deployment/"

## Primary sources (≥5, ≥3 distinct type values)
- title: "Argo Rollouts — Canary strategy"
  type: vendor-docs
  url: "https://argo-rollouts.readthedocs.io/en/stable/features/canary/"
  quoted_passages:
    - "The canary deployment strategy is a way to roll out new versions of an application that incrementally shifts traffic to the new version."
    - "With Argo Rollouts, you can define a canary strategy that specifies the percentage of traffic to be sent to the new version and the duration of each step."
  relevance: "Vendor's authoritative description of how Argo Rollouts' canary strategy is structured around `setWeight` steps with optional pauses and metric gates. Grounds the §3 architecture comparison in Argo's own model and underwrites the §5 description of Frank's 20→50→100 staged rollout."

- title: "Flagger — How it works"
  type: vendor-docs
  url: "https://docs.flagger.app/usage/how-it-works"
  quoted_passages:
    - "Flagger takes a Kubernetes deployment and optionally a horizontal pod autoscaler (HPA), then creates a series of objects (Kubernetes deployments, ClusterIP services, and a service mesh or ingress controller routing configuration) to drive the canary analysis and promotion."
    - "Flagger requires a service mesh or an ingress controller for traffic routing."
  relevance: "Definitive statement that Flagger's design assumes a traffic router (mesh or ingress). This is the architectural fork that distinguishes Flagger from Argo Rollouts and the load-bearing claim behind the §6 decision-tree branch on 'service mesh already deployed?'."

- title: "Automated Canary Analysis at Netflix with Kayenta (Netflix Tech Blog)"
  type: paper
  url: "https://netflixtechblog.com/automated-canary-analysis-at-netflix-with-kayenta-3260bc7acc69"
  quoted_passages:
    - "Kayenta is a platform for automated canary analysis (ACA). It is used by Netflix in production for thousands of deployments each day."
    - "By examining a wide range of metrics, an ACA implementation makes a much more robust assessment of canary health than humans inspecting graphs."
  relevance: "Foundational writeup of Kayenta and the term 'automated canary analysis'. Anchors the §2 axis 'manual gating ↔ automated canary analysis' and the §7 roadmap claim that AnalysisTemplate is converging on Kayenta-shaped multi-metric, multi-interval analysis."

- title: "Codefresh — Argo Rollouts vs Flagger comparison"
  type: benchmark
  url: "https://codefresh.io/learn/argo-rollouts/argo-rollouts-vs-flagger-comparing-leading-kubernetes-canary-tools/"
  quoted_passages:
    - "Argo Rollouts is a Kubernetes controller that provides advanced deployment capabilities for Kubernetes applications, including blue-green and canary deployments."
    - "Flagger is a progressive delivery tool that automates the release process for applications running on Kubernetes."
  relevance: "Practitioner-level head-to-head that explicitly compares Argo Rollouts and Flagger on traffic-router coupling, metric-gating model, and BlueGreen support. Closest thing to a controlled comparison in the public literature and the source of the §3 cross-vendor shared-shape diagrams."

- title: "Frank — Argo Rollouts gotchas (Cilium plugin 404, workloadRef.scaleDown default, Prometheus empty-vector cascade)"
  type: postmortem
  url: "https://github.com/derio-net/frank/blob/main/agents/rules/frank-gotchas.md"
  quoted_passages:
    - "`workloadRef.scaleDown` defaults to `never` — set `onsuccess` explicitly or both Rollout + chart Deployment serve traffic."
    - "`workloadRef` \"leaks\" to a healthy-looking Helm Deployment when reconcile aborts pre-workload-phase (missing AnalysisTemplate, missing traffic-router plugin, etc.) — the ONLY signal is the controller pod log; `kubectl get rollout` looks identical to a steady-state run."
    - "Prometheus provider panics on empty result vector → metric `phase: Error` → 10s-cadence retry → canary aborts in ~50s. Verify metric exists + has samples first."
    - "LiteLLM Prometheus is Enterprise-only — OSS image emits no `litellm_*` metrics."
  relevance: "Frank's own running postmortem registry — concrete operational scars accumulated while running Argo Rollouts in production for this learning platform. Provides source-of-truth dates and recovery commands for the §5 scar callouts and underwrites the §6 decision-tree branches."

## Frank artefacts (≥3, ≥2 distinct kind values)
- kind: yaml
  path_or_url: "apps/litellm/manifests/rollout.yaml"
  date: 2026-05-04
  demonstrates: "Frank's canonical Argo Rollouts canary on LiteLLM. Replica-count canary (no traffic router): 5 replicas, 20→50→100 setWeight with manual pauses at each step. `workloadRef.scaleDown: onsuccess` is explicit — without it, both the Rollout's canary ReplicaSet AND the chart's Deployment serve traffic at the same time. The Helm chart's Deployment is the workloadRef target; ArgoCD `ignoreDifferences` on `apps/Deployment/spec.replicas` prevents fighting the controller's scale-down."

- kind: incident
  path_or_url: "apps/argo-rollouts/values.yaml"
  date: 2026-04-13
  demonstrates: "The Cilium traffic-router plugin URL 404 that crash-looped the controller for 21 days. The plugin URL referenced in the original extras ConfigMap pointed at a release artefact that had never been published. The controller could not load it, but the Rollout sat stuck at Step 0/6 while the Helm-managed Deployment quietly served traffic on its own — `kubectl get rollout` showed steady-state. Discovered only when we tried to use the canary for the first time."

- kind: incident
  path_or_url: "agents/rules/frank-gotchas.md"
  date: 2026-05-04
  demonstrates: "The LiteLLM-Prometheus-Enterprise-only canary abort: AnalysisTemplate query pointed at `litellm_request_total`, a metric only emitted by LiteLLM's Enterprise (paid) image. The OSS image we run emits nothing. Empty result vector → metric phase: Error → 10-second retry cadence → consecutive-error limit of 4 → canary aborts in ~50 seconds, every single time. The 'flaky deploy' was a working alarm pointed at silence."

- kind: yaml
  path_or_url: "apps/litellm/manifests/analysis-template.yaml"
  date: 2026-05-04
  demonstrates: "The error-rate AnalysisTemplate with the `status!~\"2..|3..\"` correction. The earlier query was `status=~\"5..\"` (5xx only), which had a blind spot: a canary serving 100% 4xx responses (e.g. an upstream returning 404 'no endpoints found') would evaluate as 0 errors / N requests = 0% → AUTO-PROMOTED while completely broken to consumers. Discovered 2026-05-04 during the first end-to-end rehearsal."

- kind: grafana-screenshot
  path_or_url: "blog/content/docs/papers/14-progressive-delivery/argo-rollouts-canary-TODO.png"
  date: 2026-05-19
  demonstrates: "Argo Rollouts canary view (kubectl plugin or Grafana panel) during a real LiteLLM promotion — staged 20/50/100 progress visible. Placeholder pending cluster-side capture."

## Diagrams planned
- landscape:
    x_axis: "Mesh required ↔ Mesh optional"
    y_axis: "Manual gating ↔ Automated canary analysis"
    vendors_plotted: ["Argo Rollouts", "Flagger", "Linkerd traffic split", "Spinnaker (Kayenta)", "Istio + Flagger", "Vanilla Deployment + manual"]
- architecture_comparison:
    vendors: ["Argo Rollouts", "Flagger", "Linkerd traffic split", "Spinnaker (Kayenta)", "Istio + Flagger"]
- decision_tree:
    leaves: 4
    description: "Question: who staged-promotes your changes, and what tax do they charge? Branches on stateful-RWO (no progressive delivery applicable) and service-mesh-already-deployed, terminating in: plain Recreate Deployment, Argo Rollouts (Frank's pick), Flagger (mesh shop), Spinnaker+Kayenta (scale > human pause-button)."

## Named gaps (≥1)
- "No apples-to-apples 'progressive-delivery tax' benchmark exists in the public literature — i.e., a measurement of total operational overhead (controller CPU/memory, mesh sidecar overhead per request, metric provider scrape cost, ops time per rollout, debugging time on the long-tail failures like the workloadRef-pre-phase-abort) at small-to-medium cluster scale (3–20 nodes). Published comparisons cover either feature matrices (Argo Rollouts vs Flagger checklist) or single-dimension benchmarks (Istio sidecar P50/P99 latency in isolation) but never the bundled tax that determines whether progressive delivery is worth running at all. The single most useful number for a decision-maker — 'how many hours per month will this controller cost you?' — does not exist as published work."

## Counter-arguments considered (≥1)
- "For a 6-node homelab cluster with mostly stateful workloads and a single human operator, plain `Recreate` Deployments plus manual verification by watching Grafana is the rational choice — why doesn't that win for Frank? Answer: same shape as Paper 04. Frank is a learning platform. The reason to run Argo Rollouts is to encounter the `workloadRef.scaleDown` trap, the Prometheus-empty-vector cascade, the missing-plugin-URL crash loop, the 4xx-blind successCondition — first-hand. A team that has internalized these lessons can rationally skip the controller and keep `kubectl rollout restart`; a team that has not will reinvent the same scars at production scale, where the cost of discovery is measured in customer SLO breaches rather than a Telegram alert at 11pm. The counter-argument wins for the team that has already paid the tuition; for Frank, paying the tuition is the point."
