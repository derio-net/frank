# Journal: 2026-08-03--orch--hermes-retrieval-store-sidecar

<!-- fr:journal kind=decision scope=spec id=d1-scope created=2026-08-03T16:44:19 -->
### d1-scope · decision · Both repos in this run; agent-images half is Bun only

Operator chose to deliver frank + agent-images together. Because the CLI is installed by hand (d2), the agent-images change is a generic Bun runtime — it needs neither the CLI's name nor a pinned git ref, so the cross-repo half is unblocked despite #759 withholding those.

<!-- fr:journal kind=decision scope=spec id=d2-cli created=2026-08-03T16:44:21 -->
### d2-cli · decision · Bun baked into the image; the CLI installed by hand onto the home PVC

agent-images ships Bun only. The operator runs a one-time global install into $HOME=/opt/data/home, which is a Longhorn PVC, so it survives pod restarts (the persistent-agent pattern already used for claude/gh auth on these shells). Keeps the private tool's name out of two public repos, honouring the discretion rule established on #748. Cost: a manual op, repeated if the home PVC is ever rebuilt.

<!-- fr:journal kind=decision scope=spec id=d3-image created=2026-08-03T16:44:22 -->
### d3-image · decision · Stock pgvector/pgvector:0.8.6-pg18, digest-pinned — no custom image

PG 18 + pgvector 0.8.6 with nothing to maintain. Its stock entrypoint already runs 'chmod 00700 $PGDATA', which is exactly the boot-time fix the hindsight image had to add by hand after fsGroup kept re-loosening PGDATA. /docker-entrypoint-initdb.d gives a declarative CREATE EXTENSION vector. Precedent in-repo: apps/vk-remote runs stock postgres:16-alpine.

<!-- fr:journal kind=decision scope=spec id=d4-auth created=2026-08-03T16:44:24 -->
### d4-auth · decision · trust auth on 127.0.0.1, matching the hindsight sidecar

No secret to provision, so nothing can crashloop the shared pod at first boot. Accepted trade-off, stated rather than hidden: every container in the pod can connect as any role, including the unmodified upstream hermes container running LLM-driven agent code. Loopback-only listen_addresses keeps the blast radius at the pod.

<!-- fr:journal kind=discovery scope=spec id=g1-container-gate created=2026-08-03T16:47:40 -->
### g1-container-gate · discovery · Design-time gate: stock pgvector boots under the pod's exact posture

Ran pgvector/pgvector:0.8.6-pg18 locally under runAsUser/runAsGroup 1000, cap-drop ALL, volume root chowned root:1000 mode 0775 (what fsGroup leaves), PGDATA a SUBDIR of the mount, trust auth, -c listen_addresses=127.0.0.1 -c port=5434, and an initdb.d CREATE EXTENSION.

Results: initdb succeeded and created PGDATA itself as drwx------ 1000:1000 (0700 — Postgres refuses anything wider); the initdb.d script ran and the issue's own acceptance query returned extversion 0.8.6; an hnsw index + cosine query worked; server is PostgreSQL 18.4; both -c overrides were honoured ('listening on IPv4 address "127.0.0.1", port 5434'); and a restart on a POPULATED volume came back healthy with rows intact.

Two consequences for the design: (1) PGDATA MUST be a subdirectory of the mount — the entrypoint creating it is what yields uid-1000 ownership; pointing it at the mount root would fail. (2) The '-k /tmp' socket-directory flag the hindsight image carries is NOT needed — the official image ships /var/run/postgresql at mode 3777 precisely for arbitrary uids.

Caveat, stated rather than glossed: the gate's off-loopback reachability check was a BAD control. Docker's userland proxy accepts the client TCP connection before it ever reaches the container netns, so it cannot disprove a loopback-only bind. The loopback claim rests on the server's own startup log line, which is direct evidence.

<!-- fr:journal kind=review scope=spec id=r1-spec-review created=2026-08-03T16:53:01 -->
### r1-spec-review · review · Spec reviewed against codebase reality — five fixes

Checked every file, line reference and mechanism the spec names.

1. Wrong line reference: cited deployment.yaml:10 for 'strategy: Recreate'; line 10 is 'strategy:', the type is on 11. Fixed.
2. FALSE claim about the ssh sidecar: the spec justified numbering the PATH shim '36' as 'below the image's 50-…-motd.sh, per the family convention'. Listed /etc/profile.d in the RUNNING ssh container: it holds only 35-hermes-agent-shell-byok-env.sh (mounted by frank) and 70-systemd-shell-extra.sh. There is NO 50-motd in this image — that belongs to the sibling hermes-agent-shell image. The number is still right; the reason was borrowed from a different container. Rewritten against what the container actually has.
3. The backup claim was inherited from the hindsight PVC's comment rather than verified. Now verified with a mechanism and evidence: Longhorn auto-labels unlabelled volumes 'recurring-job-group.longhorn.io/default: enabled'; jobs daily-nas (retain 7) and weekly-r2 (retain 4) select that group; the hindsight volume carries the label despite its PVC manifest never setting one, and has 10 backups on record.
4. Added: the ssh container's command/args are deliberately untouched, so test_hermes_ssh_byok_env_snapshot.py (which locks that script exactly) keeps holding. Routing Bun through the image rather than the wrapper is what preserves it.
5. Added the two guards this must stay inside: test_config_reaches_the_process.py already exempts this app (app-scoped, so a new ConfigMap does not trip it) — and the exemption's recorded reason only covers profile.d shims, so it needs extending for an initdb.d mount; and the Application syncs the whole manifests/ dir with no kustomization, so new files need no root-template change.

Also confirmed against live/repo: storageOverProvisioningPercentage 150 present; hermes-agent-shell-ssh is in the AGENT_IMAGES bump allowlist; bun is NOT currently in the ssh sidecar; apps/vk-remote does run stock postgres:16-alpine.

<!-- fr:journal kind=discovery scope=spec id=g2-fr-acceptance-add-broken created=2026-08-03T16:56:13 -->
### g2-fr-acceptance-add-broken · discovery · fr acceptance add cannot append to frank's matrix — indentation mismatch

'fr acceptance add' fails on docs/acceptance/matrix.yaml with 'append produced an invalid matrix, rolled back: matrix is not valid YAML'. Cause: frank's matrix writes its 'rows:' sequence items FLUSH-LEFT (column 0, which is valid YAML under a mapping key), while fr's appender emits the new item indented two spaces. YAML requires uniform indentation within one sequence, so every append is invalid and correctly rolls back. Not data corruption — the rollback is clean, and the error names YAML rather than indentation, which is what makes it look like a corrupt matrix.

Two prior symptoms of the same call also worth recording: the --origin ref form is '<repo>:<path>' where repo is the BARE name ('frank:'), not 'owner/repo' ('derio-net/frank:' is rejected).

Worked around by appending the three rows in the file's own style via yaml.safe_dump and validating (parses, row count 63 -> 66, ids unique, no row lost), then 'fr acceptance report --deterministic' to clear report drift. Staleness ERROR count returned to its 13-row baseline and this spec is no longer listed as uncited. Upstream fix belongs in super-fr's appender: match the existing sequence indentation instead of assuming two spaces.
