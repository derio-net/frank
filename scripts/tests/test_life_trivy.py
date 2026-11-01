"""Trivy Operator on Frank: vulnerability scanning with bounded metrics (spec R8)."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "apps/root/templates/trivy-operator.yaml"
VALUES = ROOT / "apps/trivy-operator/values.yaml"
MAN = ROOT / "apps/trivy-operator/manifests"


def app():
    text = TEMPLATE.read_text()
    for k, v in (("{{ .Values.repoURL }}", "x"), ("{{ .Values.targetRevision }}", "main"),
                 ("{{ .Values.destination.server }}", "s")):
        text = text.replace(k, v)
    return yaml.safe_load(text)


def values():
    return yaml.safe_load(VALUES.read_text())


def manifests():
    out = []
    for f in sorted(MAN.glob("*.yaml")):
        out += [d for d in yaml.safe_load_all(f.read_text()) if d]
    return out


def test_application_is_multi_source_with_an_exact_chart_pin():
    spec = app()["spec"]
    chart = [s for s in spec["sources"] if s.get("chart") == "trivy-operator"]
    assert len(chart) == 1
    assert chart[0]["repoURL"].startswith("https://aquasecurity.github.io/")
    assert chart[0]["targetRevision"].count(".") == 2 and chart[0]["targetRevision"][0].isdigit()
    assert "$values/apps/trivy-operator/values.yaml" in chart[0]["helm"]["valueFiles"]
    assert any(s.get("ref") == "values" for s in spec["sources"])
    assert any(s.get("path") == "apps/trivy-operator/manifests" for s in spec["sources"])
    assert "ServerSideApply=true" in spec["syncPolicy"]["syncOptions"]
    assert not spec["syncPolicy"]["automated"].get("prune", False)
    assert spec["destination"]["namespace"] == "trivy-system"


def test_values_comment_records_the_chart_version():
    pin = [s for s in app()["spec"]["sources"] if s.get("chart")][0]["targetRevision"]
    assert pin in VALUES.read_text()


def test_metrics_stay_bounded():
    op = values()["operator"]
    assert op["metricsVulnIdEnabled"] is False, "per-CVE series would blow promscrape.maxScrapeSize"
    assert op["metricsFindingsEnabled"] is True, "the severity summary is what Grafana reads"


def test_scrape_is_a_vmservicescrape():
    (scrape,) = [d for d in manifests() if d["kind"] == "VMServiceScrape"]
    assert scrape["spec"]["selector"]["matchLabels"]["app.kubernetes.io/name"] == "trivy-operator"
    assert scrape["spec"]["endpoints"][0]["port"] == "metrics"
    assert values()["serviceMonitor"]["enabled"] is False


def test_scan_jobs_and_server_are_resource_bounded_and_server_is_built_in():
    v = values()
    assert v["operator"]["builtInTrivyServer"] is True
    assert v["trivy"]["mode"] == "ClientServer"
    assert v["trivy"]["resources"]["limits"]["memory"]
    assert v["trivy"]["server"]["resources"]["limits"]["memory"]
    assert v["resources"]["limits"]["memory"]


def test_namespace_is_declared():
    (ns,) = [d for d in manifests() if d["kind"] == "Namespace"]
    assert ns["metadata"]["name"] == "trivy-operator" or ns["metadata"]["name"] == "trivy-system"
    assert ns["metadata"]["name"] == "trivy-system"


def test_p3_sec_4_server_requires_a_token_from_an_out_of_band_secret():
    v = values()
    assert v["trivy"]["existingSecret"] is True, "token lives in a Secret, never in git"
    assert not v["trivy"].get("serverToken")
    assert "trivy-operator-trivy-config" in VALUES.read_text()  # the Secret name the chart expects


def test_p3_sec_4_ingress_to_the_server_is_restricted():
    (np,) = [d for d in manifests() if d["kind"] == "NetworkPolicy"]
    assert np["metadata"]["namespace"] == "trivy-system"
    assert np["spec"]["podSelector"]["matchLabels"]["app.kubernetes.io/name"] == "trivy-server"
    assert np["spec"]["policyTypes"] == ["Ingress"]
    (rule,) = np["spec"]["ingress"]
    assert [(p["protocol"], p["port"]) for p in rule["ports"]] == [("TCP", 4954)]
    srcs = rule["from"]
    ns = [s["namespaceSelector"]["matchLabels"]["kubernetes.io/metadata.name"] for s in srcs if "namespaceSelector" in s and "podSelector" not in s]
    assert ns == ["hop-scan"]
    pods = [s for s in srcs if "podSelector" in s and "namespaceSelector" not in s]
    labels = [p["podSelector"]["matchLabels"] for p in pods]
    assert {"trivy-operator.scan-job": "true"} in labels
    assert {"app.kubernetes.io/name": "trivy-operator"} in labels
    assert len(srcs) == 3
    assert v_label() == "trivy-operator.scan-job=true"


def v_label():
    return values()["trivyOperator"]["scanJobPodTemplateLabels"]
