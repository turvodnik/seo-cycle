## Источники истины (универсальные)

1. `seo-cycle.yaml` — конфиг проекта
2. `<project>/CLAUDE.md` — правила проекта (если есть)
3. `<project>/seo/entities/entities.yaml` — реестр сущностей проекта
4. `~/.codex/skills/seo-cycle/prompts/` — универсальные промпт-шаблоны
5. `<artifacts.research_root>` — результаты исследований (ATP, Perplexity, LLM CLI)
6. `seo/loops/` — журналы автоциклов качества (attempts, delta, эскалации)
7. `seo/ads/` — raw exports, аналитика и драфты платной рекламы
8. `seo/rag.db` — локальный RAG-индекс (`rag-query.py`); глобальный — `~/.seo-cycle/rag/global.db`
9. `seo/logs/` — файловые логи скриптов (`seo-cycle-YYYY-MM-DD.log`)
10. `seo/content-mirror/` — зеркало опубликованного контента сайта + `sync-report` (что изменилось на сайте)
11. `seo/strategy/` — forecast и KPI-контракт (план vs факт, corrective actions)
