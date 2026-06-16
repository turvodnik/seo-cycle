# Knowledge Hub

Knowledge Hub превращает набор SEO-артефактов проекта в единый источник правды:
правила проекта, WordPress inventory, статьи, категории, бренды, товары, отчёты,
решения, context packs, Graphify-граф и hybrid search.

## Зачем

- Не создавать дубли статей и интентов.
- Перед обновлением старой страницы видеть трафик, старый текст, ссылки, риски и причины правки.
- Хранить проектные правила: публичное написание бренда, запреты на claims, CMS-поля, публикационные ограничения.
- Давать Codex короткий context pack вместо чтения raw-выгрузок и длинных отчётов.
- Строить связи: статья -> категория -> бренд -> товар -> FAQ -> источник -> решение.

## Установка в новом проекте

```bash
curl -fsSL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/bootstrap-codex.sh | bash
bash ./.codex/skills/seo-cycle/scripts/knowledge/wiki-refresh-all.sh
bash ./.codex/skills/seo-cycle/scripts/knowledge/graphify-refresh.sh
```

Bootstrap ставит только локальные entrypoints проекта. Общий core лежит в
`~/.codex/vendor/seo-cycle`, но wiki, индексы и ключи всегда остаются внутри
текущего проекта.

## Обновление старого проекта

```bash
curl -fsSL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/bootstrap-codex.sh | bash -s -- --skip-init
python3 ./.codex/skills/seo-cycle/scripts/project-upgrade-assistant.py --write
python3 ./.codex/skills/seo-cycle/scripts/project-upgrade-apply.py --write
python3 ./.codex/skills/seo-cycle/scripts/setup-control-plane.py --write
```

`project-upgrade-apply.py --write` делает dry-run. Реальный `--apply` запускается
только после review questionnaire. `.env`, секреты, paid API, публикация,
индексация и расписания не трогаются.

## Основные команды

```bash
# Обновить wiki, API catalog, review cluster plan, context pack и hybrid index
bash ./.codex/skills/seo-cycle/scripts/knowledge/wiki-refresh-all.sh

# Проверить конкретную правку или публикацию
python3 ./.codex/skills/seo-cycle/scripts/knowledge/wiki-preflight.py \
  --url "https://example.com/blog/example/" \
  --query "основной запрос" \
  --draft seo/research-package/drafts/example.md \
  --write

# Проверить качество публичного текста
python3 ./.codex/skills/seo-cycle/scripts/knowledge/content-taste-gate.py \
  seo/research-package/drafts/example.md \
  --write

# Получить короткий context pack для следующей задачи
python3 ./.codex/skills/seo-cycle/scripts/knowledge/wiki-context-pack.py \
  --topic "изоспан пароизоляция статьи товары" \
  --write

# Graphify: semantic graph через Antigravity/Gemini CLI/API или degraded status
bash ./.codex/skills/seo-cycle/scripts/knowledge/graphify-refresh.sh

# Поиск по wiki/vector через SQLite FTS, zvec-ready output
python3 ./.codex/skills/seo-cycle/scripts/knowledge/zvec-hybrid-index.py \
  --query "Изоспан ленты пароизоляция" \
  --limit 10
```

## Артефакты

- `seo/knowledge/wiki/project-manifest.json` — manifest проекта.
- `seo/knowledge/wiki/state/*.jsonl` — статьи, категории, бренды, товары, internal links.
- `seo/knowledge/wiki/rules/*.md` — правила проекта, content taste, lean engineering.
- `seo/knowledge/wiki/context/latest-context-pack.md` — первый файл для чтения Codex.
- `seo/knowledge/wiki/preflight/wiki-preflight.md/json` — последняя preflight-проверка.
- `seo/knowledge/wiki/reports/content-taste-gate.md/json` — последняя проверка публичного текста.
- `seo/knowledge/wiki/frameworks/review-cluster-plan.md` — кандидаты review/comparison страниц.
- `seo/knowledge/wiki/api-catalog/` — curated API shortlist, а не автоподключение всех API.
- `seo/knowledge/graph/graphify-status.json` — статус Graphify.
- `seo/knowledge/zvec/hybrid.sqlite` — локальный hybrid search index.

## Project-specific overrides

Core не должен содержать темы конкретного сайта. Для конкретного проекта можно
добавить локальный файл:

```json
[
  {
    "id": "brand-comparison",
    "title": "Бренд A и Бренд B: как выбрать под задачу",
    "category_tokens": ["category-token"],
    "category_include_tokens": ["category-token"],
    "brand_tokens": ["brand-a", "brand-b"],
    "intent": "choice/comparison",
    "page_type": "comparison_article",
    "mandatory_angle": "сравнивать только подтверждённые характеристики и реальные товары проекта"
  }
]
```

Путь: `seo/knowledge/review-cluster-seeds.json`.
Если файла нет, `review-cluster-plan.py` строит generic seeds из реального inventory.

## Что нельзя делать

- Не хранить `.env`, cookies, OAuth tokens, API keys и application passwords в wiki.
- Не читать `seo/research/raw/**` в контекст без необходимости.
- Не использовать API catalog как разрешение на подключение API.
- Не создавать comparison/review pages без реальных товаров/категорий и source-backed facts.
- Не переписывать проиндексированные статьи без refresh brief и preflight.

## Graphify и zvec

Порядок принятия решений:

1. Wiki — источник правды.
2. Graphify — граф связей и communities поверх curated corpus.
3. zvec или SQLite FTS — быстрый локальный поиск по wiki/vector.

`graphify-refresh.sh` сначала пробует Antigravity CLI (`agy`) через OAuth, потом
Gemini CLI, затем API backend из env, затем local fallback. Если `graphify` не
установлен, команда не ломает upgrade: пишет `graphify-status.json` со статусом
`degraded` и next step.

## Контроль качества

Перед любой правкой или публикацией:

1. `wiki-refresh-all.sh`
2. `wiki-context-pack.py --topic "..."`
3. `wiki-preflight.py --draft ... --write`
4. `content-taste-gate.py ... --write`
5. профильный gate: `link-gate`, `draft-quality-gate`, `page-outline-quality`, `pre-publish-gate`
6. `wiki-decision-log.py` после решения или публикации

Если gate не проходит, исправляется только конкретный слой. После пяти неудачных
попыток автоматический сценарий должен остановиться и записать blocker, а не
уходить в бесконечный цикл.
