# Journal: 2026-07-25--edge--stoa-site-www-derio-net

<!-- fr:journal kind=decision scope=spec id=d1-deploy-path created=2026-07-25T18:58:24 -->
### d1-deploy-path · decision · Manifests live in frank; image tag bumped by Tekton promotion (Q1=a)

Gitea Actions in agentic-stoa/site builds+pushes the image; a Tekton pipeline commits the tag into clusters/hop/apps/www/manifests/deployment.yaml using the existing frank-gitops-push (derio-net App) credential. Mirrors the cnc-* promotion path. Frank keeps declarative ownership of what runs on its edge; only a tag crosses the org boundary. Rejected: (b) ArgoCD-on-Hop pulling SHA-pinned manifests from the Gitea mirror (stoa-live-mirror-sync shape) — more repo autonomy but needs a Gitea credential + mesh reach from Hop's ArgoCD; (c) ConfigMap-in-frank.

<!-- fr:journal kind=decision scope=spec id=d2-stack created=2026-07-25T18:58:25 -->
### d2-stack · decision · Astro as the site framework (Q2=a)

Static-first, zero JS by default (fast + clean CSP), with islands and SSR adapters available when the conversion funnel needs forms/API routes. New ground for this estate — the blog's Hugo toolchain is not reused. Rejected: (b) Hugo (proven here but weak for interactive funnel work); (c) plain HTML now, decide later.

<!-- fr:journal kind=decision scope=spec id=d3-narrative created=2026-07-25T18:58:25 -->
### d3-narrative · decision · Infra-only narrative; repo referred to as 'site' (Q3=a)

Blog/README cover the edge + CI mechanics (a second public site on Hop, cross-org build to deploy). No business detail, per agents/rules/third-party-privacy.md. Operator renamed the repo consulting -> site specifically to be more generic/discreet, so public artifacts say 'site'. Layer: edge extension, with cicd aspects. Not a new layer number.

<!-- fr:journal kind=decision scope=spec id=d4-security created=2026-07-25T18:58:25 -->
### d4-security · decision · Blog parity plus security headers, applied to blog too (Q4=a)

www gets Caddy JSON access log -> VictoriaLogs, CrowdSec bouncer, blackbox uptime probe + Grafana alert, GoatCounter. Plus a security-headers block (HSTS, CSP, X-Content-Type-Options, Referrer-Policy, Permissions-Policy) applied to the blog vhost as well, since the same Caddyfile is being edited.

<!-- fr:journal kind=decision scope=spec id=d5-models created=2026-07-25T18:58:25 -->
### d5-models · decision · Opus for every phase tier

Operator directed Opus all the way; fr models resolve returns empty at rc=0 (inherit session model), and the session model is Opus 5, so phase executors inherit Opus without per-tier binding.

<!-- fr:journal kind=decision scope=spec id=d6-manual-placement created=2026-07-25T18:58:25 -->
### d6-manual-placement · decision · Back-load repo-enrollment manual work to the final phase

Operator agreed. All frank-side work (Caddy, Hop www app, monitoring, promotion pipeline, eventlistener trigger) is agentic and does not depend on GitHub state. Repo enrollment (Gitea mirror + backfill, GitHub webhook, has_actions, CI_AUTHORITY variable) lands in one back-loaded [manual] phase so the operator does a single pass.

<!-- fr:journal kind=discovery scope=spec id=f1-gitops-push-broken created=2026-07-25T19:03:09 -->
### f1-gitops-push-broken · discovery · PRE-EXISTING: frank-gitops-push has been SecretSyncedError for 7 days — cnc-promotion is also broken

Measured 2026-07-25. ExternalSecret frank-gitops-push (ns tekton-pipelines) has failed 1477 times since 2026-07-18T16:54Z: 'error getting GH pem from secret: secrets "github-app-derio-key" not found'. The github-app-derio ClusterGenerator (App 3994132, install 138773908) resolves auth.privateKey.secretRef in the CONSUMING ExternalSecret's namespace and ignores secretRef.namespace — the documented ESO gotcha. github-app-derio-key exists ONLY in ns secure-agent-pod (47d); the sibling github-app-stoa-key IS in tekton-pipelines, which is why stoa-github-mirror syncs fine and this one does not. SOPS sources: secrets/github-app/github-app-derio-key.yaml targets ns secure-agent-pod, github-app-stoa-key.yaml targets ns tekton-pipelines. IMPACT BEYOND THIS SPEC: cnc-promotion is the existing consumer of frank-gitops-push, so CNC staging/prod tag promotion into derio-net/frank cannot currently authenticate. NOT introduced by this work. Repair needs SOPS + the age key (neither available in this pod: no sops binary, no keys.txt), so it is an operator manual op; it is a hard prerequisite for site-promotion and is placed in the back-loaded manual phase.
