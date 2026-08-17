#!/usr/bin/env bash
#
# Symlink every skill in this repository into a Claude Code skills directory.
#
#   ./install.sh                              # user scope: ~/.claude/skills
#   ./install.sh /path/to/project             # project scope: <project>/.claude/skills
#
# Symlinks, not copies: edits in this repository take effect immediately.
# Prefer the plugin marketplace install described in README.md; this script is for
# people who want the skills as plain files.

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src_dir="$repo_dir/skills"

if [ $# -gt 0 ]; then
  target_dir="${1%/}/.claude/skills"
else
  target_dir="$HOME/.claude/skills"
fi

if [ ! -d "$src_dir" ]; then
  echo "error: no skills/ directory found in $repo_dir" >&2
  exit 1
fi

mkdir -p "$target_dir"

installed=0
for skill_path in "$src_dir"/*/; do
  [ -f "$skill_path/SKILL.md" ] || continue

  name="$(basename "$skill_path")"
  link="$target_dir/$name"

  if [ -L "$link" ]; then
    rm "$link"
  elif [ -e "$link" ]; then
    echo "skip  $name (a real file or directory already exists at $link)"
    continue
  fi

  ln -s "${skill_path%/}" "$link"
  echo "link  $name -> $link"
  installed=$((installed + 1))
done

echo
echo "Installed $installed skill(s) into $target_dir"
echo "Run /skills inside Claude Code to verify."
