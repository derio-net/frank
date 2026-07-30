"""Guard the Headscale API-key checker and its Grafana alerts."""

from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "clusters/hop/apps/headscale/manifests"
ALERTS = REPO / "apps/grafana-alerting/manifests/alert-rules-cm.yaml"


def _checker():
    spec = spec_from_file_location("headscale_key_expiry", APP / "files/key-expiry-check.py")
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _payload(now, offsets):
    return {
        "apiKeys": [
            {
                "prefix": prefix,
                "expiration": (now + timedelta(days=days)).isoformat().replace("+00:00", "Z"),
            }
            for prefix, days in offsets.items()
        ]
    }


def _rules():
    cm = yaml.safe_load(ALERTS.read_text())
    rules = {}
    for blob in cm["data"].values():
        for group in yaml.safe_load(blob).get("groups", []):
            for rule in group.get("rules", []):
                rules[rule.get("uid")] = rule
    return rules


def test_checker_tracks_the_earliest_expected_key():
    checker = _checker()
    now = datetime(2026, 7, 30, tzinfo=timezone.utc)
    result = checker.evaluate_keys(_payload(now, {"key-a": 365, "key-b": 31}), {"key-a", "key-b"}, 30, now)
    assert result == {"verdict": "ok", "alert": False, "reason": "none", "min_days_left": 31}


def test_checker_accepts_headscale_nanosecond_timestamps():
    checker = _checker()
    parsed = checker.parse_expiration("2027-07-29T08:34:39.581863392Z")
    assert parsed == datetime(2027, 7, 29, 8, 34, 39, 581863, tzinfo=timezone.utc)


def test_checker_warns_at_threshold_and_errors_if_a_consumer_key_disappears():
    checker = _checker()
    now = datetime(2026, 7, 30, tzinfo=timezone.utc)
    warning = checker.evaluate_keys(_payload(now, {"key-a": 30, "key-b": 365}), {"key-a", "key-b"}, 30, now)
    missing = checker.evaluate_keys(_payload(now, {"key-a": 365}), {"key-a", "key-b"}, 30, now)
    assert warning["verdict"] == "warn" and warning["alert"] is True
    assert missing == {"verdict": "error", "alert": True, "reason": "expected-key-missing"}


def test_cronjob_uses_the_headplane_secret_and_pinned_non_root_image():
    cron = yaml.safe_load((APP / "key-expiry-cronjob.yaml").read_text())
    assert cron["spec"]["jobTemplate"]["metadata"]["labels"] == {
        "app.kubernetes.io/name": "headscale-api-key-expiry"
    }
    pod = cron["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    container = pod["containers"][0]
    env = {item["name"]: item for item in container["env"]}
    assert env["API_KEY"]["valueFrom"]["secretKeyRef"] == {"name": "headplane-api-key", "key": "api-key"}
    assert env["WARN_DAYS"]["value"] == "30"
    assert set(env["EXPECTED_PREFIXES"]["value"].split(",")) == {"8HpmMnl", "lTe41sn"}
    assert "@sha256:" in container["image"]
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert container["securityContext"]["readOnlyRootFilesystem"] is True


def test_kustomize_mounts_the_checker_and_headscale_prunes_old_hashes():
    kustomization = yaml.safe_load((APP / "kustomization.yaml").read_text())
    assert "key-expiry-cronjob.yaml" in kustomization["resources"]
    assert kustomization["configMapGenerator"][0]["files"] == ["files/key-expiry-check.py"]
    app = (REPO / "clusters/hop/apps/root/templates/headscale.yaml").read_text()
    assert "automated:\n      # Required for hash-suffixed checker script ConfigMaps.\n      prune: true" in app


def test_expiry_alert_pages_on_alert_heartbeats():
    rule = _rules()["headscale-api-key-expiry-warning"]
    query = next(item for item in rule["data"] if item["refId"] == "A")["model"]
    condition = next(item for item in rule["data"] if item["refId"] == "C")["model"]["conditions"][0]["evaluator"]
    assert query["queryType"] == "stats"
    assert 'log:"headscale-api-key-expiry-check"' in query["expr"]
    assert 'log:"alert=true"' in query["expr"]
    assert condition == {"type": "gt", "params": [0]}
    assert rule["labels"]["telegram_direct"] == "true"


def test_deadman_pages_when_hourly_heartbeat_stops():
    rule = _rules()["headscale-api-key-expiry-heartbeat-stale"]
    query = next(item for item in rule["data"] if item["refId"] == "A")
    condition = next(item for item in rule["data"] if item["refId"] == "C")["model"]["conditions"][0]["evaluator"]
    assert query["relativeTimeRange"]["from"] == 10800
    assert "stats count() as value" in query["model"]["expr"]
    assert condition == {"type": "lt", "params": [1]}
    assert rule["for"] == "1h"
    assert rule["noDataState"] == "OK"
    assert rule["execErrState"] == "Error"
