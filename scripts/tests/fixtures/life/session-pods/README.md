# Console session pod shapes

`<type>.json` is the pod `derio-net/cluster-update-fr` builds for each upgrade type
(`internal/session/launch.go` `podSpec`), used by `test_life_admission_cel.py` and
`test_life_sessions.py` so the admission policy and the network policies are tested against
the console's real pods, not shapes assumed here.

Dumped from cluster-update-fr `9604a52` by a throwaway test calling `podSpec` with every
credential key of the type present; the session and tailscale images are placeholders
(the tests substitute the configured values). These are a stop-gap: replace them with the
console's own golden files (`testdata/podspec/<type>.json`) once that repo publishes them
(journal p5-r1-fixtures).
