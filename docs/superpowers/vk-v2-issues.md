# vk v2 — Observed Misfires & Discrepancies

Logged during: writing plans for `2026-04-15--repo--frank-papers-series-design.md`
Session date: 2026-05-16
vk version at time of session: **1.4.3** (should have been 2.1.4 — see §E)
vk version after remediation: **2.1.4**
Agent: Claude Sonnet 4.6 via vk-plan skill (superpowers-for-vk 2.1.4)

All issues below were discovered by running the vk CLI against a new v2
folder-format plan. None of them blocked the work — workarounds are noted
inline. This list is for ironing out v2.

**Verification pass:** 2026-05-16 — re-tested every issue against the
correct vk 2.1.4 CLI after `install.sh` was re-run. Status column in the
summary table reflects post-verification state.

---

## A — Missing CLI command: `vk plan create`

### A1 · `vk plan create` does not exist in the CLI

> **Status: FIXED in 2.1.4** — `vk plan create` now exists and scaffolds a
> v2 plan folder while atomically appending a spec row (see also C4, C5, C6).

**Skill says:**
```bash
vk plan create --slug <YYYY-MM-DD-slug> --target-repo <owner/repo> \
    --spec docs/superpowers/specs/<spec-file>.md \
    --phases-file <phases.yaml> \
    --prose-file <prose.md>
```

**Actual CLI at time of session (`vk plan --help` on 1.4.3):**
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

`create` was not a subcommand. `vk plan create` exited with `No such command 'create'`.

**Impact:** The skill's scaffolding step (step 5 of the Procedure) could not be
followed. Agent fell back to writing `_meta.yaml`, `_prose.md`, and `NN.yaml`
files manually via the Write tool.

---

### A2 · `vk plan new --save` generates v1 flat markdown, not v2 folder format

> **Status: MOOT in 2.1.4** — `vk plan new` is removed. `vk plan create`
> scaffolds the correct v2 folder structure (`_meta.yaml` + `_prose.md` +
> `NN.yaml` per phase) from a `--phases-file` YAML.

**Skill says:** v2 folder format is the standard (`_meta.yaml` + `_prose.md` + `NN.yaml`).

**Actual behavior at time of session:** `vk plan new --save <name>` wrote a single v1 flat `.md`
file to `docs/superpowers/plans/<name>.md`. There was no CLI path to scaffold
a v2 folder.

---

## B — `vk plan self-review` incompatible with v2 folder format

### B1 · Passing the plan directory path throws `IsADirectoryError`

> **Status: FIXED in 2.1.4** — `vk plan self-review` now takes `PLAN_DIR` as
> its argument (a directory path). No `IsADirectoryError`.

**Actual behavior at time of session:**
```
IsADirectoryError: [Errno 21] Is a directory: '.../plans/2026-05-16--repo--...'
```

The command called `plan_path.read_text()` which failed on a directory.

---

### B2 · `vk plan self-review _prose.md` fails on v2 plans: looks for v1 `**Depends on:**` markers

> **Status: FIXED in 2.1.4** — `self-review` correctly reads v2 plan folders.
> Verified: `vk plan self-review docs/superpowers/plans/2026-05-16--repo--frank-papers-phase-0`
> and `…/frank-papers-paper-00` both output `self-review passed`.

**Actual behavior after workaround at time of session (passing `_prose.md`):**
```
Error: Phase 1 has no **Depends on:** line. Run 'vk plan convert ... --add-deps --yes' ...
```

The self-review read `_prose.md` and looked for v1-style inline `**Depends on:**`
annotations on each `## Phase N` heading. v2 plans encode dependencies in
`phase.depends_on: [N, ...]` inside each `NN.yaml` file. The self-review command
did not read the YAML files at all.

---

## C — `vk plan spec-index` incompatible with v2 folder format

> **Status: MOOT — `vk plan spec-index` removed in 2.1.4.** Its responsibility
> was merged into `vk plan create`, which appends the spec row atomically as
> part of plan scaffolding. C1–C4 are moot for the same reason. C5 and C6
> described bugs in the output spec-index wrote; `vk plan create` writes the
> correct format (verified below).

### C1 · Passing the plan directory path throws `IsADirectoryError`

> **Status: MOOT** — `vk plan spec-index` does not exist in 2.1.4.

Same root cause as B1: `parse_plan(plan_path)` called `path.read_text()` on
whatever path was given. Directory path → `IsADirectoryError`.

---

### C2 · `spec-index` requires `**Spec:**` header in `_prose.md`

> **Status: MOOT** — `vk plan spec-index` does not exist in 2.1.4.

v2 plans store the spec reference in `_meta.yaml` (`spec: docs/...`).
`spec-index` read the file it was given as markdown and looked for `**Spec:**`
in the text. If the header was absent, it printed:

```
No **Spec:** header in plan. Nothing to update.
```

and exited 0 (silent no-op).

---

### C3 · `spec-index` leaves `Repo` column empty for v2 plans

> **Status: MOOT** — `vk plan spec-index` does not exist in 2.1.4.

When spec-index read `_prose.md` and wrote the Implementation Plans table
row, the `Repo` column was populated from parsing the plan's `target_repo`
field. That field is in `_meta.yaml`, which `spec-index` did not read when
given a `_prose.md` path.

**Result:**
```markdown
| The Frank Papers — Phase 0 |  | `..._prose.md` | Not Started | — |
```

The Repo column was blank instead of `derio-net/frank`.

---

### C4 · Skill claims `vk plan create` appends spec table automatically (no separate spec-index step)

> **Status: RESOLVED in 2.1.4** — `vk plan create` does now append a spec row
> automatically. No separate step needed. The claim in the skill is now correct.

The skill said:
> `vk plan create` ALSO appends a row to the spec's `## Implementation Plans`
> table — there is no separate spec-index step.

At session time, `vk plan create` did not exist (A1), so agents had to call
`vk plan spec-index` separately and hit C1–C3.

---

### C5 · `spec-index` writes a `Status` column that breaks `vk spec status` parsing

> **Status: MOOT** — `vk plan spec-index` removed. `vk plan create` writes the
> correct 4-column format (verified: `| Plan | Repo | File | Depends on |`
> with a directory path in File — no Status column).

When `spec-index` wrote a row it generated a 5-column format:

```markdown
| Plan | Repo | File | Status | Depends on |
```

The correct format that `vk spec status` can parse is 4 columns (no `Status`):

```markdown
| Plan | Repo | File | Depends on |
```

`vk spec status` computes Status dynamically from each plan's `_meta.yaml`.
The extra `Status` column broke parsing — `vk spec status` returned `0/0 plans`.

---

### C6 · `spec-index` writes `_prose.md` file paths instead of plan directory paths

> **Status: MOOT** — `vk plan spec-index` removed. `vk plan create` writes the
> directory path (e.g. `docs/superpowers/plans/9999-99-99--test--slug/`), not
> a `_prose.md` path (verified by running create against a test spec).

When given `_prose.md` as the path (workaround for C1), `spec-index` recorded the
literal `_prose.md` path in the spec table `File` column:

```markdown
| ... | `docs/superpowers/plans/2026-05-16--repo--frank-papers-phase-0/_prose.md` | ... |
```

`vk spec status` expects a **directory** path. Combined with C5, both bugs caused
`vk spec status` to show `0/0 plans complete` for the Frank Papers spec.
Both were manually corrected in the spec table in this session.

---

## D — `plan-checklist-check.sh` hook misfires on `_prose.md` files

> **Status: FIXED** — Both D1 and D2 were fixed in `scripts/hooks/plan-checklist-check.sh`
> in this session. The hook now detects `_prose.md` filenames and extracts the
> layer from the parent directory; the grep is now case-insensitive.

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
other skip layers like `fix`, `investigation`) never triggers.

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
`post-deploy` but only in lowercase. `Post-deploy` (capital P, lowercase d)
matches neither pattern. Verified against the Frank Papers Phase 0 `_prose.md`.

**Fix needed:** Use case-insensitive grep (`grep -qi`) or expand the pattern:
```bash
grep -qi 'post.deploy\|post-deploy checklist' "$FILE_PATH"
```

---

## E — CLI version skew: vk 1.4.3 in use while plugin is at 2.1.4

### E1 · Root cause: `install.sh` not re-run after plugin version bump

> **Status: FIXED** — `install.sh` was re-run during this session. `vk --version`
> now reports `2.1.4`. Prevention gap (no automatic skew detection) remains open.

**Symptom:** `vk --version` reported `1.4.3`; plugin cache and `pyproject.toml`
in the source repo were both at `2.1.4`.

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

Verified against vk 2.1.4 on 2026-05-16.

| ID | Area | Severity (at log time) | Status in 2.1.4 |
|----|------|------------------------|-----------------|
| A1 | `vk plan create` missing | High | ✅ Fixed |
| A2 | `vk plan new` generates v1 format | High | ✅ Moot — `new` removed; `create` does v2 |
| B1 | `self-review` dir → IsADirectoryError | Medium | ✅ Fixed |
| B2 | `self-review` fails on v2 prose | High | ✅ Fixed |
| C1 | `spec-index` dir → IsADirectoryError | Medium | ✅ Moot — `spec-index` removed |
| C2 | `spec-index` needs `**Spec:**` in prose | Medium | ✅ Moot — `spec-index` removed |
| C3 | `spec-index` leaves Repo column empty | Low | ✅ Moot — `spec-index` removed |
| C4 | Skill promises auto spec-index via create | High | ✅ Resolved — `create` does it |
| C5 | `spec-index` writes extra `Status` column | High | ✅ Moot — `create` writes 4-col format |
| C6 | `spec-index` writes `_prose.md` path | High | ✅ Moot — `create` writes dir path |
| D1 | Hook layer extraction broken for `_prose.md` | Low | ✅ Fixed (frank repo hook patched) |
| D2 | Hook Post-Deploy grep case-sensitive | Low | ✅ Fixed (frank repo hook patched) |
| E1 | CLI version skew — `install.sh` not re-run | High | ✅ Fixed (prevention gap remains) |
