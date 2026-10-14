"""Injected semantic forge clients, not purported captures of private APIs."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import types

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'apps/tekton/manifests/ci-delivery-check.yaml'
NOW = datetime(2026, 10, 14, tzinfo=timezone.utc)
REPO = 'agentic-stoa/hum'
API_SHA = '0123456789abcdef' * 2 + '01234567'


@pytest.fixture
def checker():
    cm = next(yaml.safe_load_all(MANIFEST.read_text()))
    module = types.ModuleType('delivery')
    exec(compile(cm['data']['check.py'], str(MANIFEST), 'exec'), module.__dict__)
    return module


class Forge:
    def __init__(self):
        self.refs = {'main': 'head', 'sync-pr-7': 'pr'}
        self.prs = [(7, 'pr')]
        self.age = timedelta(hours=1)
        self.source = []
        self.dest = []
        self.calls = []
        self.commits = {'head', 'pr'}

    def repo(self, repo):
        self.calls.append(('repo', repo))

    def head(self, repo):
        return 'head', NOW - self.age

    def pulls(self, repo):
        return self.prs

    def commit_time(self, repo, sha):
        return NOW - self.age

    def branch(self, repo, ref):
        return self.refs.get(ref)

    def commit_exists(self, repo, sha):
        self.calls.append(('commit', repo, sha))
        return sha in self.commits

    def statuses(self, forge, repo, sha):
        self.calls.append((forge, repo, sha))
        return self.source if forge == 'gitea' else self.dest


def status(context='build', state='success', age=20, id=1, **kw):
    return dict(context=context, state=state, created_at=(NOW-timedelta(minutes=age)).isoformat(),
                id=id, description='done', target_url='https://ci/run', **kw)


def gitea_api_status(**kwargs):
    """Schema-shaped test input from the authorized live-read handoff.

    Not a raw capture: values are test examples; creator/API URLs are redacted.
    Gitea's observed list uses `status`, not GitHub/webhook `state`.
    """
    item = status(**kwargs)
    item['status'] = item.pop('state')
    item.update(creator={'login':'redacted'}, url='https://redacted.invalid/status',
                updated_at=item['created_at'])
    return item


def check(c, f, repo=REPO):
    return c.check(f, [repo], [repo] if repo == REPO else [], NOW)


@pytest.mark.parametrize('have,age,count', [('head',60,0), (None,60,1), ('old',60,1), (None,29,0), (None,30,1)])
def test_mirror_grace_and_missing(checker, have, age, count):
    f = Forge(); f.refs['main'] = have; f.age = timedelta(minutes=age)
    assert check(checker, f)['counts'][REPO]['mirror'] == count


def test_pr_drift_and_recovery(checker):
    f = Forge(); del f.refs['sync-pr-7']
    assert check(checker, f)['counts'][REPO]['mirror'] == 1
    f.refs['sync-pr-7'] = 'pr'
    assert check(checker, f)['counts'][REPO] == {'mirror': 0, 'status': 0}


@pytest.mark.parametrize('state,description', [('success','done'), ('skipped','Gitea: skipped'), ('warning','Gitea: warning')])
def test_bridge_mapping_exact_sha_latest_and_recovery(checker, state, description):
    f = Forge(); f.prs = [(7,'head')]; f.refs['sync-pr-7'] = 'head'
    f.source = [status(state=state), status(state='pending',age=30,id=2), status(context='tektonfoo')]
    assert check(checker, f)['counts'][REPO]['status'] == 1
    f.dest = [status(context='gitea-actions/build',state='success')]
    f.dest[0]['description'] = description
    assert check(checker, f)['counts'][REPO]['status'] == 0
    assert f.calls.count(('gitea',REPO,'head')) == 2  # once per invocation, not per ref


@pytest.mark.parametrize('field,value', [('state','pending'), ('description','old'), ('target_url','https://old')])
def test_stale_forwarding(checker, field, value):
    f = Forge(); f.prs = []; f.source = [status()]; f.dest = [status(context='gitea-actions/build')]
    f.dest[0][field] = value
    assert check(checker, f)['counts'][REPO]['status'] == 1
    f.source[0]['created_at'] = (NOW-timedelta(minutes=9)).isoformat()
    assert check(checker, f)['counts'][REPO]['status'] == 0


def test_no_status_inference_on_unmirrored_commit_or_other_org(checker):
    f = Forge(); f.refs = {}; f.commits = set(); f.source = [status()]
    assert check(checker,f)['counts'][REPO]['status'] == 0

    assert not any(call[0] == 'gitea' for call in f.calls)
    f = Forge(); check(checker,f,'derio-homelab/kid-laptops')
    assert not any(call[0] == 'gitea' for call in f.calls)


def test_status_delivery_checked_on_readable_commit_despite_branch_drift(checker):
    f = Forge(); f.prs = [(7, 'head')]; f.refs = {'main':'other'}
    f.age = timedelta(minutes=20); f.source = [status(age=15)]
    result = check(checker, f)
    assert result['counts'][REPO] == {'mirror':0, 'status':1}
    assert result['errors'][REPO] == 0
    assert f.calls.count(('commit', REPO, 'head')) == 1
    assert f.calls.count(('gitea', REPO, 'head')) == 1
    f.dest = [status(context='gitea-actions/build', age=14)]
    assert check(checker, f)['counts'][REPO]['status'] == 0
    f.commits = set()
    assert check(checker, f)['counts'][REPO]['status'] == 0


@pytest.mark.parametrize('code,expected', [(404,False), (401,None), (403,None), (500,None)])
def test_commit_readability_distinguishes_absence_from_failed_reads(checker, code, expected):
    calls = []
    def request(forge, repo, path):
        calls.append(path)
        if path == f'/repos/{repo}': return {'full_name':repo}
        raise checker.urllib.error.HTTPError(path,code,'private-response',{},None)
    api = checker.API({}, request=request)
    if expected is False:
        assert api.commit_exists(REPO,'a'*40) is False
    else:
        with pytest.raises(checker.urllib.error.HTTPError): api.commit_exists(REPO,'a'*40)
    assert calls == [f'/repos/{REPO}', f'/repos/{REPO}/git/commits/'+ 'a'*40]


def test_commit_readability_verifies_repository_and_sha(checker):
    def missing_repo(*args):
        raise checker.urllib.error.HTTPError('private',404,'private',{},None)
    api = checker.API({}, request=missing_repo)
    with pytest.raises(checker.urllib.error.HTTPError): api.commit_exists(REPO,'a'*40)
    for sha in ('a'*40, 'b'*40):
        api = checker.API({}, request=lambda forge,repo,path:
                          {'full_name':repo} if path == f'/repos/{repo}' else {'sha':sha})
        if sha == 'a'*40:
            assert api.commit_exists(REPO,sha) is True
        else:
            with pytest.raises(ValueError): api.commit_exists(REPO,'a'*40)


def test_description_limit(checker):
    f = Forge(); f.prs = []; f.source = [status()]; f.source[0]['description'] = 'x'*180
    f.dest = [status(context='gitea-actions/build')]; f.dest[0]['description'] = 'x'*140
    assert check(checker,f)['counts'][REPO]['status'] == 0
    f.dest[0]['description'] = 'x'*180
    assert check(checker,f)['counts'][REPO]['status'] == 0


def test_destination_latest_is_not_api_order(checker):
    f = Forge(); f.prs = []; f.source = [status()]
    f.dest = [status(context='gitea-actions/build',state='pending',age=15),
              status(context='gitea-actions/build',age=30,id=2)]
    assert check(checker,f)['counts'][REPO]['status'] == 1
    f.dest.reverse()
    assert check(checker,f)['counts'][REPO]['status'] == 1
    f.dest.append(status(context='gitea-actions/build',age=15,id=3))
    assert check(checker,f)['counts'][REPO]['status'] == 0


def test_github_context_identity_is_case_insensitive(checker):
    f = Forge(); f.prs = []; f.source = [status(context='Build')]
    f.dest = [status(context='gitea-actions/Build', age=19),
              status(context='gitea-actions/build', state='failure', age=15)]
    assert check(checker, f)['counts'][REPO]['status'] == 1
    f.dest = [status(context='GITEA-ACTIONS/BUILD', age=19)]
    assert check(checker, f)['counts'][REPO]['status'] == 0


def test_source_context_collisions_follow_latest_forwarded_identity(checker):
    f = Forge(); f.prs = []
    f.source = [status(context='Build', state='failure', age=25),
                status(context='build', age=20)]
    f.dest = [status(context='GITEA-ACTIONS/BUILD', age=19)]
    assert check(checker, f)['counts'][REPO]['status'] == 0
    f.dest = []
    assert check(checker, f)['counts'][REPO]['status'] == 1
    f.source.reverse()
    assert check(checker, f)['counts'][REPO]['status'] == 1
    f.source.append(status(context='BUILD', state='pending', age=5))
    assert check(checker, f)['counts'][REPO]['status'] == 0
    # Gitea filter remains case-sensitive even though GitHub identity is not.
    f.source = [status(context='tektonBuild'), status(context='TektonBuild')]
    assert check(checker, f)['counts'][REPO]['status'] == 1


def test_coverage_and_security():
    docs = list(yaml.safe_load_all(MANIFEST.read_text()))
    pod = docs[1]['spec']['jobTemplate']['spec']['template']['spec']
    reconcile = list(yaml.safe_load_all((ROOT/'apps/tekton/manifests/mirror-reconcile.yaml').read_text()))[1]
    env = {v['name']:v.get('value') for v in pod['containers'][0]['env']}
    baseline = reconcile['spec']['jobTemplate']['spec']['template']['spec']['initContainers'][0]['env']
    for e in baseline:
        if e['name'] in ('MAIN_REPOS','PR_REPOS'):
            assert set(env[e['name']].split()) == set(e['value'].split())
    assert pod['automountServiceAccountToken'] is False
    assert pod['securityContext']['runAsNonRoot'] is True
    assert docs[1]['spec']['schedule'] == '*/5 * * * *'
    assert not any('persistentVolumeClaim' in v for v in pod['volumes'])


@pytest.mark.parametrize('forge,endpoint', [('github','pulls?state=open'), ('github','commits/head/statuses'), ('gitea','commits/head/statuses')])
def test_pagination_all_pages(checker, forge, endpoint):
    calls = []
    def request(f, repo, path):
        calls.append(path)
        return [dict(n=i) for i in range(100)] if path.endswith('page=1') else ([{'n':100}] if path.endswith('page=2') else [])
    api = checker.API({}, request=request)
    assert len(api.pages(forge,REPO,f'/repos/{REPO}/{endpoint}')) == 101
    assert len(calls) == 3


@pytest.mark.parametrize('data', [{}, None, 'secret-token', [{'bad':'shape'}]])
def test_malformed_api_results(checker, data):
    api = checker.API({},request=lambda *args: data)
    with pytest.raises((ValueError, KeyError, TypeError)):
        api.pulls(REPO)


def test_pagination_exhaustion_and_deadline(checker):
    api = checker.API({},request=lambda *args: [{}]*100)
    with pytest.raises(ValueError):
        api.pages('github',REPO,f'/repos/{REPO}/pulls?state=open')
    api.deadline = 0
    with pytest.raises(TimeoutError):
        api.get('github',REPO,'/anything')


def test_partial_page_failure_is_not_success_and_calls_are_cached(checker):
    calls = []
    def request(forge,repo,path):
        calls.append(path)
        if path.endswith('page=2'):
            raise OSError('secret-token')
        return [{'number':7,'head':{'sha':API_SHA}}]
    api = checker.API({}, request=request)
    with pytest.raises(OSError): api.pulls(REPO)
    with pytest.raises(OSError): api.pulls(REPO)
    assert sum(p.endswith('page=1') for p in calls) == 1


def test_api_adapters_gitea_branch_id_and_status_path(checker):
    calls = []
    def request(forge,repo,path):
        calls.append((forge,path))
        if path == f'/repos/{repo}': return {'full_name':repo}
        if '/branches/' in path: return {'commit':{'id':API_SHA}}
        return [gitea_api_status()] if path.endswith('page=1') else []
    api = checker.API({},request=request)
    assert api.branch(REPO,'main') == API_SHA
    assert checker.latest(api.statuses('gitea',REPO,API_SHA))['build']['state'] == 'success'
    assert any(f'/commits/{API_SHA}/statuses?' in path for forge,path in calls)
    api.repo(REPO)
    assert calls.count(('gitea',f'/repos/{REPO}')) == 1


@pytest.mark.parametrize('state', ['pending','success','error','failure','skipped','warning'])
def test_gitea_status_adapter_normalizes_observed_api_schema(checker, state):
    raw = gitea_api_status(state=state)
    api = checker.API({}, request=lambda forge,repo,path: [raw] if path.endswith('page=1') else [])
    normalized, = api.statuses('gitea',REPO,API_SHA)
    assert normalized['state'] == state
    assert checker.latest([normalized])['build']['state'] == state
    assert 'state' not in raw  # do not mutate cached API responses


@pytest.mark.parametrize('invalid', [None, '', 'unknown', 1, {}, ['success']])
def test_gitea_status_adapter_rejects_invalid_status(checker, invalid):
    raw = gitea_api_status(); raw['status'] = invalid
    # A stray state field must not silently override malformed Gitea data.
    raw['state'] = 'success'
    api = checker.API({}, request=lambda forge,repo,path: [raw] if path.endswith('page=1') else [])
    with pytest.raises(ValueError): api.statuses('gitea',REPO,API_SHA)


def test_gitea_status_adapter_requires_status_and_github_remains_unchanged(checker):
    raw = status()
    api = checker.API({}, request=lambda forge,repo,path: [raw] if path.endswith('page=1') else [])
    with pytest.raises(ValueError): api.statuses('gitea',REPO,API_SHA)
    assert api.statuses('github',REPO,API_SHA) == [raw]
    assert checker.latest(api.statuses('github',REPO,API_SHA))['build']['state'] == 'success'


def test_live_shaped_nonempty_gitea_history_does_not_blind_checker(checker):
    def request(forge,repo,path):
        if path == f'/repos/{repo}': return {'full_name':repo}
        if '/branches/' in path:
            return {'commit':{'id':API_SHA, 'sha':API_SHA,
                              'commit':{'committer':{'date':NOW.isoformat()}}}}
        if '/git/commits/' in path: return {'sha':API_SHA}
        if path.endswith('page=1'):
            return [gitea_api_status()] if forge == 'gitea' else [status(context='gitea-actions/build')]
        return []
    result = checker.check(checker.API({},request=request),[REPO],[],NOW)
    assert result['errors'][REPO] == 0
    assert result['counts'][REPO] == {'mirror':0,'status':0}


@pytest.mark.parametrize('sha', ['truncated', 'a'*39, 'a'*41, 'g'*40, 'a'*64, '', None])
def test_invalid_sha_never_certifies_matching_mirror_healthy(checker, sha):
    def request(forge, repo, path):
        if path == f'/repos/{repo}': return {'full_name':repo}
        if forge == 'github':
            return {'commit':{'sha':sha, 'commit':{'committer':{'date':NOW.isoformat()}}}}
        if '/branches/' in path: return {'commit':{'id':sha}}
        if '/git/commits/' in path: return {'sha':sha}
        return []
    api = checker.API({}, request=request)
    assert checker.check(api,[REPO],[],NOW)['errors'][REPO] == 1
    with pytest.raises(ValueError): api.branch(REPO, 'main')
    with pytest.raises(ValueError): api.commit_exists(REPO, API_SHA)


def test_valid_full_api_sha_and_invalid_pr_sha(checker):
    def request(forge, repo, path):
        if path == f'/repos/{repo}': return {'full_name':repo}
        if '/branches/' in path:
            return {'commit':{'id':API_SHA, 'sha':API_SHA,
                              'commit':{'committer':{'date':NOW.isoformat()}}}}
        if '/git/commits/' in path: return {'sha':API_SHA}
        return []
    api = checker.API({}, request=request)
    result = checker.check(api,[REPO],[],NOW)
    assert result['errors'][REPO] == 0
    assert result['counts'][REPO] == {'mirror':0,'status':0}
    api = checker.API({}, request=lambda forge,repo,path:
                      [{'number':7,'head':{'sha':'truncated'}}] if path.endswith('page=1') else [])
    with pytest.raises(ValueError): api.pulls(REPO)


def test_malformed_status_fails_check_and_other_repo_still_checked(checker):
    f = Forge(); f.source = [{'context':'broken'}]
    result = checker.check(f,[REPO,'derio-homelab/kid-laptops'],[],NOW)
    assert result['errors'][REPO] == 1
    assert result['errors']['derio-homelab/kid-laptops'] == 0
    assert checker.finish(result,NOW,send=lambda *a,**kw: None) == 1


def test_pushgateway_scrape_preserves_group_job_label():
    scrape = yaml.safe_load((ROOT/'apps/pushgateway/manifests/vmservicescrape.yaml').read_text())
    assert scrape['spec']['endpoints'][0]['honorLabels'] is True


def test_bridge_description_mapping_contract():
    task = yaml.safe_load((ROOT/'apps/tekton/tasks/github-status.yaml').read_text())
    script = task['spec']['steps'][0]['args'][0]
    assert 'D=$(json_escape "$DESCRIPTION")' in script


@pytest.mark.parametrize('code', [401,403,404,500])
def test_unreadable_repository_not_missing_branch(checker, code):
    def request(*args):
        raise checker.urllib.error.HTTPError('secret-token',code,'secret-token',{},None)
    api = checker.API({}, request=request)
    result = checker.check(api,[REPO],[],NOW)
    assert result['errors'][REPO] == 1
    assert result['counts'][REPO]['mirror'] == 0
    assert 'secret-token' not in str(result)


def test_verified_repo_missing_branch_and_malformed_head(checker):
    def request(forge,repo,path):
        if path.endswith('/'+repo):
            return {'full_name':repo}
        raise checker.urllib.error.HTTPError(path,404,'missing',{},None)
    api = checker.API({},request=request)
    assert api.branch(REPO,'main') is None
    api = checker.API({},request=lambda *args: {'commit':{'id':None}})
    with pytest.raises((ValueError, KeyError)):
        api.head(REPO)


def test_token_selection_and_unreadable_tokens(checker, tmp_path, monkeypatch):
    stoa = tmp_path/'stoa'; stoa.write_text('stoa-secret')
    homelab = tmp_path/'homelab'; homelab.write_text('homelab-secret')
    auth = []
    class Response:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def read(self): return b'{}'
    def urlopen(req, **kwargs):
        auth.append(req.get_header('Authorization')); return Response()
    monkeypatch.setattr(checker.urllib.request,'urlopen',urlopen)
    api = checker.API({'agentic-stoa':str(stoa),'derio-homelab':str(homelab)})
    api.http('github',REPO,'/test'); api.http('github','derio-homelab/kid-laptops','/test')
    assert auth == ['token stoa-secret','token homelab-secret']
    homelab.unlink()
    with pytest.raises(OSError): api.http('github','derio-homelab/kid-laptops','/test')


def test_partial_failure_snapshot_recovery_replaces_findings(checker):
    f = Forge(); f.refs = {}
    first = check(checker,f)
    def bad(*args): raise ValueError('secret-token')
    f.repo = bad
    failed = check(checker,f)
    assert failed['errors'][REPO] == 1
    assert 'secret-token' not in str(failed)
    f = Forge(); f.prs = []
    recovered = check(checker,f)
    published = []
    checker.publish(first,now=NOW,send=lambda req,**kw: published.append(req))
    checker.publish(failed,now=NOW,send=lambda req,**kw: published.append(req))
    checker.publish(recovered,now=NOW,send=lambda req,**kw: published.append(req))
    assert all(req.method == 'PUT' for req in published)
    assert all(req.full_url.endswith('/metrics/job/ci-delivery-check') for req in published)
    final = published[-1].data.decode()
    assert 'kind="mirror"} 0' in final and 'kind="status"} 0' in final
    assert 'ci_delivery_read_error{repo="agentic-stoa/hum"} 0' in final
    assert 'ci_delivery_last_check_timestamp_seconds' in final
    assert 'sha=' not in final and 'context=' not in final and 'pr=' not in final
    assert 'kind="mirror"} 2' in published[0].data.decode()
    assert 'ci_delivery_read_error{repo="agentic-stoa/hum"} 1' in published[1].data.decode()


def test_push_failure_and_empty_quiet_snapshot(checker):
    snapshot = checker.check(Forge(),[],[],NOW)
    assert checker.render(snapshot,NOW).strip().endswith(str(int(NOW.timestamp())))
    def failed(*args,**kw): raise OSError('private-response')
    assert checker.finish(snapshot,NOW,send=failed) == 1
    assert checker.finish(snapshot,NOW,send=lambda *a,**kw: None) == 0
