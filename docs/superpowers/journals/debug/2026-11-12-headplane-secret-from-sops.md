<!-- fr:journal-schema=3 -->
# Journal: 2026-11-12-headplane-secret-from-sops

<!-- fr:journal kind=repro scope=debug id=948e896685d6 created=2026-11-12T22:40:42+00:00 -->
### 948e896685d6 · repro · Headplane session key and cookie flags come from the git-tracked config file

Change requested under ice#5: source Headplane's server.cookie_secret from a Kubernetes Secret instead of files/config.yaml, and set server.cookie_secure: true. Headplane 0.5.5 has no cookie_secret_path; its only non-file route is env overrides (HEADPLANE_LOAD_ENV_OVERRIDES=true, HEADPLANE_SERVER__COOKIE_SECRET), applied after the file is validated, so the file must still carry a 32-char value (a non-secret placeholder).

<!-- fr:journal kind=hypothesis scope=debug id=820119a09140 created=2026-11-12T22:40:52+00:00 -->
### 820119a09140 · hypothesis · Enabling env overrides with the existing HEADPLANE_HEADSCALE_API_KEY env var makes the pod exit

coalesceEnv maps every HEADPLANE_* var to a config path: HEADPLANE_HEADSCALE_API_KEY becomes headscale.api_key, which the 0.5.5 schema rejects (onDeepUndeclaredKey reject). coalesceConfig returns undefined, coalesceEnv returns undefined, and the loader exits with 'Fatal error encountered with configuration'. The var is unused by 0.5.5 source today (no reference outside the generic loader), so it is inert while overrides are off. To test: run ghcr.io/tale/headplane:0.5.5 locally with and without it.
