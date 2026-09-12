#!/bin/sh
set -eu

HERMES_HOME_DIR=${HERMES_HOME:-"$HOME/.hermes"}
TARGET="$HERMES_HOME_DIR/plugins/hermes-codex-usage"
if [ ! -f "$TARGET/plugin.yaml" ] || ! grep -q '^name: hermes-codex-usage$' "$TARGET/plugin.yaml"; then
  printf '%s\n' "Refusing to remove a missing or unrelated plugin at $TARGET" >&2
  exit 1
fi
rm -rf "$TARGET"
printf '%s\n' "Removed hermes-codex-usage from $TARGET"
