"""grafana-webhook receiver — the re-pointed "AI Helper Webhook" contact point.

A Grafana alert POST → build the alert fact sheet (frank-facts) → wake the agent
to triage it → deliver the narrative to Telegram (deterministic fallback on
timeout). `GET /healthz` → 200 (the cutover verifies this BEFORE re-pointing the
contact point). stdlib http.server. `process_request` is the testable core.
"""
from __future__ import annotations
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from frank_facts import facts
from tg_bridge import bridge

PORT = int(os.environ.get("GRAFANA_WEBHOOK_PORT", "8090"))


def _render_alert(alert: dict, sheet: dict) -> str:
    """Deterministic alert summary (the fallback when the agent times out)."""
    name = alert.get("alertname") or alert.get("labels", {}).get("alertname", "alert")
    extra = ", ".join(f"{k}={v}" for k, v in sheet.items() if k != "alertname") or "no extra facts"
    return f"Grafana alert firing: {name}. {extra}."


def handle_alert(alert_labels: dict) -> None:
    """Triage one firing alert: facts → agent narrative → Telegram (with fallback)."""
    sheet = facts.build_for_alert(alert_labels)
    fallback = _render_alert(alert_labels, sheet)
    prompt = ("A Grafana alert is firing. Investigate and explain what it means + likely cause, "
              "using ONLY the facts below. Reply as JSON {\"text\": \"<narrative>\"}.\n\n"
              f"alert={json.dumps(alert_labels)}\nfacts={json.dumps(sheet)}")
    resp = bridge.session_send(prompt, session_id="alert-agent-grafana")
    bridge.deliver(resp, fallback)


def handle_webhook(body: dict) -> int:
    """Process a Grafana webhook body; return the count of firing alerts triaged."""
    n = 0
    for alert in body.get("alerts", []):
        if alert.get("status", "firing") != "firing":
            continue
        labels = dict(alert.get("labels", {}))
        handle_alert(labels)
        n += 1
    return n


def process_request(method: str, path: str, body: bytes) -> tuple[int, dict]:
    """Pure request core (testable without a socket)."""
    if method == "GET" and path == "/healthz":
        return 200, {"status": "ok"}
    if method != "POST":
        return 404, {"error": "not found"}
    try:
        payload = json.loads(body or b"{}")
    except (ValueError, TypeError):
        return 400, {"error": "bad json"}
    if not isinstance(payload, dict):
        return 400, {"error": "expected object"}
    triaged = handle_webhook(payload)
    return 200, {"status": "ok", "triaged": triaged}


class _Handler(BaseHTTPRequestHandler):
    def _respond(self, code: int, obj: dict):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        code, obj = process_request("GET", self.path, b"")
        self._respond(code, obj)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0") or 0)
        code, obj = process_request("POST", self.path, self.rfile.read(n))
        self._respond(code, obj)

    def log_message(self, *a):  # quiet
        pass


def serve() -> None:  # pragma: no cover - network loop
    server = ThreadingHTTPServer(("0.0.0.0", PORT), _Handler)
    server.daemon_threads = True
    server.serve_forever()


if __name__ == "__main__":  # pragma: no cover
    serve()
