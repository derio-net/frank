# Journal: 2026-10-04--orch--paperclip-fresh-start

<!-- fr:journal kind=discovery scope=spec id=brief created=2026-10-04T04:18:27+00:00 input=true -->
### brief · discovery · Operator brief (verbatim, third-party names redacted)

hmm, I want to start fresh on Paperclip, I dont use it. I have a lot of stuff there that dont really work. And I want to use a vanilla version of Paperclip (I think our own is patched? Not sure). Then I want to see what I can really do with our setup. the company we have on example-org/companies needs to be reworked before we deploy them to paperclip. Remind me, I think we have imported a basic company from there, then we modify it in the paperclip UI and it gets synced back to the companies repo? Or is it both-ways?

Follow-up: "start with fr brainstorming" — scope as framed: wipe the current instance (DB + /paperclip data), move to vanilla upstream v2026.916.1 (supersedes PR #820), decide the fate of the paperclip-shell sidecar + hermes/opencode LiteLLM adapter configmaps, pause/re-point the live-mirror-sync trigger until the company is reworked; afterwards explore what Paperclip can really do with our setup.
