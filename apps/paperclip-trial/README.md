# Paperclip trial preparation

This chart is an inactive resource definition. Its default render is empty.
The root chart also defaults to omitting the trial Application. The Application,
when explicitly registered at a reviewed commit, has no automated sync policy.
Its child chart remains disabled.

The enabled chart defines an isolated namespace, two service identities, two
ClusterIP services, empty volumes, and app and database Deployments with zero
replicas. It creates no Secret, RBAC grant, ingress, LoadBalancer, broker, proxy,
or worker. A namespace-wide policy denies all ingress and egress, including DNS
and app-to-database traffic. It has no networking exception.

The app ceiling is two CPUs and 4 GiB with a 10 GiB volume. The database ceiling
is one CPU and 2 GiB with a 5 GiB volume. Pods have no service account token,
host namespace, host volume, added capability, privilege escalation, or writable
root filesystem. Each identity has no role binding.

## Required preparation inputs

Enabling this chart requires qualified app and database images pinned by digest,
their source revisions, existing configuration Secret names, non-root numeric
identities, persistent mount paths, and a storage class. Secret values do not
belong in values files. No existing installation's configuration or credentials
are copied here. Image compatibility with the restricted settings is unproven.

This chart deliberately cannot execute work. A separate reviewed change must
qualify the installed source, native remote adapters, authenticated review, and
resource authorization before starting a replica. That change must supply the
SSH credential and independently verified host key through restricted Secret
references. It must prohibit controller-local execution and auth-cache seeding.

No worker or public route is defined yet. The future route contract uses HTTPS
443 for the authenticated trial API and broker, proxy TCP 3128, and worker SSH
TCP 22. Address pins, selectors, identity protection, endpoint authorization,
IPv6 policy, and exact provider destinations remain required execution inputs.
Container ports 3100 and 5432 are internal and inaccessible under this policy.
No TLS termination or port-443 access is claimed by these ClusterIP services.

Deployment, registration, replica changes, routing, credential creation, and
ArgoCD sync require a later approved execution change. Removing desired state
alone does not prove cleanup because the repository uses manual pruning.

## Local verification

Run `uv run pytest scripts/tests/test_paperclip_trial.py -q` through the
repository's fr-isolation execution bridge. The tests render both charts, compare
the existing root resources with the base commit, and inspect the inert trial
resources. They do not contact a cluster or prove live containment.
