# Journal: 2026-07-24-vk-agent-hang

<!-- fr:journal kind=repro scope=debug id=8bcb25b575a6 created=2026-07-24T20:22:23 -->
### 8bcb25b575a6 · repro · VK executor pool wedged: 4/4 permits held by dead executions, 10 queued

vk-local (secure-agent-pod, gpu-1) /metrics: vibekanban_active_executions=4 == vibekanban_max_executions=4 (VK_MAX_CONCURRENT_EXECUTIONS=4, apps/secure-agent-pod/manifests/deployment.yaml), vibekanban_queued_executions=10. db.v2.sqlite: 10 execution_processes rows status='running' (created 17:16-17:47Z, run_reason codingagent/setupscript/cleanupscript) while ps shows ZERO live executor processes - only 7 defunct [sh] zombies under vibe-kanban PID 7. All 4 permits held by dead executions; every new spawn queues forever = 'my agents hang'. Pod 2/2 Running, restarts=0, ArgoCD green.

<!-- fr:journal kind=root-cause scope=debug id=839700c0353c created=2026-07-24T20:22:24 -->
### 839700c0353c · root-cause · 30s MCP-client timeout cancels server-side Child::wait -> unreaped child, row stuck running, permit leaked

Documented class (docs/runbooks/frank-gotchas/agent-shells.md#vk-issue-bridge-30-s-mcp-timeout): client _recv(timeout=30.0) in fr_vk/_mcp_client.py gives up on heavy ops (start_workspace routinely >30s under load); dropping the request cancels vk-local's Child::wait() future, the child exits unreaped (defunct), the DB row stays 'running', and the concurrency permit is NEVER released. Cap doesn't time permits out -> leaks accumulate to the cap and wedge the pool. Verified live: exact 'TimeoutError: No response from MCP server within 30.0s' traceback in fr-bridge.log at 08:58Z today (fr v3.14.0); deployed v3.15.0 client still 30.0s - the gotcha's durable fix (30->180 + try/except) never shipped. Same client backs fr apply --to vk, so any dispatcher can leak, and today's strands include setupscript/cleanupscript rows.

<!-- fr:journal kind=finding scope=debug id=1265feeb9940 created=2026-07-24T20:22:26 state=fixed -->
### 1265feeb9940 · finding [fixed] · Frank-side: cap 4->8 + wedge gotcha; durable fix filed as super-fr#404

On fix/vk-agent-hang: (1) VK_MAX_CONCURRENT_EXECUTIONS 4->8 (design worst-case ~220MiB + 8x480MiB ~= 4.1GiB inside the 8Gi limit; CAUTION comment documents the permit-leak wedge and that more concurrency accelerates 30s-timeout leaks - throughput headroom, not a fix); (2) agent-shells.md gotcha extended with the wedged-pool terminal form + /metrics detection signal + fix-not-shipped status; (3) frank-gotchas.md one-liner upgraded. Durable fix filed: super-fr#404 (bump _recv 30->180, tolerate per-call TimeoutError). Merging this PR rolls vk-local (env change), which runs orphan-cleanup and clears today's wedge as a side effect.
