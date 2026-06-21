# Staging-vCluster e2e release gate — frank plan

Implements the frank half of the staging-vCluster release gate (spec:
`docs/superpowers/specs/2026-06-15--cicd--staging-vcluster-gate-design.md`). The runs-fr half
(per-commit GHA image build + the in-cluster smoke-test image) is a **separate plan + PR** in
`derio-net/runs-fr`.

## What lands here

A dedicated `staging` vCluster, Frank's first ArgoCD external-cluster wiring, a `runs-fr-staging`
ArgoCD Application that deploys the gated image into that vCluster, a declarative per-app gate
**contract**, and the Tekton gate **Pipeline** (bump-staging → await-sync → run-smoke → promote
→ reset) triggered from GHA via the existing `github-listener`.

## TDD with a fetched toolchain (important)

The `dev` devcontainer has python3/uv/curl/node but **no helm/kubeconform/tkn/yamllint/kubectl**.
Phase 1 Task 1 provisions pinned binaries into a gitignored `.bin/`; every later validation step
runs `PATH=$PWD/.bin:$PATH …` through `fr isolation exec`. The "tests" for declarative manifests
are: `helm template apps/root` renders the expected Applications, `kubeconform -ignore-missing-schemas`
passes (CRDs tolerated), `yamllint` is clean, and python assertions over the rendered output check
the specific fields (destinations, multi-source shape, `when`/`finally` wiring, contract schema).
(Durably adding manifest-validation tooling to the `dev` profile is a sensible follow-up.)

## Agentic vs runtime split (and the manual phase)

Phases 1–6 **author + schema-validate** manifests; they do NOT touch the live cluster. The gate's
**runtime** correctness — the ArgoCD external-cluster Secret (SOPS, applied out-of-band, the
bootstrap-secret exception), the Tekton Tasks' RBAC/argocd/vCluster access, and the actual
build→stage→smoke→promote flow — is proven in the **back-loaded manual Phase 7**. Per the repo's
"a layer isn't Deployed until its workflow ran end-to-end" principle, Phase 7 requires BOTH a
real green run (a promote commit appears) AND the red path (a broken image fails smoke and leaves
prod untouched). Nothing agentic depends on Phase 7.

The `runs-fr-staging` app's `destination.server` is real only once the Phase-7 cluster Secret
exists — so the manifests render + validate now, but live sync waits on Phase 7a. This is called
out so a reviewer doesn't expect a live staging deploy from the agentic phases alone.

## Dependencies

1 (toolchain + staging vCluster) and 4 (contract) are roots. 2 → [1]; 3 → [1,2]; 5 → [4];
6 → [1,3,4,5]; 7 (manual) → [6]. The promote target (`prodApp`/`prodValuesPath` in the contract)
is the **paired runs-fr prod-wiring follow-up** — out of scope here; the contract records it and
the promote Task bumps it.

## Cross-repo note

The `runs-fr-staging` Application sources the runs-fr **chart** from the runs-fr repo
(`charts/runs-fr`) with frank-side staging values — so this plan references runs-fr read-only;
it creates nothing there. The runs-fr per-commit image build + smoke image are the sibling
runs-fr plan/PR.
