#!/usr/bin/env bash
# PostToolUse hook: check.py over a Markdown file Claude just wrote. Exit 2 hands the findings back.
# Only hard findings speak: warnings would fire on nearly every file and train everyone to ignore it.
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
file=$(python3 -c 'import json, sys; print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))')

case "$file" in
    "$ROOT"/*.md | "$ROOT"/*.mdx) ;;
    *) exit 0 ;;
esac
# Vendored and generated Markdown is not ours to restyle.
case "$file" in
    */node_modules/* | */vendor/* | */.git/* | */target/* | */dist/* | */build/* | */CHANGELOG.md) exit 0 ;;
esac
[ -f "$file" ] || exit 0

config="$ROOT/.claude/human-writing.json"
if [ -f "$config" ]; then
    # "hook": false turns this hook off for a project that runs its own checker.
    python3 -c 'import json, sys; sys.exit(0 if json.load(open(sys.argv[1])).get("hook", True) else 1)' "$config" 2>/dev/null || exit 0
    # "exclude" takes shell globs relative to the project root.
    rel="${file#"$ROOT"/}"
    while IFS= read -r pattern; do
        # shellcheck disable=SC2053
        [[ -n "$pattern" && "$rel" == $pattern ]] && exit 0
    done < <(python3 -c 'import json, sys; print("\n".join(json.load(open(sys.argv[1])).get("exclude", [])))' "$config" 2>/dev/null)
fi

# check.py exits 1 on a crash too; only a counted hard finding goes back as feedback.
out=$(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check.py" "$file" 2>&1)
if printf '%s' "$out" | grep -Eq ', [1-9][0-9]* hard finding'; then
    printf '%s\n' "$out" >&2
    exit 2
fi
exit 0
