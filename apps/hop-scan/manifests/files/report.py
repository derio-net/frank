"""Print one `hop-scan result {json}` line per scanned Hop image, plus a heartbeat line.

Lines go to stdout -> fluent-bit -> VictoriaLogs; the update console reads them back with
VICTORIALOGS_URL. The heartbeat is printed on every run, even when nothing could be scanned
(no kubeconfig yet, tailnet down), so the Grafana dead-man's switch tells "job dead" from
"job alive but blind"; `status` carries the reason.
"""
import datetime
import json
import os

WORK = "/work"
SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN")


def read(name, default=""):
    try:
        with open(os.path.join(WORK, name)) as f:
            return f.read().strip()
    except OSError:
        return default


def counts(path):
    with open(path) as f:
        doc = json.load(f)
    out = {s.lower(): 0 for s in SEVERITIES}
    for res in doc.get("Results") or []:
        for v in res.get("Vulnerabilities") or []:
            sev = (v.get("Severity") or "UNKNOWN").lower()
            out[sev if sev in out else "unknown"] += 1
    return out


def main():
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    images = sorted({l.strip() for l in read("images.sorted").splitlines() if l.strip()})
    scanned = failed = 0
    for i, image in enumerate(images):
        row = {"cluster": "hop", "image": image, "scanned_at": now}
        try:
            row.update(counts(os.path.join(WORK, "results", f"{i}.json")))
            row["error"] = None
            scanned += 1
        except (OSError, ValueError) as exc:
            row.update({s.lower(): None for s in SEVERITIES})
            row["error"] = f"no scan result: {type(exc).__name__}"
            failed += 1
        print("hop-scan result " + json.dumps(row, sort_keys=True), flush=True)
    status = read("status", "unknown")
    print("hop-scan heartbeat " + json.dumps(
        {"cluster": "hop", "at": now, "status": status, "images": len(images),
         "scanned": scanned, "failed": failed}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
