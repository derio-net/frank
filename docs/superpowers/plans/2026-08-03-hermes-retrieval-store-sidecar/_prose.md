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
(`--user 1000:1000`, `--cap-drop ALL`, volume root `root:1000 0775`,
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

1. **`PGDATA` must be a subdirectory of the mount.** The entrypoint
   creating that directory is what makes it uid-1000-owned and `0700`.
   The mount root has already been widened to `0775` by `fsGroup`, and
   Postgres refuses a data directory wider than `0750`. Phase 2 guards the
   relationship, not the literal path.
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
  The image does not exist while this plan is written, so the pin cannot be
  written either — deployment.yaml pins hermes-agent-shell-ssh by SHA. This is
  ordering, not risk: if frank merges first the sidecar and PVC land correctly
  and the ONLY consequence is that `bun --version` does not answer yet.
  hermes-agent-shell-ssh is already in the AGENT_IMAGES allowlist, so the
  scheduled agent-images bump workflow re-pins it eventually if nobody does so
  sooner — this op just makes it happen on purpose rather than by calendar.
commands:
  - "Find the tag the agent-images `main` build published: gh api repos/derio-net/agent-images/commits/main --jq .sha (the image tag is the commit SHA)."
  - "Edit apps/hermes-agent-shell/manifests/deployment.yaml, the `ssh` container's image: ghcr.io/derio-net/hermes-agent-shell-ssh:<sha> — currently pinned at 42ecbdd908a5bf6b712532028b880262559ad8f9."
  - "Push to the open PR (or a follow-up PR if this one already merged). ArgoCD recreates the pod on merge — strategy: Recreate, so Hindsight bounces and live tmux/SSH sessions drop."
verify:
  - "kubectl -n hermes-agent-shell get pod -l app=hermes-agent-shell -o jsonpath='{.items[0].spec.containers[?(@.name==\"ssh\")].image}' → the new SHA"
  - "ssh agent@192.168.55.226 'bash -lc \"bun --version\"' → prints a version. It MUST be a LOGIN shell: sshd scrubs the container env and `ssh host -- cmd` skips /etc/profile.d entirely, so the PATH shim is not exercised and the check proves nothing."
status: pending
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
  the home PVC is ever rebuilt, repeat this op.
commands:
  - "ssh agent@192.168.55.226 (login shell — the Bun PATH shim is /etc/profile.d/36-hermes-bun-path.sh and only login shells read it)."
  - "bun install -g <client CLI package>  # the package is named in the requesting repo's private issue, deliberately not written down in this public repo"
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
