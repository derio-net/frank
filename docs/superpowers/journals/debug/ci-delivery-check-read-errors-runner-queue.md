<!-- fr:journal-schema=2 -->
# Journal: ci-delivery-check-read-errors-runner-queue

<!-- fr:journal kind=repro scope=debug id=19731e8daa1d created=2026-10-19T14:48:06+00:00 -->
### 19731e8daa1d · repro · ci-delivery-check errors every run; runner queue 54 jobs / 9h

2026-10-19 after #878/#887 merged: 3 consecutive ci-delivery-check Error pods listing read-error on 9 derio-net/derio-homelab mirrors + ansible-pihole; ci-runner-probe runners_online=1 oldest_waiting_s=32438 waiting=54 while runner CPU ~1m.

<!-- fr:journal kind=root-cause scope=debug id=7d55964061bd created=2026-10-19T14:48:09+00:00 -->
### 7d55964061bd · root-cause · RC1: delivery-check reads Gitea as tekton-bot, which is not a member of derio-net/derio-homelab

Mirrors exist (ci-budget-ops status gitea-mirrors: 0 open). tekton-bot GET /repos/<org>/<repo> -> 404, /orgs/<org> -> 403; ci-budget (Owners) -> 200 on all 9. API.http uses one gitea token (gitea-api-token) for every org. kid-laptops only works because it was granted explicitly. The bare except in check() hides the HTTP code.

<!-- fr:journal kind=root-cause scope=debug id=453e616daabd created=2026-10-19T14:48:12+00:00 -->
### 453e616daabd · root-cause · RC2: derio-homelab/ansible-pihole default branch is picl; check + mirror-reconcile hardcode main

GitHub branches/main -> 404 for ansible-pihole only (others 200); gh api default_branch=picl. ci-delivery-check head() and mirror-reconcile (lines ~137,220) use main; ci-budget-ops resolves default_branch.
