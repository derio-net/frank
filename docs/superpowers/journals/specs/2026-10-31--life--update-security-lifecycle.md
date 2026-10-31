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

<!-- fr:journal kind=finding scope=spec id=s1 created=2026-10-31T18:28:12+00:00 state=open review_scope=in -->
### s1 · finding [open] (reviewer: in scope) · Security fixes for stateful/Rollouts apps vs always-session

Independent spec review finding s1.

<!-- fr:journal kind=finding scope=spec id=s2 created=2026-10-31T18:28:12+00:00 state=open review_scope=in -->
### s2 · finding [open] (reviewer: in scope) · Console write surface GitHub-only vs multi-forge

Independent spec review finding s2.

<!-- fr:journal kind=finding scope=spec id=s3 created=2026-10-31T18:28:12+00:00 state=open review_scope=in -->
### s3 · finding [open] (reviewer: in scope) · Renovate auto-merge could bypass the R28 CI hold

Independent spec review finding s3.

<!-- fr:journal kind=finding scope=spec id=s4 created=2026-10-31T18:28:12+00:00 state=open review_scope=in -->
### s4 · finding [open] (reviewer: in scope) · R16 done-definition did not fit OS steps; git trailed cluster

Independent spec review finding s4.

<!-- fr:journal kind=finding scope=spec id=s5 created=2026-10-31T18:28:12+00:00 state=open review_scope=in -->
### s5 · finding [open] (reviewer: in scope) · Idle timeout could kill a mid-upgrade session; PVC mention

Independent spec review finding s5.

<!-- fr:journal kind=finding scope=spec id=s6 created=2026-10-31T18:28:12+00:00 state=open review_scope=in -->
### s6 · finding [open] (reviewer: in scope) · talosctl rollback on Omni-managed Frank

Independent spec review finding s6.

<!-- fr:journal kind=finding scope=spec id=s7 created=2026-10-31T18:28:12+00:00 state=open review_scope=in -->
### s7 · finding [open] (reviewer: in scope) · Hop combined patch file not in git

Independent spec review finding s7.

<!-- fr:journal kind=finding scope=spec id=s8 created=2026-10-31T18:28:12+00:00 state=open review_scope=in -->
### s8 · finding [open] (reviewer: in scope) · No Frank-side route to Hop's tailnet

Independent spec review finding s8.

<!-- fr:journal kind=finding scope=spec id=s9 created=2026-10-31T18:28:12+00:00 state=open review_scope=in -->
### s9 · finding [open] (reviewer: in scope) · Session talosctl/kubectl pins vs upgrade target

Independent spec review finding s9.

<!-- fr:journal kind=finding scope=spec id=s10 created=2026-10-31T18:28:12+00:00 state=open review_scope=in -->
### s10 · finding [open] (reviewer: in scope) · Path names inconsistent

Independent spec review finding s10.

<!-- fr:journal kind=finding scope=spec id=s11 created=2026-10-31T18:28:12+00:00 state=open review_scope=in -->
### s11 · finding [open] (reviewer: in scope) · R12 alarm/report state had no Grafana design

Independent spec review finding s11.

<!-- fr:journal kind=finding scope=spec id=s12 created=2026-10-31T18:28:12+00:00 state=open review_scope=in -->
### s12 · finding [open] (reviewer: in scope) · Trivy metric cardinality vs scrape cap

Independent spec review finding s12.

<!-- fr:journal kind=finding scope=spec id=s13 created=2026-10-31T18:28:12+00:00 state=open review_scope=in -->
### s13 · finding [open] (reviewer: in scope) · Omni version source inaccurate

Independent spec review finding s13.

<!-- fr:journal kind=review scope=spec id=spec-review created=2026-10-31T18:28:12+00:00 -->
### spec-review · review · independent spec review: 13 findings, all in scope, all fixed

Reviewer: super-fr:fr-spec-reviewer (fresh context, read-only). All 13 findings fixed in the spec; no operator decision required.

<!-- fr:journal kind=finding scope=spec id=s1-resolved created=2026-10-31T18:28:12+00:00 state=fixed resolves=s1 -->
### s1-resolved · finding [fixed] · resolves s1: Security fixes for stateful/Rollouts apps vs always-session

R9 + Needs-action: security items act through their own path; session-path apps get a queue-jumping Start session.

<!-- fr:journal kind=finding scope=spec id=s2-resolved created=2026-10-31T18:28:12+00:00 state=fixed resolves=s2 -->
### s2-resolved · finding [fixed] · resolves s2: Console write surface GitHub-only vs multi-forge

Acting lists GitHub and Gitea actions plus a Gitea Actions token; never-ran recovery redelivers the GitHub push webhook instead of a cluster-side re-sync.

<!-- fr:journal kind=finding scope=spec id=s3-resolved created=2026-10-31T18:28:12+00:00 state=fixed resolves=s3 -->
### s3-resolved · finding [fixed] · resolves s3: Renovate auto-merge could bypass the R28 CI hold

Console is the only merger; Renovate automerge false; branch protection alternative documented as rejected.

<!-- fr:journal kind=finding scope=spec id=s4-resolved created=2026-10-31T18:28:12+00:00 state=fixed resolves=s4 -->
### s4-resolved · finding [fixed] · resolves s4: R16 done-definition did not fit OS steps; git trailed cluster

R16 gains an OS-step verification; R22 + new OS steps section: version declared in git before applying, gap displayed as declared/applying.

<!-- fr:journal kind=finding scope=spec id=s5-resolved created=2026-10-31T18:28:12+00:00 state=fixed resolves=s5 -->
### s5-resolved · finding [fixed] · resolves s5: Idle timeout could kill a mid-upgrade session; PVC mention

Idle clock paused during running steps; max lifetime warns; PVC dropped (emptyDir only).

<!-- fr:journal kind=finding scope=spec id=s6-resolved created=2026-10-31T18:28:12+00:00 state=fixed resolves=s6 -->
### s6-resolved · finding [fixed] · resolves s6: talosctl rollback on Omni-managed Frank

Frank rollback = revert declared version via Omni; talosctl rollback only on Hop (R19, Part 4).

<!-- fr:journal kind=finding scope=spec id=s7-resolved created=2026-10-31T18:28:12+00:00 state=fixed resolves=s7 -->
### s7-resolved · finding [fixed] · resolves s7: Hop combined patch file not in git

versions/hop.yaml stands alone; version steps via talosctl upgrade/upgrade-k8s; bringing the patch into git is out of scope.

<!-- fr:journal kind=finding scope=spec id=s8-resolved created=2026-10-31T18:28:12+00:00 state=fixed resolves=s8 -->
### s8-resolved · finding [fixed] · resolves s8: No Frank-side route to Hop's tailnet

Userspace Tailscale sidecar with tagged ephemeral pre-auth key and Headscale ACL limited to Hop APIs.

<!-- fr:journal kind=finding scope=spec id=s9-resolved created=2026-10-31T18:28:12+00:00 state=fixed resolves=s9 -->
### s9-resolved · finding [fixed] · resolves s9: Session talosctl/kubectl pins vs upgrade target

Both pinned per upgrade step; session image Renovate-tracked.

<!-- fr:journal kind=finding scope=spec id=s10-resolved created=2026-10-31T18:28:12+00:00 state=fixed resolves=s10 -->
### s10-resolved · finding [fixed] · resolves s10: Path names inconsistent

Single vocabulary: auto-merge, batch-approve, session, operator-runbook.

<!-- fr:journal kind=finding scope=spec id=s11-resolved created=2026-10-31T18:28:12+00:00 state=fixed resolves=s11 -->
### s11-resolved · finding [fixed] · resolves s11: R12 alarm/report state had no Grafana design

Console exports state metrics scraped into VictoriaMetrics.

<!-- fr:journal kind=finding scope=spec id=s12-resolved created=2026-10-31T18:28:12+00:00 state=fixed resolves=s12 -->
### s12-resolved · finding [fixed] · resolves s12: Trivy metric cardinality vs scrape cap

Per-CVE metrics off; plan measures scrape size; console reads VulnerabilityReports for detail.

<!-- fr:journal kind=finding scope=spec id=s13-resolved created=2026-10-31T18:28:12+00:00 state=fixed resolves=s13 -->
### s13-resolved · finding [fixed] · resolves s13: Omni version source inaccurate

Pin OMNI_VERSION in existing omni/omni/omni.env.template; Renovate manager points there.

<!-- fr:journal kind=decision scope=spec id=exit-baseline created=2026-10-31T18:28:12+00:00 -->
### exit-baseline · decision · exit when spec-review resolved

The exit when spec-review resolved; `fr verification set` and `deliver` compare against it.

```yaml
row_gates:
  life-automerge-and-batch: devops
  life-ci-recovery: devops
  life-clean-failure-state: devops
  life-console-acts-via-forges: devops
  life-disposable-session: devops
  life-done-means-verified: devops
  life-every-dep-has-path: devops
  life-every-version-pinned: devops
  life-grafana-trend: devops
  life-inventory-complete: devops
  life-no-credential-leak: devops
  life-os-tracks: devops
  life-rollback-and-rollouts: devops
  life-session-idempotent: devops
  life-telegram-quiet-alarm: devops
  life-vulns-jump-queue: devops
  life-working-at-handover: devops
row_kinds:
  life-automerge-and-batch: live
  life-ci-recovery: live
  life-clean-failure-state: live
  life-console-acts-via-forges: live
  life-disposable-session: live
  life-done-means-verified: live
  life-every-dep-has-path: live
  life-every-version-pinned: live
  life-grafana-trend: live
  life-inventory-complete: live
  life-no-credential-leak: live
  life-os-tracks: live
  life-rollback-and-rollouts: live
  life-session-idempotent: live
  life-telegram-quiet-alarm: live
  life-vulns-jump-queue: live
  life-working-at-handover: live
run_gate: devops
run_kind: live
```

<!-- fr:journal kind=decision scope=spec id=phase-split-2026-10-31--life--update-security-lifecycle-p2 created=2026-10-31T18:52:15+00:00 -->
### phase-split-2026-10-31--life--update-security-lifecycle-p2 · decision · ask: R4/R5/R17 — detecting updates, classifying every dependency and declaring smoke tests is its own reviewable ask
