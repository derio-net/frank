# Design — hermes-agent-shell: PVC-resident Hermes venv + baked auto-continue patch

**Issue:** [frank#496](https://github.com/derio-net/frank/issues/496)
**Layer:** `orch` (extension of the existing `hermes-agent-shell` layer)
**Status:** ready
**Repos in scope:**
- `derio-net/agent-images` — image build (primary deliverable PR)
- `derio-net/frank` — image SHA pin bump + runbook/blog (back-loaded, post-merge)

---

## Problem

The `agent` user (uid 1000) inside the `hermes-agent-shell` pod cannot modify
the Hermes runtime. The venv at `/opt/hermes-agent` is baked `root:root 0644`
in the image, and the pod's securityContext forbids privilege escalation
(`allowPrivilegeEscalation: false`, `capabilities.drop: ["ALL"]`,
`runAsNonRoot: true`). Only `/home/agent` (the PVC) is writable.

`fsGroup: 1000` does **not** help: it re-groups *mounted volumes* at attach
time, never image-baked files. So the in-pod operator has no path to
hot-patch or maintain Hermes — which was needed to fix a real stall (below).

### Motivating incident — the qwen36-a3b "announce then idle" stall

1. Qwen3-A3B stochastically emits an intent-only message (*"Got it. Let me
   wire everything up:"*) with `finish_reason=stop` and **no tool call**
   (~5–20% of turns at ~16k ctx). Once one announce-only message is in
   history, the model imitates it and the turn dies.
2. Hermes v0.15.2 ships a countermeasure — when the model returns a
   planning/ack message with no tool call, it injects
   `[System: Continue now. Execute the required tool calls…]` and loops
   (`agent/conversation_loop.py`, ~line 4183). **But it is gated on
   `api_mode == "codex_responses"`**, so it never fires on the
   OpenAI-compatible LiteLLM path Frank uses (`api_mode == "chat_completions"`).

The countermeasure's detection heuristic
(`agent.agent_runtime_helpers.looks_like_codex_intermediate_ack`) is fully
provider-agnostic — it inspects only message structure and text. So
widening the gate to also fire on `chat_completions` is safe and is the
exact fix the issue calls for.

---

## Decisions (from the operator Q&A)

| # | Decision | Choice |
|---|----------|--------|
| Q1 | Write-access approach | **Option 1+2: PVC-resident venv.** The live Hermes venv lives on the `/home/agent` PVC (uid-1000 owned, writable). Patches persist across pod restarts. |
| Q2 | Scope | **Also bake the auto-continue patch** into the image so the qwen stall is fixed permanently, not just made patchable. |
| Q3 | Cross-repo delivery | **agent-images PR now** (the fix). **frank pin-bump + runbook + blog back-loaded** as a manual phase the operator runs via `/bump-image` *after* agent-images merges and CI publishes the new commit-SHA-tagged image. |

### Reconciling Q1 with reality (recorded default)

The Q1 preview said "minimal image, no baked venv; installer creates the venv
on first boot." Two facts make a *pure* runtime-install fragile:

- A venv cannot be baked directly at `/home/agent/.local/opt/hermes-agent` —
  the PVC mount at `/home/agent` **shadows** anything baked under it
  (documented gotcha: "PVC mounts at /home/agent hide all image-baked files").
- Installing fresh from PyPI on every first boot needs network at pod start,
  is slow, non-reproducible, and risks Falco "new binary" noise.

**Robust interpretation (the design below):** the image bakes a **relocatable
seed venv** at `/opt/hermes-agent` (a read-only build artifact, NOT the live
runtime). On first boot a cont-init hook `cp -a`'s the seed onto the PVC at
`/home/agent/.local/opt/hermes-agent` — the *live* venv. This satisfies the
operator's intent (venv on PVC, uid-1000-writable, patches persist) while
staying offline, deterministic, and fast. If the operator wants a true
zero-baked-venv runtime install instead, that is a flag on plan/PR review.

**Relocatability is proven, not assumed:** `uv venv --relocatable` writes
console scripts with a `#!/bin/sh` polyglot shebang that re-execs the venv
python by *relative* path; a `cp -a` to a new directory runs unchanged
(verified locally 2026-06-07: relocatable venv copied to a new path ran its
console entry-point correctly). The base interpreter path (`pyvenv.cfg
home =`) stays stable because the image is immutable.

---

## Solution — agent-images (primary PR)

All changes in `derio-net/agent-images`, directory `hermes-agent-shell/`.

### 1. Auto-continue patch (Q2)

New file `hermes-agent-shell/patches/hermes-autocontinue-chat-completions.patch`
(follows the existing `ruflo-server/patches/` idiom). It widens one gate in
`agent/conversation_loop.py`:

```diff
                 if (
-                    agent.api_mode == "codex_responses"
+                    agent.api_mode in ("codex_responses", "chat_completions")
                     and agent.valid_tool_names
                     and codex_ack_continuations < 2
                     and agent._looks_like_codex_intermediate_ack(
```

`codex_ack_continuations < 2` caps the auto-continue at 2 injections/turn
(unchanged) so the widening cannot loop unboundedly. The variable name stays
`codex_ack_continuations` (renaming is out of scope — minimal patch).

### 2. Dockerfile — relocatable seed venv + apply patch + version marker

Replace the current single `RUN uv venv … && uv pip install …` (lines 44–48)
with a build that:

- `uv venv --relocatable --python 3.11 /opt/hermes-agent`
- `uv pip install --python /opt/hermes-agent/bin/python "hermes-agent==${HERMES_VERSION}"`
- copies `patches/` into the build context and applies the patch against the
  installed `site-packages/agent/conversation_loop.py`
  (`patch -p1 --forward` or `git apply`), failing the build if it does not
  apply cleanly (catches a silent upstream-refactor drift on the next bump)
- writes a **seed-version marker** `/opt/hermes-agent/.seed-version`
  containing `${HERMES_VERSION}+autocontinue1` (bump the suffix whenever the
  patch set changes)
- repoints the launcher symlink to the **PVC** path:
  `ln -sf /home/agent/.local/opt/hermes-agent/bin/hermes /usr/local/bin/hermes`
  (the first-boot hook guarantees the target exists before any login shell)
- `chown -R ${AGENT_UID}:${AGENT_GID} /opt/hermes-agent` *inside the same RUN*
  (so the seed copies cleanly as uid 1000; same-layer chown = no duplication)

`hermes --version` can no longer run at build time against the symlink (its
target is the not-yet-seeded PVC path). Smoke validation moves to the
post-first-boot assertions (below); the build instead asserts
`/opt/hermes-agent/bin/hermes --version` directly against the seed.

### 3. First-boot seed hook — `rootfs/etc/cont-init.d/35-hermes-venv-seed`

Runs in s6 cont-init (as uid 1000, the pod user). Numbered `35` so it
precedes the inventory installer (`40-shell-inventory`) and the MOTD
profile.d scripts that may reference the live `hermes`. Logic:

```sh
SEED=/opt/hermes-agent
LIVE=/home/agent/.local/opt/hermes-agent
want="$(cat "$SEED/.seed-version")"
have="$(cat "$LIVE/.seed-version" 2>/dev/null || true)"
if [ "$want" != "$have" ]; then
    rm -rf "$LIVE.new"
    mkdir -p "$(dirname "$LIVE")"
    cp -a "$SEED" "$LIVE.new"         # relocatable → runs at the new path
    rm -rf "$LIVE"
    mv "$LIVE.new" "$LIVE"            # atomic-ish swap on the PVC
fi
```

- **Version-aware** so an image/Hermes bump re-seeds (replacing the stale
  PVC venv + carrying the new baked patch). Equal versions = no-op, which
  **preserves any in-pod hot-patches** the operator made — the whole point.
- `cp -a` preserves perms; the copy is created by uid 1000 on the PVC, so it
  is uid-1000-owned and writable. `hermes update` / site-packages edits work
  in place and survive restarts.
- Idempotent; fail-loud to the cont-init log if `cp` fails (don't fake-succeed).

### 4. Smoke tests — `.github/workflows/build.yaml` (`smoke-test-hermes-agent-shell`)

Extend the existing job. After the container is up and `cont-init` ran:

- `docker exec has-smoke test -w /home/agent/.local/opt/hermes-agent/bin/python`
  — uid 1000 can write the live venv.
- `docker exec has-smoke hermes --version` — the PATH launcher resolves
  through the symlink → PVC venv and runs (proves relocatable copy works).
- `docker exec has-smoke test -O /home/agent/.local/opt/hermes-agent/bin/hermes`
  — owned by the calling uid (1000).
- **Patch assertion:** grep the *live* `conversation_loop.py` for
  `("codex_responses", "chat_completions")` — the baked patch is present.
- **Re-seed assertion:** write a sentinel into the live venv, bump nothing
  and re-run the hook → sentinel survives (same-version no-op); then simulate
  a version bump (overwrite the live `.seed-version`) and re-run → venv
  replaced. (Kept lightweight; the core guarantee is the version compare.)

### 5. bats unit tests — `hermes-agent-shell/tests/`

New `test_venv_seed.bats` exercising the hook script's branch logic with a
fake `$SEED`/`$LIVE` (tmpdirs): first-boot seeds, same-version no-ops and
preserves a sentinel, version-mismatch re-seeds. Pure shell, no Docker.

### Files touched (agent-images)

```
hermes-agent-shell/Dockerfile
hermes-agent-shell/patches/hermes-autocontinue-chat-completions.patch   (new)
hermes-agent-shell/rootfs/etc/cont-init.d/35-hermes-venv-seed           (new)
hermes-agent-shell/tests/test_venv_seed.bats                            (new)
hermes-agent-shell/README.md   (venv now PVC-resident; document seed/first-boot)
.github/workflows/build.yaml   (extend smoke-test-hermes-agent-shell)
```

### Integration note — the inventory `hermes update` reconcile

`install-inventory.sh` reconciles a pinned harness by calling
`hermes update` (its CLI self-update). Against the old **root-owned** seed
this could not write the venv — one of the very frictions #496 names. With
the venv now PVC-resident and uid-1000-owned, `hermes update` writes in
place and persists. No code change needed here; the seed design fixes this
path as a side effect. (Whether upstream Hermes ships an `update` subcommand
is a pre-existing question, untouched by this work.)

### Spec-review findings (verified against source, 2026-06-07)

- ✅ The LiteLLM BYOK path resolves to `api_mode == "chat_completions"`:
  `hermes_cli/providers.determine_api_mode` falls through to the
  `"chat_completions"` default for a custom provider on
  `http://litellm.litellm.svc:4000/v1` (no anthropic/kimi/openai/bedrock
  host match). The patch target is correct.
- ✅ `looks_like_codex_intermediate_ack` (in `agent.agent_runtime_helpers`)
  inspects only message structure/text — provider-agnostic, safe to widen.
- ✅ cont-init hooks use `#!/command/with-contenv bash` and run as uid 1000
  (s6 v3 non-root). `35-` precedes `40-shell-inventory`, so the live venv
  exists before the inventory installer / MOTD reference `hermes`.
- ✅ No rootfs/profile.d script hardcodes `/opt/hermes-agent` on PATH; the
  `/usr/local/bin/hermes` symlink is the only launcher. Repointing it to the
  PVC path is sufficient.
- ✅ Relocatable-venv copy proven locally (`uv venv --relocatable` + `cp -a`
  runs at the new path).

---

## Solution — frank (back-loaded, post-merge, manual)

Cannot run until agent-images merges and CI publishes
`ghcr.io/derio-net/hermes-agent-shell:<new-agent-images-sha>`. The operator
runs these after the agent-images PR merges:

1. **Bump the pin** — `/bump-image hermes-agent-shell <new-sha>` updates
   `apps/hermes-agent-shell/manifests/deployment.yaml:38`, watches the
   ArgoCD rollout (`Recreate` strategy → brief downtime = image pull), and
   verifies the pod comes up.
2. **Runbook gotcha** — one-liner in `agents/rules/frank-gotchas.md`
   (Agent shells section) + full prose in
   `docs/runbooks/frank-gotchas/agent-shells.md`: the Hermes venv is now
   PVC-resident (`/home/agent/.local/opt/hermes-agent`), seeded from a
   relocatable image seed on first boot, version-gated re-seed on image bump;
   in-pod patches persist but are superseded by an image bump.
3. **Blog (retroactive, fix/extension)** — update the existing
   hermes-agent-shell building + operating posts with the PVC-venv note and
   the auto-continue fix; **no new post** (fix/extension workflow).

This phase ships in the frank PR **deliberately unimplemented**, marked for
the operator.

---

## Out of scope / rejected

- **Option 3 (sudo + `allowPrivilegeEscalation: true`)** — the issue itself
  judges it overkill; biggest blast radius. Not pursued.
- **PYTHONPATH shadow-copy wrapper** — the fragile workaround the issue names;
  superseded by the PVC venv.
- **Renaming `codex_ack_continuations`** — cosmetic; keep the patch minimal.

---

## Test Plan (post-merge — operator-driven)

Run after the frank pin-bump rolls the new image onto the pod.

1. **Writability** — `kubectl exec -n hermes-agent-shell deploy/hermes-agent-shell -- \
   sh -c 'ls -ld /home/agent/.local/opt/hermes-agent && touch /home/agent/.local/opt/hermes-agent/.wtest && rm /home/agent/.local/opt/hermes-agent/.wtest && echo WRITABLE'`
   → expect `WRITABLE`, dir owned by uid 1000.
2. **hermes runs from PVC** — `kubectl exec … -- hermes --version` returns
   the version; `kubectl exec … -- readlink -f $(command -v hermes)` resolves
   under `/home/agent/.local/opt/hermes-agent`.
3. **Patch is live** — `kubectl exec … -- grep -n '"codex_responses", "chat_completions"' \
   /home/agent/.local/opt/hermes-agent/lib/python3.11/site-packages/agent/conversation_loop.py`
   returns the widened gate.
4. **Persistence across restart** — write a sentinel into the live venv,
   `kubectl rollout restart deploy/hermes-agent-shell`, confirm the sentinel
   survives (same-version no-op) and `hermes` still runs.
5. **Stall fixed (behavioral)** — replay the operator's session-matrix repro
   (the `/tmp` scripts referenced in the issue) against the LiteLLM path on
   `qwen36-a3b-64k`; confirm an announce-only turn now triggers the
   `[System: Continue now…]` injection and the agent proceeds instead of
   idling.
