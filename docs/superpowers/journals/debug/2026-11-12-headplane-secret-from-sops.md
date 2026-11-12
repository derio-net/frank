<!-- fr:journal-schema=3 -->
# Journal: 2026-11-12-headplane-secret-from-sops

<!-- fr:journal kind=repro scope=debug id=948e896685d6 created=2026-11-12T22:40:42+00:00 -->
### 948e896685d6 · repro · Headplane session key and cookie flags come from the git-tracked config file

Change requested under ice#5: source Headplane's server.cookie_secret from a Kubernetes Secret instead of files/config.yaml, and set server.cookie_secure: true. Headplane 0.5.5 has no cookie_secret_path; its only non-file route is env overrides (HEADPLANE_LOAD_ENV_OVERRIDES=true, HEADPLANE_SERVER__COOKIE_SECRET), applied after the file is validated, so the file must still carry a 32-char value (a non-secret placeholder).

<!-- fr:journal kind=hypothesis scope=debug id=820119a09140 created=2026-11-12T22:40:52+00:00 -->
### 820119a09140 · hypothesis · Enabling env overrides with the existing HEADPLANE_HEADSCALE_API_KEY env var makes the pod exit

coalesceEnv maps every HEADPLANE_* var to a config path: HEADPLANE_HEADSCALE_API_KEY becomes headscale.api_key, which the 0.5.5 schema rejects (onDeepUndeclaredKey reject). coalesceConfig returns undefined, coalesceEnv returns undefined, and the loader exits with 'Fatal error encountered with configuration'. The var is unused by 0.5.5 source today (no reference outside the generic loader), so it is inert while overrides are off. To test: run ghcr.io/tale/headplane:0.5.5 locally with and without it.

<!-- fr:journal kind=ruled-out scope=debug id=05f088156f52 created=2026-11-12T22:46:12+00:00 -->
### 05f088156f52 · ruled-out · HEADPLANE_HEADSCALE_API_KEY does not break the loader once env overrides are on

Ran ghcr.io/tale/headplane:0.5.5 locally with the proposed config (32-char placeholder, cookie_secure: true), HEADPLANE_LOAD_ENV_OVERRIDES=true and HEADPLANE_SERVER__COOKIE_SECRET, with and without HEADPLANE_HEADSCALE_API_KEY. Both booted ('Running on 0.0.0.0:3000'). The var stays: the API-key rotation runbook's verify step reads it inside the pod.

<!-- fr:journal kind=root-cause scope=debug id=e36f9c7575f1 created=2026-11-12T22:46:18+00:00 -->
### e36f9c7575f1 · root-cause · With overrides on, Headplane 0.5.5 signs sessions with the env key and rejects the file value

Oracle: GET /admin/login with an hp_sess cookie (react-router format, base64 JSON + HMAC-SHA256, '=' stripped) returns 302 to /admin/machines only when the cookie is signed with the active key, else 200. Overrides on: env key gives 302; file placeholder and a random key give 200. Overrides off (current shape): only the file key gives 302. The env override is therefore sufficient: the file keeps a non-secret placeholder and the Secret value is authoritative. The same oracle verifies a rotation on the live pod (old key must give 200).
