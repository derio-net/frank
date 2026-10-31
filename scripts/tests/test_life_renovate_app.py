"""Renovate runs on Frank as a CronJob with a scoped GitHub App token via ESO."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MAN = ROOT / "apps/renovate/manifests"
TEMPLATE = ROOT / "apps/root/templates/renovate.yaml"


def docs():
    out = []
    for f in sorted(MAN.glob("*.yaml")):
        out += [d for d in yaml.safe_load_all(f.read_text()) if d]
    return out


def of(kind):
    return [d for d in docs() if d["kind"] == kind]


def test_application_template():
    text = TEMPLATE.read_text()
    assert "path: apps/renovate/manifests" in text
    assert "sources:" not in text, "single-source Application"
    app = yaml.safe_load(text.replace("{{ .Values.repoURL }}", "x").replace(
        "{{ .Values.targetRevision }}", "main").replace("{{ .Values.destination.server }}", "s"))
    spec = app["spec"]
    assert "ServerSideApply=true" in spec["syncPolicy"]["syncOptions"]
    assert spec["syncPolicy"]["automated"]["selfHeal"] is True
    assert not spec["syncPolicy"]["automated"].get("prune", False)
    assert spec["destination"]["namespace"] == "renovate"


def test_cronjob():
    (cj,) = of("CronJob")
    spec = cj["spec"]
    assert spec["schedule"] == "0 * * * *"
    assert spec["concurrencyPolicy"] == "Forbid"
    pod = spec["jobTemplate"]["spec"]["template"]["spec"]
    assert pod["securityContext"]["runAsNonRoot"] is True
    (c,) = pod["containers"]
    image = c["image"]
    assert image.split(":")[0].endswith("renovate/renovate")
    tag = image.split(":")[1]
    assert tag.count(".") == 2 and tag.replace(".", "").isdigit(), "exact tag"
    assert c["securityContext"]["capabilities"]["drop"] == ["ALL"]
    assert c["securityContext"]["allowPrivilegeEscalation"] is False
    assert c["resources"]["limits"]["memory"] and c["resources"]["limits"]["cpu"]
    env = {e["name"]: e for e in c["env"]}
    assert env["RENOVATE_PLATFORM"]["value"] == "github"
    assert env["RENOVATE_REPOSITORIES"]["value"] == "derio-net/frank"
    assert env["RENOVATE_ONBOARDING"]["value"] == "false"
    assert "secretKeyRef" in env["RENOVATE_TOKEN"]["valueFrom"]
    assert "DISABLE_AUTOUPDATER" not in env


def test_token_comes_from_a_clustergenerator_with_the_pem_in_this_namespace():
    (cg,) = of("ClusterGenerator")
    assert cg["spec"]["kind"] == "GithubAccessToken"
    gen = cg["spec"]["generator"]["githubAccessTokenSpec"]
    assert gen["repositories"] == ["frank"]
    secret_ref = gen["auth"]["privateKey"]["secretRef"]
    assert secret_ref["name"] == "github-app-renovate-key"
    (es,) = of("ExternalSecret")
    assert es["metadata"]["namespace"] == "renovate", "ESO resolves secretRef in the CONSUMER's namespace"
    ref = es["spec"]["dataFrom"][0]["sourceRef"]["generatorRef"]
    assert ref["kind"] == "ClusterGenerator" and ref["name"] == cg["metadata"]["name"]
    assert es["spec"]["target"]["name"] == "renovate-github-token"


def test_namespace_and_no_secret_data_in_git():
    (ns,) = of("Namespace")
    assert ns["metadata"]["name"] == "renovate"
    assert not of("Secret"), "the PEM is applied out-of-band (manual phase), never committed"
    for f in MAN.glob("*.yaml"):
        assert "BEGIN" not in f.read_text() or "PRIVATE KEY" not in f.read_text()


def _placeholders():
    (cg,) = of("ClusterGenerator")
    gen = cg["spec"]["generator"]["githubAccessTokenSpec"]
    return "PENDING" in gen["appID"] or "PENDING" in gen["installID"]


def test_cronjob_is_suspended_exactly_while_the_app_ids_are_placeholders():
    (cj,) = of("CronJob")
    assert cj["spec"].get("suspend", False) is _placeholders()


def test_token_outlives_the_job_that_uses_it():
    """The installation token lives 3600s; the ExternalSecret may be up to refreshInterval stale."""
    (es,) = of("ExternalSecret")
    (cj,) = of("CronJob")
    refresh = int(es["spec"]["refreshInterval"].rstrip("m")) * 60
    deadline = cj["spec"]["jobTemplate"]["spec"]["activeDeadlineSeconds"]
    assert deadline + refresh < 3600, (deadline, refresh)
