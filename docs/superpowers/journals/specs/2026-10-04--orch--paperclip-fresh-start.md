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
