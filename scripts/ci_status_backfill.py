#!/usr/bin/env python3
"""Re-forward Gitea Actions statuses the status bridge never delivered.

Gitea does not retry a webhook and nothing reconciles commit statuses, so a
status event the bridge missed (org hook not yet created, trigger allowlist
not yet widened, a dropped delivery) stays missing on GitHub forever. On a
quiet repo whose head does not move, `layer-25-delivery-overdue` (kind=status)
then fires indefinitely.

This prints one `stoa-status-bridge` PipelineRun per undelivered status — the
exact set ci-delivery-check counts (its `undelivered()` is loaded from the
ConfigMap), rendered from the bridge's own TriggerTemplate — so the repair
goes through the same mapping and token selection as a live event. It never
writes anything itself:

    scripts/ci_status_backfill.py --tokens DIR [repo ...]               # review
    scripts/ci_status_backfill.py --tokens DIR [repo ...] | kubectl create -f -

DIR holds the checker's token files: stoa, homelab, net (GitHub App tokens,
Secrets *-github-mirror) and gitea (Secret gitea-api-token), all in
tekton-pipelines. Stale `pending` statuses are listed on stderr and skipped
unless --include-pending: a never-served runner label would otherwise pin a
permanent pending check on GitHub.
"""
import argparse
import json
import sys
import types
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / 'apps/tekton/manifests/ci-delivery-check.yaml'
TRIGGERS = ROOT / 'apps/tekton/triggers/eventlistener.yaml'
TOKEN_NAMES = {'agentic-stoa': 'stoa', 'derio-homelab': 'homelab', 'derio-net': 'net', 'gitea': 'gitea'}


def load_checker():
    cm = next(yaml.safe_load_all(CHECKER.read_text()))
    module = types.ModuleType('ci_delivery_check')
    exec(compile(cm['data']['check.py'], str(CHECKER), 'exec'), module.__dict__)
    return module


def default_repos():
    job = list(yaml.safe_load_all(CHECKER.read_text()))[1]
    env = {e['name']: e.get('value', '') for e in
           job['spec']['jobTemplate']['spec']['template']['spec']['containers'][0]['env']}
    return sorted(set(env['MAIN_REPOS'].split() + env['PR_REPOS'].split()))


def bridge_run(repo, sha, expected, context):
    template = next(d for d in yaml.safe_load_all(TRIGGERS.read_text())
                    if d and d.get('kind') == 'TriggerTemplate'
                    and d['metadata']['name'] == 'stoa-status-bridge-template')
    state, description, url = expected
    values = {'repo-full-name': repo, 'revision': sha, 'state': state,
              'context': context, 'description': description, 'target-url': url}
    run = template['spec']['resourcetemplates'][0]
    for param in run['spec']['params']:
        param['value'] = values[param['name']]
    return run


def plan(client, repos, now, include_pending=False):
    """(PipelineRuns to create, [(repo, sha, status)] skipped as stale pending)."""
    checker = load_checker()
    runs, skipped = [], []
    for repo in repos:
        shas = {client.head(repo)[0]} | {sha for _, sha in client.pulls(repo)}
        for sha, status, expected in checker.undelivered(client, repo, shas, now):
            if expected[0] == 'pending' and not include_pending:
                skipped.append((repo, sha, status))
                continue
            runs.append(bridge_run(repo, sha, expected, status['context']))
    return runs, skipped


def live_client(tokens, gitea_api, gitea_web):
    checker = load_checker()

    def request(forge, repo, path):
        key = 'gitea' if forge == 'gitea' else repo.split('/')[0]
        token = (Path(tokens) / TOKEN_NAMES[key]).read_text().strip()
        base = gitea_api if forge == 'gitea' else 'https://api.github.com'
        req = urllib.request.Request(base + path, headers={
            'Authorization': 'token ' + token, 'Accept': 'application/json',
            'User-Agent': 'frank-ci-status-backfill'})
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.load(response)

    client = checker.API({}, request=request)
    client.gitea_web_url = gitea_web
    client.deadline = float('inf')
    return client


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('repos', nargs='*', help='owner/name (default: every repo the checker covers)')
    parser.add_argument('--tokens', required=True, help='directory holding stoa, homelab, net, gitea token files')
    parser.add_argument('--gitea-api', default='http://192.168.55.209:3000/api/v1')
    parser.add_argument('--gitea-web', default='http://192.168.55.209:3000/',
                        help="Gitea server.ROOT_URL (the checker's GITEA_WEB_URL)")
    parser.add_argument('--include-pending', action='store_true')
    args = parser.parse_args(argv)

    client = live_client(args.tokens, args.gitea_api, args.gitea_web)
    runs, skipped = plan(client, args.repos or default_repos(), datetime.now(timezone.utc),
                         args.include_pending)
    for repo, sha, status in skipped:
        print(f'skip pending {repo}@{sha[:8]} {status["context"]!r} (--include-pending to forward)',
              file=sys.stderr)
    print(f'{len(runs)} undelivered status(es) to re-forward', file=sys.stderr)
    if runs:
        yaml.safe_dump_all(runs, sys.stdout, sort_keys=False)
    return 0


if __name__ == '__main__':
    sys.exit(main())
