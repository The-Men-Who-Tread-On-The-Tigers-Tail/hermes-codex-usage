#!/bin/sh
set -eu

REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
HERMES_HOME_DIR=${HERMES_HOME:-"$HOME/.hermes"}
PLUGIN_DIR="$HERMES_HOME_DIR/plugins"
TARGET="$PLUGIN_DIR/hermes-codex-usage"
STAGE="$PLUGIN_DIR/.hermes-codex-usage.install.$$"
BACKUP="$PLUGIN_DIR/.hermes-codex-usage.previous.$$"

cleanup() {
  rm -rf "$STAGE"
}
trap cleanup EXIT INT TERM

mkdir -p "$PLUGIN_DIR"
if [ -e "$TARGET" ] || [ -L "$TARGET" ]; then
  if [ ! -f "$TARGET/plugin.yaml" ] || ! grep -q '^name: hermes-codex-usage$' "$TARGET/plugin.yaml"; then
    printf '%s\n' "Refusing to overwrite unrelated plugin at $TARGET" >&2
    exit 1
  fi
fi

rm -rf "$STAGE" "$BACKUP"
mkdir "$STAGE"
cp "$REPO_DIR/__init__.py" "$STAGE/"
cp "$REPO_DIR/plugin.yaml" "$STAGE/"
cp -R "$REPO_DIR/dashboard" "$STAGE/"
cp -R "$REPO_DIR/desktop" "$STAGE/"

if [ -e "$TARGET" ] || [ -L "$TARGET" ]; then
  mv "$TARGET" "$BACKUP"
fi
if ! mv "$STAGE" "$TARGET"; then
  if [ -e "$BACKUP" ]; then mv "$BACKUP" "$TARGET"; fi
  exit 1
fi
rm -rf "$BACKUP"
printf '%s\n' "Installed hermes-codex-usage to $TARGET"
printf '%s\n' "Next: hermes plugins enable hermes-codex-usage"
printf '%s\n' "Then restart the Hermes gateway and reload Desktop plugins."
