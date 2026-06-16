"""frank-facts CLI — deterministic observability facts as JSON on stdout.

Subcommands the alert-agent's tools + the surge gate call. stdlib-only.
Windows default to sensible spans; override with --since/--until (ISO 8601).
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

from . import facts, surge


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _emit(obj) -> int:
    json.dump(obj, sys.stdout)
    sys.stdout.write("\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="frank-facts", description="Deterministic observability facts (JSON).")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("surge-compute", help="the deterministic surge gate verdict")

    sp = sub.add_parser("surge", help="surge fact sheet for a window")
    sp.add_argument("--since"); sp.add_argument("--until")

    dg = sub.add_parser("digest", help="daily digest fact sheet")
    dg.add_argument("--since"); dg.add_argument("--until")

    sub.add_parser("alert", help="alert fact sheet (alert JSON on stdin)")

    for name in ("top-attacker-ips", "top-scanned-paths", "scan-patterns", "crowdsec"):
        s = sub.add_parser(name, help=f"{name} over a window")
        s.add_argument("--since"); s.add_argument("--until")

    args = p.parse_args(argv)

    def window(default_hours: int):
        until = _iso(args.until) if getattr(args, "until", None) else _now()
        since = _iso(args.since) if getattr(args, "since", None) else until - timedelta(hours=default_hours)
        return since, until

    if args.cmd == "surge-compute":
        return _emit(surge.compute())
    if args.cmd == "surge":
        s, u = window(1)
        return _emit(facts.build_for_surge(s, u))
    if args.cmd == "digest":
        u = _iso(args.until) if args.until else _now().replace(hour=0, minute=0, second=0, microsecond=0)
        s = _iso(args.since) if args.since else u - timedelta(days=1)
        return _emit(facts.build_for_digest(s, u, _now()))
    if args.cmd == "alert":
        return _emit(facts.build_for_alert(json.load(sys.stdin)))
    if args.cmd == "top-attacker-ips":
        s, u = window(24); return _emit(facts.top_attacker_ips(s, u))
    if args.cmd == "top-scanned-paths":
        s, u = window(24); return _emit(facts.top_scanned_paths(s, u))
    if args.cmd == "scan-patterns":
        s, u = window(24); return _emit(facts.scan_pattern_counts(s, u))
    if args.cmd == "crowdsec":
        s, u = window(24); return _emit(facts.crowdsec_activity(s, u))
    return 2


if __name__ == "__main__":
    sys.exit(main())
