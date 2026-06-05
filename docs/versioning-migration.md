# Versioning & Upgrade Guide

Как обновить существующий проект (v1.0) до новых версий скилла без поломки текущего workflow.

## Принципы

1. **Все новые поля конфига — опциональны** (`enabled: false` по умолчанию)
2. **Новые скрипты не заменяют старые** — добавляются параллельно
3. **Изменения в SKILL.md** — additive (новые секции, не rewrites)
4. **Breaking changes** — только в major version (v2.0+) с migration guide

## Текущая версия: v1.1 (2026-05-27)

См. `CHANGELOG.md` для полного списка изменений.

## Upgrade v1.0 → v1.1

### Минимальный upgrade (5 минут)

Ничего не делать. v1.0 проекты продолжают работать с скиллом v1.1 без правок. Все новые фичи (Phase 9 snapshot pipeline, Phase 10 triggers engine, OAuth fetchers) — opt-in.

### Рекомендованный upgrade (30 минут)

Включить новые фичи постепенно.

#### Шаг 1. Прогон валидатора

```bash
cd <project-root>
python3 ~/.codex/skills/seo-cycle/scripts/validate-config.py
```

Если 0 errors — конфиг совместим. Прочти warnings и new checklist items (новые поля env vars для observability hub).

#### Шаг 2. Включить snapshot pipeline (Phase 9)

В `seo-cycle.yaml` добавь секцию (если нет):

```yaml
monitoring:
  cadence: "2 weeks"
  snapshot_format: json
  retention_months: 12
  pagespeed_insights:
    enabled: false                          # включи когда настроишь PSI API
```

Тестовый прогон:
```bash
# Создай пустой snapshot для проверки
mkdir -p 09-monitoring
echo '{"snapshot_date":"2026-05-27","queries":[],"pages":[]}' > 09-monitoring/test.json
python3 ~/.codex/skills/seo-cycle/scripts/triggers-eval.py 09-monitoring/test.json --output test-iterations.md
cat test-iterations.md
```

#### Шаг 3. Подключить аналитику (опционально)

Если хочешь использовать прямые API вызовы (вместо `claude-seo:seo-google` делегата):

1. Пройти `docs/oauth-setup.md`
2. Скопировать `.env.example` → `.env`, заполнить
3. Прогнать smoke test:
   ```bash
   python3 ~/.codex/skills/seo-cycle/scripts/psi-fetch.py https://yoursite.com
   python3 ~/.codex/skills/seo-cycle/scripts/gsc-fetch.py --days 7 --row-limit 10
   ```

#### Шаг 4. Добавить новые секции конфига (по мере необходимости)

```yaml
# Stock-first (для ecommerce)
stock_inventory:
  enabled: true
  file: "./seo/stock-inventory.yaml"
  source: manual

# E-E-A-T (для YMYL)
eeat:
  enabled: true
  author_bio_required: true

# Backlinks (когда есть данные)
backlinks:
  enabled: true
  source: manual
  file: "./backlinks.csv"

# Programmatic SEO (для каталогов)
mode: programmatic   # либо standard | migration

# Migration (только если планируется смена домена/CMS)
mode: migration
migration:
  enabled: true
  old_domain: ...
  new_domain: ...
```

#### Шаг 5. (Опционально) Использовать новые скрипты

| Скрипт | Когда |
|---|---|
| `nw-cli.sh` | Universal NW wrapper (если раньше был проектный nw.sh) |
| `validate-entities.py` | Регулярная проверка реестра сущностей |
| `programmatic-template-gen.py` | Массовая генерация страниц |
| `schema-validate.py` | Перед публикацией с JSON-LD |
| `google-trends.py` | Сезонные данные (требует `pip3 install pytrends`) |
| `init-project.sh` | Для **нового** проекта (не для существующего) |

### Полный upgrade (2 часа)

Для проектов, которые активно используют скилл и хотят все новые фичи.

1. Минимальный + Рекомендованный upgrade (см. выше)
2. Прочитай новые docs:
   - `docs/oauth-setup.md` — единая API настройка
   - `docs/migration-planner.md` — если планируется миграция
   - `docs/eeat-audit.md` — для YMYL контента
   - `docs/backlink-research.md` — workflow для backlinks
   - `docs/sxo-quality-gates.md` — расширение quality gates
   - `docs/international-seo.md` — для мультирегион
   - `docs/image-seo.md`, `docs/video-seo.md` — оптимизация медиа
   - `docs/troubleshooting.md` — FAQ
3. Скопируй custom triggers (если нужны) в `<project>/seo-triggers.yaml`:
   ```bash
   cp ~/.codex/skills/seo-cycle/config/triggers.yaml seo-triggers.yaml
   # Отредактируй под свой проект
   ```
   Указать в `monitoring.triggers_file: "./seo-triggers.yaml"`.

## Откат

Если что-то ломается:

1. Все новые секции конфига можно убрать или поставить `enabled: false` — поведение откатится к v1.0
2. Старые скрипты не тронуты — работают как раньше
3. Если проблема в новом fetcher — используй делегат `claude-seo:seo-google` вместо

## Будущие версии — guidelines

### v1.x (minor) — back-compat гарантируется

- Новые опц. секции конфига
- Новые скрипты в `scripts/`
- Новые docs
- Расширение шаблонов (новые поля frontmatter)

### v2.0 (major) — может быть breaking

Что **может** измениться:
- Schema конфига (новый required field)
- Default behavior (например, fact-check включён по умолчанию)
- Перемещение скриптов / шаблонов

Каждый major release будет иметь свой `docs/upgrade-vX.X-to-vY.Y.md` с пошаговым migration plan.

## Чеклист после upgrade

- [ ] `validate-config.py` → 0 errors
- [ ] Существующие cycles в `seo/cycles/` нечитаемы валидатором (старая структура совместима)
- [ ] Проектные суб-скиллы (если есть) работают (emwoody-publish-*)
- [ ] Smoke test нового fetcher если подключён
- [ ] Документация в `<project>/CLAUDE.md` отражает upgrade (опционально)
