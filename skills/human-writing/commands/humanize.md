---
description: Review prose in one pass, generated-voice tells, an AI-detector score and the code names it cites, with an optional Opus claim check
argument-hint: <file-or-dir>... [--offline] [--repo DIR] [--full]
---

Load the human-writing skill first. Its base directory holds `scripts/humanize.py`, `scripts/check.py`,
`scripts/ai-score.py` and `references/fact-check.md`. `HW` below is that directory.

1. Run `python3 HW/scripts/humanize.py $ARGUMENTS -v` without `--full`, which is this command's own
   flag. The AI score is on by default and sends the prose, code removed, to Grammarly. In auto mode
   the permission classifier may block it: say so and rerun with `--offline` rather than working
   around the block. Exit status 1 only means hard findings, the report is still good.
2. Show the table. For each file with hard findings, list them with their lines. Fact leads matter
   when the prose describes its own code base (a README, design doc, PR text or task reasoning). For
   a blog post or essay they mostly list outside APIs, so mention them only if one looks wrong.
3. With `--full`, rerun with `--offline --json`, fill `HW/references/fact-check.md` below its `---`
   line (`{FILES}`, `{ROOT}` from `facts.root`, `{SCRIPT_FACTS}` the `facts` object, `{OUT}` a
   `humanize-review.md` beside the first file unless the user names a place, `{DATE}` today) and hand it
   to one Agent with `model: "opus"`, in the background. When it returns, report each wrong claim.

The tells count and the AI score are reasons to read closely, never proof of who wrote a text. Do
not rewrite the files unless the user asks. Rewriting for clarity follows the human-writing skill.
