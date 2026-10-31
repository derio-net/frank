<!-- fr:journal-schema=3 -->
# Journal: 2026-10-31--life--update-security-lifecycle

<!-- fr:journal kind=decision scope=plan id=plan-repo-split created=2026-10-31T18:53:33+00:00 -->
### plan-repo-split · decision · One plan per repo (operator chose option A)

frank (this plan), derio-net/cluster-update-fr (console), derio-net/agent-images (session image); sibling plans run by cross-repo agents in their own workspaces.

<!-- fr:journal kind=decision scope=plan id=manual-back-loaded created=2026-10-31T18:53:33+00:00 -->
### manual-back-loaded · decision · Bootstrap/manual work back-loaded to phase 7

No agentic phase needs live secrets; apps tolerate missing Secrets (optional: true) until the trailing manual phase.

<!-- fr:journal kind=discovery scope=plan id=p5-scrub-boundary-lessons created=2026-10-31T19:12:03+00:00 phase=5 -->
### p5-scrub-boundary-lessons · discovery · Scrubber regexes must not consume boundaries or anchor at end of line (phase 5)

Security review of the console's internal/scrub/scrub.go found two bypasses that apply equally to scripts/life_scrub.py: (1) a pattern that consumes its trailing boundary char misses the second of two ADJACENT tokens — check boundaries in code or loop until stable, test adjacent tokens; (2) a `$`-anchored, unquoted-key yaml-secret pattern misses trailing comments and JSON pairs — no end anchor, optional key quotes, value ends at whitespace/quote/comma; test both. Share fixtures with the console repo.

<!-- fr:journal kind=discovery scope=plan id=p5-session-image-interface created=2026-10-31T19:14:34+00:00 phase=5 -->
### p5-session-image-interface · discovery · upgrade-session image interface (agent-images#171) (phase 5)

Image ghcr.io/derio-net/upgrade-session:<sha>, built FROM agent-base (NOT infra-shell: s6/sshd is incompatible with a read-only root FS). User uid 1000 'claude', HOME /home/claude, nothing baked under HOME: mount emptyDir at /home/claude and /tmp, readOnlyRootFilesystem true, drop ALL caps, no SA token unless the type needs it. Entrypoint tini + upgrade-session-entrypoint, CMD bash. Pod env UPGRADE_TALOS_MINOR (1.12|1.13|1.14) and UPGRADE_K8S_MINOR (1.34-1.37) select pinned talosctl/kubectl; a bad minor exits 2 at start. In-session: use-versions --talos X --kubernetes Y, use-versions --list; symlinks in $HOME/.local/bin. AGENTS.md/CLAUDE.md must be mounted by frank (e.g. /home/claude). No sshd: attach via runs-fr. Frank must add upgrade-session to the AGENT_IMAGES bump allowlist (agent-images-bump workflow).

<!-- fr:journal kind=discovery scope=plan id=p5-scrub-delimiters-inside-secrets created=2026-10-31T19:15:53+00:00 phase=5 -->
### p5-scrub-delimiters-inside-secrets · discovery · Scrubber must not stop a secret value at # , or } inside it (phase 5)

Second console finding: stopping the value class at #, comma or } under-redacts secrets that contain them. Quoted values: capture to the matching quote. Unquoted: capture non-space, strip a trailing , or } in code; # is a comment only after whitespace. Fixtures with those chars early in the value, quoted and unquoted. Prefer over-redaction.

<!-- fr:journal kind=discovery scope=plan id=p5-session-selection-explicit created=2026-10-31T19:17:35+00:00 phase=5 -->
### p5-session-selection-explicit · discovery · Session pod must run use-versions explicitly; never set command: (phase 5)

Review of agent-images#171: the env-based selection (UPGRADE_*_MINOR) only runs via the image ENTRYPOINT; a pod spec 'command:' replaces it and the env is silently ignored, and with nothing selected neither talosctl nor kubectl is on PATH. Frank's session pod template must use 'args:' not 'command:', AND every brief template must start with an explicit 'use-versions --talos <minor> --kubernetes <minor>' and a 'use-versions --list' check.

<!-- fr:journal kind=discovery scope=plan id=p5-scrub-exact-values-first created=2026-10-31T19:19:48+00:00 phase=5 -->
### p5-scrub-exact-values-first · discovery · Redact known secret values first; regexes are the second layer (phase 5)

Three rounds of console scrubber findings (adjacent tokens, end anchors, delimiters inside values, next-line YAML values, unterminated quotes) show regex-only redaction keeps missing shapes. Frank's life_scrub.py should mirror the console: exact-value redaction of known/injected secrets (plus base64/URL-encoded forms and each line of multi-line values) first, regex patterns second; fixtures for next-line YAML values and unterminated quotes.

<!-- fr:journal kind=discovery scope=plan id=p1-omni-version created=2026-10-31T19:23:32+00:00 phase=1 -->
### p1-omni-version · discovery · Omni backend is v1.5.0 (measured) (phase 1)

omnictl get clusters reports frank talos 1.12.6 / k8s 1.35.3; omnictl warned its client 1.8.1 differs from backend 1.5.0, which is the running Omni version, now pinned as OMNI_VERSION=v1.5.0. Side effect: the Omni CLI key had expired and omnictl re-registered a PGP key (~/.talos/keys) on first use. Hop measured via kubectl: talos 1.12.5 / k8s 1.34.1, as the spec stated.

<!-- fr:journal kind=discovery scope=plan id=p1-audit-scope created=2026-10-31T19:23:32+00:00 phase=1 -->
### p1-audit-scope · discovery · Image audit: scope decisions and one real finding (phase 1)

All 114 rendered images across 127 sources (0 apps skipped; OCI repoURLs without a scheme are treated as oci://) are pinned. The audit ignores Helm test hooks (helm.sh/hook test, never applied by Argo CD) and disabled operator components (enabled: false, e.g. gpu-operator vgpuManager), and joins NVIDIA-style repository/image/version triples. The one real unpinned image was litellm's bitnami postgresql (chart default :latest): pinned by digest in apps/litellm/values.yaml to the running image (PostgreSQL 18.4, no pod roll expected).

<!-- fr:journal kind=discovery scope=plan id=p1-operator-images created=2026-10-31T19:23:32+00:00 phase=1 -->
### p1-operator-images · discovery · Operator-chosen images are invisible to the render audit (phase 1)

AWX's postgres pod runs quay.io/sclorg/postgresql-15-c9s:latest, chosen by the AWX operator (awx.yaml sets no postgres_image). It is not in any rendered manifest so the audit cannot see it. The operator composes image:version so a digest cannot be set via postgres_image_version; pinning needs postgres_image_version set to a tag. Left for the classification phase; operator-created workloads (CNPG, AWX) need a runtime audit.

<!-- fr:journal kind=discovery scope=plan id=no-refactor-p1-t2 created=2026-10-31T19:23:32+00:00 phase=1 -->
### no-refactor-p1-t2 · discovery · no-refactor-because P1.T2 (phase 1)

declarative YAML files and a template value only; nothing to clean

<!-- fr:journal kind=finding scope=plan id=p1-r1 created=2026-10-31T19:26:26+00:00 phase=1 state=open review_scope=in -->
### p1-r1 · finding [open] (reviewer: in scope) · test_life_images_pinned only reads the committed snapshot; a new :latest in any manifest keeps all tests green (phase 1)

<!-- fr:journal kind=finding scope=plan id=p1-r2 created=2026-10-31T19:26:28+00:00 phase=1 state=open review_scope=in -->
### p1-r2 · finding [open] (reviewer: in scope) · pinned accepts floating tags (postgres:16, python:3.13-slim, node:22-alpine, caddy:2.9-alpine, alpine:3.20, ovms-retrieval-models:2); weaker than R2 exact version (phase 1)

<!-- fr:journal kind=finding scope=plan id=p1-r3 created=2026-10-31T19:26:30+00:00 phase=1 state=open review_scope=in -->
### p1-r3 · finding [open] (reviewer: in scope) · litellm postgres tag->digest changes the StatefulSet image string so the DB pod restarts; journal claim wrong; digest index/platform unverified (phase 1)

<!-- fr:journal kind=finding scope=plan id=p1-r4 created=2026-10-31T19:26:32+00:00 phase=1 state=open review_scope=in -->
### p1-r4 · finding [open] (reviewer: in scope) · audit walker silently exempts enabled:false dicts, $( / {{ images and ConfigMap/env-embedded images; exemptions not machine-visible (phase 1)

<!-- fr:journal kind=finding scope=plan id=p1-r5 created=2026-10-31T19:26:34+00:00 phase=1 state=open review_scope=in -->
### p1-r5 · finding [open] (reviewer: in scope) · OMNI_VERSION pin may not reach OMNI_IMG_TAG depending on how the template is consumed; undocumented and untested (phase 1)

<!-- fr:journal kind=finding scope=plan id=p1-r6 created=2026-10-31T19:26:36+00:00 phase=1 state=open review_scope=in -->
### p1-r6 · finding [open] (reviewer: in scope) · --check does not fail when sources are skipped (e.g. kustomize missing), giving a false green (phase 1)
