---
name: seo-monitoring
description: Мониторинг (Phase 9): ежедневный pulse (GSC + Я.Вебмастер + Метрика + GA4 + PSI) в единую схему snapshot.json, потерянные ключи, AI-visibility (GEO), конкурентный бенчмарк. Используй когда просят «сними позиции», «что с трафиком», «обнови мониторинг» — отдельно или как стадию цикла.
---

# Monitoring — снапшоты позиций и поведения

Модуль seo-cycle v2 · **Фазы: 9** · запуск **отдельно** или **стадией конвейера**.

## Контракт модуля

- **Входы:** API-токены источников (Keychain через ai-secret), `config/projects-registry.yaml` для `pulse --global`
- **Конвейер:** `_state.json` цикла (`scripts/cycle-state.py`) — предыдущая фаза `done`; **standalone:** state нет → `seo-cycle cycle init --topic "<тема>"`, работай по этому файлу, state обнови на выходе.
- **Выходы:** `09-monitoring/YYYY-MM-DD-snapshot.json` + markdown-отчёт; `seo.db` через `db-sync`
- **Gate:** freshness: снапшоту < 3 дней (warn) / < 7 дней (error) — проверяется в `doctor`
- **Делегаты:** `delegate.google_data` (`claude-seo:seo-google`), `delegate.yandex_specialist`
- **Общие правила:** `../_shared/policy-intake.md` (политики/бюджеты проекта — прочитать до платных действий), `../_shared/scorecard.md` (самооценка после задачи), `../_shared/rag-usage.md` (переиспользуй накопленное).

---

## Phase 9 — Monitoring

**Цель:** регулярные снапшоты позиций / трафика / поведения.

**Делегировать:**
- `delegate.google_data` (`claude-seo:seo-google`) — GSC + GA4 + CrUX (если включено)
- `delegate.yandex_specialist` — Я.Вебмастер + Метрика (если включено)

**Cadence (единая, v2):** данные собираются **ежедневно** — `seo-cycle pulse` (или `pulse --global` daily-джобом): fetch → snapshot → db-sync → position-progress + алерты. **Раз в 2 недели** поверх ежедневных снапшотов строится человеческий отчёт по `templates/monitoring-report.template.md`. Свежесть снапшота проверяет `seo-cycle doctor` (warn ≥3 дн., fail ≥7 дн.). Важно: Вебмастер-выгрузка — это `query_sample` (обычно топ-500 запросов, `sitewide: false`); все производные цифры (forecast, KPI, триггеры) наследуют этот потолок.

**Локальный мониторинг (если локальный бизнес):** раз в месяц снимать прогресс vs конкуренты на обеих картах — скорость отзывов (`review-velocity.py`), новые категории/рубрики, частота постов, прирост фото. Промпты — `prompts/local/`. Отставание → задача в Phase 10.

**Потерянные ключи:** сравнить текущий снапшот с прошлым — `scripts/lost-keywords.py --old <prev> --new <cur>` (выпавшие/просевшие ключи → refresh + перелинковка).

**AI-visibility (GEO):** свод присутствия в Яндекс Нейро / Google AI Overviews / ChatGPT / Perplexity — промпт `prompts/ai-visibility.md` (+ плагины `seo-geo`/`seo-seranking`).

**Медианный бенчмарк по конкурентам:** `scripts/competitor-benchmark.py` — где мы ниже медианы топ-N (ключи/бэклинки/отзывы/посты/фото) → приоритеты в roadmap (ICE).

**Реклама + соцсети:** разведка платной выдачи и соцактивности конкурентов + генерация объявлений/постов (Директ/VK/TG/Дзен) — промпт `prompts/ad-and-social.md`.

**Pipeline (observability hub):**

```
delegate(claude-seo:seo-google) → GSC/GA4 JSON ┐
delegate(yandex-seo-specialist) → Webmaster/   ├→ snapshot-build.py --source X
  Metrika данные                               │   (нормализация в единую schema)
psi-fetch.py URL → PSI JSON                    ┘                  ↓
                                                    09-monitoring/YYYY-MM-DD-snapshot.json
```

**Единая schema `snapshot.json`:** см. `scripts/snapshot-build.py --help`. Поля: `queries[]`, `pages[]`, `cwv{}`, `behavior{}`, `sources[]`. Скрипт умеет мердж нескольких источников в один snapshot через `--merge`.

**Что собирать:**
- Топ-100 запросов: impressions, clicks, CTR, position, дельты
- Топ-страниц: то же + behavior (bounce, time, conversions)
- CWV per URL (PSI) с статусом good/needs_improvement/poor
- Изменения vs прошлый снапшот
- Сезонные сравнения (если есть данные за прошлый период)

**Выход:** `09-monitoring/YYYY-MM-DD-snapshot.json` + `*.md` отчёт по шаблону.
