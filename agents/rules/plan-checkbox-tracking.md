## Plan Checkbox Tracking

When executing plans (via `subagent-driven-development`, `executing-plans`, or manually), update the plan file's checkboxes as you go:

- After completing each step, edit the plan `.md` file to change `- [ ]` to `- [x]` for that step
- Do this in the controller/coordinator, not inside subagents (subagents don't know the plan file path)
- Do this immediately after marking a task complete in TodoWrite — don't batch checkbox updates
- If a step is skipped intentionally, change `- [ ]` to `- [-]` and add a parenthetical reason (e.g., `*(skipped — already deployed)*`)

The `writing-plans` skill creates checkboxes (`- [ ]`). The execution skills must consume them. TodoWrite is ephemeral and does not survive session end — the plan file is the persistent record.
