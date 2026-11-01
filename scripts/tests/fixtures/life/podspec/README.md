# Console session pod specs

`<type>.json` are byte-for-byte copies of `derio-net/cluster-update-fr`
`testdata/podspec/<type>.json` (taken at `537f208`): the golden pods its `podSpec`
(`internal/session/launch.go`) builds per upgrade type. `test_life_admission_cel.py` and
`test_life_sessions.py` test the admission policy and every CiliumNetworkPolicy selector
against them; `test_pod_fixtures_are_byte_copies_of_the_consoles_golden_files` re-compares
them whenever the console worktree is present. Re-copy, never edit. The image digests are
the console's placeholders; the tests substitute the configured tailscale digest.
