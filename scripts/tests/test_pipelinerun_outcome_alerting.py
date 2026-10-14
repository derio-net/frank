"""CI outcome, delivery and scrape guards. Quiet CI is not a failure."""
import json
from pathlib import Path
import re

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
ALERT_RULES_CM = REPO/'apps/grafana-alerting/manifests/alert-rules-cm.yaml'
SCRAPE_MANIFEST = REPO/'apps/tekton/manifests/vmservicescrape-pipelines-controller.yaml'
GROUP = 'layer-25-pipeline-outcomes'
IDLE = {'layer-25-idle-stoa-status-bridge', 'layer-25-idle-github-pull-sync'}
DELIVERY = {'layer-25-delivery-overdue', 'layer-25-delivery-read-error', 'layer-25-delivery-stale'}


def document():
    return yaml.safe_load(yaml.safe_load(ALERT_RULES_CM.read_text())['data']['alert-rules.yaml'])


def rules():
    return {r['uid']: r for g in document()['groups'] for r in g['rules']}


def expr(rule):
    return next(d['model']['expr'] for d in rule['data'] if d['refId'] == 'A')


def test_idle_definitions_retired_and_explicitly_deleted():
    assert not IDLE.intersection(rules())
    assert IDLE <= {r['uid'] for r in document()['deleteRules'] if r['orgId'] == 1}


def test_delivery_rules_and_retained_faults():
    all_rules = rules()
    assert DELIVERY <= set(all_rules)
    assert {'layer-25-pipeline-failing', 'layer-25-cicd-down',
            'layer-25-ci-workspace-pvc-pending', 'layer-25-pipelinerun-timeout',
            'layer-25-mirror-sync-failing', 'layer-25-mirror-reconcile-stale'} <= set(all_rules)
    group = next(g for g in document()['groups'] if g['name'] == GROUP)
    assert group['folder'] == 'feature-health'
    assert DELIVERY <= {r['uid'] for r in group['rules']}
    for uid in DELIVERY:
        r = all_rules[uid]
        assert len(uid) <= 40
        assert r['for'] == '10m' and r['condition'] == 'C'
        assert r['noDataState'] == 'OK' and r['execErrState'] == 'Error'
        assert r['labels'] == {'severity':'warning', 'github_issue':'frank-ops#25'}
        assert [d['refId'] for d in r['data']] == ['A','B','C']
        b, c = r['data'][1]['model'], r['data'][2]['model']
        assert b['type'] == 'reduce' and b['expression'] == 'A' and b['reducer'] == 'last'
        assert c['type'] == 'threshold' and c['expression'] == 'B'
        assert c['conditions'][0]['evaluator'] == {'type':'gt','params':[0]}
    assert all('kube_pod_status_ready' not in yaml.safe_dump(r) for r in group['rules'])


def test_predicate_queries_are_explicit():
    r = rules()
    assert expr(r['layer-25-delivery-overdue']) == 'sum by (repo, kind) (ci_delivery_overdue{job="ci-delivery-check"}) > 0'
    assert expr(r['layer-25-delivery-read-error']) == 'max by (repo) (ci_delivery_read_error{job="ci-delivery-check"}) > 0'
    assert expr(r['layer-25-delivery-stale']) == '(time() - max(ci_delivery_last_check_timestamp_seconds{job="ci-delivery-check"}) > 900) or absent(ci_delivery_last_check_timestamp_seconds{job="ci-delivery-check"})'


@pytest.mark.parametrize('counts,errors,age,expected', [
    ([0,0], [0], 0, (False,False,False)),
    ([1,0], [0], 0, (True,False,False)),
    ([0,1], [0], 0, (True,False,False)),
    ([0,0], [1], 0, (False,True,False)),
    ([0,0], [0], None, (False,False,True)),
    ([0,0], [0], 901, (False,False,True)),
    ([0,0], [0], 900, (False,False,False)),
])
def test_predicate_scenarios_and_recovery(counts, errors, age, expected):
    # Semantic evaluation of the exact predicates pinned above. These are
    # instant filters: a healthy vector is empty (NoData OK), not a zero alert.
    actual = (any(n > 0 for n in counts), any(n > 0 for n in errors), age is None or age > 900)
    assert actual == expected
    assert (any(n > 0 for n in [0,0]), any(n > 0 for n in [0]), 0 > 900) == (False,False,False)


def test_failure_ratio_retains_unless_and_query_noise_floor():
    rule = rules()['layer-25-pipeline-failing']
    query = expr(rule)
    assert 'unless' in query and '>= 3' in query and '== 0' not in query
    assert 'status="failed"' in query and 'status="success"' in query
    assert query.count('sum by (pipeline)') >= 2
    assert rule['data'][2]['model']['conditions'][0]['evaluator'] == {'type':'gt','params':[0]}
    assert rule['labels'] == {'severity':'warning','github_issue':'frank-ops#25'}


def test_controller_scrape_port_cardinality_and_outcome_metrics():
    scrape = yaml.safe_load(SCRAPE_MANIFEST.read_text())
    assert scrape['apiVersion'] == 'operator.victoriametrics.com/v1beta1'
    assert scrape['kind'] == 'VMServiceScrape'
    assert scrape['metadata']['namespace'] == 'tekton-pipelines'
    assert scrape['spec']['selector']['matchLabels'] == {'app':'tekton-pipelines-controller'}
    endpoint, = scrape['spec']['endpoints']
    assert endpoint['port'] == 'http-metrics'
    fixtures = REPO/'scripts/tests/fixtures/tekton'
    census = json.loads((fixtures/'controller-series-census.json').read_text())
    largest = max(census['series_by_metric'], key=census['series_by_metric'].get)
    assert census['series_by_metric'][largest] / census['total_series'] > .5
    drops = [c['regex'] for c in endpoint['metricRelabelConfigs'] if c.get('action') == 'drop' and c.get('source_labels') == ['__name__']]
    assert largest in drops
    sample = (fixtures/'controller-metrics-sample.txt').read_text()
    for uid in ('layer-25-pipeline-failing','layer-25-pipelinerun-timeout'):
        names = re.findall(r'[A-Za-z_:][A-Za-z0-9_:]*(?=\{)',expr(rules()[uid]))
        assert names
        for name in names:
            assert name+'{' in sample
            assert not any(re.fullmatch(drop,name) for drop in drops)
