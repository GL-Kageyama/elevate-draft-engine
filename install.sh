#!/usr/bin/env bash
#
# Elevate Draft Engine installer
#
# Installs the 24 creator agent variants (8 agents × 3 languages:
# English `strategist.md`, Japanese `strategist-ja.md`, Chinese `strategist-zh.md`)
# and the elevate-draft-engine facade skill to Claude Code discovery locations
# so they are available by name.
#
# Usage:
#   ./install.sh            # Global: ~/.claude/agents/ + ~/.claude/skills/ (callable from any project)
#   ./install.sh --local    # Project: .claude/agents/ + .claude/skills/ (this repo only)
#   ./install.sh --uninstall
#
# Installation uses symlinks: the canonical source stays in ./agents/ and
# ./skills/, so edits to the repo are reflected immediately.
#
# Language variants: all agents/*.md files are installed, so the agent list
# grows 3× (e.g. strategist, strategist-ja, strategist-zh). The engine picks
# the language via `--lang` / the ELEVATE_DRAFT_ENGINE_LANG env var.
#
# Note: the engine (main.py) reads ./agents/*.md directly and needs no
# installation. The agents + skill are only for calling them from Claude Code:
# the skill is a facade that invokes main.py (orchestration stays in Python).

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENTS_DIR="$REPO_DIR/agents"
SKILLS_DIR="$REPO_DIR/skills"

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
      echo "  --uninstall  Remove the installed agents and skills (default: global target)"
      exit 0
      ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
  shift
done

if [[ "$MODE" == "local" ]]; then
  TARGET_AGENTS_DIR="$REPO_DIR/.claude/agents"
  TARGET_SKILLS_DIR="$REPO_DIR/.claude/skills"
else
  TARGET_AGENTS_DIR="$HOME/.claude/agents"
  TARGET_SKILLS_DIR="$HOME/.claude/skills"
fi

if [[ "$ACTION" == "uninstall" ]]; then
  echo "==> Uninstalling Elevate Draft Engine agents/skills from:"
  echo "    $TARGET_AGENTS_DIR"
  echo "    $TARGET_SKILLS_DIR"
  removed=0
  # agents
  for agent_file in "$AGENTS_DIR"/*.md; do
    name="$(basename "$agent_file")"
    if [[ -L "$TARGET_AGENTS_DIR/$name" || -e "$TARGET_AGENTS_DIR/$name" ]]; then
      rm -rf "$TARGET_AGENTS_DIR/$name"
      echo "    ✓ removed agent $name"
      removed=$((removed+1))
    fi
  done
  # skills
  for skill_dir in "$SKILLS_DIR"/*/; do
    name="$(basename "$skill_dir")"
    if [[ -L "$TARGET_SKILLS_DIR/$name" || -e "$TARGET_SKILLS_DIR/$name" ]]; then
      rm -rf "$TARGET_SKILLS_DIR/$name"
      echo "    ✓ removed skill $name"
      removed=$((removed+1))
    fi
  done
  echo "==> Removed $removed component(s)."
  exit 0
fi

echo "==> Installing Elevate Draft Engine to:"
echo "    agents: $TARGET_AGENTS_DIR"
echo "    skills: $TARGET_SKILLS_DIR"
mkdir -p "$TARGET_AGENTS_DIR" "$TARGET_SKILLS_DIR"

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

# Install the facade skill
for skill_dir in "$SKILLS_DIR"/*/; do
  name="$(basename "$skill_dir")"
  target="$TARGET_SKILLS_DIR/$name"
  rm -rf "$target"
  ln -s "$skill_dir" "$target"
  installed=$((installed+1))
  echo "    ✓ skill $name"
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
for target in "$TARGET_SKILLS_DIR"/*/; do
  if [[ -f "$target/SKILL.md" ]]; then
    :
  else
    echo "    ✗ broken: $target"
    failures=$((failures+1))
  fi
done

echo ""
if [[ $failures -gt 0 ]]; then
  echo "==> $installed installed, $failures broken symlink(s). Check $AGENTS_DIR and $SKILLS_DIR."
  exit 1
fi

echo "==> Done: $installed components installed."
echo ""
echo "    Callable as follows:"
echo "      Skill: elevate-draft-engine       # ファサード（main.py を起動）"
echo "      Agent: strategist, humanist, ...  # クリエイターエージェント（サブエージェントとして起動可）"
echo "      Language variants: -ja / -zh suffixes (e.g. strategist-ja)"
echo "      (the engine selects the language via --lang / ELEVATE_DRAFT_ENGINE_LANG)"
echo ""
echo "    Note: the engine (main.py) reads ./agents/*.md directly —"
echo "          the agents/skill installation only makes them callable from Claude Code."
echo "    Note: restart Claude Code or run /agents and /skills once to reload the listing."
