"""Contracts the lifecycle code assumes of Trivy (p3-r5).

* report.py is exercised on a REAL `trivy image --format json` output: the golden file of the
  Trivy repository's own integration test (aquasecurity/trivy v0.56.0,
  integration/testdata/alpine-310.json.golden), captured once, not hand-built.
* The pinned trivy-operator chart is rendered with our values and checked against what the
  NetworkPolicy, the VMServiceScrape and the token Secret expect. Needs the network (or a
  cached chart); skips with the reason locally and FAILS under CI=true.
"""
import json
import os
import re
import runpy
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "scripts/tests/fixtures/life/trivy-image-alpine-310.json"
REPORT = ROOT / "apps/hop-scan/manifests/files/report.py"
TRIVY = ROOT / "apps/trivy-operator"


def run_report(tmp_path, images, results):
    g = runpy.run_path(str(REPORT))
    (tmp_path / "results").mkdir()
    (tmp_path / "status").write_text("ok")
    (tmp_path / "images.sorted").write_text("\n".join(images) + "\n")
    for i, text in results.items():
        (tmp_path / "results" / f"{i}.json").write_text(text)
    g["main"].__globals__["WORK"] = str(tmp_path)
    import contextlib
    import io

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        g["main"]()
    rows, hb = [], None
    for line in out.getvalue().splitlines():
        if line.startswith("hop-scan result "):
            rows.append(json.loads(line[len("hop-scan result "):]))
        elif line.startswith("hop-scan heartbeat "):
            hb = json.loads(line[len("hop-scan heartbeat "):])
    return rows, hb


def test_report_reads_a_real_trivy_json(tmp_path):
    doc = json.loads(FIX.read_text())
    assert "Results" in doc and doc["Results"][0]["Vulnerabilities"], "fixture is a real scan"
    rows, hb = run_report(tmp_path, ["a/ok:1"], {0: FIX.read_text()})
    (row,) = rows
    sev = {}
    for r in doc["Results"]:
        for v in r["Vulnerabilities"]:
            sev[v["Severity"].lower()] = sev.get(v["Severity"].lower(), 0) + 1
    for k in ("critical", "high", "medium", "low", "unknown"):
        assert row[k] == sev.get(k, 0), k
    assert row["error"] is None and hb["healthy"] is True and hb["scanned"] == 1


def test_report_error_rows_and_clean_scans(tmp_path):
    clean = json.dumps({"SchemaVersion": 2, "ArtifactName": "x", "Results": [{"Target": "t", "Class": "os-pkgs"}]})
    nores = json.dumps({"SchemaVersion": 2, "ArtifactName": "x"})
    rows, hb = run_report(tmp_path, ["a:1", "b:1", "c:1", "d:1"],
                          {0: FIX.read_text(), 1: clean, 2: "{ truncated"})  # d: no file at all
    by = {r["image"]: r for r in rows}
    assert by["a:1"]["medium"] == 4 and by["a:1"]["error"] is None
    assert by["b:1"]["critical"] == 0 and by["b:1"]["error"] is None, "Vulnerabilities absent = clean"
    assert by["c:1"]["error"] and by["c:1"]["high"] is None, "unparseable output is an error row"
    assert by["d:1"]["error"] and by["d:1"]["critical"] is None, "missing output is an error row"
    assert (hb["scanned"], hb["failed"], hb["images"]) == (2, 2, 4) and hb["healthy"] is True
    del nores


# ------------------------------------------------------------------ chart render contract
def _helm(*args):
    return subprocess.run(["helm", *args], capture_output=True, text=True, timeout=240)


@pytest.fixture(scope="module")
def chart(tmp_path_factory):
    if not shutil.which("helm"):
        if os.environ.get("CI") == "true":
            pytest.fail("helm missing in CI")
        pytest.skip("helm not installed")
    app = yaml.safe_load((ROOT / "apps/root/templates/trivy-operator.yaml").read_text()
                         .replace("{{ .Values.repoURL }}", "x").replace("{{ .Values.targetRevision }}", "m")
                         .replace("{{ .Values.destination.server }}", "s"))
    src = next(s for s in app["spec"]["sources"] if s.get("chart"))
    work = tmp_path_factory.mktemp("chart")
    pull = _helm("pull", src["chart"], "--repo", src["repoURL"], "--version", src["targetRevision"],
                 "--untar", "--untardir", str(work))
    if pull.returncode != 0:
        if os.environ.get("CI") == "true":
            pytest.fail(f"cannot pull the pinned chart: {pull.stderr}")
        pytest.skip(f"cannot pull the pinned chart (offline?): {pull.stderr[:200]}")
    d = work / src["chart"]
    r = _helm("template", "trivy-operator", str(d), "-n", "trivy-system", "-f", str(TRIVY / "values.yaml"))
    assert r.returncode == 0, r.stderr
    docs = [x for x in yaml.safe_load_all(r.stdout) if x]
    return d, docs


def test_server_pod_carries_the_label_the_networkpolicy_selects(chart):
    _, docs = chart
    (sts,) = [d for d in docs if d["kind"] == "StatefulSet"]
    labels = sts["spec"]["template"]["metadata"]["labels"]
    (np,) = [d for d in yaml.safe_load_all((TRIVY / "manifests/networkpolicy.yaml").read_text()) if d]
    for k, v in np["spec"]["podSelector"]["matchLabels"].items():
        assert labels.get(k) == v, (k, labels)
    svc = next(d for d in docs if d["kind"] == "Service" and d["metadata"]["name"] == "trivy-service")
    assert svc["spec"]["ports"][0]["port"] == 4954
    assert np["spec"]["ingress"][0]["ports"][0]["port"] == 4954


def test_scan_job_label_and_operator_label_are_rendered(chart):
    _, docs = chart
    cms = " ".join(str(d.get("data")) for d in docs if d["kind"] == "ConfigMap")
    assert "trivy-operator.scan-job=true" in cms
    (dep,) = [d for d in docs if d["kind"] == "Deployment"]
    assert dep["spec"]["template"]["metadata"]["labels"]["app.kubernetes.io/name"] == "trivy-operator"


def test_metrics_service_port_name_matches_the_scrape(chart):
    _, docs = chart
    scrape = yaml.safe_load((TRIVY / "manifests/vmservicescrape.yaml").read_text())
    svcs = [d for d in docs if d["kind"] == "Service"
            and all(d["metadata"]["labels"].get(k) == v
                    for k, v in scrape["spec"]["selector"]["matchLabels"].items())]
    assert len(svcs) == 1, "the scrape selector must match exactly the operator Service"
    assert [p["name"] for p in svcs[0]["spec"]["ports"]] == ["metrics"] == [scrape["spec"]["endpoints"][0]["port"]]


def test_token_secret_keys_match_what_the_chart_reads(chart):
    d, docs = chart
    assert not [x for x in docs if x["kind"] == "Secret" and x["metadata"]["name"] == "trivy-operator-trivy-config"], \
        "existingSecret: the chart must not render its own copy"
    (sts,) = [x for x in docs if x["kind"] == "StatefulSet"]
    refs = [e["secretRef"]["name"] for e in sts["spec"]["template"]["spec"]["containers"][0]["envFrom"] if "secretRef" in e]
    assert "trivy-operator-trivy-config" in refs, "server env (TRIVY_TOKEN) comes from this Secret"
    tmpl = "\n".join(p.read_text() for p in (d / "templates").rglob("*") if p.is_file())
    assert re.search(r"trivy\.serverToken", tmpl), "scan jobs read key trivy.serverToken"
    hop = (ROOT / "apps/hop-scan/manifests/cronjob.yaml").read_text()
    assert "name: trivy-server-token" in hop and "TRIVY_TOKEN" in hop
