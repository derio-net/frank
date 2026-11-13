<!-- fr:journal-schema=4 -->
# Journal: life-lifecycle-live-defects

<!-- fr:journal kind=repro scope=debug id=b4d4aa0de36e created=2026-11-13T15:23:31+00:00 -->
### b4d4aa0de36e · repro · tailscale sidecar Init:Error on pods without SA token

cluster-update-fr pod 0/3 Init:Error: 'error initializing kube client ... serviceaccount/namespace: no such file'. Pods run automountServiceAccountToken:false.
