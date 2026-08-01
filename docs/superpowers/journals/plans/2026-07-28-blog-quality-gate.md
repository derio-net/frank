# Journal: 2026-07-28-blog-quality-gate

<!-- fr:journal kind=finding scope=plan id=c9e8165d5447 created=2026-07-28T22:15:37 phase=1 state=fixed -->
### c9e8165d5447 · finding [fixed] · Phase 1's expected corpus count (13) is off by one: LINT FAIL is not a gate finding (phase 1)

**FIXED by the orchestrator.** Re-measured independently (14 gate findings / 11
posts / 0 LINT FAIL — matches). Corrected in two places, because the error
originated in the spec and was inherited by the plan: `01.yaml`'s P1.T3.S1 now
states 14 and explains the two counters, and the spec's remaining-backlog table
carries a note that its rows are **15 gate findings + 1 lint FAIL**, not 16 of
one thing. Later phases quote gate findings only.

The validator reports gate findings as indented `x ` lines under a post, and lint hits as separate top-level `LINT FAIL:` lines — two independent counters, each able to fail the run on its own. The spec's remaining-backlog table lists both in one table, so the plan subtracted the lint FAIL from the *finding* total and double-counted it.

Measured, not inferred — `git archive HEAD` into a temp dir, same validator and config, then the Phase 1 tree:

| | findings | posts | LINT FAIL |
|---|---|---|---|
| HEAD baseline | 15 | 11 | 1 |
| after Phase 1 | 14 | 11 | 0 |

Exactly one gate finding cleared (the `diataxis` one) plus the lint FAIL — which is the correct and complete Phase 1 result. Per-finding breakdown at baseline: 10 no-actionable-section, 2 too-little-evidence, 2 missing-diagram, 1 invalid-diataxis. No other post was touched.

Later phases quoting a target number should treat **14 findings / 11 posts** as the Phase 1 exit state, and should count gate findings and lint hits separately.

<!-- fr:journal kind=discovery scope=plan id=49afdb2d69f4 created=2026-07-28T22:15:50 phase=1 -->
### 49afdb2d69f4 · discovery · Fixing the invalid diataxis mode UNMASKS a new what-transfers lint warning on 01-introduction (phase 1)

`diataxis: explainer` was not merely a typo — an invalid mode also suppressed a lint check. The what-transfers check only applies to posts declaring `tutorial` or `explanation`, so while the value was invalid the post was exempt from it by accident.

Before (`explainer`): 3 findings, 1 WARN (em-dash density).
After (`explanation`): 2 findings, 2 WARNs — the new one being `no what-transfers closing section (expected for tutorial/explanation posts)`.

Non-gating (WARN, not FAIL) so it does not affect Phase 1's exit, but Phase 2 owns this post's evidence + actionable section and should add the what-transfers closing section in the same pass rather than leaving a WARN it just created. Generalises: any post in the corpus with an invalid `diataxis` value is silently skipping mode-conditional lint checks.

<!-- fr:journal kind=finding scope=plan id=7e2020bb5d9d created=2026-07-28T22:34:14 phase=2 state=fixed -->
### 7e2020bb5d9d · finding [fixed] · The phase executor cannot dispatch post-researcher — it has no Agent tool; every remaining evidence step says to (phase 2)

**FIXED by the orchestrator**, taking the second of the two suggested routes.
Confirmed the grant independently from the agent registry — `fr-phase-executor`
is `Read, Edit, Write, Bash, Grep, Glob`, no Agent tool — then reworded
`P3.T1.S1`, `P4.T1.S1` and `P5.T1.S1` to name the **outcome** ("gather
file:line-cited evidence, following the protocol in blog-craft's
`agents/post-researcher.md`") instead of the mechanism. Rewording beats having
the orchestrator run the researcher: it is durable across future executions by
any harness, and Phase 2 showed the inline research is good when the protocol is
named. The diagnosis is the valuable part — a step naming a tool the actor lacks
does not fail loudly, it gets ticked.

P2.T1.S1 could not be executed as written. The `fr-phase-executor` grant is Read / Edit / Write / Bash only, with no Task/Agent tool, so it cannot dispatch `blog-craft:post-researcher` or any other subagent.

I did the research inline instead, following the researcher's own brief (`~/.claude/plugins/cache/derio-net--blog-craft/blog-craft/0.18.1/agents/post-researcher.md`): locate the code, read it rather than infer it, cite file:line, and mark what has to be captured live. Same artefact, different hands, so Phase 2 was not blocked.

The reason this is a finding and not a footnote: **P3, P4 and P5 all carry the same 'dispatch the post-researcher' instruction**, and they will all be run by an executor with the same missing tool. The failure mode is not a hard stop. It is an executor that reads the step, cannot comply, and quietly ticks it anyway — which is exactly the hollow-compliance shape this plan was written to avoid.

Two ways out, both fine: the orchestrator runs the researcher itself and hands the brief down inside the dispatch prompt, or the steps are reworded to name the outcome ('gather file:line-cited evidence and run the candidate commands') rather than the mechanism.

<!-- fr:journal kind=discovery scope=plan id=17b15712e944 created=2026-07-28T22:34:31 phase=2 -->
### 17b15712e944 · discovery · roadmap.yaml's key is a COLOUR key and its num is a post number — cross-checking it against docs/layers.yaml reads as drift that is not there (phase 2)

While looking for a check a reader could run against 00-overview's roadmap, I compared `blog/data/roadmap.yaml` (28 entries) with `docs/layers.yaml` (22 entries) and it looked like six layers were missing from the roadmap. They are not. The two files use different vocabularies:

- `docs/layers.yaml` `code` is the **layer registry code** used in plan filenames and commit scopes (`fix(gpu):`), numbered 1-21 plus unnumbered `repo`.
- `blog/data/roadmap.yaml` `key` is a **palette key** into `blog/data/layer_palette.yaml` (it only selects the card colour), and `num` is the **published post number**, which runs 1-33 with gaps.

So Multi-tenancy is roadmap `num: 14, key: net` (coloured as Networking) while the registry calls it `tenant`, number 14. A `set` diff between the two files produces six false positives.

Two real, small things fell out, neither fixed here (out of Phase 2 scope, which is two posts):

1. `docs/layers.yaml`'s own header comment claims 'Layer numbers reflect order of introduction (matches roadmap shortcode)'. Measured, the titles match one-for-one through 17 and diverge from 18 onward (roadmap 18 = Persistent Agent, which has no registry code; registry 18 = deploy = Progressive Delivery, which is roadmap 19). The comment is stale.
2. `layer_palette.yaml` has `tenant`, `orch`, `media`, `deploy`, `auto` colours that `roadmap.yaml` never uses, because those rows are keyed to older palette entries. Cosmetic, but it means five roadmap cards are coloured as a layer they are not.

00-overview now states the divergence rather than papering over it, because a reader who counts the roadmap cards and then counts `docs/layers.yaml` will hit exactly the confusion I did.

<!-- fr:journal kind=discovery scope=plan id=b33252aeaff3 created=2026-07-28T22:35:20 phase=2 -->
### b33252aeaff3 · discovery · Live cluster output IS obtainable from the isolation worktree, but only via an absolute KUBECONFIG — the worktree has no .env and no .talos (phase 2)

The phase brief warned that `.env` sets a relative `KUBECONFIG` (`.talos/Frank_Kubeconfig.yaml`) and that a command run from the wrong cwd silently falls back to a dead endpoint. In an fr isolation worktree the trap is one step earlier: **neither file exists there at all.** `.env` and `.talos/` are gitignored, so `git worktree add` never brings them, and sourcing `.env` from the worktree fails outright rather than pointing anywhere.

The base clone still has them, and the cluster answers. The working shape is a single command that changes into the worktree as usual and passes the kubeconfig as an absolute path into the base clone, inline:

    KUBECONFIG=<base-clone>/.talos/Frank_Kubeconfig.yaml kubectl get nodes

Confirmed live on 2026-07-28: 7 nodes Ready, Talos v1.12.6, k8s v1.35.3, 148d uptime. Read-only `kubectl` never touches the base working tree, so it does not conflict with the isolation edit-gate.

Second-order trap, hit twice while filing this very entry: the fr pipeline guard scans the **whole** command string, not just its leading segment. A journal body that quotes the base-clone path, or that contains an inner `&&` after a `cd`, is itself rejected as a base-repo command. The fix is to keep the example abstract (as above) and, if the body needs literal shell, write it to a scratch file and pass `--body "$(cat …)"` so the guard never sees it.

This matters for Phases 3-5, which need real output for nine more posts. **Live cluster evidence is available — do not settle for repo-only commands on the assumption the cluster is unreachable.**

<!-- fr:journal kind=finding scope=plan id=4eeefd7d47f9 created=2026-07-28T23:35:41 phase=3 state=fixed -->
### 4eeefd7d47f9 · finding [fixed] · A handed-down candidate command was wrong in the most dangerous way: -l longhornvolume returns 'No resources found' on Backup objects (phase 3)

The `-l longhornvolume=<vol>` selector handed down as a candidate command for 08-backup returns `No resources found in longhorn-system namespace.` — not because the volume has no backups, but because that label does not exist on a `Backup` object. The real label is `backup-volume`. Measured both, same volume, same moment:

    -l longhornvolume=pvc-64409163-...   -> No resources found in longhorn-system namespace.
    -l backup-volume=pvc-64409163-...    -> 6 rows, all Completed, one per day + Sunday weekly

The trap is not a typo, it is a plausible one. `longhornvolume` IS a genuine Longhorn label — confirmed live on `replicas.longhorn.io` and `engines.longhorn.io`, whose label sets are `{longhorn.io/backing-image, longhorndiskuuid, longhornnode, longhornvolume}` and `{longhornnode, longhornvolume}`. So the habit is learned correctly on two resource kinds and then silently wrong on the third.

This is exactly the failure class the plan exists to prevent, one level down from where it was expected. The gate's concern is that a heading can pass with nothing under it. This is a heading with a command under it, where the command runs, exits 0, and reports a catastrophe in the same words it uses for a wrong selector. A reader verifying backups at 2am would have concluded their data was gone.

Two consequences worth carrying into Phases 4 and 5:

1. Handed-down candidate commands must be RUN, not pasted. This one came in a brief as a verified-looking citation and was wrong. Running it took ten seconds.
2. A verification command that returns empty on both "healthy but mis-queried" and "genuinely broken" is not a verification command. The published section now shows both invocations side by side and names the ambiguity, because the useful teaching artefact here is the trap, not the working selector.

**Fixed 2026-08-01.** `building/08-backup` queries `-l backup-volume` and keeps the wrong
selector as a deliberate counter-example. Closing this also turned up the *same* bug live in
`operating/02-storage-backups:133` — a `backups.longhorn.io` list under
`-l longhornvolume`, in the operational backup-verification runbook, a post outside this
plan's set. Corrected there too, with the ambiguity named. The `longhornvolume` uses on
`replicas.longhorn.io` (:278, :387) and `engines.longhorn.io` (:349) are correct and were
left alone; the two `snapshots.longhorn.io` uses (:248, :391) are **unverified** — the label
set on that kind was never measured, and the cluster needs an interactive OIDC login this
session could not perform. Recorded in `_improvements.md` rather than guessed at.

<!-- fr:journal kind=discovery scope=plan id=f134ca1c2616 created=2026-07-28T23:36:14 phase=3 -->
### f134ca1c2616 · discovery · quality_exempt drops the post from the LINT layer too, not just the gate — it is a whole-post opt-out, unlike diagram_exempt (phase 3)

`quality_exempt` is a WHOLE-POST opt-out, not a per-check waiver. From the validator's driver loop:

    if fm.get("quality_exempt"):
        skipped += 1
        continue

The `continue` happens before `validate_post` AND before `lint_post`, so an exempted post leaves the gate and the AI-tells lint at the same time. Contrast `diagram_exempt`, which waives exactly one check and leaves the rest enforced.

Measured on 06-fun-stuff: before, 1 gate finding + 2 LINT WARN (em-dash 12.8/1000, no what-transfers). After adding `quality_exempt`, the validator reports `0 post(s) checked, 1 skipped` and prints nothing at all for it. The em-dash warning did not improve; it stopped being computed.

This is the right call for 06-fun-stuff — the layer genuinely has no operational surface, and the alternative was a manufactured runbook — but the cost is not zero and is worth stating rather than discovering later:

1. Every future ai-vocabulary FAIL in that post is now invisible. `ai-vocabulary` is a FAIL-severity check; an exempt post cannot fail it.
2. Phase 6's planned tripwire (fenced command block required under every actionable heading) will also skip it, if the tripwire is built on this validator's post-selection logic. Worth checking when Phase 6 is written: the tripwire should probably scan headings independently of `quality_exempt`, since the exemption is about not HAVING an actionable section, not about being allowed a hollow one.
3. The corpus arithmetic changes shape. An exempted post leaves the denominator, so "N findings across M posts" silently measures a smaller corpus than it did before. Phase 6 should quote checked/skipped alongside the finding count.

Upstream shape, if anyone wants it: an `actionable_exempt: <reason>` per-check waiver (mirroring `diagram_exempt`) would express "this layer has nothing to verify" without also buying an exit from the lint layer. Not filed — the total opt-out is defensible for a novelty layer, and blog-craft may reasonably want exemptions to be expensive.

<!-- fr:journal kind=discovery scope=plan id=d780977882f5 created=2026-07-28T23:36:56 phase=3 -->
### d780977882f5 · discovery · Adding actionable sections surfaced 6 factual errors the gate cannot see — all true-when-written, all invalidated by later repo work (phase 3)

The blind researchers were dispatched to answer "what would a reader run, and does the repo contradict the post?". The second half turned out to be the higher-yield half. Adding an actionable section requires reading the surrounding prose closely enough to write in its voice, and that reading is what surfaces the drift. Six corrections came out of four posts, none of which any gate can see:

- 05-gitops: `longhorn v1.11.0` in the App-of-Apps tree; the pin has been `1.11.2` since the instance-manager heap-leak fix. Checked the two sibling versions in the same tree (cilium 1.17.0, gpu-operator v25.10.1) — both still correct, so exactly one number had gone stale.
- 05-gitops: the "typical Application" snippet carried `prune: false` and a `group: ""` that the real `apps/root/templates/cilium.yaml` does not have. The post's own Missteps table narrates removing that line, four screens below the snippet that still shows it.
- 05-gitops: the Missteps row explaining WHY it was removed was also wrong — it said pruning was "safe and desired" for some apps. Commit 62ca0e7c says the opposite: ArgoCD normalises `prune: false` to absent, so the explicit line made root permanently OutOfSync. Behaviour did not change; only the drift went away.
- 05-gitops: "Dex disabled — no SSO yet. Authentik integration planned." Live `argocd-cm` has had an Authentik `oidc.config` since Layer 13. A reader would conclude ArgoCD is unauthenticated.
- 08-backup: "Layer 8 protects that data" — it is Layer 9. Corroborated by `docs/layers.yaml` (obs=8, backup=9), the alert rule's own header, `blog/data/roadmap.yaml`, and the post's own `weight: 9`.
- 08-backup: RTO figures presented as fact when the paper dossier for this very layer names the absence of a measured RTO as one of its gaps. No restore drill has been run here.

The pattern: all six were TRUE WHEN WRITTEN and were invalidated by later work in the same repo. Nothing notices. The blog has no equivalent of `selfHeal`, and a version number in prose carries no tracking annotation.

Two things follow for the remaining phases:

1. Budget for corrections, not just additions. The phase brief framed this as "add a section"; roughly half the work was repair. Phases 4 and 5 cover live-service layers (inference, auth, metrics-api) that have moved considerably more than storage has, so expect a higher rate, not lower.
2. Verify the citations you are handed. Two of the four researcher briefs contained a claim that did not survive checking: 03-storage's "no manifest defines longhorn-static" (it exists live, generated by Longhorn from its own `default-longhorn-static-storage-class` setting — the post's sample was correct and needed no fix), and 08-backup's `longhornvolume` selector (filed separately as a finding). Read-only researchers cannot run commands, so their NEGATIVE claims are the weakest part of a brief and the most tempting to act on.

<!-- fr:journal kind=finding scope=plan id=288cdc2efe7a created=2026-07-29T00:09:20 phase=3 state=fixed -->
### 288cdc2efe7a · finding [fixed] · All four Phase 3 posts ended in a recap — and the gate's own what-transfers check was firing on every one of them as an ignored WARN (phase 3)

Phase 3 shipped four posts at 0 gate findings. A blind cold-reader per post then found, independently, that **all four ended in a recap rather than a takeaway** and that three of the four made a claim the surrounding evidence did not support. None of it is visible to the validator, and one of the findings is visible to the validator only as a WARN nobody had to act on.

The gate's own model of the ending is `transfer_headings` (`what transfers` / `what you keep` / `takeaway(s)`), severity **warn**. All four posts were emitting that warning before this pass and all four were still counted green. So the corpus had a check for exactly this defect, firing correctly, on every post, ignored — because the failing severity is what gets worked and the warning severity is what gets scrolled past.

What the cold-readers added on top of the warning is the part a regex cannot supply: in every case the strongest portable lesson was **already in the post**, buried mid-document, and the fix was promotion rather than authorship.

- 03-storage: declared-size accounting is not disk fullness (was inside the verify section).
- 05-gitops: never write a value your controller normalises away (was a Missteps row).
- 06-fun-stuff: a device that accepts writes and does nothing is a handshake problem, and firmware changes under you silently (was spread across two detour sections).
- 08-backup: passing every check proves a backup ran, never that it restores (was the last sentence of a mid-post section, and is the sharpest line in the post).

Two things follow for Phases 4 and 5:

1. **Do not treat the lint WARN block as informational.** `no what-transfers closing section` is currently firing on roughly every tutorial/explanation post in the corpus, including the nine remaining ones. That is a real backlog rendered invisible by severity.
2. **A recap ending is the default failure mode of this blog's house style**, not a per-post slip. `## What We Have Now` was a template. Anything inheriting it needs replacing, not editing.

Em-dash density behaved the same way: warn-severity, over threshold on 03/05/06/08 (17.6 / 19.1 / 11.9 / 16.2 against a threshold of 8) and over threshold on essentially the whole corpus. Brought to 4.5 / 4.2 / 4.6 / 4.9 here by preferring colons and full stops. Almost every remaining dash in these four is in the References list, which is house style, and in the Missteps tables.

<!-- fr:journal kind=finding scope=plan id=01aec0276288 created=2026-07-29T00:09:54 phase=3 state=fixed -->
### 01aec0276288 · finding [fixed] · A verify section can be fully evidenced and still not be a decision procedure — 05-gitops printed statuses and never told the reader how to classify their own (phase 3)

05-gitops's verify section passed the gate, contained four real commands with real pasted output, and was still not a decision procedure. It printed a status histogram (`62 Synced Healthy / 5 OutOfSync Healthy / 1 Synced Suspended / 1 OutOfSync Missing`), explained what each status *can* mean in the abstract, and then stopped. A reader whose own cluster shows `OutOfSync` had no way to determine whether theirs was benign.

This is a distinct failure from the one the plan was written against. The plan's stated worry is a heading with nothing underneath it. This was a heading, with commands underneath it, whose commands were all **observational**. Every one described the system. None discriminated between two states the reader must act on differently. A section can be fully evidenced and still teach nothing actionable, and no structural check will ever catch it, because structurally it is indistinguishable from a good one.

The fix was addition, not rewording. Two commands, both verified live:

    kubectl -n argocd get application root -o json | jq -r \
      '.status.resources[] | select(.status=="OutOfSync") | "\(.kind)/\(.name)"'
    -> Application/gpu-operator, Application/longhorn, Application/sympozium

    argocd app diff root --core
    -> all three differ ONLY by pre/post-delete Helm cleanup finalizers
       that ArgoCD's own machinery added and git never declared

That turns "root is OutOfSync" into "three children differ, by fields the tooling owns, safely ignorable" in about ten seconds, and the same pair on a real drift would show an image tag or a replica count instead.

Three practical notes for anyone reusing this:

1. **`argocd app diff --core` is the right tool from a laptop** and needs no login and no port-forward. Frank's documented `--port-forward --port-forward-namespace argocd` invocation FAILED here (`connection reset by peer` forwarding 8080), which is the known flaky-port-forward gotcha; `--core` sidestepped it entirely.
2. **`--core` reads `argocd-cm` from the kubeconfig context's CURRENT namespace.** Point it elsewhere and it dies with `configmap "argocd-cm" not found`, which reads exactly like a broken ArgoCD install rather than a wrong namespace. Cost several minutes; now documented in the post.
3. **Filter on `.status == "OutOfSync"`, never on `!= "Synced"`.** On `tekton-extras` the negative form returned ~40KB of live PipelineRuns whose status is `null`, burying the two EventListeners that actually differ.

Generalisable test to apply to the remaining nine posts: for each command in an actionable section, ask *"what would I do differently depending on its output?"* If the answer is "nothing", it is documentation, not verification.

<!-- fr:journal kind=discovery scope=plan id=556c05f44ad3 created=2026-07-29T00:10:21 phase=3 -->
### 556c05f44ad3 · discovery · Checked the handed-down claims: RecurringJob->CronJob holds, the Longhorn-1.13 NAS switchback is wrong, the OpenRGB handshake is a hypothesis sold as a finding (phase 3)

Four claims in the handed-down critiques and in the posts themselves were checked rather than accepted. Two held, one was wrong, one was unverifiable and got softened instead. Recording the split because the ratio matters for Phases 4 and 5.

**HELD — `RecurringJob` materialises as a Kubernetes `CronJob`.** The repo asserts this implicitly (`layer-9-backup-stale` is built on `kube_cronjob_status_last_successful_time`) and never proves it. If it were false the alert would be watching nothing at all. Measured live:

    kubectl -n longhorn-system get cronjob
    daily-nas   0 2 * * *   False   0   19h     142d
    weekly-r2   0 3 * * 0   False   0   2d18h   142d

Two RecurringJobs in, two CronJobs out, same names, same cron expressions, 142d old. The alert's join is real. Now stated and shown in the post.

**HELD — `apps/grafana-alerting/manifests/alert-rules-cm.yaml:975-978`** is exactly the DEFERRED comment admitting the substitution. Quoted verbatim rather than paraphrased.

**WRONG — "when NAS support lands in Longhorn 1.13, the default target switches back to NAS".** Nothing switches. The stubbed manifest declares a BackupTarget named `nas`, and Gotcha 2 in the same post establishes that RecurringJobs can only ever use the target named `default`. Uncommenting the stub therefore creates a second idle target and changes nothing. Routing to the NAS requires editing `backup-target-default.yaml` so the target called `default` points at the NFS URL. The post contained the setup for its own contradiction two screens apart and neither half noticed the other.

**UNVERIFIABLE — 06-fun-stuff's unlock handshake.** The post asserted as settled fact that firmware `V3.5.14.0` "requires an unlock handshake before it will apply LED writes". The investigation it cites labels this a *hypothesis* under a heading literally called "Current hypothesis", with the supporting argument that the sibling IT5711 takes a separate OpenRGB code path that got the newer compatibility work. Rewritten as observed (writes accepted, stored, no physical effect, began with the BIOS change) versus inferred (the mechanism), citing the investigation inline. A hypothesis reported as a finding is how a blog becomes a source of confident wrong answers.

Also found while checking it: **the post's link to that investigation was dead.** It pointed at `docs/superpowers/plans/2026-03-09-openrgb-it5701-investigation.md`; the file is at `docs/superpowers/implemented/investigations/2026-03-09--fun--openrgb-it5701-investigation.md`. Nothing in the blog CI checks repo-relative GitHub links, so this would not have surfaced on its own. Worth a Phase 6 thought: the tripwire could cheaply assert that every `github.com/derio-net/frank/blob/main/<path>` link resolves to a file in the working tree.

Unresolved, flagged not fixed: the post says the fans are rainbow; the investigation's "Current State" section says the LEDs are black, replaying the NV-saved colour from before the BIOS update. One of the two is stale. I have no way to observe the physical LEDs from here, so I left both alone rather than guess.

<!-- fr:journal kind=finding scope=plan id=cef05b5a55c7 created=2026-07-29T00:46:13 phase=3 state=fixed -->
### cef05b5a55c7 · finding [fixed] · Seven of eight commit hashes cited in two Missteps tables were fabricated - real commits, wrong rows (phase 3)

The retrofit was supposed to be a prose pass over three already-green posts. Most of the work turned out to be repair, and the highest-yield check was the cheapest one available: paste every cited commit hash into `git show` and read the subject line.

**Seven of the eight commit citations across the two Missteps tables were wrong, and the two tables were wrong in different ways.**

`building/01-introduction` cited `ce2fcd9e` in two unrelated rows (adding Pi edge workers; rewriting bootstrap docs). It is neither: `docs(orch): hermes-agent-shell blog posts + plan archive`, 2026-06-06. `building/00-overview` cited `ce2fcd9e` a third time, for the same bootstrap-rewrite claim, plus `cfb7dd1e`, `39cfcec4` and `bd0415e6` for its other three rows. Checked one by one:

| cited | claim in the row | what the commit actually is |
|---|---|---|
| `ce2fcd9e` (x3) | Pi edge workers / bootstrap rewrite | hermes-agent-shell blog posts, 2026-06-06 |
| `cfb7dd1e` | adopting the 12-layer model | page-derived series-index adoption, 2026-07-04 |
| `39cfcec4` | building/operating split | blog-post auto-append + workflow fix, 2026-07-03 |
| `bd0415e6` | relref-to-draft fix | the blog-craft cutover, 2026-07-03 |

Every one is a real commit in this repo, recent, and plausible at a glance. None is the commit its row describes. That is the signature of hashes written to fill a column rather than looked up, and a `Commit` column is the last place a reader expects to have to verify. Only `46673fde` (the homelab photo) checked out, and its row was cut anyway for being about the post rather than the system.

The real commits exist and took minutes to find: `d7678b9e` (2026-03-21, Phase to Layer convention), `7f5ff73f` plus `fc274975` (2026-03-13, the building/ move and the operating series), `2840cce7` (2026-04-18, the relref fix). Note that last one is a **different** relref bug from the one claimed: a missing `/docs/` prefix, not a draft target. No evidence for the draft-target story exists anywhere in the history, so the row was rewritten around the bug that did happen.

Two rows also failed on substance, not just citation. `01-introduction`'s "Zone D was originally just pc-1, the Raspberry Pis were added months later" is contradicted by `26d7d08f` (2026-03-02), which adds label patches for **all seven nodes in one commit**, four days before the post's own date. And "Management ran on mini-1, Omni and Authentik shared the first control-plane node" has no support anywhere in the repo, and is a chicken-and-egg impossibility for Omni specifically, which has to exist before the node it provisions does.

Three rules fall out, for Phases 4 and 5:

1. **`git show` every hash in a Missteps table before touching anything else.** Thirty seconds per row, and the highest-yield check in this plan so far.
2. **A citation column raises trust faster than it earns it.** Readers discount prose. Nobody discounts a hash.
3. **When you cannot find the real commit, ask whether the row is about the system at all.** Two of the four rows removed here were about the *drafting* of the post rather than the building of the cluster, which is also why no commit fitted them.

<!-- fr:journal kind=finding scope=plan id=a6be9fd74671 created=2026-07-29T00:46:43 phase=3 state=fixed -->
### a6be9fd74671 · finding [fixed] · operating/22 published three broken commands, not one - and the two the brief missed both fail silently (phase 3)

The phase brief flagged one broken command in `operating/22-cicd-platform`. Running the rest of the post found two more, and the two the brief missed are worse, because the flagged one fails loudly and they do not.

**1. `kubectl logs -c step-*` (the flagged one).** `-c` takes a single container name and does not glob. Reproduced live:

    error: container step-* is not valid for pod kid-laptops-main-sync-4ps98-pull-and-push-pod
    out of: step-pull-from-github-push-to-gitea, prepare (init), place-scripts (init)

Bad, but self-announcing: you cannot mistake it for working. Replaced with `--all-containers --prefix`, which is what the reader wanted anyway since a PodSecurity violation can surface in an init container. The post now also shows how to list a pod's step containers first, because their names come from the Task's step names and there is nothing to guess from.

**2. The Verify block's mirror check silently returned nulls.** The published line was unauthenticated, and `tekton-bot/frank` is a private repo, so Gitea answers `404` and `jq` renders that as a tidy object:

    unauthenticated -> {"mirror": null, "updated_at": null}
    with the token  -> {"mirror": true, "updated_at": "2026-07-28T22:10:37Z"}

A missing credential and a deleted mirror produce byte-identical output. Anyone who ran the documented health check on the documented service got a clean-looking answer that proved nothing, forever.

**3. "Trigger a Mirror Sync" returned 401, silently.** It passed the Gitea **admin password** as `Authorization: token`, which wants an API token. Measured, same endpoint, same second:

    admin password as bearer token -> HTTP 401
    tekton-bot API token           -> HTTP 200

And the published invocation used `curl -sf`, so the 401 produced no output at all and only a non-zero exit — indistinguishable from success to anyone not checking `$?`. Fixed by sourcing the token from the `gitea-api-token` Secret in `tekton-pipelines` and printing `%{http_code}`.

The pattern across all three, and the reason this belongs in the plan rather than in a fix commit: **the gate's failure model is a heading with nothing under it, and every one of these is a heading with a command under it.** Two of the three exit 0 or print nothing. Structurally they are indistinguishable from working documentation, and they had been published for months in the one post a reader reaches mid-incident.

Two more things fell out of running the rest of the post:

- `ALLOWED_HOST_LIST` was cited under "Gitea Mirror Not Updating" with the advice to check that it "includes GitHub". It is a `[webhook]` setting governing outbound webhook *targets*; mirror pulls are unaffected by it. So the recovery step pointed at a knob that cannot cause the symptom, in the section a reader lands on when the symptom occurs.
- `CI_AUTHORITY` was documented as still being `github` pending cutover. Live value on the Gitea org is `gitea`, flipped 2026-07-22.

Carry into Phases 4 and 5: **run every command a post already publishes, not only the ones you add.** The brief's list of defects was a floor, not a ceiling, and the defects it missed were exactly the ones that produce no error message.

<!-- fr:journal kind=discovery scope=plan id=40a33e0b5009 created=2026-07-29T00:47:13 phase=3 -->
### 40a33e0b5009 · discovery · A one-directional grep is the half of a boundary check guaranteed to pass - the reverse found four Layer 2 files in the Layer 1 tree (phase 3)

`building/01-introduction` claimed a universal ("Omni never touches workloads. ArgoCD never touches machine config.") and offered as proof a single grep for one string in one direction:

    grep -rn 'zone: ai-compute' patches/ apps/
    -> patches/phase01-node-config/03-labels-gpu-1.yaml:13

Clean, and it has always been clean. It asks whether a *machine fact* leaked into the *workload* tree. It never asks the reverse, and the reverse is where this repo actually leaks. Discriminator: every genuine Omni resource declares a `type:` ending in `.omni.sidero.dev`, so anything in the machine-config tree without that string is either a false positive or a leak.

    git ls-files 'patches/**/*.yaml' | xargs grep -L 'omni.sidero.dev'
    patches/phase02-cilium/cilium-values.yaml
    patches/phase03-longhorn/longhorn-gpu-local-sc.yaml
    patches/phase03-longhorn/longhorn-values.yaml
    patches/phase04-gpu/gpu-operator-values.yaml
    patches/phase13-auth/oidc-apiserver.yaml

One false positive (`oidc-apiserver.yaml` is a raw Talos `cluster:` patch with no Omni envelope, correctly Layer 1). The other four are two Helm values files, a Kubernetes StorageClass and a third Helm values file: Layer 2 artefacts, tracked and non-empty, in the Layer 1 tree. All four have live counterparts under `apps/` (`apps/cilium/values.yaml`, `apps/longhorn/values.yaml`, `apps/longhorn/manifests/gpu-local-sc.yaml`, `apps/gpu-operator/values.yaml`), and `patches/README.md` says as much, so they are archaeology rather than a live violation. Nothing in the repo applies them.

Three notes worth carrying:

1. **The direction you check is the direction you were careful about.** That is the whole trap. A one-directional check is not 50% of a boundary check, it is the half guaranteed to pass, because the string you think to grep for is the one you already policed. The post now runs both and states what each does and does not establish.

2. **`kubectl get nodes -L zone,tier,accelerator` was billed as "the cheapest probe" of the boundary and proves nothing about it.** A hand-typed `kubectl label node` yields byte-identical output, which the post conceded two paragraphs later without noticing it had refuted its own evidence. The command is still worth running: it shows Zone A has no node, which is a real claim. It just cannot distinguish declarative from imperative, and being explicit about that is the difference between evidence and a screenshot.

3. **Dead files rot in place and lie confidently.** `patches/phase03-longhorn/longhorn-values.yaml` documents `helm install --version 1.11.0` against `patches/phase3-longhorn/` — a chart version the cluster left in June (instance-manager heap leak, chart now 1.11.2) and a directory path a zero-padding rename retired. Three wrong facts in one file nobody reads, and a paper dossier still cites its sibling as a live artefact. The post names them rather than deleting them, because deleting was out of scope and the checkable claim is more useful than the tidy one.

<!-- fr:journal kind=discovery scope=plan id=bbf76d4a5593 created=2026-07-29T00:47:42 phase=3 -->
### bbf76d4a5593 · discovery · Documenting a Hugo shortcode trap re-triggered it - and it surfaced as six failures in files I never touched (phase 3)

While rewriting `building/00-overview`'s Missteps table I documented an old Hugo trap: a `relref` without the `/docs/` prefix is not a warning, it is `REF_NOT_FOUND` and a dead build. I wrote the example inside backticks, assuming an inline code span would keep Hugo out of it.

It does not. Hugo evaluates shortcodes inside inline code spans, so the example resolved as a real `relref`, failed exactly as documented, and took the build down:

    ERROR [en] REF_NOT_FOUND: Ref "building/...": ".../00-overview/index.md:133:161": page not found
    ERROR error building site: logged 1 error(s)

The row about the bug caused the bug. Fixed with Hugo's escape form, which the repo already uses in `operating/25-frank-papers`: open with `{{<` + `/*` and close with `*/` + `>}}`.

The part worth recording is not the trap, it is **how it presented**. The educational gate passed the post. The blog build I had already run passed, because I ran it before writing that row. What caught it was `pytest`, and it caught it as **six failures in files I had never touched** — five in `test_series_index_adoption.py` and one in `test_image_optimization_adoption.py`. Both suites build the whole site into a temp dir and then assert on the rendered HTML, so a single unresolvable ref in one post's table cell surfaces as "the series index cards are wrong" and "the build emits no webp". Nothing in those six failure messages names `00-overview`; the cause is two stack frames down, inside a shared `build_site()` helper, in the assertion text rather than the test name.

Same neighbourhood as the earlier finding in this plan about `-l longhornvolume` reporting a catastrophe in the same words as a wrong selector: **the failure message described a plausible different problem.** I very nearly filed all six as pre-existing baseline breakage against `origin/main`, which would have been the reasonable-looking move and would have shipped a broken build.

Two rules:

1. **Run the full `pytest`, not just the blog build, after editing content.** The Hugo build I ran mid-edit was green; the one inside pytest was not, because I had written the offending row between them. Order of operations matters more than which command you run.
2. **When N unrelated-looking tests fail at once, read the assertion body before the test names.** A shared expensive fixture (build the site once, assert many things) converts one root cause into N misleading symptoms by design.

There is also a cheap tripwire available if anyone wants it: the corpus already has a Hugo-build guard, but nothing flags an *unescaped* shortcode inside an inline code span, which is a purely lexical check and the exact shape of this bug.
