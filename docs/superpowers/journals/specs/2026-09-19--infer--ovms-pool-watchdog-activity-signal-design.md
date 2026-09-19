# Journal: 2026-09-19--infer--ovms-pool-watchdog-activity-signal-design

<!-- fr:journal kind=decision scope=spec id=d1 created=2026-09-19T23:57:28 -->
### d1 · decision · Fix the proven root cause only; leave Rule 1's cost model untouched

Operator answered the batched Q&A: 'Nothing extra — fix the proven cause only' plus 'make watchdog restarts visible'. #813's three directions all target Rule 1, which VictoriaLogs shows never fired (peak 48.4% against a 50% trigger). The suppression lease and the busy-aware Rule 1 are both declined: they would soften the OOM protection to solve a problem that was never Rule 1's. Client-side resumability is the consumer's repo, not frank's.

<!-- fr:journal kind=decision scope=spec id=d2 created=2026-09-19T23:57:33 -->
### d2 · decision · Add a restart-loop alert — nothing paged during five restarts

Operator selected the optional visibility scope item. The incident was found by the downstream consumer noticing its job had died, not by the cluster. New feature-health rule 'ovms-pool-watchdog-restart-loop': >2 action=restart lines in 30m. Catches the class (a runaway) rather than this instance.

<!-- fr:journal kind=decision scope=spec id=d3 created=2026-09-19T23:57:39 -->
### d3 · decision · Rule 1's numerator moves from shmem to memory.current

Operator answered 'Yes — use memory.current'. memory.max is enforced by the kernel against memory.current, not against memory.stat's shmem; measured live at baseline the two differ by ~25% (1.84 vs 2.30 GiB). This explains #813's unexplained '68% with no action'. memory.peak was offered and declined for now: peak runs ~2 GiB above settled, so at an unchanged CRITICAL_PERCENT=50 it would fire Rule 1 during every normal index.

<!-- fr:journal kind=decision scope=spec id=d4 created=2026-09-19T23:57:44 -->
### d4 · decision · Test Plan: synthetic replay first, then the consumer's real 40-batch index

Operator answered 'Both'. Rows 1-4 and 6-7 are agent-drivable immediately post-merge; row 5 needs the downstream consumer to re-run the index and is the acceptance proof. Ordering is deliberate — a failure in the cheap rows means row 5 would only re-break the consumer's job.

<!-- fr:journal kind=discovery scope=spec id=x1 created=2026-09-20T00:02:13 -->
### x1 · discovery · fr acceptance add (4.5.2) corrupts a matrix whose last row ends in a folded scalar

Both rows had to be hand-appended. 'fr acceptance add' rolled back with 'write produced an invalid matrix': it emitted the new row indented 6 spaces, i.e. inside the trailing 'notes: >-' block of the final row (infer-rerank-batch-curve-measured). The file itself is valid YAML and ends with a newline, so the appender appears to derive its indent from the last physical line rather than from the document structure. Worked around by appending the rows in the file's own style with a YAML round-trip assertion on the row count; 'fr acceptance status' reads both. Worth filing upstream after checking for an existing issue.

<!-- fr:journal kind=review scope=spec id=r1 created=2026-09-20T00:06:16 -->
### r1 · review · Spec named the wrong activity counter — ovms_requests_success is readiness-probe traffic

Caught by measuring rather than reading. Control (12s, no inference) moved exactly one series: ovms_requests_success{method=ModelReady,name=bge-reranker-v2-m3} 42->44. Treatment (one /v3/embeddings + one /v3/rerank, both 200) moved ovms_requests_accepted{api=V3}, ovms_responses{api=V3} and ovms_graph_processing_time_us_count — and NOT ovms_requests_success. Shipping the first draft would have made busy=yes on every tick forever (readinessProbe hits /v2/models/bge-reranker-v2-m3/ready every 10s), silently disabling Rule 2 with no symptom until the ceiling — a failure in the opposite direction to the one being fixed, and quieter. Corrected to sum(ovms_requests_accepted) + sum(ovms_requests_rejected); neither carries a ModelReady series, so no probe filtering is needed. Test Plan row 2 added as the regression that catches exactly this.

<!-- fr:journal kind=review scope=spec id=r2 created=2026-09-20T00:06:17 -->
### r2 · review · The same wrong series is the repo's documented usage query, in three places

agents/rules/frank-gotchas.md:157, docs/runbooks/frank-gotchas/igpu-dra.md:234 and the --metrics_enable comment in apps/ovms-retrieval/manifests/deployment.yaml all recommend 'sum by (name) (increase(ovms_requests_success[1d]))' to answer whether the retrieval tier is used. That reports ~8,600/day of readiness probes for bge-reranker-v2-m3 and ~0 for bge-m3 regardless of real traffic — it invents usage for one model and hides it for the other. Added to scope as section 5 (correction to ovms_requests_accepted in all three places) because leaving the documentation asserting what this work just disproved guarantees the next reader repeats it. Flagged explicitly in the PR rather than expanded silently.

<!-- fr:journal kind=review scope=spec id=r3 created=2026-09-20T00:06:19 -->
### r3 · review · Codebase reality check: every named file, flag, series and folder exists

--metrics_enable at deployment.yaml:224. vmservicescrape.yaml present. feature-health folder present in alert-rules-cm.yaml. curl present in the ovms container (exercised via kubectl exec). Role already grants patch on deployments, so the second annotation needs no RBAC change. Alert uid 'ovms-pool-watchdog-restart-loop' is 31 chars, under Grafana's 40-char limit whose breach CrashLoops the whole Grafana pod. LogsQL validated against the live endpoint: _msg (not Hop's log:) with queryType stats returns a populated vector. scripts/tests/test_ovms_pool_watchdog.py already extracts the inline script and runs it against a stubbed kubectl, so the behaviour is testable without restructuring the manifest — and the kustomization's documented no-generator decision stays intact.
