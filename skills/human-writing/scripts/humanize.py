#!/usr/bin/env python3
"""Review prose in one pass: generated-voice tells, an AI-detector score and the names it cites.

    humanize.py <file-or-dir>... [--offline] [--json] [-v] [--repo DIR]

A directory is searched for .md, .mdx and .txt files, skipping .git, node_modules, vendor and build
output. For each file:

- Prose: check.py findings and tells per 100 words (hard findings, warnings and filler words).
- AI: the AI-detector score from ai-score.py, and with -v the spans it flagged. This sends the prose,
  code removed, to Grammarly. --offline skips it.
- Facts: file paths and code identifiers the prose names that do not occur anywhere in the code
  base, which is --repo or else the git root of the first file. Needs ripgrep.

The tells count and the AI score are reasons to read closely, never proof of who wrote a text. A
name that is not found is a lead: the prose may describe code by another name.

Exit status 1 when check.py has hard findings, 2 on usage errors, else 0.
"""

import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SUFFIXES = {".md", ".mdx", ".txt"}
SKIP_DIRS = {".git", "node_modules", "vendor", "target", "dist", "build", ".venv", "__pycache__", ".astro"}
EXT = r"(?:py|go|rs|ts|tsx|js|mjs|kt|java|rb|c|h|cc|cpp|php|cs|swift|toml|json|ya?ml|sh|sql|xml)"
# A file name with a code extension, optionally under directories. "read/write" is a word pair.
PATH = re.compile(r"(?<![\w/.])(?:\.{1,3}/)?(?:[\w.-]+/)*[\w-]+(?:\.[\w-]+)*\." + EXT + r"\b")
IDENT = re.compile(r"\b(?:[a-z][a-z0-9]*[A-Z]\w*|[A-Z][a-z0-9]+[A-Z]\w*|[a-z0-9]+_[a-z0-9_]*[a-z0-9])\b")
VOCAB = {"JavaScript", "TypeScript", "GitHub", "GitLab", "PostgreSQL", "MySQL", "OAuth", "macOS", "iOS",
         "WebSocket", "OpenAPI", "YouTube", "LinkedIn", "iPhone", "WebAssembly", "DevOps", "PhD"}


def load_checker():
    spec = importlib.util.spec_from_file_location("human_writing_check", HERE / "check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def find_files(target):
    path = Path(target)
    if path.is_file():
        return [path]
    found = []
    for root, dirs, files in os.walk(path):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        found += [Path(root) / f for f in sorted(files) if Path(f).suffix in SUFFIXES]
    return found


def prose_summary(checker, path):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        hard = checker.check(str(path), checker.strict_names())
    lines = out.getvalue().splitlines()
    findings = [l for l in lines if not re.search(r": \d+ words of prose, \d+ hard finding", l)]
    warnings = sum(": warning:" in l for l in findings)
    filler = sum(int(n) for l in findings if ": filler: " in l for n in re.findall(r" x(\d+)", l))
    words = int(re.search(r": (\d+) words of prose", lines[-1]).group(1))
    tells = hard + warnings + filler
    return {"path": str(path), "words": words, "hard": hard, "warnings": warnings, "filler": filler,
            "per100": round(100 * tells / words, 1) if words else 0.0,
            "findings": [l.replace(str(path), "").lstrip(":") for l in findings]}


def ai_scores(files):
    """Score every file in one ai-score.py run. A failed run is reported, not fatal."""
    if not shutil.which("uv"):
        return None, "uv is not installed"
    run = subprocess.run(["uv", "run", "--quiet", "--script", str(HERE / "ai-score.py"), *map(str, files)],
                         capture_output=True, text=True)
    scores = {r["path"]: r for r in map(json.loads, run.stdout.splitlines())}
    error = run.stderr.strip().splitlines()[-1] if run.returncode else None
    return scores, error


def code_root(files, repo):
    if repo:
        return Path(repo)
    top = subprocess.run(["git", "-C", str(files[0].resolve().parent), "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True)
    return Path(top.stdout.strip()) if top.returncode == 0 else None


def split_code(files, checker):
    """Prose with inline code kept, and the text of fenced code blocks, over all files."""
    prose, code = [], []
    for f in files:
        in_fence = False
        for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            if checker.FENCE.match(line.strip()):
                in_fence = not in_fence
            elif in_fence:
                code.append(line)
            else:
                prose.append(line)
    return "\n".join(prose), "\n".join(code)


def facts(files, root, checker):
    if root is None or not shutil.which("rg"):
        return None
    prose_paths = {str(f.resolve()) for f in files}
    text, own_code = split_code(files, checker)
    paths = {re.sub(r"^(?:\.{1,3}/)+", "", m.group()) for m in PATH.finditer(text)}
    listed = subprocess.run(["rg", "--files", "--hidden", "-g", "!.git", str(root)],
                            capture_output=True, text=True).stdout.splitlines()
    missing_paths = sorted(p for p in paths if not any(f.endswith("/" + p) for f in listed))

    idents = {m.group() for m in IDENT.finditer(text)} - VOCAB
    # Names the text defines in its own code blocks are not claims about the code base.
    idents = {i for i in idents if not any(i in p for p in paths) and not re.search(rf"\b{i}\b", own_code)}
    found = set()
    if idents:
        # rg -o prints the first pattern that matches at a position, so longer names go first.
        ordered = sorted(idents, key=lambda t: (-len(t), t))
        out = subprocess.run(["rg", "--only-matching", "--fixed-strings", "--hidden", "-g", "!.git",
                              "--with-filename", *[a for t in ordered for a in ("-e", t)], str(root)],
                             capture_output=True, text=True).stdout
        for line in out.splitlines():
            where, _, match = line.rpartition(":")
            # A name only the reviewed prose itself mentions does not count as found.
            if str(Path(where).resolve()) not in prose_paths:
                found.add(match)
    return {"root": str(root), "paths_checked": len(paths), "paths_not_found": missing_paths,
            "identifiers_checked": len(idents), "identifiers_not_found": sorted(idents - found)}


def main(argv):
    flags, targets, repo = set(), [], None
    args = iter(argv)
    for a in args:
        if a == "--repo":
            repo = next(args, None)
        elif a.startswith("-"):
            flags.add(a)
        else:
            targets.append(a)
    if not targets:
        print(__doc__.strip())
        return 2
    files = [f for t in targets for f in find_files(t)]
    if not files:
        print("no .md, .mdx or .txt files found", file=sys.stderr)
        return 2

    checker = load_checker()
    prose = [prose_summary(checker, f) for f in files]
    scores, ai_error = ({}, "skipped (--offline)") if "--offline" in flags else ai_scores(files)
    fact = facts(files, code_root(files, repo), checker)
    status = 1 if any(p["hard"] for p in prose) else 0

    if "--json" in flags:
        print(json.dumps({"prose": prose, "ai": scores or None, "ai_error": ai_error, "facts": fact}, indent=2))
        return status

    ai_on = bool(scores)
    print(f"{'tells/100w':>10} {'words':>6} {'hard':>5} {'warn':>5} {'filler':>6}{' ai%' if ai_on else ''}  file")
    for p in prose:
        ai = ""
        if ai_on:
            s = scores.get(p["path"], {}).get("score")
            ai = f" {'-' if s is None else s:>3}"
        print(f"{p['per100']:>10.1f} {p['words']:>6} {p['hard']:>5} {p['warnings']:>5} {p['filler']:>6}{ai}  {p['path']}")
        if "-v" in flags:
            for finding in p["findings"]:
                print(f"{'':>12}{finding}")
            for span in scores.get(p["path"], {}).get("ranges", []) if ai_on else []:
                t = " ".join(span["text"].split())
                print(f"{'':>12}ai {span['score']}%: {t[:100]}{'...' if len(t) > 100 else ''}")
    if ai_error:
        print(f"\nai score: {ai_error}")
    if fact:
        print(f"\nnames checked against {fact['root']}:")
        print(f"  paths: {fact['paths_checked']}, not found: {', '.join(fact['paths_not_found']) or 'none'}")
        print(f"  identifiers: {fact['identifiers_checked']}, not found: {', '.join(fact['identifiers_not_found']) or 'none'}")
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
