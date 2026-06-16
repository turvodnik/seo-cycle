#!/usr/bin/env bash
set -euo pipefail

ROOT="${SEO_CYCLE_PROJECT_ROOT:-$(pwd)}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

python3 "$SCRIPT_DIR/wiki-export-project-state.py"
python3 "$SCRIPT_DIR/api-catalog-curator.py" --write
python3 "$SCRIPT_DIR/review-cluster-plan.py" --write

if [[ -n "${SEO_CYCLE_WIKI_INGEST_REPORTS:-}" ]]; then
  IFS=":" read -r -a report_candidates <<< "$SEO_CYCLE_WIKI_INGEST_REPORTS"
else
  report_candidates=(
    seo/research-package/research-package-quality.json
    seo/research-package/page-outline-quality.json
    seo/research-package/draft-quality-gate.json
    seo/setup/project-journey.json
    seo/technical/technical-site-audit.json
    seo/vnext/ai-brand-audit.json
    seo/vnext/expert-source-pack.json
  )
fi

for report in "${report_candidates[@]}"; do
  if [[ -f "$report" ]]; then
    python3 "$SCRIPT_DIR/wiki-ingest-report.py" "$report" --write
  fi
done

topic="${SEO_CYCLE_CONTEXT_TOPIC:-правила статьи категории бренды товары}"
python3 "$SCRIPT_DIR/wiki-context-pack.py" --topic "$topic" --write
python3 "$SCRIPT_DIR/zvec-hybrid-index.py" --build --write
