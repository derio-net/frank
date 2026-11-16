"""Guards for the speech app: manifests, Application, private exposure."""
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
    assert "ip-allowlist" in mws and "security-headers" in mws
    assert "authentik-forwardauth" not in mws
    assert r["services"][0]["name"] == "speech"
    assert r["services"][0]["namespace"] == "speech"
    assert r["services"][0]["port"] == 8000


def test_ingressroute_has_explicit_upload_limit_and_timeouts():
    r = _route()["spec"]["routes"][0]
    mws = [m["name"] for m in r["middlewares"]]
    by_name = {}
    for d in _docs(REPO / "apps/traefik/manifests/middlewares.yaml"):
        by_name[(d["kind"], d["metadata"]["name"])] = d
    assert "speech-upload-limit" in mws
    buf = by_name[("Middleware", "speech-upload-limit")]["spec"]["buffering"]
    # 2.5 h of 16 kHz mono 16-bit WAV is ~290 MB; allow headroom
    assert buf["maxRequestBodyBytes"] >= 1024 * 1024 * 1024
    assert buf["memRequestBodyBytes"] <= 64 * 1024 * 1024
    transport = r["services"][0]["serversTransport"]
    st = by_name[("ServersTransport", transport)]["spec"]["forwardingTimeouts"]

    def secs(v):
        v = str(v)
        return int(v[:-1]) * {"s": 1, "m": 60, "h": 3600}[v[-1]]

    # a 2.5 h recording transcribes in well under that, but the response header
    # only arrives when the whole file is done (non-streaming)
    assert secs(st["responseHeaderTimeout"]) >= 3600
    assert "dialTimeout" in st


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
