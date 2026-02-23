#!/bin/sh
# Install repo git hooks (e.g. strips Cursor co-author from commit messages).
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOKS_SRC="$ROOT/scripts/git-hooks"
HOOKS_DST="$ROOT/.git/hooks"
[ ! -d "$HOOKS_DST" ] && echo "Not a git repo or no .git/hooks" && exit 1
for f in "$HOOKS_SRC"/*; do
  [ -f "$f" ] || continue
  name=$(basename "$f")
  cp "$f" "$HOOKS_DST/$name"
  chmod +x "$HOOKS_DST/$name"
  echo "Installed $name"
done
