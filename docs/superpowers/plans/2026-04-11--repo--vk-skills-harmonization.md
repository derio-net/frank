# VK Skills Harmonization — Frank Implementation Plan

> **For VK agents:** Use vk-execute to implement assigned phases.
> **For local execution:** Use subagent-driven-development or executing-plans.
> **For dispatch:** Use vk-dispatch to create Issues from this plan.

**Spec:** `willikins/docs/superpowers/specs/2026-04-10-vk-skills-harmonization-design.md`
**Status:** In Progress

**Goal:** Harmonize Frank's plan infrastructure with the canonical vk-plan model — create the plan profile, delete vendored superpowers skills, replace local scripts with thin wrappers around the canonical validator, and convert the 4 active plans to the Phase > Task > Step format.

**Architecture:** Create `docs/superpowers/plan-config.yaml` defining Frank's filename convention and dispatch config. Delete vendored superpowers skills (they install at user level now). Replace `scripts/validate-plans.sh` with a thin wrapper that delegates to the plugin validator. Update `plan-status.sh` to understand Phase headers. Update rules and hooks. Convert 4 active plans to the Phase hierarchy while preserving checkbox state.

**Tech Stack:** Bash, YAML, Markdown, `gh` CLI, `yq` (for plan conversion)

**Cross-plan note:** This is Plan B of the VK Skills Harmonization feature. Plan A (`derio-net/superpowers-for-vk`) must be merged and installed at user level before this plan's agentic phases run — the new vk-plan and the canonical validator must be available. See the spec's Implementation Plans section.

---

## Phase 0: Infrastructure Harmonization [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/35 -->

Create the profile, delete vendored skills, update scripts and rules. This phase prepares Frank for Phase-structured plans.

### Task 1: Create plan-config.yaml

**Files:**
- Create: `docs/superpowers/plan-config.yaml`

- [x] **Step 1: Write the Frank profile**

```yaml
plan:
  filename: "YYYY-MM-DD--{layer}--{details}.md"
  layers: docs/layers.yaml
  save_to: docs/superpowers/plans/

header:
  required:
    - Spec
    - Status
  status_values:
    - Not Started
    - In Progress
    - Deployed
    - Complete
    - Closed

manual_operations:
  enabled: true
  runbook: docs/runbooks/manual-operations.yaml
  sync_skill: sync-runbook

post_deploy:
  name: "Post-Deploy Checklist"
  type: manual
  steps:
    - "Write building blog post — Use /blog-post skill"
    - "Write operating blog post — Use /blog-post skill"
    - "Update README — Run /update-readme"
    - "Sync runbook — Run /sync-runbook if plan has manual-operation blocks"
    - "Update plan status to Deployed/Complete"
  skip_when:
    - "fix/extension plans"
    - "meta/repo layer"
    - "investigation/audit plans"

dispatch:
  target: github-issues
  owner: derio-net
  project_board: "Derio Ops"
  default_repo: derio-net/frank
  labels:
    agentic: vk-ready
    manual: manual
```

**Note:** No `structure:` section — Phase/Task/Step markers are invariants hardcoded in vk-plan and vk-execute. `dispatch.owner` is required for vk-dispatch and vk-progress to reach GitHub without hardcoded org names.

- [x] **Step 2: Verify YAML**

```bash
python3 -c "import yaml; yaml.safe_load(open('docs/superpowers/plan-config.yaml'))" && echo "Valid YAML"
```

- [x] **Step 3: Commit** *(completed out-of-band in commit b8d2bdd)*

```bash
git add docs/superpowers/plan-config.yaml
git commit -m "feat: add plan-config.yaml profile for Frank

Profile-driven plan behavior: Frank filename convention, Spec+Status headers,
post-deploy checklist, Derio Ops dispatch config."
```

### Task 2: Delete vendored superpowers skills

**Files:**
- Delete: 19 skill directories under `.claude/skills/` (keep `gitnexus/`)

- [x] **Step 1: Delete all vendored superpowers skill directories**

```bash
for dir in brainstorming blog-post deploy-app dispatching-parallel-agents \
  executing-plans finishing-a-development-branch media receiving-code-review \
  requesting-code-review subagent-driven-development sync-runbook \
  systematic-debugging test-driven-development update-readme \
  using-git-worktrees using-superpowers verification-before-completion \
  writing-plans writing-skills; do
  rm -rf ".claude/skills/$dir"
done
```

- [x] **Step 2: Verify only gitnexus remains**

```bash
ls .claude/skills/
# Expected: only gitnexus/
```

- [x] **Step 3: Commit**

```bash
git add -A .claude/skills/
git commit -m "chore: delete vendored superpowers skills

Skills are now installed at user level via plugins. Only gitnexus
(Frank-specific) remains in the repo."
```

### Task 3: Delete sync-superpowers.sh

**Files:**
- Delete: `scripts/sync-superpowers.sh`

- [x] **Step 1: Delete the script**

```bash
rm scripts/sync-superpowers.sh
```

- [x] **Step 2: Commit**

```bash
git add scripts/sync-superpowers.sh
git commit -m "chore: delete sync-superpowers.sh

No longer needed — skills installed at user level via plugins, not vendored."
```

### Task 4: Replace validate-plans.sh with thin wrapper

**Files:**
- Modify: `scripts/validate-plans.sh`

- [x] **Step 1: Replace with thin wrapper**

```bash
#!/usr/bin/env bash
# Thin wrapper — delegates to the canonical validator from superpowers-for-vk.
# Falls back to minimal local validation if the plugin validator is not found.
set -euo pipefail

PLUGIN_VALIDATOR=""
for candidate in \
  "$HOME/.claude/plugins/cache/derio-net/superpowers-for-vk/"*/scripts/validate-plans.sh \
  "$HOME/repos/superpowers-for-vk/scripts/validate-plans.sh"; do
  if [ -x "$candidate" ]; then
    PLUGIN_VALIDATOR="$candidate"
    break
  fi
done

if [ -n "$PLUGIN_VALIDATOR" ]; then
  exec "$PLUGIN_VALIDATOR" "$@"
fi

echo "WARNING: superpowers-for-vk validator not found — running minimal checks" >&2
ERRORS=()
for f in "$@"; do
  [ -f "$f" ] || continue
  base="$(basename "$f" .md)"
  header=$(head -20 "$f")
  if ! echo "$header" | grep -q '\*\*Status:\*\*'; then
    ERRORS+=("$base: missing **Status:**")
  fi
done
if [ ${#ERRORS[@]} -gt 0 ]; then
  echo "Plan validation failed:" >&2
  for e in "${ERRORS[@]}"; do echo "  - $e" >&2; done
  exit 1
fi
```

- [x] **Step 2: Verify syntax**

```bash
bash -n scripts/validate-plans.sh && echo "Syntax OK"
```

- [x] **Step 3: Commit**

```bash
git add scripts/validate-plans.sh
git commit -m "refactor: replace validate-plans.sh with thin wrapper

Delegates to the canonical validator from superpowers-for-vk plugin.
Falls back to minimal local validation if plugin not installed."
```

### Task 5: Update plan-status.sh for Phase headers

**Files:**
- Modify: `scripts/plan-status.sh`

- [x] **Step 1: Update the --open loop to recognize Phase headers**

In the `--open` section of `scripts/plan-status.sh`, locate the block starting at `# Collect tasks with their open steps` and extend it to detect `## Phase N:` headers. Replace the inner parsing loop (the `while IFS= read -r line; do` block) with:

```bash
    current_phase=""
    current_task=""
    current_idx=-1

    while IFS= read -r line; do
      # Phase header: ## Phase N: Name [type]
      if [[ "$line" =~ ^##\ Phase\ [0-9]+:\ (.+)\ \[(manual|agentic)\]$ ]]; then
        current_phase="${BASH_REMATCH[1]}"
      fi

      # Task header: ### Task N: Name
      if [[ "$line" =~ ^###\ Task\ [0-9]+:\ (.+)$ ]]; then
        current_task="${BASH_REMATCH[1]}"
        if [ -n "$current_phase" ]; then
          current_task="$current_phase / $current_task"
        fi
        current_idx=$(( ${#task_names[@]} ))
        task_names+=("$current_task")
        task_steps+=("")
      fi

      # Open checkbox: - [ ] **...**
      if [[ "$line" =~ ^-\ \[\ \]\ \*\*(.+)\*\*$ ]]; then
        step_name="${BASH_REMATCH[1]}"
        step_name="${step_name#Step [0-9]: }"
        step_name="${step_name#Step [0-9][0-9]: }"
        if [ "$current_idx" -ge 0 ]; then
          if [ -n "${task_steps[$current_idx]}" ]; then
            task_steps[$current_idx]="${task_steps[$current_idx]}|$step_name"
          else
            task_steps[$current_idx]="$step_name"
          fi
        fi
      fi
    done < "$f"
```

- [x] **Step 2: Test against a phased plan**

```bash
./scripts/plan-status.sh --open
# Should display tasks grouped under phases (phase name prepended to task name)
```

- [x] **Step 3: Commit**

```bash
git add scripts/plan-status.sh
git commit -m "feat: update plan-status.sh to understand Phase headers

The --open view now prepends the parent Phase name to each Task when
the plan uses the Phase > Task > Step hierarchy."
```

### Task 6: Update rules for vk-plan canonical skill

**Files:**
- Modify: `.claude/rules/repo-workflows.md`
- Modify: `.claude/rules/repo-principles.md`
- Modify: `.claude/rules/plan-post-deploy-checklist.md`

- [x] **Step 1: Update repo-workflows.md**

Locate the Standard Layer Workflow steps 2-3 in `.claude/rules/repo-workflows.md`. Replace:

```markdown
2. **Plan** — `/writing-plans` to produce a step-by-step implementation plan. The layer code is chosen at this step (see `docs/layers.yaml` for the registry)
3. **Execute** — `/executing-plans` to implement the plan with review checkpoints
```

With:

```markdown
2. **Plan** — `/vk-plan` to produce a phase-structured implementation plan. The layer code is chosen at this step (see `docs/layers.yaml` for the registry). Plan behavior is driven by `docs/superpowers/plan-config.yaml`
3. **Execute** — vk-plan offers three execution paths: VK dispatch, subagent-driven, or inline execution
```

In the Plan Management Scripts section, replace:

```markdown
- `scripts/validate-plans.sh [files...]` — validate plan headers (filename, Spec, Status, Task heading level)
```

With:

```markdown
- `scripts/validate-plans.sh [files...]` — validate plan headers (delegates to canonical validator from superpowers-for-vk plugin)
```

- [x] **Step 2: Update repo-principles.md**

Delete the entire "### Superpowers plugin skills (vendored)" section (from `### Superpowers plugin skills (vendored)` through the closing `Check for updates periodically...` line). Replace with:

```markdown
### Skills

Skills are installed at user level via the `superpowers` and `superpowers-for-vk` plugins. They are NOT vendored in this repo (only gitnexus skills remain repo-local in `.claude/skills/gitnexus/`).

Plan behavior is driven by the profile at `docs/superpowers/plan-config.yaml`.
```

- [x] **Step 3: Update plan-post-deploy-checklist.md**

Prepend this note at the very top of the file:

```markdown
> **Note:** vk-plan auto-appends a Post-Deploy Checklist phase from
> `docs/superpowers/plan-config.yaml` (`post_deploy` section). This rule
> documents the checklist content for reference and for manual plan creation.

```

- [x] **Step 4: Verify changes**

```bash
grep -q "vk-plan" .claude/rules/repo-workflows.md && echo "OK: workflows"
grep -q "user level" .claude/rules/repo-principles.md && echo "OK: principles"
grep -q "vk-plan auto-appends" .claude/rules/plan-post-deploy-checklist.md && echo "OK: post-deploy"

# Ensure no references to sync-superpowers.sh remain
grep -r "sync-superpowers" .claude/rules/ && echo "FAIL: stale refs" || echo "OK: no stale refs"
```

- [x] **Step 5: Commit**

```bash
git add .claude/rules/repo-workflows.md .claude/rules/repo-principles.md .claude/rules/plan-post-deploy-checklist.md
git commit -m "docs: update rules for vk-plan canonical skill

- repo-workflows: reference vk-plan instead of writing-plans
- repo-principles: remove vendored superpowers section
- plan-post-deploy-checklist: note auto-append from profile"
```

### Task 7: Update plan-checklist-check hook for Phase format

**Files:**
- Modify: `scripts/hooks/plan-checklist-check.sh`

- [x] **Step 1: Extend the detection for Phase-based plans**

In `scripts/hooks/plan-checklist-check.sh`, locate the final check:

```bash
if ! grep -q 'blog.*post\|/blog-post\|Post-Deploy' "$FILE_PATH"; then
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PostToolUse\",\"additionalContext\":\"This standard layer plan is missing the Post-Deploy Checklist (blog post, README update, runbook sync). See .claude/rules/plan-post-deploy-checklist.md. Add a final task with these steps.\"}}"
fi
```

Replace with:

```bash
# Phase-based plans get post-deploy auto-appended by vk-plan via profile
if grep -q '^## Phase' "$FILE_PATH"; then
  # Phase-based plan — check for a post-deploy phase specifically
  if ! grep -q 'Post-Deploy\|post.deploy' "$FILE_PATH"; then
    echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PostToolUse\",\"additionalContext\":\"This phase-based plan is missing a Post-Deploy phase. vk-plan should auto-append it from plan-config.yaml. If this is a fix/meta/investigation plan, ignore this warning.\"}}"
  fi
elif ! grep -q 'blog.*post\|/blog-post\|Post-Deploy' "$FILE_PATH"; then
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PostToolUse\",\"additionalContext\":\"This standard layer plan is missing the Post-Deploy Checklist (blog post, README update, runbook sync). See .claude/rules/plan-post-deploy-checklist.md. Add a final task with these steps.\"}}"
fi
```

- [x] **Step 2: Verify syntax**

```bash
bash -n scripts/hooks/plan-checklist-check.sh && echo "Syntax OK"
```

- [x] **Step 3: Commit**

```bash
git add scripts/hooks/plan-checklist-check.sh
git commit -m "fix: update plan-checklist-check hook for Phase format

Phase-based plans check for a Post-Deploy phase header instead of
inline blog/README references."
```

---

## Phase 1: Active Plan Conversion [agentic]
<!-- Tracking: https://github.com/derio-net/frank/issues/36 -->

Convert the 4 active plans from flat Task format to Phase > Task > Step format. Preserve all existing checkbox state and content.

### Task 1: Convert multi-cluster-restructure plan

**Files:**
- Modify: `docs/superpowers/plans/2026-03-20--repo--multi-cluster-restructure.md`

- [ ] **Step 1: Read the current plan**

Read the full plan file. Identify the existing `### Task N:` sections and their natural phase boundaries. For a monorepo restructure, typical phases:
- Phase 0: Pre-flight [manual] — disable auto-sync, take inventory (if present)
- Phase 1: Restructure [agentic] — the bulk of the work
- Phase 2: Post-restructure verification [agentic or manual]

- [ ] **Step 2: Update the banner**

Replace the existing "For agentic workers" banner with:

```markdown
> **For VK agents:** Use vk-execute to implement assigned phases.
> **For local execution:** Use subagent-driven-development or executing-plans.
> **For dispatch:** Use vk-dispatch to create Issues from this plan.
```

- [ ] **Step 3: Insert Phase headers**

Group existing `### Task N:` sections under `## Phase N: <name> [<type>]` headers. Rules:
- Preserve all existing `### Task N:` headers and their content unchanged
- Preserve all existing checkbox state (`- [x]` stays checked, `- [ ]` stays unchecked)
- Add `[manual]` or `[agentic]` tag to each new Phase header
- Tasks must be h3 (`###`) — do NOT convert to h4

- [ ] **Step 4: Validate**

```bash
scripts/validate-plans.sh docs/superpowers/plans/2026-03-20--repo--multi-cluster-restructure.md && echo "PASS"
```

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/plans/2026-03-20--repo--multi-cluster-restructure.md
git commit -m "refactor: convert multi-cluster-restructure plan to Phase format

Wraps existing Tasks under sequential Phase headers. Preserves all
checkbox state and content. Updates banner to reference vk-execute."
```

### Task 2: Convert safe-update-automation plan

**Files:**
- Modify: `docs/superpowers/plans/2026-03-25--repo--safe-update-automation.md`

- [ ] **Step 1: Read the current plan**

Read the full plan. This plan has three pipeline tracks (Renovate, Talos version tracking, ARC v2). These map naturally to phases.

- [ ] **Step 2: Apply the conversion procedure**

Same procedure as Task 1: update banner, wrap existing `### Task N:` sections under `## Phase N:` headers with appropriate phase names and types. Natural phase split: one phase per pipeline track. Preserve all checkbox state.

- [ ] **Step 3: Validate**

```bash
scripts/validate-plans.sh docs/superpowers/plans/2026-03-25--repo--safe-update-automation.md && echo "PASS"
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-03-25--repo--safe-update-automation.md
git commit -m "refactor: convert safe-update-automation plan to Phase format

Splits into three phases (one per pipeline track: Renovate, Talos,
ARC v2). Preserves all checkbox state and content."
```

### Task 3: Convert cicd-platform plan

**Files:**
- Modify: `docs/superpowers/plans/2026-03-29--cicd--platform.md`

- [ ] **Step 1: Read the current plan**

Read the full plan. This is a multi-component deployment (Gitea, Tekton, Zot). Status is `semi-Deployed` with pending items — **preserve the status value exactly**.

- [ ] **Step 2: Apply the conversion procedure**

Same procedure. Natural phase split: one phase per component (or one phase for base infrastructure + one per component). The `semi-Deployed` status may fail validation against the profile's `status_values` — if so, update to `In Progress` with a note in the header explaining the pending items, or leave as `semi-Deployed` and add a `status_values` entry in the profile. **Preferred:** change to `In Progress` since `semi-Deployed` isn't in the profile.

- [ ] **Step 3: Validate**

```bash
scripts/validate-plans.sh docs/superpowers/plans/2026-03-29--cicd--platform.md && echo "PASS"
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-03-29--cicd--platform.md
git commit -m "refactor: convert cicd-platform plan to Phase format

Splits into phases per component (Gitea, Tekton, Zot). Preserves all
checkbox state. Normalizes status to In Progress (was 'semi-Deployed',
not in profile status_values)."
```

### Task 4: Convert blog-media-infrastructure plan

**Files:**
- Modify: `docs/superpowers/plans/2026-04-09--repo--blog-media-infrastructure.md`

- [ ] **Step 1: Read the current plan**

Read the full plan. This is a straightforward implementation plan — likely a single agentic phase with a post-deploy manual phase.

- [ ] **Step 2: Apply the conversion procedure**

Same procedure. Likely split:
- Phase 0: Implementation [agentic] — all existing tasks
- Phase 1: Post-Deploy Checklist [manual] — if the plan already has one, preserve it

- [ ] **Step 3: Validate**

```bash
scripts/validate-plans.sh docs/superpowers/plans/2026-04-09--repo--blog-media-infrastructure.md && echo "PASS"
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-04-09--repo--blog-media-infrastructure.md
git commit -m "refactor: convert blog-media-infrastructure plan to Phase format

Splits implementation tasks under a single agentic phase, preserving
the existing post-deploy checklist as a manual phase."
```

---

*Last progress sync: —*
