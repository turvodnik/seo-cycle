# Changelog — seo-cycle

## [1.22.0] — 2026-06-05

### Low-token task router

- Added `scripts/task-router.py` to classify a concrete SEO/marketing task and produce a compact execution route: phases, sources, approval gates, blocked actions, automation recommendation, and context/token caps.
- The router is read-only by default and writes `seo/setup/latest-task-route.md/json` plus archived per-task routes only with `--write`.
- `setup-control-plane.py` now accepts `--task` and includes the latest task route in the readiness report, so first-run setup and handoffs start from a bounded execution plan.
- Project templates, validation, governance report, init wizard, README, INSTALL, GUIDE, SKILL.md, and Codex runtime docs now include the task route as part of the standard low-token workflow.

## [1.21.0] — 2026-06-04

### Setup control plane

- Added `scripts/setup-control-plane.py` as the single low-token first-run surface for intake, profile, source resolution, governance, validation, and automation readiness.
- `--write` refreshes safe generated artifacts and writes `seo/setup/setup-control-plane.md`, `setup-control-plane.json`, `latest-validation.txt`, `latest-governance.json`, and `latest-sources.json`.
- `--apply-profile` remains an explicit opt-in for applying generated profile changes to `seo-cycle.yaml` with backup.
- `init-project.sh` now creates the setup control-plane report after intake/profile generation, so every new project starts with a compact readiness report and next-action checklist.
- README, INSTALL, GUIDE, SKILL.md, and Codex runtime docs now include the setup control-plane command as the default post-init review step.

## [1.20.0] — 2026-06-04

### Detailed project intake wizard

- Added `scripts/project-intake-wizard.py` to create/refine `seo/project-intake.yaml` from `seo-cycle.yaml` in `--defaults` mode or through a detailed `--interactive` wizard.
- The wizard covers project type, business model, sales channels, priority products/services, audiences, conversion goals, countries, regions, languages, search engines, local platforms, marketing channels, paid ads policy, analytics tracking policy, guarded tools, AI visibility platforms, governance, automation mode, cache-first, and distillate requirements.
- `init-project.sh` now asks whether to run the detailed intake wizard; otherwise it auto-fills intake defaults from the generated `seo-cycle.yaml`.
- The setup now writes `seo/project-intake-report.md` before generating `seo/project-profile.generated.yaml` and `seo/project-profile-report.md`.
- `init-project.sh` now offers an explicit opt-in to apply the generated project profile to the fresh `seo-cycle.yaml` immediately, with the normal backup behavior.
- README, INSTALL, GUIDE, SKILL.md, and Codex runtime docs now route new-project setup through `project-intake-wizard.py` before `project-profile.py`.

## [1.19.0] — 2026-06-04

### Project profile overlay and intake applier

- Added `scripts/project-profile.py` to read `seo/project-intake.yaml` and generate project-specific engines, region profile, source overrides, marketing decisions, and governance recommendations.
- Default mode writes `seo/project-profile.generated.yaml` and `seo/project-profile-report.md`; `--apply` updates `seo-cycle.yaml` only after explicit review and creates a timestamped backup.
- `init-project.sh` now generates the initial project profile report/overlay after creating policy templates.
- `policy_files` now includes `project_profile`, and governance/Codex docs mention the generated overlay.
- Codex entrypoint and SKILL.md now route detailed per-project setup through `project-profile.py --write` before optional `--apply`.
- `docs/oauth-setup.md` now covers the broader access matrix from the setup work: Google NLP/Merchant/Business/YouTube, Bing Webmaster/IndexNow/Places, Yandex Merchant/Direct, and RF tracking-tag restrictions.

## [1.18.0] — 2026-06-04

### Safe scheduled automation planner

- Added `scripts/automation-plan.py` to generate `seo/automations/automation-plan.md`, `automation-plan.json`, `crontab.txt`, and launchd plist templates from `seo-cycle.yaml` + `seo/automation-policy.yaml`.
- Schedule installation is blocked unless both governance and automation policy set `create_schedules: true`, and `SEO_CYCLE_ALLOW_SCHEDULE_INSTALL=1` is present.
- Monthly automation now references the planner script and output directory in `config/project.template.yaml`.
- `init-project.sh` next steps now include safe automation-plan generation after governance report.
- `validate-config.py` now reminds projects with enabled schedule creation to generate/review schedule artifacts.
- Codex runtime docs and SKILL.md now require `automation-plan.py --write --include-disabled` before any real scheduled automation.

## [1.17.9] — 2026-06-04

### Token, budget, subscription, and automation governance

- Added `governance` to `config/project.template.yaml`: token policy, cache-first rules, monthly paid API/LLM caps, subscription caps, and automation approval gates.
- Added project-local policy templates: `seo/tool-budget.yaml`, `seo/automation-policy.yaml`, and `seo/project-intake.yaml`.
- Added `scripts/governance-report.py` to print active token/budget/tool/automation policy without exposing secrets.
- `init-project.sh` now asks for governance profile, paid API budget, LLM budget, automation mode, and schedule creation before image workflow questions.
- `validate-config.py` now checks governance sanity: raw data in context, cache-first, oversized phase context, active paid sources with zero budget, invalid automation modes, and missing automation policy.
- SKILL.md, Codex runtime docs, and Codex entrypoint now require governance report before expensive collection, browser work, publishing, or scheduled automations.

## [1.17.8] — 2026-06-04

### Project policy intake for paid/API SEO tools

- SKILL.md: `seo-cycle` now checks project-local policy files before phase selection, API calls, credit spend, indexing changes, or analytics/tracking changes.
- Added local contracts for `seo/neuronwriter-limits.yaml`, `seo/neuronwriter.md`, `seo/entities/google-nlp-policy.yaml`, `seo/seo-data-collection-map.md`, and `seo/access-setup-runbook.md`.
- NeuronWriter is treated as the primary SERP/NLP content editor when configured; Google Cloud Natural Language is treated only as a guarded technical entity audit layer with cache/unit caps.
- Added `scripts/google-nlp-audit.py` with project-local `.env` loading, policy defaults, cache, dry-run mode, and monthly unit guards.
- `install-codex.sh` now installs the Codex-first entrypoint skill via `~/.codex/skills/codex-primary-runtime` and includes `beautifulsoup4`/`google-auth` dependencies.
- `init-project.sh` now creates project `AGENTS.md` and policy templates for NeuronWriter, Google NLP, data access, setup runbooks, and AI visibility prompts.
- `validate-config.py` now checks policy-file presence and warns when NeuronWriter/Google NLP are configured without local guard files.
- Added source/env scaffolding for Bing Webmaster, IndexNow, Bing Places, Google Merchant/Business Profile/YouTube, Yandex Merchant, and Ads accounts as approval-only data sources.
- Added RF-site tracking guard: do not add foreign analytics/tracking tags or pixels without explicit project-policy approval.
- Added robots/Content-Signal policy handling: `search=yes, ai-input=yes, ai-train=no` is allowed as a training opt-out, while public `robots.txt` must be clean text without PHP warnings/HTML.
- `docs/codex-runtime.md` and GUIDE.md RU+EN now document the same Codex policy intake flow.

## [1.17.7] — 2026-06-02

### Configurable photo pipeline

- Добавлен штатный инструмент `scripts/wp-photo-image.py`: локальное фото/URL → crop по `images.aspect_ratios.*` → WebP → WordPress upload через SSH/WP-CLI → alt/caption/featured.
- `config/project.template.yaml`: секция `images` расширена до photo-first workflow с `tool`, `source_policy`, `visual_style`, `output`, `captions`, `alt`, `lazy_loading`, `upload` и `inline_min_per_post`.
- `scripts/init-project.sh`: wizard для нового проекта теперь спрашивает пропорции featured/inline, WebP width/quality, источник фото, visual style, минимум inline-картинок, caption policy и разрешение видимого текста.
- `validate-config.py` проверяет `images.*`: наличие tool scripts, featured/inline ratios и SSH/WP-CLI env для WordPress upload.
- Установочные инструкции и `install-codex.sh` теперь добавляют `pillow`, нужный для crop/WebP.
- GUIDE.md RU+EN и SKILL.md обновлены: image workflow теперь config-driven, `wp-photo-image.py` закреплён как основной photo-first инструмент.

## [1.17.6] — 2026-06-02

### WordPress REST publishing fallback

- SKILL.md: Phase 7 теперь фиксирует WordPress REST API + Application Password как основной независимый канал публикации.
- MCP/`emwoody-publish-*` остаются удобным интерфейсом, но не единственной точкой отказа.
- SSH/WP-CLI закреплён как fallback для backup, cache purge, REST meta limitations и серверных исправлений.
- GUIDE.md RU+EN обновлён в таблице фаз.

## [1.17.5] — 2026-06-02

### Scope для `skip-lazy`

- SKILL.md и GUIDE.md RU+EN: `skip-lazy`/`data-no-lazy` применяется только к первому или above-the-fold inline image, если оптимизатор показывает плейсхолдер.
- Inline images ниже первого экрана должны оставаться lazy-loaded, чтобы не раздувать начальную загрузку страницы.

## [1.17.4] — 2026-06-02

### Проверка lazy-load плейсхолдеров

- SKILL.md: Phase 7 verify теперь требует не только GET/HTML, но и браузерную проверку inline images после публикации.
- GUIDE.md RU+EN: lazy-load плейсхолдер вместо реального inline-фото считается blocker/exception.
- Зафиксирован способ исправления для критичных inline images: исключение из lazy-load через `skip-lazy`/`data-no-lazy` или CMS-аналог с повторным screenshot-check.

## [1.17.3] — 2026-06-02

### Визуальный gate для inline images

- SKILL.md: image QA теперь требует чистые тематические фото/визуалы в стиле проекта, без видимого SEO/AEO/GEO текста, схем, товарных описаний и каталоговых дисклеймеров на изображении.
- GUIDE.md RU+EN: зафиксировано, что inline images должны иметь естественный `alt` и короткий редакционный caption; товарные карточки/коллажи не используются как основной визуал без явного запроса.
- Публичная проверка теперь блокирует запрещённые тексты на/под изображениями и inline images без caption.

## [1.17.2] — 2026-06-02

### Обязательный alt-gate для изображений

- SKILL.md: добавлен Image alt check в Phase 6 QA и публичная проверка `<img>` без `alt` в Phase 7 Publishing.
- GUIDE.md RU+EN: зафиксировано, что featured, inline, OG/schema и product/category visuals должны иметь естественный alt без переспама ключами.
- Изображение без alt теперь считается publication blocker/exception, а не мелкой рекомендацией.

## [1.17.1] — 2026-06-02

### Обязательный evidence-gate для семантики, сущностей и фактчекинга

- SKILL.md: Antigravity CLI и Perplexity Deep Research теперь обязательны для Phase 2 (семантика), Phase 4 (Entity Map) и Phase 6 (fact-check перед публикацией), если инструменты доступны.
- Если Antigravity/Perplexity недоступны технически, цикл должен записать blocker/exception в артефакт; нельзя выдавать сбор или проверку за полные.
- GUIDE.md RU+EN обновлен: добавлены правила сохранения raw-ответов на диск, использования только distilled artifacts в контексте и QA-цепочка `stop-words → Perplexity+Antigravity fact-check → NW≥65`.

## [1.17.0] — 2026-05-30

### Установка одной командой (Codex + Claude)

- **`install-codex.sh`** — `curl -sL .../install-codex.sh | bash`: идемпотентно клонирует/обновляет ядро `seo-cycle` (+ `seo-keywords`), ставит зависимости (pyyaml/requests), создаёт симлинк `~/.codex/skills/seo-cycle` для Codex, чинит `AGENTS.md`, печатает следующие шаги (init-project + AGENTS.md + .env + SEO_RUNTIME=codex).
- README: one-command установка в TL;DR.

## [1.16.0] — 2026-05-30

### Оптимизация расхода Keys.so (Professional-тариф)

- **Кэш TTL 30→60 дней** в `keyso-fetch.py` и `competitor-discovery.py` — повторный сбор темы в пределах 60д = 0 обращений к API (главная экономия лимита).
- **Usage-трекер** в `keyso-fetch.py` — счётчик реальных запросов за месяц в `seo/research/keyso/_usage.json` (cache-hit не считается); печатает расход в stderr.
- Секция `keyso` в конфиге расширена: `plan: professional`, `cache_ttl_days: 60`, `rate_limit`, `monthly_request_budget` (впиши лимит из кабинета для guard).
- Принципы экономии задокументированы (keyword-info — 1 запрос/ключ без batch; competitor-discovery агрегирует топы за немного запросов; крупный per_page = больше данных за проверку).
- GUIDE.md (RU+EN) — обновлены ячейки Keys.so.

## [1.15.0] — 2026-05-30

### Кластеризация в Keys.so через браузер (clustering API закрыт)

Keys.so clustering недоступен через API (только UI) — добавлена полуавтоматическая загрузка.
- **`scripts/keyso-clustering-export.py`** — детерминированная подготовка файла ключей (из keyso-кэша / CSV / markdown-таблицы / списка) → `.txt` по ключу на строку, дедуп, фильтр по частоте/лимиту. Дёшево, без браузера.
- **`prompts/keyso-clustering-upload.md`** — runbook браузерной загрузки (Chrome MCP / Codex browser): создать проект → file_upload → запустить → экспорт в `<cycle>/03-clusters-keyso.md`. С предупреждением о расходе токенов и критериями «когда оправдано» (большие ядра) vs «наша кластеризация дешевле» (малые/средние).
- GUIDE.md (RU+EN) — export-скрипт в таблицах.

## [1.14.0] — 2026-05-30

### keyso-save.py — сохранение конкурентов в кабинет Keys.so (write-API)

- **`scripts/keyso-save.py`** — `group-report`: сохраняет группу доменов (свой + конкуренты) в кабинет Keys.so через `POST /report/group` (рабочий write-эндпоинт). `--from-config` берёт домены из `business_profile.competitors`. Возвращает rid отчёта.
- Разведка write-API Keys.so: реально доступен только групповой отчёт; `clustering/my_projects/position-monitoring` через API отвечают "Method not allowed" (только UI). Поэтому **семантика и кластеризация хранятся у нас** (seo/cycles + seo.db + Obsidian), в Keys.so сохраняется групповой отчёт конкурентов.
- GUIDE.md (RU+EN) — keyso-save в таблицах.

## [1.13.0] — 2026-05-30

### competitor-discovery.py — поиск максимально похожих конкурентов

- **`scripts/competitor-discovery.py`** — находит прямых бизнес-конкурентов через агрегацию топа выдачи Яндекса по коммерческим seed-ключам (Keys.so `keyword_dashboard.top[]`), а не через `concurents` по домену (который врёт, если сайт ранжируется блогом). Ранжирует по числу ключей в топе + видимости, помечает/исключает гигантов (`--exclude-giants`). Кэш, троттлинг 10/10сек.
- Обкатано на emwoody: топ похожих — shop.tn.ru, strd.ru, tstn.ru, msk.saturn.net; занесены в `business_profile.competitors`.
- GUIDE.md (RU+EN) — в таблицах источников.

## [1.12.0] — 2026-05-30

### Keys.so — Яндекс/РФ источник данных

- **`scripts/keyso-fetch.py`** — клиент Keys.so API (header `X-Keyso-TOKEN`, лимит 10 req/10сек + 429-retry, кэш 30 дней). Подкоманды: `keyword-info` (Wordstat-частоты ws/wsk/kei/cpc), `keywords` (ключи домена + позиции), `competitors` (видимость, топ-10/3, реклама), `lost` (потерянные ключи). Сильная сторона — **Яндекс-данные для РФ**, дополняет Wordstat (частоты) и Serpstat (Google).
- Добавлен в `region-profiles` ru + global (РФ-сервис; не eu/us), `seo-cycle.yaml` emwoody + `project.template.yaml`, `.env.example` (`KEYSO_API_TOKEN`).
- В `prompts/competitor-analysis.md` — Keys.so в источниках (конкуренты/частоты/lost).
- GUIDE.md (RU+EN) + CLAUDE.md emwoody — таблицы источников.

## [1.11.0] — 2026-05-30

### Маркетинг-слой: стратегия → результат (замыкает полноценный маркетинг)

Верхний слой над органикой — решение «куда вкладывать» и измерение результата в деньгах.
- **`scripts/roi-calc.py`** — воронка трафик→лиды→заказы→выручка + ROI/CAC/ДРР/AOV по каналам + вердикт «что окупается / нужна ли реклама». «Конечный результат» в деньгах.
- **`prompts/marketing-strategy.md`** — цели → оценка органика vs платка (на цифрах) → медиаплан/бюджет → KPI. Реклама только при дефиците объёма с ROI>0.
- **`prompts/distribution-channels.md`** — каналы РФ (email/Telegram/видео) + **товарные фиды/маркетплейсы** (Яндекс.Маркет, Озон, Google Merchant).
- **`prompts/orm.md`** — мониторинг отзывов + алерт на негатив (`notify.py`).
- **`prompts/marketing-calendar.md`** — единый план SEO+соцсети+email+реклама+акции.
- Секция `marketing.channels/marketplaces/measurement` в конфиге emwoody; мостик в Phase 0 SKILL; GUIDE.md (RU+EN) раздел 7.9.
- Отмечено внешнее (вне кода скилла): цели Метрики, коллтрекинг, CRM, кабинеты маркетплейсов, РФ ESP.

## [1.10.0] — 2026-05-30

### Закрытие пробелов охвата: потерянные ключи, бенчмарк, AI-visibility, реклама+соцсети

- **`scripts/lost-keywords.py`** — потерянные/просевшие ключи между двумя снапшотами (GSC/Вебмастер): LOST (выпал из топа) / DROPPED (просел) + потерянные клики. Детерминированно, без трат API.
- **`scripts/competitor-benchmark.py`** — медианный бенчмарк: для каждой метрики (ключи/бэклинки/отзывы/посты/фото) медиана топ-N конкурентов vs моё → статус 🔴/🟡/🟢 + разрыв %.
- **`prompts/ai-visibility.md`** — единый GEO-свод: присутствие в Яндекс Нейро / Google AI Overviews / ChatGPT / Perplexity (плагины `seo-geo`/`seo-seranking` + браузер). РФ-приоритет Нейро/GigaChat.
- **`prompts/ad-and-social.md`** — разведка рекламы конкурентов (SpyFu PPC / Serpstat ads / Директ) + генерация объявлений и соцпостов (Директ/VK/TG/Дзен) через `marketing-skills` с РФ-адаптацией и маркировкой рекламы.
- Мостики в Phase 9 SKILL.md; GUIDE.md (RU+EN) — новые скрипты в таблицах.

## [1.9.0] — 2026-05-30

### Конкурентный анализ + ICE-приоритизация

Из практики РФ-SEO (статья sostav): единый метод свести разрозненные конкурентные данные и приоритизировать находки.
- **`scripts/ice-score.py`** — приоритизация находок по ICE (Impact×Confidence×Ease, 1..10): сортировка + зоны 🔥 quick-win / ✅ do / ⏳ later. Вход CSV (`finding,impact,confidence,ease,source,note`).
- **`prompts/competitor-analysis.md`** — 7-шаговый метод: цель → конкуренты → источники (Serpstat/SpyFu/Keys.so/local/GSC, без дублирования сбора) → измерения → ICE → roadmap 1-6 мес → мониторинг. РФ-приоритет (Яндекс + Карты/2ГИС), инсайт «надёжность/экспертиза > цена».
- Мостик в Phase 1 SKILL.md (audit → конкурентный анализ + ICE → quick-wins в roadmap/keyword-queue).
- GUIDE.md (RU+EN): `ice-score.py` в таблицах инструментов.

(Остальное из присланного — ruflo/cybersecurity-skills/habr — оценено как оверинжиниринг / вне scope / уже реализовано; не внедрялось.)

## [1.8.0] — 2026-05-30

### Маркетинговые мостики (marketing-skills) + РФ-адаптация каналов

Связка с плагином `marketing-skills` (Corey Haines) — без дублирования его кода.
- **`docs/marketing-bridges.md`** — карта «фаза seo-cycle → релевантный marketing-skill» + **таблица РФ-замен каналов** (Google Ads→Яндекс.Директ, Meta→VK/Telegram, GA→Метрика, каталоги→2ГИС/Яндекс.Бизнес, Stripe→ЮKassa, отзывы→Яндекс.Карты/2ГИС, +RuStore). Что НЕ дублировать (SEO-скиллы плагина).
- **Секция `marketing`** в `seo-cycle.yaml` (emwoody: enabled + rf_adaptation + rf_channel_map + relevant_skills) и в `project.template.yaml` (opt-in).
- **Мостик в Phase 7** SKILL.md: после публикации → CRO через marketing-skills с РФ-адаптацией каналов.
- GUIDE.md (RU+EN): раздел 7.8.

## [1.7.0] — 2026-05-30

### Локальный SEO-модуль (карты: Google + Яндекс/2ГИС)

Парные тактики локального доминирования для обеих карт-экосистем (для РФ приоритет Яндекс.Карты + 2ГИС). Адаптировано из набора local-SEO приёмов.

- **`prompts/local/`** — `README` + `google-maps.md` + `yandex-maps.md`: 5 тактик парно (категории/рубрики gap, скорость отзывов, календарь постов, визуальное доминирование, локальная видимость). Оба рантайма (Chrome MCP / browser-skill).
- **`scripts/review-velocity.py`** — детерминированный расчёт плана догона лидера по отзывам (Google/Яндекс/2ГИС): темп/мес и срок.
- **`business_profile`** расширен: `gbp_url`, `yandex_business_url`, `2gis_url`, `target_local_keywords`, `competitors[{name,gbp,yandex,2gis}]` — «постоянный профиль», чтобы тактики брали конкурентов из конфига.
- **Чек-лист локального доминирования** встроен в Phase 1 (audit) и Phase 9 (monitoring): сравнение с топ-3 конкурентами по категориям/отзывам/постам/фото на обеих картах.
- GUIDE.md (RU+EN): раздел 7.7 Локальное SEO.
- Не дублируем уже покрытое: keyword gap (Serpstat/SpyFu), позиции 11-20 (triggers), бэклинки (seo-backlinks/ahrefs), общий GBP/NAP (плагин seo-maps/seo-local).

## [1.6.1] — 2026-05-30

### Дробление заморожено на пилоте (решение)

После обкатки пилота решено **не продолжать** дробление на фазовые скиллы — для текущего масштаба (1-2 проекта) overhead координации и дрейф логики не окупаются.
- Монолитный `seo-cycle` со всеми 10 фазами — **основной и рабочий**.
- Пилот (`cycle-state.py` + `seo-keywords`) оставлен как есть (аддитивен, обратим, опционален).
- Остальные фазы НЕ выносятся без явной потребности (продажа модулей / команда / переиспользование / параллелизм).
- Формулировки в SKILL.md и GUIDE.md обновлены: статус «заморожено», а не «по плану».

## [1.6.0] — 2026-05-30

### Модульная архитектура — пилот (фазовые скиллы + state-цепочка)

Начало перехода от монолитного оркестратора к независимым фазовым скиллам, координируемым через единый файл состояния. Эволюционно — без ломки текущего.

- **`scripts/cycle-state.py`** — контракт состояния цикла `seo/cycles/<тема>/_state.json`: `init`/`show`/`next`/`set`/`gate`. DAG из 11 фаз с `depends_on`; `next` вычисляет разблокированные фазы; `gate` проверяет готовность артефакта. Это «цепочка передачи» между скиллами.
- **Новый скилл `seo-keywords`** (`~/.claude/skills/seo-keywords/`) — самостоятельный фазовый скилл Phase 2-3 (сбор семантики + кластеризация): SKILL.md + README, читает/обновляет `_state.json`, использует core collector-скрипты. Шарибельный отдельно.
- `seo-cycle` SKILL.md: раздел «Модульная архитектура» — диспетчер ведёт цикл через `cycle-state.py`, проверяет quality-gate перед передачей, независимые фазы параллельно. «Улучшение» на данных, без авто-рефакторинга.
- GUIDE.md (RU+EN): раздел 6b + `cycle-state.py` в таблицах инструментов.

Дальше по плану: вынести `seo-entity-map`, `seo-writing`, `seo-publishing`, `seo-monitoring` по тому же образцу → затем `seo-cycle` станет чистым диспетчером (v2.0.0).

## [1.5.0] — 2026-05-29

### Полная двуязычная документация + AI-автоустановка

- **`GUIDE.md`** — подробное руководство **RU (сверху) + EN (полный перевод ниже)**: что это, преимущества, установка для человека и **для ИИ-агента (самостоятельный машинный сценарий)**, архитектура, оба рантайма, **все ~36 инструментов** (что делает / команда / какой результат), 10 фаз по шагам, агенты/делегаты, команды-шпаргалка, типовые сценарии.
- **Правило обновления документации** закреплено в `GUIDE.md`, `SKILL.md` и памяти: при любом изменении — обновить GUIDE (обе версии) + CHANGELOG + VERSION в том же коммите.
- README: ссылка на GUIDE как главную документацию.

## [1.4.0] — 2026-05-29

### Codex как основной мозг (гибридный двойной рантайм)

Полная адаптация под сценарий, когда оркестратор — Codex CLI, а не Claude. Принцип гибрида: наши скрипты для уникального (РФ-источники, Serpstat/SpyFu, кэш, guard'ы, публикация); нативные Codex-skills для изображений/браузера/делегирования; **без `codex exec` самовызовов**.

- **RUNTIME-режим:** `runtime: auto|claude|codex` в конфиге + env `SEO_RUNTIME`. Авто-детект Codex по env-признакам.
- **`llm-cli-collect.sh`** — RUNTIME-aware: в codex-режиме запускает только `agy`, печатает промпт для нативного сбора Codex (web_search), без вложенного `codex exec`.
- **`img-generate.sh`** — перенесён в скилл, RUNTIME-aware: claude → `codex exec` обёртка; codex → вывод `CODEX_NATIVE_IMAGE` для нативного `seo-image-gen`/`image`/`sora`. emwoody-версия стала тонким враппером.
- **`docs/codex-runtime.md`** — полный маппинг Claude↔Codex (изображения, браузер, делегирование, сбор, фазы) + детект режима.
- Заполнен `~/.codex/skills/codex-primary-runtime/SKILL.md` — точка входа для Codex-сессии.
- `runtime` добавлен в `project.template.yaml`; секция RUNTIME в `SKILL.md`.

## [1.3.0] — 2026-05-29

### Слой данных + уведомления (Этап 1 автоматизации — без n8n/Next.js)

После разбора «n8n vs Next.js vs CLI»: вместо тяжёлой инфры — тонкий слой к существующему ядру.
- **`scripts/db-sync.py`** — собирает CSV/JSON-артефакты (keyword-queue, source-attribution, publish-log, monitoring snapshots, api usage) в единую `seo/seo.db` (SQLite). Фундамент под дашборды (Obsidian/Metabase/Next.js) и алерты. Устойчив к отсутствию файлов, идемпотентен.
- **`scripts/notify.py`** — Telegram-уведомления одним скриптом (без n8n). Graceful no-op без токена (pipeline не ломается). `--test`, уровни info/warn/alert.
- Интеграция: `approval-gate.py` шлёт алерт при создании тикета; `monthly-runner.sh all` — при сбое проекта.
- Секции `data_store` + `notifications` в `project.template.yaml`, `.env.example` (TELEGRAM_*). `seo/seo.db` в .gitignore.

### SpyFu (новый источник Phase 2 — competitor/PPC для US/UK/EU)

- **`scripts/spyfu-fetch.py`** — клиент SpyFu API (Basic auth из `API_SpyFu_ID:API_SpyFu_secret_key`). Подкоманды: `usage`, `domain-stats` (latest/all), `raw`. ⚠ Покрывает только западные рынки (countryCode US/GB/DE/...), **RU отвергается** — поэтому в профилях us/eu/global, в ru → `sources_disable` с причиной.
- Защита $-бюджета (Pro $40/мес, pay-as-you-go): локальный usage-трекер с месячным сбросом + CPM-таблица по эндпоинтам, блок при достижении `--budget`. Кэш 30 дней, дистиллят → stdout.
- Добавлен в `region-profiles` (us/eu/global), `project.template.yaml`, `.env.example`, Phase 2 SKILL.

### Serpstat (новый источник Phase 2 — volume/KD/конкуренты для РФ/СНГ)

- **`scripts/serpstat-fetch.py`** — клиент Serpstat API v4 (JSON-RPC). Подкоманды: `stats` (бесплатно), `keywords-info`, `related`, `suggestions`, `domain-keywords`, `competitors`. Работает с `g_ru` — закрывает дыру Ahrefs/SEMrush в РФ.
- Защита кредитов (план Appsumo 1000/мес, 1 req/sec): pre-flight через getStats + `--min-credits` guard, `--size` лимит строк, кэш на диск (`--ttl 30`), rate-limit 1.1с/запрос. Сырьё → диск, дистиллят (md-таблица) → stdout.
- Добавлен в `region-profiles` (ru/eu/us/global), `project.template.yaml`, `.env.example` (`SERPSTAT_API_KEY`), Phase 2 SKILL.

### Региональные профили источников (универсальность по странам)

- **`config/region-profiles/{ru,eu,us,global}.yaml`** — пресет источников на регион. Проект задаёт одной строкой `region_profile: ru`. ru = Яндекс-приоритет + Google-инструменты доступные из РФ, Ahrefs/SEMrush выключены, DataForSEO через прокси. eu/us = Google-моно + полный западный SaaS, Яндекс off, ATP без перевода.
- **`scripts/resolve-sources.py`** — разворачивает профиль + локальные override → список активных/пропущенных источников с причиной + `seo/cycles/<date>/active-sources.json`. Legacy-режим для конфигов без `region_profile`.
- `validate-config.py` научен резолвить активность источников через профиль.

### Экономия токенов

- **`scripts/research-cache.py`** — TTL-кэш (`research_cache_ttl_days`, дефолт 14): дорогой сбор не перезапускается, если свежий результат на диске. Подключён в `llm-cli-collect.sh`.
- LLM-CLI **deep-режим**: Codex `model_reasoning_effort=xhigh` + `web_search=live` явно; Antigravity + Perplexity — через deep-преамбулы промптов.
- Правило в SKILL: «сырьё на диск, в контекст — только `*-merged-*.md` / дистилляты».

### E-E-A-T

- **`scripts/schema-org-build.py`** — канонический Organization/LocalBusiness узел из `business_profile` конфига (@id, trust-сигналы: address/telephone/openingHours/areaServed/knowsAbout/sameAs); `inject` переписывает author/publisher всех Article/Product на @id-референс (идемпотентно).
- **`scripts/eeat-render.py`** — из `fact_check_log` frontmatter рендерит видимый trust-блок «Источники» (только verdict достоверно/частично).
- **`scripts/source-attribution.py`** — замыкает петлю: какой источник семантики дал ключи в топ (джойн `source-attribution.csv` × snapshot) → рекомендации, какие источники отключить.
- `business_profile` + `region_profile` + `research_cache_ttl_days` добавлены в `project.template.yaml`.

### Масштабирование на N проектов

- **`config/projects-registry.yaml`** — реестр всех проектов (path/region_profile/cms/status/monthly_automation).
- `init-project.sh` — выбирает `region_profile` по стране и дозаписывает проект в реестр.
- `monthly-runner.sh all [subcmd]` — итерация по активным проектам реестра.

## [1.2.0] — 2026-05-28

### Step 10 — Monthly Automation (MVP + Full)

**4-system automated monthly workflow** заменяющий команду из 4 SEO-специалистов:
- System 1 — Keyword Research (replenish queue)
- System 2 — Weekly Publisher (Mon 9am, 4 posts/mo)
- System 3 — Monthly Site Audit (Week 2)
- System 4 — Refresh + Deindex Rescue (Week 3-4)

**Новые скрипты (5):**
- `scripts/keyword-queue.py` — FIFO очередь ключей (add/pop/approve/publish/status)
- `scripts/approval-gate.py` — file-based approval tickets (5 типов)
- `scripts/monthly-runner.sh` — auto-detect day/week → запуск операции; парсит расписание из yaml
- `scripts/deindex-detect.py` — sitemap vs GSC diff + HTTP classification (deindex/4xx/5xx/noindex/redirect)
- `scripts/monthly-dashboard.py` — auto-generated status dashboard в markdown

**Новые subagents (6 экспертов в `~/.claude/agents/`):**
- `seo-monthly-orchestrator` — top-level координатор расписания и approval gates
- `seo-keyword-queue-manager` — System 1 expert (replenish + Phase 2 research)
- `seo-weekly-publisher` — System 2 expert (pop → entity-map → write → QA → approval → publish)
- `seo-monthly-auditor` — System 3 expert (P0+P1 filter, approval перед фиксами)
- `seo-refresh-rescuer` — System 4 expert (refresh + полный deindex workflow)
- `seo-approval-gate` — helper для всех 5 approval точек

Все subagents в стандарте Anthropic Agent Skills (YAML frontmatter + markdown) — **работают в Claude Code и Codex CLI без модификаций**.

**Новые templates (1):**
- `templates/keyword-queue.template.csv` — стартовый шаблон очереди

**Новые prompts (1):**
- `prompts/page-rewrite-rescue.md` — diagnose + rewrite plan для деиндексированных страниц

**Новая документация (1):**
- `docs/automated-monthly.md` — полный workflow doc (setup cron, approval flow, troubleshooting, cross-platform notes для Codex)

**Обновления existing:**
- `config/project.template.yaml` — секция 21 `monthly_automation` (cron schedule, queue file, approval gates, refresh triggers, deindex)
- `scripts/monthly-runner.sh` — schedule parser из yaml (опц. override defaults)
- `agents/seo-refresh-rescuer.md` — полная реализация DEINDEX RESCUE workflow (вместо placeholder из MVP)

**Регрессия:**
- ✅ emwoody pilot активирован: `monthly_automation.enabled: true`, 5 approved keywords в очереди (minvata×2, shumoizolyacziya, plitochnyy-kley, xps)
- ✅ Все 26 скриптов имеют `--help`
- ✅ End-to-end: deindex-detect на dummy data → diff корректен (2 lost из 5 sitemap)
- ✅ Dashboard для emwoody генерится: TL;DR + queue + approvals + snapshot status

**Personal time (target ~2-3h/month):**
- Approve keyword research: 5 min × 1/mo
- Approve каждый пост: 2 min × 4/mo = 8 min
- Audit review + fixes: 30 min × 1/mo
- Refresh plan review: 10 min × 1/mo
- Deindex rewrite approve: 5 min × variable
- **Total: ~1.5-2 часа в месяц**

**Заменяет:**
- Content Strategist ($3-5k/mo)
- Content Writer ($2-4k/mo)
- Technical SEO ($2-3k/mo)
- Content Editor ($1.5-3k/mo)
- **Total команды: $8.5-15k/mo → Total системы: <$50/mo**

### Roadmap → v1.3

- [ ] `scripts/notification.py` — email на P0 audit findings (опц.)
- [ ] Schedule parser в monthly-runner.sh — полный (сейчас MVP: content + audit)
- [ ] WooCommerce auto-sync для stock-inventory.yaml
- [ ] Shopify / Webflow publish handlers (универсальные)
- [ ] Готовые Schema.org JSON-LD скелеты по project_type
- [ ] DataForSEO fallback для Wordstat
- [ ] Stop-words для DE/TR/PL/EN-более-расширенный

## [1.1.0] — 2026-05-27

### Production-ready upgrade: observability hub + actionable feedback engine

**Архитектурное:**

- Phase 9 переработана как **master observability hub** с единой schema snapshot.json
- Phase 10 = **actionable feedback engine** на декларативных правилах (`config/triggers.yaml`)
- Введён `mode: standard | migration | programmatic` для разных типов циклов
- Новые опц. секции конфига (back-compat): `monitoring`, `eeat`, `migration`, `backlinks`

**Новые скрипты (P0/P1/P2 = 12 шт):**

- `google-trends.py` — pytrends wrapper для сезонности
- `init-project.sh` — интерактивный wizard (7 вопросов → готовый yaml)
- `snapshot-build.py` — нормализатор аналитики в единую schema (5 источников: gsc/ga4/metrika/webmaster/psi)
- `triggers-eval.py` — оценщик правил Phase 10 → markdown action list
- `nw-cli.sh` — universal NeuronWriter wrapper
- `validate-entities.py` — universal entity registry checker
- `psi-fetch.py` — PageSpeed Insights API client (free, без OAuth)
- `gsc-fetch.py` — Search Console API client (service account)
- `ga4-fetch.py` — GA4 Data API client
- `metrika-fetch.py` — Я.Метрика API client (OAuth)
- `webmaster-fetch.py` — Я.Вебмастер API client (OAuth)
- `programmatic-template-gen.py` — data-driven генератор страниц
- `schema-validate.py` — JSON-LD валидатор

**Новые шаблоны:**

- `templates/monitoring-report.template.md` — snapshot отчёт
- `templates/cycle-plan.template.md` — content plan
- `templates/programmatic-page.template.md` — для PSEO
- `templates/hreflang-matrix.template.md` — мультирегион
- `templates/stock-inventory.template.yaml` — перенесён из scripts/, расширен примерами WooCommerce/Shopify

**Новый config:**

- `config/triggers.yaml` — 18 декларативных правил Phase 10

**Новая документация (9 docs):**

- `docs/oauth-setup.md` — единый OAuth setup (GCP + Яндекс), таблица всех env vars
- `docs/troubleshooting.md` — FAQ по типичным ошибкам
- `docs/migration-planner.md` — domain/CMS миграция
- `docs/eeat-audit.md` — E-E-A-T cross-cutting checklist
- `docs/backlink-research.md` — backlink workflow
- `docs/sxo-quality-gates.md` — SXO quality gates
- `docs/international-seo.md` — hreflang strategy
- `docs/image-seo.md` — image SEO checklist
- `docs/video-seo.md` — video SEO + VideoObject schema
- `docs/versioning-migration.md` — upgrade guide для v1.0 → v1.1

**Новые промпты:**

- `prompts/competitor-pages-analysis.md` — глубокий SERP-анализ топ-10

**Новые конфиг-файлы:**

- `.env.example` — шаблон env vars

**Обновления existing:**

- `SKILL.md` — Phase 0 (mode), Phase 9 (snapshot pipeline + единая schema), Phase 10 (triggers engine + декларативные правила)
- `INSTALL.md` — TL;DR Вариант A: интерактивный wizard
- `config/project.template.yaml` — schema v1.1, новые секции 17-20
- `scripts/validate-config.py` — поддержка v1.1 расширений + OAuth env vars check

**Регрессия:**

- ✅ Existing `emwoody/seo-cycle.yaml` валидируется без новых ошибок
- ✅ End-to-end pipeline: API → snapshot → triggers → markdown action list
- ✅ Все 7 P0 + 5 P1 fetcher скриптов имеют `--help`
- ✅ programmatic-template-gen + schema-validate тестируется на dummy данных

### Известные ограничения

- AnswerThePublic не поддерживает регион Россия — используем en/us для шаблонов с переводом
- LLM CLI (Antigravity / Codex) могут давать разный результат, нужен merge через `llm-cli-merge.py`
- Perplexity требует ручной установки Claude for Chrome extension — autosetup невозможен
- ATP может создать все провайдеры даже когда указан один — кредитный овершут возможен

### Roadmap → v1.2

- [ ] `scripts/stock-sync-woo.py` — авто-синк stock-inventory.yaml из WooCommerce
- [ ] `scripts/stock-sync-shopify.py` — то же для Shopify
- [ ] `scripts/backlinks-normalize.py` — нормализация backlinks export в snapshot
- [ ] `scripts/hreflang-validate.py` — валидация hreflang кросс-ссылок
- [ ] Shopify / Webflow publish handlers (универсальные)
- [ ] Schema.org templates по project_type (готовые JSON-LD скелеты)
- [ ] DataForSEO интеграция как fallback для Wordstat
- [ ] Поддержка немецкого / турецкого / польского tone of voice в `check-stop-words.py`

## [1.0.0] — 2026-05-26

### Initial release — универсальный SEO-цикл скилл

[см. предыдущую версию CHANGELOG ниже]

**Что внутри:**

- `SKILL.md` — оркестратор 10 фаз
- `INSTALL.md` — wizard для нового проекта
- `config/project.template.yaml` — полная схема конфига
- 4 универсальных промпта, 2 шаблона, 4 doc
- 7 переносимых скриптов (validate-config, check-stop-words, yandex/google suggest, atp-fetch, llm-cli×2, obsidian-sync)
- 16 sources в config (Yandex 8, Google 5, NW 1, LLM CLI 1, ATP 1)
- 12 делегатов через `~/.claude/agents/` и `claude-seo:*` plugin skills
- Obsidian-интеграция (через obsidian-native-mcp + obsidian-sync.py)
- 5 kepano-skills установлены параллельно
