# Journal: pr787-mermaid-width-gate

<!-- fr:journal kind=repro scope=debug id=d54327742c8d created=2026-09-06T22:40:33 -->
### d54327742c8d · repro · PR #787 mermaid width gate: 8 diagrams over 1400px after reader experience

CI blog-validate on feat/blog-reader-agent-experience@065785b5 fails the mermaid width gate on 8/186 diagrams (main@c14577c: widest 1367px). Repro: fr isolation exec -- (cd blog && hugo --minify); CHROME_BIN=<host Chrome> node blog/scripts/validate_mermaid_layout.mjs --public blog/public --max-width 1400 -> 7 over on macOS (operating/11-public-edge 2206px, 24-ruflo 1896px, 17-ingress 1527, 14-secure-agent-pod 1486, 13-workflow-automation 1456, papers/05 #4 1418, papers/09 #4 1422). Container has no Chrome; gate runs on host against the shared worktree build.

<!-- fr:journal kind=ruled-out scope=debug id=a3c14192f50b created=2026-09-06T22:44:53 -->
### a3c14192f50b · ruled-out · Ruled out: reader.css font-size inflating mermaid labels

validate_mermaid_layout.mjs renders each extracted <pre class=mermaid> source in a bare harness page containing only the site's mermaid bundle (no site CSS, no page), so reader.css cannot affect measured width. Extracted source for operating/11-public-edge #1 is byte-identical between live main and the PR build.

<!-- fr:journal kind=root-cause scope=debug id=c6595c90c5cf created=2026-09-06T22:44:55 -->
### c6595c90c5cf · root-cause · Root cause: hextra fetches mermaid@latest at build time; 11.17.x widened 8 diagrams

Hextra v0.12.3 layouts/_partials/scripts/mermaid.html defaults $mermaidBase to https://cdn.jsdelivr.net/npm/mermaid@latest/dist and resources.GetRemote's it at build time; go.mod pins hextra, not mermaid. Main's last blog-ci run (2026-08-15) got 11.16.1; mermaid 11.17.0 shipped 2026-08-19 (11.17.2 on 08-25), and the PR build got 11.17.2. Controlled swap: PR build's public/ with the 11.16.1 bundle copied over the 11.17.2 file -> MERMAID LAYOUT OK, 186/186, widest 1363px. Not caused by the PR; any blog/** push to main fails identically today.

<!-- fr:journal kind=finding scope=debug id=45d7dcdc573e created=2026-09-06T22:51:11 state=fixed -->
### 45d7dcdc573e · finding [fixed] · Fixed: pin mermaid to 11.16.1 via params.mermaid.base; tripwire guards the pin

blog/hugo.toml gains [params.mermaid] base = https://cdn.jsdelivr.net/npm/mermaid@11.16.1/dist (Hextra's documented knob). Failing test first: scripts/tests/test_mermaid_bundle_pinned.py asserts the base pins an exact X.Y.Z release. After the pin the rebuilt bundle hash equals live main's (mermaid.min.18327bef…, version 11.16.1) and the gate reports 186/186 within 1400px, widest 1363px. Tripwire fixture separately repointed from blog-craft-5dc31f8 to blog-craft-362e2be (the PR's pinned upstream), since the srcset-clamp fix landed upstream and opt-image.html is byte-identical again.
