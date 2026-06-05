# Адаптация seo-cycle под конкретный проект

Скилл `seo-cycle` универсальный — один и тот же фреймворк работает для интернет-магазина в РФ, англоязычного блога, локального бизнеса в Европе или глобального SaaS. Адаптация — через `seo-cycle.yaml` проекта и (опционально) через проектные субскиллы.

## Уровни адаптации

### Уровень 1 — только конфиг (90% случаев)

Большинство адаптаций решается заполнением `seo-cycle.yaml`. См. `INSTALL.md`.

### Уровень 2 — переопределение промптов

Если стандартные промпт-шаблоны (`~/.codex/skills/seo-cycle/prompts/`) не подходят под нишу, скопируй их в проект и переопредели:

```bash
mkdir -p <project>/seo/prompts
cp ~/.codex/skills/seo-cycle/prompts/*.md <project>/seo/prompts/
# Отредактируй под свою нишу
```

В `seo-cycle.yaml`:
```yaml
sources:
  perplexity:
    prompts_dir: "./seo/prompts/"   # вместо ~/.codex/skills/seo-cycle/prompts/
```

### Уровень 3 — проектные субскиллы

Если у проекта **специфичная инфраструктура** (custom CMS, особый формат публикации, уникальный pipeline картинок) — создавай **проектные субскиллы** в `<project>/.claude/skills/<name>/` и прописывай в `delegate.*`.

Пример (emwoody):
```
<project>/.claude/skills/
├── emwoody-semantic-brief/        # entity-first SEO специально под emwoody
├── emwoody-publish-taxonomy/      # публикация product_cat + product_brand
├── emwoody-publish-post/          # публикация статей блога с lightbox
└── emwoody-publish-page/          # публикация WP pages с ACF
```

В `seo-cycle.yaml`:
```yaml
delegate:
  semantic_brief: emwoody-semantic-brief
  publish_skills:
    blog: emwoody-publish-post
    category: emwoody-publish-taxonomy
```

### Уровень 4 — расширение универсального скилла (PR upstream)

Если решение полезно для **многих проектов** (новый источник данных, новый CMS-публикатор):

1. Реализуй и протестируй в своём проекте
2. Перенеси в `~/.codex/skills/seo-cycle/` с правкой документации
3. Добавь в `config/project.template.yaml` секцию опций
4. Обнови `SKILL.md` Phase где применяется
5. (Если у тебя git-репо для skills) — PR upstream

## Адаптация по типам проектов

### Ecommerce (РФ или СНГ)

**Стандартный профиль emwoody.** Включить:
- `engines`: yandex + google
- `project_type: ecommerce`
- `cms: wordpress` (или shopify/opencart)
- Все Яндекс-источники (`yandex_*`)
- NeuronWriter с `engine: google.ru`
- `content_rules.stock_first: true`
- `content_rules.fact_check: true` (для технических ниш)
- `content_rules.local_signals.min_per_page: 3`

Отключить:
- AnswerThePublic для русских ключей (регион не поддерживается; используй для англоязычных шаблонов вопросов с переводом)

### Глобальный SaaS (английский)

```yaml
locale:
  language: en
  country: US
  region: "Global"
engines:
  - name: google
project_type: saas
cms: webflow                  # или nextjs / strapi
sources:
  # Удалить все yandex_*
  google_search_console:
    enabled: true
  answerthepublic:
    enabled: true
    default_region: us         # тут работает!
content_rules:
  stock_first:
    enabled: false             # не релевантно
  local_signals:
    min_per_page: 0
  fact_check:
    enabled: true              # для технического SaaS
```

### Локальный бизнес одного города

```yaml
locale:
  language: ru
  region: "Москва"
  yandex_region_code: 213
project_type: local_business
sources:
  yandex_business_maps:
    enabled: true              # критично!
  yandex_q:
    enabled: true
content_rules:
  local_signals:
    min_per_page: 5
    examples: ["Москва", "район Хамовники", "м. Парк культуры"]
  stock_first:
    enabled: false             # услуги — нет товаров
  fact_check:
    enabled: false             # для не-технических ниш
```

Дополнительно: на Phase 8 (schema) обязательно `LocalBusiness` + `Service` schema.

### Англоязычный блог / медиа

```yaml
locale:
  language: en
  country: GB
project_type: blog
cms: hugo                       # или astro / jekyll / wordpress
publishing:
  enabled: true
  cms: hugo
  # ...свой pipeline (git commit + redeploy)
sources:
  google_*: enabled: true
  answerthepublic:
    enabled: true              # отлично работает для en
content_rules:
  stock_first:
    enabled: false
  fact_check:
    enabled: true              # медицинский / финансовый — обязательно
```

### Мультирегиональный проект

Несколько `seo-cycle.yaml` в подпапках по локализациям:
```
project/
├── seo-cycle.yaml              # дефолт (если есть)
├── ru/
│   └── seo-cycle.yaml          # русская версия — Яндекс приоритет
├── en-us/
│   └── seo-cycle.yaml          # US — Google only
└── de/
    └── seo-cycle.yaml          # Германия — Google + локальные источники
```

Запуск скилла из подпапки автоматически подхватит свой конфиг.

## Расширение источников данных

Если в твоей нише есть специфичный источник (Я.Маркет, eBay seller analytics, Amazon Brand Analytics, Etsy trends) — добавляй в `sources` под своим ключом:

```yaml
sources:
  yandex_market_competitors:
    enabled: true
    method: manual              # browser_mcp | api | script
    note: "Ручной сбор данных конкурентов с Я.Маркета по карточкам товаров"
```

В Phase 2 при разборе источников скилл подхватит и попросит описать workflow для этого custom-источника.

## Расширение content_rules

Под специфичные ниши могут понадобиться доп. правила:

```yaml
content_rules:
  # Стандартные
  stock_first: ...
  fact_check: ...
  
  # Custom — медицинская тематика
  medical_disclaimer_required: true
  consult_doctor_phrase: "Перед применением проконсультируйтесь со специалистом"
  
  # Custom — финансы (РФ)
  finance_disclaimer_required: true
  not_investment_advice: true
  
  # Custom — детский контент
  age_restriction: "0+"
  no_violence: true
```

Эти правила можешь обрабатывать в **проектных субскиллах** (Phase 6 writing / Phase 7 publishing).

## Отладка адаптации

После изменения конфига:

```bash
# Перевалидировать
python3 ~/.codex/skills/seo-cycle/scripts/validate-config.py

# Запустить dry-run на одной фазе
# (просто скажи Клоду: «запусти Phase 2 для темы X в режиме dry-run»)

# Проверить какие источники активны для текущего проекта
python3 -c "
import yaml
cfg = yaml.safe_load(open('seo-cycle.yaml'))
print('Engines:', [e['name'] for e in cfg.get('engines', [])])
print('Active sources:')
for name, src in cfg.get('sources', {}).items():
    if isinstance(src, dict):
        if src.get('enabled'):
            print(f'  ✓ {name}')
        else:
            for sub_name, sub in src.items():
                if isinstance(sub, dict) and sub.get('enabled'):
                    print(f'  ✓ {name}.{sub_name}')
"
```

## Что НЕ адаптируется через конфиг (требует кода)

- Парсинг новых форматов CMS (нужен новый publish-script)
- Новые типы schema beyond JSON-LD стандарта (нужен schema generator)
- Кастомные KPI / dashboard (нужен monitoring script)
- LLM-провайдеры за пределами Antigravity/Codex/Perplexity (нужен новый source script)

Если упёрся в это — см. уровень 3 (проектные субскиллы) и уровень 4 (PR upstream).
