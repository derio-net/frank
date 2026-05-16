# vk v2 — Observed Misfires & Discrepancies

Logged during: writing plans for `2026-04-15--repo--frank-papers-series-design.md`
Session date: 2026-05-16
vk version at time of session: **1.4.3** (should have been 2.1.4 — see §E)
vk version after remediation: **2.1.4**
Agent: Claude Sonnet 4.6 via vk-plan skill (superpowers-for-vk 2.1.4)

All issues below were discovered by running the vk CLI against a new v2
folder-format plan. None of them blocked the work — workarounds are noted
inline. This list is for ironing out v2.

---

## A — Missing CLI command: `vk plan create`

### A1 · `vk plan create` does not exist in the CLI

**Skill says:**
```bash
vk plan create --slug <YYYY-MM-DD-slug> --target-repo <owner/repo> \
    --spec docs/superpowers/specs/<spec-file>.md \
    --phases-file <phases.yaml> \
    --prose-file <prose.md>
```

**Actual CLI (`vk plan --help`):**
```
Commands:
  format       Print the plan's actual format.
  new          Generate a new plan file skeleton.
  self-review  Run automated quality checks on a plan file.
  spec-index   Update the spec's Implementation Plans table for this plan.
  rework-add   ...
  convert      ...
  rework       ...
  rework-list  ...
```

`create` is not a subcommand. `vk plan create` exits with `No such command 'create'`.

**Impact:** The skill's scaffolding step (step 5 of the Procedure) cannot be
followed. Agent falls back to writing `_meta.yaml`, `_prose.md`, and `NN.yaml`
files manually via the Write tool.

**Workaround:** Write the plan folder manually. The skill should either be
updated to use `vk plan new` or `vk plan create` needs to be implemented.

---

### A2 · `vk plan new --save` generates v1 flat markdown, not v2 folder format

**Skill says:** v2 folder format is the standard (`_meta.yaml` + `_prose.md` + `NN.yaml`).

**Actual behavior:** `vk plan new --save <name>` writes a single v1 flat `.md`
file to `docs/superpowers/plans/<name>.md`. There is no CLI path to scaffold
a v2 folder.

Observed output of `vk plan new`:
```
# 2026 05 16  Repo  Frank Papers Series Implementation Plan

**Spec:** `docs/superpowers/specs/...`
**Status:** Not Started

**Goal:** [One sentence]

---

## Phase 1: [Name] 

### Task 1: [Component]

- [ ] **Step 1: [Action]**
```

**Impact:** The CLI and the skill describe different default formats. Every v2
plan must be scaffolded manually.

**Workaround:** Write files by hand. Long-term: `vk plan new --save` should
create the folder structure and files, or `vk plan create` (A1) needs implementing.

---

## B — `vk plan self-review` incompatible with v2 folder format

### B1 · Passing the plan directory path throws `IsADirectoryError`

**Skill says:** `vk plan self-review <plan-dir>` (step 7 of Procedure).

**Actual behavior:**
```
IsADirectoryError: [Errno 21] Is a directory: '.../plans/2026-05-16--repo--...'
```

The command calls `plan_path.read_text()` which fails on a directory.

**Workaround:** Pass `_prose.md` as the path instead of the directory.

---

### B2 · `vk plan self-review _prose.md` fails on v2 plans: looks for v1 `**Depends on:**` markers

**Actual behavior after workaround (passing `_prose.md`):**
```
Error: Phase 1 has no **Depends on:** line. Run 'vk plan convert ... --add-deps --yes' ...
```

The self-review reads `_prose.md` and looks for v1-style inline `**Depends on:**`
annotations on each `## Phase N` heading. v2 plans encode dependencies in
`phase.depends_on: [N, ...]` inside each `NN.yaml` file. The self-review command
does not read the YAML files at all.

**Impact:** `vk plan self-review` effectively cannot be used on v2 plans.
The skill's step 7 is a no-op.

**Workaround:** None available without modifying the plan files. Accepted the
broken self-review and moved on — the YAML `depends_on` fields are correct.

**Fix needed:** `self-review` should accept a directory and read `NN.yaml` files
for dependency information, or the `_prose.md` format should not require v1
markers when `NN.yaml` files are present.

---

## C — `vk plan spec-index` incompatible with v2 folder format

### C1 · Passing the plan directory path throws `IsADirectoryError`

Same root cause as B1: `parse_plan(plan_path)` calls `path.read_text()` on
whatever path is given. Directory path → `IsADirectoryError`.

**Workaround:** Pass `_prose.md` as the path.

---

### C2 · `spec-index` requires `**Spec:**` header in `_prose.md`

v2 plans store the spec reference in `_meta.yaml` (`spec: docs/...`).
`spec-index` reads the file it's given as markdown and looks for `**Spec:**`
in the text. If the header is absent, it prints:

```
No **Spec:** header in plan. Nothing to update.
```

and exits 0 (silent no-op).

**Workaround:** Add a redundant `**Spec:** ...` line to `_prose.md`. This
duplicates information already in `_meta.yaml`.

**Fix needed:** When given a directory (or when `_prose.md` has no `**Spec:**`),
fall back to reading `spec:` from `_meta.yaml`.

---

### C3 · `spec-index` leaves `Repo` column empty for v2 plans

When spec-index reads `_prose.md` and writes the Implementation Plans table
row, the `Repo` column is populated from parsing the plan's `target_repo`
field. That field is in `_meta.yaml`, which `spec-index` does not read when
given a `_prose.md` path.

**Result:**
```markdown
| The Frank Papers — Phase 0 |  | `..._prose.md` | Not Started | — |
```

The Repo column is blank instead of `derio-net/frank`.

**Workaround:** Manually edit the spec table after running `spec-index --yes`.

**Fix needed:** Same as C2 — spec-index should read `_meta.yaml` when operating
on a v2 folder plan.

---

### C4 · Skill claims `vk plan create` appends spec table automatically (no separate spec-index step)

The skill says:
> `vk plan create` ALSO appends a row to the spec's `## Implementation Plans`
> table — there is no separate spec-index step.

Since `vk plan create` doesn't exist (A1), agents must call `vk plan spec-index`
separately. When they do, they hit C1–C3 above.

**Impact:** The skill's promised "no separate spec-index step" is doubly broken:
the create command is missing, and spec-index has v2 incompatibilities.

---

### C5 · `spec-index` writes a `Status` column that breaks `vk spec status` parsing

When `spec-index` writes a row to the spec's `## Implementation Plans` table, it
generates a 5-column format:

```markdown
| Plan | Repo | File | Status | Depends on |
```

The correct format that `vk spec status` can parse is 4 columns (no `Status`):

```markdown
| Plan | Repo | File | Depends on |
```

`vk spec status` computes Status dynamically from each plan's `_meta.yaml`. When
the table has 5 columns, the parser cannot match the `File` column (position 3 vs
expected position 3 of a 4-column table is fine — but if the parser is
column-order-sensitive, the extra `Status` column shifts `Depends on` out of
position). Observed effect: `vk spec status` outputs an empty table with `0/0
plans complete` even though the plans exist.

**Workaround:** Manually remove the `Status` column from the spec table and
change paths from `_prose.md` to directory paths (see C6).

**Fix needed:** `spec-index` should write the 4-column format without `Status`.

---

### C6 · `spec-index` writes `_prose.md` file paths instead of plan directory paths

When given `_prose.md` as the path (workaround for C1), `spec-index` records the
literal `_prose.md` path in the spec table `File` column:

```markdown
| ... | `docs/superpowers/plans/2026-05-16--repo--frank-papers-phase-0/_prose.md` | ... |
```

`vk spec status` expects a **directory** path:

```markdown
| ... | `docs/superpowers/plans/2026-05-16--repo--frank-papers-phase-0/` | ... |
```

It resolves the plan by reading `<File>/_meta.yaml`. Given a `_prose.md` path,
it attempts to open `_prose.md/_meta.yaml` (invalid — `_prose.md` is a file, not
a directory), silently fails, and the row disappears from the status output.

Combined with C5, both bugs cause `vk spec status` to show `0/0 plans` even
though all plan files are correctly written.

**Workaround:** After running `spec-index`, manually:
1. Remove the `Status` column from the spec table header and divider (C5).
2. Strip `/_prose.md` from each `File` cell, leaving the directory path (C6).

**Fix needed:** When `spec-index` is operating on a v2 plan, it should record the
plan directory (parent of `_prose.md`), not the `_prose.md` path itself.

---

## D — `plan-checklist-check.sh` hook misfires on `_prose.md` files

### D1 · Layer extraction broken for `_prose.md` — `repo` layer exemption never fires

`plan-checklist-check.sh` extracts the layer from the plan's basename:
```bash
BASE=$(basename "$FILE_PATH" .md)   # → "_prose" for _prose.md files
LAYER="${BASE#*--}"                  # → "_prose" (no "--" in "_prose")
LAYER="${LAYER%%--*}"                # → "_prose"
case "$LAYER" in
  repo) exit 0 ;;                    # never matches
esac
```

For `_prose.md` files (path like `.../2026-05-16--repo--frank-papers-phase-0/_prose.md`),
`basename` gives `_prose`, not `repo`. The layer exemption for `repo` (and
presumably other skip layers like `fix`, `investigation`) never triggers.

The hook then proceeds to check whether the plan has a Post-Deploy phase —
on every Write/Edit of a `_prose.md`, regardless of layer.

**Fix needed:** When the path ends in `/_prose.md`, extract the layer from the
parent directory's name instead:
```bash
if [[ "$(basename "$FILE_PATH")" == "_prose.md" ]]; then
  PLAN_DIR=$(basename "$(dirname "$FILE_PATH")")  # e.g. "2026-05-16--repo--..."
  BASE="$PLAN_DIR"
fi
```

---

### D2 · `Post-Deploy` grep is case-sensitive and misses `Post-deploy` (lowercase d)

The hook checks:
```bash
if ! grep -q 'Post-Deploy\|post.deploy' "$FILE_PATH"; then
    echo "...missing Post-Deploy phase..."
fi
```

The pattern `Post-Deploy` is case-sensitive. A prose file with
`## Phase 9: Post-deploy checklist` (lowercase `d`) does not match — the
warning fires even though a post-deploy phase exists.

The pattern `post.deploy` (BRE: `post` + any char + `deploy`) would catch
`post-deploy` but only in lowercase. `Post-deploy` (capital P) does not match
`post.deploy`.

**Fix needed:** Use case-insensitive grep (`grep -qi`) or expand the pattern:
```bash
grep -qi 'post.deploy\|post-deploy checklist' "$FILE_PATH"
```

---

---

## E — CLI version skew: vk 1.4.3 in use while plugin is at 2.1.4

### E1 · Root cause: `install.sh` not re-run after plugin version bump

**Symptom:** `vk --version` reports `1.4.3`; plugin cache and `pyproject.toml`
in the source repo are both at `2.1.4`.

**Root cause:** The vk CLI binary and the plugin are versioned together in the
`superpowers-for-vk` repo, but they are installed through two independent
channels:

1. **Plugin cache** (`~/.claude/plugins/cache/derio-net/superpowers-for-vk/2.1.4/`) —
   updated by the Claude Code plugin system automatically when a new version is
   published. This controls the skills, rules, and hooks the agent sees.

2. **CLI binary** (`~/.local/bin/vk`) — installed by `uv tool install` as part
   of `scripts/install.sh`. This controls what `vk plan`, `vk apply`, etc. do.

When the plugin is updated from 1.4.3 → 2.1.4, channel 1 updates automatically.
Channel 2 does **not** — `install.sh` must be re-run manually. Without it, the
agent loads skills that describe v2 CLI behaviour (`vk plan create`, v2 folder
format) while actually running v1 CLI commands. This is what happened in this
session.

**Remediation:**
```bash
bash /home/claude/repos/superpowers-for-vk/scripts/install.sh
```

Output confirmed:
```
- vk==1.4.3 (from file:///...superpowers-for-vk/1.4.3)
+ vk==2.1.4 (from file:///home/claude/repos/superpowers-for-vk)
```

**Prevention gap:** There is no automatic check at session start that detects
skew between the plugin cache version and `vk --version`. An agent running a
plan session may silently operate against a stale CLI version.

**Fix needed:** A session-start check (or an `install.sh` cron or hook) that
compares the plugin cache version against `vk --version` and warns if they
differ. Something like:

```bash
# In install.sh or a separate health-check script:
CACHE_VER=$(jq -r '.version' \
  ~/.claude/plugins/cache/derio-net/superpowers-for-vk/*/plugin.json 2>/dev/null \
  | tail -1)
CLI_VER=$(vk --version 2>/dev/null | awk '{print $2}')
if [ "$CACHE_VER" != "$CLI_VER" ]; then
  echo "WARNING: vk CLI ($CLI_VER) is out of sync with plugin cache ($CACHE_VER)."
  echo "  Run: bash /home/claude/repos/superpowers-for-vk/scripts/install.sh"
fi
```

---

## Summary table

| ID | Area | Severity | Workaround available? |
|----|------|----------|-----------------------|
| A1 | `vk plan create` missing | High — blocks skill scaffolding step | Yes — write files manually |
| A2 | `vk plan new` generates v1 format | High — no CLI path to v2 scaffold | Yes — write files manually |
| B1 | `self-review` dir → IsADirectoryError | Medium — clear error, easy to avoid | Yes — pass `_prose.md` |
| B2 | `self-review` fails on v2 prose | High — self-review is unusable for v2 | None |
| C1 | `spec-index` dir → IsADirectoryError | Medium — clear error, easy to avoid | Yes — pass `_prose.md` |
| C2 | `spec-index` needs `**Spec:**` in prose | Medium — silent no-op otherwise | Yes — add header to prose |
| C3 | `spec-index` leaves Repo column empty | Low — cosmetic, easy manual fix | Yes — edit table manually |
| C4 | Skill promises auto spec-index via create | High — skill is misleading | N/A — workaround is A1 fix |
| C5 | `spec-index` writes extra `Status` column — breaks `vk spec status` | High — `vk spec status` shows 0/0 plans | Yes — remove column manually |
| C6 | `spec-index` writes `_prose.md` path instead of plan dir — breaks `vk spec status` | High — plans invisible to spec status | Yes — strip `/_prose.md` manually |
| D1 | Hook layer extraction broken for `_prose.md` | Low — false positive warning only | Accept the noise |
| D2 | Hook Post-Deploy grep case-sensitive | Low — false positive warning only | Accept the noise |
| E1 | CLI version skew — `install.sh` not re-run | High — agent uses wrong CLI silently | Fixed: re-ran `install.sh` |
