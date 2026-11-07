## Кастомизация под нишу

Адаптация под конкретный проект через:

- **`seo-cycle.yaml`** — основной механизм (язык, поисковики, project_type, источники, tone, content_rules)
- **`content_rules.fact_check`** — отключи для не-технических ниш
- **`content_rules.stock_first`** — только для ecommerce с инвентарём
- **`content_rules.local_signals`** — отключи для глобального B2B SaaS
- **`seo/brand/voice.yaml`** — профиль голоса бренда, методов письма по типам страниц и типов изображений (`seo-cycle voice init --write`, `docs/brand-voice.md`); доходит до брифа, context pack и гейта черновика
- **`tone.stop_words_extra`** — добавляй свои запреты
- **Custom prompts** — клонируй `./.codex/skills/seo-cycle/prompts/*` в `<project>/seo/prompts/` и переопредели
- **Custom delegate** — создавай проектные субскиллы и прописывай в `delegate.*`

См. `docs/adapt.md` для подробной инструкции по адаптации.
