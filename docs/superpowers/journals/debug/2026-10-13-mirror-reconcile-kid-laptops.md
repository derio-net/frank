<!-- fr:journal-schema=2 -->
# Journal: 2026-10-13-mirror-reconcile-kid-laptops

<!-- fr:journal kind=root-cause scope=debug id=5e04492bd47d created=2026-10-13T21:50:19+00:00 -->
### 5e04492bd47d · root-cause · mirror-reconcile never covered derio-homelab/kid-laptops

Built in #851 against the agentic-stoa-main-sync trigger only; kid-laptops has its own trigger (derio-homelab-kid-laptops-main-sync, different GitHub App + webhook secret). The guard test derived its expected list from that one trigger, so it passed while a sibling was uncovered. Also: the job used one GITHUB_TOKEN (agentic-stoa App), which 404s on derio-homelab private repos, so adding the repo to the list alone would have failed every run.
