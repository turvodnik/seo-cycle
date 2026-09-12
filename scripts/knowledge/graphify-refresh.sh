#!/usr/bin/env bash
# graphify-refresh.sh — rebuild the wiki corpus and the Graphify knowledge graph.
#
# Money (T-069 fix round 1, gate F-2): the semantic graph is built either by an
# LLM CLI (`agy`/`gemini` — subscription tokens; a live health probe first, then
# up to --max-files files) or by `graphify extract --backend <api>` on API keys
# from env (per-token billing). Any of those needs explicit consent:
#   graphify-refresh.sh --live      (or GRAPHIFY_LIVE=1)
# Without it, when an LLM path is reachable, the script prints the plan and
# exits 3 — no CLI probe, no extract. Before the first LLM call one
# write-ahead line goes to usage-ledger (`--service graphify --category llm
# --requests 1 --fail-on-block`); a cap, a broken ledger, or no seo-cycle.yaml
# in the project root stops the run (exit 1). The wiki refresh, the corpus
# build and the local (no-LLM) fallback graph are free and need no flag.
set -euo pipefail

ROOT="${SEO_CYCLE_PROJECT_ROOT:-$(pwd)}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEDGER_SCRIPT="$SCRIPT_DIR/../usage-ledger.py"
LIVE="${GRAPHIFY_LIVE:-0}"
for arg in "$@"; do
  [[ "$arg" == "--live" ]] && LIVE=1
done
cd "$ROOT"

paths_json="$(PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
import json
from wiki_common import GRAPH_CORPUS_ROOT, GRAPH_ROOT
print(json.dumps({"corpus": str(GRAPH_CORPUS_ROOT), "graph": str(GRAPH_ROOT)}, ensure_ascii=False))
PY
)"
CORPUS="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["corpus"])' <<< "$paths_json")"
OUT="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["graph"])' <<< "$paths_json")"
BACKEND="${GRAPHIFY_BACKEND:-}"
MODEL="${GRAPHIFY_MODEL:-}"
MODE="${GRAPHIFY_MODE:-}"
LOCAL_FALLBACK="${GRAPHIFY_LOCAL_FALLBACK:-1}"
AUTO_CLI="${GRAPHIFY_AUTO_CLI:-1}"
GEMINI_CLI="${GRAPHIFY_GEMINI_CLI:-auto}"
ANTIGRAVITY_CLI="${GRAPHIFY_ANTIGRAVITY_CLI:-auto}"
ANTIGRAVITY_ARGS="${GRAPHIFY_ANTIGRAVITY_ARGS:---max-files 35 --max-chars 26000 --per-file-chars 5000 --timeout 150}"
GEMINI_ARGS="${GRAPHIFY_GEMINI_ARGS:---max-files 35 --max-chars 26000 --per-file-chars 5000 --timeout 150}"

status_json() {
  local status="$1"
  local reason="$2"
  local next_step="$3"
  cat > "$OUT/graphify-status.json" <<JSON
{
  "status": "$status",
  "reason": "$reason",
  "corpus_root": "$CORPUS",
  "next_step": "$next_step"
}
JSON
}

graphify_python() {
  local graphify_bin
  graphify_bin="$(command -v graphify)"
  head -1 "$graphify_bin" | sed 's/^#!//'
}

cli_requested() {
  local value="$1"
  [[ "$value" == "1" || ( "$value" == "auto" && "$AUTO_CLI" == "1" ) ]]
}

cli_health() {
  local cli="$1"
  local timeout_secs="${2:-45}"
  command -v "$cli" >/dev/null 2>&1 || return 1
  if [[ "$cli" == "agy" ]]; then
    "$cli" --print "Ответь одним словом: готов" --print-timeout "${timeout_secs}s" >/dev/null 2>&1
  else
    "$cli" -p "Ответь одним словом: готов" --output-format text --approval-mode plan >/dev/null 2>&1
  fi
}

build_with_cli() {
  local cli="$1"
  shift
  local py
  py="$(graphify_python)"
  "$py" "$SCRIPT_DIR/graphify-build-gemini-cli-graph.py" --cli "$cli" "$@"
}

write_graph_tree() {
  local graph_json="$OUT/graphify-out/graph.json"
  local graph_tree="$OUT/graphify-out/GRAPH_TREE.html"
  if [[ -f "$graph_json" ]]; then
    graphify tree \
      --graph "$graph_json" \
      --output "$graph_tree" \
      --root "$ROOT" \
      --label "${GRAPHIFY_PROJECT_LABEL:-SEO Knowledge Graph}" >/dev/null 2>&1 \
      || echo "Graphify graph.json was built, but GRAPH_TREE.html generation failed." >&2
  fi
}

bash "$SCRIPT_DIR/wiki-refresh-all.sh"
python3 "$SCRIPT_DIR/graphify-build-corpus.py" --write

mkdir -p "$OUT"

if ! command -v graphify >/dev/null 2>&1; then
  status_json "degraded" "graphify is not installed." "Install with: uv tool install graphifyy, then rerun graphify-refresh.sh."
  echo "graphify is not installed. Install with: uv tool install graphifyy" >&2
  exit 0
fi

# T-069: decide whether an LLM (paid) path is reachable BEFORE probing any CLI.
paid_paths=()
if [[ -n "$BACKEND" ]]; then
  paid_paths+=("backend=$BACKEND")
else
  if cli_requested "$ANTIGRAVITY_CLI" && command -v agy >/dev/null 2>&1; then paid_paths+=("cli=agy"); fi
  if cli_requested "$GEMINI_CLI" && command -v gemini >/dev/null 2>&1; then paid_paths+=("cli=gemini"); fi
  if [[ -n "${GEMINI_API_KEY:-${GOOGLE_API_KEY:-}}" ]]; then paid_paths+=("backend=gemini(api-key)"); fi
  if [[ -n "${OPENAI_API_KEY:-}" ]]; then paid_paths+=("backend=openai(api-key)"); fi
  if [[ -n "${DEEPSEEK_API_KEY:-}" ]]; then paid_paths+=("backend=deepseek(api-key)"); fi
  if [[ -n "${KIMI_API_KEY:-}" ]]; then paid_paths+=("backend=kimi(api-key)"); fi
fi
if [[ ${#paid_paths[@]} -gt 0 ]]; then
  if [[ "$LIVE" != "1" ]]; then
    echo "⛔ Нужно --live (или GRAPHIFY_LIVE=1): построение графа пойдёт через LLM (${paid_paths[*]}) — токены подписки или API-ключа." >&2
    echo "   Повтори с --live, чтобы согласиться на расход. Бесплатный путь без LLM: GRAPHIFY_AUTO_CLI=0 без API-ключей в env (локальный граф)." >&2
    exit 3
  fi
  if ! python3 "$LEDGER_SCRIPT" record --service graphify --category llm --requests 1 --fail-on-block \
        --task "graphify-refresh" --note "graphify-refresh ${paid_paths[*]}" >/dev/null; then
    echo "⛔ usage-ledger отказал в записи расхода (потолок, битый журнал или нет seo-cycle.yaml в $ROOT) — граф не строится." >&2
    exit 1
  fi
fi

if [[ -z "$BACKEND" ]]; then
  if cli_requested "$ANTIGRAVITY_CLI"; then
    if cli_health agy 45; then
      # shellcheck disable=SC2086
      if build_with_cli agy $ANTIGRAVITY_ARGS; then
        write_graph_tree
        echo "Graphify Antigravity CLI/OAuth semantic graph built automatically without API key." >&2
        exit 0
      fi
      echo "Graphify Antigravity CLI extraction failed; trying next backend." >&2
    else
      echo "Antigravity CLI is not available or not authenticated; trying next backend." >&2
    fi
  fi
  if cli_requested "$GEMINI_CLI"; then
    if cli_health gemini 45; then
      # shellcheck disable=SC2086
      if build_with_cli gemini $GEMINI_ARGS; then
        write_graph_tree
        echo "Graphify Gemini CLI/OAuth semantic graph built automatically without API key." >&2
        exit 0
      fi
      echo "Graphify Gemini CLI extraction failed; trying next backend." >&2
    else
      echo "Gemini CLI is not available or not authenticated; trying next backend." >&2
    fi
  fi
  if [[ -n "${GEMINI_API_KEY:-${GOOGLE_API_KEY:-}}" ]]; then
    BACKEND="gemini"
  elif [[ -n "${OPENAI_API_KEY:-}" ]]; then
    BACKEND="openai"
  elif [[ -n "${DEEPSEEK_API_KEY:-}" ]]; then
    BACKEND="deepseek"
  elif [[ -n "${KIMI_API_KEY:-}" ]]; then
    BACKEND="kimi"
  else
    if [[ "$LOCAL_FALLBACK" == "1" ]]; then
      GRAPHIFY_PY="$(graphify_python)"
      "$GRAPHIFY_PY" "$SCRIPT_DIR/graphify-build-local-graph.py"
      write_graph_tree
      echo "Graphify local wiki/vector graph built without API key." >&2
      exit 0
    fi
    status_json "degraded" "No Graphify LLM backend API key or authenticated CLI found." "Sign in to Antigravity CLI, or set GEMINI_API_KEY/GOOGLE_API_KEY, then rerun graphify-refresh.sh."
    echo "Graphify corpus is ready, but extraction is skipped: no supported LLM backend key is exported." >&2
    echo "Corpus: $CORPUS" >&2
    exit 0
  fi
fi

args=(extract "$CORPUS" --backend "$BACKEND" --out "$OUT")
if [[ -n "$MODEL" ]]; then
  args+=(--model "$MODEL")
fi
if [[ "$MODE" == "deep" ]]; then
  args+=(--mode deep)
fi

graphify "${args[@]}"
write_graph_tree

cat > "$OUT/graphify-status.json" <<JSON
{
  "status": "ok",
  "backend": "$BACKEND",
  "model": "$MODEL",
  "mode": "$MODE",
  "corpus_root": "$CORPUS",
  "graph_root": "$OUT/graphify-out"
}
JSON
