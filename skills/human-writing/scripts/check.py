#!/usr/bin/env python3
"""Mechanical pass over Markdown prose for the tells that read as generated.

    check.py <file>...

Exit 1 on typography that marks text as machine-written: em dashes, curly
quotes, ellipsis characters. Everything else is a warning. Fenced code blocks
and inline code are skipped, so paths and commands do not count as slash
pairs or filler.

A project can promote the semicolon to a hard finding for some files by
listing their basenames under "strict" in .claude/human-writing.json at the
project root.
"""

import json
import os
import re
import sys

HARD = {
    "—": "em dash",
    "“": "curly quote",
    "”": "curly quote",
    "‘": "curly quote",
    "’": "curly quote",
    "…": "ellipsis character",
}
OPENERS = re.compile(
    r"(?:(?<=^)|(?<=[.!?]\s))(Certainly|Absolutely|Great question|Notably|In summary|To summarize|"
    r"It(?:'s| is) (?:worth noting|important to note)|First,|Additionally,|Furthermore,|Moreover,|"
    r"Finally,|Therefore,|Thus,|Hence,|Consequently,|As a result,|This means|This ensures|"
    r"This allows|This guarantees|This demonstrates|The key insight|The important (?:part|distinction|"
    r"thing)|The crucial|An important detail|A subtle issue|The reason (?:is simple|this matters))\b",
    re.MULTILINE,
)
FILLER = re.compile(
    r"\b(robust|seamless|comprehensive|holistic|powerful|flexible|scalable|streamlined|leverages?|"
    r"utilizes?|empowers?|unlocks?|facilitates?|enhances?|ensures?|crucial|pivotal|noteworthy|"
    r"valuable|significant|effectively|efficiently)\b",
    re.IGNORECASE,
)
ADJ = r"(?:simple|clean|robust|readable|maintainable|fast|effective|reliable|safe|correct|secure|efficient|elegant|clear|concise)"
SLASH_PAIR = re.compile(rf"\b{ADJ}/{ADJ}\b")
# What AI-text detectors flagged in reviewed comments (2026-10-12): a colon opening a long inventory,
# a chain of "no X" negatives, and a closing verdict sentence.
SENTENCE = re.compile(r"[^.!?]+[.!?]?")
NEGATIVE = re.compile(r"\b(no|nothing|none|neither|nor|never)\b", re.IGNORECASE)
VERDICT = re.compile(r"^\s*(Neither|None of (?:these|them|the \w+))\b.*\b(defect|problem|issue|concern)\b", re.IGNORECASE)
FENCE = re.compile(r"^(```|~~~)")
INLINE_CODE = re.compile(r"`[^`\n]*`")
ENTITY = re.compile(r"&#?\w+;")
# Leading blank lines are allowed: Astro and other static-site loaders accept them before the fence.
FRONTMATTER = re.compile(r"\A\s*---\n.*?\n---\n", re.DOTALL)


def strict_names():
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    try:
        with open(os.path.join(root, ".claude", "human-writing.json"), encoding="utf-8") as f:
            return set(json.load(f).get("strict", []))
    except (OSError, ValueError, AttributeError):
        return set()


def prose_lines(text):
    # Frontmatter is metadata, but its lines still count toward the numbering.
    m = FRONTMATTER.match(text)
    skip = m.group().count("\n") if m else 0
    in_fence = False
    for number, line in enumerate(text.splitlines(), 1):
        if number <= skip:
            continue
        if FENCE.match(line.strip()):
            in_fence = not in_fence
            continue
        if not in_fence:
            yield number, INLINE_CODE.sub("", line)


def check(path, strict):
    text = open(path, encoding="utf-8").read()
    lines = list(prose_lines(text))
    prose = "\n".join(line for _, line in lines)
    hard = 0
    strict_file = os.path.basename(path) in strict
    for number, line in lines:
        for char, name in HARD.items():
            if char in line:
                print(f"{path}:{number}: {name}")
                hard += 1
        # A quoted source keeps its own punctuation.
        if ";" in ENTITY.sub("", line) and not line.lstrip().startswith(">"):
            if strict_file:
                print(f"{path}:{number}: semicolon")
                hard += 1
            else:
                print(f"{path}:{number}: warning: semicolon")
        if "!" in re.sub(r"!\[", "", line) and not line.lstrip().startswith(("!", "<!--")):
            print(f"{path}:{number}: warning: exclamation mark")
        for m in SLASH_PAIR.finditer(line):
            print(f"{path}:{number}: warning: slash pair '{m.group()}'")
    for m in OPENERS.finditer(prose):
        number = prose.count("\n", 0, m.start()) + 1
        print(f"{path}:{lines[number - 1][0]}: warning: opener '{m.group()}'")
    for m in SENTENCE.finditer(prose):
        sentence = m.group()
        start = m.start() + len(sentence) - len(sentence.lstrip())
        number = lines[prose.count("\n", 0, start)][0]
        head, colon, tail = sentence.partition(":")
        # A Markdown list after the colon is a list, not an inventory sentence.
        if colon and tail.count(",") >= 4 and not re.search(r"\n\s*(?:[-*]|\d+\.)\s", tail):
            print(f"{path}:{number}: warning: inventory after a colon ({tail.count(',') + 1} items)")
        if len(NEGATIVE.findall(sentence)) >= 3:
            print(f"{path}:{number}: warning: chain of negatives")
        if VERDICT.match(sentence):
            print(f"{path}:{number}: warning: verdict sentence '{sentence.strip()[:60]}'")
    fillers = {}
    for m in FILLER.finditer(prose):
        fillers[m.group().lower()] = fillers.get(m.group().lower(), 0) + 1
    if fillers:
        print(f"{path}: filler: " + ", ".join(f"{w} x{n}" for w, n in sorted(fillers.items())))
    words = len(re.findall(r"\b\w+\b", prose))
    print(f"{path}: {words} words of prose, {hard} hard finding(s)")
    return hard


def main(paths):
    if not paths:
        print(__doc__.strip())
        return 2
    strict = strict_names()
    return 1 if sum(check(p, strict) for p in paths) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
