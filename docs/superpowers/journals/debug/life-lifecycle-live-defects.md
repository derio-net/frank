<!-- fr:journal-schema=4 -->
# Journal: life-lifecycle-live-defects

<!-- fr:journal kind=repro scope=debug id=b4d4aa0de36e created=2026-11-13T15:23:31+00:00 -->
### b4d4aa0de36e · repro · tailscale sidecar Init:Error on pods without SA token

cluster-update-fr pod 0/3 Init:Error: 'error initializing kube client ... serviceaccount/namespace: no such file'. Pods run automountServiceAccountToken:false.

<!-- fr:journal kind=root-cause scope=debug id=b5f4d10c7265 created=2026-11-13T15:23:34+00:00 -->
### b5f4d10c7265 · root-cause · containerboot keys kube mode on KUBERNETES_SERVICE_HOST

v1.82.5 cmd/containerboot/settings.go:97 InKubernetes = os.Getenv(KUBERNETES_SERVICE_HOST) != ''; main.go:183 then newKubeClient unconditionally. TS_KUBE_SECRET='' only skips setupKube, not client creation. No documented opt-out; explicit empty container env overrides the kubelet-injected value.
