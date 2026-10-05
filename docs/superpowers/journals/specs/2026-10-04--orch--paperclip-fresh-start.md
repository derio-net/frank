# Journal: 2026-10-04--orch--paperclip-fresh-start

<!-- fr:journal kind=discovery scope=spec id=brief created=2026-10-04T04:18:27+00:00 input=true -->
### brief · discovery · Operator brief (verbatim, third-party names redacted)

hmm, I want to start fresh on Paperclip, I dont use it. I have a lot of stuff there that dont really work. And I want to use a vanilla version of Paperclip (I think our own is patched? Not sure). Then I want to see what I can really do with our setup. the company we have on example-org/companies needs to be reworked before we deploy them to paperclip. Remind me, I think we have imported a basic company from there, then we modify it in the paperclip UI and it gets synced back to the companies repo? Or is it both-ways?

Follow-up: "start with fr brainstorming" — scope as framed: wipe the current instance (DB + /paperclip data), move to vanilla upstream v2026.916.1 (supersedes PR #820), decide the fate of the paperclip-shell sidecar + hermes/opencode LiteLLM adapter configmaps, pause/re-point the live-mirror-sync trigger until the company is reworked; afterwards explore what Paperclip can really do with our setup.

<!-- fr:journal kind=decision scope=spec id=vanilla-scope created=2026-10-04T04:30:18+00:00 -->
### vanilla-scope · decision · Pure upstream — drop sidecar, CLI shims, adapter ConfigMaps

Operator chose pure upstream after the shim/sidecar chain was explained. Upstream v2026.916.1 bundles claude/codex/opencode/gemini/kimi CLIs; local-model glue is re-added only if later exploration needs it.

<!-- fr:journal kind=decision scope=spec id=no-backup created=2026-10-04T04:30:18+00:00 -->
### no-backup · decision · Wipe with no backup

Operator chose no pg_dump, export or snapshot: nothing in the instance is worth keeping.

<!-- fr:journal kind=decision scope=spec id=mirror-pause created=2026-10-04T04:30:18+00:00 -->
### mirror-pause · decision · Pause the companies Gitea hook, keep the Tekton chain

Hook set active:false; chain, secrets and ArgoCD app stay; resume = new fireUrl in Infisical + re-activate.

<!-- fr:journal kind=decision scope=spec id=done-bar created=2026-10-04T04:30:18+00:00 -->
### done-bar · decision · Done = one Claude-adapter agent completes one task

Signed in via Connections with the operator's subscription, in a throwaway company. Broader exploration is a separate effort.

<!-- fr:journal kind=review scope=spec id=spec-review created=2026-10-05T18:10:57+00:00 -->
### spec-review · review · independent spec review: 12 findings (10 in, 2 out)

fr-spec-reviewer, separate context, read-only. All four operator decisions honoured.

<!-- fr:journal kind=finding scope=spec id=s1 created=2026-10-05T18:10:57+00:00 state=open review_scope=in -->
### s1 · finding [open] (reviewer: in scope) · Wipe step 3 order-dependent (PVC Terminating race)

Delete PVCs under running pods races both controllers; paperclip may boot on old DB.

<!-- fr:journal kind=finding scope=spec id=s2 created=2026-10-05T18:10:57+00:00 state=open review_scope=in -->
### s2 · finding [open] (reviewer: in scope) · TRUST_PROXY uniquelocal trusts the whole LAN via .212

uniquelocal = all RFC1918 incl. 192.168.55.0/24.

<!-- fr:journal kind=finding scope=spec id=s3 created=2026-10-05T18:10:57+00:00 state=open review_scope=in -->
### s3 · finding [open] (reviewer: in scope) · No Test Plan; R4/R5/R8/R9 unverifiable

Map each R to a check.

<!-- fr:journal kind=finding scope=spec id=s4 created=2026-10-05T18:10:57+00:00 state=open review_scope=in -->
### s4 · finding [open] (reviewer: in scope) · Connections credential durability unstated

Only /paperclip persists; a Recreate may log the agent out.

<!-- fr:journal kind=finding scope=spec id=s5 created=2026-10-05T18:10:57+00:00 state=open review_scope=in -->
### s5 · finding [open] (reviewer: in scope) · Guard test misses half of R3; exemption must be dropped

test_exempt_list_has_no_dead_entries fails otherwise.

<!-- fr:journal kind=finding scope=spec id=s6 created=2026-10-05T18:10:57+00:00 state=open review_scope=in -->
### s6 · finding [open] (reviewer: in scope) · Sequence rationale contradicts its order

New image migrates the doomed DB before the wipe; '57' unsourced.

<!-- fr:journal kind=finding scope=spec id=s7 created=2026-10-05T18:10:57+00:00 state=open review_scope=in -->
### s7 · finding [open] (reviewer: in scope) · R9 sweep misses named stale docs/ops/rows

infisical-secrets note, agent-shells.md, networking.md, purge-fs script, matrix paperclip-litellm-agents-operable.

<!-- fr:journal kind=finding scope=spec id=s8 created=2026-10-05T18:10:57+00:00 state=open review_scope=in -->
### s8 · finding [open] (reviewer: in scope) · webhooks.yaml desired state silently wrong after pause

Add a note on the companies entry.

<!-- fr:journal kind=finding scope=spec id=s9 created=2026-10-05T18:10:57+00:00 state=open review_scope=in -->
### s9 · finding [open] (reviewer: in scope) · Window trips layer-15-workflows-down

Expect it; require resolved before R7 proof.

<!-- fr:journal kind=finding scope=spec id=s10 created=2026-10-05T18:10:57+00:00 state=open review_scope=in -->
### s10 · finding [open] (reviewer: in scope) · Step 4 should assert Secrets gone; step 2 shouldn't wait on Synced

App is OutOfSync until the sweep under prune:false.

<!-- fr:journal kind=finding scope=spec id=s11 created=2026-10-05T18:10:57+00:00 state=open review_scope=out -->
### s11 · finding [open] (reviewer: out of scope) · orch-traefik-paperclip-route op pending against retired edge/domain

Pre-existing staleness.

<!-- fr:journal kind=finding scope=spec id=s12 created=2026-10-05T18:10:57+00:00 state=open review_scope=out -->
### s12 · finding [open] (reviewer: out of scope) · Paper 17 and sibling-app comments cite paperclip-shell/LITELLM-key pattern

Historical precedent, not wrong.

<!-- fr:journal kind=finding scope=spec id=s1-resolved created=2026-10-05T18:10:57+00:00 state=fixed resolves=s1 -->
### s1-resolved · finding [fixed] · resolves s1: Wipe step 3 order-dependent (PVC Terminating race)

Step 3 rewritten: DB PVC+pod first, wait new UID + Ready, then paperclip-data; UIDs recorded and compared; Pending recovery given.

<!-- fr:journal kind=finding scope=spec id=s2-resolved created=2026-10-05T18:10:57+00:00 state=fixed resolves=s2 -->
### s2-resolved · finding [fixed] · resolves s2: TRUST_PROXY uniquelocal trusts the whole LAN via .212

TRUST_PROXY = loopback,10.244.0.0/16 (Cilium ipam kubernetes, Talos default podSubnets, confirmed live before ship); guard test forbids uniquelocal/true; R4 check added.

<!-- fr:journal kind=finding scope=spec id=s3-resolved created=2026-10-05T18:10:57+00:00 state=fixed resolves=s3 -->
### s3-resolved · finding [fixed] · resolves s3: No Test Plan; R4/R5/R8/R9 unverifiable

Test Plan section maps R1–R9 to checks with CI/post-merge timing; R8 check needs no push to the third-party repo; R9 acceptance row added.

<!-- fr:journal kind=finding scope=spec id=s4-resolved created=2026-10-05T18:10:57+00:00 state=fixed resolves=s4 -->
### s4-resolved · finding [fixed] · resolves s4: Connections credential durability unstated

R7 proof now includes rollout restart + second task without re-sign-in; fix lands in this PR if it fails.

<!-- fr:journal kind=finding scope=spec id=s5-resolved created=2026-10-05T18:10:57+00:00 state=fixed resolves=s5 -->
### s5-resolved · finding [fixed] · resolves s5: Guard test misses half of R3; exemption must be dropped

Guard test assertions extended to all of R3; exemption 'drop' stated.

<!-- fr:journal kind=finding scope=spec id=s6-resolved created=2026-10-05T18:10:57+00:00 state=fixed resolves=s6 -->
### s6-resolved · finding [fixed] · resolves s6: Sequence rationale contradicts its order

Preamble reworded: migration on old DB is harmless because discarded; unsourced count removed.

<!-- fr:journal kind=finding scope=spec id=s7-resolved created=2026-10-05T18:10:57+00:00 state=fixed resolves=s7 -->
### s7-resolved · finding [fixed] · resolves s7: R9 sweep misses named stale docs/ops/rows

R9 Design bullet names each stale doc, op note, script and matrix row.

<!-- fr:journal kind=finding scope=spec id=s8-resolved created=2026-10-05T18:10:57+00:00 state=fixed resolves=s8 -->
### s8-resolved · finding [fixed] · resolves s8: webhooks.yaml desired state silently wrong after pause

webhooks.yaml note added to Design.

<!-- fr:journal kind=finding scope=spec id=s9-resolved created=2026-10-05T18:10:57+00:00 state=fixed resolves=s9 -->
### s9-resolved · finding [fixed] · resolves s9: Window trips layer-15-workflows-down

Expected alert stated; must resolve before step 6.

<!-- fr:journal kind=finding scope=spec id=s10-resolved created=2026-10-05T18:10:57+00:00 state=fixed resolves=s10 -->
### s10-resolved · finding [fixed] · resolves s10: Step 4 should assert Secrets gone; step 2 shouldn't wait on Synced

Step 4 asserts both Secrets absent; step 2 waits on sync-operation revision + live image.

<!-- fr:journal kind=finding scope=spec id=s11-resolved created=2026-10-05T18:10:57+00:00 state=open resolves=s11 out_of_scope=true -->
### s11-resolved · finding [out-of-scope] · resolves s11: orch-traefik-paperclip-route op pending against retired edge/domain

Pre-existing; flip it while touching runbook if trivial, else follow-up issue.

<!-- fr:journal kind=finding scope=spec id=s12-resolved created=2026-10-05T18:10:57+00:00 state=open resolves=s12 out_of_scope=true -->
### s12-resolved · finding [out-of-scope] · resolves s12: Paper 17 and sibling-app comments cite paperclip-shell/LITELLM-key pattern

Historical references; left as-is.
