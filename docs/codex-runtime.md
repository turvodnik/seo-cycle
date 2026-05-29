# Codex как основной мозг seo-cycle

Скилл работает с двумя рантаймами. Логика фаз — общая (в `SKILL.md`), различается только **механика вызова инструментов**. Этот документ — про запуск, когда оркестратор не Claude Code, а **Codex CLI**.

## Точка входа

- Claude Code читает `SKILL.md` (распознаёт скилл по YAML-frontmatter).
- Codex читает `AGENTS.md` — это **симлинк на `SKILL.md`**, то есть тот же контент. Codex воспринимает frontmatter как обычный markdown-заголовок, это не мешает.

Запуск Codex-сессии из корня проекта (где лежит `seo-cycle.yaml`):
```bash
cd <проект>
codex exec -c model_reasoning_effort="xhigh" -c web_search="live" \
  "Прочитай ~/.claude/skills/seo-cycle/AGENTS.md и seo-cycle.yaml. Запусти SEO-цикл Phase 2 для кластера 'минеральная вата'."
```
Либо положить `AGENTS.md`-симлинк в корень проекта, чтобы Codex подхватил автоматически:
```bash
ln -s ~/.claude/skills/seo-cycle/AGENTS.md ./AGENTS.md
```

## Отличия механики (Claude → Codex)

| Аспект | Claude Code | Codex CLI |
|---|---|---|
| Точка входа | `SKILL.md` (Skill tool) | `AGENTS.md` (симлинк) |
| Делегирование субзадач | subagents (`Agent` tool) | последовательные `codex exec` вызовы или внутренние шаги |
| Сбор семантики | те же скрипты | те же скрипты (`scripts/*.py`, `*.sh`) |
| Approval gates | `approval-gate.py` + UI | `approval-gate.py` (file-based, читается в любом рантайме) |
| Браузерные источники (Perplexity, Wordstat deep) | Claude in Chrome MCP | нужен свой браузер-инструмент или ручной ввод |

**Главное:** все `scripts/` рантайм-агностичны (чистый Python/bash) — работают одинаково. Меняется только кто их оркестрирует.

## Что Codex-специфично

- **Reasoning + web search** включать явно: `-c model_reasoning_effort="xhigh" -c web_search="live"` (для глубокого fact-check и сбора). Уже зашито в `llm-cli-collect.sh`.
- **Headless/cron:** Codex хорош для неинтерактивных прогонов. `monthly-runner.sh` можно вызывать из Codex-сессии так же, как из Claude.
- **MCP-браузер:** если у Codex нет браузерного MCP — браузерные источники (Perplexity Deep Research, Wordstat deep, Я.Вебмастер) выполняются вручную или пропускаются; API-источники (Serpstat/SpyFu/GSC/suggest) работают полностью.

## Поддержание симлинка

`AGENTS.md → SKILL.md` создаётся один раз:
```bash
cd ~/.claude/skills/seo-cycle && ln -sf SKILL.md AGENTS.md
```
При шаринге через git симлинк сохраняется (git хранит симлинки). После `git clone` проверь: `ls -l AGENTS.md` должен показывать `-> SKILL.md`.
