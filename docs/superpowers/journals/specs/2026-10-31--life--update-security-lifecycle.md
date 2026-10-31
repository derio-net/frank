<!-- fr:journal-schema=3 -->
# Journal: 2026-10-31--life--update-security-lifecycle

<!-- fr:journal kind=discovery scope=spec id=brief created=2026-10-31T09:13:40+00:00 input=true -->
### brief · discovery · Operator brief

1) "do we have any unimplemented/unfinished specs/github issues about keeping the clusters (frank and hop) up to date and secure?"

2) "yes, let's start it. I am also interested in having a fast acting \"hotfix\" path, for security updates, as well as an early warning system (via Telegram and a dashboard)"

<!-- fr:journal kind=decision scope=spec id=proposal-b created=2026-10-31T18:22:31+00:00 decided_by=operator -->
### proposal-b · decision · Engines + thin custom console (proposal B)

Operator chose Renovate + Trivy + Grafana engines with a purpose-built console over pure tool assembly (A) or Dependency-Track (C).

<!-- fr:journal kind=decision scope=spec id=action-queue-landing created=2026-10-31T18:22:31+00:00 decided_by=operator -->
### action-queue-landing · decision · Console lands on an action queue

Mockup B chosen: Needs action (Security / batch / auto-merge countdowns / guided upgrades) first; Inventory and History as tabs.

<!-- fr:journal kind=decision scope=spec id=automerge-visible created=2026-10-31T18:22:31+00:00 decided_by=operator -->
### automerge-visible · decision · Auto-merge allowed, visibly

Renovate auto-merge for low-risk deps; console shows when they merge, allows hold/merge-now; all recorded in History. Deliver a working system, not infra only.

<!-- fr:journal kind=decision scope=spec id=disposable-sessions created=2026-10-31T18:22:31+00:00 decided_by=operator -->
### disposable-sessions · decision · Disposable agent pods for guided upgrades

Per-upgrade pod from agent-images, scoped creds injected, operator logs agent in interactively, attach via runs-fr, cleaned up afterwards. May act on clusters (omnictl/talosctl) but locked down.

<!-- fr:journal kind=decision scope=spec id=verify-real-service created=2026-10-31T18:22:31+00:00 decided_by=operator -->
### verify-real-service · decision · Every upgrade smoke-tests the real service

Done = ArgoCD applied the merge SHA (operationState) AND a smoke test against the real service passes.

<!-- fr:journal kind=decision scope=spec id=anti-goals created=2026-10-31T18:22:31+00:00 decided_by=operator -->
### anti-goals · decision · Anti-goals

No repeated Telegram alarms; no messy state after failures; always a rollback path; no credential leaks; canary/blue-green supported.

<!-- fr:journal kind=decision scope=spec id=one-spec created=2026-10-31T18:22:31+00:00 decided_by=operator -->
### one-spec · decision · One design document, possibly multi-repo plans

Four parts in order: detection, console, sessions, OS tracks.

<!-- fr:journal kind=decision scope=spec id=verification created=2026-10-31T18:22:31+00:00 decided_by=operator -->
### verification · decision · Verification: offline CI + staging pre-merge, live post-merge, devops gate

Operator holds the close-out.

<!-- fr:journal kind=decision scope=spec id=omni-runbook created=2026-10-31T18:22:31+00:00 decided_by=operator -->
### omni-runbook · decision · Omni upgrades are an operator runbook from the laptop

No pod gets access to the Omni host; console tracks and links only. Omni upgrade itself deferred to derio-net/willikins#528.

<!-- fr:journal kind=decision scope=spec id=no-console-cluster-writes created=2026-10-31T18:22:31+00:00 decided_by=operator -->
### no-console-cluster-writes · decision · Snapshots and Rollouts promote/abort only inside sessions

Console makes no cluster writes; stateful and Rollouts apps take the session path.

<!-- fr:journal kind=decision scope=spec id=ci-recovery created=2026-10-31T18:22:31+00:00 decided_by=operator -->
### ci-recovery · decision · Diagnosed CI recovery in the console

Status lost -> re-forward; never ran -> rebase/re-sync; failed -> one re-run, then failed.

<!-- fr:journal kind=decision scope=spec id=session-idempotent created=2026-10-31T18:22:31+00:00 decided_by=operator -->
### session-idempotent · decision · Start session is idempotent

Deterministic session id + per-target lock.

<!-- fr:journal kind=decision scope=spec id=naming-telegram created=2026-10-31T18:22:31+00:00 decided_by=operator -->
### naming-telegram · decision · Repo name and Telegram destination

Console repo derio-net/cluster-update-fr. Telegram group 'derio.net' with Topics, #security topic, new bot Frank Updater (@frank_updater_bot).

<!-- fr:journal kind=decision scope=spec id=stateful-always-session created=2026-10-31T18:22:31+00:00 decided_by=operator -->
### stateful-always-session · decision · Stateful and Rollouts apps always take the session path

Operator kept the session path even for patch bumps of stateful/Rollouts apps (no lighter batch path).
