# Hermes Agent Shell — retrieval-store sidecar (frank half)

**Spec:** `docs/superpowers/specs/2026-08-03--orch--hermes-retrieval-store-sidecar-design.md`
**Issue:** derio-net/frank#759
**Layer:** `orch` (15)

Adds a fourth container to the `hermes-agent-shell` pod: a stock
PostgreSQL 18 + pgvector store on loopback, with its own Longhorn volume.
Hindsight's container, image, env and 5 Gi PVC are untouched.

The sibling half — Bun in the `hermes-agent-shell-ssh` image — lives in
`derio-net/agent-images` under its own plan. See the spec's Sequencing
section: the two are independent to write and to merge, and meet only at
the image pin, which is back-loaded here into phase 4.

## What is already proven, and what is not

The design was gated locally before this plan was written: stock
`pgvector/pgvector:0.8.6-pg18` was run under this pod's exact posture
(`--user 1000:1000`, `--cap-drop ALL`, volume root `root:1000 2775`,
`PGDATA` a subdirectory, `trust`, `-c listen_addresses=127.0.0.1 -c
port=5434`, an initdb.d script). It initialised, created the extension,
built an `hnsw` index, honoured both `-c` overrides, and survived a
restart on a populated volume.

That is evidence for the **design**, not for the **deployment**. It ran on
a laptop with a Docker volume, not on Longhorn under a kubelet that
re-walks `fsGroup`. Every acceptance row therefore stays
`not-implemented` until phase 4 produces live output. Do not let the gate
tempt you into closing them early.

Two findings from the gate are load-bearing in the phases below:

1. **`PGDATA` must be a subdirectory of the mount.** The entrypoint runs
   `chmod 00700 "$PGDATA" || :` on every start; because the container
   creates and owns the subdirectory, that chmod succeeds. At the mount
   root — which `fsGroup` leaves at `root:1000 2775` — the same chmod
   `EPERM`s, is swallowed by the `|| :`, and initdb then dies on its own
   chmod. Phase 2 guards the relationship, not the literal path.
   (An earlier draft explained this as "the root is `0775` and Postgres
   refuses wider than `0750`" — that is not the mechanism; corrected
   2026-08-03 and again in the test file 2026-08-15.)
2. **The `-k /tmp` socket flag the Hindsight image carries is not needed.**
   The official image ships `/var/run/postgresql` at mode `3777` for
   exactly this arbitrary-uid case.

## Why phase 2 exists at all

Phase 1 alone would pass review and pass CI. Every one of the four failures
phase 2 guards is invisible in a diff and green in a suite:

- a `PGDATA` at the mount root fails only against a real `fsGroup` re-walk;
- an `httpGet` probe against a loopback-only server is refused forever —
  the `hindsight` container above cost 37 restarts learning this;
- a future edit reviving the withdrawn 5 Gi → 10 Gi Hindsight expansion
  would contradict the entire premise of the revised issue while touching
  one number;
- and an exemption whose recorded reason no longer describes what it
  exempts is how a guard quietly stops guarding.

Each guard in phase 2 is **mutation-checked**: doctor the manifest, confirm
the test fails, restore, and journal the result. This repo has already been
bitten by guards that passed against their own doctored input — a
seed-source check that matched its explanatory comment, a "must not push"
check that passed for `!=`, `==` and `true`, and a capacity tripwire that
walked only dict keys. An unmutated guard is a claim, not a check.

## Manual operations

Two operator steps cannot be declarative, and both are back-loaded into
phase 4 because neither can exist while this plan is being written.

```yaml
# manual-operation
id: orch-hermes-ssh-bun-repin
layer: orch
app: hermes-agent-shell
plan: docs/superpowers/plans/2026-08-03-hermes-retrieval-store-sidecar
when: "Phase 4 — after the sibling agent-images plan merges and its `main` build publishes a `hermes-agent-shell-ssh` tag carrying Bun"
why_manual: >
  The image did not exist while this plan was written, so the pin could not be
  written either — deployment.yaml pins hermes-agent-shell-ssh by SHA. This was
  ordering, not risk: if frank merged first the sidecar and PVC would land
  correctly and the ONLY consequence was that `bun --version` did not answer yet.
  OVERTAKEN BY EVENTS, 2026-08-15: agent-images#158 (the Bun runtime + PATH shim)
  merged 2026-08-13 as c04eaab, and because hermes-agent-shell-ssh is in the
  AGENT_IMAGES allowlist the scheduled bump workflow already re-pinned it on
  frank main (#766). Rebasing this branch inherited that pin, so the EDIT half of
  this op is done and what remains is the VERIFY half — which still cannot run
  before merge, because ArgoCD syncs from main. Do not skip the verify on the
  strength of the pin looking right: the image carrying Bun and a LOGIN shell
  resolving it are different claims.
commands:
  - "Confirm the pin rather than assuming it: read the CURRENT value out of apps/hermes-agent-shell/manifests/deployment.yaml (the `ssh` container's image:) — do not trust a SHA written down here, this file goes stale every time the bump workflow runs."
  - "If and only if that pin predates the Bun runtime, find the tag the agent-images `main` build published (gh api repos/derio-net/agent-images/commits/main --jq .sha — the image tag is the commit SHA) and edit the pin to it. As of 2026-08-15 the pin is already at or past c04eaab and no edit is needed."
  - "If an edit WAS needed: push to the open PR (or a follow-up PR if this one already merged). ArgoCD recreates the pod on merge — strategy: Recreate, so Hindsight bounces and live tmux/SSH sessions drop."
verify:
  - "kubectl -n hermes-agent-shell get pod -l app=hermes-agent-shell -o jsonpath='{.items[0].spec.containers[?(@.name==\"ssh\")].image}' → the new SHA"
  - "ssh agent@192.168.55.226 'bash -lc \"bun --version\"' → prints a version. It MUST be a LOGIN shell: sshd scrubs the container env and `ssh host -- cmd` skips /etc/profile.d entirely, so the PATH shim is not exercised and the check proves nothing."
status: done
done_note: "2026-08-15 — no edit was needed: the scheduled agent-images bump had already carried the pin past Bun (live pin 4ed6ec9, /usr/local/bin/bun dated 2026-08-13). Verified both halves post-merge: the live ssh container image matches the manifest, and `ssh hermes 'bash -lc \"bun --version\"'` returns 1.3.14 over a LOGIN shell. Note the raw-IP form in the command above needs an IdentityFile; the `hermes` alias from apps/hermes-agent-shell/client-setup/laptop/ssh-config.snippet is what actually authenticates."
```

```yaml
# manual-operation
id: orch-hermes-gbrain-cli-install
layer: orch
app: hermes-agent-shell
plan: docs/superpowers/plans/2026-08-03-hermes-retrieval-store-sidecar
when: "Phase 4 — after orch-hermes-ssh-bun-repin, once `bun --version` answers over SSH. AND AGAIN every time the hermes-agent-shell-home PVC is rebuilt."
why_manual: >
  Decision 2 of the spec: the ssh image ships a generic Bun runtime and names
  nothing, and the client CLI is installed by hand, globally, onto the home PVC
  ($HOME=/opt/data/home) — the same persistent-agent pattern this pod already
  uses for `claude` and `gh` auth. That keeps a private tool's name out of two
  public repos. The accepted cost is that the install is NOT reproducible from
  git: nothing reconciles it, nothing alerts when it is missing, and the
  symptom is `command not found` in a shell that otherwise looks healthy. If
  the home PVC is ever rebuilt, repeat this op. INSTALL FROM A PINNED GIT REF,
  NEVER FROM THE NPM REGISTRY — #759 is explicit that an unrelated package
  squats the name there, and this shell holds `gh` and `claude` credentials
  with cluster access, so a mistaken `bun install -g <name>` puts a stranger's
  postinstall script on that PVC.
commands:
  - "ssh agent@192.168.55.226 (login shell — the Bun PATH shim is /etc/profile.d/36-hermes-bun-path.sh and only login shells read it)."
  - "bun install -g 'git+<client CLI repo URL>#<pinned ref>'  # NOT from npm — the name is SQUATTED there by an unrelated package. Install from a PINNED git ref (tag or commit SHA), never a bare package name and never a moving branch. The repo URL and the ref are named in the requesting repo's private issue, deliberately not written down in this public repo."
  - "The global install lands under $HOME/.bun/bin on the hermes-agent-shell-home PVC, which is what makes it survive a pod recreate."
verify:
  - "ssh agent@192.168.55.226 'bash -lc \"<cli> --version\"' → prints a version. Use `bash -lc`; `ssh host -- cmd` skips /etc/profile.d and would fail even on a correct install."
  - "Connectivity from the same shell: psql 'postgres://gbrain@127.0.0.1:5434/gbrain' -c 'select extversion from pg_extension where extname = $$vector$$' → 0.8.6 (or run it in the gbrain container if psql is not on the ssh sidecar)."
  - "Then delete the pod and re-run the --version check. That is Test Plan row 8, and it is the row that decides whether decision 2 was right — if the CLI does not survive the restart, it belongs in the image and this is a rework, not a patch."
status: pending
```

## Rollout honesty

Merging this recreates the pod. `strategy: Recreate` is not a choice here —
every volume is RWO and cannot double-mount — so Hindsight bounces and live
tmux/SSH/mosh sessions drop when ArgoCD syncs. The issue's "no restart
required by this work" means no volume *detach*, which is the risky,
schedulable operation the revision avoids. It does not mean no restart, and
the documentation added in phase 3 says so plainly.

## Close-out status (2026-08-15, post-merge)

PR #763 merged as `0fbbe549`. ArgoCD reconciled to it and recreated the pod
`4/4 Running`. **Test Plan rows 1-6 pass; rows 7-9 remain owed**, which is why
this plan is still `in progress` and NOT archived.

| Row | Result |
|---|---|
| 1 | Pod `4/4`, all containers ready, 0 restarts. Hindsight PVC still `5Gi`, container healthy |
| 2 | `vector 0.8.6` |
| 3 | Own Longhorn volume (`pvc-a10dd99b`, 9.8G) vs Hindsight's (`pvc-cf287075`, 4.9G) |
| 4 | `/opt/gbrain` = `drwxrwsr-x root:1000` (**2775 — observed, not derived**); `pgdata` = `drwx------ 1000:1000` |
| 5 | Row + hnsw index survived a real pod delete; PGDATA still `0700` after the kubelet fsGroup re-walk |
| 6 | `bun --version` -> `1.3.14` over a **login** shell |
| 7-8 | **OWED** — need the CLI's private git ref, which is not in this repo |
| 9 | **OWED** — the requesting repo's own benchmark |

Two extra observations worth keeping. The 2026-08-15 review's collation fix was
confirmed live (`datlocprovider` `b`, `datlocale` `C.UTF-8`) — it had exactly one
window, the first initdb on a fresh volume, and it landed. And **ArgoCD reported
`Synced/Healthy` at the PRE-merge revision for about two minutes after the merge,
with a `3/3` pod** — the textbook version of this repo's "Synced can mean synced to
a stale revision" gotcha. Every row above is asserted on an artifact, never on
sync status.

## Why there is no Post-Deploy Checklist phase

A repo hook flags any plan without one. That checklist
(`agents/rules/plan-post-deploy-checklist.md`) is written for a **standard
layer** — a new deployment getting its first building and operating posts.
This is an **extension** to a layer that is already deployed
(`hermes-agent-shell`), and the same rule says extensions skip the blog
posts and update the existing layer's material instead. That is what phases
1-3 did, deliberately and in full:

- **Blog posts** — skipped by rule. No new layer, no new narrative.
- **Gotchas** — done in the extension shape the rule prescribes: a one-line
  summary in `agents/rules/frank-gotchas.md`, the full prose and recovery
  detail in `docs/runbooks/frank-gotchas/agent-shells.md`.
- **README** — done: `apps/hermes-agent-shell/README.md` carries the DSN,
  the manual install and the restart consequence.
- **Runbook sync** — done: both manual-operation blocks are registered in
  `docs/runbooks/manual-operations.yaml` and verified byte-identical to the
  blocks above.
- **Exposure (step 1)** — not applicable. The store binds `127.0.0.1` inside
  the pod on purpose; there is no IngressRoute and no homepage tile to add,
  and adding either would defeat the security posture the design rests on.
- **Plan status** — the operator sets it after the phase-4 Test Plan runs,
  which is the only step that can produce the evidence.
