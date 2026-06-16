#!/usr/bin/env bash
# nw-cli.sh — universal NeuronWriter API helper (seo-cycle skill).
#
# Usage:
#   nw-cli projects                              List all NeuronWriter projects
#   nw-cli queries PROJECT_ID [STATUS]           List queries (status: waiting|in progress|ready)
#   nw-cli new PROJECT KEYWORD [ENGINE] [LANG] [MODE]
#                                                Create query (defaults: google.com, English, top-intent)
#   nw-cli get QUERY_ID                          Get analysis result (polls until ready, max ~2.5 min)
#   nw-cli content QUERY_ID                      Get last saved content
#   nw-cli evaluate QUERY_ID HTML_FILE           Score content without saving
#   nw-cli import QUERY_ID HTML_FILE             Save content and score
#   nw-cli plagiarism QUERY_ID [HTML_FILE]       Run account-specific plagiarism API call only when NW_PLAGIARISM_PATH is set
#
# Reads NEURON_API_KEY from env or from .env in current/parent dirs (up to 3 levels).
# Defaults можно переопределить через env: NW_DEFAULT_ENGINE, NW_DEFAULT_LANGUAGE, NW_DEFAULT_MODE.
# Public NeuronWriter API docs do not list a plagiarism endpoint. Use the UI
# Editor menu by default. Set NW_PLAGIARISM_PATH only if NeuronWriter support
# gives you an account-specific documented path.
# Requires: curl, jq.

set -euo pipefail
NW_BASE="https://app.neuronwriter.com/neuron-api/0.5/writer"

# Defaults (для русскоязычных проектов переопредели через env или передавай явно)
DEFAULT_ENGINE="${NW_DEFAULT_ENGINE:-google.com}"
DEFAULT_LANGUAGE="${NW_DEFAULT_LANGUAGE:-English}"
DEFAULT_MODE="${NW_DEFAULT_MODE:-top-intent}"
PLAGIARISM_PATH="${NW_PLAGIARISM_PATH:-}"

if [[ "${1:-}" == "" || "${1:-}" == "-h" || "${1:-}" == "--help" || "${1:-}" == "help" ]]; then
  sed -n '2,/^# Requires:/p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
fi

# Load NEURON_API_KEY from .env (search up to 3 levels). Do not source the
# whole file: project .env files often contain values that are not valid shell.
if [ -z "${NEURON_API_KEY:-}" ]; then
  for envfile in ".env" "../.env" "../../.env"; do
    if [ -f "$envfile" ]; then
      value="$(
        awk '
          /^[[:space:]]*NEURON_API_KEY[[:space:]]*=/ {
            sub(/^[[:space:]]*NEURON_API_KEY[[:space:]]*=[[:space:]]*/, "", $0)
            gsub(/^[\"\047]|[\"\047]$/, "", $0)
            print
            exit
          }
        ' "$envfile"
      )"
      if [ -n "$value" ]; then
        NEURON_API_KEY="$value"
      fi
      [ -n "${NEURON_API_KEY:-}" ] && break
    fi
  done
fi

if [ -z "${NEURON_API_KEY:-}" ]; then
  echo "Error: NEURON_API_KEY not found in env or .env" >&2
  echo "  Add to <project>/.env: NEURON_API_KEY=your_key_here" >&2
  exit 1
fi

command -v jq >/dev/null 2>&1 || { echo "Error: jq is required (brew install jq)" >&2; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "Error: curl is required" >&2; exit 1; }

req() {
  local path="$1"; shift
  curl -sS -X POST "$NW_BASE$path" \
    -H "X-API-KEY: $NEURON_API_KEY" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    "$@"
}

cmd="${1:-}"; shift || true

case "$cmd" in
  projects)
    req /list-projects -d '{}' | jq .
    ;;
  queries)
    project="${1:?need project_id (см. nw-cli projects)}"
    status="${2:-}"
    if [ -n "$status" ]; then
      body=$(jq -nc --arg p "$project" --arg s "$status" '{project:$p, status:$s}')
    else
      body=$(jq -nc --arg p "$project" '{project:$p}')
    fi
    req /list-queries -d "$body" | jq .
    ;;
  new)
    project="${1:?need project_id}"
    keyword="${2:?need keyword}"
    engine="${3:-$DEFAULT_ENGINE}"
    lang="${4:-$DEFAULT_LANGUAGE}"
    mode="${5:-$DEFAULT_MODE}"
    body=$(jq -nc --arg p "$project" --arg k "$keyword" --arg e "$engine" --arg l "$lang" --arg m "$mode" \
      '{project:$p, keyword:$k, engine:$e, language:$l, competitors_mode:$m}')
    req /new-query -d "$body" | jq .
    ;;
  get)
    qid="${1:?need query_id}"
    body=$(jq -nc --arg q "$qid" '{query:$q}')
    for i in $(seq 1 30); do
      resp=$(req /get-query -d "$body")
      status=$(echo "$resp" | jq -r '.status // "unknown"')
      if [ "$status" = "ready" ]; then
        echo "$resp" | jq .
        exit 0
      fi
      echo "[nw-cli get] status=$status (attempt $i/30)" >&2
      sleep 5
    done
    echo "Error: timeout waiting for query $qid" >&2
    exit 1
    ;;
  content)
    qid="${1:?need query_id}"
    body=$(jq -nc --arg q "$qid" '{query:$q}')
    req /get-content -d "$body" | jq .
    ;;
  evaluate|import)
    qid="${1:?need query_id}"
    file="${2:?need html file}"
    [ ! -f "$file" ] && { echo "Error: file not found: $file" >&2; exit 1; }
    html=$(cat "$file")
    # NW оценивает полную страницу: <title> + <meta description> + body.
    # Body-only снижает content_score на 15-20 пунктов.
    if ! grep -qi '<title>' <<<"$html"; then
      echo "Warning: $file has no <title> tag. NW score may be 15-20pt lower than expected." >&2
      echo "         Wrap body HTML in a full page with <title> for accurate scoring." >&2
    fi
    body=$(jq -nc --arg q "$qid" --arg h "$html" '{query:$q, html:$h}')
    if [ "$cmd" = "evaluate" ]; then
      req /evaluate-content -d "$body" | jq .
    else
      req /import-content -d "$body" | jq .
    fi
    ;;
  plagiarism)
    qid="${1:?need query_id}"
    file="${2:-}"
    if [ -z "$PLAGIARISM_PATH" ]; then
      cat >&2 <<'EOF'
Error: public NeuronWriter API docs do not document a plagiarism endpoint.
Use the NeuronWriter editor UI:
  1) nw-cli import QUERY_ID file.html
  2) open query_url in a logged-in browser
  3) Editor menu → Check for plagiarism
  4) save the UI report under seo/research/neuronwriter/

If NeuronWriter support gives you an account-specific API path, set:
  NW_PLAGIARISM_PATH=/your-documented-path
EOF
      exit 2
    fi
    if [ -n "$file" ] && [ ! -f "$file" ]; then
      echo "Error: file not found: $file" >&2
      exit 1
    fi
    if [ -n "$file" ]; then
      html=$(cat "$file")
      body=$(jq -nc --arg q "$qid" --arg h "$html" '{query:$q, html:$h}')
    else
      body=$(jq -nc --arg q "$qid" '{query:$q}')
    fi
    req "$PLAGIARISM_PATH" -d "$body" | jq .
    ;;
  ""|-h|--help|help)
    sed -n '2,/^# Requires:/p' "$0" | sed 's/^# \{0,1\}//'
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    echo "Run 'nw-cli help' for usage." >&2
    exit 1
    ;;
esac
