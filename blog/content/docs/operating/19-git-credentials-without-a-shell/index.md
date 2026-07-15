---
title: "Git Credentials Without a Shell"
series: [operating]
layer: agents
date: 2026-04-11
draft: false
tags: [operations, secure-agent-pod, git, kubernetes, secrets, credentials, troubleshooting]
summary: "Why $GITHUB_TOKEN is set in your terminal but missing in VS Code's git — and a credential helper that fixes it permanently by reading /proc/1/environ. Covers troubleshooting the missing-credential symptom across VS Code, cron, and non-interactive shells."
reader_goal: "Fix silent git auth failures in SSH sessions and VS Code by deploying a credential helper that reads /proc/1/environ instead of relying on inherited environment variables."
diataxis: [how-to, reference]
last_updated: 2026-07-15
last_updated_commit: https://github.com/derio-net/frank/commit/a8bed9a1d358b7ad87bb6dcaa9b0162e5fb0e127
weight: 20
---
{{< last-updated >}}

The symptom is weird: you ssh into the secure-agent-pod, run `git push`, and it works. You open the VS Code source control panel in the same session, click Sync, and get:

```
remote: Invalid username or token. Password authentication is not supported for Git operations.
fatal: Authentication failed for 'https://github.com/.../...'
```

Same pod, same user, same repo. What's different?

```bash
source .env   # sets KUBECONFIG
```


## Where the token actually lives

Kubernetes injects env vars into the container's PID 1 at startup. In the secure-agent-pod, `entrypoint.sh` is PID 1, so it gets `GITHUB_TOKEN` (and the rest of `agent-secrets-tier2`) via `envFrom`. Everything PID 1 spawns — sshd, supercronic, vibe-kanban — inherits that env by the normal Unix rules.

But **SSH sessions do not inherit PID 1's env.** OpenSSH builds a fresh environment for each new session from `/etc/environment`, PAM, and the login shell's init files. `GITHUB_TOKEN` isn't in any of those. So when you ssh in, your shell has no token.

The usual workaround is to re-hydrate from `/proc/1/environ` in `.bashrc`:

```bash
_env_from_pid1() { cat /proc/1/environ 2>/dev/null | tr '\0' '\n' | grep "^${1}=" | cut -d= -f2-; }
export GITHUB_TOKEN="${GITHUB_TOKEN:-$(_env_from_pid1 GITHUB_TOKEN)}"
```

That works for **interactive** shells. Your terminal sources `.bashrc`, gets the token, git works.

VS Code's git doesn't source `.bashrc`. Neither does cron. Neither does any subprocess that its parent didn't explicitly set up. You get a silent auth failure.

## The fix

Skip the env var entirely. Read `/proc/1/environ` directly from the credential helper:

```ini
[credential]
    helper = "!f() { echo \"username=clawdia-ai-assistant\"; echo \"password=$(tr '\\0' '\\n' < /proc/1/environ | sed -n 's/^GITHUB_TOKEN=//p')\"; }; f"
```

Every git invocation — regardless of how it was spawned, whether it sourced a shell init file, whether the env contains `GITHUB_TOKEN` — reads the kernel's view of PID 1's startup environment and returns the token.

```console
$ kubectl exec -n secure-agent-pod deploy/secure-agent-pod -c kali -- git config --get credential.helper
!f() { echo "username=clawdia-ai-assistant"; echo "password=$(tr '\0' '
' < /proc/1/environ | sed -n 's/^GITHUB_TOKEN=//p')"; }; f

$ kubectl exec -n secure-agent-pod deploy/secure-agent-pod -c kali -- bash -c 'env | grep -c ^GITHUB_TOKEN='
1

$ kubectl exec -n secure-agent-pod deploy/secure-agent-pod -c kali -- bash -c 'tr "\0" "
" < /proc/1/environ | grep -c ^GITHUB_TOKEN='
1
```

Baked into the image at `/opt/gitconfig`, seeded to `~/.gitconfig` on first boot:

```dockerfile
COPY gitconfig /opt/gitconfig
```

```bash
# in entrypoint.sh
[ -f "$HOME/.gitconfig" ] || cp /opt/gitconfig "$HOME/.gitconfig"
```

## Is this secure?

Strictly more secure than the env-var approach. Three reasons:

1. **`/proc/PID/environ` is kernel-enforced to be readable only by the same uid (or root)** via `ptrace_may_access`. In the secure-agent-pod, PID 1 and the `claude` user both run as uid 1000, so the helper can read it. A hypothetical attacker on the same host running as a different user cannot.

2. **Nothing touches disk.** `/proc/1/environ` is a kernel pseudo-file backed by the process's startup env in kernel memory. The token is only materialised for the duration of one `tr` + `sed` pipeline per git call, then discarded. The spec for the secure-agent-pod requires "no credential touches disk as a plaintext file" — this holds.

3. **Smaller leakage surface.** The env-var approach puts `GITHUB_TOKEN` into every interactive shell's environment, where it can leak via `env`, `ps e`, shell history, or child-process inheritance. The `/proc/1/environ` helper never exports the token anywhere.

Token rotation works the same as the env-var version: ESO updates the K8s Secret, you restart the pod, PID 1 gets the new value, the helper starts returning it.

### Verify

Confirm the credential helper works end-to-end:

```bash
# Git push should succeed without GITHUB_TOKEN in env
unset GITHUB_TOKEN
git push --dry-run

# The helper reads the token from /proc/1/environ directly
kubectl exec -n secure-agent-pod deploy/secure-agent-pod -c kali -- \
  git config --get credential.helper | grep -q /proc/1/environ && echo "helper active"
```

Expected: `git push` authenticates without prompting; the helper path is active.


## Caveats

- **Linux only.** `/proc/1/environ` doesn't exist on macOS or Windows. Not a concern for containers, but worth noting if you copy the helper to a laptop.
- **PID 1 must run as your uid.** If your entrypoint runs as root and drops privileges to a non-root user, `/proc/1/environ` becomes root-only and the helper fails with EACCES. The secure-agent-pod entrypoint runs as uid 1000 throughout.
- **Env is frozen at container start.** If ESO refreshes the Secret while the pod is running, `/proc/1/environ` still shows the old value. You have to restart the pod. This is standard Kubernetes behaviour, not specific to this helper.


## Missteps

The layer's design took a few wrong turns before it settled. These are the ones worth remembering so the next operator doesn't repeat them.

| What we assumed | Why it was wrong | What it cost |
|---|---|---|
| SSH sessions inherit PID 1's environment variables | OpenSSH builds a fresh environment per session from /etc/environment and PAM — it does not inherit env from the container entrypoint | Hours debugging silent git auth failures across VS Code, cron, and non-interactive shells before tracing the root cause to env inheritance |
| A .bashrc workaround is sufficient for all git operations | VS Code's git and cron jobs do not source .bashrc, so the token is still missing in those contexts | Repeated auth failures in VS Code and automated tasks until the /proc/1/environ credential helper was deployed |
| Exporting GITHUB_TOKEN in the shell is the standard Kubernetes pattern and is secure enough | Exporting the token pollutes every child process, can leak via env/ps/shell history, and forces every interactive shell to carry credentials it doesn't need | Larger credential surface area; the /proc/1/environ approach is strictly more secure with no leakage |
| PID 1 always runs as the same user as the credential helper | If the entrypoint runs as root and drops privileges, /proc/1/environ becomes root-only and the helper fails with EACCES | Required a design constraint that the secure-agent-pod entrypoint runs as uid 1000 throughout, limiting deployment flexibility |

## References

- [Operating on Secure Agent Pod]({{< relref "/docs/operating/14-secure-agent-pod" >}}) — Full operational guide for the pod
- [`proc(5)` — `/proc/pid/environ`](https://man7.org/linux/man-pages/man5/proc.5.html) — Kernel documentation
- [Git `gitcredentials(7)`](https://git-scm.com/docs/gitcredentials) — Credential helper protocol
