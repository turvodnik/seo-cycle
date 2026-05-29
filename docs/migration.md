# Миграция с `emwoody-seo-cycle` на универсальный `seo-cycle`

Этот документ описывает, как мигрировать проект emwoody (и другие, у которых уже есть проектный SEO-цикл скилл) на универсальный `seo-cycle` без поломки текущего workflow.

## Стратегия миграции — поэтапная

**Не нужно ломать emwoody-seo-cycle сразу.** Универсальный `seo-cycle` рассчитан на параллельное существование с проектными скиллами. Идём пошагово:

### Этап 1. Установка конфига (5 мин)

```bash
cd /Users/turvodnik/AI/emwoody
cp ~/.claude/skills/seo-cycle/config/project.template.yaml seo-cycle.yaml
```

Заполнить значениями emwoody (см. готовый пример ниже).

### Этап 2. Валидация и подключение

```bash
python3 ~/.claude/skills/seo-cycle/scripts/validate-config.py
```

Закрыть `[ ]` пункты чек-листа.

### Этап 3. Тест-запуск универсального скилла рядом с проектным

При вопросах типа «запусти SEO-цикл для X» Клод может выбрать **либо** `emwoody-seo-cycle`, **либо** новый `seo-cycle`. Оба скилла видны.

Различия:
- `emwoody-seo-cycle` — заточен под emwoody, знает контекст из коробки, не требует конфига
- `seo-cycle` — универсальный, читает `seo-cycle.yaml`

Выбор зависит от формулировки. «Полное продвижение emwoody» → проектный. «Универсальный SEO под мой проект» → универсальный.

### Этап 4. Постепенное переключение

По мере того как универсальный скилл закрывает функционал — обновляй `seo-cycle.yaml` и переключайся на него для новых тем. `emwoody-seo-cycle` оставляешь как **проектную обёртку** (делает то же, но с emwoody-defaults без необходимости каждый раз парсить yaml).

### Этап 5. Когда удалять проектный

`emwoody-seo-cycle` можно удалить когда:
- Все его кастомные правила перенесены в `seo-cycle.yaml`
- Все его уникальные lessons learned записаны в `CLAUDE.md` проекта
- Универсальный `seo-cycle` отрабатывает все фазы без замечаний

**Но это не обязательно.** Проектный скилл — это **сахар** поверх универсального (как `git lol` поверх `git log`). Если удобнее — оставляй.

## Готовый `seo-cycle.yaml` для emwoody

```yaml
# ============================================================================
# seo-cycle.yaml для emwoody.ru
# ============================================================================

project:
  name: "Эмвуди"
  domain: "emwoody.ru"
  brand_name_user_facing: "Эмвуди"
  brand_name_technical: "emwoody"
  description: |
    Интернет-магазин стройматериалов: ОСП, ДВП, теплоизоляция, минеральная
    вата, строительные смеси, герметики. Склад в Мытищах, доставка по
    Москве и Московской области. Сегменты: частные клиенты, мастера,
    бригады, опт и розница.

locale:
  language: ru
  country: RU
  region: "Москва и Московская область"
  city: "Москва"
  locale_iso: ru-RU
  yandex_region_code: 213
  google_gl: ru
  google_hl: ru
  timezone: "Europe/Moscow"

engines:
  - name: yandex
    priority: 1
  - name: google
    priority: 2

project_type: ecommerce
cms: wordpress

business_model:
  - retail
  - wholesale

sales_channels:
  - online
  - offline_warehouse

target_audiences:
  - private_customers
  - construction_crews
  - wholesale_buyers

industry:
  name: "Building Materials"
  tags: [construction, b2c, b2b]
  primary_categories:
    - "Минеральная вата"
    - "ОСП и ДВП"
    - "Плиточный клей"
    - "Герметики"
    - "Пароизоляция и гидроизоляция"
    - "Шумоизоляция"
  homepage_h1: |
    Строительные материалы оптом и в розницу с доставкой по Москве и Московской области

tone:
  formal_level: 2
  style_keywords: [factual, concrete, local]
  avoid_epithets: true
  avoid_marketing_fluff: true
  stop_words_extra:
    # Пополнять по обнаружениям детектора
    - "400+"     # без подтверждения
  description: |
    Деловой, конкретный, без маркетинговой воды. Только факты:
    что есть, сколько стоит, как быстро, кому подходит.

sources:
  yandex_wordstat:
    enabled: true
    method: agent
    delegate_to: yandex-seo-specialist
  yandex_wordstat_deep:
    enabled: true
    method: browser_mcp
  yandex_suggest:
    enabled: true
    script: ~/.claude/skills/seo-cycle/scripts/yandex-suggest.py
  yandex_serp_blocks:
    enabled: true
    method: browser_mcp
  yandex_webmaster_history:
    enabled: false   # включить после верификации в Я.Вебмастере
    method: browser_mcp
  yandex_images_suggest:
    enabled: true
    method: browser_mcp
  yandex_business_maps:
    enabled: true    # для склада в Мытищах
    method: browser_mcp
  yandex_q:
    enabled: true
    method: browser_mcp

  google_search_console:
    enabled: true
    delegate_to: "claude-seo:seo-google"
    min_days_after_publish: 30
  google_trends:
    enabled: true
    script: ~/.claude/skills/seo-cycle/scripts/google-trends.py
  google_suggest:
    enabled: true
    script: ~/.claude/skills/seo-cycle/scripts/google-suggest.py
  dataforseo:
    enabled: false

  neuronwriter:
    enabled: true
    api_key_env: NEURON_API_KEY
    project_id: "a365f12af3967c5d"
    engine: google.ru
    target_score: 65
    helper_script: "./seo/scripts/nw.sh"

  llm_cli:
    antigravity:
      enabled: true
      cmd: agy
    codex:
      enabled: true
      cmd: codex
    parallel_collect_script: ~/.claude/skills/seo-cycle/scripts/llm-cli-collect.sh
    merge_script: ~/.claude/skills/seo-cycle/scripts/llm-cli-merge.py

  answerthepublic:
    enabled: true
    api_key_env: TOKEN_ANSWERTHEPUBLIC
    default_lang: en
    default_region: us
    default_provider: gweb

  perplexity:
    enabled: true
    method: browser_mcp
    setup_doc: "./seo/research/perplexity/SETUP.md"
    prompts_dir: "./seo/research/perplexity/prompts/"

publishing:
  enabled: true
  cms: wordpress
  env_vars:
    base_url: WP_BASE_URL
    user: WP_USER
    app_password: WP_APP_PASSWORD
    woo_rest_key: WOO_REST_API_KEY
    woo_rest_secret: WOO_REST_API_SECRET
  post_types:
    blog: blog
    catalog_categories: product_cat
    brands: product_brand
    static_pages: page
  acf_fields:
    h1: h1_title_category_product
    description: product_category_description
    faq: faq_product_category
    cta: cta_text_category_product
  seo_plugin: seopress
  seopress_term_meta_via_rest: true
  publish_skills:
    blog: emwoody-publish-post
    category: emwoody-publish-taxonomy
    brand: emwoody-publish-taxonomy
    page: emwoody-publish-page

images:
  generator: codex_cli
  generator_script: "./seo/scripts/publish/img-generate.sh"
  optimize_script: "./seo/scripts/publish/img-optimize.sh"
  output_format: webp
  aspect_ratios:
    hero: "4:3"
    icon: "1:1"
    og: "1.91:1"
    article_inline: "16:9"
  brand_palette:
    primary: forest_green
    secondary: kraft_beige
    accent: mustard
    tertiary: [terracotta, dusty_teal, cream]
    avoid: [bright_red, neon_blue, neon_green, pastel_washed_out]
  alt_text_pattern: "{category_name} — {city} | {brand_name}"

content_rules:
  stock_first:
    enabled: true
    stocked_skus_source: "manual"
  fact_check:
    enabled: true
    required_for: [technical_specs, norms, brands, prices, claims]
    max_age_months: 6
    workflow_doc: "./seo/research/perplexity/prompts/fact-check.md"
    results_dir: "./seo/research/perplexity/results"
  local_signals:
    min_per_page: 3
    examples: ["Москва", "Московская область", "Мытищи"]
  internal_linking:
    min_links_per_article: 5
    require_category_links: true
  aeo:
    enabled: true
    answer_first_sentences: 3
    faq_required: true

quality_gates:
  stop_words_check:
    enabled: true
    script: ~/.claude/skills/seo-cycle/scripts/check-stop-words.py
    fail_on_match: true
  neuronwriter_score:
    enabled: true
    min_score: 65
  fact_check_log_present:
    enabled: true
  word_count_min:
    enabled: true
    blog_post: 1500
    category: 800
    landing: 1200

artifacts:
  cycles_root: "./seo/cycles"
  entities_root: "./seo/entities"
  research_root: "./seo/research"
  drafts_root: "./blog"
  categories_root: "./categories"
  publish_log: "./seo/publish-log.csv"

context_files:
  - path: "./CLAUDE.md"
    role: "project rules"
  - path: "./emwoody-seo-geo-ux-package-2026-04-23.md"
    role: "base SEO/GEO/UX package"

delegate:
  semantic_brief: emwoody-semantic-brief
  audit: seo-auditor
  keyword_research: seo-keyword-researcher
  content_writer: seo-content-writer
  content_strategy: seo-content-strategist
  yandex_specialist: yandex-seo-specialist
  link_building: seo-linkbuilder
  google_data: "claude-seo:seo-google"
  schema_markup: "claude-seo:seo-schema"
  cluster_analysis: "claude-seo:seo-cluster"
  technical_audit: "claude-seo:seo-technical"
```

## Что делать с проектными скиллами после миграции

| Проектный скилл | Действие | Причина |
|---|---|---|
| `emwoody-seo-cycle` | **Оставить** | Как сахар: запускает универсальный с emwoody-context |
| `emwoody-semantic-brief` | **Оставить** | Делегируется через `delegate.semantic_brief` |
| `emwoody-publish-taxonomy` | **Оставить** | CMS-специфичный, делегируется через `publishing.publish_skills.category` |
| `emwoody-publish-post` | **Оставить** | То же |
| `emwoody-publish-page` | **Оставить** | То же |

Все они становятся **подчинёнными** универсального оркестратора. Универсальный знает _что_ делать, проектные — _как_ для emwoody.

## Что переносить в универсальный скилл (PR upstream)

Если в emwoody-скиллах накопился полезный универсальный код:

- ✅ Stop-words detector с морфологией → перенесён (`check-stop-words.py`)
- ✅ ATP клиент с обходом Cloudflare → перенесён
- ✅ LLM CLI parallel collect → перенесён
- ✅ Yandex / Google Suggest → перенесены
- ⏳ NeuronWriter helper wrapper → можно перенести (`scripts/nw.sh` сейчас в emwoody)
- ⏳ Universal image gen wrapper → можно перенести (codex CLI + WebP optimization)
- ⏳ WordPress publish helper — оставить в emwoody, очень специфичен под Bricks/ACF/SEOPress

## Проверка миграции

1. `python3 ~/.claude/skills/seo-cycle/scripts/validate-config.py` → 0 errors
2. Запустить мелкий цикл («покажи фазы для категории X в режиме dry-run»)
3. Проверить, что артефакты сохраняются в `seo/cycles/` правильно
4. Проверить, что quality gates срабатывают на тестовом тексте с эпитетами
5. Если всё ок — `emwoody-seo-cycle` можно опционально упростить (сделать тонкой обёрткой над универсальным)
