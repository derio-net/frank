---
paper: 06-gitops-at-small-scale
status: ready
---

## Vendors in scope (≥3, typically 4–6)
- name: ArgoCD
  positioning: "Intuit/CNCF graduated — pull-mode reconciler with a polished UI and the App-of-Apps composition pattern."
  primary_url: "https://argo-cd.readthedocs.io/"
- name: Flux v2
  positioning: "Weaveworks/CNCF graduated — modular pull-mode reconciler (source-controller + kustomize-controller + helm-controller), Kustomize-first."
  primary_url: "https://fluxcd.io/"
- name: Jenkins X
  positioning: "CD-Foundation — opinionated all-in-one GitOps + Tekton + preview environments, optimized for app teams not platform teams."
  primary_url: "https://jenkins-x.io/"
- name: Cloud-managed GitOps (Anthos Config Management / EKS GitOps add-ons)
  positioning: "Hyperscaler-bundled — GKE Config Sync, Azure Arc, EKS Flux/ArgoCD add-ons. GitOps as a managed feature of the control plane."
  primary_url: "https://cloud.google.com/anthos/config-management"
- name: Spinnaker
  positioning: "Netflix-origin push-mode CD — pipeline-first, multi-cloud, predates the GitOps label. The push-mode foil for the §3 comparison."
  primary_url: "https://spinnaker.io/"
- name: Just bash + kubectl in CI
  positioning: "The null hypothesis — CI runs 'kubectl apply -f' against the cluster on push to main. No reconciler, no drift detection. Useful as the lower bound for the §6 decision tree."
  primary_url: "https://kubernetes.io/docs/concepts/cluster-administration/manage-deployment/"

## Primary sources (≥5, ≥3 distinct type values)
- title: "Argo CD — Architecture"
  type: vendor-docs
  url: "https://argo-cd.readthedocs.io/en/stable/operator-manual/architecture/"
  quoted_passages:
    - "Argo CD is implemented as a Kubernetes controller which continuously monitors running applications and compares the current, live state against the desired target state (as specified in the Git repo)."
    - "The application controller is a Kubernetes controller which continuously monitors running applications and compares the current, live state against the desired target state. It detects OutOfSync application state and optionally takes corrective action."
  relevance: "Vendor's own articulation of ArgoCD's reconciliation model — pull-mode controller that compares declared state against live state continuously. Anchors the §3 architecture diagram for ArgoCD and underwrites the §1 capability definition."

- title: "Flux — Core Concepts"
  type: vendor-docs
  url: "https://fluxcd.io/flux/concepts/"
  quoted_passages:
    - "Flux is a tool for keeping Kubernetes clusters in sync with sources of configuration (like Git repositories and OCI artifacts), and automating updates to configuration when there is new code to deploy."
    - "Flux is constructed with the GitOps Toolkit, a set of composable APIs and specialized tools for building Continuous Delivery on top of Kubernetes."
  relevance: "Definitive description of the GitOps Toolkit composition model — Flux is unbundled by design, where ArgoCD ships as a single application. Anchors the §2 axis (unbundled vs opinionated) and the §3 Flux architecture diagram."

- title: "OpenGitOps Principles v1.0.0"
  type: paper
  url: "https://opengitops.dev/"
  quoted_passages:
    - "Declarative: A system managed by GitOps must have its desired state expressed declaratively."
    - "Versioned and Immutable: Desired state is stored in a way that enforces immutability, versioning and retains a complete version history."
    - "Pulled Automatically: Software agents automatically pull the desired state declarations from the source."
    - "Continuously Reconciled: Software agents continuously observe actual system state and attempt to apply the desired state."
  relevance: "The CNCF/OpenGitOps working-group definition of what GitOps actually is. The four principles are load-bearing for §1 (the capability definition) and §6 (the decision-tree leaf where the 'just bash + kubectl' option fails Principle 3 and 4)."

- title: "GitOps — Operations by Pull Request (Alexis Richardson, Weaveworks, 2017)"
  type: talk
  url: "https://www.weave.works/blog/gitops-operations-by-pull-request"
  quoted_passages:
    - "By using Git as our source of truth and operations toolkit, we can keep declarative descriptions of all of our infrastructure and applications under version control."
    - "Our Git repository is the source of truth for what we want our system to look like. Our diff tools and convergence operators are how we get there."
  relevance: "The original Weaveworks blog post that named the practice. Cited as the historical origin of the GitOps label (the term predates both ArgoCD and Flux v2). Used in §1 to ground the capability in its 2017 articulation."

- title: "Frank — ArgoCD gotcha registry (symlink ComparisonError, manual-syncOptions-inheritance, root re-templating)"
  type: postmortem
  url: "https://github.com/derio-net/frank/blob/main/docs/runbooks/frank-gotchas/argocd.md"
  quoted_passages:
    - "ArgoCD's repo-server refuses to generate manifests for any source in a repo that contains a symlink resolving above the repo root. Self-heal can't fire because comparison itself fails, so the cluster silently runs on the last-known-good cache indefinitely."
    - "Manually-triggered syncs do NOT inherit spec.syncPolicy.syncOptions ... any chart-bundled CM larger than ~250KB ... fails with metadata.annotations: Too long: may not be more than 262144 bytes."
    - "Root App-of-Apps re-templates leaf Application specs on every sync. Any live mutation to a leaf is reverted within the root's sync window."
  relevance: "Frank's running postmortem registry for ArgoCD — concrete operational scars accumulated while running the App-of-Apps pattern in production for this learning platform. Provides the source-of-truth dates and recovery commands for the §5 scar callouts and underwrites the §6 decision-tree branches with real failure modes."

- title: "ArgoCD vs FluxCD — r/kubernetes practitioner thread"
  type: benchmark
  url: "https://www.reddit.com/r/kubernetes/comments/16dj9lr/argocd_vs_fluxcd_which_one_did_you_choose_and_why/"
  quoted_passages:
    - "ArgoCD has the better UI by far. Flux is more modular and feels more Kubernetes-native, but the UI gap is real."
    - "We picked Flux because we wanted everything to be a CR and we didn't want a separate UI service running. We picked ArgoCD because we wanted the UI and the App-of-Apps pattern."
  relevance: "Practitioner-level head-to-head capturing the community consensus on the trade Frank made. Not a controlled benchmark, but representative of the decision shape for the ≤10-node single-cluster case the paper actually addresses."

## Frank artefacts (≥3, ≥2 distinct kind values)
- kind: yaml
  path_or_url: "apps/root/Chart.yaml"
  date: 2026-02-15
  demonstrates: "The App-of-Apps entrypoint. A single Helm chart (apps/root) templates every leaf Application CR from apps/root/templates/<app>.yaml. Adding a new app to Frank is one file plus one values entry — the reconciler does the rest."

- kind: incident
  path_or_url: "docs/runbooks/frank-gotchas/argocd.md"
  date: 2026-05-13
  demonstrates: "The out-of-bounds symlink that locked the entire GitOps loop. Commit 024ab58 created .claude/skills pointing two levels up which escapes the repo root. ArgoCD's repo-server refused to generate manifests for ANY source in the repo for ~14 hours; every Application went Unknown. Self-heal could not fire because comparison itself was failing. The fix was a single dot-dot but the blast radius was repo-wide."

- kind: incident
  path_or_url: "docs/runbooks/frank-gotchas/argocd.md"
  date: 2026-04-22
  demonstrates: "The manual-syncOptions-inheritance gotcha. kubectl patch application with --type=merge runs the sync client-side with kubectl apply, which injects last-applied-configuration into every resource. A chart-bundled Grafana dashboard CM at 241KB blew the 262144-byte annotation ceiling. The controller's polling-loop sync honors spec syncOptions; only manual kubectl patch operations don't. ServerSideApply must be passed explicitly in the operation payload."

- kind: incident
  path_or_url: "docs/runbooks/frank-gotchas/argocd.md"
  date: 2026-03-30
  demonstrates: "The root App-of-Apps re-templating leaf specs within the sync window. We tried to suspend selfHeal on a leaf via kubectl patch application for a multi-step manual flow; the root re-rendered the leaf Application CR and SSA-reverted the patch within minutes. Live spec mutations against ArgoCD-managed Applications are not durable unless you also pause the parent — or commit to git."

- kind: commit
  path_or_url: "https://github.com/derio-net/frank/commit/024ab58"
  date: 2026-05-13
  demonstrates: "The actual commit that introduced the symlink-causing-ComparisonError incident. Move-skills-and-symlink commit that pointed .claude/skills two levels up instead of one. The post-commit sanity command find-l-name pattern is now muscle memory after every symlink change."

- kind: grafana-screenshot
  path_or_url: "blog/content/docs/papers/06-gitops-at-small-scale/argocd-app-of-apps-tree-healthy.png"
  date: 2026-05-19
  demonstrates: "ArgoCD UI snapshot showing the root App-of-Apps tree healthy — every leaf Application Synced and Healthy. The visible evidence that 30+ workloads reconcile cleanly from a single root Application, and that the App-of-Apps pattern is what's actually running on Frank."

## Diagrams planned
- landscape:
    x_axis: "OSS to Commercial"
    y_axis: "Unbundled to Opinionated"
    vendors_plotted: ["ArgoCD", "Flux v2", "Jenkins X", "Cloud-managed GitOps", "Spinnaker", "Just bash + kubectl"]
- architecture_comparison:
    vendors: ["ArgoCD", "Flux v2", "Jenkins X", "Cloud-managed GitOps", "Spinnaker"]
- decision_tree:
    leaves: 4
    description: "Question: who watches Git and reconciles your cluster? Branches on cluster count and team familiarity, terminating in: ArgoCD App-of-Apps, Flux v2, cloud-managed GitOps, just-bash-in-CI."

## Named gaps (≥1)
- "No published end-to-end TCO comparison of ArgoCD App-of-Apps vs Flux v2 vs cloud-managed GitOps at ≤10-node single-cluster scale that accounts for the operator's time. Every available comparison either benchmarks reconciliation latency without cost, or compares licensing without measuring the gotcha tax. The single most useful number for a decision-maker — how many hours per month does each option cost you when something goes wrong — does not exist as published work."

## Counter-arguments considered (≥1)
- "GitOps is overengineering for small clusters — just have CI run kubectl apply on push to main and skip the reconciler entirely. Why does not that win for Frank? Answer: same as Paper 00. Frank is a learning platform. The reconciler exists to catch drift, and drift only happens when somebody edits the cluster outside Git — which is exactly the discipline a learning platform needs to develop. Without the reconciler reverting your ad-hoc kubectl edit patches, you never learn to commit them. The counter-argument wins for a one-app team with strong CI discipline and zero out-of-band cluster surgery; for Frank, it would have erased every scar that actually taught the lesson, including the three in §5."
