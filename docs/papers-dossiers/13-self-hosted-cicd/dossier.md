---
paper: 13-self-hosted-cicd
status: ready
---

## Vendors in scope (≥3, typically 4–6)
- name: Gitea + Tekton + Zot
  positioning: "Three-tool stack — Gitea (git host), Tekton (Kubernetes-native pipeline engine using CRDs as build steps), Zot (CNCF OCI-conformant registry). Manifests-as-code at every layer; Frank's pick."
  primary_url: "https://tekton.dev/docs/concepts/"
- name: GitLab CE
  positioning: "All-in-one self-hosted platform — built-in git host, CI/CD runner, container registry, package registry, issue tracker. A single Rails monolith plus runners; the GitHub-equivalent in one package."
  primary_url: "https://docs.gitlab.com/ee/install/"
- name: Forgejo + Woodpecker CI
  positioning: "Lightweight homelab pattern — Forgejo (community-governed Gitea fork) plus Woodpecker (Drone fork). One-tool-each, minimal-ops; the most popular small-scale self-host combo on r/selfhosted."
  primary_url: "https://woodpecker-ci.org/docs/intro"
- name: Drone CI
  positioning: "Container-native CI — every pipeline step is a container, simple YAML, lightweight server + agent model. The architectural predecessor of Tekton's pods-as-steps approach."
  primary_url: "https://docs.drone.io/"
- name: Jenkins
  positioning: "The heritage incumbent — JVM controller, Groovy DSL pipelines, vast plugin ecosystem, agent-as-VM (or container) build runners. Two decades of accumulated CI design patterns and warts."
  primary_url: "https://www.jenkins.io/doc/book/pipeline/"
- name: GitHub Actions
  positioning: "The SaaS baseline — fully managed, generous free tier for OSS, marketplace of pre-built actions. The thing self-hosted CI/CD exists to compete with."
  primary_url: "https://docs.github.com/en/actions"

## Primary sources (≥5, ≥3 distinct type values)
- title: "Tekton — Concepts (Pipelines, Tasks, TaskRuns, PipelineRuns)"
  type: vendor-docs
  url: "https://tekton.dev/docs/concepts/"
  quoted_passages:
    - "Tekton Pipelines are a Kubernetes-native, lightweight, and easy-to-use framework that allow you to build CI/CD systems."
    - "A Task defines a series of ordered Steps that you want to execute. Each Step runs in its own container image."
  relevance: "Vendor's authoritative description of Tekton's pods-as-steps model — Tasks are CRDs, Steps are containers, PipelineRuns and TaskRuns are runtime objects. Grounds the §3 architecture diagram and underwrites the §1 claim that Tekton makes the pipeline itself a manifest in Git."

- title: "Tekton Triggers — EventListeners and Interceptors"
  type: vendor-docs
  url: "https://github.com/tektoncd/triggers/blob/main/docs/interceptors.md"
  quoted_passages:
    - "Interceptors are an extension mechanism that can be used to validate and modify the events that pass through them, including the headers and the body of the request."
    - "The CEL Interceptor can be used to apply CEL expressions to the request body, headers, or other parts of the request."
  relevance: "Definitive description of Tekton Triggers' interceptor mechanism — the `cel` interceptor is what makes Gitea-webhook-to-Tekton-pipeline wiring possible (matching `X-Gitea-Event`, not `X-GitHub-Event`). Load-bearing source for the §5 scar about the github interceptor silently dropping Gitea events."

- title: "Gitea — Webhooks documentation"
  type: vendor-docs
  url: "https://docs.gitea.com/usage/webhooks"
  quoted_passages:
    - "Gitea supports webhooks for repository events. To set up webhooks, in your repository, click on Settings → Webhooks → Add Webhook."
    - "Gitea webhooks send the following headers: X-Gitea-Event, X-Gitea-Delivery, X-Hub-Signature, X-Hub-Signature-256."
  relevance: "Vendor confirmation that Gitea sends `X-Gitea-Event` (not `X-GitHub-Event`). This is the single header difference that makes the Tekton `github` interceptor drop every Gitea webhook silently. Cited in §5's scar callout."

- title: "Zot — Architecture overview"
  type: vendor-docs
  url: "https://zotregistry.dev/v2.1.0/general/architecture/"
  quoted_passages:
    - "Zot is a production-ready vendor-neutral OCI-native container image registry that supports the OCI Distribution and Image Specifications."
    - "Zot's modular architecture supports pluggable storage backends, authentication providers, and a sync mechanism that can mirror from other registries."
  relevance: "Vendor's architectural description of Zot as an OCI-native, CNCF-incubated registry. Grounds the §3 architecture diagram (Zot as the image destination) and the §7 roadmap claim that OCI registries are absorbing arbitrary artefact storage."

- title: "GitHub — GitHub Actions now supports CI/CD (free for public repos)"
  type: paper
  url: "https://github.blog/2019-08-08-github-actions-now-supports-ci-cd/"
  quoted_passages:
    - "GitHub Actions is free for public repositories, providing CI/CD with up to 20 concurrent jobs and a marketplace of pre-built actions."
    - "Hosted runners are available across Linux, macOS, and Windows, with 2,000 free minutes per month for private repositories on the Free plan."
  relevance: "GitHub's own announcement framing of Actions as the SaaS baseline that self-hosted CI/CD competes with. Establishes the cost-curve geometry the rest of the paper measures against (free for OSS at small scale, expensive almost immediately above)."

- title: "Frank — Tekton, Gitea, and Zot gotchas (v1 Task computeResources, X-Gitea-Event header, Zot v0.1.0 missing TLS/auth)"
  type: postmortem
  url: "https://github.com/derio-net/frank/blob/main/agents/rules/frank-gotchas.md"
  quoted_passages:
    - "v1 Task uses `computeResources` not `resources` — schema validation silently fails the whole app."
    - "Gitea sends `X-Gitea-Event` (not `X-GitHub-Event`) — use `cel` interceptor, not `github`."
    - "Zot Helm chart v0.1.0 too minimal — use v0.1.60+ for TLS/auth/persistence."
    - "Gitea `webhook.ALLOWED_HOST_LIST` blocks in-cluster delivery — add `*.svc.cluster.local`."
  relevance: "Frank's own running postmortem registry — concrete operational scars accumulated while running Gitea + Tekton + Zot in production for this learning platform. Provides source-of-truth dates and recovery commands for the §5 scar callouts and underwrites the §6 decision-tree branches."

## Frank artefacts (≥3, ≥2 distinct kind values)
- kind: yaml
  path_or_url: "apps/tekton/manifests/github-listener/"
  date: 2026-03-15
  demonstrates: "Frank's Tekton EventListener + cel-interceptor wiring for Gitea webhooks. The listener exposes a LoadBalancer at 192.168.55.223 for external GitHub-style webhooks; the cel interceptor matches on `X-Gitea-Event` (not `X-GitHub-Event`) because the Tekton-bundled `github` interceptor filters on the wrong header for Gitea-origin events. This is the wiring that makes a Gitea push trigger a PipelineRun without an afternoon of debugging dropped events."

- kind: yaml
  path_or_url: "apps/zot/values.yaml"
  date: 2026-03-22
  demonstrates: "Frank's Zot install — chart pinned at v0.1.60+ (NOT v0.1.0 — see incident below), exposed at LB IP 192.168.55.210 (port 5000 HTTPS), htpasswd auth with `ZOT_PUSH_PASSWORD` from SOPS, Longhorn-backed PVC for image storage. The three-line summary of the three-tool stack's registry tier."

- kind: incident
  path_or_url: "agents/rules/frank-gotchas.md"
  date: 2026-03-15
  demonstrates: "Tekton v1 Task validation silently failed: we wrote `spec.resources` (the v1beta1 field). The CRD schema accepted it without error, but the runtime ignored it entirely — the build pod ran without the resource limits we believed we'd set. The whole ArgoCD Application reported Synced/Healthy. The schema migration from v1beta1 to v1 isn't graceful — it eats fields whose name differs by one letter, with no error. Recovery: rename to `computeResources`."

- kind: incident
  path_or_url: "agents/rules/frank-gotchas.md"
  date: 2026-03-18
  demonstrates: "Tekton EventListener with a `github` interceptor refused to fire on Gitea pushes. Gitea sends `X-Gitea-Event`, not `X-GitHub-Event`. The github interceptor doesn't log rejections — it silently drops the event. The cost was an afternoon of staring at the EventListener pod's log looking for an error message that wasn't there. Recovery: replace `github` with a `cel` interceptor matching the actual header."

- kind: incident
  path_or_url: "agents/rules/frank-gotchas.md"
  date: 2026-03-22
  demonstrates: "Zot Helm chart v0.1.0 has no first-class TLS, no auth, no persistence story — those schema fields didn't land until v0.1.60+. Frank pinned at v0.1.0 because it was the chart's first GA release. The lesson: pinning to .0 because it's the GA isn't the same as pinning to .0 because it's stable. A new chart's first GA can still be feature-incomplete relative to the project's documented capabilities."

## Diagrams planned
- landscape:
    x_axis: "Three composable tools ↔ All-in-one platform"
    y_axis: "Agent-based runners ↔ Kubernetes-native pods-as-steps"
    vendors_plotted: ["Gitea + Tekton + Zot", "GitLab CE", "Forgejo + Woodpecker", "Drone CI", "Jenkins", "GitHub Actions"]
- architecture_comparison:
    vendors: ["Gitea + Tekton + Zot", "GitLab CE", "Forgejo + Woodpecker", "Drone CI", "Jenkins"]
- decision_tree:
    leaves: 4
    description: "Question: who runs your builds, who stores your images, and what is the tax? Branches on 'solo dev / OSS repo?' (GitHub Actions) and 'three tools or one?', terminating in: GitHub Actions (SaaS), Forgejo + Woodpecker (tiny homelab), Gitea + Tekton + Zot (Frank's pick), GitLab CE + Runner (enterprise)."

## Named gaps (≥1)
- "No apples-to-apples 'self-hosted CI/CD tax' benchmark exists in the public literature at homelab-to-small-team scale — i.e., a measurement of the bundled operational overhead (server CPU/RAM for the controller, persistent storage growth for the registry, ops time per pipeline failure, webhook latency at the seams between tools, total wall-clock build time vs GitHub Actions for the same workload) at 1–10 concurrent builds. Published comparisons cover either feature matrices (Jenkins vs Tekton vs Drone checklists) or single-dimension benchmarks (Tekton pod startup latency in isolation) but never the bundled tax that determines whether self-hosting is worth running at all vs paying GitHub's per-minute meter. The single most useful number for a decision-maker — 'how many hours per month will this stack cost a single operator?' — does not exist as published work."

## Counter-arguments considered (≥1)
- "For a solo developer with an open-source repo, GitHub Actions is free, zero-ops, has a marketplace of pre-built actions, and runs builds in seconds — why doesn't that win for Frank? Answer: same shape as Papers 04 and 14. Frank is a learning platform. The reason to run Gitea + Tekton + Zot is to encounter the Tekton v1 schema-eats-fields trap, the X-Gitea-Event header mismatch, the Zot v0.1.0 missing-TLS-auth-persistence triple, the Gitea ALLOWED_HOST_LIST in-cluster block — first-hand. A developer who has internalized these lessons can rationally pick GitHub Actions and pay for what they don't have to operate; a team that has not will reinvent the same scars when the day comes that GitHub Actions minutes get rate-limited or an air-gap requirement lands. The counter-argument wins for the team that has already paid the tuition; for Frank, paying the tuition is the point."
