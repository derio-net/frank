# Work Lifecycle Tracking — M3: Health Bridge Service (Frank)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy a standalone service on Frank that receives Grafana webhook alerts and automatically updates GitHub Issue lifecycle states on the "Derio Ops" project board.

**Architecture:** Lightweight Go HTTP server receives Grafana webhook POSTs. Each alert carries a `github_issue` label (e.g., `frank#8`). The bridge maps alert severity/status to lifecycle states (`healthy`, `degraded`, `dead`) and updates the GitHub Project v2 item via GraphQL API. Comments are added to Issues with alert context. The service is stateless — all state lives in GitHub and Grafana. Self-monitored by the same Grafana stack (dogfooding).

**Tech Stack:** Go 1.22+, GitHub GraphQL API, Grafana webhooks, Docker (distroless base), Kubernetes raw manifests, ArgoCD

**Spec:** `willikins/docs/superpowers/specs/2026-04-01-work-lifecycle-tracking-design.md` (Milestone 3)

**Companion plans:**
- `willikins/docs/superpowers/plans/2026-04-01-work-lifecycle-m1-willikins.md` (M1: GitHub Projects board) — **Complete**
- `frank/docs/superpowers/plans/2026-04-01--obs--work-lifecycle-health-monitoring.md` (M2: Probes & dashboards) — **Complete**

**Prerequisites from M1/M2:**
- "Derio Ops" GitHub Project exists (project number from M1)
- Lifecycle field with 10 states configured
- Grafana alert rules exist with `github_issue` labels (added in Task 8)
- Telegram contact point working

---

## File Map

### New repo: `derio-net/health-bridge`

| File | Purpose |
|------|---------|
| `main.go` | Entry point: config loading, HTTP server, health endpoint |
| `bridge.go` | Core logic: webhook handler, alert processing, state mapping |
| `github.go` | GitHub GraphQL client: project metadata, lifecycle updates, comments |
| `bridge_test.go` | Tests for webhook handler, mapping logic, and GitHub client (with mock HTTP) |
| `go.mod` | Go module definition |
| `Dockerfile` | Multi-stage build → distroless image |
| `.github/workflows/release.yaml` | Build + push to GHCR on tag |
| `README.md` | Setup and configuration docs |

### Frank repo: `derio-net/frank`

| File | Action | Purpose |
|------|--------|---------|
| `apps/health-bridge/manifests/deployment.yaml` | Create | Deployment + Service |
| `apps/health-bridge/manifests/configmap.yaml` | Create | Non-secret configuration |
| `apps/health-bridge/manifests/externalsecret.yaml` | Create | GitHub token + webhook secret from Infisical |
| `apps/health-bridge/manifests/vmservicescrape.yaml` | Create | Self-monitoring metrics scrape |
| `apps/root/templates/health-bridge.yaml` | Create | ArgoCD Application CR |

---

## Task 1: Create Go Project and Repository

**Files:**
- Create: `go.mod`
- Create: `main.go`
- Create: `README.md`

- [ ] **Step 1: Create the repository on GitHub**

```bash
gh repo create derio-net/health-bridge --private --description "Grafana webhook → GitHub Project lifecycle state bridge"
gh repo clone derio-net/health-bridge
cd health-bridge
```

- [ ] **Step 2: Initialize Go module**

```bash
go mod init github.com/derio-net/health-bridge
```

Expected: `go.mod` created with module path.

- [ ] **Step 3: Write `main.go`**

Create `main.go`:

```go
package main

import (
	"log"
	"net/http"
	"os"
	"strconv"
)

func main() {
	token := mustEnv("GITHUB_TOKEN")
	secret := mustEnv("WEBHOOK_SECRET")
	org := envOrDefault("GITHUB_ORG", "derio-net")
	projectNum := envOrDefaultInt("PROJECT_NUMBER", 1)
	port := envOrDefault("PORT", "8080")

	bridge, err := NewBridge(token, org, projectNum)
	if err != nil {
		log.Fatalf("Failed to initialize bridge: %v", err)
	}

	mux := http.NewServeMux()
	mux.HandleFunc("POST /webhook", bridge.WebhookHandler(secret))
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("ok"))
	})
	mux.HandleFunc("GET /readyz", func(w http.ResponseWriter, r *http.Request) {
		if bridge.Ready() {
			w.WriteHeader(http.StatusOK)
			w.Write([]byte("ready"))
		} else {
			w.WriteHeader(http.StatusServiceUnavailable)
			w.Write([]byte("not ready"))
		}
	})

	log.Printf("health-bridge listening on :%s (org=%s, project=%d)", port, org, projectNum)
	log.Fatal(http.ListenAndServe(":"+port, mux))
}

func mustEnv(key string) string {
	val := os.Getenv(key)
	if val == "" {
		log.Fatalf("Required environment variable %s is not set", key)
	}
	return val
}

func envOrDefault(key, fallback string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return fallback
}

func envOrDefaultInt(key string, fallback int) int {
	if val := os.Getenv(key); val != "" {
		n, err := strconv.Atoi(val)
		if err != nil {
			log.Fatalf("Environment variable %s must be an integer, got %q", key, val)
		}
		return n
	}
	return fallback
}
```

- [ ] **Step 4: Commit**

```bash
git add go.mod main.go
git commit -m "feat: initial project structure with main entry point"
```

---

## Task 2: Implement Core Bridge Logic

**Files:**
- Create: `bridge.go`

- [ ] **Step 1: Write `bridge.go`**

Create `bridge.go`:

```go
package main

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"strconv"
	"strings"
)

// Bridge is the core service that processes Grafana alerts and updates GitHub.
type Bridge struct {
	github *GitHubClient
}

// GrafanaPayload is the webhook payload sent by Grafana alerting.
type GrafanaPayload struct {
	Status string  `json:"status"`
	Alerts []Alert `json:"alerts"`
}

// Alert is a single alert within a Grafana webhook payload.
type Alert struct {
	Status       string            `json:"status"`
	Labels       map[string]string `json:"labels"`
	Annotations  map[string]string `json:"annotations"`
	StartsAt     string            `json:"startsAt"`
	EndsAt       string            `json:"endsAt"`
	GeneratorURL string            `json:"generatorURL"`
	Fingerprint  string            `json:"fingerprint"`
}

// NewBridge creates a Bridge and loads GitHub Project metadata.
func NewBridge(token, org string, projectNumber int) (*Bridge, error) {
	gh, err := NewGitHubClient(token, org, projectNumber)
	if err != nil {
		return nil, fmt.Errorf("github client init: %w", err)
	}
	return &Bridge{github: gh}, nil
}

// Ready returns true if the bridge has loaded project metadata.
func (b *Bridge) Ready() bool {
	return b.github != nil && b.github.projectID != ""
}

// WebhookHandler returns an HTTP handler that validates the webhook secret
// and processes Grafana alerts.
func (b *Bridge) WebhookHandler(secret string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		body, err := io.ReadAll(r.Body)
		if err != nil {
			http.Error(w, "read error", http.StatusBadRequest)
			return
		}
		defer r.Body.Close()

		// Validate webhook secret via Authorization header (Bearer token)
		authHeader := r.Header.Get("Authorization")
		if authHeader != "Bearer "+secret {
			log.Printf("Unauthorized webhook request from %s", r.RemoteAddr)
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}

		var payload GrafanaPayload
		if err := json.Unmarshal(body, &payload); err != nil {
			log.Printf("Invalid JSON payload: %v", err)
			http.Error(w, "invalid JSON", http.StatusBadRequest)
			return
		}

		processed := 0
		for _, alert := range payload.Alerts {
			if err := b.processAlert(alert); err != nil {
				log.Printf("Error processing alert %s: %v", alert.Labels["alertname"], err)
				continue
			}
			processed++
		}

		w.WriteHeader(http.StatusOK)
		fmt.Fprintf(w, `{"processed": %d, "total": %d}`, processed, len(payload.Alerts))
	}
}

func (b *Bridge) processAlert(alert Alert) error {
	issueRef := alert.Labels["github_issue"]
	if issueRef == "" {
		log.Printf("Alert %s has no github_issue label, skipping", alert.Labels["alertname"])
		return nil
	}

	repo, number, err := ParseIssueRef(issueRef)
	if err != nil {
		return fmt.Errorf("parse issue ref %q: %w", issueRef, err)
	}

	newState := MapAlertToState(alert.Status, alert.Labels["severity"])

	// Update lifecycle state on project board
	if err := b.github.UpdateLifecycleState(repo, number, newState); err != nil {
		return fmt.Errorf("update lifecycle %s → %s: %w", issueRef, newState, err)
	}

	// Add comment to issue with alert context
	comment := FormatComment(alert, newState)
	if err := b.github.AddIssueComment(repo, number, comment); err != nil {
		log.Printf("Warning: failed to add comment to %s (state update succeeded): %v", issueRef, err)
		// Non-fatal: the state update is the critical action
	}

	// On dead transition, create a bug Issue linked to the feature Issue
	if newState == "dead" {
		bugURL, err := b.github.CreateBugIssue(repo, number, alert)
		if err != nil {
			log.Printf("Warning: failed to create bug issue for %s: %v", issueRef, err)
		} else {
			log.Printf("Created bug issue: %s", bugURL)
		}
	}

	log.Printf("Processed: %s → %s (alert: %s, status: %s)", issueRef, newState, alert.Labels["alertname"], alert.Status)
	return nil
}

// ParseIssueRef parses a "repo#number" string into repo name and issue number.
func ParseIssueRef(ref string) (repo string, number int, err error) {
	parts := strings.SplitN(ref, "#", 2)
	if len(parts) != 2 {
		return "", 0, fmt.Errorf("expected format 'repo#number', got %q", ref)
	}
	repo = parts[0]
	number, err = strconv.Atoi(parts[1])
	if err != nil {
		return "", 0, fmt.Errorf("invalid issue number %q: %w", parts[1], err)
	}
	if repo == "" || number <= 0 {
		return "", 0, fmt.Errorf("invalid issue ref: repo=%q number=%d", repo, number)
	}
	return repo, number, nil
}

// MapAlertToState maps Grafana alert status and severity to a lifecycle state.
func MapAlertToState(alertStatus, severity string) string {
	switch alertStatus {
	case "resolved":
		return "healthy"
	case "firing":
		switch severity {
		case "critical":
			return "dead"
		case "warning":
			return "degraded"
		default:
			return "degraded" // Default firing alerts to degraded
		}
	default:
		return "degraded" // Unknown status defaults to degraded
	}
}

// FormatComment creates a markdown comment for a GitHub Issue describing the alert.
func FormatComment(alert Alert, newState string) string {
	var sb strings.Builder
	sb.WriteString(fmt.Sprintf("## Health Bridge: `%s`\n\n", newState))
	sb.WriteString(fmt.Sprintf("**Alert:** %s\n", alert.Labels["alertname"]))
	sb.WriteString(fmt.Sprintf("**Status:** %s\n", alert.Status))
	sb.WriteString(fmt.Sprintf("**Severity:** %s\n", alert.Labels["severity"]))
	if summary := alert.Annotations["summary"]; summary != "" {
		sb.WriteString(fmt.Sprintf("**Summary:** %s\n", summary))
	}
	if desc := alert.Annotations["description"]; desc != "" {
		sb.WriteString(fmt.Sprintf("**Description:** %s\n", desc))
	}
	sb.WriteString(fmt.Sprintf("**Started:** %s\n", alert.StartsAt))
	if alert.Status == "resolved" && alert.EndsAt != "" {
		sb.WriteString(fmt.Sprintf("**Resolved:** %s\n", alert.EndsAt))
	}
	if alert.GeneratorURL != "" {
		sb.WriteString(fmt.Sprintf("\n[View in Grafana](%s)\n", alert.GeneratorURL))
	}
	sb.WriteString("\n---\n*Automated by health-bridge*\n")
	return sb.String()
}
```

- [ ] **Step 2: Commit**

```bash
git add bridge.go
git commit -m "feat: implement core bridge logic — webhook handler, alert mapping, comment formatting"
```

---

## Task 3: Implement GitHub GraphQL Client

**Files:**
- Create: `github.go`

- [ ] **Step 1: Write `github.go`**

Create `github.go`:

```go
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"time"
)

const githubGraphQLURL = "https://api.github.com/graphql"
const githubRESTURL = "https://api.github.com"

// GitHubClient handles GitHub API interactions for project lifecycle management.
type GitHubClient struct {
	token         string
	org           string
	projectNumber int
	projectID     string
	fieldID       string
	optionIDs     map[string]string // lifecycle state name → option ID
	httpClient    *http.Client
}

type graphQLRequest struct {
	Query     string         `json:"query"`
	Variables map[string]any `json:"variables,omitempty"`
}

type graphQLResponse struct {
	Data   json.RawMessage `json:"data"`
	Errors []struct {
		Message string `json:"message"`
	} `json:"errors"`
}

// NewGitHubClient creates a client and loads project metadata (project ID, field ID, option IDs).
func NewGitHubClient(token, org string, projectNumber int) (*GitHubClient, error) {
	c := &GitHubClient{
		token:         token,
		org:           org,
		projectNumber: projectNumber,
		optionIDs:     make(map[string]string),
		httpClient:    &http.Client{Timeout: 30 * time.Second},
	}
	if err := c.loadProjectMetadata(); err != nil {
		return nil, err
	}
	return c, nil
}

func (c *GitHubClient) loadProjectMetadata() error {
	query := `query($org: String!, $number: Int!) {
		organization(login: $org) {
			projectV2(number: $number) {
				id
				field(name: "Lifecycle") {
					... on ProjectV2SingleSelectField {
						id
						options {
							id
							name
						}
					}
				}
			}
		}
	}`

	vars := map[string]any{
		"org":    c.org,
		"number": c.projectNumber,
	}

	resp, err := c.graphQL(query, vars)
	if err != nil {
		return fmt.Errorf("load project metadata: %w", err)
	}

	var result struct {
		Organization struct {
			ProjectV2 struct {
				ID    string `json:"id"`
				Field struct {
					ID      string `json:"id"`
					Options []struct {
						ID   string `json:"id"`
						Name string `json:"name"`
					} `json:"options"`
				} `json:"field"`
			} `json:"projectV2"`
		} `json:"organization"`
	}
	if err := json.Unmarshal(resp, &result); err != nil {
		return fmt.Errorf("parse project metadata: %w", err)
	}

	project := result.Organization.ProjectV2
	if project.ID == "" {
		return fmt.Errorf("project #%d not found in org %s", c.projectNumber, c.org)
	}
	c.projectID = project.ID

	if project.Field.ID == "" {
		return fmt.Errorf("'Lifecycle' field not found on project #%d", c.projectNumber)
	}
	c.fieldID = project.Field.ID

	for _, opt := range project.Field.Options {
		c.optionIDs[opt.Name] = opt.ID
	}

	log.Printf("Loaded project metadata: id=%s, field=%s, %d lifecycle states",
		c.projectID, c.fieldID, len(c.optionIDs))
	return nil
}

// UpdateLifecycleState finds the Issue's project item and updates its Lifecycle field.
func (c *GitHubClient) UpdateLifecycleState(repo string, issueNumber int, newState string) error {
	optionID, ok := c.optionIDs[newState]
	if !ok {
		return fmt.Errorf("unknown lifecycle state %q (available: %v)", newState, mapKeys(c.optionIDs))
	}

	// Step 1: Find the project item ID for this issue
	itemID, err := c.findProjectItem(repo, issueNumber)
	if err != nil {
		return fmt.Errorf("find project item for %s#%d: %w", repo, issueNumber, err)
	}

	// Step 2: Update the Lifecycle field
	mutation := `mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
		updateProjectV2ItemFieldValue(input: {
			projectId: $projectId
			itemId: $itemId
			fieldId: $fieldId
			value: { singleSelectOptionId: $optionId }
		}) {
			projectV2Item { id }
		}
	}`

	vars := map[string]any{
		"projectId": c.projectID,
		"itemId":    itemID,
		"fieldId":   c.fieldID,
		"optionId":  optionID,
	}

	if _, err := c.graphQL(mutation, vars); err != nil {
		return fmt.Errorf("update lifecycle field: %w", err)
	}

	return nil
}

func (c *GitHubClient) findProjectItem(repo string, issueNumber int) (string, error) {
	query := `query($org: String!, $repo: String!, $number: Int!) {
		repository(owner: $org, name: $repo) {
			issue(number: $number) {
				projectItems(first: 10) {
					nodes {
						id
						project { id }
					}
				}
			}
		}
	}`

	vars := map[string]any{
		"org":    c.org,
		"repo":   repo,
		"number": issueNumber,
	}

	resp, err := c.graphQL(query, vars)
	if err != nil {
		return "", err
	}

	var result struct {
		Repository struct {
			Issue struct {
				ProjectItems struct {
					Nodes []struct {
						ID      string `json:"id"`
						Project struct {
							ID string `json:"id"`
						} `json:"project"`
					} `json:"nodes"`
				} `json:"projectItems"`
			} `json:"issue"`
		} `json:"repository"`
	}
	if err := json.Unmarshal(resp, &result); err != nil {
		return "", fmt.Errorf("parse project items: %w", err)
	}

	for _, item := range result.Repository.Issue.ProjectItems.Nodes {
		if item.Project.ID == c.projectID {
			return item.ID, nil
		}
	}

	return "", fmt.Errorf("issue %s#%d is not on project %s", repo, issueNumber, c.projectID)
}

// CreateBugIssue creates a new bug Issue linked to a feature Issue when it transitions to dead.
func (c *GitHubClient) CreateBugIssue(repo string, featureIssueNumber int, alert Alert) (string, error) {
	title := fmt.Sprintf("[Bug] %s is dead — %s", alert.Labels["alertname"], alert.Annotations["summary"])
	body := fmt.Sprintf(`## Auto-created by health-bridge

**Feature Issue:** %s/%s#%d
**Alert:** %s
**Severity:** %s
**Summary:** %s
**Started:** %s

This feature has been marked as **dead** by the health monitoring system.

[View in Grafana](%s)

---
*Automated by health-bridge on dead transition*`,
		c.org, repo, featureIssueNumber,
		alert.Labels["alertname"],
		alert.Labels["severity"],
		alert.Annotations["summary"],
		alert.StartsAt,
		alert.GeneratorURL,
	)

	payload, err := json.Marshal(map[string]any{
		"title":  title,
		"body":   body,
		"labels": []string{"bug"},
	})
	if err != nil {
		return "", err
	}

	url := fmt.Sprintf("%s/repos/%s/%s/issues", githubRESTURL, c.org, repo)
	req, err := http.NewRequest("POST", url, bytes.NewReader(payload))
	if err != nil {
		return "", err
	}
	req.Header.Set("Authorization", "Bearer "+c.token)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/vnd.github+json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return "", fmt.Errorf("http request: %w", err)
	}
	defer resp.Body.Close()

	respBody, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusCreated {
		return "", fmt.Errorf("github API returned %d: %s", resp.StatusCode, string(respBody))
	}

	var result struct {
		HTMLURL string `json:"html_url"`
	}
	if err := json.Unmarshal(respBody, &result); err != nil {
		return "", fmt.Errorf("parse response: %w", err)
	}

	return result.HTMLURL, nil
}

// AddIssueComment adds a comment to a GitHub Issue via REST API.
func (c *GitHubClient) AddIssueComment(repo string, issueNumber int, body string) error {
	url := fmt.Sprintf("%s/repos/%s/%s/issues/%d/comments", githubRESTURL, c.org, repo, issueNumber)

	payload, err := json.Marshal(map[string]string{"body": body})
	if err != nil {
		return err
	}

	req, err := http.NewRequest("POST", url, bytes.NewReader(payload))
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+c.token)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/vnd.github+json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("http request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusCreated {
		respBody, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("github API returned %d: %s", resp.StatusCode, string(respBody))
	}

	return nil
}

func (c *GitHubClient) graphQL(query string, variables map[string]any) (json.RawMessage, error) {
	reqBody := graphQLRequest{Query: query, Variables: variables}
	payload, err := json.Marshal(reqBody)
	if err != nil {
		return nil, fmt.Errorf("marshal request: %w", err)
	}

	req, err := http.NewRequest("POST", githubGraphQLURL, bytes.NewReader(payload))
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}
	req.Header.Set("Authorization", "Bearer "+c.token)
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("http request: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("github API returned %d: %s", resp.StatusCode, string(body))
	}

	var gqlResp graphQLResponse
	if err := json.Unmarshal(body, &gqlResp); err != nil {
		return nil, fmt.Errorf("parse response: %w", err)
	}

	if len(gqlResp.Errors) > 0 {
		return nil, fmt.Errorf("graphql errors: %v", gqlResp.Errors[0].Message)
	}

	return gqlResp.Data, nil
}

func mapKeys(m map[string]string) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	return keys
}
```

- [ ] **Step 2: Commit**

```bash
git add github.go
git commit -m "feat: implement GitHub GraphQL client — project metadata, lifecycle updates, issue comments"
```

---

## Task 4: Write Tests

**Files:**
- Create: `bridge_test.go`
- Create: `github_test.go`

- [ ] **Step 1: Write `bridge_test.go`**

Create `bridge_test.go`:

```go
package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestParseIssueRef(t *testing.T) {
	tests := []struct {
		input      string
		wantRepo   string
		wantNumber int
		wantErr    bool
	}{
		{"frank#8", "frank", 8, false},
		{"willikins#11", "willikins", 11, false},
		{"content-factory#1", "content-factory", 1, false},
		{"nohash", "", 0, true},
		{"#5", "", 0, true},
		{"repo#0", "", 0, true},
		{"repo#abc", "", 0, true},
		{"", "", 0, true},
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			repo, number, err := ParseIssueRef(tt.input)
			if (err != nil) != tt.wantErr {
				t.Fatalf("ParseIssueRef(%q) error = %v, wantErr %v", tt.input, err, tt.wantErr)
			}
			if repo != tt.wantRepo {
				t.Errorf("ParseIssueRef(%q) repo = %q, want %q", tt.input, repo, tt.wantRepo)
			}
			if number != tt.wantNumber {
				t.Errorf("ParseIssueRef(%q) number = %d, want %d", tt.input, number, tt.wantNumber)
			}
		})
	}
}

func TestMapAlertToState(t *testing.T) {
	tests := []struct {
		status   string
		severity string
		want     string
	}{
		{"resolved", "critical", "healthy"},
		{"resolved", "warning", "healthy"},
		{"resolved", "", "healthy"},
		{"firing", "critical", "dead"},
		{"firing", "warning", "degraded"},
		{"firing", "", "degraded"},
		{"unknown", "", "degraded"},
	}

	for _, tt := range tests {
		t.Run(tt.status+"_"+tt.severity, func(t *testing.T) {
			got := MapAlertToState(tt.status, tt.severity)
			if got != tt.want {
				t.Errorf("MapAlertToState(%q, %q) = %q, want %q", tt.status, tt.severity, got, tt.want)
			}
		})
	}
}

func TestFormatComment(t *testing.T) {
	alert := Alert{
		Status:       "firing",
		Labels:       map[string]string{"alertname": "exercise-reminder-stale", "severity": "critical"},
		Annotations:  map[string]string{"summary": "Exercise reminder heartbeat stale"},
		StartsAt:     "2026-04-04T10:00:00Z",
		GeneratorURL: "https://grafana.frank.derio.net/alerting/grafana/exercise-reminder-stale/view",
	}

	comment := FormatComment(alert, "dead")

	if !bytes.Contains([]byte(comment), []byte("## Health Bridge: `dead`")) {
		t.Error("Comment should contain the state header")
	}
	if !bytes.Contains([]byte(comment), []byte("exercise-reminder-stale")) {
		t.Error("Comment should contain the alert name")
	}
	if !bytes.Contains([]byte(comment), []byte("View in Grafana")) {
		t.Error("Comment should contain Grafana link")
	}
}

func TestWebhookHandler_Unauthorized(t *testing.T) {
	bridge := &Bridge{github: &GitHubClient{projectID: "test"}}
	handler := bridge.WebhookHandler("correct-secret")

	req := httptest.NewRequest("POST", "/webhook", bytes.NewReader([]byte("{}")))
	req.Header.Set("Authorization", "Bearer wrong-secret")
	w := httptest.NewRecorder()

	handler(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("Expected 401, got %d", w.Code)
	}
}

func TestWebhookHandler_ValidPayload(t *testing.T) {
	// Create a mock GitHub API server
	mockGH := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]any{"data": map[string]any{}})
	}))
	defer mockGH.Close()

	bridge := &Bridge{
		github: &GitHubClient{
			projectID: "test-project",
			fieldID:   "test-field",
			optionIDs: map[string]string{"healthy": "opt-1", "dead": "opt-2", "degraded": "opt-3"},
			httpClient: mockGH.Client(),
		},
	}

	// Payload with no github_issue label — should process without error
	payload := GrafanaPayload{
		Status: "firing",
		Alerts: []Alert{
			{
				Status: "firing",
				Labels: map[string]string{"alertname": "test", "severity": "warning"},
			},
		},
	}
	body, _ := json.Marshal(payload)

	req := httptest.NewRequest("POST", "/webhook", bytes.NewReader(body))
	req.Header.Set("Authorization", "Bearer test-secret")
	w := httptest.NewRecorder()

	handler := bridge.WebhookHandler("test-secret")
	handler(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected 200, got %d", w.Code)
	}
}
```

- [ ] **Step 2: Run tests**

```bash
go test -v ./...
```

Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add bridge_test.go
git commit -m "test: add unit tests for issue ref parsing, alert mapping, webhook handler"
```

---

## Task 5: Create Dockerfile

**Files:**
- Create: `Dockerfile`
- Create: `.github/workflows/release.yaml`

- [ ] **Step 1: Write `Dockerfile`**

Create `Dockerfile`:

```dockerfile
# Build stage
FROM golang:1.22-alpine AS builder

WORKDIR /app
COPY go.mod ./
RUN go mod download
COPY *.go ./
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /health-bridge .

# Runtime stage
FROM gcr.io/distroless/static-debian12:nonroot

COPY --from=builder /health-bridge /health-bridge

USER nonroot:nonroot
EXPOSE 8080

ENTRYPOINT ["/health-bridge"]
```

- [ ] **Step 2: Build locally and verify image size**

```bash
docker build -t health-bridge:test .
docker images health-bridge:test --format "{{.Size}}"
```

Expected: Image size < 15MB. The distroless static base is ~2MB + Go binary ~10MB.

- [ ] **Step 3: Write GitHub Actions workflow for GHCR publish**

Create `.github/workflows/release.yaml`:

```yaml
name: Build and Push

on:
  push:
    tags:
      - 'v*'

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-go@v5
        with:
          go-version: '1.22'

      - name: Run tests
        run: go test -v ./...

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.ref_name }}
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:latest
```

- [ ] **Step 4: Commit**

```bash
git add Dockerfile .github/workflows/release.yaml
git commit -m "feat: add Dockerfile (distroless) and GitHub Actions release workflow"
```

- [ ] **Step 5: Tag and push to trigger first build**

```bash
git push origin main
git tag v0.1.0
git push origin v0.1.0
```

Expected: GitHub Actions workflow runs, builds image, pushes to `ghcr.io/derio-net/health-bridge:v0.1.0`.

- [ ] **Step 6: Verify GHCR image exists**

```bash
gh api /orgs/derio-net/packages/container/health-bridge/versions --jq '.[0].metadata.container.tags'
```

Expected: Shows `["v0.1.0", "latest"]`.

---

## Task 6: Store Secrets in Infisical

**Files:**
- No file changes — Infisical UI operations

This is a manual operation (Infisical has no CLI for secret creation).

- [ ] **Step 1: Create HEALTH_BRIDGE_WEBHOOK_SECRET in Infisical**

```yaml
# manual-operation
id: health-bridge-webhook-secret
layer: obs
app: health-bridge
plan: docs/superpowers/plans/2026-04-04--obs--health-bridge-service.md
when: Before deploying K8s manifests
why_manual: Infisical secret creation is UI-only
commands:
  - description: Generate a webhook secret
    command: openssl rand -hex 32
  - description: Create secret in Infisical
    command: |
      Navigate to Infisical UI → derio-net project → prod environment
      Create secret: HEALTH_BRIDGE_WEBHOOK_SECRET = <generated hex string>
      Create secret: HEALTH_BRIDGE_GITHUB_TOKEN = <GitHub PAT with project and repo scope>
verify:
  - description: Verify secrets exist
    command: kubectl get externalsecret -n monitoring health-bridge-secrets -o jsonpath='{.status.conditions[0].status}'
    expected: "True"
status: pending
```

Note: The `HEALTH_BRIDGE_GITHUB_TOKEN` needs these GitHub PAT scopes:
- `repo` (full control) — for issue comments
- `project` (read/write) — for project item updates
- `read:org` — for organization project access

---

## Task 7: Create Kubernetes Manifests in Frank Repo

**Working directory:** `derio-net/frank` (not the health-bridge repo)

**Files:**
- Create: `apps/health-bridge/manifests/deployment.yaml`
- Create: `apps/health-bridge/manifests/configmap.yaml`
- Create: `apps/health-bridge/manifests/externalsecret.yaml`
- Create: `apps/health-bridge/manifests/vmservicescrape.yaml`

- [ ] **Step 1: Create ExternalSecret for health-bridge credentials**

Create `apps/health-bridge/manifests/externalsecret.yaml`:

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: health-bridge-secrets
  namespace: monitoring
spec:
  refreshInterval: 5m
  secretStoreRef:
    name: infisical
    kind: ClusterSecretStore
  target:
    name: health-bridge-secrets
    creationPolicy: Owner
  data:
    - secretKey: GITHUB_TOKEN
      remoteRef:
        key: HEALTH_BRIDGE_GITHUB_TOKEN
    - secretKey: WEBHOOK_SECRET
      remoteRef:
        key: HEALTH_BRIDGE_WEBHOOK_SECRET
```

- [ ] **Step 2: Create ConfigMap for non-secret config**

Create `apps/health-bridge/manifests/configmap.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: health-bridge-config
  namespace: monitoring
data:
  GITHUB_ORG: "derio-net"
  PROJECT_NUMBER: "1"
  PORT: "8080"
```

- [ ] **Step 3: Create Deployment + Service**

Create `apps/health-bridge/manifests/deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: health-bridge
  namespace: monitoring
  labels:
    app: health-bridge
spec:
  replicas: 1
  selector:
    matchLabels:
      app: health-bridge
  template:
    metadata:
      labels:
        app: health-bridge
    spec:
      containers:
        - name: health-bridge
          image: ghcr.io/derio-net/health-bridge:v0.1.0
          ports:
            - name: http
              containerPort: 8080
          envFrom:
            - configMapRef:
                name: health-bridge-config
            - secretRef:
                name: health-bridge-secrets
          resources:
            requests:
              cpu: 10m
              memory: 16Mi
            limits:
              memory: 32Mi
          livenessProbe:
            httpGet:
              path: /healthz
              port: http
            initialDelaySeconds: 5
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            initialDelaySeconds: 5
            periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: health-bridge
  namespace: monitoring
  labels:
    app: health-bridge
spec:
  selector:
    app: health-bridge
  ports:
    - name: http
      port: 8080
      targetPort: 8080
```

- [ ] **Step 4: Create VMServiceScrape for self-monitoring**

Create `apps/health-bridge/manifests/vmservicescrape.yaml`:

```yaml
apiVersion: operator.victoriametrics.com/v1beta1
kind: VMServiceScrape
metadata:
  name: health-bridge
  namespace: monitoring
spec:
  selector:
    matchLabels:
      app: health-bridge
  endpoints:
    - port: http
      path: /metrics
```

Note: The Go service doesn't expose `/metrics` yet. This is forward-looking — add Prometheus metrics (e.g., `health_bridge_alerts_processed_total`) in a future iteration. For now, the VMServiceScrape is harmless (scrape will 404, VictoriaMetrics ignores it).

- [ ] **Step 5: Commit in frank repo**

```bash
git add apps/health-bridge/
git commit -m "feat(obs): add health-bridge K8s manifests — deployment, secrets, config"
```

---

## Task 8: Create ArgoCD Application CR

**Files:**
- Create: `apps/root/templates/health-bridge.yaml`

- [ ] **Step 1: Create ArgoCD Application**

Create `apps/root/templates/health-bridge.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: health-bridge
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: infrastructure
  source:
    repoURL: {{ "{{ .Values.repoURL }}" }}
    targetRevision: {{ "{{ .Values.targetRevision }}" }}
    path: apps/health-bridge/manifests
  destination:
    server: {{ "{{ .Values.destination.server }}" }}
    namespace: monitoring
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
    syncOptions:
      - CreateNamespace=false
      - ServerSideApply=true
      - RespectIgnoreDifferences=true
  ignoreDifferences:
    - group: ""
      kind: Secret
      jsonPointers:
        - /data
```

- [ ] **Step 2: Commit**

```bash
git add apps/root/templates/health-bridge.yaml
git commit -m "feat(obs): add health-bridge ArgoCD Application CR"
```

- [ ] **Step 3: Push and verify ArgoCD sync**

```bash
git push origin main
```

Wait for ArgoCD to sync (typically < 3 minutes). Verify:

```bash
source .env
argocd app get health-bridge
kubectl get pods -n monitoring -l app=health-bridge
kubectl logs -n monitoring -l app=health-bridge --tail=20
```

Expected: Pod running, logs show "health-bridge listening on :8080" and "Loaded project metadata: id=..., field=..., 10 lifecycle states".

---

## Task 9: Configure Grafana Webhook Contact Point

**Files:**
- No file changes — Grafana API operations

- [ ] **Step 1: Create webhook contact point in Grafana**

```yaml
# manual-operation
id: grafana-health-bridge-webhook
layer: obs
app: health-bridge
plan: docs/superpowers/plans/2026-04-04--obs--health-bridge-service.md
when: After health-bridge pod is running
why_manual: Grafana provisioning is API-only (not GitOps)
commands:
  - description: Create webhook contact point
    command: |
      GRAFANA_URL="https://grafana.frank.derio.net"
      GRAFANA_API_KEY="<from Infisical or env>"
      WEBHOOK_SECRET="<same as HEALTH_BRIDGE_WEBHOOK_SECRET in Infisical>"

      curl -s -X POST "$GRAFANA_URL/api/v1/provisioning/contact-points" \
        -H "Authorization: Bearer $GRAFANA_API_KEY" \
        -H "Content-Type: application/json" \
        -H "X-Disable-Provenance: true" \
        -d '{
          "name": "Health Bridge Webhook",
          "type": "webhook",
          "settings": {
            "url": "http://health-bridge.monitoring.svc.cluster.local:8080/webhook",
            "httpMethod": "POST",
            "authorization_scheme": "Bearer",
            "authorization_credentials": "'"$WEBHOOK_SECRET"'"
          },
          "disableResolveMessage": false
        }'
  - description: Verify contact point was created
    command: |
      curl -s "$GRAFANA_URL/api/v1/provisioning/contact-points" \
        -H "Authorization: Bearer $GRAFANA_API_KEY" | jq '.[] | select(.name == "Health Bridge Webhook")'
verify:
  - description: Contact point exists
    command: curl -s "$GRAFANA_URL/api/v1/provisioning/contact-points" -H "Authorization:Bearer $GRAFANA_API_KEY" | jq '.[].name' | grep "Health Bridge"
    expected: "Health Bridge Webhook"
status: pending
```

- [ ] **Step 2: Update notification policy to route to webhook**

```yaml
# manual-operation
id: grafana-notification-policy-webhook
layer: obs
app: health-bridge
plan: docs/superpowers/plans/2026-04-04--obs--health-bridge-service.md
when: After webhook contact point is created
why_manual: Grafana notification policy is API-only
commands:
  - description: Get current notification policy tree
    command: |
      GRAFANA_URL="https://grafana.frank.derio.net"
      curl -s "$GRAFANA_URL/api/v1/provisioning/policies" \
        -H "Authorization: Bearer $GRAFANA_API_KEY" | jq .
  - description: Update policy to add webhook route alongside existing Telegram routes
    command: |
      GRAFANA_URL="https://grafana.frank.derio.net"
      # Fetch current policy, add a new child route for the webhook.
      # The existing severity-based Telegram routes have `continue: true` so
      # alerts also fall through to the next matching route.
      CURRENT=$(curl -s "$GRAFANA_URL/api/v1/provisioning/policies" \
        -H "Authorization: Bearer $GRAFANA_API_KEY")

      # Append a new route that catches all Feature Health alerts for the webhook:
      UPDATED=$(echo "$CURRENT" | jq '.routes += [{
        "receiver": "Health Bridge Webhook",
        "object_matchers": [["grafana_folder", "=", "Feature Health"]],
        "continue": false,
        "group_wait": "30s",
        "group_interval": "1m",
        "repeat_interval": "5m"
      }]')

      # Also ensure existing Telegram severity routes have continue: true
      UPDATED=$(echo "$UPDATED" | jq '(.routes[] | select(.receiver == "Telegram - Willikins")) .continue = true')

      curl -s -X PUT "$GRAFANA_URL/api/v1/provisioning/policies" \
        -H "Authorization: Bearer $GRAFANA_API_KEY" \
        -H "Content-Type: application/json" \
        -H "X-Disable-Provenance: true" \
        -d "$UPDATED"
verify:
  - description: Verify notification policy has webhook route
    command: |
      curl -s "$GRAFANA_URL/api/v1/provisioning/policies" \
        -H "Authorization: Bearer $GRAFANA_API_KEY" | \
        jq '.routes[] | select(.receiver == "Health Bridge Webhook")'
    expected: Route object with receiver "Health Bridge Webhook" and grafana_folder matcher
  - description: Send test notification to webhook contact point
    command: |
      curl -s -X POST "http://health-bridge.monitoring.svc.cluster.local:8080/webhook" \
        -H "Authorization: Bearer $WEBHOOK_SECRET" \
        -H "Content-Type: application/json" \
        -d '{"status":"firing","alerts":[{"status":"firing","labels":{"alertname":"test","severity":"warning"},"annotations":{"summary":"notification policy test"},"startsAt":"2026-04-04T00:00:00Z"}]}'
    expected: '{"processed": 0, "total": 1}' (0 processed because no github_issue label)
status: pending
```

---

## Task 10: Add `github_issue` Labels to Alert Rules

**Files:**
- No file changes — Grafana API operations

The existing alert rules from M2 need `github_issue` labels so the bridge can map alerts to Issues.

- [ ] **Step 1: Update existing alert rules with `github_issue` labels**

```yaml
# manual-operation
id: grafana-alert-labels-github-issue
layer: obs
app: health-bridge
plan: docs/superpowers/plans/2026-04-04--obs--health-bridge-service.md
when: After health-bridge is deployed and webhook configured
why_manual: Grafana alert rules are API-provisioned
commands:
  - description: List current alert rules to get UIDs
    command: |
      curl -s "$GRAFANA_URL/api/v1/provisioning/alert-rules" \
        -H "Authorization: Bearer $GRAFANA_API_KEY" | \
        jq '.[] | {uid: .uid, title: .title}'
  - description: Update each rule to add github_issue label
    command: |
      # For each rule, GET the full rule, add the label, PUT back.
      # Mapping (from M1 issue table):
      #   exercise-reminder-stale → github_issue=willikins#11
      #   session-manager-stale → github_issue=willikins#13
      #   audit-digest-stale → github_issue=willikins#12
      #   endpoint-down → (per-target, handled by bridge using instance label)
      #   agent-pod-not-running → github_issue=frank#8

      for RULE_UID in exercise-reminder-stale session-manager-stale audit-digest-stale agent-pod-not-running; do
        RULE=$(curl -s "$GRAFANA_URL/api/v1/provisioning/alert-rules/$RULE_UID" \
          -H "Authorization: Bearer $GRAFANA_API_KEY")

        case $RULE_UID in
          exercise-reminder-stale) ISSUE="willikins#11" ;;
          session-manager-stale) ISSUE="willikins#13" ;;
          audit-digest-stale) ISSUE="willikins#12" ;;
          agent-pod-not-running) ISSUE="frank#8" ;;
        esac

        UPDATED=$(echo "$RULE" | jq --arg issue "$ISSUE" '.labels.github_issue = $issue')

        curl -s -X PUT "$GRAFANA_URL/api/v1/provisioning/alert-rules/$RULE_UID" \
          -H "Authorization: Bearer $GRAFANA_API_KEY" \
          -H "Content-Type: application/json" \
          -H "X-Disable-Provenance: true" \
          -d "$UPDATED"

        echo "Updated $RULE_UID → github_issue=$ISSUE"
      done
verify:
  - description: Verify labels on alert rules
    command: |
      curl -s "$GRAFANA_URL/api/v1/provisioning/alert-rules" \
        -H "Authorization: Bearer $GRAFANA_API_KEY" | \
        jq '.[] | {title: .title, github_issue: .labels.github_issue}'
    expected: Each rule shows its github_issue label
status: pending
```

Note: The `endpoint-down` alert covers multiple targets. The bridge will need to handle this by mapping the `instance` label to the correct Issue. For the MVP, endpoint-down alerts update a single "infrastructure health" Issue. Refined per-endpoint mapping is future work.

---

## Task 11: End-to-End Verification

- [ ] **Step 1: Check bridge pod is healthy**

```bash
source .env
kubectl get pods -n monitoring -l app=health-bridge
kubectl logs -n monitoring -l app=health-bridge --tail=5
```

Expected: Pod running, logs show startup message with project metadata loaded.

- [ ] **Step 2: Send a test webhook directly to the bridge**

From the secure-agent-pod or via port-forward:

```bash
# Port-forward to bridge
kubectl port-forward -n monitoring svc/health-bridge 8080:8080 &

# Send a test alert (use the real webhook secret)
WEBHOOK_SECRET="<from Infisical>"

curl -s -X POST http://localhost:8080/webhook \
  -H "Authorization: Bearer $WEBHOOK_SECRET" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "firing",
    "alerts": [{
      "status": "firing",
      "labels": {
        "alertname": "test-bridge",
        "severity": "warning",
        "github_issue": "willikins#11"
      },
      "annotations": {
        "summary": "Test alert from health-bridge verification"
      },
      "startsAt": "2026-04-04T12:00:00Z",
      "generatorURL": "https://grafana.frank.derio.net"
    }]
  }'

kill %1
```

Expected: Response `{"processed": 1, "total": 1}`. Check the GitHub Issue:

```bash
gh issue view 11 --repo derio-net/willikins --json projectItems,comments | jq .
```

Expected: Issue lifecycle state changed to `degraded`, new comment with alert details.

- [ ] **Step 3: Send a resolved alert to restore state**

```bash
kubectl port-forward -n monitoring svc/health-bridge 8080:8080 &

curl -s -X POST http://localhost:8080/webhook \
  -H "Authorization: Bearer $WEBHOOK_SECRET" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "resolved",
    "alerts": [{
      "status": "resolved",
      "labels": {
        "alertname": "test-bridge",
        "severity": "warning",
        "github_issue": "willikins#11"
      },
      "annotations": {
        "summary": "Test alert resolved"
      },
      "startsAt": "2026-04-04T12:00:00Z",
      "endsAt": "2026-04-04T12:05:00Z",
      "generatorURL": "https://grafana.frank.derio.net"
    }]
  }'

kill %1
```

Expected: Issue lifecycle state changed back to `healthy`.

- [ ] **Step 4: Trigger a real Grafana alert and verify bridge receives it**

Temporarily lower the exercise-reminder-stale threshold (as done in M2 testing):

```bash
# The exercise cron should already be running. If the heartbeat is stale,
# the alert will fire and route through the webhook to the bridge.
# Check bridge logs for processing:
kubectl logs -n monitoring -l app=health-bridge --tail=20 -f
```

Expected: Bridge logs show "Processed: willikins#11 → dead" (or degraded, depending on severity). Issue on GitHub Project board reflects the new state.

- [ ] **Step 5: Add self-monitoring probe (dogfooding)**

The bridge itself must be monitored by the same Grafana stack. Add its healthz endpoint to the Blackbox Exporter VMProbe.

Edit `apps/blackbox-exporter/manifests/vmprobe.yaml` — add the health-bridge endpoint to the `targets.staticConfig.targets` list:

```yaml
        - http://health-bridge.monitoring.svc.cluster.local:8080/healthz
```

Add it under the existing targets (n8n, paperclip, grafana, blog). Keep the same `probe_group: feature_health` label so it's picked up by the existing `endpoint-down` alert rule.

Commit in the frank repo:

```bash
git add apps/blackbox-exporter/manifests/vmprobe.yaml
git commit -m "feat(obs): add health-bridge self-monitoring probe"
git push origin main
```

Wait for ArgoCD to sync, then verify in Grafana Explore:

```
probe_success{instance="http://health-bridge.monitoring.svc.cluster.local:8080/healthz"}
```

Expected: `1` (probe succeeds).

---

## Deployment Deviations

Document any deviations from this plan here during execution:

*(To be filled during implementation)*
