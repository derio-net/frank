# Journal: 2026-07-28-blog-quality-gate

<!-- fr:journal kind=finding scope=plan id=c9e8165d5447 created=2026-07-28T22:15:37 phase=1 state=fixed -->
### c9e8165d5447 · finding [fixed] · Phase 1's expected corpus count (13) is off by one: LINT FAIL is not a gate finding (phase 1)

**FIXED by the orchestrator.** Re-measured independently (14 gate findings / 11
posts / 0 LINT FAIL — matches). Corrected in two places, because the error
originated in the spec and was inherited by the plan: `01.yaml`'s P1.T3.S1 now
states 14 and explains the two counters, and the spec's remaining-backlog table
carries a note that its rows are **15 gate findings + 1 lint FAIL**, not 16 of
one thing. Later phases quote gate findings only.

The validator reports gate findings as indented `x ` lines under a post, and lint hits as separate top-level `LINT FAIL:` lines — two independent counters, each able to fail the run on its own. The spec's remaining-backlog table lists both in one table, so the plan subtracted the lint FAIL from the *finding* total and double-counted it.

Measured, not inferred — `git archive HEAD` into a temp dir, same validator and config, then the Phase 1 tree:

| | findings | posts | LINT FAIL |
|---|---|---|---|
| HEAD baseline | 15 | 11 | 1 |
| after Phase 1 | 14 | 11 | 0 |

Exactly one gate finding cleared (the `diataxis` one) plus the lint FAIL — which is the correct and complete Phase 1 result. Per-finding breakdown at baseline: 10 no-actionable-section, 2 too-little-evidence, 2 missing-diagram, 1 invalid-diataxis. No other post was touched.

Later phases quoting a target number should treat **14 findings / 11 posts** as the Phase 1 exit state, and should count gate findings and lint hits separately.

<!-- fr:journal kind=discovery scope=plan id=49afdb2d69f4 created=2026-07-28T22:15:50 phase=1 -->
### 49afdb2d69f4 · discovery · Fixing the invalid diataxis mode UNMASKS a new what-transfers lint warning on 01-introduction (phase 1)

`diataxis: explainer` was not merely a typo — an invalid mode also suppressed a lint check. The what-transfers check only applies to posts declaring `tutorial` or `explanation`, so while the value was invalid the post was exempt from it by accident.

Before (`explainer`): 3 findings, 1 WARN (em-dash density).
After (`explanation`): 2 findings, 2 WARNs — the new one being `no what-transfers closing section (expected for tutorial/explanation posts)`.

Non-gating (WARN, not FAIL) so it does not affect Phase 1's exit, but Phase 2 owns this post's evidence + actionable section and should add the what-transfers closing section in the same pass rather than leaving a WARN it just created. Generalises: any post in the corpus with an invalid `diataxis` value is silently skipping mode-conditional lint checks.
