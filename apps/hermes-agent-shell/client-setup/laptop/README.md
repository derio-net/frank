# hermes-agent-shell — laptop client setup

Connect to the standalone hermes agent shell on `gpu-1`.

| Transport | Endpoint | Notes |
|-----------|----------|-------|
| SSH  | `192.168.55.226:22` → container `2222` | `ssh-config.snippet` |
| Mosh | `192.168.55.226` UDP `60032–60047`     | `mosh-wrapper.sh` (pins the server range) |

## One-time

1. Append `ssh-config.snippet` to `~/.ssh/config`, set `IdentityFile` to the
   private key whose public half is in the `hermes-agent-shell-ssh-keys` Secret
   (reuse the key paired with the other shells, or add a new one — see
   `secrets/hermes-agent-shell/README.md`).
2. For Mosh, copy `mosh-wrapper.sh` somewhere on `$PATH` (e.g.
   `~/bin/mosh-hermes`), `chmod +x`, and fix the `IdentityFile` path inside.

## Connect

```bash
ssh hermes              # SSH
mosh-hermes             # Mosh (via the wrapper)
```

On login the MOTD prints the reconcile summary and the auth-status row
(`~ hermes (BYOK — no login flow)`). If you see `OPENAI_BASE_URL not set`, the
BYOK ConfigMap secret hasn't synced yet (Phase 1 bootstrap incomplete) — see
the operating post.

## Run hermes

```bash
hermes            # interactive
hermes --version  # sanity check (needs no BYOK env)
```

> **Env caveat.** `ssh hermes -- hermes ...` (a non-interactive remote command)
> does **not** source `/etc/profile.d`, so it won't have `OPENAI_BASE_URL` /
> `OPENAI_API_KEY`. Run hermes from an **interactive** session, or use
> `kubectl exec` for scripted invocations.
