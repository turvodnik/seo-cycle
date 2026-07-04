# Полный аудит seo-cycle v1.82 — оценки 1–10 по всем областям

Дата: 2026-07-04. Методика: та же формула честности, что в scorecard-слое —
10 = «закрыто полностью и проверено тестами», минус баллы за реальные пробелы.
Оценка ставится **возможностям инструмента**, не результатам конкретного
проекта (те смотрите в `seo-cycle progress` и `seo-cycle score show`).

## Сводная таблица

| # | Область | Оценка | Что есть | Чего не хватает |
|---|---|---:|---|---|
| 1 | Семантика: multi-source сбор | 9 | Wordstat/GSC/Keyso/Serpstat/XMLRiver/LLM-CLI/ATP/suggest/trends, кэш, ledger | регулярный парсинг SERP-фич по расписанию |
| 2 | Кластеризация + интенты | 9 | keyso-export, semantic-core-clean/resync, intent-разметка в ядре | собственная SERP-overlap кластеризация (сейчас — делегат в claude-seo:seo-cluster) |
| 3 | Структура сайта | 8 | semantic-architecture, programmatic-template-gen, orphan-resolver, spoke-audit | визуальная карта структуры (граф) |
| 4 | Сущности (метод Шестакова) | 9 | entity-map, entity-graph-quality, validate-entities, google-nlp, триплеты в RAG | автопополнение сущностей из SERP по расписанию |
| 5 | Факт-чекинг / E-E-A-T | 9 | evidence map, eeat-render, expert/xmlriver/writerzen source packs, fact-check queue, source-attribution | автоматическая проверка живости внешних ссылок в цикле |
| 6 | Брифы и контент-продакшн | 9 | page-outline v2/v3, copywriter-ready, стоп-слова, NW-интеграция, RAG-контекст | мультиформат (видео-скрипты/соцсети) сверх marketing-bridges |
| 7 | Quality gates + автоцикл | 10 | loop-runner (max 5, no-progress, эскалация), evidence-классы, scorecards, journey-видимость | — |
| 8 | Технический SEO | 8 | technical-site-audit, lighthouse/PSI, guardrails, schema, redirect-map, log-bot-audit, каннибализация | полноценный собственный краулер (точечные проверки вместо обхода; параллельно — RustySEO/firecrawl) |
| 9 | AEO / GEO | 9 | answer-units, ai-brand-audit, geo-kpi, llms.txt, ai-bot-access, snippet-аудит | регулярный трекинг цитируемости в AI-ответах как метрика |
| 10 | Индексация | 9 | IndexNow, Яндекс recrawl, GSC queue + inspection + recheck, Bing, deindex-detect | авто-ресабмит по deindex-кейсу без человека (сознательно за approval) |
| 11 | Прогресс позиций | 9 | position-progress: срезы, top-3/10/30, movers, HTML-бары, портфель --global, loops-digest | автоснапшоты позиций строго по расписанию (нужен systemd/launchd из vps-runbook) |
| 12 | Forecast / KPI / «гарантия» | 9 | CTR-кривые, сценарии, kpi-contract план-vs-факт + эскалация, budget-mix с убывающей отдачей | доверительные интервалы прогноза |
| 13 | Платная реклама | 8 | Директ+Google guarded слой, 5 кросс-правил (включая n-gram waste), драфты, apply v1 (Директ, 6 предохранителей), Editor CSV | apply для Google Ads (для ru не нужен), РСЯ/МК-стратегии глубже |
| 14 | Метрика / GA4 / поведение | 8 | metrika-fetch + Logs API, ga4-fetch, conversion-sxo-audit | когортный анализ, автопроверка целей |
| 15 | GTM | 8 | gtm-audit: карта тегов/триггеров, драфты изменений | запись через API (сознательно только драфты + человек) |
| 16 | Merchant / Яндекс.Товары | 7 | merchant-health/fetch, yml-feed-audit, ru-commerce-readiness | автогенерация фидов из CMS (зависит от магазина) |
| 17 | Google Business Profile | 8 | health/fetch (locations+reviews), OAuth-helper, Testing-режим сегодня, submission-pack | человеческий шаг: подача verification (docs/gbp-verification-submission.md) |
| 18 | Яндекс.Бизнес / 2GIS | 6 | честный partner_limited, обходные пути (браузер, экспорт отзывов → review-velocity) | API закрыт партнёрством — внешнее ограничение платформы |
| 19 | CMS-sync / хранилище контента | 9 | mirror engine (hash-дифф, drift), WP/Tilda/Bitrix pull, WP publish, research-cache | авто-push в Tilda/Bitrix (сейчас pull + публикация делегатами) |
| 20 | Вики / знания проекта | 9 | knowledge hub, obsidian-sync, дистилляты, context-pack | — существенного |
| 21 | RAG | 9 | FTS5/BM25 + опц. embeddings, кросс-проектный global.db, потребители в брифах | авто-переиндексация хуком после каждого артефакта |
| 22 | Governance / бюджеты | 10 | usage-ledger, spend-guard, approval-gate, token policy, redaction секретов | — |
| 23 | Оркестрация / автоматизация | 9 | monthly 4 системы, triggers, task-router, cycle-state DAG, loop, menu | live web-дашборд (сознательно: статические HTML-отчёты) |
| 24 | Уведомления / контроль | 9 | Telegram-алерты, approvals, эскалации loop/KPI, scorecards в journey и чате | — существенного |
| 25 | Мультипроектность | 9 | projects-registry, портфель-прогресс, глобальный RAG, env-профили global/project | кросс-проектные инсайты глубже (общие сущности уже в RAG) |
| 26 | Клиентские отчёты | 9 | white-label md/HTML/PDF, агентский брендинг, все источники | автоотправка (email/Telegram-файл) |
| 27 | Auth / доступы | 9 | auth-assistant (login/set/list, источники), цепочка профилей, GBP OAuth end-to-end, 0600 | автопроверка сроков жизни токенов |
| 28 | Инженерия | 9 | 249 тестов, CI 3.11/3.12/3.14, optional Pydantic, модульное ядро (19 core-модулей), логи | ruff/mypy в CI |
| 29 | Онбординг / UX | 9 | init wizard, intake, journey, doctor, единый CLI, интерактивное меню, desktop-иконка | — существенного |
| 30 | Документация | 9 | 25 docs + SKILL.md + runbooks (VPS, GBP, экосистема) | единый учебник для сотрудников агентства |

**Интегральная оценка: 8.7/10** (v1.59 на начало дня было ≈6.5: без автоцикла,
ads, RAG, прогресса, профилей и самооценок).

## Чем этот стек занимается для продвижения (карта цикла)

1. **Онбординг** — wizard + intake + control-plane: конфиг, ключи (auth-профили), policy.
2. **Исследование** — семантика из 6+ источников → чистка → кластеры → интенты →
   сущности → evidence (факты с источниками). Всё кэшируется и попадает в RAG.
3. **Стратегия** — структура сайта, контент-план, forecast (сколько трафика/лидов
   и когда), KPI-контракт, бюджет-микс SEO+PPC с убывающей отдачей.
4. **Продакшн** — брифы v3 → драфты → автоцикл качества (стоп-слова, E-E-A-T,
   схемы, честность) → публикация в CMS → индексация (IndexNow/GSC/recrawl).
5. **Реклама** — Директ: fetch → кросс-аналитика с органикой → драфты → approval →
   apply; минус-слова из wasted spend, кандидаты в семантику из конверсионных термов.
6. **Мониторинг** — снапшоты позиций/CWV/индексации → position-progress (движение),
   triggers (просадки, устаревшие факты) → refresh/rescue.
7. **Отчётность** — журналы, самооценки, месячный дашборд, white-label отчёт
   клиенту (md/HTML/PDF), портфельная сводка по агентству.
8. **Контроль** — бюджеты и токены под ledger, платное за approval, эскалации в
   Telegram; человек решает, машина готовит.

## Топ-5 следующих шагов по ценности

1. **Человеческое**: подать GBP verification по submission-pack (30–40 мин).
2. Расписание на VPS/launchd по docs/vps-deployment.md — чтобы снапшоты позиций
   и monthly шли без ноутбука (питает пункты 11 и 23).
3. Собственный лёгкий краулер (или регулярный seo-firecrawl прогон) → поднимет
   Технический SEO с 8 до 9–10.
4. Автоотправка клиентских отчётов (notify-файл в Telegram) — мелко, но заметно.
5. ruff в CI — дешёвая страховка стиля.
