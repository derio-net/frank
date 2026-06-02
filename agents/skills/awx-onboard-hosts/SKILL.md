---
name: awx-onboard-hosts
description: Onboard real (non-Talos) hosts into AWX for Ansible automation — dedicated SSH key, ssh-copy-id, AWX org/credential/inventory, ad-hoc ping proof, then a Gitea-backed Project + Job Template
user-invocable: true
disable-model-invocation: false
arguments:
  - name: env-file
    description: Path to the filled host inputs env file (default scripts/tmp/awx-hosts.env)
    required: false
    default: scripts/tmp/awx-hosts.env
---

# Onboard Hosts to AWX

Wire one or more **real, non-Talos** hosts (home-lab boxes, Pis, VPSes — anything
you can SSH to) into AWX so AWX can run Ansible against them. This is the path the
AWX layer's "Deployed gate" uses, and the reusable path for every host added after.

> Companion: `/oidc-onboard` wires a service into Authentik SSO. This skill is the
> *targets* side of AWX, not the auth side.

## Operating principle: scripts, not pasted blocks

Every step here is a committed, idempotent script you run with a single
`bash <path>` line — never a multi-line paste (the TUI soft-wraps code blocks and
breaks copy-paste). Scripts `set -euo pipefail`, read secrets live from the cluster,
and print verification. Read-only checks the agent runs itself.

## Inputs: the env file

Copy `awx-hosts.env.example` to `scripts/tmp/awx-hosts.env` (gitignored) and fill it.
Key fields:

- `AWX_KEY_PATH` — where the **new dedicated** AWX key is created (`~/.ssh/...`).
- `AWX_HOSTS` — one host per line, `ssh_alias | awx_host | ansible_user | become`.
  - `ssh_alias` = a `~/.ssh/config` Host (used **on your Mac** for `ssh-copy-id`).
  - `awx_host` = IP/DNS **AWX (in-cluster) connects to** — must be cluster-reachable
    (a LAN IP), NOT a Mac-only alias. Blank ⇒ resolved from `ssh -G <alias>`.
- `AWX_ORG / AWX_INVENTORY / AWX_CREDENTIAL / AWX_JOB_TEMPLATE / AWX_PLAYBOOK`.
- `AWX_PROJECT_SCM_URL` — blank ⇒ a Gitea repo is created for the ping playbook.

## Steps

### 0. Preflight (agent, read-only) — the make-or-break checks
- **ssh aliases resolve:** `ssh -G <alias>` returns hostname/user/identityfile.
- **Cross-network reachability:** an AWX pod must reach each `awx_host:22`.
  ```bash
  kubectl -n awx exec deploy/awx-task -c awx-task -- python3 -c "import socket;s=socket.socket();s.settimeout(4);s.connect(('<IP>',22));print('OPEN')"
  ```
  If targets are on a different VLAN than the cluster (e.g. `192.168.10.x` vs
  `192.168.55.x`), confirm pod→host routing here **before** building anything.

### 1. Dedicated key + ssh-copy-id  →  `bash 01-key-onboard.sh [env-file]`
Generates one ed25519 key (no passphrase — AWX needs it unlocked), `ssh-copy-id -f`
to each host, then verifies **the AWX way**: `ssh -F /dev/null -i <key>
-o IdentitiesOnly=yes <user>@<host>` so the green check reflects the new key *alone*,
not a fallback to your existing config identity.

### 2. AWX objects + ad-hoc ping proof  →  `bash 02-wire-up.sh [env-file]`
Creates (idempotent) the Organization, Machine Credential (loads the **private** key),
Inventory + hosts, sets an inventory var to skip first-contact host-key prompts, then
runs an **ad-hoc `ansible -m ping`** and reports per-host `pong`. This alone satisfies
the gate's intent ("a play runs green against a real host").

### 3. Formalize: Gitea Project + Job Template  →  `bash 03-formalize.sh [env-file]`
Creates a **private** Gitea repo with `ping.yml`, an AWX **Source Control credential**
(`frank-gitea-scm`) so the clone authenticates, an AWX Project pointing at the in-cluster
Gitea URL (`gitea-http.gitea.svc.cluster.local:3000`), waits for project sync, creates the
Job Template with the machine credential attached, launches it, and reports the `PLAY
RECAP`. This is the reusable artifact (nicer job URL for the blog).

## Security posture (baked into the scripts)
- **TLS verification ON** — `awx.cluster.derio.net` and `gitea.cluster.derio.net` have
  valid Let's Encrypt certs, so no `curl -k`. Admin password + SSH private key travel
  verified. (The in-cluster `SCM_URL` is pod→pod http, authenticated by the SCM cred.)
- **Private playbook repo** — never public; AWX clones it with the SCM credential.
- **Host keys: `accept-new` TOFU** — pins on first contact and rejects a *changed* key
  (not blanket `StrictHostKeyChecking=no`). To harden to full verification, pre-seed the
  Machine Credential's SSH known-hosts (`ssh-keyscan` the hosts) instead of TOFU.
- Secrets (AWX admin pw, Gitea pw, the private key) are read live at run time and never
  written into the env file or committed.

### 4. Verify + capture
- AWX UI job output: `https://awx.cluster.derio.net/#/jobs/playbook/<id>/output`.
- Screenshot via browser-harness for the operating post (needs Brave-Clawdia CDP up).

## Gotchas (all field-hit, 2026-06-02)

- **`ansible_ssh_common_args` is PROHIBITED in ad-hoc `extra_vars`** (AWX denylist,
  returns 400). Set host-key options as an **inventory/host variable** instead.
- **OIDC-style settings live in their own category** — unrelated here, but the same
  class of trap: AWX settings PATCH **silently drops keys not in the category** and
  returns 200. Always re-GET to confirm a write stuck.
- **`ssh-copy-id` false-"already exists":** its pre-check logs in via your agent/config
  identity, so it skips installing the new key. Use `-f` to force, and verify with
  `-F /dev/null` so your `~/.ssh/config` IdentityFile isn't silently offered alongside
  `-i` (note: `IdentitiesOnly=yes` does NOT exclude config IdentityFiles).
- **`ssh` eats `while`-loop stdin:** iterate hosts from an array (or `ssh -n`), never
  pipe the host list into `while read` with an `ssh` in the body — it consumes the rest.
- **Cross-VLAN routing** from pods to LAN hosts works on this cluster (Cilium), but
  always run the preflight socket test — it's the difference between "feasible" and
  hours of dead-end AWX config.
- **AWX runs jobs in EE pods** on the cluster network, so reachability == the preflight
  pod test (don't assume your Mac's reachability implies AWX's).
- Gitea admin creds: secret `gitea-secrets` (`username`/`password`); public repo ⇒
  AWX clones anonymously (no SCM credential needed).

## Files
- `awx-hosts.env.example` — input template (copy to `scripts/tmp/awx-hosts.env`).
- `01-key-onboard.sh`, `02-wire-up.sh`, `03-formalize.sh` — the three steps.
