# Multi-Agent Discussion Pattern

A reusable pattern for collaborative cascades where 2+ agents work concurrently on a shared operation (canary observations, postmortems, complex audits) with the operator acting as broker.

Worked example: `docs/agentic-discussion/2026-05-04--litellm-canary-for-real/` — three agents cooperated through the PR #210 canary cascade. The patterns below were extracted from what worked (and what didn't) during that session.

## When to use

Use this pattern when:
- A task benefits from **structurally different vantage points** (controller-watcher + data-plane-observer + load-driver, or narrative-writer + fact-checker + diagrammer)
- The operation is long enough (>15 min) that real-time coordination matters
- Findings need to be **artifact-captured** for a postmortem or documentation deliverable

Do *not* use this pattern when:
- The task is single-agent in nature
- The operation is short enough that one agent can hold full context
- High-velocity decisions are needed (the file-based protocol is async by design)

## Folder layout

Each cascade gets a dated folder:

```
docs/agentic-discussion/
├── 2026-05-04--litellm-canary/             ← prior cascade (rehearsal)
└── 2026-05-04--litellm-canary-for-real/    ← current cascade
    ├── 00-context.md          # operator-set context, lane assignments, vocabulary
    ├── 00-INBOX.md            # optional: structured inter-agent pings
    ├── terminal-1.md          # T1 (coordinator) — append-only
    ├── terminal-2.md          # T2 (specialist role) — append-only
    └── terminal-3.md          # T3 (specialist role) — append-only
```

Per-cascade folders mean each conversation is self-contained and history-preserving. Don't reuse old folders.

## File conventions

- `00-context.md` — Written **once** by T1 at session start. Other agents reference but do not mutate. T1 may append a synthesis section at the very end of the cascade.
- `terminal-N.md` — Append-only. Each new entry has a timestamped header. Free-form within the entry.
- `00-INBOX.md` — Append-only. Structured ping schema (see Communication Channel below).

## Bootstrap prompts

Copy-paste these into each agent's session at start. Replace placeholders.

### Operator → T1 (coordinator boot)

```
You are T1 (coordinator) for cascade `<cascade-name>`.

Goal: <one-sentence: what's about to happen and why>
(e.g., "land PR #N which bumps X and renames Y; capture canary
observation evidence for postmortem")

Read:
- Pattern: docs/patterns/multi-agent-discussion.md
- Runbook: docs/runbooks/<relevant>.md
- Prior cascade (if any): docs/agentic-discussion/<prev-folder>/

Then:
1. Take a cluster-state snapshot relevant to this cascade
2. Write docs/agentic-discussion/<cascade-name>/00-context.md per the
   template in the pattern doc
3. Propose lane assignments (which agents needed, what each does)
4. Stop and wait for me to spawn the subordinate agents
```

### Operator → T<N> (subordinate boot)

```
You are T<N> for cascade `<cascade-name>`. Your lane: <one-sentence>.

Read:
- docs/agentic-discussion/<cascade-name>/00-context.md
- docs/agentic-discussion/<cascade-name>/terminal-1.md
- Pattern: docs/patterns/multi-agent-discussion.md

Write to: docs/agentic-discussion/<cascade-name>/terminal-<N>.md
(append-only).

Engagement: I'll ping you when other agents post substantive content
or when there's a decision point. Stand down with a clear footer when
your role completes.
```

### Operator → T1 (cascade-end synthesis)

```
Cascade is winding down. Read all terminal-*.md files in
docs/agentic-discussion/<cascade-name>/. Append a synthesis section
to 00-context.md covering:
- What happened (timeline)
- What each agent contributed
- Disagreements and how they resolved
- What to fold into the runbook / postmortem
- Channel digest (see pattern doc)

Then stand down.
```

## 00-context.md template

```markdown
# Cascade: <cascade-name>

## What this cascade is
<1-3 sentences: the operation, the goal, what's about to happen>

## Cluster state at session start
<relevant snapshot — pods, RSes, versions, PVC sizes, anything
context-bearing for what's about to change>

## Lane assignments
- T1 (coordinator): <role + primary tools/focus>
- T2 (<role>): <role + primary tools/focus>
- T3 (<role>): <role + primary tools/focus>

## Carryforward from prior cascade
<bullet list: what was decided, what lessons were learned, what's
being applied here. Link to prior cascade folder.>

## Vocabulary
<terms that emerged in prior cascades or are local to this domain.
Lets agents use shorthand without re-deriving. e.g.:
- "Path A / Path B" — the post-rehearsal direction split
- "synthetic-trigger PR" — env-var bump to fire a no-op canary
- "the 6-pod transient" — maxSurge mid-state at SetWeight 50>

## See also
- runbook: <link>
- prior cascade: <link>
- postmortem (if/when): <link>

---

## Synthesis (appended by T1 at cascade end)
<filled in only when the cascade wraps up>
```

## terminal-N.md conventions

Each entry uses this shape:

```markdown
## YYYY-MM-DD ~HH:MM — <short title>

<free-form content. Tables, code blocks, lists welcome.>

### Replies to other agents (when applicable)

> @T1: <quoted point you're responding to>

<your response>
```

End-of-cascade footer:

```markdown
---

**Stood down at HH:MM.** Available for: <list of follow-ups you'd
take if pinged again, or "no further role">.
```

The quoted-reply (`> @T<N>:`) convention does threading without UI. When reading top-to-bottom, the response is right next to what it's responding to.

## Communication channel — `00-INBOX.md`

Optional inter-agent channel for direct coordination without operator round-trip. The channel is for **coordination, not collaboration** — brainstorming happens in each agent's terminal-N.md (free-form); only structured outputs travel through the inbox.

### Ping schema

Every entry follows this exact structure:

```
## HH:MM from=T<N> to=T<M> ack=required|optional|none tag=<short-tag>
<subject line — one sentence>

<body — 2-5 lines max>
```

The fields do real work:

| Field | Purpose |
|---|---|
| `from=` | Sender. Required for accountability. |
| `to=` | **Single addressee or `operator`.** Only the named target is expected to act. Others can read but don't engage unless explicitly tagged. |
| `ack=required` | Recipient MUST respond by the next turn — even with "ack, no, here's why" or "escalating to operator." Prevents pings going to the void. |
| `ack=optional` | Recipient may respond if value-add. |
| `ack=none` | Informational, closing a thread, no response expected. |
| `tag=` | Short topic tag. Threads share a tag. |

### Guardrails

These are mutually-reinforcing. Don't drop one without thinking about which failure mode comes back.

#### 1. Bounded thread depth

After **3 round-trips** on the same `tag`, the next message must either:
- Close with a decision (`ack=none`), or
- Escalate to operator (`to=operator`)

Single biggest guard against feedback loops. Agreeable LLMs will keep replying indefinitely if you let them. Hard cap forces convergence.

#### 2. Per-agent ping budget

Each agent has a budget per cascade (suggested defaults):
- T1 (coordinator): 10 outbound pings
- T2/T3+ (specialists): 5 outbound pings each

Forces prioritization. If you'd ping for every observation, you'll burn budget on low-value traffic and have nothing left for real signals.

#### 3. Cooldown between same-pair pings

After A pings B, A can't ping B again on the same `tag` until B has acked. Prevents one-sided spam during a busy moment.

#### 4. Topic-separated inboxes (when natural)

For cascades with multiple parallel concerns, split the inbox:

```
00-INBOX-coordination.md   # rollout phase, promotes, decisions
00-INBOX-observation.md    # cluster state, anomalies
00-INBOX-decisions.md      # operator-required calls
```

Bulkheads. Feedback loop in one topic doesn't drown out unrelated traffic.

#### 5. Operator-readable digest at cascade end

T1's wrap-up synthesis includes a "channel digest":

| Time | from→to | tag | subject | resolution | time-to-ack |
|---|---|---|---|---|---|
| 18:22 | T3→T1 | routing-strategy | dual-probe vs single? | switched to single after ERR thrash | 4 min |

Auditable. Bad channels get spotted; you tune the budget/depth caps based on real data.

### Anti-patterns

- **No "I notice X" broadcasts.** A ping without a clear single addressee invites "anyone want to engage?" which agreeable LLMs always will. Either you have a target or you don't ping.
- **No reply-to-reply expansion.** "Building on that..." in LLMs becomes runaway. A reply must close the open question or open a new tagged thread.
- **No agent-initiated meta-pings.** "Should we discuss X?" → just do it or don't. Meta-pings double channel volume without producing decisions.
- **No cross-tag references in ack-required pings.** If you need to discuss two things, send two pings.

## Disagreement protocol

LLMs default to agreement. The protocol counter-pressures that:

- **Pushback must include what would change your mind.** Not "I disagree because Y" but "I disagree because Y; if Z were true I'd accept your position."
- **Corrections must be explicit.** Not "great point, building on that" — "I was wrong about X, you were right because Y." This is a *capability*, not a personality trait. Naming it makes it usable.
- **The synthesis section calls out unresolved disagreements** as such. Not every disagreement converges; some are correctly preserved as open questions for the operator.

## Stand-down protocol

When an agent's role completes:

1. Append a final entry to terminal-N.md.
2. End with the footer:

   ```
   **Stood down at HH:MM.** Available for: <list>.
   ```

3. Stop responding to non-explicit re-tags.

If the operator wants the agent active again, they explicitly re-spawn or send a new prompt referencing the cascade. This prevents zombie wake-ups where a long-tail event triggers an agent who thought they were done.

## Cascade lifecycle

```
1. Operator decides to run a cascade
   └─→ "I'm about to land PR #N" / "I want to investigate X"

2. Operator boots T1
   └─→ T1 reads pattern + runbook + prior cascade
   └─→ T1 takes cluster-state snapshot
   └─→ T1 writes 00-context.md, proposes lanes
   └─→ T1 stops, awaits operator

3. Operator reviews 00-context.md, approves/edits lanes
   └─→ Operator boots T2, T3, ... with subordinate prompts

4. Cascade runs
   └─→ Each agent writes their terminal-N.md
   └─→ Operator brokers (signals "X posted," makes decisions)
   └─→ 00-INBOX.md (optional) carries structured pings if used

5. Operation completes / cascade winds down
   └─→ Each agent stands down (final entry + footer)
   └─→ Operator asks T1 for synthesis

6. T1 synthesis appended to 00-context.md
   └─→ Channel digest table
   └─→ What to fold into runbook / postmortem
   └─→ Open questions preserved as such

7. Folder is read-only artifact for postmortem reference
```

## Operator's role — load-bearing

The single biggest leverage in this pattern is the operator's editorial judgment about **when to broker**. They don't tell agents to read each other until both have written substantive content. They don't ask agents to engage with every point. They pick moments.

This is *not* automatable cheaply. Direct agent-to-agent brokerage tends toward deadlock or runaway-agreement. The pattern explicitly accepts the operator-as-keystone and is designed around supporting *their* attention:

- 00-context.md cuts redundant restatement
- Bootstrap prompts cut briefing time
- Stand-down footers cut "is this agent done?" guessing
- Channel digest cuts post-cascade audit time

If you find yourself fighting the operator-as-broker architecture, you're probably solving the wrong problem.

## Trade-offs

- **Coordination overhead.** This pattern has real setup cost. Don't use it for tasks one agent can handle.
- **Async by design.** File-based discussion is slower than synchronous chat. Tasks needing rapid coordination want a different shape.
- **Operator attention.** This pattern shifts work *to* the operator (brokering, deciding) compared to a single-agent pattern. The trade is depth of artifact + diversity of perspective for breadth of operator attention.

## Cost-aware role assignment

Some lanes are LLM-shaped (synthesis, correlation, narrative observation, judgment under uncertainty). Some are not (driving 1 req/sec, polling endpoints, log-tailing).

When designing lanes, recognize:
- **LLM-essential**: lanes that require interpretation, narrative, cross-correlation, judgment
- **Automation candidates**: lanes that are deterministic loops with structured signal/alarm rules

A "traffic driver" lane is the canonical automation candidate — most of the work is `while true; curl ...; sleep 1; done` plus a 5xx-detector. The agent's narrative-observer half is the high-value LLM piece. Future cascades may split such lanes into a Tekton task (with a Telegram webhook for alarms) plus a thin agent slot for interpretation.

This isn't required by the pattern, but it's worth noting when assigning lanes — match the cognitive shape of the work to the cost of the slot.
