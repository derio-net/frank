# vk v2 — Observed Misfires & Discrepancies

Logged during: writing plans for `2026-04-15--repo--frank-papers-series-design.md`
Session date: 2026-05-16
Agent: Claude Sonnet 4.6 via vk-plan skill (superpowers-for-vk 2.1.4)

---

## Wrong binary (1.4.3 vs 2.1.4)

The first plan session ran against vk **1.4.3** while the plugin cache was at
**2.1.4**. Root cause: the plugin auto-updates via Claude Code's plugin system
but the CLI binary requires a manual `bash scripts/install.sh` re-run. When
they drift, the agent runs skills that describe v2 behaviour against a v1 CLI.

During that session, eleven apparent bugs were observed and logged (`A1–C6,
E1`). On re-verification against the correct 2.1.4 binary, **all eleven were
caused by the wrong binary** — none reflect real v2 bugs:

- `vk plan create` (A1), `vk plan new` (A2): `create` exists in 2.1.4;
  `new` is gone. `create` scaffolds v2 folder format and appends the spec row
  atomically, so spec-index (C1–C6) was removed as a separate command.
- `vk plan self-review` (B1, B2): now accepts a plan directory and reads v2
  YAML correctly. Verified `self-review passed` on both Frank Papers plans.
- Spec row format (C5, C6): `vk plan create` writes the correct 4-column
  format with a directory path. No `Status` column, no `_prose.md` suffix.

**Prevention:** Add a session-start version check to `install.sh` or a
health-check script:

```bash
CACHE_VER=$(jq -r '.version' \
  ~/.claude/plugins/cache/derio-net/superpowers-for-vk/*/plugin.json 2>/dev/null \
  | tail -1)
CLI_VER=$(vk --version 2>/dev/null | awk '{print $2}')
if [ "$CACHE_VER" != "$CLI_VER" ]; then
  echo "WARNING: vk CLI ($CLI_VER) out of sync with plugin cache ($CACHE_VER)."
  echo "  Run: bash /home/claude/repos/superpowers-for-vk/scripts/install.sh"
fi
```

---

## D — `plan-checklist-check.sh` hook misfires on `_prose.md` files

These are real v2 bugs — the hook is frank-repo-specific (`scripts/hooks/`,
wired via `.claude/settings.json`). The vk plugin ships no PostToolUse hooks.
Both were fixed in this session.

### D1 · Layer extraction uses filename instead of parent directory — `repo` exemption never fires

`basename _prose.md .md` → `_prose`. The `--layer--` pattern doesn't appear
in `_prose`, so `LAYER` is set to `_prose` and the `repo` exit-0 case never
matches. Every write to a `_prose.md` triggers the checklist warning regardless
of layer.

**Fix applied:** Detect `_prose.md` filenames and derive `BASE` from the
parent directory instead:

```bash
BASE=$(basename "$FILE_PATH" .md)
if [ "$BASE" = "_prose" ]; then
  BASE=$(basename "$(dirname "$FILE_PATH")")
fi
```

### D2 · Post-Deploy grep is case-sensitive — misses `Post-deploy` (lowercase d)

Pattern `Post-Deploy\|post.deploy` doesn't match `Post-deploy checklist`
(capital P, lowercase d). The warning fires even when a post-deploy phase exists.

**Fix applied:** Changed to `grep -qi 'post.deploy'`.

---

## Summary

| ID | Area | Status |
|----|------|--------|
| A1–A2 | `vk plan create` / `vk plan new` | ✅ Wrong binary — fixed by `install.sh` |
| B1–B2 | `vk plan self-review` | ✅ Wrong binary — fixed by `install.sh` |
| C1–C6 | `vk plan spec-index` | ✅ Wrong binary — `spec-index` removed in 2.1.4; `create` handles it |
| D1 | Hook layer extraction broken for `_prose.md` | ✅ Fixed in `plan-checklist-check.sh` |
| D2 | Hook Post-Deploy grep case-sensitive | ✅ Fixed in `plan-checklist-check.sh` |
| E1 | CLI version skew (`install.sh` not re-run) | ✅ Remediated; prevention gap open in vk |
