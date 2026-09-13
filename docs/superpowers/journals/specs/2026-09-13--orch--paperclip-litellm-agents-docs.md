# Journal: 2026-09-13--orch--paperclip-litellm-agents-docs

<!-- fr:journal kind=decision scope=spec id=d1-structure created=2026-09-13T21:35:34 -->
### d1-structure · decision · Fold #382 into the posts' house sections

Operator chose folding over keeping dedicated appended sections: building content becomes one tutorial section before Missteps plus Missteps/Recovery rows; operating content distributes into Verify/Steps/Recover/Missteps/Quick Reference.

<!-- fr:journal kind=decision scope=spec id=d2-ci created=2026-09-13T21:35:50 -->
### d2-ci · decision · CI waits for #787; no mermaid changes here

blog-validate fails on 5 pre-existing over-budget diagrams (none added by #382). #787 touches all 5 and is green. #382 stays draft, rebases after #787 merges.

<!-- fr:journal kind=decision scope=spec id=d3-hermes created=2026-09-13T21:36:19 -->
### d3-hermes · decision · Keep full hermes coverage, updated to sha-8e6edcd

No hermes_local agent is hired today, but the wiring is live, the smoke passes and paperclip#1 is still open.

<!-- fr:journal kind=decision scope=spec id=d4-testplan created=2026-09-13T21:36:36 -->
### d4-testplan · decision · Post-merge Test Plan: rendered-page check on the live blog

<!-- fr:journal kind=discovery scope=spec id=g1-opencode-version-flip created=2026-09-13T21:36:55 -->
### g1-opencode-version-flip · discovery · Image opencode (1.18.23) is now newer than the PVC install (1.15.3)

#382 called the PVC install a newer-version fallback; after the Paperclip image bumps it is the stale copy. XDG_CONFIG_HOME wiring still targets the binary that wins on PATH.

<!-- fr:journal kind=discovery scope=spec id=g2-provider-rule created=2026-09-13T21:37:19 -->
### g2-provider-rule · discovery · hermes adapter always passes --provider unless resolution is auto

Bare qwen-* resolves to auto via MODEL_PREFIX_PROVIDER_HINTS, so config.yaml's ollama-cloud default still routes via LiteLLM. Aliases matching claude/gpt-/o1-/hermes-/glm-/kimi hints would be forced to a cloud provider.

<!-- fr:journal kind=discovery scope=spec id=g3-extraargs created=2026-09-13T21:37:49 -->
### g3-extraargs · discovery · extraArgs is now string-array-only; a single string is ignored

<!-- fr:journal kind=discovery scope=spec id=g4-litellm-logs created=2026-09-13T21:38:27 -->
### g4-litellm-logs · discovery · deploy/litellm logs sample one of 5 replicas; blackbox probe also POSTs

Routing proof must grep all running litellm pods filtered by the paperclip pod IP (verified: 10.244.10.187 on two replicas). Pod label is app.kubernetes.io/name=paperclip, not app=paperclip.

<!-- fr:journal kind=discovery scope=spec id=g5-truncation-open created=2026-09-13T21:38:57 -->
### g5-truncation-open · discovery · Session-ID truncation still present (execute.ts:594); paperclip#1 OPEN

<!-- fr:journal kind=discovery scope=spec id=g6-acceptance-blocked created=2026-09-13T21:58:43 -->
### g6-acceptance-blocked · discovery · Acceptance row not created: fr acceptance add rolls back on this matrix (super-fr#470, open)

fr 4.2.1 appends at the wrong indentation and rolls back; the matrix is intact (66 rows, trailing newline). Rows are never hand-edited, so the row paperclip-litellm-agents-operable (status skipped, manual live proof 2026-09-13) is deferred until #470 ships. Defended in the PR body.

<!-- fr:journal kind=review scope=spec id=r1-spec-review created=2026-09-13T21:59:12 -->
### r1-spec-review · review · Spec review against Q&A and codebase reality

All four decisions reflected. Codebase checks: configmap-opencode.yaml, configmap-hermes.yaml, building/16-media-generation exist; apps/paperclip-extras does NOT (building References cited it) -> fixed. MOTD tip also fires on a missing PVC opencode copy -> operating cold-PVC text corrected. Building post lacked a what-transfers section (pre-existing lint warning) -> added. Em-dash density fell vs main on both posts (28.5->22.8, 24.2->16.4).
