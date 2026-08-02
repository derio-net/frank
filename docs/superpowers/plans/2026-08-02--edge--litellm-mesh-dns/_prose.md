# LiteLLM on the Mesh — MagicDNS Names for the Kid Laptops

**Spec:** `docs/superpowers/specs/2026-08-02--edge--litellm-mesh-dns-design.md`
**Upstream issue:** `derio-homelab/kid-laptops#72`
**Layer:** edge

## What this actually is

Three lines of YAML and one IngressRoute. That is the whole change.

It is worth being blunt about that, because the issue that produced this plan
reads like a networking project. It reports that the kid laptops have "neither a
name nor a route" to Frank's LiteLLM, and it names three candidate owners: the
Proxmox cluster that runs the VLAN10 exit nodes, the Omada gear underneath, and
this repo. That framing implies somebody has to go build routing.

Nobody does. The routing has been there the whole time.

`argonath-w` and `argonath-e` both advertise `192.168.55.0/24`, Headscale has
both routes `Enabled=true`, and all three laptops are already registered mesh
nodes. The proof is not a config file — it is a measurement taken from hop-1, a
node in a Hetzner datacentre with no LAN access whatsoever, which reached
`http://192.168.55.206:4000/v1/models` and got back LiteLLM's *own* `401`
("Authentication Error, No api key passed in"). Not a timeout. Not an Authentik
`302`. LiteLLM, answering, asking for a key.

So the packet path works and the auth path works. What is missing is a name.

That is the entire diagnosis, and it collapses a three-repo question into a
one-file change. The reason it was hard to see is a genuinely non-obvious split:
Headscale *runs* on Hop, but it is GitOps-configured from this repo, at
`clusters/hop/apps/headscale/manifests/configmap.yaml`. Looking for "the
Tailscale config" in the cluster that hosts the mesh finds a Deployment; the
thing that decides what names resolve lives here.

## Why two names instead of one

The plan ships `litellm-lb` (straight to the Cilium LoadBalancer, `http`, port
4000) and `litellm-api` (through Traefik, `https`, port 443, wildcard cert).
They reach the same service.

The instinct is to call one of them redundant. The reason to keep both is that
they fail independently. `litellm-lb` needs the subnet route and Cilium and
nothing else — it is the path already measured working end-to-end. `litellm-api`
additionally needs Traefik to be up, the middleware chain to be correct, and the
wildcard certificate to attach. That is three more things that can break.

Normally you would accept that and take the nicer URL. Here the operator is
about to be on another continent with three laptops belonging to someone who
will not be debugging Traefik. A fallback that has *already been proven* costs
one line of YAML and no new network access. Keep it.

It also removes a hazard the phased approach would otherwise have carried. "LB
now, TLS after," read literally as one record repointed in phase 2, breaks when
both phases ship in one PR: a DNS record holds one value, so the interim value
never serves, and the migration becomes a hard cutover with no way back. Two
permanent records preserve the intended journey — laptops start on `http`,
migrate to `https` — without the flip.

## The security question, answered plainly

This change grants no new network access *to mesh nodes* — and that
qualification is load-bearing, so it is worth keeping rather than rounding off
to the cleaner-sounding absolute.

Any mesh node could already reach both `192.168.55.206:4000` and
`192.168.55.220:443` before any of this — that was measured before a single file
was touched. What the records add, for them, is *names*. The reachability was
always there.

The absolute form does not survive contact with the LAN, though. Before this
change nothing matched `Host(litellm-api.cluster.derio.net)`, so the name 404'd;
now any source inside `ip-allowlist`'s RFC1918 ranges that can reach Traefik
gets an SSO-free path to the LiteLLM API, held only by the Bearer key. For
anything that could already reach the LB on `:4000` that is no new authority at
all — but which hosts those are is decided by Omada inter-VLAN policy, outside
this repo, and cannot be checked from here. Saying "none" would have been
claiming knowledge this repo does not have.

Nor is anything punched through the Authentik outpost. The outpost sits on one
hostname's route; `litellm-api` is a different route that simply never carries
the middleware. The public `litellm.cluster.derio.net` keeps SSO on its admin UI,
untouched. The API hosts are authenticated by LiteLLM's own virtual keys, which
is what those keys are for, and the two that the laptops will use already exist.

The invariant worth defending is that this stays true, and it can go wrong in two
opposite directions that a careless edit makes equally likely. Someone could
copy-paste `authentik-forwardauth` onto the API route — reintroducing, silently,
the exact bug this plan exists to route around. Or someone tidying two
near-identical routes could strip SSO off the public one. Phase 2 asserts both
directions, because a test that only checks one of them will cheerfully applaud
the other.

## The step that will silently do nothing

Phase 3 is manual, and it is not ceremony.

`headscale-config` is a plain, unhashed ConfigMap, and it cannot be converted to
a Kustomize `configMapGenerator` the way caddy, homepage and the gitea runner
were. headplane is a separate ArgoCD Application that mounts the *same* ConfigMap
by name with `config_strict: true`; hashing the name would rename it out from
under headplane and crashloop it, and Kustomize cannot rewrite a
cross-Application reference. `test_config_reaches_the_process.py` already carries
headscale as an explicit, reasoned exemption.

The consequence is the repo's most-repeated failure mode, the one that file was
written to catch: nothing in the pod spec changes, so ArgoCD reports `Synced`,
the ConfigMap holds both new records, and headscale serves the DNS map it parsed
at boot — forever, with nothing anywhere reporting staleness. It has bitten Caddy
(63-day-old pod serving unhardened), blackbox-exporter, and the gitea runner.

So `kubectl -n headscale-system rollout restart deploy/headscale` is a required
deployment step. Merging without it produces a green ArgoCD, a correct
ConfigMap, and laptops that still cannot resolve anything.

## What is deliberately not here

Mesh clients cannot resolve *any* `*.cluster.derio.net` name today — the zone is
homelab-DNS-only, `NXDOMAIN` from the public internet. Adding split-DNS for the
whole zone would fix that in general. It is not here, for a specific reason: it
would not fix hop 2. `litellm.cluster.derio.net` would resolve to Traefik and hit
Authentik exactly as it does now. It is additive convenience, and the deadline is
in days.

Likewise absent: widening `ip-allowlist` to `100.64.0.0/10` (measured
unnecessary — argonath SNATs, so mesh requests arrive as RFC1918 and already pass
the allowlist), converting headscale to a `configMapGenerator` (real root cause
of Phase 3, but it touches headplane's mount days before travel), and anything
laptop-side, which belongs to `derio-homelab/kid-laptops` along with the
acceptance row this unblocks.
