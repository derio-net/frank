"""Shared GitHub / Gitea HTTP clients for the ci-budget watcher and report.

Stdlib only. `http` is injectable (method, url, headers, body) -> (status, data)
so both scripts test against fakes.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request


class HttpError(RuntimeError):
    def __init__(self, status, body, method="", url=""):
        super().__init__(f"{method} {url} -> HTTP {status}: {str(body)[:200]}")
        self.status = status


def default_http(method, url, headers=None, body=None, timeout=30, context=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=dict(headers or {}))
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=context) as r:
            raw = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read(), e.code
    try:
        return status, (json.loads(raw) if raw else None)
    except ValueError:
        return status, raw.decode("utf-8", "replace")


class GitHubClient:
    API = "https://api.github.com"

    def __init__(self, org, billing_token, authority_token, http=default_http):
        self.org, self.billing_token, self.authority_token, self.http = org, billing_token, authority_token, http

    def _call(self, token, method, path, body=None, ok=(200, 201, 204), allow=()):
        if not token:
            raise RuntimeError(f"no GitHub token configured for {self.org}")
        url = path if path.startswith("http") else self.API + path
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28"}
        status, data = self.http(method, url, headers, body)
        if status in ok or status in allow:
            return status, data
        raise HttpError(status, data, method, url)

    def _pages(self, token, path):
        out, page = [], 1
        while True:
            sep = "&" if "?" in path else "?"
            _, data = self._call(token, "GET", f"{path}{sep}per_page=100&page={page}")
            batch = data or []
            out += batch
            if len(batch) < 100:
                return out
            page += 1

    def billing_usage(self, org, year, month):
        q = urllib.parse.urlencode({"year": year, "month": month})
        _, data = self._call(self.billing_token, "GET", f"/organizations/{org}/settings/billing/usage?{q}")
        return (data or {}).get("usageItems", [])

    def public_repos(self, org):
        return {r["name"] for r in self._pages(self.billing_token, f"/orgs/{org}/repos?type=public")}

    def list_failed_runs(self, repo, since):
        q = urllib.parse.urlencode({"status": "failure", "per_page": 100,
                                    "created": ">=" + since.strftime("%Y-%m-%dT%H:%M:%SZ")})
        _, data = self._call(self.authority_token, "GET", f"/repos/{self.org}/{repo}/actions/runs?{q}")
        return (data or {}).get("workflow_runs", [])

    def run_annotations(self, repo, run_id):
        _, jobs = self._call(self.authority_token, "GET",
                             f"/repos/{self.org}/{repo}/actions/runs/{run_id}/jobs?per_page=100")
        out = []
        for j in (jobs or {}).get("jobs", []):
            _, a = self._call(self.authority_token, "GET",
                              f"/repos/{self.org}/{repo}/check-runs/{j['id']}/annotations?per_page=100")
            out.append((j, a or []))
        return out

    def get_variable(self, repo, name):
        status, data = self._call(self.authority_token, "GET",
                                  f"/repos/{self.org}/{repo}/actions/variables/{name}", allow=(404,))
        return None if status == 404 else data["value"]

    def set_variable(self, repo, name, value):
        base = f"/repos/{self.org}/{repo}/actions/variables"
        status, _ = self._call(self.authority_token, "PATCH", f"{base}/{name}",
                               {"name": name, "value": value}, allow=(404,))
        if status == 404:
            self._call(self.authority_token, "POST", base, {"name": name, "value": value})

    def workflow_files(self, repo):
        files = {}
        for d in (".github/workflows", ".gitea/workflows"):
            status, listing = self._call(self.authority_token, "GET",
                                         f"/repos/{self.org}/{repo}/contents/{d}", allow=(404,))
            if status == 404:
                continue
            for ent in listing or []:
                if ent.get("type") == "file" and ent["name"].endswith((".yml", ".yaml")):
                    _, f = self._call(self.authority_token, "GET", ent["url"])
                    files[f"{d}/{ent['name']}"] = base64.b64decode(f["content"]).decode()
        return files


class GiteaClient:
    def __init__(self, base, token, http=default_http):
        self.base, self.token, self.http = base.rstrip("/"), token, http

    def _call(self, method, path, body=None, ok=(200, 201, 204), allow=()):
        if not self.token:
            raise RuntimeError("no Gitea token configured")
        url = self.base + path
        status, data = self.http(method, url, {"Authorization": f"token {self.token}", "Accept": "application/json"}, body)
        if status in ok or status in allow:
            return status, data
        raise HttpError(status, data, method, url)

    def _get_var(self, scope, name):
        status, data = self._call("GET", f"{scope}/actions/variables/{name}", allow=(404,))
        return None if status == 404 else data.get("data")

    def _set_var(self, scope, name, value):
        status, _ = self._call("PUT", f"{scope}/actions/variables/{name}", {"value": value}, allow=(404,))
        if status == 404:
            self._call("POST", f"{scope}/actions/variables/{name}", {"value": value})

    def get_repo_var(self, org, repo, name):
        return self._get_var(f"/repos/{org}/{repo}", name)

    def set_repo_var(self, org, repo, name, value):
        self._set_var(f"/repos/{org}/{repo}", name, value)

    def get_org_var(self, org, name):
        return self._get_var(f"/orgs/{org}", name)

    def set_org_var(self, org, name, value):
        self._set_var(f"/orgs/{org}", name, value)

    def create_branch(self, org, repo, name, sha):
        self._call("POST", f"/repos/{org}/{repo}/branches",
                   {"new_branch_name": name, "old_ref_name": sha}, allow=(409,))

    def list_branches(self, org, repo):
        out, page = [], 1
        while True:
            _, data = self._call("GET", f"/repos/{org}/{repo}/branches?limit=50&page={page}")
            out += data or []
            if len(data or []) < 50:
                return out
            page += 1

    def delete_branch(self, org, repo, name):
        self._call("DELETE", f"/repos/{org}/{repo}/branches/{urllib.parse.quote(name, safe='')}", allow=(404,))


class GitHubIssues:
    """Issues in one repo, with the token of the issues-write generator."""

    def __init__(self, token, repo, http=default_http):
        self.token, self.repo, self.http = token, repo, http

    def _call(self, method, path, body=None):
        if not self.token:
            raise RuntimeError("no GitHub issues token configured")
        url = path if path.startswith("http") else f"{GitHubClient.API}/repos/{self.repo}{path}"
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28"}
        status, data = self.http(method, url, headers, body)
        if status not in (200, 201):
            raise HttpError(status, data, method, url)
        return data

    def list(self, label):
        """Every issue (any state) carrying `label`; pull requests are included, callers filter."""
        out, page = [], 1
        while True:
            q = urllib.parse.urlencode({"labels": label, "state": "all", "per_page": 100, "page": page})
            batch = self._call("GET", f"/issues?{q}") or []
            out += batch
            if len(batch) < 100:
                return out
            page += 1

    def create(self, title, body, label):
        return self._call("POST", "/issues", {"title": title, "body": body, "labels": [label]})["number"]

    def search(self, title):
        """Issues whose title matches, via the search API (no label needed)."""
        q = urllib.parse.urlencode({"q": f'repo:{self.repo} in:title "{title}" type:issue', "per_page": 100})
        return (self._call("GET", f"{GitHubClient.API}/search/issues?{q}") or {}).get("items", [])

    def edit(self, number, body, label=None):
        self._call("PATCH", f"/issues/{number}", {"body": body})
        if label:
            self._call("POST", f"/issues/{number}/labels", {"labels": [label]})
