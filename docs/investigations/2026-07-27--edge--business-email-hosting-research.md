---
status: closed-no-build
decision: buy-managed (Infomaniak)
opened: 2026-07-27
closed: 2026-07-27
---

# Business Email for `derio.net` — Research Notes (Closed: No Build)

> **Outcome up front:** Frank will **not** run a mail server. Business email
> for `derio.net` is bought from **Infomaniak** (Swiss, own Geneva
> datacenters, ~€1.58/address/month). No ArgoCD app, no new layer, no
> manifests. This document exists so the question isn't re-litigated from
> scratch — and because the interesting part is *why* the obvious build was
> the wrong build.

## The question as asked, and as refined

The brainstorm opened as *"set up a self-hostable OSS email server for
Frank — routed via Hop, in the backup scheme, easy to manage, multi-user,
modern, for consulting work."* That framing assumes the deliverable is a
server.

Mid-brainstorm the operator refined the goal:

> "My use case is to have `@derio.net` emails, not be a full-time
> email-server admin. The goal is not to self-host everything — it's to have
> a business email, ideally private and free."

That reframing is what closed the investigation. Everything below is kept
because the analysis is durable even though the build was cancelled.

## The decomposition that resolved it

"Business email" is three independent concerns that normally ship as one
product, which is why the question reads as a single decision. It isn't:

| Concern | What it is | Difficulty | Verdict |
|---|---|---|---|
| **Inbound** | Receiving `@derio.net` | Easy, low-risk | Self-hostable, genuinely |
| **Outbound** | Sending *as* `@derio.net` | Reputation-bound, adversarial, never "done" | **Do not self-host** |
| **Storage** | Where the archive lives | Easy | This is what "private" actually means |

Every serious risk identified in this investigation is an **outbound** risk.
Inbound self-hosting carries almost none of them. Once outbound is
delegated, the remaining question is only whether you want custody of the
archive badly enough to run a server for it — and here the answer was no.

## Part 1 — The OSS mail-server landscape (for the record)

Evaluated against: fits Frank's declarative-only GitOps rule, survives being
fronted by an L4 proxy on Hop, lands in Longhorn's existing backup scheme,
multi-user, manageable without a full-time admin.

| | Stalwart | Mailcow | Mailu | docker-mailserver | Maddy | WildDuck |
|---|---|---|---|---|---|---|
| Shape | 1 Rust binary | ~15 containers | ~8 containers | 1 container, many daemons | 1 Go binary | Node + Mongo + Redis |
| K8s story | Official StatefulSet docs + reference chart | **compose-only, no official chart** | Official chart, "looking for maintainers" | Community charts | DIY | DIY |
| State footprint | **1 PVC** (RocksDB) | 6+ volumes | 4+ volumes + DB | 1 volume | 1 dir | Mongo + Redis + GridFS |
| Admin UX | Web admin (users, domains, DKIM, queue, DMARC/TLS-RPT reports) | Best-in-class | Functional | **CLI/env only** | Config file | REST API only |
| Behind L4 proxy | **PROXY v1+v2, per-listener trusted nets** | ✅ | ✅ | ✅ | partial | partial |
| Maturity | **0.16.x, not 1.0** | Very mature | Mature | Mature | Young | Niche |
| Webmail | **none bundled** | SOGo | Roundcube | none | none | none |

**Had we built, the answer was Stalwart.** One binary, one PVC, PROXY
protocol v1/v2 with per-listener trusted networks, JMAP + CalDAV + CardDAV,
and a real admin UI. Its costs were 0.16.x version churn (documented
breaking migration at 0.15→0.16) and bring-your-own webmail.

**Mailcow was the best product and the wrong one here:** `docker-compose`
only, with [no maintained Helm chart](https://github.com/mailcow/mailcow-dockerized/issues/7200).
Adopting it means either a pet VM outside GitOps — a direct violation of
`agents/rules/repo-principles.md` — or owning an unmaintained chart forever.

## Part 2 — Why self-hosted outbound was rejected

### Microsoft blocks small senders, arbitrarily, and tells you nothing

In **February 2026** Microsoft hard-blocked delivery to `outlook.com` /
`hotmail.com` / `live.com` with `550 5.7.1 S3150` while its own SNDS portal
reported the blocked IPs as *clean* and the delist tool reported *"no issues
detected."* It hit Proofpoint, Mimecast, SendGrid and Mailgun alike —
**senders under 1,500 messages/day with strict spam controls were blocked.**
Operators received permanent 550s with **no preceding 421 throttling**, so
there was no early signal. Resolution took ~25 hours after escalating past
the automated response.

Note the asymmetry: **M365/Entra corporate tenants were unaffected.** Only
Microsoft's consumer domains. This is a *permanent structural* condition,
not a warm-up problem — the general operator experience is that a small
self-hosted server is blocked by Microsoft by default regardless of correct
SPF/DKIM/DMARC and a clean history.

### Silent failure is the default failure

A bounce is alertable. Spam-foldering is not. New senders are throttled,
deferred or silently dropped for weeks, and neither ArgoCD nor Frank's
Grafana stack would see it. First signal is a client saying "I never got
your proposal." Making this observable would require DMARC/TLS-RPT report
ingestion plus scheduled seed-testing with inbox-placement alerting — an
entire observability sub-layer, not a checkbox.

### Hetzner's port 25 is a permission, not a property

Outbound 25 is blocked by default on Hetzner Cloud and unblocked *on
request*, case-by-case, after the first invoice. It is a manual operation
that **gates the entire layer** — everything could be built and still not
send — and it is **revocable** on an abuse report.

### The Frank-specific finding: Hop's IP is not just a mail IP

This is the strongest argument against the build, and it is specific to this
topology. **Hop's single public IP is also the Headscale coordination
server.** A suspension, abuse action or IP change on that address takes down:

- `headscale.hop.derio.net` — the mesh control plane for the entire fleet
- the public blog at `blog.derio.net/frank`
- `counter.derio.net` — GoatCounter ingest, proxied over the mesh to
  `192.168.55.224`
- Hop's fluent-bit → Frank VictoriaLogs (`192.168.55.225`) shipping, i.e.
  **the CrowdSec canary and Falco security telemetry go dark** and the
  Frank-side dead-man's-switch fires

Self-hosted outbound would place the highest-abuse-risk workload in the
estate onto the node already carrying the mesh control plane, the public web
presence, and the security observability pipeline — making Hop a 4-role
SPOF. This repo already has two recorded SPOF deaths of exactly this shape
(`docs/runbooks/frank-gotchas/omni.md`, the Pi's 3-role death;
`hop-gotchas.md` passim). Doing it properly would have required a **second
dedicated Hetzner instance** purely so mail reputation and mesh control
lived on different IPs — real added scope.

## Part 3 — The managed-provider landscape

Free + custom domain + private + real IMAP has effectively stopped existing:
**Zoho Mail free** removed IMAP/POP (webmail only, region-restricted);
**Proton free** has no custom domains; **Cloudflare Email Routing** is free
and unlimited-volume but *only receives and forwards* — it cannot send.
The real answers sit at €1–4/month.

The axis that decides cost is **pricing model**, not privacy: flat-rate
per-account (unlimited mailboxes, priced on volume) versus per-mailbox.
Aliases are free and unlimited nearly everywhere, so for consulting the
question is how many distinct *logins* are needed, not how many addresses.

| Provider | Jurisdiction | DC location | Price | Standard IMAP/SMTP | Notes |
|---|---|---|---|---|---|
| **Infomaniak** ← chosen | 🇨🇭 CH | **Own datacenters, Geneva** | ~**€1.58**/address/mo, generous free tier | ✅ | Owns its DCs, renewable-powered, offsets 200%, CalDAV/CardDAV, kSuite bundles drive/calendar/meet |
| mailbox.org | 🇩🇪 EU | Published: Berlin, redundant | €1 Light / €4 Standard / €12 Premium per user/mo | ✅ | ISO 27001 + **BSI C5**, team admin, groups, API |
| Hetzner Webhosting | 🇩🇪 EU | Nuremberg, **owned** | ~€1.76/mo + €0.76/mo external domain | ✅ | **Unlimited mailboxes**; but shared web+mail storage metered at €1.09/GB/mo overage, konsoleH admin, no email certifications |
| Migadu | 🇨🇭 CH | ⚠️ **undisclosed** | $19/yr Micro (**20 outgoing/day**) / $90/yr Mini | ✅ | Flat unlimited mailboxes; privacy policy names no DC location or hosting subprocessor |
| Mailfence | 🇧🇪 EU | Belgium | ~€3.50/mo | ✅ | OpenPGP built in |
| OVHcloud MX Plan | 🇫🇷 EU | France | ~€1/account/mo | ✅ | Cheapest real EU option, basic UX |
| Runbox | 🇳🇴 EEA | Norway | ~$25/yr | ✅ | Hydro-powered, 25+ years |
| Proton Mail | 🇨🇭 CH | Switzerland | ~$7/user/mo Business | ⚠️ **Bridge only** | IMAP needs a local desktop app |
| Tuta | 🇩🇪 EU | Germany | ~€3/mo | ❌ **none** | Proprietary E2EE, no standard clients |
| Posteo | 🇩🇪 EU | Germany | €1/mo | ✅ | Excellent — but **no custom domains at all** |

**Traps worth recording:** Posteo is the cheapest well-regarded German
provider and cannot do custom domains. Tuta's encryption precludes IMAP,
locking you into its clients. Migadu's €19/yr headline tier sends only
**20 emails/day**, and its privacy policy discloses neither datacenter
location nor hosting subprocessor — a poor fit for anyone whose stated
requirement is jurisdiction.

**Switzerland vs EU:** Switzerland holds a GDPR adequacy decision and Swiss
FADP is comparable; neither CH nor the EU is subject to the US CLOUD Act.
The practical difference is the enforcement surface and how easily the
arrangement is written into a client contract — not substantive protection.

## Decision

**Buy Infomaniak.** Swiss, operates its own Geneva datacenters (a stronger
transparency story than EU resellers renting from hyperscalers),
~€1.58/address/month with a generous free tier, standard IMAP/SMTP plus
CalDAV/CardDAV, and zero operational burden.

**Explicitly not built:**

- No mail server on Frank (no Stalwart, no `apps/mail/`)
- No new ArgoCD Application, no new layer in `docs/layers.yaml`
- No L4 mail relay in Hop's Caddyfile
- No Hetzner port-25 unblock request
- No DMARC/seed-test observability sub-layer

## Follow-up work (outside this repo)

Buying the mailbox still requires DNS. `derio.net` is on Cloudflare — Hop's
Caddy authenticates against it via `acme_dns cloudflare` — and this repo has
**no DNS-as-code**, so these are console operations, not commits:

- `MX` records pointing at Infomaniak
- `SPF` (`TXT`) authorising Infomaniak's senders
- `DKIM` (`TXT`) from Infomaniak's generated key
- `DMARC` (`TXT`) — start at `p=none` with an `rua=` address, tighten later

Care is needed not to disturb the existing `derio.net` records serving the
blog, `counter.derio.net`, and the ACME DNS-01 challenge.

## Reusable findings for this repo

Two facts surfaced that outlive this decision:

1. **Hop's Caddy already has an L4 proxy compiled in.**
   `clusters/hop/apps/caddy/Dockerfile` builds with
   `hslatman/caddy-crowdsec-bouncer/layer4`, which pulls in `mholt/caddy-l4`.
   Hop can therefore terminate **arbitrary TCP** — with CrowdSec IP blocking
   applied to those ports — and forward over the mesh to a Frank LB IP. Any
   future non-HTTP service needing public exposure is a Caddyfile change,
   not a new component.

2. **Frank's backup requirement is close to free for any new workload.**
   `apps/longhorn/manifests/recurring-job-{daily,weekly}.yaml` target group
   `default`, which every Longhorn PVC joins automatically — daily NAS plus
   weekly Cloudflare R2, 7/4 retention. A workload whose state is one PVC is
   in the backup scheme the moment it is deployed.

## Reopen triggers

Revisit only if one of these changes:

- **Custody becomes a requirement** — a client contract mandating that the
  mail archive is held on infrastructure you control. Then Stalwart on
  Frank with a delegated smarthost becomes defensible, since it carries no
  outbound reputation risk.
- **The mailbox count grows past ~10 real logins**, where per-address
  pricing stops being trivially cheap relative to a flat-rate or self-hosted
  option.
- **Stalwart reaches 1.0 and ships webmail** (its own SPA was slated to
  begin in 2026), removing two of the three objections to the build.

None of these are current. Until one is, the answer is the mailbox.

## Sources

- [Stalwart Labs](https://stalw.art/mail-server/) ·
  [Stalwart Kubernetes docs](https://stalw.art/docs/cluster/orchestration/kubernetes/) ·
  [Stalwart PROXY protocol](https://stalw.art/docs/server/reverse-proxy/proxy-protocol/) ·
  [Stalwart roadmap / webmail](https://stalw.art/blog/roadmap/)
- [mailcow Kubernetes support request #7200](https://github.com/mailcow/mailcow-dockerized/issues/7200) ·
  [Mailu helm-charts README](https://github.com/Mailu/helm-charts/blob/master/charts/mailu/README.md)
- [Microsoft's February 2026 blocking event](https://www.engagor.ai/resources/blog/microsoft-broke-email-february-2026) ·
  [S3150 delisting](https://learn.microsoft.com/en-us/answers/questions/5516448/550-5-7-1-my-ip-is-blocked-by-outlook-(s3150)-need)
- [Hetzner port 25 policy](https://blog.hqcodeshop.fi/archives/553-Hetzner-outgoing-mail-SMTP-blocked-on-TCP25.html) ·
  [Hetzner Web Hosting features](https://docs.hetzner.com/managed/webhosting/overview/)
- [Infomaniak kMail](https://european-alternatives.eu/product/infomaniak-kmail) ·
  [mailbox.org business](https://mailbox.org/en/business) ·
  [Migadu pricing](https://www.migadu.com/pricing/) ·
  [Migadu privacy policy](https://www.migadu.com/privacy/)
- [Cloudflare Email Routing limits](https://developers.cloudflare.com/email-service/platform/limits/) ·
  [Zoho free-tier IMAP removal](https://mail.mailbux.com/blog/email-comparisons/zoho-mail-free-plan-limitations-alternative)
