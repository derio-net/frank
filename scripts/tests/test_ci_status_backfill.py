"""Backfill re-forwards exactly what ci-delivery-check reports as undelivered.

A status event the bridge never saw (hook not yet created, trigger filter not
yet widened, a dropped delivery) is never retried, so it stays missing on
GitHub and the delivery-overdue alert cannot clear while the repo is quiet.
The backfill must agree with the checker on WHAT is missing (one comparison,
loaded from the checker's ConfigMap) and with the trigger on HOW it is posted
(the bridge's own TriggerTemplate), or it would repair a different set than
the alert measures.
"""
from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 19, 20, tzinfo=timezone.utc)
REPO = 'derio-net/vibe-kanban'


@pytest.fixture
def backfill():
    spec = spec_from_file_location('ci_status_backfill', ROOT / 'scripts/ci_status_backfill.py')
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def status(context, state, age=60, id=1, description='done'):
    return dict(context=context, state=state, id=id, description=description,
                target_url='http://192.168.55.209:3000/run/1',
                created_at=(NOW - timedelta(minutes=age)).isoformat())


class Forge:
    def __init__(self, source, dest=()):
        self.source, self.dest = list(source), list(dest)

    def repo(self, repo):
        pass

    def default_branch(self, repo):
        return 'main'

    def head(self, repo):
        return 'a' * 40, NOW - timedelta(hours=14)

    def pulls(self, repo):
        return []

    def branch(self, repo, ref):
        return 'a' * 40

    def commit_exists(self, repo, sha):
        return True

    def statuses(self, forge, repo, sha):
        return self.source if forge == 'gitea' else self.dest


def params(run):
    return {p['name']: p['value'] for p in run['spec']['params']}


def test_checker_exposes_the_comparison_it_alerts_on(backfill):
    checker = backfill.load_checker()
    forge = Forge([status('ci / test (push)', 'skipped')])
    missing = checker.undelivered(forge, REPO, ['a' * 40], NOW)
    assert [(sha, s['context'], expected) for sha, s, expected in missing] == [
        ('a' * 40, 'ci / test (push)', ('success', 'Gitea: skipped', 'http://192.168.55.209:3000/run/1'))]
    assert checker.check(forge, [REPO], [], NOW)['counts'][REPO]['status'] == 1


def test_emits_one_bridge_run_per_undelivered_status(backfill):
    forge = Forge(
        [status('ci / test (push)', 'skipped', id=1),
         status('ci / lint (push)', 'success', id=2),
         status('tekton/ci', 'failure', id=3)],
        dest=[dict(status('gitea-actions/ci / lint (push)', 'success'))])
    runs, skipped = backfill.plan(forge, [REPO], NOW)
    assert skipped == []
    assert len(runs) == 1
    run = runs[0]
    assert run['kind'] == 'PipelineRun'
    assert run['metadata']['generateName'] == 'stoa-status-bridge-'
    assert run['spec']['pipelineRef'] == {'name': 'stoa-status-bridge'}
    # Trigger template carries the placement, not a hand-copied one.
    assert run['spec']['taskRunTemplate']['podTemplate']['nodeSelector']
    assert params(run) == {
        'repo-full-name': REPO, 'revision': 'a' * 40, 'state': 'success',
        'context': 'ci / test (push)', 'description': 'Gitea: skipped',
        'target-url': 'http://192.168.55.209:3000/run/1'}
    assert '$(' not in str(run)


def test_pending_is_reported_not_forwarded_by_default(backfill):
    # A stale 'Waiting to run' (e.g. a runner label nobody serves) would pin
    # a permanent yellow on GitHub; forwarding it is an explicit choice.
    forge = Forge([status('ci / test-macos (push)', 'pending', description='Waiting to run')])
    runs, skipped = backfill.plan(forge, [REPO], NOW)
    assert runs == []
    assert [(sha, s['context']) for _, sha, s in skipped] == [('a' * 40, 'ci / test-macos (push)')]
    runs, skipped = backfill.plan(forge, [REPO], NOW, include_pending=True)
    assert params(runs[0])['state'] == 'pending' and skipped == []


def test_fresh_statuses_are_left_to_the_live_bridge(backfill):
    forge = Forge([status('ci / test (push)', 'success', age=5)])
    assert backfill.plan(forge, [REPO], NOW) == ([], [])


def test_default_repos_are_the_checkers(backfill):
    assert 'derio-net/vibe-kanban' in backfill.default_repos()
    assert 'derio-homelab/kid-laptops' in backfill.default_repos()
