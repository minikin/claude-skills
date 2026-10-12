---
name: human-writing
description: >
  Writes and reviews technical prose so it reads as written by an engineer, not generated.
  Carries the typography rules, the generated-voice tells with prefer-over rewrites, and a
  mechanical checker in scripts/check.py. Use this skill when: (1) drafting or editing a
  README, design doc, report, PR description or any Markdown meant for other people,
  (2) reviewing prose for machine-written tells, (3) a reader said a text sounds like AI.
license: MIT
metadata:
  version: "1.0.0"
---

# Human writing

Write like a senior engineer writing for other engineers. Plain technical language, short and
medium sentences, fragments where they read naturally. Say which option is better when one is.
State the fact, not a run-up to it: "7.9 minutes, 27 steps. Fixed the lease origin." rather than
"The 7.9-minute, 27-step run fixed the lease origin."

Run the checker first and last:

    python3 <this skill's directory>/scripts/check.py <file>...

It exits 1 on em dashes, curly quotes and ellipsis characters, warns on semicolons, exclamation
marks, slash pairs and the openers below, counts filler words and prints the word count. It skips
frontmatter, fenced code and inline code. It cannot see symmetry or a restated conclusion, so the
read-through at the end is still the review. The plugin's hook runs it after every Markdown write
and hands back only the hard findings. A second hook runs it before `git commit` and before `gh pr`,
`gh issue` and `gh release` commands that publish text, on each message, body or notes file, and
blocks the command on a hard finding.

## Typography

- Never an em dash (U+2014). Colon when the second half explains the first, comma when it is an
  aside, two sentences when it is neither. Do not swap every one for the same replacement.
- ASCII quotes only. No curly quotes, no ellipsis character, no exclamation marks.
- Avoid semicolons. Two sentences, a comma, or a colon. A semicolon stays when the content needs
  it: code, a quoted source, a list whose items carry their own commas.
- No `simple/effective` slash pairs. No invented abbreviations in parentheses.

## Prose that reads as generated

- No restating the question before answering it, no generic introduction or conclusion, no "In
  summary", no offer of more help, no reference to yourself as a model or assistant.
- No empty transitions: "It's worth noting", "Notably", "Certainly", "First, ... Additionally, ...
  Furthermore, ... Finally".
- No significance language when the fact already shows it: "an important detail", "a subtle
  issue", "the key insight", "crucially".
- No writing about the writing: "this gives a complete picture", "this demonstrates that".
- No causal connectors where adjacent sentences already carry the cause: "therefore", "this
  means", "this ensures", "which allows".
- No explaining the same thing twice in adjacent sections. A document describes the thing as it
  is, present tense, not its development history.
- Bullets in a list need not share a grammar. Not every idea is a list. No heading over one or two
  sentences.

Filler words are not forbidden when technically exact, never as filler: robust, seamless,
comprehensive, holistic, powerful, flexible, scalable, streamlined, leverage, utilize, empower,
unlock, facilitate, enhance, ensure, crucial, pivotal, noteworthy, valuable, significant, key,
effectively, efficiently.

## Over-justification and meta narration

Once the facts establish a conclusion, stop. Not every paragraph ends with its own summary, not
every example is followed by a lesson.

Prefer "`verify_migrations` rejects the divergent migration before anything runs, so the
duplicate-version fix alone does not unblock the deploy." and nothing after it. Not "This means
that both issues must be addressed for the system to return to a consistent and deployable state."

Do not narrate the reasoning: "There are two things to understand", "The first thing to notice
is", "This is where things get complicated". State the distinction.

Prefer "V7 is absent rather than recorded with the wrong checksum." over "The key insight is that
V7 represents a different class of problem: it is absent rather than mismatched."

Answer a claim of importance, realism or difficulty with the facts that make it so, never with
"This is important because" or "The obvious approach is wrong".

## Symmetry and punchlines

Do not force pairs, triads or mirrored paragraphs: one side / the other side, first / second /
finally, problem / solution, before / after. Technical writing is uneven because the facts are.

Do not manufacture short dramatic sentences: "The data looks complete. It isn't", "The fix is
small. The consequences are not". Prefer "Updating every checksum mismatch would replace V6 and
would still miss V7."

## Concrete subjects, active verbs, named mechanisms

Name the function, migration, release, test, operator or tool that acts.

Prefer "`verify_migrations` rejects the changed migration before anything runs." over "The changed
migration is rejected prior to execution."

Prefer "The test checks that distinct versions still run in order." over "The test provides
verification of the preservation of ordering behavior for distinct versions."

Prefer "`Migration::unapplied` hashes the version, name and SQL body, so a formatting-only change
changes the stored checksum." over "Formatting changes can affect migration consistency due to how
checksums are calculated."

Passive voice is fine when the actor is unknown or irrelevant. Nominalisations ("the validation
of", "the handling of") almost never are.

## The read-through

After the checker passes, read once for:

- a conclusion explained, then explained again in more abstract words
- mirrored paragraph shapes and forced pairs
- a rhetorical punchline
- a passive that hides a useful subject, a nominalisation where a verb would do
- a sentence about importance or completeness in place of the fact
- a paragraph that ends by restating itself
- a fact stated in two adjacent sections

Do not shorten a file merely to look less generated. Keep the exact values, names and evidence.
The goal is dense technical writing with no filler. Cutting repetition is most of the technique.

## Per-project settings

`.claude/human-writing.json` at a project root, every key optional:

```json
{ "hook": true, "strict": ["comments.md"], "exclude": ["docs/vendor/*", "third_party/*"] }
```

`hook: false` turns the hook off for a project that runs its own checker. `strict` lists basenames
where a semicolon is a hard finding. `exclude` takes shell globs relative to the project root.
