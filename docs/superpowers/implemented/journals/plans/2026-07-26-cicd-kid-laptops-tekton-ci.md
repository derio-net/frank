# Journal: 2026-07-26-cicd-kid-laptops-tekton-ci

<!-- fr:journal kind=finding scope=plan id=f2-cel-substring-not-builtin created=2026-07-26T17:42:07 state=fixed -->
### f2-cel-substring-not-builtin · finding [fixed] · CEL substring() is not a documented Tekton interceptor function

The short-sha overlay used body.after.substring(0,7). substring comes from a cel-go strings extension whose presence in Tekton's CEL interceptor is undocumented; truncate(uint) IS a Tekton builtin and the docs' reference example is literally body.commit.sha.truncate(5). A missing CEL function fails at event time: the webhook 202s, the EventListener logs an eval error, and no PipelineRun appears — indistinguishable from a missing webhook. Switched to truncate(7); tripwire now asserts truncate and rejects substring.

<!-- fr:journal kind=finding scope=plan id=f3-yaml-dump-reformatted-runbook created=2026-07-26T17:42:09 state=fixed -->
### f3-yaml-dump-reformatted-runbook · finding [fixed] · Round-tripping manual-operations.yaml through yaml.safe_dump destroyed it

Appending 5 ops via yaml.safe_load + safe_dump reformatted all 132 existing entries and dropped the file's header comment block: 826 insertions / 384 deletions for what should be a 62-line addition. Reverted and appended as text; re-parsed to confirm validity and unique ids. General rule for this repo's hand-maintained YAML registries.

<!-- fr:journal kind=finding scope=plan id=f4-kid-laptops-test-named-for-vendor created=2026-07-26T17:42:12 state=fixed -->
### f4-kid-laptops-test-named-for-vendor · finding [fixed] · kid-laptops test asserted the vendor name, not the invariant

tests/test_molecule_kubevirt_scenario.py had test_container_disk_image_is_a_variable_with_a_harbor_default asserting 'harbor' in the scenario text. The invariant worth guarding is that a concrete registry default EXISTS and comes from a variable — not who vends it. Renamed to ..._with_a_registry_default and pinned to the Zot coordinate. Also fixed my own new test matching its own docstring in the repo-wide grep.

<!-- fr:journal kind=finding scope=plan id=f5-rewrite-kickstart-delivery created=2026-07-26T17:42:14 state=refuted -->
### f5-rewrite-kickstart-delivery · finding [refuted] · Planned mkksiso -> HTTP-kickstart rewrite: not shipped, deliberately

P4.T1.S4 planned to convert build-containerdisk.sh to packer's HTTP-served kickstart, on the premise that the sibling box template already did it. Investigating found the premise half-wrong: build-vagrant-box.sh indeed never calls mkksiso, but kid-laptops-box.pkr.hcl's comment CLAIMS it does and sets boot_command: [] — so http/ks.cfg is probably not injected there either. Establishing what that template really does requires a 45-minute VM install this session cannot run. Shipping an unverifiable rewrite into another repo is the exact failure mode this run criticised in their request. Corrected the docs, annotated the contradiction, left the mechanism alone.
