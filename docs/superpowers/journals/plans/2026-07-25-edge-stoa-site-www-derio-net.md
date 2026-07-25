# Journal: 2026-07-25-edge-stoa-site-www-derio-net

<!-- fr:journal kind=finding scope=plan id=r1-inert-race-guard created=2026-07-25T19:32:38 state=fixed -->
### r1-inert-race-guard · finding [fixed] · site-promotion's ordering guard was inert — merge-base ran in the wrong repo

Found in self-review. The pipeline ran 'git merge-base --is-ancestor $OUR_SHA $CURRENT_SHA' inside the FRANK clone, but both shas are agentic-stoa/site commits. Frank's object database has never seen them, so git errors; stderr was discarded with 2>/dev/null, the non-zero exit read as 'not an ancestor', and the guard could never fire — a newer build could be silently overwritten by an older one. Root cause: the loop shape was lifted from the blog workflow, where OUR_SHA and CURRENT_SHA ARE frank shas, so the in-place form is correct there; the sha provenance changed but the code did not. Fixed by resolving ancestry against a bare, blobless, depth-100 clone of agentic-stoa/site using the already-present read-only stoa-github-mirror token (no new credential), with cat-file -e existence checks and a loud WARNING when either sha falls outside the fetched window rather than a silent pass. Test tightened to assert merge-base runs with --git-dir against the site repo, and the credential assertion sharpened from 'stoa token absent' to a per-URL check that frank is cloned with GITHUB_TOKEN and agentic-stoa with STOA_TOKEN.

<!-- fr:journal kind=finding scope=plan id=r2-probe-masked-by-fallback created=2026-07-25T19:32:38 state=fixed -->
### r2-probe-masked-by-fallback · finding [fixed] · Acceptance row overclaimed: handle_errors 200 hides a backend outage from the probe

Found in self-review. www-outage-is-visible claimed the operator is alerted if www 'stops answering'. But the handle_errors fallback answers 200 when the backend is unreachable, so the blackbox probe stays green for a www-backend outage and only catches an edge/Caddy outage. The fallback is still right (before launch it IS the intended state, and a content assertion would page continuously), so the fix is honesty plus a scheduled close: the acceptance note now states the limit explicitly, the spec records the trade-off next to the fallback rationale, and phase 6 gains step P6.T2.S4 to move the www probe to a content-asserting module once the real page ships — with a scale-to-0 verification.

<!-- fr:journal kind=finding scope=plan id=r3-inline-css-vs-csp created=2026-07-25T19:32:38 state=fixed -->
### r3-inline-css-vs-csp · finding [fixed] · Astro's default inline stylesheet would have been blocked by the CSP

Found while building phase 1. Astro inlines small stylesheets by default (build.inlineStylesheets: 'auto'), and the edge CSP is style-src 'self' with no 'unsafe-inline' — the page would have returned a healthy 200 while rendering completely unstyled, invisible to every server-side check. Fixed by setting inlineStylesheets: 'never' rather than weakening the CSP, and asserting both the presence of an external stylesheet and the absence of any <style> block in scripts/check-build.sh.

<!-- fr:journal kind=finding scope=plan id=r4-runbook-diff-churn created=2026-07-25T19:32:38 state=fixed -->
### r4-runbook-diff-churn · finding [fixed] · Runbook sync re-serialised the whole file: 1297-line diff for 5 additions

The sync-runbook procedure sorts by (layer, id), but the live file is grouped by layer WITHOUT being sorted by id inside each group. A faithful sort plus PyYAML re-serialisation produced 683 insertions / 614 deletions for five new entries — burying the change and making it impossible to review that nothing else moved. Reverted and replaced with a textual insertion at the end of each entry's layer group: 69 insertions, 0 deletions. Verified no pre-existing entry lost its status and none were dropped.

<!-- fr:journal kind=discovery scope=plan id=r5-sh-not-bash created=2026-07-25T19:32:38 -->
### r5-sh-not-bash · discovery · Check scripts had to be POSIX sh — the image build stage has no bash

The Dockerfile runs the build checks inside node:22-alpine, which ships no bash. The scripts started as bash with 'set -euo pipefail'. Converted to /bin/sh with 'set -eu' (no pipes, so pipefail was never load-bearing) and rewrote a fragile 'grep -q X && fail' construct as an explicit if/then — under set -e that pattern is only safe because it is not the final command of the list, which is too subtle to leave in place.
