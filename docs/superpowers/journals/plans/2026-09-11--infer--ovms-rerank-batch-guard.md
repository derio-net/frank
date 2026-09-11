# Journal: 2026-09-11--infer--ovms-rerank-batch-guard

<!-- fr:journal kind=discovery scope=plan id=nrb-p1t1 created=2026-09-11T10:57:21 phase=1 -->
### nrb-p1t1 · discovery · no-refactor-because P1.T1 (phase 1)

This task writes no code. It captures two files verbatim off the running pod into a fixture directory; the whole point is that the bytes are unedited, so there is nothing to clean up and any tidying would destroy the property the fixture exists to have.

<!-- fr:journal kind=discovery scope=plan id=nrb-p1t3 created=2026-09-11T10:57:22 phase=1 -->
### nrb-p1t3 · discovery · no-refactor-because P1.T3 (phase 1)

Appending paths to SCANNED_PATHS and running the suite. No production code, no design latitude — the list is a list, and the second step is a CI observation. The injector's refactor lives in P1.T2.S3, where the code actually is.

<!-- fr:journal kind=discovery scope=plan id=nrb-p3t1 created=2026-09-11T10:57:24 phase=3 -->
### nrb-p3t1 · discovery · no-refactor-because P3.T1 (phase 3)

Measurement, not implementation: read the baseline restart count and idle working set, then run the harness built and refactored in phase 2. Refactoring the instrument mid-measurement would invalidate the curve.

<!-- fr:journal kind=discovery scope=plan id=nrb-p3t2 created=2026-09-11T10:57:26 phase=3 -->
### nrb-p3t2 · discovery · no-refactor-because P3.T2 (phase 3)

Live cluster operations plus arithmetic over the resulting curve. The only artefact produced is two numbers written into the spec and the reasoning behind them written into this journal. Nothing here is code that could be refactored.

<!-- fr:journal kind=discovery scope=plan id=nrb-p3t3 created=2026-09-11T10:57:28 phase=3 -->
### nrb-p3t3 · discovery · no-refactor-because P3.T3 (phase 3)

A restore-and-verify task: put the ArgoCD sync policy back exactly as found and assert on the live object. It is deliberately a separate task rather than a trailing step precisely so it cannot be skipped — turning it into a refactor slot would dilute that.

<!-- fr:journal kind=discovery scope=plan id=nrb-p6t2 created=2026-09-11T10:57:29 phase=6 -->
### nrb-p6t2 · discovery · no-refactor-because P6.T2 (phase 6)

Prose edits to two existing blog posts plus the final full-suite gate. The refactor step for phase 6's documentation work is P6.T1.S3, which re-reads the gotcha and runbook prose against house style; re-reading the same posts twice in one phase is ceremony, not review.
