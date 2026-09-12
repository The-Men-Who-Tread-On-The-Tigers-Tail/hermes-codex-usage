#!/bin/sh
set -eu

REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
HERMES_HOME_DIR=${HERMES_HOME:-"$HOME/.hermes"}
TARGET="$HERMES_HOME_DIR/plugins/hermes-codex-usage"
STAGE="$HERMES_HOME_DIR/plugins/.hermes-codex-usage.install.$$"

mkdir -p "$HERMES_HOME_DIR/plugins"
if [ -e "$TARGET/plugin.yaml" ] && ! grep -q '^name: hermes-codex-usage$' "$TARGET/plugin.yaml"; then
  printf '%s\n' "Refusing to overwrite unrelated plugin at $TARGET" >&2
  exit 1
fi
rm -rf "$STAGE"
mkdir "$STAGE"
cp "$REPO_DIR/plugin.yaml" "$STAGE/"
cp -R "$REPO_DIR/dashboard" "$STAGE/"
cp -R "$REPO_DIR/desktop" "$STAGE/"
rm -rf "$TARGET"
mv "$STAGE" "$TARGET"
printf '%s\n' "Installed hermes-codex-usage to $TARGET"
printf '%s\n' "Next: hermes plugins enable hermes-codex-usage"
printf '%s\n' "Then restart the Hermes gateway and reload Desktop plugins."
