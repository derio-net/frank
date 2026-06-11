# Frank — Repository Audit, Improvement Plan & Public-Exposure Assessment

*Date: 2026-06-11 · Auditor: igor (infrastructure) · Scope: `derio-net/frank` @ `origin/main` + public satellite repos*

> **Read priority.** The operator's explicit question is the public-exposure assessment.
> It is a first-class section ([§Public-Exposure Assessment](#public-exposure-assessment-operators-question)),
> not an appendix. The general repo audit precedes it.

---

## Executive Summary

**Health grade: B+.** Frank is a mature, unusually disciplined GitOps homelab. The
declarative-only principle is real and enforced (App-of-Apps, Talos patches, SOPS at rest),
secret hygiene is excellent (no plaintext secret ever committed across full history,
`encrypted_regex` correct, age private key gitignored and absent), and the agent-contract /
validator tooling is better than most production shops. It is not an A only because of three
self-inflicted blast-radius choices and a documentation surface that is *too* good — the
README is a complete intel pack for an attacker.

**Top 3 risks.**
1. **`secure-agent-pod` ServiceAccount is `cluster-admin` while its egress NetworkPolicy is
   disabled** (`apps/secure-agent-pod/manifests/serviceaccount.yaml:1`,
   `apps/secure-agent-pod/cilium-egress.yaml.disabled`). A compromised agent process = full
   cluster control + unrestricted outbound. The pod is hardened against *breakout*, not
   against *misuse of its own token*.
2. **Public documentation completeness is itself an attack accelerator.** The README plus the
   `agent-images` README plus the operating posts compose into a turn-key target map (highest-
   value pod, where it runs, what it can do, how auth works). No single file is a leak; the
   *correlation* is.
3. **`root-agents` group → `cluster-admin`** via Authentik OIDC (`apps/authentik-extras/manifests/k8s-rbac.yaml:43`).
   Gated by the IdP, so not directly exploitable from outside, but a broad standing grant on a
   group whose membership is machine identities.

**Top 3 opportunities.**
1. Re-enable + scope the agent-pod egress policy and downgrade its SA from cluster-admin to a
   purpose-scoped ClusterRole — the single highest-leverage hardening on the cluster.
2. Add a CI secret-scanner (gitleaks/trufflehog) gate. History is currently clean; a gate keeps
   it clean as the repo stays public.
3. Introduce a short "Threat model & exposure" doc that consciously records what is public and
   *why* — converts the diffuse leak surface into a deliberate, defensible decision.

**Verdict on the operator's question (one line):** *Public is tenable and worth keeping for its
portfolio value — there is no actual credential compromise — but two cluster-internal grants
must be fixed and the documentation's cross-repo correlation should be reduced consciously.*

**Lighter-reviewed areas (declared):** `blog/` content prose (333 files — skimmed for leaks, not
for editorial quality), `omni/` (5 files, gitignored sensitive bits), `patches/` Talos internals
(reviewed for secrets, not for Talos correctness), and per-app Helm values beyond the high-value
apps. Depth was spent on the core 20%: app-of-apps wiring, secret management, RBAC, the
agent-pod, the Hop edge, CI/validators, and the public surface.

---

## Repo Map

**Purpose.** GitOps source of truth for "Frank," a 7-node Talos Kubernetes homelab (3 control-
plane NUCs, 1 RTX-5070-Ti GPU desktop, 2 RPi4 + 1 legacy worker) plus "Hop," a single-node
Hetzner public-edge cluster. Everything on the cluster is reproducible from this repo. Doubles as
a public engineering portfolio (the blog is built and hosted from here).

**Stack.** Talos Linux + Sidero Omni · Cilium (eBPF, L2 LB) · Longhorn · ArgoCD App-of-Apps ·
SOPS (age) for bootstrap secrets + Infisical/ESO for runtime secrets · Authentik OIDC · Traefik
v3 (in-cluster) + Caddy (edge) · Headscale/Tailscale mesh · VictoriaMetrics/Logs + Grafana ·
Tekton/Gitea/Zot CI · a fleet of agent pods (Kali secure-agent-pod, Paperclip, Ruflo, Hermes).
Tooling: Hugo blog, Python+`uv` validators, bash scripts, a shared agent contract (`AGENTS.md`).

**Architecture sketch.**
- `apps/root/templates/*.yaml` — one ArgoCD `Application` CR per component (~75 apps + namespaces).
  `apps/<app>/values.yaml` + `apps/<app>/manifests/` carry the per-app config.
- `clusters/hop/` — parallel App-of-Apps for the public edge (Caddy, Headscale, blog, CrowdSec, Falco).
- `patches/phaseNN-*` — Talos machine config (legacy phase naming).
- `secrets/` — SOPS-encrypted bootstrap secrets only (the documented exception to declarative-only).
- `agents/` — the agent contract: rules, skills, reviewers, commands (load-order in `AGENTS.md`).
- `docs/` — plans/specs (superpowers), runbooks, investigations, papers dossiers.
- `blog/` — Hugo PaperMod site, three series (building / operating / papers).
- `scripts/` — validators (plans, agent-config, papers, mermaid) wired into `.githooks/pre-commit` + CI.

**Key directories (one-liners).**
| Dir | What |
|-----|------|
| `apps/` | Frank App-of-Apps; the cluster's declarative inventory |
| `clusters/hop/` | Public-edge cluster (the only internet-facing surface) |
| `secrets/` | SOPS-encrypted bootstrap secrets, per-namespace |
| `agents/` | Canonical AI-agent contract + repo-local skills |
| `docs/` | Plans, specs, runbooks, investigations, papers |
| `blog/` | Public Hugo site (also the portfolio) |
| `patches/` | Talos node config |
| `scripts/` | Validators + ops utilities |

**Surprises (facts).**
- `apps/secure-agent-pod/cilium-egress.yaml.disabled` — a *written, then deliberately disabled*
  egress policy sitting next to a cluster-admin SA. The intent existed; the enforcement was switched off.
- Secret hygiene is genuinely clean across **full** history (1657 tracked files, 39 secret-touching
  commits) — rare for a repo this age that went public.
- The README (28.5 KB) is effectively a runbook + network diagram + service inventory in one.

---

## Audit Report

Findings grouped by dimension, sorted by severity. **Fact** vs **Judgment** labelled per item.

### Security

- **[High · Fact] Agent-pod SA is `cluster-admin` and egress policy is disabled.**
  `apps/secure-agent-pod/manifests/serviceaccount.yaml:1-19` binds `agent-sa` to `cluster-admin`;
  `apps/secure-agent-pod/cilium-egress.yaml.disabled` is the (inert) egress restriction.
  *Why it matters:* the pod runs an autonomous coding agent (a class of workload designed to
  fetch and run arbitrary code). Container hardening is good — `runAsNonRoot`, `allowPrivilege‑
  Escalation: false`, `capabilities.drop:[ALL]` (`apps/secure-agent-pod/manifests/deployment.yaml:111-116,179-184`)
  — but that only stops *breakout*. The agent process legitimately holds a cluster-admin token
  and has unrestricted egress, so a prompt-injection or supply-chain compromise of the agent
  itself = full cluster control + free exfiltration path. This is the single biggest blast radius
  in the repo.

- **[Medium · Judgment] `root-agents` group bound to `cluster-admin`.**
  `apps/authentik-extras/manifests/k8s-rbac.yaml:43-54`. The binding is gated behind Authentik
  OIDC (the public knowledge of the mapping grants nothing without authenticating), so this is
  *defense-in-depth*, not an open door. But a standing cluster-admin grant to a *group of machine
  identities* is broader than the principle of least privilege wants. `root-developers → view`
  and `root-devops → admin` (same file) are well-scoped; `root-admins` + `root-agents` →
  cluster-admin are the two broad ones.

- **[Low · Fact] Documentation doubles as an attack guide.** `agents/rules/frank-infrastructure.md`,
  `README.md:186-303`, and `docs/runbooks/manual-operations.yaml` enumerate every service, IP,
  port, and access method. *Why it matters:* covered in full in the [Public-Exposure section](#public-exposure-assessment-operators-question);
  noted here for completeness. Severity is Low *for the repo* because the IPs are non-routable;
  the risk is acceleration, not access.

- **[Strength · Fact] Secret management is correct.** `.sops.yaml` encrypts only `data|stringData`
  with age; spot-check confirms ciphertext at rest (`secrets/authentik/authentik-secrets.yaml`
  — all values `ENC[AES256_GCM,...]`); no `data`/`stringData` block anywhere under `secrets/`
  lacks a `sops:` envelope; age **private** key is gitignored (`.gitignore`) and absent from the
  tree and from full history; runtime secrets flow through Infisical + ESO, not the repo.

- **[Strength · Fact] Git history is clean.** Full-history patch scan for private keys, PATs
  (`ghp_`, `github_pat_`), `sk-`, `xoxb-`, AWS keys, and `password=`/`api_key=` literals returned
  nothing outside SOPS envelopes; no `.key`/`.pem`/`.env`/`kubeconfig`/`talosconfig` file was ever
  added; secrets were SOPS-encrypted from first commit (no plaintext-then-encrypt window).

- **[Strength · Fact] Edge is defended in depth.** Hop's Caddy
  (`clusters/hop/apps/caddy/manifests/configmap.yaml`) runs a CrowdSec bouncer (403 at edge),
  mesh-gates private routes by Tailscale CGNAT range (`not remote_ip 100.64.0.0/10 → 403`),
  passes GitHub webhooks through to an HMAC-validating Tekton interceptor, and Falco (modern_ebpf)
  watches the edge node. The public route set is deliberately tiny (blog, headscale, webhooks,
  counter, a "Coming soon" www).

### Architecture & Design

- **[Strength] Clean App-of-Apps boundaries.** One `Application` CR per component, values/manifests
  split, namespaces as explicit `ns-*.yaml` templates. Manual-prune convention is documented and
  the reasoning (ArgoCD normalizing `prune:false`) is captured inline (`apps/root/values.yaml`).
- **[Low · Judgment] `patches/` uses legacy `phaseNN-` naming** while the rest of the repo moved to
  layer codes (`repo-architecture.md:30-36` documents the divergence). Cosmetic; renaming risks
  Talos config churn for no functional gain — recommend leaving it (see Strategy trade-offs).
- **[Low · Judgment] README is a god-document.** `README.md` (28.5 KB) carries architecture,
  full service inventory, access matrix, and per-app status. It's excellent and current, but it's
  a single file doing five jobs; the `update-readme` skill keeps it in sync, so churn is managed.

### Code Quality / DevEx & Operations

- **[Strength] Validators are real and enforced.** `.githooks/pre-commit` + `.github/workflows/`
  gate plan headers, agent config, paper frontmatter, and dossiers. Portable checks live in
  `scripts/` (not just Claude hooks), per the AGENTS.md contract — so non-Claude agents are covered too.
- **[Medium · Fact] No secret-scanning gate in CI.** `.github/workflows/` has build + agent-config
  workflows but no gitleaks/trufflehog. *Why it matters:* the repo is public; history is clean
  today, but nothing *prevents* a future accidental commit (e.g. a misplaced `.env`, a token in a
  runbook example). A scanner is the cheapest insurance for a public repo.
- **[Low · Fact] Thin test surface.** `tests/` holds only `image-pipeline/test_pipeline.py` (350
  lines) + agent-config fixtures. *Judgment:* appropriate for a declarative GitOps repo — the
  "tests" here are the validators + ArgoCD sync health, not unit tests. Not a gap worth closing.

### Dependencies

- **[Strength · Fact] Helm charts pinned to current-ish versions.** Authentik chart `2026.2.1`,
  Traefik `39.0.7`, Gitea `12.5.0`, ArgoCD `9.4.6`, Infisical `1.7.2` (`apps/root/templates/*.yaml`).
  No wildcard/`latest` chart revisions spotted in the high-value apps. *Note:* a few workload
  images use `:latest` (e.g. `frank-blog:latest` per README:313) — acceptable for the blog,
  worth pinning for anything in the request path.

### Documentation

- **[Strength] Onboarding path is excellent.** `AGENTS.md` load-order, per-rule files, README
  structure, and runbooks make this navigable. Docs match code (spot-checks agreed).
- See [Public-Exposure section](#public-exposure-assessment-operators-question) for the flip side:
  the docs are *so* complete they leak operational structure.

### Performance / Testing

Healthy for the project type. No N+1 / blocking-async / unbounded-growth concerns apply to a
declarative manifest repo. One sentence each — moving on.

### Strengths (preserve these)

1. Disciplined declarative-only GitOps with a documented, narrow exception.
2. Correct SOPS-at-rest + Infisical/ESO-at-runtime split; clean history.
3. Enforced, portable validators (not agent-specific hooks).
4. Defense-in-depth at the public edge (CrowdSec + mesh-gating + HMAC + Falco).
5. Documentation quality and currency (the same property that creates the exposure trade-off).

---

## Public-Exposure Assessment (operator's question)

> *"Am I compromising my security by having frank — and the blog within it, and the satellite
> repos (agent-images etc.) — public?"*

**Direct answer: No, you are not compromising your security in the sense of exposing anything
that grants an attacker access. There are zero live credential leaks. What you *are* doing is
publishing a high-resolution map of the target — which lowers an attacker's reconnaissance cost
to near zero. That is an acceptable trade for the portfolio value, provided you fix two
cluster-internal grants and consciously reduce the cross-repo correlation. Keep it public.**

The findings sort into three buckets, exactly as requested.

### (a) Actual compromise vectors — MUST FIX

These are real and exploitable, though note: **both are cluster-internal, not "because the repo
is public."** Making the repo private would *not* fix them; it would only hide them.

1. **Agent-pod cluster-admin + disabled egress** (detailed above). An attacker who lands code in
   that pod — via the agent fetching a malicious dependency, a poisoned MCP server, or prompt
   injection — has the SA token and a clear outbound path. **This is the one true "fix now."**
2. **Broad standing cluster-admin grants** (`root-agents`, `root-admins`). IdP-gated, so second
   priority, but scope them down.

There is **no leaked secret, key, kubeconfig, talosconfig, or token** — confirmed across full
git history. Nothing in the public surface lets an attacker authenticate.

### (b) Attacker-acceleration info — REDUCE or ACCEPT CONSCIOUSLY

This is the bulk of the exposure. None of it grants access; all of it saves an attacker work.

- **Full internal topology is public.** The entire `192.168.55.0/24` map — every node, role,
  hardware spec, and the complete service→IP→port inventory — is in `README.md:13-303` and
  `agents/rules/frank-infrastructure.md`. **Mitigating fact:** these are RFC1918 addresses,
  reachable only from the LAN or across the authenticated Tailscale/Headscale mesh. The **only**
  routable address in the repo is the Hetzner public IP for `hop-1`, and even that is described,
  not pinned. So this is a *map of a network an attacker can't reach* — until they're already
  inside, at which point it's a fast-forward button.
- **Cross-repo correlation is the sharpest edge.** Compose three public facts:
  `agent-images` documents a Kali pod carrying `kubectl`/`talosctl`/`omnictl` + pentest tooling →
  `frank` documents that pod runs on `gpu-1` as cluster-admin with egress disabled →
  the operating blog post + README narrate the SSH/mesh auth model. Individually each is fine;
  together they hand an attacker "here is the highest-value foothold, here is where it runs, and
  here is exactly what it can do once you're in." This is the item most worth reducing.
- **`runs-fr` publicly documents a no-auth-of-its-own design.** Its README's "Security contract"
  states it trusts a single upstream header and performs no auth itself. That's a *correct and
  honest* design disclosure, but it tells an attacker precisely which assumption to attack (the
  upstream auth proxy). Acceptable if the proxy is sound — flagged so it's a conscious choice.
- **Operating runbooks double as step-by-step ops guides** (`docs/runbooks/manual-operations.yaml`,
  the operating blog series). Great for you; a warm start for an intruder mapping how to move.

**Recommendation for bucket (b):** accept the topology exposure (the mesh is the real boundary;
hiding RFC1918 IPs buys little), but **reduce the cross-repo correlation** — specifically, stop
co-publishing "this pod is cluster-admin with egress off" alongside "this pod carries cluster
admin CLIs." Fixing bucket (a) #1 also neutralizes most of this correlation's value.

### (c) Harmless-but-public — fine as is

- Technology stack, chart versions, GitOps patterns, blog narrative, agent contract — this is the
  portfolio, and it's the *point* of being public. Versions being visible is a minor CVE-targeting
  convenience but they're current; the payoff of hiding them is near zero.
- Hostnames (`*.derio.net`, `*.cluster.derio.net`) — DNS is public anyway; mesh-only names don't
  resolve for outsiders.

### The blog & published docs (`blog.derio.net`, `derio-net.github.io`)

The blog's *operating* series narrates the auth model, the s6/sshd supervision, and the SSH
access pattern for the agent pod (`blog/content/docs/operating/14-secure-agent-pod/index.md`).
This is the same acceleration info as above in prose form — it explains *how the auth works*,
which is exactly what an attacker wants to read first. No credentials, but the most "attack-guide-
shaped" prose in the public surface. Consider trimming the auth-mechanism detail from the public
post (keep the ops commands, drop the "here's why the trust boundary is where it is" exposition).

### Satellite public repos (enumerated)

`gh repo list derio-net --visibility public` → 10 public repos (12 private). Assessed:
- **`agent-images`** — the correlation risk above. No secrets; CI publishes to GHCR by SHA. The
  *capability disclosure* (what each agent image can do) is the concern, not any leak.
- **`frank-ops`** — **private** (confirmed via `gh repo view`). Good: operational Layer-tracker
  state is *not* public. This is the right call and worth keeping.
- **`runs-fr`** — the documented no-auth design (above). Code-clean; the disclosure is the item.
- **`health-bridge`, `super-fr`, `agent-skills`, `blog-craft`, `vscode-launchpad`, `icm-fr`,
  `autoresearch-skill`** — tooling/skills repos; spot-checked, no infrastructure secrets, low
  correlation value. Fine public.

### Bottom line for the operator

Public is **tenable and recommended to keep** — the portfolio value is real and you are not
leaking anything that grants access. Do not make `frank` private. Instead:
1. Fix bucket (a) — those are cluster bugs that exist regardless of repo visibility.
2. Reduce the one sharp correlation (agent-pod capability × privilege × location) — mostly solved
   by fixing (a)#1.
3. Trim the auth-*mechanism* exposition from the public operating post.
4. Write down the threat model so this exposure is a decision, not an accident.

---

## Improvement Strategy

**Themes that explain most findings:**

1. **Agent blast radius is the real risk, and it's internal.** Target state: every agent pod runs
   with a least-privilege SA and an enforced egress allowlist; cluster-admin is reserved for human
   break-glass. Principle: *capability should match need, and the most-likely-compromised workload
   should have the least power.*
2. **Exposure should be a decision, not a side effect.** Target state: a short threat-model doc
   records what's public and why; the cross-repo correlation is consciously minimized. Principle:
   *public-as-portfolio is fine when the boundary (the mesh + IdP) is the thing that protects you,
   not the obscurity of the docs.*
3. **Keep the clean history clean by machine, not by discipline alone.** Target state: a CI
   secret-scanner gate. Principle: *a public repo's history is forever; prevention beats rotation.*
4. **(Preserve) Declarative + validated + documented.** Don't regress these. They're the reason
   the grade is a B+ and not a C.

**Explicitly NOT fixing (trade-offs):**
- **Renaming `patches/phaseNN-`** — cosmetic, risks Talos config churn, no payoff. Leave it.
- **Hiding internal RFC1918 IPs from docs** — the mesh is the boundary; scrubbing IPs is security
  theater that degrades the (valuable, accurate) documentation. Accept the topology exposure.
- **Adding a unit-test suite** — wrong tool for a declarative repo; the validators + ArgoCD health
  are the correct test surface. Don't.
- **Making `frank` private** — destroys portfolio value to "fix" risks that aren't fixed by privacy.

**"Done" looks like:** zero workload with cluster-admin SA except documented break-glass; agent-pod
egress policy enforced (`.yaml`, not `.yaml.disabled`); a CI secret-scan job that fails on a planted
test secret; a `docs/threat-model.md` committed; the public operating post trimmed of auth-mechanism
exposition.

---

## Task Plan

### Quick wins (high impact, S effort — do immediately)

| # | Task | Effort | Why now |
|---|------|--------|---------|
| QW1 | Add gitleaks (or trufflehog) CI gate on PRs + a pre-commit hook | S | Cheapest insurance for a public repo; history is clean *today* |
| QW2 | Write `docs/threat-model.md` recording the public-exposure decision (this report is the seed) | S | Converts diffuse leak into a conscious, defensible choice |
| QW3 | Trim auth-*mechanism* exposition from the public agent-pod operating post (keep ops commands) | S | Removes the most attack-guide-shaped prose |

### Milestone 0 — Safety net

| Task | Files | Acceptance | Effort | Risk | Deps |
|------|-------|------------|--------|------|------|
| M0.1 Add secret-scan CI + hook | `.github/workflows/`, `.githooks/pre-commit` | A planted test secret fails CI; real history passes | S | Low | — |
| M0.2 Snapshot current RBAC for rollback | `docs/` | `kubectl get clusterrolebindings -o yaml` archived before any RBAC change | S | None | — |

### Milestone 1 — Critical fixes (the real risk)

| Task | Files | Acceptance | Effort | Risk | Deps |
|------|-------|------------|--------|------|------|
| **M1.1 Re-enable + scope agent-pod egress** | `apps/secure-agent-pod/cilium-egress.yaml(.disabled)` | Policy is `.yaml`, ArgoCD-synced; pod reaches only its allowlist (LiteLLM, GHCR, Anthropic, GitHub, DNS); a curl to an off-list host fails | M | **Med** — could break the agent's legit egress; needs the allowlist right | M0.2 |
| **M1.2 Downgrade agent-pod SA from cluster-admin** | `apps/secure-agent-pod/manifests/serviceaccount.yaml` | SA bound to a purpose-scoped ClusterRole, not `cluster-admin`; the pod's known workflows still function | L | **Med-High** — agent may rely on broad access today; enumerate real needs first | M0.2, M1.1 |
| M1.3 Scope `root-agents` group binding | `apps/authentik-extras/manifests/k8s-rbac.yaml:43-54` | `root-agents` bound to a scoped role; human break-glass retains cluster-admin via `root-admins` only | M | Med | M0.2 |

### Milestone 2 — High-leverage

| Task | Files | Acceptance | Effort | Risk | Deps |
|------|-------|------------|--------|------|------|
| M2.1 Reduce cross-repo capability correlation | `agent-images` README, `frank` README/status | Capability + privilege + location are no longer co-stated for the agent pod | S | Low | M1.1 |
| M2.2 Pin request-path workload images off `:latest` | per-app values referencing `:latest` | Blog/edge images pinned to a tag/SHA | S | Low | — |

### Milestone 3 — Quality & polish

| Task | Acceptance | Effort | Risk |
|------|------------|--------|------|
| M3.1 Audit remaining agent pods (Paperclip/Ruflo/Hermes) for SA scope | each has least-privilege SA documented | M | Low |
| M3.2 Periodic exposure review cadence in the threat-model doc | review date + owner recorded | S | None |

### Top-3 implementation sketches

**M1.1 — Re-enable agent-pod egress.**
- Approach: read `cilium-egress.yaml.disabled`, confirm the allowlist matches the agent's *real*
  outbound needs (LiteLLM in-cluster, GHCR, GitHub API, Anthropic API, DNS, NTP), rename to `.yaml`,
  let ArgoCD sync, then verify with an in-pod `curl` to both an allowed and a denied host.
- Gotchas: agents pull from many hosts (npm, pypi, crates, model CDNs). Under-scope and you break
  the agent; over-scope and you've re-created the open egress. Start in *audit/log* mode if Cilium
  supports it for this policy, capture real destinations for a day, then enforce. Coordinate with a
  Frank-side agent — this is a live-cluster change, not a repo-only edit.

**M1.2 — Downgrade the SA.**
- Approach: enumerate what `agent-sa` actually calls (it's used for in-cluster kubectl by operators).
  Build a ClusterRole granting only those verbs/resources; if humans need cluster-admin for
  break-glass, give *them* that via `root-admins`, not the *pod's* SA.
- Gotchas: the pod is the operator's daily driver; silently removing access mid-session is painful.
  Stage it, announce it, keep a documented break-glass path. This is the higher-risk change — do it
  after M1.1 proves the egress allowlist is right.

**QW1 — Secret-scan gate.**
- Approach: add a `gitleaks` GitHub Action on `pull_request` + a thin pre-commit invocation; allowlist
  the SOPS `ENC[...]` pattern so encrypted secrets don't trip it. Plant a fake secret in a throwaway
  branch to prove the gate fails, then delete the branch.
- Gotchas: gitleaks will flag SOPS ciphertext and age *public* keys unless allowlisted — tune the
  config against the existing `secrets/` tree first so the baseline is green.

---

## Open Questions (need a human)

1. **Agent-pod egress allowlist contents.** What does the agent legitimately need to reach? (Model
   APIs, package registries, GitHub, anything else?) M1.1 can't be scoped correctly without this.
2. **Is the agent-pod SA's cluster-admin actually used, or incidental?** If operators rely on it for
   day-to-day kubectl, M1.2 needs a break-glass design; if it's just "we never scoped it," M1.2 is
   straightforward.
3. **Portfolio vs. exposure appetite.** How much of the cross-repo capability correlation are you
   willing to trade for portfolio completeness? This report recommends reducing it; the call is yours.
4. **`runs-fr` upstream auth proxy.** Is the trusted-header upstream a hardened component? Its public
   no-auth design is only as safe as that proxy.

---

*Report scope note: this document lives in a public repo. Sensitive findings are described by
`file:line` and generic shape, never by quoting secret-shaped values, and the cross-repo correlation
is summarized rather than spelled out into a usable playbook.*
