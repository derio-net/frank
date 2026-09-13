# Journal: 2026-09-13--obs--pipelinerun-failure-alerting

<!-- fr:journal kind=discovery scope=plan id=71c87342ad8a created=2026-09-13T22:26:02 -->
### 71c87342ad8a · discovery · no-refactor-because P1.T2

The task adds two YAML keys to a manifest (an action:drop metricRelabelConfigs entry) and one test that derives the metric name from the committed census. The only shared machinery it needs — the repo-anchored YAML loader — was extracted one task earlier in P1.T1.S3, so there is nothing left to restructure. Inventing a refactor step here would mean restructuring a four-line YAML literal.

<!-- fr:journal kind=discovery scope=plan id=9fa1f7b72dfc created=2026-09-13T22:26:03 -->
### 9fa1f7b72dfc · discovery · no-refactor-because P2.T2

This task replaces a placeholder PromQL string with the real expression and sets relativeTimeRange on three refIds. The unit of change is a query literal inside a Grafana provisioning document, not code: there is no duplication to collapse and no abstraction to extract. The test-side helpers (_rule_by_uid, _query_expr) were extracted in P2.T1.S3 precisely so this task and phase 3 would not each grow their own.

<!-- fr:journal kind=discovery scope=plan id=a5b62a6f87e4 created=2026-09-13T22:26:05 -->
### a5b62a6f87e4 · discovery · no-refactor-because P3.T3

One test function plus one deliberate red-then-revert demonstration. It consumes the _idle_rules() helper extracted in P3.T1.S3 and adds no duplication. The step that would normally be the refactor is instead spent proving the guard can fail — which is the more valuable use of the step for a test whose entire purpose is to catch a rename nobody will be watching for.

<!-- fr:journal kind=discovery scope=plan id=746b1bab2f52 created=2026-09-13T22:26:07 -->
### 746b1bab2f52 · discovery · no-refactor-because P4.T2

Documentation and status bookkeeping: prose into docs/runbooks/frank-gotchas/grafana.md, a one-liner into agents/rules/frank-gotchas.md, a spec Status field, and a final full-suite run. No code is written, so red-green-refactor does not apply. The deliberate structural decision — prose in the per-topic file, one-liner in the hot file, never both — is stated in the step text rather than discovered by refactoring.
