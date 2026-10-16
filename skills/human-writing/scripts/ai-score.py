#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright==1.53.0"]
# ///
"""Score prose with Grammarly's AI detector, one JSON line per file.

    grammarly-score.py <file>...

Each file's prose, with fenced and inline code removed the way check.py removes it, goes through
the public detector page at grammarly.com/ai-detector in headless Chrome. The text leaves the
machine. Output per file:

    {"path": ..., "chars": ..., "score": 0-100 or null, "ranges": [{"begin", "end", "score", "text"}]}

score is the detector's AI-Detector score for the whole text, ranges are the spans it flagged.
score is null when the page refuses the text: too short, or over 25,000 characters.
humanize.py runs this for its ai% column.
"""

import importlib.util
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

PAGE = "https://www.grammarly.com/ai-detector"
MAX_CHARS = 25_000
CHECKER = Path(__file__).resolve().parent / "check.py"


def load_checker():
    spec = importlib.util.spec_from_file_location("human_writing_check", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prose(checker, path):
    text = Path(path).read_text(encoding="utf-8")
    return "\n".join(line for _, line in checker.prose_lines(text)).strip()


def score(browser, text):
    # A signed-out page scans once and then drops the button, so each text gets a fresh context.
    context = browser.new_context(viewport={"width": 1400, "height": 900})
    try:
        page = context.new_page()
        page.goto(PAGE, wait_until="domcontentloaded")
        editor = page.locator("textarea").first
        editor.wait_for(timeout=30_000)
        editor.fill(text)
        page.wait_for_timeout(500)
        return scan(page, text)
    finally:
        context.close()


def scan(page, text):
    button = page.get_by_role("button", name="Scan for AI")
    if not button.is_enabled():
        return None, []
    with page.expect_response(lambda r: "/api/check/aidetector" in r.url, timeout=60_000) as info:
        button.click()
    body = info.value.json()
    ranges = [
        {"begin": r["begin"], "end": r["end"], "score": r["score"], "text": text[r["begin"]:r["end"]]}
        for r in body.get("alertRanges", [])
    ]
    return body.get("score"), ranges


def main(paths):
    if not paths:
        print(__doc__.strip())
        return 2
    checker = load_checker()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        for path in paths:
            text = prose(checker, path)
            if len(text) > MAX_CHARS:
                result, ranges = None, []
            else:
                result, ranges = score(browser, text)
            print(json.dumps({"path": path, "chars": len(text), "score": result, "ranges": ranges}), flush=True)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
