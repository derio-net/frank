# The Frank Papers — Paper 09: Secrets Management Without the Bootstrap Chicken-and-Egg

**Spec:** `docs/superpowers/specs/2026-04-15--repo--frank-papers-series-design.md`
**Status:** Complete (2026-05-20) — Paper 09 draft published on branch `paper-09`; PR open for human review.

**Prerequisite:** `2026-05-16--repo--frank-papers-phase-0` complete (scripts,
shortcodes, dossier gate, `agents/skills/papers/SKILL.md`). Papers 00, 02, 04,
06, 07, 10, 11, 14 published.

Paper 09 is the secrets-management Paper in the series: 2400–4200 words, the
standard skeleton (§1 capability → §2 landscape → §3 architecture per vendor
→ §4 scale → §5 Frank's choice → §6 generalization → §7 roadmap), and the
first Paper to confront the *secret-store chicken-and-egg* — the capability
that is "obvious" until you try to deploy it on a fresh cluster, at which
point you discover that the secret store itself needs secrets to exist.

The capability question is: *how do you store and serve secrets to a
Kubernetes cluster without trusting any one machine, any one engineer, or
any one Git history line — AND how do you bootstrap that system when the
secret store itself needs an admin password before it can run?* The vendor
space splits along two axes: where the source of truth lives (Git
encrypted, external server, cloud-managed) and whether the system can
bootstrap itself or needs an out-of-band first step. Six candidates make
the landscape, with **Infisical + External Secrets Operator + SOPS-for-
bootstrap** as Frank's case study — a three-layer stack where SOPS-encrypted
secrets are applied out-of-band to seed the Infisical admin and database
credentials, after which Infisical becomes the source of truth and ESO
syncs everything else as native Kubernetes Secrets.

The scars are the point. The `data: []` admission rejection when the last
key was removed from an ExternalSecret. The `envFrom.secretRef` without
`optional: true` that wedged every rolling update on `CreateContainerConfigError`
until the Secret materialized. The Infisical chart that ships
`postgresql.enabled: true` AND `useExistingPostgresSecret` injecting
`DB_CONNECTION_URI` from both code paths with no else branch, forcing the
single app to split into three (`infisical`, `infisical-postgresql`,
`infisical-redis`). The SOPS-bootstrap circularity itself — Infisical
needs an admin password, the admin password needs Infisical — solved by
the only documented exception to the declarative-everything principle:
SOPS-encrypted secrets applied via `sops --decrypt … | kubectl apply -f -`
BEFORE the secret store exists.

## Phase 1: Dossier construction

Six vendors, ≥5 primary sources across ≥3 type values, ≥3 Frank artefacts
across ≥2 kinds, the named gap on the absence of a credible "bootstrap-
cost" benchmark (operator overhead, key-rotation friction, first-day
setup time, ops time per secret rotation), and the counter-argument that
for solo developers running one cluster on one laptop, SOPS+age in Git
with decrypt-on-deploy is the rational choice and a self-hosted secret
store is overkill. Parallel subagents per vendor are appropriate — one
each for Infisical, ESO+SOPS, HashiCorp Vault, Sealed Secrets, AWS
Secrets Manager+CSI, and "plaintext in Git" (the anti-pattern this Paper
exists to argue against) — with a merger pass.

## Phase 2: Gate validation

Run `validate-dossier.py`. Human gate: author reviews the named gap and
the counter-argument. The counter to nail: *"for a solo developer on
one laptop with one cluster, just SOPS in Git is correct — why doesn't
that win for Frank?"* Same shape as Paper 04's framing applied to the
secrets capability.

## Phase 3: Scaffold + draft

Standard capability-paper skeleton. Section order is fixed:

- TL;DR (≤150 words) — write last
- §1 The capability (200–350 words) + `flowchart LR` stack-position diagram
- §2 The landscape (400–600 words) + `{{< papers/landscape >}}` + `{{< papers/capability-matrix >}}` reading from `data/vendors.yaml`
- §3 How each option handles the hard part (800–1400 words) + one `flowchart TD` per vendor with shared visual language
- §4 What scale changes (300–600 words) + benchmark callouts (rotation cost per N secrets, audit-log retention, key-server availability impact)
- §5 Frank's choice, and what happened (300–600 words) + 1–3 `{{< papers/scar >}}` callouts (data:[] rejection, envFrom.secretRef without optional, the SOPS-bootstrap circularity)
- §6 When Frank's answer doesn't generalize (200–400 words) + decision flowchart, ≤4 leaves
- §7 Roadmap & where this space is going (200–400 words)
- §8 References — auto-rendered from frontmatter

## Phase 4: Media fill

Per-paper cover: Frank examining a chained-key handoff with a satisfied
expression — the kind of person who finally has a clean key-rotation
story. Thin black tie, round reading glasses. The visual metaphor is
*chained custody*. Mermaid diagrams: §1 stack position, §2 landscape
(quadrantChart) + capability matrix, §3 four-to-six architecture
flowcharts, §6 decision tree. At least one Infisical / ExternalSecret
screenshot (the Infisical UI at `192.168.55.204` or a `kubectl describe
externalsecret`) captured live from the cluster. Cluster-side captures
may be deferred with `-TODO.png` placeholders if access is unavailable.

## Phase 5: Review + publish

Voice pass (Frank speaks as the cluster — first-person plural or third-
person cluster, not academic). TL;DR ≤150 words written last. Dossier-link
rendering check (use either inline shortcode OR rely on automatic injection
— not both). Set `draft: false`, `status: published`. CI deploys via the
existing blog pipeline.

## Phase 6: Post-deploy checklist

Standard checklist for a published Paper: update `_index.md`, verify the
auto-rendered cross-link chips appear on Building 09-secrets and Operating
06-secrets, update README if relevant, set plan status to Complete.

## Phase summary

| # | Phase | Depends on |
|---|-------|-----------|
| 1 | Dossier construction | — |
| 2 | Gate validation | 1 |
| 3 | Scaffold + draft | 2 |
| 4 | Media fill | 3 |
| 5 | Review + publish | 4 |
| 6 | Post-deploy checklist | 5 |
