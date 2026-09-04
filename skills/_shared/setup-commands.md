## Phase 0 — полный набор setup/audit команд (загружай по требованию)

9. Сгенерировать и проверить рекомендации автоматизаций:
```bash
seo-cycle run script tool-stack-recommender --write
# после review: seo-cycle run script tool-stack-recommender --apply
seo-cycle run script growth-roadmap --write
seo-cycle run script setup-onboarding --write
seo-cycle run script setup-blueprint --write
seo-cycle run script project-upgrade-assistant --write
seo-cycle run script access-key-assistant --write
seo-cycle run script setup-gap-audit --write
seo-cycle run script setup-answer-plan --write  # после заполнения setup-questionnaire.csv
seo-cycle run script launch-plan --write
seo-cycle spend --write
seo-cycle run script token-waste-audit --write
seo-cycle run script perplexity-health --write
seo-cycle run script notebooklm-health --write
seo-cycle run script xmlriver-health --write
seo-cycle run script perplexity-collect --topic "<тема>" --write
seo-cycle run script notebooklm-source-pack --topic "<тема>" --export-file <export.md> --write
seo-cycle run script expert-source-pack --write
seo-cycle run script ai-brand-audit --write
seo-cycle run script answer-units-audit --write
seo-cycle run script technical-guardrails-audit --write
seo-cycle run script link-audit --write
seo-cycle run script redirect-map-audit --write
seo-cycle run script gsc-url-inspection --write
seo-cycle run script bing-url-inspection --write
seo-cycle run script lighthouse-audit --write
seo-cycle run script technical-mcp-health --write
seo-cycle run script serpstat-audit --write
seo-cycle run script labrika-source-pack --write
seo-cycle run script labrika-health --write
seo-cycle run script technical-site-audit --write
seo-cycle run script automation-recommender --write
# после review: seo-cycle run script automation-recommender --apply
```
