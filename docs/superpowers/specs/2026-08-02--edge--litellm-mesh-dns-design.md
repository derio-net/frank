# LiteLLM on the Mesh — MagicDNS Names for the Kid Laptops

**Date:** 2026-08-02
**Layer:** edge
**Status:** Draft
**Upstream issue:** `derio-homelab/kid-laptops#72`

## Problem

The three kid laptops (`t490s`, `x1yoga`, `p52`) need to reach Frank's LiteLLM
from a foreign network. Their LLM chain has two hops: the girl's own OpenRouter
free tier first, Frank's LiteLLM once that is exhausted. Hop 1 works. Hop 2 has
never worked at all. The operator travels within days, after which the laptops
leave the LAN permanently and the mesh becomes the only path to Frank.

The upstream issue diagnosed this as "neither a name nor a route." That is half
right, and the half that is wrong is the expensive half — it points at the
homelab networking layer, which turns out to have nothing to do.

## Evidence

All measured 2026-08-02 against live infrastructure.

### What already works

| Check | Result |
|---|---|
| `headscale nodes list` | `t490s` (100.64.0.9), `x1yoga` (.10), `p52` (.11) all registered |
| `headscale routes list` | `192.168.55.0/24` **advertised and `Enabled=true`** by `argonath-w` (primary) *and* `argonath-e` |
| `argonath-{e,w}` liveness | both `online`, seen within the hour |
| Headscale ACL | `* -> *:*` — no policy obstacle |
| From **hop-1** (Hetzner, off-LAN, `--accept-routes`) → `http://192.168.55.206:4000/health/liveliness` | `200` `"I'm alive!"` |
| From **hop-1** → `http://192.168.55.206:4000/v1/models` | `401` — **LiteLLM's own** `"Authentication Error, No api key passed in."` |

That last row is the crux. From a genuinely off-LAN mesh node, LiteLLM is
already reachable and already evaluating `Authorization: Bearer`. The route
exists. The auth path exists.

### What does not work

| Check | Result |
|---|---|
| Cloudflare DoH for `*.cluster.derio.net` | `NXDOMAIN` (status 3) — the zone is homelab-DNS-only |
| Headscale `dns.nameservers.split` | covers `lab.` / `frank.` / `arr.derio.net` — **not** `cluster.derio.net` |
| Headscale `dns.extra_records` | one service entry only: `gitea-ssh.cluster.derio.net` |
| `https://litellm.cluster.derio.net/v1/models` | `302` → `auth.cluster.derio.net` (Authentik forward-auth) |

So a laptop has a route to `192.168.55.206` and no name that resolves to it.
**The sole gap is DNS.**

### Ownership

| Repo | Its part | State |
|---|---|---|
| `derio-homelab/proxmox-cluster` | `argonath-{e,w}` advertise `192.168.55.0/24` + exit nodes | **Done** |
| `derio-homelab/omada-controller` | inter-VLAN routing into `192.168.55.0/24` | **Done** — proven by hop-1 reaching `.206` |
| **`derio-net/frank`** | Headscale MagicDNS config | **The gap — this spec** |
| `derio-homelab/kid-laptops` | client `--accept-routes` + base URL | consumer-side, that repo |

Headscale *runs* on Hop but is GitOps-configured from this repo
(`clusters/hop/apps/headscale/manifests/configmap.yaml`). That split is why
ownership was ambiguous; "frank — Tailscale configuration generally" was right.

## Design

Two MagicDNS `extra_records`, plus one IngressRoute. Nothing else.

### Record 1 — `litellm-lb.cluster.derio.net` → `192.168.55.206`

Straight to LiteLLM's Cilium L2 LoadBalancer, `http`, port 4000. This is the
path already measured working from hop-1. It depends on nothing but the subnet
route and Cilium.

```
OPENAI_BASE_URL=http://litellm-lb.cluster.derio.net:4000/v1
```

### Record 2 — `litellm-api.cluster.derio.net` → `192.168.55.220`

To Traefik, `https`, port 443, under the existing `*.cluster.derio.net`
wildcard cert — carrying `ip-allowlist` and `security-headers` but **not**
`authentik-forwardauth`. This is the canonical endpoint the laptops settle on.

```
OPENAI_BASE_URL=https://litellm-api.cluster.derio.net/v1
```

The route declares `domains: [{main: "*.cluster.derio.net"}]`, the same wildcard
the existing routes use, so Traefik reuses the already-issued certificate. No
new ACME order is placed and there is no rate-limit exposure.

### Why two records and not one repointed

The chosen approach was "LB now, TLS after." Taken literally — one name whose
value changes in phase 2 — it breaks when both phases ship in one PR: a record
holds one value, so the interim never serves and the migration becomes a hard
cutover with no fallback.

Two permanent records preserve the intended journey (laptops start on `http`,
migrate to `https`) while removing the flip. They also differ in what they
depend on, which is the point: `-lb` needs only the subnet route and Cilium;
`-api` additionally needs Traefik, the cert resolver, and the middleware chain.
With the operator travelling and unable to debug remotely, keeping a path that
has already been measured end-to-end is worth one line of YAML.

### Precedent

This is not a new mechanism. `gitea-ssh.cluster.derio.net → 192.168.55.209`
already exists in the same file for the same reason — Traefik cannot carry SSH,
so mesh peers get a name straight to the LB. Verified live: it resolves to
`192.168.55.209` on a mesh node while returning `NXDOMAIN` from Cloudflare.

## Security posture — what this does and does not change

**It grants no new network access.** Any mesh node can already reach both
`192.168.55.206:4000` and `192.168.55.220:443`; that was measured before any
change. These records add *names*, not reachability.

| Endpoint | Auth | Change |
|---|---|---|
| `litellm.cluster.derio.net` (public) | Authentik SSO → LiteLLM | **untouched** — admin UI keeps SSO |
| `litellm-api.cluster.derio.net` (new) | LiteLLM Bearer key | mesh/LAN only, `ip-allowlist` |
| `litellm-lb.cluster.derio.net` (new) | LiteLLM Bearer key | mesh/LAN only |

The API surface is authenticated by LiteLLM's own virtual keys, which is what
those keys are for. Nothing is punched through the outpost — the outpost sits on
one hostname's route, and these are different routes. The invariant worth
pinning is that the *public* name keeps forward-auth and the *API* names never
gain it; a test enforces both directions.

`ip-allowlist` needs no change. Measured: from hop-1, a request to
`192.168.55.220` with a `cluster.derio.net` Host header reached the Authentik
`302`, not a `403`. Middleware order is `ip-allowlist → security-headers →
authentik-forwardauth`, so reaching the redirect proves the allowlist accepted
it — the subnet router SNATs to its own RFC1918 address, and the absence of
`100.64.0.0/10` from the allowlist is moot.

## Deployment mechanics — the step that silently fails

`clusters/hop/apps/headscale/manifests/kustomization.yaml` lists
`configmap.yaml` under plain `resources:`, **not** `configMapGenerator`. It
cannot be converted: `headplane` is a separate ArgoCD Application that mounts
the same `headscale-config` with `config_strict: true`, and Kustomize cannot
rewrite a cross-Application reference. `test_config_reaches_the_process.py`
already records headscale as an explicit exemption for exactly this reason.

Consequence: ArgoCD will report `Synced`, the ConfigMap will hold the new
records, and **headscale will keep serving the old DNS map indefinitely**. A
restart is a required deployment step, not a nicety.

```yaml
# manual-operation
id: edge-headscale-litellm-mesh-dns-restart
layer: edge
app: headscale
plan: docs/superpowers/plans/2026-08-02--edge--litellm-mesh-dns
when: After the PR merges and ArgoCD syncs the headscale Application.
why_manual: |
  headscale-config is a plain (unhashed) ConfigMap and cannot be converted to a
  Kustomize configMapGenerator, because headplane is a separate ArgoCD
  Application that mounts the same ConfigMap by name with config_strict: true;
  hashing would rename it and crashloop headplane. Nothing in the pod spec
  changes when the ConfigMap content changes, so ArgoCD reports Synced while
  headscale continues serving the DNS map it parsed at boot.
commands: |
  source .env_hop
  kubectl -n headscale-system rollout status deploy/headscale --timeout=120s
  kubectl -n headscale-system rollout restart deploy/headscale
  kubectl -n headscale-system rollout status deploy/headscale --timeout=180s
verify: |
  # Homelab DNS serves a WILDCARD *.cluster.derio.net -> 192.168.55.220, so on
  # the LAN a lookup of litellm-api returns .220 whether or not the record
  # exists. Only the litellm-lb record discriminates (.206 != the wildcard's
  # .220), so THAT is the one that proves the restart took effect. Both records
  # live in the same ConfigMap and are loaded by the same restart, so proving
  # one proves both.
  #
  # macOS (operator's Mac) — no `getent` on macOS:
  dscacheutil -q host -a name nope-xyz.cluster.derio.net     # -> 192.168.55.220 (NEGATIVE CONTROL: the wildcard)
  dscacheutil -q host -a name litellm-lb.cluster.derio.net   # -> 192.168.55.206 (PROOF: differs from the wildcard)
  # Linux mesh node (laptops, argonath): same two, via `getent hosts <name>`.
  #
  # Do NOT treat `litellm-api -> 192.168.55.220` as evidence on the LAN; it is
  # the wildcard answering. Verify that endpoint FUNCTIONALLY instead (Test
  # Plan step 5), or resolve it from a genuinely off-LAN mesh node where no
  # homelab resolver is reachable.
status: pending
```

Existing WireGuard sessions survive a headscale restart; only the control plane
blips. Clients pick up the new DNS map on their next control-plane poll, so a
laptop that is offline during the restart gets it when it next connects.

## Out of scope

- **`cluster.derio.net` split-DNS.** Would let mesh clients resolve every
  cluster name, but does not fix hop 2 on its own —
  `litellm.cluster.derio.net` would still resolve to Traefik and hit Authentik.
  Additive convenience, deliberately deferred.
- **Widening `ip-allowlist` to `100.64.0.0/10`.** Measured unnecessary.
- **Converting headscale to `configMapGenerator`.** Real root cause of the
  restart requirement, but it touches headplane's cross-Application mount days
  before travel. Deferred.
- **Laptop-side configuration.** `--accept-routes` and the base URL belong to
  `derio-homelab/kid-laptops`, which carries the acceptance row.

## Implementation Plans

| Plan | Repo | File | Depends on |
|------|------|------|-----------|
| 2026-08-02--edge--litellm-mesh-dns | `derio-net/frank` | `2026-08-02--edge--litellm-mesh-dns` | — |

## Risks

| Risk | Mitigation |
|---|---|
| Headscale restart forgotten → silently stale DNS | Back-loaded manual phase with exact commands + `verify` block; the failure mode is documented in the phase itself |
| Laptops lack `--accept-routes` → name resolves, route dead | Cross-repo dependency, flagged to kid-laptops; symptom is distinctive (resolves, then connection timeout) |
| Traefik/cert failure while travelling | `litellm-lb` fallback needs neither |
| Someone later attaches forward-auth to the API route, or strips it from the public name | `scripts/tests/` guard asserts both directions |

## Test Plan

Post-merge, operator-driven. Each row is an acceptance claim.

1. **ArgoCD syncs headscale.** `kubectl -n argocd get app headscale -o custom-columns=SYNC:.status.sync.status,HEALTH:.status.health.status` → `Synced/Healthy`.
2. **Run the manual operation above** (`rollout restart deploy/headscale`).
3. **Names resolve on the mesh — via the one check that can actually fail.**
   Homelab DNS serves a **wildcard** `*.cluster.derio.net → 192.168.55.220`,
   measured 2026-08-02 (`nope-xyz.cluster.derio.net` resolves to `.220`). So on
   the LAN, `litellm-api → 192.168.55.220` passes *identically whether or not
   the record exists* — it is the wildcard answering, and asserting it proves
   nothing.

   `litellm-lb → 192.168.55.206` **does** discriminate, because `.206` differs
   from the wildcard's `.220` and can only come from MagicDNS. That MagicDNS
   outranks the wildcard on a mesh node is already demonstrated by the existing
   `gitea-ssh.cluster.derio.net → 192.168.55.209`, which resolves correctly
   today against the same wildcard.

   Both records live in one ConfigMap and are loaded by one restart, so proving
   `litellm-lb` proves the restart landed and therefore both records are live.
   Run the negative control alongside it, so the wildcard is visible rather than
   assumed (macOS has no `getent`; use `dscacheutil -q host -a name <name>`):

   ```
   nope-xyz.cluster.derio.net    -> 192.168.55.220   # control: the wildcard
   litellm-lb.cluster.derio.net  -> 192.168.55.206   # proof: differs from it
   ```

   Public `NXDOMAIN` still holds (confirm over **DoH**, not `dig @1.1.1.1` —
   the homelab blocks outbound port 53, so that merely times out), but note it
   only shows the zone is private; it does not distinguish MagicDNS from the
   homelab wildcard. The `.206`/`.220` split is what does.

   For `litellm-api` specifically, either resolve it from a genuinely off-LAN
   mesh node (no homelab resolver in reach) or rely on step 5, which verifies
   that endpoint functionally.
4. **Direct LB path serves.** `curl -s -o /dev/null -w '%{http_code}' http://litellm-lb.cluster.derio.net:4000/health/liveliness` → `200`.
5. **TLS path serves with a valid cert and no SSO.**
   `curl -s -o /dev/null -w '%{http_code}' https://litellm-api.cluster.derio.net/v1/models` → **`401`**, not `302`.
   A `302` means forward-auth leaked onto the route; a cert error means the
   wildcard did not attach.
6. **Authenticated call succeeds** with the vaulted `kid-laptops` key:
   `curl -H "Authorization: Bearer $KEY" https://litellm-api.cluster.derio.net/v1/models` → `200` with a model list.
7. **SSO is intact on the public name.** `https://litellm.cluster.derio.net/` still `302`s to Authentik.
8. **End-to-end from a laptop on a foreign network** (the issue's own done-condition): authenticated `GET <base>/v1/models` → `200`. This is the row `derio-homelab/kid-laptops` flips.

Steps 1–7 are verifiable by the operator from the Mac. Step 8 requires a laptop
off-LAN and closes `laptop-reaches-frank-from-anywhere` in the kid-laptops
matrix — that row is theirs to flip, not this repo's.
