---
paper: 09-secrets-bootstrap
status: ready
---

## Vendors in scope (≥3, typically 4–6)
- name: Infisical
  positioning: "Self-hosted secret manager — projects/environments/identities model, web UI + API, Helm chart, free for self-hosting."
  primary_url: "https://infisical.com/docs/self-hosting/overview"
- name: External Secrets Operator + SOPS-in-Git
  positioning: "ESO syncs from external stores into native K8s Secrets; SOPS+age encrypts bootstrap secrets in Git for the chicken-and-egg layer."
  primary_url: "https://external-secrets.io/latest/"
- name: HashiCorp Vault
  positioning: "Enterprise-grade secret store — KV, transit, PKI, dynamic credentials, audit log, the most feature-complete option in the space."
  primary_url: "https://developer.hashicorp.com/vault/docs"
- name: Bitnami Sealed Secrets
  positioning: "Encrypt-in-Git, controller-decrypts — asymmetric key pair; encrypted SealedSecret CRs ship in Git, controller materializes Secrets."
  primary_url: "https://github.com/bitnami-labs/sealed-secrets"
- name: AWS Secrets Manager + CSI driver
  positioning: "Cloud-managed secret store mounted into pods via the Secrets Store CSI Driver — no self-hosted server, IAM-gated, auto-rotation."
  primary_url: "https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html"
- name: Plaintext in Git
  positioning: "The null hypothesis — secrets committed as raw .env or values.yaml. The anti-pattern Paper 09 exists to argue against."
  primary_url: "https://12factor.net/config"

## Primary sources (≥5, ≥3 distinct type values)
- title: "External Secrets Operator — ClusterSecretStore API"
  type: vendor-docs
  url: "https://external-secrets.io/latest/api/clustersecretstore/"
  quoted_passages:
    - "The ClusterSecretStore is a cluster scoped SecretStore that can be referenced by all ExternalSecrets from all namespaces."
    - "It defines how the operator authenticates against the secret provider — for Infisical, via universalAuthCredentials referencing a clientId and clientSecret stored in Kubernetes Secrets."
  relevance: "Definitive vendor documentation of the ClusterSecretStore CR Frank actually deploys. Grounds the §3 architecture comparison in ESO's own model and underwrites the §5 description of `apps/infisical/manifests/cluster-secret-store.yaml`."

- title: "Infisical — Self-hosting overview"
  type: vendor-docs
  url: "https://infisical.com/docs/self-hosting/overview"
  quoted_passages:
    - "Infisical is an open-source platform for managing secrets, certificates, and configurations across teams and infrastructure."
    - "You can self-host Infisical on your own infrastructure using Docker, Kubernetes, or any other container-orchestration platform."
  relevance: "Vendor's authoritative statement of Infisical's self-hosting model and the projects/environments/identities architecture. Anchors §3's Infisical diagram and the §5 narrative of why a UI-first secret store earns its operational cost at small homelab scale."

- title: "HashiCorp Vault — Architecture"
  type: paper
  url: "https://developer.hashicorp.com/vault/docs/internals/architecture"
  quoted_passages:
    - "Vault is a complex system that has many different pieces. To help both users and developers of Vault build a mental model of how it works, this page documents the system architecture."
    - "The storage backend is untrusted, and is used only to durably store encrypted data."
  relevance: "Canonical architecture document for the heavyweight in the space. Anchors §2's 'self-hosted · dynamic-credentials' quadrant and the §4 scale claim that Vault's storage-backend-is-untrusted model is what enables the audit-log + transit + PKI feature surface that compliance teams pay for."

- title: "Mozilla SOPS — README and design"
  type: vendor-docs
  url: "https://github.com/getsops/sops"
  quoted_passages:
    - "sops is an editor of encrypted files that supports YAML, JSON, ENV, INI and BINARY formats and encrypts with AWS KMS, GCP KMS, Azure Key Vault, age, and PGP."
    - "Only the values are encrypted, the keys are still readable. That allows you to do diffs that are meaningful and preserve the structure of your file."
  relevance: "Vendor design document for SOPS — the only sane way to ship encrypted bootstrap secrets in Git. Anchors the §3 SOPS-in-Git architecture diagram and the §5 explanation of why `secrets/` is applied out-of-band before Infisical exists."

- title: "Frank — Storage / Secrets / SSA gotcha registry"
  type: postmortem
  url: "https://github.com/derio-net/frank/blob/main/agents/rules/frank-gotchas.md"
  quoted_passages:
    - "SOPS-encrypted secrets must NOT be ArgoCD-managed; apply out-of-band from `secrets/`."
    - "ESO: empty `data: []` is rejected; delete the ExternalSecret if all keys are removed."
    - "`envFrom.secretRef` without `optional: true` blocks rolling updates when the Secret is missing."
  relevance: "Frank's own running incident catalogue, codified as one-liner gotchas with per-topic prose under `docs/runbooks/frank-gotchas/storage-secrets-ssa.md`. Direct evidence for the §5 scar callouts; also the load-bearing claim that every scar in Paper 09 came from a real incident, not a hypothetical."

- title: "Secrets Store CSI Driver — Overview"
  type: vendor-docs
  url: "https://secrets-store-csi-driver.sigs.k8s.io/"
  quoted_passages:
    - "Secrets Store CSI Driver for Kubernetes Secrets — Integrates secrets stores with Kubernetes via a CSI volume."
    - "The Secrets Store CSI Driver secrets-store.csi.k8s.io allows Kubernetes to mount multiple secrets, keys, and certs stored in enterprise-grade external secrets stores into their pods as a volume."
  relevance: "Vendor docs for the CSI-driver alternative to ESO. Anchors the §7 roadmap claim about 'CSI driver vs ESO is the architectural fork to watch' and the §3 architecture diagram for AWS Secrets Manager + CSI."

- title: "External Secrets Operator — GitHub repo"
  type: vendor-docs
  url: "https://github.com/external-secrets/external-secrets"
  quoted_passages:
    - "External Secrets Operator is a Kubernetes operator that integrates external secret management systems like AWS Secrets Manager, HashiCorp Vault, Google Secrets Manager, Azure Key Vault, IBM Cloud Secrets Manager, Akeyless, CyberArk Conjur, Pulumi ESC, and many more."
    - "The operator reads information from external APIs and automatically injects the values into a Kubernetes Secret."
  relevance: "The canonical project repo. Anchors the §2 'ESO + SOPS-in-Git' placement on the landscape and the §3 architecture flow for how ESO sync into native K8s Secret resources is the same regardless of upstream store."

- title: "GitGuardian — The State of Secrets Sprawl 2024"
  type: benchmark
  url: "https://blog.gitguardian.com/the-state-of-secrets-sprawl-2024/"
  quoted_passages:
    - "In 2023, we detected 12.8 million secrets exposed in public GitHub commits — a 28% increase over 2022."
    - "Generic high-entropy strings, generic passwords, and Google API keys remain the top three leak types."
  relevance: "The closest thing to an industry-wide benchmark on the cost of NOT running a secret-store: 12.8M leaks in public Git in one year, the empirical pricetag of 'plaintext in Git'. Anchors §4's scale claim that the rotation-cadence axis flips the ranking when secret count grows past a single human's mental cache, and provides the headline number for §6's argument that the null-hypothesis leaf is not safe at any scale where you ship code from more than one machine."

- title: "KubeCon NA 2022 — The State of Kubernetes Secrets Management"
  type: talk
  url: "https://kccncna2022.sched.com/event/182PB/the-state-of-kubernetes-secrets-management"
  quoted_passages:
    - "There is no single 'right' way to manage secrets in Kubernetes — the right answer depends on whether you trust your cluster API, your storage backend, your CI system, and your operators, and the answer to each is rarely the same."
    - "The trade-off between encrypt-in-Git (Sealed Secrets, SOPS) and sync-from-external-store (ESO, CSI) is fundamentally an axis of where you put the trust boundary."
  relevance: "A community talk that frames the entire space as a trust-boundary decision, which is exactly the framing §6's decision-tree adopts. Cited as the canonical 'there is no single right answer' source — useful when the Paper resists the temptation to declare one vendor universally correct."

## Frank artefacts (≥3, ≥2 distinct kind values)
- kind: yaml
  path_or_url: "apps/infisical/values.yaml"
  date: 2026-03-08
  demonstrates: "Why the Infisical chart's two-source DB_CONNECTION_URI injection bug forced splitting one ArgoCD app into three (`infisical`, `infisical-postgresql`, `infisical-redis`). The chart has no else branch between `postgresql.enabled` and `useExistingPostgresSecret`; both code paths inject the env var. Also documents `kubeSecretRef: infisical-secrets` as the SOPS-bootstrapped Secret reference."

- kind: yaml
  path_or_url: "apps/infisical/manifests/cluster-secret-store.yaml"
  date: 2026-03-08
  demonstrates: "How ESO reaches into Infisical via the projectSlug + environmentSlug + secretsPath triple and `universalAuthCredentials`. The credentials themselves live in a Secret in the external-secrets namespace, which is itself SOPS-bootstrapped — the dependency chain made visible in one CR."

- kind: incident
  path_or_url: "agents/rules/frank-gotchas.md#storage--secrets--ssa"
  date: 2026-03-08
  demonstrates: "ESO admission webhook rejects ExternalSecret CRs with an empty `data: []`. Removing the last key from a values.yaml is not a valid state — the only resolution is to delete the ExternalSecret entirely. ArgoCD doesn't infer this from a values diff and leaves the app stuck OutOfSync."

- kind: incident
  path_or_url: "agents/rules/frank-gotchas.md#storage--secrets--ssa"
  date: 2026-03-12
  demonstrates: "A Deployment that envFroms a Secret which ESO has not yet materialized wedges every rolling update on `CreateContainerConfigError`. Without `optional: true` on the envFrom block, there is no signal except a stuck ReplicaSet. The fix is a one-line annotation per envFrom — easy when you know it, invisible when you don't."

- kind: incident
  path_or_url: "agents/rules/repo-principles.md"
  date: 2026-03-05
  demonstrates: "The SOPS-bootstrap chicken-and-egg itself. Infisical needs an admin password and a DB connection string before it can run; those secrets cannot come from Infisical. The only accepted exception to declarative-everything is SOPS-encrypted secrets in `secrets/`, applied via `sops --decrypt | kubectl apply -f -` BEFORE the secret store exists. Three Secrets, one out-of-band command per cluster rebuild."

- kind: yaml
  path_or_url: "secrets/infisical/infisical-secrets.yaml"
  date: 2026-03-05
  demonstrates: "The SOPS-encrypted bootstrap Secret applied out-of-band. Holds Infisical's `ENCRYPTION_KEY`, `AUTH_SECRET`, SMTP credentials, and `REDIS_URL` — the seed values without which Infisical cannot start and from which everything else downstream is materialized by ESO."

## Diagrams planned
- landscape:
    x_axis: "Cloud managed ↔ Self-hosted"
    y_axis: "Plain KV ↔ Dynamic credentials"
    vendors_plotted: ["Infisical", "ESO + SOPS-in-Git", "HashiCorp Vault", "Sealed Secrets", "AWS Secrets Manager + CSI", "Plaintext in Git"]
- architecture_comparison:
    vendors: ["Infisical + ESO + SOPS-bootstrap", "ESO + SOPS-in-Git (no Infisical)", "HashiCorp Vault", "Sealed Secrets", "AWS Secrets Manager + CSI"]
- decision_tree:
    leaves: 4

## Named gaps (≥1)
- "No apples-to-apples 'bootstrap-cost' benchmark exists in the public literature for self-hosted secret stores. Vendor comparisons cover feature matrices (KV vs PKI vs transit; audit-log retention; rotation cadence) and single-dimension benchmarks (request latency, HA failover time) — but never the bundled cost that determines whether a self-hosted secret store is worth running at small-to-medium scale (3–20 nodes, 10–200 secrets). The bootstrap chicken-and-egg itself is rarely measured: how many out-of-band steps does the operator pay on day one? How many on the day they rotate the root key? Comparisons either skip this entirely or treat it as 'covered by Helm' — which is the value system this Paper exists to contradict."

## Counter-arguments considered (≥1)
- "For a solo developer on one laptop with one cluster and ten secrets, plain SOPS+age in Git with decrypt-on-deploy is the rational choice — why doesn't that win for Frank? Answer: same shape as Paper 04. Frank is a learning platform. The reason to run Infisical + ESO is to encounter the ExternalSecret `data: []` admission rejection, the `envFrom.secretRef` rolling-update wedge, the Infisical chart's two-source DB_CONNECTION_URI bug — first-hand. A team that has internalized these lessons can rationally skip the secret-store layer and keep SOPS+age; a team that has not will reinvent the same scars at production scale. The counter-argument wins for the team that has already paid the tuition; for Frank, paying the tuition is the point."
