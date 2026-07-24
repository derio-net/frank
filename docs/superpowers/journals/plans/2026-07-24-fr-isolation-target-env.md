# Journal: 2026-07-24-fr-isolation-target-env

<!-- fr:journal kind=discovery scope=plan id=aa5ebbb1d1d0 created=2026-07-24T17:06:02 -->
### aa5ebbb1d1d0 · discovery · Guard suite runs outside base venv (fr-gated) + 7 pre-existing failures

The base clone .venv (which has pytest) is fr-pipeline-gated, and the cluster-admin devcontainer (fr isolation exec) ships no pytest. Ran the guard via a throwaway venv (pytest+pyyaml+pytest-timeout) from the worktree cwd. Full scripts/tests/ run (172 passed) surfaced 7 failures ALL unrelated to this phase: test_cert_expiry_canary (known pre-existing route-count drift), test_series_index_adoption (blog), and 5x test_sync_dossier_to_data (references scripts/sync-dossier-to-data.py which is absent from this checkout). None touch secure-agent-pod/hermes/FR_ISOLATION. Also: the suite hangs >2min without a per-test timeout (some tests attempt live calls) — use --timeout=20 --timeout-method=thread.

<!-- fr:journal kind=decision scope=plan id=8d487ee35518 created=2026-07-24T17:06:18 -->
### 8d487ee35518 · decision · kali shim mounted only on kali; vk-local left env-only

Per spec section 3, vk-local gets FR_ISOLATION_TARGET in its env: but NO profile.d shim — it runs no sshd, and the VK executor processes it spawns inherit the process env directly. Only kali (sshd) needs the re-export shim. The new configmap-fr-env.yaml re-exports FR_ISOLATION_TARGET ONLY (not the BYOK vars, which kali doesn't carry), mirroring the hermes shim's structure with renamed loop vars (_fv/_fcur/_fval).
