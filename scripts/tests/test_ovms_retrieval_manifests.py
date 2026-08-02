"""Tripwires for the ovms-retrieval manifests — Frank's first DRA consumer.

Contract source of truth:
docs/superpowers/specs/2026-08-02--infer--igpu-embedding-rerank-design.md
("Verified state of the cluster", "The ResourceClaim", "Model acquisition",
"Health probes", "Resource ceiling", "Placement", "Security context",
"Routing: in-cluster only")

This app serves an embeddings model and a cross-encoder rerank model on a
mini's Intel iGPU, claimed through Dynamic Resource Allocation. Four of the
things it gets right are things that FAIL SILENTLY if they regress, which is
why they are pinned here rather than left to review:

1. **The claim must not request capacity.** The live ResourceSlice advertises
   `capacity.memory: "0"` — the iGPU has no dedicated VRAM, it borrows the
   node's 64 GB. A claim that asks for GPU memory can never be satisfied, and
   the pod simply stays Pending.

2. **Readiness must be model-level.** Measured live during the design gate:
   OVMS answers `GET /v2/health/ready` with 200 while its only servable sits
   in `LOADING_PRECONDITION_FAILED`. That endpoint reports SERVER liveness.
   Pointed there, a pod that serves nothing is Ready, the Application is
   green, and every request fails.

3. **The PVC seed must be version-gated, not seed-if-absent.** Frank already
   documents this exact bug for the comfyui custom-nodes PVC: an image update
   never reaches an already-seeded volume, pods stay Ready, stale content is
   served indefinitely. A `[ -d … ] || cp` here means the first model bump
   silently does not deploy.

4. **The service is in-cluster only.** The routing decision was a ClusterIP
   and nothing else — no LoadBalancer IP, no IngressRoute, no LiteLLM alias.
   This is an UNAUTHENTICATED inference endpoint; the test below is what keeps
   a later drive-by from quietly putting it on the LAN.

All assertions are OFFLINE — they parse the YAML in this repo. No cluster, no
network, and deliberately no `kustomize` binary (siblings that shell out to it
fail wherever it is not installed).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = REPO_ROOT / "apps/ovms-retrieval"
MANIFESTS = APP_DIR / "manifests"
APP_CR = REPO_ROOT / "apps/root/templates/ovms-retrieval.yaml"
WORKFLOW = REPO_ROOT / ".github/workflows/build-ovms-retrieval-models.yml"

NAMESPACE = "retrieval"
APP_NAME = "ovms-retrieval"
DEVICE_CLASS = "gpu.intel.com"
CLAIM_TEMPLATE = "ovms-igpu"
CLAIM_REF = "igpu"

# Stock upstream runtime — the only thing this repo maintains is a bag of
# model files, so an OVMS upgrade is a tag bump, not a forked-server rebuild.
SERVING_IMAGE = "openvino/model_server:2026.2.1-gpu"
MODEL_IMAGE_REPO = "ghcr.io/derio-net/ovms-retrieval-models"

# Servable names, as exported by apps/ovms-retrieval/docker/Dockerfile.
# Kept generic/technical on purpose — see agents/rules/third-party-privacy.md.
EMBEDDINGS_MODEL_NAME = "bge-m3"
RERANK_MODEL_NAME = "bge-reranker-v2-m3"

MODELS_MOUNT = "/models"
SEED_SOURCE = "/models-src/gpu"
SEED_MARKER = ".seed-rev"
REST_PORT = 8000
PVC_NAME = "ovms-retrieval-models"


# ── helpers ────────────────────────────────────────────────────────────────


def _docs(name: str) -> list[dict]:
    path = MANIFESTS / name
    assert path.is_file(), f"missing manifest: {path.relative_to(REPO_ROOT)}"
    return [d for d in yaml.safe_load_all(path.read_text()) if d]


def _one(name: str, kind: str) -> dict:
    matches = [d for d in _docs(name) if d.get("kind") == kind]
    assert len(matches) == 1, f"expected exactly one {kind} in {name}, got {len(matches)}"
    return matches[0]


def _deployment() -> dict:
    return _one("deployment.yaml", "Deployment")


def _pod_spec() -> dict:
    return _deployment()["spec"]["template"]["spec"]


def _container(name: str) -> dict:
    spec = _pod_spec()
    for c in spec.get("containers", []) + spec.get("initContainers", []):
        if c["name"] == name:
            return c
    raise AssertionError(f"no container named {name!r} in the Deployment")


def _ovms() -> dict:
    return _container("ovms")


def _seed() -> dict:
    return _container("seed-models")


def _seed_script() -> str:
    c = _seed()
    return "\n".join(c.get("command", []) + c.get("args", []))


def _application() -> dict:
    assert APP_CR.is_file(), f"missing Application CR: {APP_CR.relative_to(REPO_ROOT)}"
    text = (
        APP_CR.read_text()
        .replace("{{ .Values.repoURL }}", "REPO")
        .replace("{{ .Values.targetRevision }}", "REV")
        .replace("{{ .Values.destination.server }}", "SERVER")
    )
    return yaml.safe_load(text)


def _walk(node, path="") -> list[tuple[str, object]]:
    """Flatten a nested dict/list into (dotted-path, value) pairs."""
    out: list[tuple[str, object]] = []
    if isinstance(node, dict):
        for k, v in node.items():
            out.append((f"{path}.{k}".lstrip("."), v))
            out.extend(_walk(v, f"{path}.{k}"))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out.extend(_walk(v, f"{path}[{i}]"))
    return out


def _quantity(value) -> str:
    return str(value)


# ── 1. the ResourceClaimTemplate ───────────────────────────────────────────


def test_claim_template_uses_ga_dra_api():
    """`resource.k8s.io/v1` is GA on this cluster (v1.35.3).

    The alpha/beta group names are the ones every tutorial still shows; using
    one here would make the object apply against nothing.
    """
    rct = _one("resourceclaimtemplate.yaml", "ResourceClaimTemplate")
    assert rct["apiVersion"] == "resource.k8s.io/v1", rct["apiVersion"]
    assert rct["metadata"]["name"] == CLAIM_TEMPLATE
    assert rct["metadata"]["namespace"] == NAMESPACE


def test_claim_selects_exactly_one_device_of_the_intel_class():
    rct = _one("resourceclaimtemplate.yaml", "ResourceClaimTemplate")
    requests = rct["spec"]["spec"]["devices"]["requests"]
    assert len(requests) == 1, f"one device, one request: {requests}"

    req = requests[0]
    assert "firstAvailable" not in req, (
        "firstAvailable is an alternatives list — this app wants the Intel "
        "iGPU or nothing, so the request must be `exactly`"
    )
    exactly = req["exactly"]
    assert exactly["deviceClassName"] == DEVICE_CLASS, exactly
    assert exactly["allocationMode"] == "ExactCount", exactly
    assert exactly["count"] == 1, exactly


def test_claim_requests_no_capacity():
    """The ResourceSlice advertises `capacity.memory: "0"` — measured live.

    The iGPU shares the node's 64 GB rather than owning VRAM, so a request for
    GPU memory can NEVER be satisfied: the scheduler finds no matching device
    and the pod sits Pending with no error that names the cause. The claim must
    select the device and nothing else.
    """
    rct = _one("resourceclaimtemplate.yaml", "ResourceClaimTemplate")
    for dotted, _value in _walk(rct["spec"]["spec"]["devices"]):
        leaf = dotted.rsplit(".", 1)[-1]
        assert leaf != "capacity", (
            f"the claim requests capacity at {dotted} — the live ResourceSlice "
            'advertises capacity.memory: "0" (shared host RAM), so this can '
            "never be allocated and the pod will stay Pending"
        )


# ── 2. the Deployment ──────────────────────────────────────────────────────


def test_deployment_is_a_single_pinned_replica_with_recreate():
    dep = _deployment()
    assert dep["metadata"]["namespace"] == NAMESPACE
    assert dep["spec"]["replicas"] == 1, (
        "one replica by design — three would triple control-plane exposure "
        "before anything has been measured"
    )
    assert dep["spec"]["strategy"]["type"] == "Recreate", (
        "RWO PVC: RollingUpdate deadlocks because the new pod cannot attach "
        "the volume the old pod still holds"
    )


def test_deployment_pins_one_mini_and_tolerates_the_control_plane():
    spec = _pod_spec()
    host = spec["nodeSelector"]["kubernetes.io/hostname"]
    assert re.fullmatch(r"mini-[123]", host), (
        f"expected a hostname pin to one mini, got {host!r} — an inference pod "
        "silently hopping between control-plane nodes is not something to "
        "discover later"
    )
    tolerations = spec.get("tolerations") or []
    assert any(
        t.get("key") == "node-role.kubernetes.io/control-plane" for t in tolerations
    ), f"the minis are control-plane nodes; without the toleration the pod never schedules: {tolerations}"


def test_both_images_are_tag_pinned_and_never_latest():
    for c in (_seed(), _ovms()):
        image = c["image"]
        assert ":" in image, f"{c['name']}: image has no tag — implicitly :latest ({image})"
        tag = image.rsplit(":", 1)[1]
        assert tag != "latest", (
            f"{c['name']}: :latest defeats GitOps determinism — the running "
            "bytes stop being a property of the repo"
        )
    assert _ovms()["image"] == SERVING_IMAGE, (
        "the serving runtime must stay STOCK upstream; a forked server image "
        "turns every OVMS upgrade into a rebuild"
    )
    assert _seed()["image"].startswith(f"{MODEL_IMAGE_REPO}:"), _seed()["image"]


def test_model_image_tag_matches_the_rev_ci_publishes():
    """The Deployment must consume the tag the build workflow actually pushes.

    Bumping one without the other has two failure modes and both are bad: a
    Deployment ahead of CI is an ImagePullBackOff, a Deployment behind CI is a
    model bump that silently never deploys.
    """
    workflow = yaml.safe_load(WORKFLOW.read_text())
    published_rev = str(workflow["env"]["MODELS_REV"])
    deployed_tag = _seed()["image"].rsplit(":", 1)[1]
    assert deployed_tag == published_rev, (
        f"Deployment pins model rev {deployed_tag!r} but "
        f"{WORKFLOW.name} publishes {published_rev!r}"
    )


def test_seed_is_version_gated_by_a_marker_not_seed_if_absent():
    """The comfyui custom-nodes bug, refused by construction.

    Seed-if-absent means an already-populated PVC never sees a new model
    image: the pod boots Ready and serves the old weights forever, with the
    Application green throughout. The gate must compare a marker written by a
    previous seed against the rev this image carries — so it must both READ
    and WRITE the marker, and the comparison must be against MODELS_REV.
    """
    script = _seed_script()
    marker = f"{MODELS_MOUNT}/{SEED_MARKER}"

    env = {e["name"]: e.get("value") for e in _seed().get("env", [])}
    assert "MODELS_REV" in env, (
        "the seed container needs MODELS_REV in its env — that value is what "
        f"the {SEED_MARKER} marker is compared against"
    )
    assert env["MODELS_REV"] == _seed()["image"].rsplit(":", 1)[1], (
        "MODELS_REV must equal the model image's own tag, or the marker "
        "records a rev the seeded bytes are not"
    )

    assert SEED_MARKER in script, f"no {SEED_MARKER} marker in the seed script"
    assert re.search(rf'=\s*"?\$\{{?MODELS_REV', script), (
        "the skip condition must compare the marker to $MODELS_REV — anything "
        "else (a directory-exists test, a file-count test) is seed-if-absent "
        "wearing a marker's clothes"
    )
    assert re.search(rf'>\s*"?{re.escape(marker)}|>\s*"?\$\w*marker', script, re.I), (
        "the seed script never WRITES the marker — it would re-seed on every "
        "single pod start"
    )
    assert SEED_SOURCE in script, (
        f"the seed must copy {SEED_SOURCE} (the GPU-targeted repository); "
        "/models-src also holds a CPU control arm whose graph.pbtxt names the "
        "wrong device"
    )


def test_readiness_is_model_level_never_the_server_health_endpoint():
    """`/v2/health/ready` returned 200 with the servable in
    LOADING_PRECONDITION_FAILED — observed live during the design gate.

    It is a SERVER-liveness endpoint. Used for readiness it produces the worst
    available outcome: a Ready pod, a green Application, and every request
    failing.
    """
    c = _ovms()
    probes = {k: c[k] for k in ("startupProbe", "readinessProbe", "livenessProbe") if k in c}
    assert "readinessProbe" in probes, "no readinessProbe — a pod serving nothing would take traffic"

    for name in ("startupProbe", "readinessProbe"):
        probe = probes.get(name)
        if not probe:
            continue
        path = probe["httpGet"]["path"]
        assert path != "/v2/health/ready", (
            f"{name} points at /v2/health/ready, which answers 200 while a "
            "model is in LOADING_PRECONDITION_FAILED"
        )
        assert re.fullmatch(r"/v2/models/[^/]+/ready", path), (
            f"{name} must be model-level (/v2/models/<name>/ready), got {path!r}"
        )

    ready_models = {
        probes[n]["httpGet"]["path"].split("/")[3]
        for n in ("startupProbe", "readinessProbe")
        if n in probes
    }
    assert {EMBEDDINGS_MODEL_NAME, RERANK_MODEL_NAME} <= ready_models, (
        "both servables must be gated before the pod takes traffic — "
        "startupProbe runs to completion before readiness, so one probe each "
        f"covers the pair. Covered: {sorted(ready_models)}"
    )

    if "livenessProbe" in probes:
        assert probes["livenessProbe"]["httpGet"]["path"] == "/v2/health/live", (
            "liveness is the one place the SERVER-level endpoint is correct"
        )


def test_resources_declare_both_requests_and_limits():
    """A limit without a request lets the scheduler over-commit an etcd member."""
    res = _ovms()["resources"]
    assert _quantity(res["requests"]["cpu"]) == "500m", res
    assert _quantity(res["requests"]["memory"]) == "2Gi", res
    assert _quantity(res["limits"]["cpu"]) == "2", res
    assert _quantity(res["limits"]["memory"]) == "6Gi", res


def test_security_context_is_restricted_compliant_with_fsgroup():
    """`fsGroup: 5000` is the easiest thing here to get wrong.

    Longhorn mounts a PVC root-owned and OVMS runs as uid 5000, so without it
    the seed initContainer cannot write the model repository and the pod fails
    at first boot — visible only if you watch the initContainer rather than the
    pod. Same trap already documented for Tekton workspaces.

    PodSecurity only *enforces* baseline here (restricted merely warns), so
    restricted compliance is a choice, not a requirement — which is exactly why
    it needs a test.
    """
    pod_sc = _pod_spec()["securityContext"]
    assert pod_sc["fsGroup"] == 5000, (
        "no fsGroup: 5000 — the Longhorn volume mounts root-owned and the "
        "uid-5000 seed container cannot write it"
    )
    assert pod_sc["runAsUser"] == 5000, pod_sc
    assert pod_sc["runAsNonRoot"] is True, pod_sc
    assert pod_sc["seccompProfile"]["type"] == "RuntimeDefault", pod_sc

    # No supplementalGroups: /dev/dri is crw-rw-rw- root:root (measured live),
    # so the usual render-GID hunt does not apply. Carrying one anyway would be
    # cargo cult that a reader would later have to disprove.
    assert "supplementalGroups" not in pod_sc, (
        "/dev/dri is world-readable on these nodes — a render GID here is "
        "unverified cargo cult"
    )

    for c in (_seed(), _ovms()):
        sc = c["securityContext"]
        assert sc["allowPrivilegeEscalation"] is False, c["name"]
        assert sc["capabilities"]["drop"] == ["ALL"], c["name"]
        assert sc["runAsNonRoot"] is True, c["name"]
        assert sc.get("privileged") is not True, c["name"]


def test_the_igpu_claim_is_wired_to_the_serving_container_only():
    spec = _pod_spec()
    claims = spec["resourceClaims"]
    assert len(claims) == 1, claims
    assert claims[0]["name"] == CLAIM_REF
    assert claims[0]["resourceClaimTemplateName"] == CLAIM_TEMPLATE, (
        "a ResourceClaimTemplate (not a shared ResourceClaim) so the "
        "allocation is owned by the pod's lifecycle and cannot dangle"
    )

    assert [c["name"] for c in _ovms()["resources"].get("claims", [])] == [CLAIM_REF]
    assert not _seed()["resources"].get("claims"), (
        "the seed container copies files; giving it the iGPU would hold the "
        "device through the init phase for nothing"
    )


def test_model_repository_is_the_pvc_and_ovms_reads_its_config():
    spec = _pod_spec()
    vols = {v["name"]: v for v in spec["volumes"]}
    pvc_vols = [
        n for n, v in vols.items() if v.get("persistentVolumeClaim", {}).get("claimName") == PVC_NAME
    ]
    assert pvc_vols, f"no volume backed by PVC {PVC_NAME}: {vols}"
    vol = pvc_vols[0]

    for c in (_seed(), _ovms()):
        mounts = {m["name"]: m["mountPath"] for m in c["volumeMounts"]}
        assert mounts.get(vol) == MODELS_MOUNT, f"{c['name']}: {mounts}"

    args = _ovms().get("args") or []
    joined = " ".join(str(a) for a in args)
    assert "--config_path" in joined, f"OVMS needs --config_path: {args}"
    assert f"{MODELS_MOUNT}/config.json" in joined, (
        f"--config_path must point inside the seeded repository: {args}"
    )
    assert "--rest_port" in joined and str(REST_PORT) in joined, args


# ── 3. routing: in-cluster only ────────────────────────────────────────────


def test_service_is_clusterip_on_8000():
    svc = _one("service.yaml", "Service")
    assert svc["metadata"]["namespace"] == NAMESPACE
    assert svc["spec"]["type"] == "ClusterIP", (
        "in-cluster only — this is an UNAUTHENTICATED inference endpoint"
    )
    ports = svc["spec"]["ports"]
    assert len(ports) == 1, f"REST only; gRPC is deliberately not exposed: {ports}"
    assert ports[0]["port"] == REST_PORT, ports

    # the Service must actually reach the pod
    target = ports[0].get("targetPort", ports[0]["port"])
    container_ports = {p.get("name"): p["containerPort"] for p in _ovms()["ports"]}
    assert target in container_ports or target in container_ports.values(), (
        f"targetPort {target!r} matches no container port: {container_ports}"
    )
    selector = svc["spec"]["selector"]
    labels = _deployment()["spec"]["template"]["metadata"]["labels"]
    assert selector.items() <= labels.items(), f"selector {selector} matches no pod label {labels}"


def test_no_loadbalancer_ip_is_claimed_anywhere_in_the_app():
    for path in sorted(MANIFESTS.rglob("*.yaml")):
        text = path.read_text()
        # Comments are stripped before the scan — this file's own manifests
        # explain WHY there is no LoadBalancer, and a naive substring match
        # would fail on the explanation rather than on a violation.
        live = "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith("#")
        )
        assert "lbipam.cilium.io" not in live, (
            f"{path.relative_to(REPO_ROOT)} claims a LAN LoadBalancer IP — the "
            "routing decision was in-cluster only"
        )
        for doc in yaml.safe_load_all(text):
            if not doc:
                continue
            annotations = (doc.get("metadata") or {}).get("annotations") or {}
            assert not any("lbipam" in k for k in annotations), annotations
            if doc.get("kind") == "Service":
                assert doc["spec"]["type"] == "ClusterIP", doc["metadata"]["name"]


def test_nothing_outside_the_app_routes_to_it():
    """The tripwire that keeps this off the LAN.

    An IngressRoute, a homepage tile or a LiteLLM alias added later would each
    put an unauthenticated embeddings/rerank endpoint in front of something
    that has no auth of its own. Any of them would have to name this app, so a
    repo-wide reference scan catches all three at once — and fails loudly
    enough that exposing it becomes a deliberate, reviewed decision.
    """
    allowed = {
        APP_DIR,
        APP_CR,
        WORKFLOW,
        Path(__file__),
    }
    offenders: list[str] = []
    for root in ("apps", "clusters"):
        for path in sorted((REPO_ROOT / root).rglob("*")):
            if not path.is_file() or path.suffix not in {".yaml", ".yml", ".json"}:
                continue
            if any(path == a or a in path.parents for a in allowed):
                continue
            if APP_NAME in path.read_text():
                offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, (
        "these files reference ovms-retrieval from outside the app itself — if "
        "this is an intentional exposure it needs an auth story first, not a "
        f"drive-by edit: {offenders}"
    )


def test_no_ingressroute_targets_the_retrieval_namespace():
    ingressroutes = REPO_ROOT / "apps/traefik/manifests/ingressroutes.yaml"
    for doc in yaml.safe_load_all(ingressroutes.read_text()):
        if not doc or doc.get("kind") != "IngressRoute":
            continue
        for route in doc["spec"].get("routes", []):
            for svc in route.get("services", []):
                assert svc.get("namespace") != NAMESPACE, (
                    f"IngressRoute {doc['metadata']['name']} routes to the "
                    f"{NAMESPACE} namespace"
                )


# ── 4. the supporting objects ──────────────────────────────────────────────


def test_namespace_carries_pod_security_labels():
    ns = _one("namespace.yaml", "Namespace")
    assert ns["metadata"]["name"] == NAMESPACE
    labels = ns["metadata"]["labels"]
    assert labels["pod-security.kubernetes.io/enforce"] == "baseline"
    assert labels["pod-security.kubernetes.io/warn"] == "restricted"
    assert labels["pod-security.kubernetes.io/audit"] == "restricted"


def test_model_pvc_is_longhorn_rwo():
    pvc = _one("pvc.yaml", "PersistentVolumeClaim")
    assert pvc["metadata"]["name"] == PVC_NAME
    assert pvc["metadata"]["namespace"] == NAMESPACE
    assert pvc["spec"]["storageClassName"] == "longhorn"
    assert pvc["spec"]["accessModes"] == ["ReadWriteOnce"]
    assert pvc["spec"]["resources"]["requests"]["storage"] == "20Gi"


def test_kustomization_lists_every_manifest():
    """A manifest no kustomization references is inert, and nothing surfaces it."""
    kustomization = yaml.safe_load((MANIFESTS / "kustomization.yaml").read_text())
    listed = set(kustomization.get("resources") or [])
    on_disk = {
        p.name for p in MANIFESTS.glob("*.yaml") if p.name != "kustomization.yaml"
    }
    assert on_disk <= listed, f"unreferenced manifests: {sorted(on_disk - listed)}"
    assert listed <= on_disk, f"kustomization lists missing files: {sorted(listed - on_disk)}"


def test_root_application_wiring():
    app = _application()
    assert app["kind"] == "Application"
    assert app["metadata"]["name"] == APP_NAME
    assert app["spec"]["project"] == "infrastructure"
    assert app["spec"]["source"]["path"] == "apps/ovms-retrieval/manifests"
    assert app["spec"]["destination"]["namespace"] == NAMESPACE
    assert app["spec"]["syncPolicy"]["automated"]["selfHeal"] is True
    opts = app["spec"]["syncPolicy"]["syncOptions"]
    assert "ServerSideApply=true" in opts, opts
    assert "CreateNamespace=true" in opts, opts


def test_prune_can_never_reach_the_model_cache():
    """Conditional by design, so it stays true if a generator is added later.

    No configMapGenerator today (the seed script lives in the pod spec, which
    already rolls the pod on edit), so prune stays off and the PVC is safe by
    default. If someone adds a generator, prune: true becomes mandatory — and
    at that moment the PVC must opt out individually, or a mis-sync destroys a
    20Gi model cache that takes a CI rebuild to recreate.
    """
    kustomization = yaml.safe_load((MANIFESTS / "kustomization.yaml").read_text())
    has_generator = bool(
        kustomization.get("configMapGenerator") or kustomization.get("secretGenerator")
    )
    prune = _application()["spec"]["syncPolicy"]["automated"].get("prune", False)

    if has_generator:
        assert prune is True, (
            "hash-suffixed generated objects orphan their predecessor on every "
            "edit; without prune the app sits OutOfSync forever"
        )
        pvc = _one("pvc.yaml", "PersistentVolumeClaim")
        annotations = pvc["metadata"].get("annotations", {})
        assert "Prune=false" in annotations.get("argocd.argoproj.io/sync-options", ""), (
            "prune: true is on, so the model-cache PVC must opt out per-resource"
        )
    else:
        assert prune is not True, (
            "nothing here needs prune, and leaving it on puts a 20Gi model "
            "cache one mis-sync away from deletion"
        )
