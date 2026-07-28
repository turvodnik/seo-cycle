## Phase 0 — полный набор setup/audit команд (загружай по требованию)

9. Сгенерировать и проверить рекомендации автоматизаций:
```bash
python3 ~/.codex/skills/seo-cycle/scripts/tool-stack-recommender.py --write
# после review: python3 ~/.codex/skills/seo-cycle/scripts/tool-stack-recommender.py --apply
python3 ~/.codex/skills/seo-cycle/scripts/growth-roadmap.py --write
python3 ~/.codex/skills/seo-cycle/scripts/setup-onboarding.py --write
python3 ~/.codex/skills/seo-cycle/scripts/setup-blueprint.py --write
python3 ~/.codex/skills/seo-cycle/scripts/project-upgrade-assistant.py --write
python3 ~/.codex/skills/seo-cycle/scripts/access-key-assistant.py --write
python3 ~/.codex/skills/seo-cycle/scripts/setup-gap-audit.py --write
python3 ~/.codex/skills/seo-cycle/scripts/setup-answer-plan.py --write  # после заполнения setup-questionnaire.csv
python3 ~/.codex/skills/seo-cycle/scripts/launch-plan.py --write
python3 ~/.codex/skills/seo-cycle/scripts/spend-guard.py --write
python3 ~/.codex/skills/seo-cycle/scripts/token-waste-audit.py --write
python3 ~/.codex/skills/seo-cycle/scripts/perplexity-health.py --write
python3 ~/.codex/skills/seo-cycle/scripts/notebooklm-health.py --write
python3 ~/.codex/skills/seo-cycle/scripts/xmlriver-health.py --write
python3 ~/.codex/skills/seo-cycle/scripts/perplexity-collect.py --topic "<тема>" --write
python3 ~/.codex/skills/seo-cycle/scripts/notebooklm-source-pack.py --topic "<тема>" --export-file <export.md> --write
python3 ~/.codex/skills/seo-cycle/scripts/expert-source-pack.py --write
python3 ~/.codex/skills/seo-cycle/scripts/ai-brand-audit.py --write
python3 ~/.codex/skills/seo-cycle/scripts/answer-units-audit.py --write
python3 ~/.codex/skills/seo-cycle/scripts/technical-guardrails-audit.py --write
python3 ~/.codex/skills/seo-cycle/scripts/link-audit.py --write
python3 ~/.codex/skills/seo-cycle/scripts/redirect-map-audit.py --write
python3 ~/.codex/skills/seo-cycle/scripts/gsc-url-inspection.py --write
python3 ~/.codex/skills/seo-cycle/scripts/bing-url-inspection.py --write
python3 ~/.codex/skills/seo-cycle/scripts/lighthouse-audit.py --write
python3 ~/.codex/skills/seo-cycle/scripts/technical-mcp-health.py --write
python3 ~/.codex/skills/seo-cycle/scripts/serpstat-audit.py --write
python3 ~/.codex/skills/seo-cycle/scripts/labrika-source-pack.py --write
python3 ~/.codex/skills/seo-cycle/scripts/labrika-health.py --write
python3 ~/.codex/skills/seo-cycle/scripts/technical-site-audit.py --write
python3 ~/.codex/skills/seo-cycle/scripts/automation-recommender.py --write
# после review: python3 ~/.codex/skills/seo-cycle/scripts/automation-recommender.py --apply
```
