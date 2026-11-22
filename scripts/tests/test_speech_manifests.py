"""Guards for the speech app: manifests, Application, private exposure."""
import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
MANIFESTS = REPO / "apps/speech/manifests"
ROOT_TEMPLATE = REPO / "apps/root/templates/speech.yaml"
NS_TEMPLATE = REPO / "apps/root/templates/ns-speech.yaml"
INGRESS = REPO / "apps/traefik/manifests/ingressroutes.yaml"
HOMEPAGE = REPO / "apps/homepage/manifests/files/services.yaml"
WORKFLOW = REPO / ".github/workflows/build-speech.yml"


def _load(name):
    return yaml.safe_load((MANIFESTS / name).read_text())


def _deployment():
    return _load("deployment.yaml")


def _pod():
    return _deployment()["spec"]["template"]["spec"]


def test_deployment_is_pinned_gpu_pod():
    dep = _deployment()
    rev = yaml.safe_load(WORKFLOW.read_text())["env"]["SPEECH_REV"]
    c = _pod()["containers"][0]
    assert c["image"] == f"ghcr.io/derio-net/speech:{rev}"
    assert "@" not in c["image"] and not c["image"].endswith(":latest")
    assert dep["spec"]["strategy"]["type"] == "Recreate"
    assert _pod()["nodeSelector"] == {"kubernetes.io/hostname": "gpu-1"}
    assert any(
        t.get("key") == "nvidia.com/gpu" and t.get("operator") == "Exists"
        for t in _pod()["tolerations"]
    )
    assert c["resources"]["requests"]["nvidia.com/gpu"] == "1"
    assert c["resources"]["limits"]["nvidia.com/gpu"] == "1"
    assert dep["metadata"]["labels"]["app.kubernetes.io/name"] == "speech"
    assert dep["spec"]["template"]["metadata"]["labels"]["app.kubernetes.io/name"] == "speech"
    assert dep["spec"]["selector"]["matchLabels"]["app.kubernetes.io/name"] == "speech"
    assert dep["metadata"]["namespace"] == "speech"


def test_deployment_starts_at_zero_for_the_switcher():
    # gpu-switcher decides when speech runs (group with ollama); git declares 0.
    assert _deployment()["spec"]["replicas"] == 0


def test_model_cache_is_a_longhorn_pvc():
    pvc = _load("pvc.yaml")
    assert pvc["kind"] == "PersistentVolumeClaim"
    assert pvc["spec"]["storageClassName"] == "longhorn"
    assert pvc["spec"]["accessModes"] == ["ReadWriteOnce"]
    claims = [v["persistentVolumeClaim"]["claimName"] for v in _pod()["volumes"] if "persistentVolumeClaim" in v]
    assert pvc["metadata"]["name"] in claims


def test_default_models_and_long_request_settings():
    env = {e["name"]: e.get("value") for e in _pod()["containers"][0]["env"]}
    assert env["PRELOAD_MODELS"]
    assert "large-v3-turbo" in env["PRELOAD_MODELS"]
    assert env["WHISPER__INFERENCE_DEVICE"] == "cuda"
    # models unload after use so an idle speech pod does not pin VRAM
    assert int(env["STT_MODEL_TTL"]) >= 0 and int(env["TTS_MODEL_TTL"]) >= 0


def test_service_is_cluster_ip_only():
    svc = _load("service.yaml")
    assert svc["spec"]["type"] == "ClusterIP"
    assert svc["metadata"]["namespace"] == "speech"
    for f in MANIFESTS.glob("*.yaml"):
        doc = yaml.safe_load(f.read_text())
        if doc and doc.get("kind") == "Service":
            assert doc["spec"].get("type", "ClusterIP") != "LoadBalancer"


def test_application_follows_argocd_rules():
    app = yaml.safe_load(ROOT_TEMPLATE.read_text().replace("{{", "'{{").replace("}}", "}}'"))
    assert app["spec"]["source"]["path"] == "apps/speech/manifests"
    assert app["spec"]["destination"]["namespace"] == "speech"
    auto = app["spec"]["syncPolicy"]["automated"]
    assert auto["selfHeal"] is True and auto["prune"] is False
    opts = app["spec"]["syncPolicy"]["syncOptions"]
    assert "ServerSideApply=true" in opts
    ign = app["spec"]["ignoreDifferences"]
    assert any(
        i["kind"] == "Deployment" and i["name"] == "speech" and "/spec/replicas" in i["jsonPointers"]
        for i in ign
    )
    ns = yaml.safe_load(NS_TEMPLATE.read_text())
    assert ns["kind"] == "Namespace" and ns["metadata"]["name"] == "speech"


# ---- private exposure -------------------------------------------------------

def _docs(path):
    return [d for d in yaml.safe_load_all(path.read_text()) if d]


def _route():
    for d in _docs(INGRESS):
        if d["kind"] == "IngressRoute" and d["metadata"]["name"] == "speech":
            return d
    raise AssertionError("IngressRoute speech missing")


def test_ingressroute_is_private_and_unauthenticated_by_forwardauth():
    d = _route()
    assert d["spec"]["entryPoints"] == ["websecure"]  # no public entrypoint
    r = d["spec"]["routes"][0]
    assert r["match"] == "Host(`speech.cluster.derio.net`)"
    mws = [m["name"] for m in r["middlewares"]]
    assert "speech-ip-allowlist" in mws and "security-headers" in mws
    assert "authentik-forwardauth" not in mws
    assert r["services"][0]["name"] == "speech"
    assert r["services"][0]["namespace"] == "speech"
    assert r["services"][0]["port"] == 8000


def _by_name():
    out = {}
    for d in _docs(REPO / "apps/traefik/manifests/middlewares.yaml"):
        out[(d["kind"], d["metadata"]["name"])] = d
    return out


def test_route_middlewares_exist_and_do_not_buffer():
    r = _route()["spec"]["routes"][0]
    by_name = _by_name()
    for m in r["middlewares"]:
        mw = by_name.get(("Middleware", m["name"]))
        if mw is None:
            # shared middlewares (security-headers) live outside this file's
            # speech-specific set; every speech-* reference must resolve here.
            assert not m["name"].startswith("speech-"), f"{m['name']} missing from middlewares.yaml"
            continue
        # buffering a multi-GiB upload on the Pi edge exhausts its disk
        assert "buffering" not in mw["spec"], m["name"]
    assert not [k for k in by_name if k[1] == "speech-upload-limit"]


def test_route_caps_concurrent_requests_per_source_ip():
    r = _route()["spec"]["routes"][0]
    assert "speech-inflight" in [m["name"] for m in r["middlewares"]]
    spec = _by_name()[("Middleware", "speech-inflight")]["spec"]["inFlightReq"]
    assert spec["amount"] == 4
    assert "ipStrategy" in spec["sourceCriterion"]


def test_servers_transport_sets_long_response_timeout():
    """Only checks the ServersTransport (backend response timeout). The
    websecure entrypoint's own read timeout is NOT covered: long recordings use
    the in-cluster Service URL, so this does not assert 2.5 h end-to-end."""
    r = _route()["spec"]["routes"][0]
    # Cross-namespace form "<ns>-<name>@kubernetescrd"; resolution itself is
    # guarded by test_traefik_servers_transport_refs.py.
    transport = r["services"][0]["serversTransport"]
    assert transport == "traefik-system-speech-long-requests@kubernetescrd"
    st = _by_name()[("ServersTransport", "speech-long-requests")]["spec"]["forwardingTimeouts"]

    def secs(v):
        v = str(v)
        return int(v[:-1]) * {"s": 1, "m": 60, "h": 3600}[v[-1]]

    assert secs(st["responseHeaderTimeout"]) >= 3600
    assert "dialTimeout" in st


def test_speech_route_has_its_own_narrow_allowlist():
    r = _route()["spec"]["routes"][0]
    mws = [m["name"] for m in r["middlewares"]]
    assert "speech-ip-allowlist" in mws and "ip-allowlist" not in mws
    ranges = _by_name()[("Middleware", "speech-ip-allowlist")]["spec"]["ipAllowList"]["sourceRange"]
    assert set(ranges) == {"192.168.0.0/16", "100.64.0.0/10", "10.0.0.0/8"}


def test_probes_use_real_endpoints_and_tolerate_long_jobs():
    c = _pod()["containers"][0]
    assert c["ports"][0]["containerPort"] == 8000
    assert c["readinessProbe"]["httpGet"]["path"] == "/v1/models"
    assert c["livenessProbe"]["httpGet"]["path"] == "/health"
    assert c["startupProbe"]["httpGet"]["path"] == "/health"
    for k in ("startupProbe", "livenessProbe", "readinessProbe"):
        assert c[k]["httpGet"]["port"] == "http"
    st = c["startupProbe"]
    assert st["periodSeconds"] * st["failureThreshold"] >= 1200  # cold model download
    lv = c["livenessProbe"]
    # survive a blocked event loop during a multi-hour transcription
    assert lv["periodSeconds"] * lv["failureThreshold"] >= 300


DOCKERFILE = REPO / "apps/speech/docker/Dockerfile"
# The upstream image's USER is `ubuntu`, which is uid/gid 1000 (no numeric uid in
# the Dockerfile to compare against); its HOME is /home/ubuntu.
IMAGE_USER_UID = 1000


def test_pod_runs_non_root_as_the_image_user():
    sc = _pod()["securityContext"]
    assert sc["runAsNonRoot"] is True
    assert re.search(r"^USER\s+ubuntu\s*$", DOCKERFILE.read_text(), re.M)
    assert sc["runAsUser"] == IMAGE_USER_UID and sc["runAsGroup"] == IMAGE_USER_UID
    assert sc["fsGroup"] == IMAGE_USER_UID


def test_container_drops_privileges():
    c = _pod()["containers"][0]
    sc = c["securityContext"]
    assert sc["allowPrivilegeEscalation"] is False
    assert sc["capabilities"]["drop"] == ["ALL"]
    assert sc["seccompProfile"]["type"] == "RuntimeDefault"
    # deliberately writable root fs (model/cache writes) — see the deployment
    assert not sc.get("readOnlyRootFilesystem")


def test_model_cache_mounted_at_the_image_users_hf_cache():
    c = _pod()["containers"][0]
    mounts = {m["name"]: m["mountPath"] for m in c["volumeMounts"]}
    assert mounts.get("model-cache") == "/home/ubuntu/.cache/huggingface"
    claims = {
        v["name"]: v["persistentVolumeClaim"]["claimName"]
        for v in _pod()["volumes"]
        if "persistentVolumeClaim" in v
    }
    assert claims["model-cache"] == "speech-models"


def test_namespace_declares_pod_security_labels():
    ns = yaml.safe_load(NS_TEMPLATE.read_text())
    labels = ns["metadata"]["labels"]
    # the pod needs no privileges (GPU comes from the device plugin), so the
    # namespace is held to baseline on all three modes
    for mode in ("enforce", "audit", "warn"):
        assert labels[f"pod-security.kubernetes.io/{mode}"] == "baseline"


def test_homepage_tile_exists():
    text = HOMEPAGE.read_text()
    assert "https://speech.cluster.derio.net" in text
    assert "http://speech.speech:8000" in text


def test_vram_budget_models_match_preloaded_models():
    import json

    budget = yaml.safe_load((MANIFESTS / "files/vram-budget.yaml").read_text())
    env = {e["name"]: e.get("value") for e in _pod()["containers"][0]["env"]}
    preload = set(json.loads(env["PRELOAD_MODELS"]))
    assert {m["name"] for m in budget["speech"]["models"]} == preload


# Spec R5: TTS for English, German and Greek. Kokoro-82M has no de/el voice (its
# 54 voices cover en/zh/ja/hi/es/pt/it/fr), so de/el come from Piper. Chosen by
# the operator's listening test on 2026-11-22 (Test Plan step 3): Piper
# de_DE-thorsten-high and el_GR-rapunzelina-low, the only Greek Piper voice.
TTS_FOR_LANGUAGE = {
    "en": "speaches-ai/Kokoro-82M-v1.0-ONNX",
    "de": "speaches-ai/piper-de_DE-thorsten-high",
    "el": "speaches-ai/piper-el_GR-rapunzelina-low",
}


def test_every_required_language_has_a_preloaded_tts_voice():
    import json

    env = {e["name"]: e.get("value") for e in _pod()["containers"][0]["env"]}
    preload = json.loads(env["PRELOAD_MODELS"])
    missing = {lang: m for lang, m in TTS_FOR_LANGUAGE.items() if m not in preload}
    assert not missing, f"not preloaded (a fresh model cache would lose them): {missing}"
