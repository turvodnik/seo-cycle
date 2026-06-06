#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: install-ai-toolchain.sh [--codex] [--check]

Installs the optional local AI/SEO support toolchain:
- GitHub Spec Kit CLI for spec-driven development
- Microsoft MarkItDown for evidence/document ingestion
- Graphify for mixed code/docs/research knowledge graphs
- CodeGraph for local code-symbol graphs and Codex MCP access

This script does not install stealth/anti-bot browsers, paid APIs, or memory
services. It never writes secrets.

Options:
  --codex   Install Codex integrations for Graphify and CodeGraph
  --check   Print installed versions/status only
EOF
}

install_codex=false
check_only=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --codex)
      install_codex=true
      ;;
    --check)
      check_only=true
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

print_status() {
  echo "== AI toolchain status =="
  if command -v specify >/dev/null 2>&1; then
    specify version | sed -n '1,24p'
  else
    echo "specify: not installed"
  fi
  if command -v markitdown >/dev/null 2>&1; then
    markitdown --version || true
  else
    echo "markitdown: not installed"
  fi
  if command -v graphify >/dev/null 2>&1; then
    graphify --version
  else
    echo "graphify: not installed"
  fi
  if command -v codegraph >/dev/null 2>&1; then
    codegraph --version
  else
    echo "codegraph: not installed"
  fi
  if grep -q '^\[mcp_servers\.codegraph\]' "$HOME/.codex/config.toml" 2>/dev/null; then
    echo "codex codegraph MCP: configured"
  else
    echo "codex codegraph MCP: not configured"
  fi
}

if [[ "$check_only" == true ]]; then
  print_status
  exit 0
fi

need_cmd uv
need_cmd npm

echo "Installing GitHub Spec Kit CLI..."
uv tool install specify-cli --force --from git+https://github.com/github/spec-kit.git@v0.9.0

echo "Installing Microsoft MarkItDown..."
uv tool install 'markitdown[all]' --force

echo "Installing Graphify..."
uv tool install graphifyy --force

echo "Installing CodeGraph..."
npm install -g @colbymchenry/codegraph

if [[ "$install_codex" == true ]]; then
  echo "Installing Graphify Codex skill..."
  graphify install --platform codex

  echo "Installing CodeGraph Codex MCP config..."
  codegraph install --target codex --location global --yes
fi

print_status
