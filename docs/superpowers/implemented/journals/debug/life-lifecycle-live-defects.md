<!-- fr:journal-schema=4 -->
# Journal: life-lifecycle-live-defects

<!-- fr:journal kind=repro scope=debug id=b4d4aa0de36e created=2026-11-13T15:23:31+00:00 -->
### b4d4aa0de36e · repro · tailscale sidecar Init:Error on pods without SA token

cluster-update-fr pod 0/3 Init:Error: 'error initializing kube client ... serviceaccount/namespace: no such file'. Pods run automountServiceAccountToken:false.

<!-- fr:journal kind=root-cause scope=debug id=b5f4d10c7265 created=2026-11-13T15:23:34+00:00 -->
### b5f4d10c7265 · root-cause · containerboot keys kube mode on KUBERNETES_SERVICE_HOST

v1.82.5 cmd/containerboot/settings.go:97 InKubernetes = os.Getenv(KUBERNETES_SERVICE_HOST) != ''; main.go:183 then newKubeClient unconditionally. TS_KUBE_SECRET='' only skips setupKube, not client creation. No documented opt-out; explicit empty container env overrides the kubelet-injected value.

<!-- fr:journal kind=finding scope=debug id=3469a96ca829 created=2026-11-13T15:28:28+00:00 state=fixed -->
### 3469a96ca829 · finding [fixed] · Defect A+B fixed with pinning tests

A: KUBERNETES_SERVICE_HOST='' on tailscale sidecar in cluster-update-fr deployment, hop-scan cronjob, admission policy (+golden hop-os fixture), console launch.go (cluster-update-fr#2). B: life_sessions._destinations keeps host-cluster destinations only (cnc-staging, cnc-staging-db, runs-fr-staging are vCluster-destined); app-roles.yaml regenerated; test_app_namespaces_only_name_apps_that_deploy_to_the_host_cluster. Local suites pass; test_life_admission_cel is CI-only.

<!-- fr:journal kind=review scope=debug id=8ac044205b12 created=2026-11-13T15:34:26+00:00 -->
### 8ac044205b12 · review · Review

Self-reviewed diff; no findings. CEL deny cases unverified locally (CI-only).
