# AI-tells catalog — patterns that make prose read machine-written

Adapted from [@blader's humanizer skill](https://github.com/blader/humanizer)
and Wikipedia's WikiProject AI Cleanup
["Signs of AI writing"](https://en.wikipedia.org/wiki/Wikipedia:WikiProject_AI_Cleanup/Signs_of_AI_writing).

Each family below has a one-line description, a bad → good example pair, and
the fix rule. Apply this catalog as a **mandatory self-revision pass** on every
draft: read the draft once looking only for these patterns, and rewrite each
hit. The validator's lint layer derives its word lists and thresholds from the
machine-readable block at the bottom of this file — the prose and the mechanics
share one source and cannot drift apart.

## AI vocabulary

Words and stock phrases that LLMs reach for far more often than working
engineers do; each one is a fingerprint.

- Bad: "Let's delve into the ever-evolving realm of container networking."
- Good: "Container networking has three moving parts; here's the one that bit us."
- Fix: replace each flagged word with the plain word a colleague would say out
  loud — dig into, changing, area — or delete the sentence if it says nothing.

## Rule of three (triads)

Grouping everything into rhythmic three-item lists ("fast, simple, and
reliable") regardless of whether the content has three parts.

- Bad: "The migration was quick, painless, and effective."
- Good: "The migration took twenty minutes and nothing broke."
- Fix: count the real items. If there are two, write two; if the list is
  decorative, replace it with the one concrete fact you actually have.

## Negative parallelisms

The "not X, but Y" / "it isn't about X, it's about Y" seesaw — asserting by
first denying a strawman.

- Bad: "This isn't about saving disk space, it's about protecting your data."
- Good: "Snapshots protect your data; the disk savings are incidental."
- Fix: state the positive claim directly. If the contrast genuinely matters,
  give the reader the evidence for it instead of the rhetorical shape.

## Em-dash overuse

Em dashes stitching together clauses that wanted a period, a comma, or a
rewrite — several per paragraph is a tell.

- Bad: "The cache was stale — not corrupted — which meant the fix — clearing it — was safe."
- Good: "The cache was stale rather than corrupted, so clearing it was safe."
- Fix: keep an em dash only where a deliberate interruption earns it; convert
  the rest to periods or commas.

## Inflated symbolism

Framing routine work as emblematic: "a testament to," "underscores the
importance of," "marks a pivotal moment."

- Bad: "This bugfix is a testament to the power of systematic debugging."
- Good: "Bisecting the config found the bad key in four steps."
- Fix: delete the symbolism and report what happened. Significance the reader
  can't derive from the facts wasn't there.

## Promotional language

Marketing adjectives welded onto technical nouns: seamless integration,
game-changing performance, supercharged workflow.

- Bad: "The seamless integration supercharges your deployment workflow."
- Good: "Deploys now run in CI; nobody SSHes into the box anymore."
- Fix: replace every claim of quality with the measurement or behavior change
  that would justify it.

## Superficial "-ing" analyses

Trailing participial clauses that fake analysis: "..., highlighting the
importance of testing," "..., showcasing the framework's flexibility."

- Bad: "The service crashed under load, highlighting the importance of monitoring."
- Good: "The service crashed under load. We had no alert on file descriptors; now we do."
- Fix: cut the participial clause and, if the point matters, give it its own
  sentence with its own evidence.

## Vague attributions

Ghost authorities: "industry experts say," "many developers believe," "it is
widely considered."

- Bad: "Many experts consider connection pooling a best practice."
- Good: "Postgres caps connections at 100 by default; without pooling we hit it in a week."
- Fix: name the source or own the claim yourself. If neither is possible, the
  claim doesn't belong in the post.

## Conjunctive-phrase excess

Furthermore/Moreover/Additionally chains gluing paragraphs together instead of
actual logical flow.

- Bad: "Furthermore, the API is versioned. Moreover, it supports pagination. Additionally, it returns JSON."
- Good: "The API is versioned, paginated, and returns JSON — table stakes; the interesting part is the cursor design."
- Fix: delete the connective and check whether the paragraphs still follow. If
  they don't, the problem is the ordering, not the missing glue word.

## Cliché conclusions

Endings that open with "In conclusion" / "Ultimately" / "At the end of the
day" and then recap what the post already said.

- Bad: "In conclusion, we learned that monitoring, testing, and documentation are essential."
- Good: "The portable rule: alert on the resource you'll exhaust first, not the one that's easy to graph."
- Fix: end with what transfers — the general rule or heuristic the reader
  keeps — not a summary of the journey.

## Machine-readable lint data

The validator (`tools/validate_educational.py::load_lint_data`) parses this
block. Edit the lists here; never in the tool.

```yaml
vocabulary:
  - delve
  - delves
  - delving
  - delved
  - tapestry
  - a testament to
  - seamless
  - seamlessly
  - game-changer
  - game-changing
  - ever-evolving
  - in today's fast-paced
  - treasure trove
  - supercharge
  - supercharges
  - supercharged
  - supercharging
  - revolutionize
  - revolutionizes
  - revolutionized
  - revolutionizing
  - harness the power
  - embark
  - embarks
  - embarked
  - embarking
  - realm
  - myriad
  - plethora
  - boasts
  - boasting
  - boasted
conclusion_openers:
  - in conclusion
  - ultimately
  - in the end
  - at the end of the day
  - all in all
  - in summary
patterns:
  negative_parallelism: "\\bnot (?:just |only |merely |simply )?[^.;:]{3,40}[,;] but\\b|\\bisn'?t about [^.;:]{3,40}[,;.] it'?s about\\b"
  triad: "\\b\\w+, \\w+, and \\w+\\b"
thresholds:
  em_dash_per_1000: 8
  negative_parallelisms_per_1000: 2
  triads_per_1000: 3
transfer_headings:
  - what transfers
  - what you keep
  - takeaway
  - takeaways
```

Deliberately **excluded** from the fail list because they have legitimate
technical uses: *underscore* (the character), *landscape* (this methodology's
own term), *deep dive* (the repo's explainer vocabulary), *robust* / *crucial*
/ *leverage* (common legit tech usage).
