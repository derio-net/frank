#!/usr/bin/env python3
"""Dotted-path reader for .blog-craft.yaml (spec D4).

The seam that lets shell tooling (blog-post-create.sh) read the config it
requires instead of hardcoding paths (#39 item 1).

Usage:
  blog_config.py --config <path> get <dotted.key> [--default <value>]

Prints the resolved value. A missing key exits 1 unless --default is given.
Non-scalar values print as compact YAML (flow style) — callers wanting
structure should read the YAML directly.
"""
from __future__ import annotations

import argparse
import sys

import yaml


def dig(cfg, dotted: str):
    cur = cfg
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    get = sub.add_parser("get")
    get.add_argument("key")
    get.add_argument("--default")
    a = ap.parse_args(argv)

    with open(a.config) as f:
        cfg = yaml.safe_load(f) or {}
    val = dig(cfg, a.key)
    if val is None:
        if a.default is None:
            print(f"key not found: {a.key}", file=sys.stderr)
            return 1
        print(a.default)
        return 0
    if isinstance(val, (str, int, float, bool)):
        print(val)
    else:
        print(yaml.safe_dump(val, default_flow_style=True).strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
