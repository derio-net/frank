# Journal: 2026-08-02--edge--litellm-mesh-dns

<!-- fr:journal kind=discovery scope=plan id=acl-yaml-is-hujson created=2026-08-02T17:22:13 phase=1 -->
### acl-yaml-is-hujson · discovery · ConfigMap key acl.yaml is HuJSON, not YAML — it parses with neither yaml.safe_load nor json.loads (phase 1)

The plan step P1.T2.S1 verification asked for "acl parses: True" via yaml.safe_load(cm["data"]["acl.yaml"]). That raises ParserError — and it does so on HEAD too, before any edit of mine, so it is pre-existing and not caused by the litellm-lb record. Reason: despite the .yaml key name, that blob is Headscale POLICY, which is HuJSON (JSON with // comments). yaml.safe_load fails with "while parsing a flow mapping ... expected comma or brace, but got colon" at the "// Allow all traffic" line; json.loads fails with "Expecting property name enclosed in double quotes" at the same comment. It parses cleanly as JSON only after stripping ^\s*// lines. Consequence for later phases: do NOT add an "acl still parses" guard using either stock loader — it will look like the edit broke the file when nothing did. If an ACL guard is ever wanted, strip // comments first (or use a HuJSON parser). The extra_records half of that step verified fine: exactly four records printed (headplane, entry, gitea-ssh, litellm-lb) and the list is still a list of mappings.

<!-- fr:journal kind=discovery scope=plan id=phase1-green-baseline created=2026-08-02T17:22:26 phase=1 -->
### phase1-green-baseline · discovery · Phase 1 green: 372 passed / 1 xfailed (baseline 369 + 3 new) (phase 1)

RED run of scripts/tests/test_headscale_litellm_mesh_dns.py was 1 failed / 2 passed — only test_litellm_lb_record_present failed, on the missing {name: litellm-lb.cluster.derio.net, type: A, value: 192.168.55.206}; the gitea-ssh regression guard and the magic_dns guard were already green, which is the point (they guard what must NOT change). After adding the record the file is 3 passed. Full suite 372 passed, 1 xfailed in 65s — exactly the 369+1 baseline plus my three tests, no regressions. Phase 2 note: the file remains hand-edited embedded YAML with the litellm-api record still to be added under the same extra_records list; the test module already exposes a reusable _extra_records() helper that asserts list-of-mappings shape, so a Phase 2 guard should extend that module rather than re-derive the double-safe_load.

<!-- fr:journal kind=finding scope=plan id=no-fr-acceptance-set created=2026-08-02T17:23:48 phase=1 state=fixed -->
### no-fr-acceptance-set · finding [fixed] · Phase 3 step references `fr acceptance set`, which does not exist in this fr build (phase 1)

**RESOLVED by the orchestrator, 2026-08-02.** The open question here — does
`fr acceptance add` upsert or duplicate an existing id? — was answered by
running it: it **errors** with `duplicate row id:
litellm-reachable-from-mesh-by-name`. It is append-only, so there is no CLI
path to flip a row's status at all. P3.T1.S2 now directs a hand-edit of
`docs/acceptance/matrix.yaml` (the documented exception to "agents never
hand-edit YAML shapes"), then `fr acceptance report --deterministic` and
`fr acceptance check` in that order, with the expected `exit 1` / 13
pre-existing staleness errors stated up front so a red gate is not mistaken
for a broken edit.

P3.T1.S2 instructs: "flip litellm-reachable-from-mesh-by-name to skipped with the evidence, via `fr acceptance set`". There is no such subcommand — `fr acceptance` offers check / report / status / summary / add / init / backfill / digest only, and `fr acceptance set --help` errors with "No such command set". The nearest tool is `fr acceptance add` (--id --capability --acceptance --status --notes --level --origin), documented as "append a schema-validated row"; whether re-adding an existing id upserts the row or duplicates it is UNVERIFIED and Phase 3 should check before running it blind. Separately, `fr plan edit --complete-phase 1` warns that phase 1 acceptance rows are still not-implemented — that is EXPECTED and needs no action in Phase 1: the row is shared by all three phases, it can only be proven after the headscale rollout restart (manual-op edge-headscale-litellm-mesh-dns-restart), and its existing matrix note already records exactly that.

<!-- fr:journal kind=finding scope=plan id=plan-acl-hujson created=2026-08-02T17:26:08 phase=1 state=fixed -->
### plan-acl-hujson · finding [fixed] · Plan step P1.T2.S1 told the executor to yaml-parse a HuJSON file (phase 1)

My verification snippet ended with yaml.safe_load(cm['data']['acl.yaml']) and expected 'acl parses: True'. That value is Headscale POLICY in HuJSON (JSON with // comments) despite the .yaml key name; it loads with neither yaml.safe_load nor json.loads, only as JSON after stripping ^\\s*// lines. It raises ParserError on unmodified HEAD too, so the snippet would have reported a pre-existing condition as though the edit under test had corrupted the ConfigMap — the worst kind of false positive, appearing at exactly the moment someone is checking whether they broke something. FIXED: snippet trimmed to the extra_records assertion it was actually for, with an explicit warning not to add a stock-loader guard on acl.yaml.

<!-- fr:journal kind=finding scope=plan id=plan-no-acceptance-set created=2026-08-02T17:26:10 phase=3 state=fixed -->
### plan-no-acceptance-set · finding [fixed] · Plan step P3.T1.S2 instructed a CLI verb that does not exist (phase 3)

P3.T1.S2 told the operator to flip litellm-reachable-from-mesh-by-name 'via fr acceptance set'. Verified: no such subcommand in fr 3.15 (surface is check/report/status/summary/add/init/backfill/digest), and 'fr acceptance add' is append-only — re-adding the id errors 'duplicate row id', it does not upsert. The operator would have hit this at the very end of the run, post-merge, with no documented alternative. FIXED: step now says to hand-edit docs/acceptance/matrix.yaml (status not-implemented -> skipped, notes replaced with observed evidence) and validate with 'fr acceptance check'. Worth noting the general lesson: I wrote a plausible-sounding CLI invocation without running it, in the one phase no agent would execute before the operator does.

<!-- fr:journal kind=discovery scope=plan id=p2-guards-mutation-tested created=2026-08-02T17:32:00 phase=2 -->
### p2-guards-mutation-tested · discovery · Both SSO-invariant guards mutation-tested; only one could ever have gone red naturally (phase 2)

The phase's headline assertions are deliberately opposite-facing, and that asymmetry has a consequence TDD alone does not cover: test_litellm_api_route_has_no_forward_auth went red naturally (no route existed -> 6 failed, 5 passed on the RED run), but test_litellm_public_route_still_has_forward_auth PASSED from the very first run, because it guards a property that is already true on HEAD. A regression guard that has never been observed failing is indistinguishable from a tautology (e.g. a typo'd middleware name, or a helper returning [] and 'not in []' trivially holding). So both were mutation-tested before commit: (a) stripping authentik-forwardauth from the PUBLIC litellm route -> exactly 1 failed (test_litellm_public_route_still_has_forward_auth), 10 passed; (b) adding authentik-forwardauth to the new litellm-api route -> exactly 1 failed (test_litellm_api_route_has_no_forward_auth), 10 passed. Each mutation failed exactly one test and no others, which also proves the two are independent rather than coupled through the shared _route_for_host helper. Original file restored from a backup copy and re-verified 11 passed; git diff --stat confirms no mutation residue.

<!-- fr:journal kind=discovery scope=plan id=p2-directory-mode-uniqueness created=2026-08-02T17:32:30 phase=2 -->
### p2-directory-mode-uniqueness · discovery · Directory-mode collision check promoted from a one-shot snippet into a standing test (phase 2)

P2.T2.S1 specified an inline python snippet asserting no duplicate IngressRoute metadata.name (apps/traefik/manifests/ has no kustomization.yaml, so ArgoCD applies every document as-is and a duplicate name is a live overwrite, not a build error). Ran as specified: 34 IngressRoutes, all uniquely named. But a snippet that runs once in one phase guards nothing afterwards, and this file is exactly the kind that grows by copy-paste — this phase added the 34th route by copying the 'litellm' one. So the check was also encoded as test_ingressroute_names_are_unique in the plan's own test module, where it runs on every suite. Additionally checked (not required by the step, same failure class): duplicate route MATCH rules, i.e. two differently-named IngressRoutes claiming the same Host() — none. That is arguably the sharper hazard here, since two routes for one host collide in Traefik's router rather than in the API server, and unique metadata.names would not catch it; _route_for_host asserts exactly-one-hit and so covers it for the two litellm hosts specifically.

<!-- fr:journal kind=discovery scope=plan id=p2-green-baseline created=2026-08-02T17:32:40 phase=2 -->
### p2-green-baseline · discovery · Phase 2 green: 380 passed / 1 xfailed (372 + 8 new) (phase 2)

RED run of scripts/tests/test_headscale_litellm_mesh_dns.py after adding the phase-2 assertions: 6 failed, 5 passed. The 6 failures were the missing litellm-api extra_record plus five route assertions all bottoming out in _route_for_host ('expected exactly one route matching Host(litellm-api.cluster.derio.net); found 0'). The 5 that passed were the three phase-1 tests plus the two new must-not-change guards. After both edits the file is 11 passed. Full suite 380 passed, 1 xfailed in 63s — exactly the phase-1 baseline of 372+1 plus my 8 new tests, no regressions. Note the count arithmetic is the check that matters: 8 tests added, 8 more passing, so nothing elsewhere was silently broken or silently skipped.

<!-- fr:journal kind=finding scope=plan id=lan-wildcard-makes-verify-vacuous created=2026-08-02T17:33:36 phase=3 state=fixed -->
### lan-wildcard-makes-verify-vacuous · finding [fixed] · A LAN *.cluster.derio.net wildcard makes the Phase 3 verify for litellm-api a false positive (phase 3)

**RESOLVED by the orchestrator, 2026-08-02.** Confirmed independently and found
slightly sharper than reported. Fixed in three places — the spec's Test Plan
step 3, the `# manual-operation` verify block, and `03.yaml` — by leaning the
proof on `litellm-lb -> 192.168.55.206`, which differs from the wildcard and so
can only have come from MagicDNS. Two controls now sit beside it in the runnable
block: `nope-xyz` (negative — shows what the wildcard says) and `gitea-ssh ->
.209` (positive — proves MagicDNS is answering at all and outranks the
wildcard). Since both records ride one ConfigMap and one restart, proving `-lb`
proves both. The converse observation was captured too: because the wildcard
already points `litellm-api` at Traefik, the *route* can be curl-verified from
the LAN before the restart, decoupling "is the route right" from "did the DNS
land". Also added a resolver-cache flush, since the pre-deployment lookups
recorded below are exactly what mDNSResponder would otherwise replay.

Measured read-only from the operator's Mac (LAN, no cluster mutation): litellm.cluster.derio.net -> 192.168.55.220, gitea-ssh.cluster.derio.net -> 192.168.55.209, litellm-api.cluster.derio.net -> 192.168.55.220 ALREADY (before any headscale restart), and the control nonexistent-xyz.cluster.derio.net -> 192.168.55.220 too. That control is the proof: homelab DNS serves a WILDCARD *.cluster.derio.net -> 192.168.55.220 (the Traefik LB), so every unknown name under the zone answers .220.

Two consequences.

(1) The manual-op verify block in the spec (edge-headscale-litellm-mesh-dns-restart) tells the operator to run 'dscacheutil -q host -a name litellm-api.cluster.derio.net # -> 192.168.55.220'. On the Mac, and on any LAN client, that check PASSES IDENTICALLY WITH AN EMPTY extra_records — it is measuring the LAN wildcard, not the Headscale record. It is a vacuous check that will report success whether or not the phase-3 rollout restart actually took effect, which is the exact moment it is being run, by an operator who is about to travel and lose the ability to retest. Note the asymmetry: the sibling check for litellm-lb -> 192.168.55.206 is NOT vacuous, because the wildcard answers .220, so a .206 answer can only have come from the extra_record. Only the -api line is affected, which is why this is easy to miss — half the verify block is sound.

(2) Suggested fix, cheap: run the -api check from a genuine off-LAN mesh node (a laptop on a foreign network, or hop-1), not from the Mac on the LAN, AND include the negative control alongside it — nonexistent-xyz.cluster.derio.net must NOT resolve to .220 on that path. If it does, the answer is coming from a wildcard resolver and the record is unproven either way.

Upside worth recording: the same wildcard means the new IngressRoute is verifiable from the LAN the moment the PR merges and ArgoCD syncs, with NO headscale restart involved — 'curl -H "Authorization: Bearer <key>" https://litellm-api.cluster.derio.net/v1/models' from the LAN exercises the Traefik route, the wildcard cert and the middleware chain (i.e. proves the no-forward-auth behaviour end-to-end, a 200 rather than a 302) independently of phase 3. That decouples 'is the route right' from 'did the DNS rollout land', which are the two things this plan otherwise conflates. Did not run it: needs a virtual key and is deployment verification, which is phase 3 and operator-owned.

<!-- fr:journal kind=discovery scope=plan id=p2-acceptance-row-ci created=2026-08-02T17:37:59 phase=2 -->
### p2-acceptance-row-ci · discovery · litellm-public-host-keeps-sso flipped not-implemented -> ci; scripts/tests DOES run on every PR (phase 2)

fr plan edit --complete-phase 2 warned that both acceptance rows were still not-implemented. One of them is now genuinely satisfied and was flipped; the other correctly stays.

litellm-public-host-keeps-sso -> status 'ci', levels.unit citing the three route guards (test_headscale_litellm_mesh_dns.py L143 no-forward-auth, L156 keeps ip-allowlist+security-headers, L167 public route retains forward-auth). 'ci' rather than 'skipped' because .github/workflows/repo-tripwires.yml runs 'pytest scripts/tests/ -q' on 'on: pull_request' with NO paths filter (deliberately — its own comment says a filter narrow enough to be meaningful would be wrong more often than it saved minutes). Worth stating explicitly because the older repo lore that 'no CI runs scripts/tests/' is now obsolete; that was true when the crowdsec guards were written and repo-tripwires.yml postdates it. Note the matrix schema has no 'implemented' status at all — the vocabulary is ci|scheduled|skipped|not-implemented|failing, i.e. status records HOW it is verified, not whether the code exists.

litellm-reachable-from-mesh-by-name stays not-implemented, as phase 1 predicted: it can only be proven after the phase-3 headscale rollout restart, and its notes already say so.

Two mechanical traps for anyone editing this matrix. (1) 'fr acceptance add' is append-only and cannot flip an existing row (phase-1 finding plan-no-acceptance-set) — the row must be hand-edited, which is what was done. (2) Editing matrix.yaml WITHOUT regenerating the reports makes 'fr acceptance check' fail with three 'report drift' errors on report_local.html / report_linked.html / report_linked.md. Baseline on HEAD is 13 ERRORs, all pre-existing spec-staleness on unrelated archived specs, and 0 report-drift; after the edit it was 13+3, and after 'fr acceptance report --deterministic' it is back to exactly 13 with 0 drift. The baseline was measured by stashing rather than assumed, because 13 pre-existing errors is otherwise an excellent place to hide a 14th.

<!-- fr:journal kind=finding scope=plan id=lan-wildcard-vacuous-verify created=2026-08-02T17:41:02 phase=3 state=fixed -->
### lan-wildcard-vacuous-verify · finding [fixed] · Half the Phase 3 DNS verification was vacuous — homelab wildcard answers .220 for everything (phase 3)

Surfaced by the Phase 2 executor, then verified directly. Homelab DNS (192.168.10.11) serves a wildcard *.cluster.derio.net -> 192.168.55.220: the impossible names nope-xyz and definitely-not-a-service both resolve to .220. Consequence: my manual-op verify block and Test Plan step 3 asserted 'litellm-api -> 192.168.55.220', which passes IDENTICALLY with an empty extra_records list. The operator would have run it immediately before travelling, seen it pass, and concluded the DNS was live when nothing had been proven. FIXED in both the spec and 03.yaml. The corrected check leans on litellm-lb -> 192.168.55.206, which discriminates because .206 differs from the wildcard, plus an explicit nope-xyz negative control so the wildcard is visible rather than assumed; since both records ride one ConfigMap and one restart, proving -lb proves both. Pre-deployment baseline recorded for comparison (all four names .220 today, while gitea-ssh already answers .209 — which is itself the proof that MagicDNS outranks the wildcard on a mesh node). Also captured the useful converse the executor spotted: the LAN wildcard means the Traefik route can be curl-verified from the LAN BEFORE the restart, decoupling 'is the route right' from 'did the DNS land'.

<!-- fr:journal kind=review scope=plan id=mutation-verified-independently created=2026-08-02T17:44:23 -->
### mutation-verified-independently · review · Security invariant mutation-tested independently of the implementing agent

The Phase 2 executor reported mutation-testing both SSO guards. Verified independently rather than accepted, in a detached git worktree at HEAD so the concurrent reviewer's tree was untouched. Control: 11 passed. Three mutations, each hitting exactly ONE test and no others (proving they are not coupled through the shared _routes()/_extra_records() helpers): (1) stripping authentik-forwardauth from the PUBLIC litellm route -> only test_litellm_public_route_still_has_forward_auth failed; (2) adding authentik-forwardauth TO litellm-api -> only test_litellm_api_route_has_no_forward_auth failed; (3) dropping the pre-existing gitea-ssh extra_record -> only test_gitea_ssh_record_still_present failed. Tree restored and re-verified at 11 passed, mutation worktree removed. The guards discriminate; they are not tautologies that merely pass on HEAD.

<!-- fr:journal kind=finding scope=plan id=rev-c1-unauthenticated-evidence created=2026-08-02T18:06:46 phase=3 state=fixed -->
### rev-c1-unauthenticated-evidence · finding [fixed] · CRITICAL: phase 3 flipped an acceptance row on evidence that never authenticated (phase 3)

Review finding. The row claims an AUTHENTICATED API response, but the runnable command block held only two DNS lookups and three unauthenticated curls. Every one passes against a LiteLLM that rejects every key in existence — 401 is exactly what an unauthenticated request should get — so the operator could have flipped the row to proven, boarded the plane, and left the laptops getting 401s behind a green matrix. Corroborated by both kid-laptops keys showing spend=0.0: neither has ever completed a request, so nothing had ever exercised the auth path end to end. FIXED twice over: (a) the authenticated curl (200 + model list) is now in the block, marked LOAD-BEARING, with an explicit do-not-flip-without-it; (b) the row was itself over-scoped — it claimed a device 'on any foreign network', which frank cannot verify and which duplicates derio-homelab/kid-laptops' laptop-reaches-frank-from-anywhere. Narrowed to what frank delivers, with the scope correction recorded in the row notes rather than made silently.

<!-- fr:journal kind=finding scope=plan id=rev-i2-configmap-freshness-gate created=2026-08-02T18:06:47 phase=3 state=fixed -->
### rev-i2-configmap-freshness-gate · finding [fixed] · IMPORTANT: nothing gated the restart on the ConfigMap being fresh (phase 3)

The step printed ArgoCD's sync status then restarted regardless — no wait, no assertion on content. Restarting before ArgoCD reconciles re-reads the OLD ConfigMap, and the symptom is indistinguishable from a failed restart, so the operator restarts again, still stale, and loops. Sharp irony: this plan exists BECAUSE Synced-does-not-imply-serving is the repo's most-repeated bug, and the one manual phase never checked the thing it warns about. FIXED: the gate is now a grep against live ConfigMap content, explicitly NOT the ArgoCD status — which on this cluster can itself mean 'synced to a stale revision'. Includes a force-sync patch for when it lags.

<!-- fr:journal kind=finding scope=plan id=rev-i3-acceptance-check-exits-1 created=2026-08-02T18:06:49 phase=3 state=fixed -->
### rev-i3-acceptance-check-exits-1 · finding [fixed] · IMPORTANT: the prescribed validation command already exits 1 on this branch (phase 3)

Phase 3 closed with 'validate the edit with fr acceptance check'. Measured: exit 1, 13 pre-existing staleness errors about unrelated archived specs, none concerning this spec. Post-merge under time pressure the operator sees red and either reverts a correct edit or spends their last hour chasing someone else's backlog. FIXED: the step states the baseline outright (exit 1, 13 staleness, 0 drift — re-measured after my own matrix edit, still exactly 13/0) and orders 'fr acceptance report --deterministic' BEFORE the check, since a hand-edit otherwise adds three fresh drift errors on top.

<!-- fr:journal kind=finding scope=plan id=rev-i4-manual-op-missing-from-runbook created=2026-08-02T18:06:50 phase=3 state=fixed -->
### rev-i4-manual-op-missing-from-runbook · finding [fixed] · IMPORTANT: the manual operation was invisible to /sync-runbook (phase 3)

The manual-operation block lived only in the spec. sync-runbook scans docs/superpowers/plans/, so it would never be picked up, and manual-operations.yaml — the documented single source for pending manual ops — had no headscale entry. An operator consulting the runbook post-merge would see nothing owed. FIXED: block moved into 03.yaml where the scanner looks, converted to the runbook's list-form commands/verify so a future sync is idempotent, and merged into manual-operations.yaml (141 -> 142) at its correct sorted position by textual splice, leaving the other 141 byte-identical. Found while doing it: my first draft of the block DID NOT PARSE — wrapped list items whose continuation lines began with '|' read as YAML block-scalar indicators, which would have broken the scanner silently. Noted but NOT fixed (pre-existing, out of scope): cicd-stoa-site-first-promotion is mislabelled layer: edge.

<!-- fr:journal kind=finding scope=plan id=rev-i5-entrypoints-unasserted created=2026-08-02T18:06:52 phase=3 state=fixed -->
### rev-i5-entrypoints-unasserted · finding [fixed] · IMPORTANT: entryPoints unasserted — a broken tree passed all 11 tests (phase 3)

No test referenced entryPoints or kind: Rule. Setting entryPoints: [web] — a plausible copy-paste from a non-TLS route — passes every existing test: tls block still correct, middlewares correct, backend correct. Live, Traefik has no :443 router for the host, so https falls through to the default cert and 404s while CI stays green. FIXED: added test_litellm_api_route_serves_on_websecure, mutation-verified rather than assumed (flipping entryPoints to ['web'] fails exactly that one test: 1 failed, 12 passed).

<!-- fr:journal kind=finding scope=plan id=rev-minors-verification-ergonomics created=2026-08-02T18:07:21 phase=3 state=fixed -->
### rev-minors-verification-ergonomics · finding [fixed] · MINOR (6,7,8): the DNS check could fail for three different reasons and said only one (phase 3)

Three review minors, all one failure mode: the verification could not tell the operator WHICH thing broke. (6) No resolver-cache flush — the operator had already looked these names up pre-deployment and got the wildcard's .220, and mDNSResponder caches it, so a correct restart could still read .220 and the step called that categorically 'the restart did NOT take effect'. (7) The gitea-ssh positive control was mentioned in prose but absent from the runnable block, though it is the one line that distinguishes 'not on the tailnet' from 'restart failed'. (8) 'curl -s' hid the very TLS error the step told the operator to look for — a cert failure prints a bare 000 with no diagnostic. FIXED: flush + tailscale-status precondition added, gitea-ssh promoted into the block as an explicit POSITIVE CONTROL beside the nope-xyz NEGATIVE CONTROL, and -s changed to -sS. The three lookups now separate the failure modes explicitly: gitea-ssh=.220 means you are off the tailnet; gitea-ssh=.209 with litellm-lb=.220 means the restart did not land; litellm-lb=.206 means live.

<!-- fr:journal kind=finding scope=plan id=rev-m9-security-claim-overstated created=2026-08-02T18:07:23 phase=3 state=fixed -->
### rev-m9-security-claim-overstated · finding [fixed] · MINOR (9): 'grants no new network access. None.' was stronger than the evidence (phase 3)

True for mesh nodes, and measured. But before this change nothing matched Host(litellm-api.cluster.derio.net), so the name 404'd; after it, any source inside ip-allowlist's RFC1918 ranges that can reach Traefik gets an SSO-free L7 path to the LiteLLM API held only by the Bearer key. For anything that could already reach the LB on :4000 the delta is nil — but which hosts those are is decided by Omada inter-VLAN policy, outside this repo and unverifiable from here. Saying 'None' claimed knowledge this repo does not have. FIXED in both spec and prose: the claim is now qualified to mesh nodes, with the LAN delta stated explicitly and its unquantifiability named.

<!-- fr:journal kind=finding scope=plan id=rev-m10-lb-plaintext-bearer created=2026-08-02T18:07:24 phase=3 state=fixed -->
### rev-m10-lb-plaintext-bearer · finding [fixed] · MINOR (10): litellm-lb normalises plaintext Bearer transport, undocumented (phase 3)

Mesh-to-argonath is WireGuard-encrypted, but argonath-to-192.168.55.206:4000 crosses VLAN55 as cleartext HTTP carrying the API key. The spec discussed litellm-lb purely as a resilience fallback and never mentioned this, which matters more than it would otherwise because the record is permanent rather than temporary. FIXED: stated in the spec, along with why litellm-api (not -lb) is the endpoint the laptops are meant to settle on — -lb is break-glass.

<!-- fr:journal kind=finding scope=plan id=rev-m11-guard-gaps created=2026-08-02T18:07:26 phase=3 state=fixed -->
### rev-m11-guard-gaps · finding [fixed] · MINOR (11): duplicate-name guards had two small holes (phase 3)

No assertion that extra_records names are unique — a duplicated litellm-lb entry with a different value would pass every test, and Headscale would serve one of them arbitrarily. And test_ingressroute_names_are_unique keyed on name alone, ignoring namespace, so it would false-positive on a same-named route legitimately added in another namespace. FIXED: added test_extra_record_names_are_unique; re-keyed the IngressRoute uniqueness check on (namespace, name), which is the actual uniqueness scope of a namespaced object. Neither was violated today.

<!-- fr:journal kind=finding scope=plan id=rev-m12-doc-drift-raspi-argonath created=2026-08-02T18:07:28 phase=3 state=fixed -->
### rev-m12-doc-drift-raspi-argonath · finding [fixed] · MINOR (12): raspi-vlan10 vs argonath naming drift three lines apart (phase 3)

The pre-existing gitea-ssh comment credited the 'raspi-vlan10 subnet routers' while my two new comments said 'argonath', in the same block. Both name the same routes; the Pi routers were replaced by the argonath VLAN10 nodes and the old comment was never updated. Left as-is it reads like two different mechanisms. FIXED: updated to argonath-{e,w} with a parenthetical recording the rename, so anyone who remembers the Pi names can still follow it.
