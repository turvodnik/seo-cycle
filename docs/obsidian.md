# Obsidian vault integration

Opt-in слой поверх артефактов проекта: создаёт Obsidian vault как **зеркало** контента с wiki-links между сущностями, складскими позициями, статьями и категориями.

## Когда включать

| Тип проекта | Стоит ли включать |
|---|---|
| Ecommerce с >30 категорий или >20 брендов | ✅ Да — граф сущностей реально помогает видеть связи |
| Локальный бизнес мультилокация | ✅ Да — NAP-консистентность через граф |
| Маленький блог (<10 статей) | ⚠ Overhead не оправдан |
| Глобальный SaaS с <10 фич | ⚠ Overhead не оправдан |
| Любой проект с большим entities.yaml | ✅ Да — entities графически выраженный |

## Включение

В `seo-cycle.yaml`:
```yaml
obsidian:
  enabled: true
  vault_root: "./obsidian-vault"
  generate_links: true            # оборачивать в [[wiki-links]]
  dashboards: true                # Dataview-дашборды

stock_inventory:                  # для Stock-First правила
  enabled: true
  file: "./seo/stock-inventory.yaml"
  source: manual
```

Если `stock_inventory` ещё не создан — скопируй шаблон:
```bash
cp ~/.claude/skills/seo-cycle/scripts/stock-inventory.template.yaml \
   seo/stock-inventory.yaml
# Заполни реальными складскими позициями
```

## Первый запуск

```bash
python3 ~/.claude/skills/seo-cycle/scripts/obsidian-sync.py
```

Создаст vault со структурой:
```
obsidian-vault/
├── _README.md
├── _Dashboards/
│   ├── Stock.md             # бренды/категории на складе
│   ├── Pipeline.md          # состояние публикаций
│   └── Quality.md           # fact-check + NW scores
├── _Inbox/                  # для черновиков и заметок (пустое)
├── Entities/                # одна сущность = один .md
│   ├── Минеральная вата.md
│   ├── Технониколь.md
│   └── ...
├── Stock/                   # СКЛАДСКИЕ ПОЗИЦИИ (источник истины Stock-First)
│   ├── Brands/              # 🟢 primary | 🟡 secondary | ⚫ discontinued
│   ├── Categories/          # категории с указанием складских брендов
│   └── SKUs/                # отдельные товары (если ведёшь учёт)
├── Content/                 # КОПИИ user-facing контента
│   ├── Articles/            # статьи блога
│   ├── Categories/          # категории каталога
│   ├── Brands/              # страницы брендов
│   └── Pages/               # WP pages
├── Research/                # результаты исследований
│   ├── Perplexity/
│   ├── ATP/
│   └── LLM-CLI/
└── Cycles/                  # снапшоты SEO-циклов по фазам
    └── <topic>-<quarter>/
```

## Что даёт vault

### 1. Граф сущностей (Cmd+G в Obsidian)

Все сущности из `entities.yaml` и все упоминания в Entity Map/контенте связаны через `[[wiki-links]]`. Видно:
- Какие бренды связаны с какими категориями
- Какие материалы упоминаются в каких статьях
- Какие услуги релевантны каким локациям

Для Шестаковской методики «entity-first SEO» граф буквально визуализирует «тройки отношений».

### 2. Backlinks по каждой сущности

Открыл «Минеральная вата.md» → панель Backlinks справа показывает **все** места, где она упоминается:
- Статьи блога
- Категории каталога
- Entity Map'ы
- Research-документы

Это автоматический контроль внутренней перелинковки без отдельного инструмента.

### 3. Stock-First визуально

В `Stock/Brands/<Бренд>.md`:
- `🟢 на складе` — основной товар
- `🟡 secondary` — есть, но не приоритет
- `⚫ discontinued` — снято с производства

Везде, где упоминается «Технониколь» в контенте — wiki-link ведёт сюда. Сразу видно, нужно ли менять акцент в тексте (правило №10 stock-first из CLAUDE.md).

### 4. Dataview-дашборды

Открой `_Dashboards/Stock.md` (требует плагин Dataview):
- **Все бренды на складе** — таблица
- **Все категории и их складские бренды**
- **Discontinued / secondary** — для аудита

`_Dashboards/Pipeline.md`:
- Категории по статусу публикации
- Статьи: drafts vs published
- Entity Maps по статусу

`_Dashboards/Quality.md`:
- Страницы с устаревшим fact-check (>6 мес)
- Страницы без fact_check_log (нарушают правило №11)
- Низкий NW score (<65)

## Источник истины — НЕ vault

**Важно:** vault — **зеркало**, не source of truth. Источник:
- `entities.yaml` — реестр сущностей
- `stock-inventory.yaml` — складские позиции
- `categories/*.publish.md` — категории
- `blog/*.publish.md` — статьи

Vault обновляется по запросу:
```bash
python3 ~/.claude/skills/seo-cycle/scripts/obsidian-sync.py
```

Изменения вручную в vault **будут перезаписаны** при следующем sync (если ты их вручную не перенесёшь в исходники).

## Обновление vault

### После публикации новой статьи / категории
```bash
python3 ~/.claude/skills/seo-cycle/scripts/obsidian-sync.py
```

### После обновления stock-inventory.yaml
То же самое — пересинк подхватит изменения.

### Полная пересборка (если структура изменилась)
```bash
python3 ~/.claude/skills/seo-cycle/scripts/obsidian-sync.py --rebuild
```

### Dry-run (посмотреть что будет создано)
```bash
python3 ~/.claude/skills/seo-cycle/scripts/obsidian-sync.py --dry-run
```

### Без wiki-links (для просмотра «как есть»)
```bash
python3 ~/.claude/skills/seo-cycle/scripts/obsidian-sync.py --no-links
```

## Plugins в Obsidian

Минимум:
- **Dataview** — для дашбордов
- **Templater** — для шаблонов новых сущностей (опционально)
- **Excalidraw** — для визуализации архитектуры (опционально)

## Использование AI в vault

Два варианта:

### Базовый (без MCP) — Claude работает с файлами vault напрямую

- Read/Write/Edit/Grep — все стандартные тулы работают на файлах vault
- Источник истины — `entities.yaml`, `stock-inventory.yaml` (не vault!)
- Vault обновляется через `obsidian-sync.py` по запросу

### Продвинутый — Native MCP для Obsidian

Опциональный апгрейд через [obsidian-native-mcp](https://github.com/usrivastava92/obsidian-native-mcp) — даёт Claude:

- **Backlinks/outlinks** через `links.get` — мгновенно «где упоминается X»
- **Frontmatter queries** через `frontmatter.get` — программный аудит metadata
- **Surgical edits** через `str_replace` / `apply_patch` с hash precondition — точечные правки без полной перезаписи (соответствует Karpathy principle №3)
- **Heading/block/tag discovery** для умных вставок в нужное место документа
- **Batch operations с rollback** через `bulk.apply` — массовые обновления безопасно

Полный список тулов: `vault.list`, `vault.info`, `file.list`, `file.find`, `file.read`, `file.read_range`, `outline`, `heading.find`, `block.find`, `frontmatter.get`, `tags.list`, `links.get`, `metadata.read`, `search.content`, `str_replace`, `apply_patch`, `apply_edits`, `heading.replace_body`, `heading.rename`, `block.replace`, `block.rename`, `frontmatter.set`, `frontmatter.delete`, `lines.replace`, `lines.insert`, `file.create`, `file.replace`, `file.append`, `file.move`, `file.delete`, `bulk.apply`, `regex.replace`, `file.diff`.

#### Установка

**1. Obsidian-плагин** (для GUI работы с тем же MCP):
- Obsidian → Settings → Community Plugins → Browse → «Native MCP» → Install + Enable
- Default port: 9789, авторизация: startup-generated bearer token
- В Claude Desktop config: `"url": "http://127.0.0.1:9789/sse?token=<token>"`

**2. CLI binary** (для Claude Code и headless режима):
```bash
npm install -g obsidian-native-mcp

# Регистрация в Claude Code (stdio, без зависимости от запущенного Obsidian)
claude mcp add obsidian-native-mcp \
  --env "OBSIDIAN_VAULT_PATHS=/path/to/central/vault" \
  -- obsidian-native-mcp
```

После перезапуска Claude Code появятся тулы `mcp__obsidian-native-mcp__*`.

#### Когда использовать MCP-тулы vs прямую работу с файлами

| Сценарий | Подход |
|---|---|
| Массовая генерация (sync 168 файлов) | **Прямые файлы** (`obsidian-sync.py`) — быстрее |
| Surgical patch в одном файле | **MCP `str_replace`** — точнее и безопаснее |
| «Где упоминается [[бренд X]]?» | **MCP `links.get`** — мгновенно |
| «Все entity-maps без fact_check_log» | **MCP `frontmatter.get`** + `file.find` |
| Чтение source yaml (`entities.yaml`) | **Прямой Read** — yaml вне vault |
| Аудит контента vault | **MCP `search.content`** — индексированный поиск |
| Обновить 76 категорий разом | **MCP `bulk.apply`** с rollback |

LLM-агностично: skill `seo-cycle` работает в **обоих** режимах — если MCP не подключён, fallback на прямые файловые операции через стандартные тулы.

## Workflow примера: добавление нового бренда

1. **Источник:** добавь запись в `seo/stock-inventory.yaml`:
   ```yaml
   brands:
     - slug: new-brand
       name_user_facing: "Новый Бренд"
       role: primary
       categories: [...]
   ```

2. **Sync:**
   ```bash
   python3 ~/.claude/skills/seo-cycle/scripts/obsidian-sync.py
   ```

3. **Результат в vault:**
   - `Stock/Brands/Новый Бренд.md` — карточка бренда с зелёной плашкой 🟢 на складе
   - В `Stock/Categories/<категория>.md` появляется ссылка на новый бренд
   - В будущих статьях упоминание «Новый Бренд» автоматически становится `[[Новый Бренд]]`

4. **Применение в контенте:** Phase 6 (Writing) скилла seo-cycle прочитает `stock-inventory.yaml` и поставит новый бренд primary в текстах соответствующих категорий.

## Troubleshooting

**Vault не создался** — проверь что `obsidian.enabled: true` и путь `vault_root` доступен для записи.

**Wiki-links не появились** — проверь что `generate_links: true` и что в `entities.yaml` есть записи с `name`. Короткие имена (<4 символов) пропускаются для избежания шума.

**Dataview-дашборды пустые** — установи плагин Dataview в Obsidian (Settings → Community plugins).

**Конфликт с существующим vault** — переименуй или используй `--rebuild` для полной пересборки.

**Slow sync на больших проектах** — wiki-link wrapping проходит по каждому файлу. Для разовых обновлений включай `--no-links`, для полной — оставляй links.
