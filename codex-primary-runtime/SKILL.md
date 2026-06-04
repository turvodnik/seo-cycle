---
name: codex-primary-runtime
description: Точка входа для seo-cycle, когда Codex — основной мозг. Используй при запросах «запусти SEO-цикл», «продвинь раздел/категорию X», «семантическое ядро + контент-план + публикация», «мониторинг и обновления». Делегирует в универсальный скилл seo-cycle (~/.claude/skills/seo-cycle), используя гибрид: наши скрипты для уникального (РФ-источники, Serpstat/SpyFu, кэш, публикация) + нативные Codex-skills для изображений/браузера/делегирования.
---

# Codex primary runtime для seo-cycle

Когда Codex — основной оркестратор SEO-цикла, **вся логика 10 фаз** — в универсальном скилле:

```
~/.claude/skills/seo-cycle/AGENTS.md              # = симлинк на SKILL.md, полная логика фаз
~/.claude/skills/seo-cycle/docs/codex-runtime.md # маппинг Claude↔Codex
```

## Как работать

1. Установи режим: `export SEO_RUNTIME=codex`.
2. Прочитай `seo-cycle.yaml`, `docs/codex-runtime.md` и локальные policy-файлы проекта, если есть: `seo/setup/setup-control-plane.md`, `seo/setup/latest-task-route.md`, `seo/setup/latest-usage-ledger.md`, `seo/tool-stack.generated.yaml`, `seo/setup/tool-stack-report.md`, `seo/automations/automation-recommendations.md`, `seo/neuronwriter-limits.yaml`, `seo/neuronwriter.md`, `seo/entities/google-nlp-policy.yaml`, `seo/seo-data-collection-map.md`, `seo/access-setup-runbook.md`, `seo/ai-visibility-prompts.csv`, `seo/tool-budget.yaml`, `seo/automation-policy.yaml`, `seo/project-intake.yaml`, `seo/project-intake-report.md`, `seo/project-profile.generated.yaml`.
3. Перед дорогим сбором, браузером, публикацией или scheduled automation запусти `python3 ~/.claude/skills/seo-cycle/scripts/governance-report.py --format md`.
4. Для единой readiness-сводки используй `python3 ~/.claude/skills/seo-cycle/scripts/setup-control-plane.py --write`.
5. Перед конкретной задачей запусти `python3 ~/.claude/skills/seo-cycle/scripts/task-router.py --task "<цель пользователя>" --write` и следуй `seo/setup/latest-task-route.md`.
6. Перед расходом токенов/API/credits/ads сделай `python3 ~/.claude/skills/seo-cycle/scripts/usage-ledger.py check --service <tool> ... --fail-on-block`; после расхода запиши `usage-ledger.py record --service <tool> ... --write`.
7. Для выбора инструментов запускай `python3 ~/.claude/skills/seo-cycle/scripts/tool-stack-recommender.py --write`; `--apply` только после review, платные API/LLM/ads/tracking/index submission не включаются автоматически.
8. Для рекомендаций schedule запускай `python3 ~/.claude/skills/seo-cycle/scripts/automation-recommender.py --write`; `--apply` только после review, `--allow-schedules` только при явном разрешении.
9. Для детального intake используй `python3 ~/.claude/skills/seo-cycle/scripts/project-intake-wizard.py --interactive --write` или `--defaults --write`.
10. Для точечной настройки проекта используй `python3 ~/.claude/skills/seo-cycle/scripts/project-profile.py --write`; `--apply` только после review overlay/report.
11. Веди по фазам из `AGENTS.md`, но не шире task route и usage ledger.

Правила гибрида:

- **Наши скрипты** (`~/.claude/skills/seo-cycle/scripts/`) — для РФ-семантики, Serpstat/SpyFu, suggest, кэша, публикации, данных/алертов. Вызывай через bash/Python.
- **Нативные Codex skills** — для генерации изображений (`seo-image-gen`/`image`/`sora`), браузера (`browser`/`playwright`/`screenshot`) и делегирования (`dispatching-parallel-agents`).
- **Не вызывай `codex exec` сам в себе.** `llm-cli-collect.sh` в codex-режиме отдаёт только Antigravity + промпт для нативного сбора; `img-generate.sh` отдаёт `CODEX_NATIVE_IMAGE`.
- Low-token режим обязателен: сырьё на диск, в контекст только distillates/top-N, progressive disclosure вместо чтения всего проекта.
- Проверяй robots/Content-Signal policy: `search=yes, ai-input=yes, ai-train=no` допустимо как запрет обучения моделей, но публичный `robots.txt` должен быть чистым `text/plain` без PHP warnings/HTML и editor preview мусора.
- Не печатай секреты из `.env`, OAuth, API keys или service-account JSON.

## Не для одношаговых задач

Нужна только генерация картинки / только публикация / только сбор — вызывай конкретный скрипт или специализированный skill напрямую, без полного цикла.
