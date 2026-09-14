# Paperclip LiteLLM-backed agents — finish #382

Spec: `docs/superpowers/specs/2026-09-13--orch--paperclip-litellm-agents-docs-design.md`

## Shape

This is a docs-only layer extension. There are four phases:

1. **Walking skeleton:** the blog gate suite (educational validator, actionable-sections tripwire, Hugo build) runs against the two posts on the PR branch.
2. **Content:** fold #382's two appended sections into the house structure, with every claim re-verified against the live cluster. This phase was **executed inline** by the fr-goal orchestrator before the plan was written, because the facts had to be established during the brainstorm to frame the operator Q&A. It is recorded here as complete rather than re-dispatched.
3. **CI:** wait for #787 to merge (it carries the fixes for the 5 pre-existing over-budget mermaid diagrams), rebase, and reach green checks. Operator decision d2: no mermaid changes in this PR.
4. **Manual:** the post-merge rendered-page check (the Test Plan). The acceptance row `paperclip-litellm-agents-operable` already exists (appended via a round-trip around super-fr#470). This phase appends the live-check date to its notes; its status stays `skipped`.

## Why no code tests

Nothing executable changes. The "red" in each content task is the live-cluster diff or the lint output that shows a wrong or missing claim. The "green" is the edit. The refactor step re-runs the gates and the commands the post publishes.
