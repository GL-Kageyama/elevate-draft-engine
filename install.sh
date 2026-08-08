#!/usr/bin/env bash
#
# Elevate Draft Engine installer
#
# Installs the 8 creator agents to Claude Code agent discovery locations so
# they are available by name (Agent tool / @-mention), alongside the wisdom
# council evaluators.
#
# Usage:
#   ./install.sh            # Global: ~/.claude/agents/ (callable from any project)
#   ./install.sh --local    # Project: .claude/agents/ (this repo only)
#   ./install.sh --uninstall
#
# Installation uses symlinks: the canonical source stays in ./agents/, so
# edits to the repo are reflected immediately.
#
# Note: the engine (main.py) reads ./agents/*.md directly and needs no
# installation. This script only makes the creator agents callable as
# Claude Code subagents (Agent tool / @-mention).

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENTS_DIR="$REPO_DIR/agents"

MODE="global"
ACTION="install"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --local)    MODE="local" ;;
    --global)   MODE="global" ;;
    --uninstall) ACTION="uninstall" ;;
    -h|--help)
      echo "Usage: ./install.sh [--local|--global] [--uninstall]"
      echo ""
      echo "  --local      Install to .claude/ (this project only)"
      echo "  --global     Install to ~/.claude/ (default; callable from anywhere)"
      echo "  --uninstall  Remove the installed agents (default: global target)"
      exit 0
      ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
  shift
done

if [[ "$MODE" == "local" ]]; then
  TARGET_AGENTS_DIR="$REPO_DIR/.claude/agents"
else
  TARGET_AGENTS_DIR="$HOME/.claude/agents"
fi

if [[ "$ACTION" == "uninstall" ]]; then
  echo "==> Uninstalling Elevate Draft Engine agents from:"
  echo "    $TARGET_AGENTS_DIR"
  removed=0
  for agent_file in "$AGENTS_DIR"/*.md; do
    name="$(basename "$agent_file")"
    if [[ -L "$TARGET_AGENTS_DIR/$name" || -e "$TARGET_AGENTS_DIR/$name" ]]; then
      rm -rf "$TARGET_AGENTS_DIR/$name"
      echo "    ✓ removed agent $name"
      removed=$((removed+1))
    fi
  done
  echo "==> Removed $removed agent(s)."
  exit 0
fi

echo "==> Installing Elevate Draft Engine agents to:"
echo "    agents: $TARGET_AGENTS_DIR"
mkdir -p "$TARGET_AGENTS_DIR"

installed=0

# Install creator agents
for agent_file in "$AGENTS_DIR"/*.md; do
  name="$(basename "$agent_file")"
  target="$TARGET_AGENTS_DIR/$name"
  rm -rf "$target"          # remove any previous install (symlink or file)
  ln -s "$agent_file" "$target"
  installed=$((installed+1))
  echo "    ✓ agent  $name"
done

# Verify every symlink resolves to a readable file
failures=0
for target in "$TARGET_AGENTS_DIR"/*.md; do
  if [[ -f "$target" ]]; then
    :
  else
    echo "    ✗ broken: $target"
    failures=$((failures+1))
  fi
done

echo ""
if [[ $failures -gt 0 ]]; then
  echo "==> $installed installed, $failures broken symlink(s). Check $AGENTS_DIR."
  exit 1
fi

echo "==> Done: $installed agents installed."
echo ""
echo "    Callable as follows:"
echo "      Agent: strategist, differentiator, humanist, ...   # クリエイターエージェント"
echo ""
echo "    Note: the engine (main.py) reads ./agents/*.md directly —"
echo "          this installation only makes them callable as Claude Code subagents."
echo "    Note: restart Claude Code or run /agents once to reload the listing."
