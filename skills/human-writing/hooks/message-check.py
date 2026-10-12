#!/usr/bin/env python3
"""PreToolUse hook: check.py over the prose a Bash command is about to publish.

Covers `gh pr create|edit|merge|comment`, `gh issue create|edit|comment`,
`gh release create|edit` and `git commit`: the text given with --body,
--body-file, --subject, --title, --notes, --notes-file, -m, -F and friends.
Exit 2 blocks the command and hands the findings back. Only hard findings
block, as in the Markdown hook. A command this cannot parse is let through.
"""

import json
import os
import shlex
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CHECK = os.path.join(HERE, "..", "scripts", "check.py")

# Flags whose value is the text itself, and flags whose value names a file.
GH_TEXT = {"--body", "-b", "--subject", "-t", "--title", "--notes", "-n"}
GH_FILE = {"--body-file", "-F", "--notes-file"}
GIT_TEXT = {"-m", "--message"}
GIT_FILE = {"-F", "--file"}
GH_TARGETS = {
    ("pr", "create"), ("pr", "edit"), ("pr", "merge"), ("pr", "comment"),
    ("issue", "create"), ("issue", "edit"), ("issue", "comment"),
    ("release", "create"), ("release", "edit"),
}


def segments(command):
    """Split a shell line into simple commands on &&, ||, ; and |."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|")
    lexer.whitespace_split = True
    current = []
    for token in lexer:
        if token and set(token) <= set(";&|"):
            if current:
                yield current
            current = []
        else:
            current.append(token)
    if current:
        yield current


def flag_values(args, flag_set):
    """Values of the flags in flag_set, as `--flag value` or `--flag=value`."""
    values = []
    i = 0
    while i < len(args):
        arg = args[i]
        name, eq, inline = arg.partition("=")
        if eq and name in flag_set:
            values.append(inline)
        elif arg in flag_set and i + 1 < len(args):
            values.append(args[i + 1])
            i += 1
        i += 1
    return values


def git_subcommand(args):
    """The git subcommand, skipping global options such as -C dir."""
    i = 1
    while i < len(args):
        if args[i] in ("-C", "-c", "--git-dir", "--work-tree"):
            i += 2
        elif args[i].startswith("-"):
            i += 1
        else:
            return args[i], args[i + 1:]
    return None, []


def texts_and_files(args):
    texts, files = [], []
    if not args:
        return texts, files
    tool = os.path.basename(args[0])
    if tool == "gh" and len(args) >= 3 and (args[1], args[2]) in GH_TARGETS:
        rest = args[3:]
        texts += flag_values(rest, GH_TEXT)
        files += flag_values(rest, GH_FILE)
    elif tool == "git":
        sub, rest = git_subcommand(args)
        if sub == "commit":
            texts += flag_values(rest, GIT_TEXT)
            files += flag_values(rest, GIT_FILE)
    return texts, files


def main():
    try:
        payload = json.load(sys.stdin)
        command = payload.get("tool_input", {}).get("command", "")
        cwd = payload.get("cwd") or os.getcwd()
        parsed = list(segments(command))
    except (ValueError, AttributeError):
        return 0
    texts, files = [], []
    for args in parsed:
        t, f = texts_and_files(args)
        texts += t
        files += f
    paths = []
    tmp = []
    for text in texts:
        handle = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
        handle.write(text)
        handle.close()
        tmp.append(handle.name)
        paths.append(handle.name)
    for name in files:
        if name == "-":
            continue
        path = name if os.path.isabs(name) else os.path.join(cwd, name)
        if os.path.isfile(path):
            paths.append(path)
    if not paths:
        return 0
    try:
        out = subprocess.run(
            [sys.executable, CHECK, *paths], capture_output=True, text=True, check=False
        ).stdout
    finally:
        for name in tmp:
            os.unlink(name)
    hard = [line for line in out.splitlines() if ": warning" not in line and "hard finding" not in line
            and "filler:" not in line and line.strip()]
    if not hard:
        return 0
    print("human-writing: fix these before publishing the text:", file=sys.stderr)
    for line in hard:
        for name in tmp:
            line = line.replace(name, "inline text")
        print(line, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
