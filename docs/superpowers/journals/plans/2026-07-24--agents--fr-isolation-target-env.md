# Journal: 2026-07-24--agents--fr-isolation-target-env

<!-- fr:journal kind=discovery scope=plan id=aa5ebbb1d1d0 created=2026-07-24T17:06:02 -->
### aa5ebbb1d1d0 · discovery · Guard suite runs outside base venv (fr-gated) + 7 pre-existing failures

The base clone .venv (which has pytest) is fr-pipeline-gated, and the cluster-admin devcontainer (fr isolation exec) ships no pytest. Ran the guard via a throwaway venv (pytest+pyyaml+pytest-timeout) from the worktree cwd. Full scripts/tests/ run (172 passed) surfaced 7 failures ALL unrelated to this phase: test_cert_expiry_canary (known pre-existing route-count drift), test_series_index_adoption (blog), and 5x test_sync_dossier_to_data (references scripts/sync-dossier-to-data.py which is absent from this checkout). None touch secure-agent-pod/hermes/FR_ISOLATION. Also: the suite hangs >2min without a per-test timeout (some tests attempt live calls) — use --timeout=20 --timeout-method=thread.

<!-- fr:journal kind=decision scope=plan id=8d487ee35518 created=2026-07-24T17:06:18 -->
### 8d487ee35518 · decision · kali shim mounted only on kali; vk-local left env-only

Per spec section 3, vk-local gets FR_ISOLATION_TARGET in its env: but NO profile.d shim — it runs no sshd, and the VK executor processes it spawns inherit the process env directly. Only kali (sshd) needs the re-export shim. The new configmap-fr-env.yaml re-exports FR_ISOLATION_TARGET ONLY (not the BYOK vars, which kali doesn't carry), mirroring the hermes shim's structure with renamed loop vars (_fv/_fcur/_fval).

<!-- fr:journal kind=finding scope=plan id=rev-volume-linkage created=2026-07-24T17:23:03 state=fixed -->
### rev-volume-linkage · finding [fixed] · Guard did not pin volume→ConfigMap linkage (Important)

Reviewer mutation-proved a typo'd configMap.name in the fr-env volume passed all tests yet would strand the pod ContainerCreating (Recreate = old pod already gone → agent-shell outage). Fixed: test_kali_shim_configmap_and_mount now resolves the mount's volume and asserts its configMap.name equals the shim CM's metadata.name; fix mutation-verified (typo now fails the test).

<!-- fr:journal kind=finding scope=plan id=rev-shim-substring created=2026-07-24T17:23:04 state=fixed -->
### rev-shim-substring · finding [fixed] · Shim assertions were substring-level (Minor)

A comment mentioning FR_ISOLATION_TARGET would satisfy the old check even if the loop line dropped it. Fixed: _reexport_loop_covers() asserts on the 'for _x in …; do' loop line itself, applied to both shims.

<!-- fr:journal kind=finding scope=plan id=rev-container-merge created=2026-07-24T17:23:05 state=fixed -->
### rev-container-merge · finding [fixed] · containers.update() could silently shadow on cross-deployment name collision (Minor)

Fixed: per-deployment dicts with an explicit disjoint-keys assertion before merging.

<!-- fr:journal kind=finding scope=plan id=rev-naming-convention created=2026-07-24T17:23:06 state=fixed -->
### rev-naming-convention · finding [fixed] · Spec/plan names dropped the YYYY-MM-DD--<layer>-- convention (Minor)

Renamed spec to 2026-07-24--agents--fr-isolation-target-env-design.md and plan folder/journals to 2026-07-24--agents--fr-isolation-target-env (43 chars, under the vk 45-char label limit); all references updated (matrix origins, _meta.yaml slug+spec, prose, spec plan-table, test docstring, agent-shells.md); self-review re-passed.

<!-- fr:journal kind=finding scope=plan id=smoke-sshd-pid1-environ created=2026-07-24T17:56:44 state=fixed -->
### smoke-sshd-pid1-environ · finding [fixed] · hermes ssh sidecar: /proc/1/environ is proctitle junk (sshd is PID 1) — login-shell re-export dead

P2.T2.S2 smoke: kali login shell (env -i bash -lc) printed worktree, hermes ssh printed MISSING. Root cause: hermes-agent-shell-ssh has no init — PID 1 IS sshd, and OpenSSH overwrites argv/environ with its proctitle, so the shim's /proc/1/environ read returns 'sshd: … [listener] …' bytes. Fixed for FR_ISOLATION_TARGET with a static fallback export in the shim (static config, not a secret; guard-pinned to the Deployment value). Side discovery: the sidecar's BYOK (OPENAI_*) re-export is dead for the same reason — pre-existing since the official-image migration, filed as frank#688 (secrets can't be hardcoded; needs env-dump wrapper or image init).

<!-- fr:journal kind=discovery scope=plan id=smoke-results created=2026-07-24T17:56:46 -->
### smoke-results · discovery · P2 smoke results: env 4/4 live; kali login shell proven; in-pod fr walk blocked by fr 3.14.0

Post-merge roll (both pods Recreate'd, Ready): kubectl exec env checks 4/4 = worktree (row fr-isolation-env-in-pods flipped to skipped, live-proven). kali login-shell re-export proven under env -i. In-pod fr walk (P2.T2.S3): fr CLI present on secure-agent-pod PVC but at 3.14.0 < 3.15.0 (host-worktree mode ships in 3.15.0) — pod-provisioning gap, walk deferred to the agents' own plugin update; env contract independently proven.
