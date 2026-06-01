# Маркетинговые мостики (seo-cycle ↔ marketing-skills) + РФ-адаптация

Плагин **`marketing-skills`** (Corey Haines, 40+ скиллов) дополняет `seo-cycle`:
seo-cycle ведёт органику и контент, marketing-skills закрывают платный трафик,
CRO, удержание, монетизацию, позиционирование. Этот документ — **когда какой
marketing-skill звать в цикле** и **чем заменить западные каналы на РФ-аналоги**.

> Сами скиллы плагина мы НЕ редактируем (чужой код). Здесь — слой связи и
> РФ-контекста, который применяем при их вызове.

---

## ⚠ Правило РФ-адаптации (применять ВСЕГДА при вызове marketing-skills)

Скиллы плагина западо-ориентированы. Для проектов с `locale.country: RU` (или
`region_profile: ru`) подставляй РФ-эквиваленты каналов и инструментов:

| Западное (в скилле) | РФ-замена |
|---|---|
| Google Ads | **Яндекс.Директ** (Поиск + РСЯ) |
| Meta / Facebook / Instagram Ads | **VK Реклама**, **Telegram Ads**, РСЯ |
| Соцсети (X/Twitter, LinkedIn, Instagram) | **VK**, **Telegram**, **Дзен**, Одноклассники |
| Google Analytics / GA4 | **Яндекс.Метрика** (GA4 опционально) |
| Email (Mailchimp/ConvertKit) | **Unisender / Sendsay / DashaMail** |
| Биллинг (Stripe) | **ЮKassa / СБП / эквайринг банка** |
| Каталоги (G2, Capterra, Product Hunt) | **2ГИС, Яндекс.Бизнес, Яндекс.Услуги**, профильные РФ-каталоги стройматериалов |
| Отзывы (Google Reviews, Trustpilot) | **Яндекс.Карты, 2ГИС, Отзовик, Яндекс.Маркет** |
| ASO (App Store / Google Play) | + **RuStore** |
| Cold email/нормы | РФ-реалии: 152-ФЗ (перс. данные), закон о рекламе; B2B чаще через звонки/мессенджеры |
| Reviews-генерация | только реальные (Яндекс/2ГИС жёстко фильтруют накрутку) |

Контентные, CRO и исследовательские скиллы переносятся почти без изменений —
адаптируй только примеры каналов и tone of voice (для emwoody — из `CLAUDE.md`).

---

## Карта: фаза seo-cycle → marketing-skill → когда

| Фаза / момент | marketing-skill | Зачем | РФ-нюанс |
|---|---|---|---|
| Phase 0-1 (discovery/audit) | `customer-research`, `competitor-profiling`, `marketing-psychology` | сегменты, боли, позиционирование | B2C+B2B (частник/бригада/закупщик) |
| Phase 5 (content plan) | `content-strategy`, `marketing-ideas` | идеи и воронка контента | TOFU/MOFU/BOFU под РФ-аудиторию |
| Phase 6 (writing) | `copywriting`, `copy-editing` | усиление текстов | tone из CLAUDE.md приоритетнее дефолтов скилла |
| Phase 7 (publishing) | `page-cro`, `form-cro`, `popup-cro` | конверсия карточек/категорий/форм заявки | формы под звонок/СБП/самовывоз |
| Phase 9-10 (monitoring/iteration) | `analytics-tracking`, `ab-test-setup`, `churn-prevention` | замеры, A/B, удержание | трекинг через **Метрику** |
| Вне цикла — привлечение | `paid-ads`, `ad-creative`, `launch-strategy` | платный трафик | **Яндекс.Директ / VK** вместо Google/Meta |
| Вне цикла — удержание/LTV | `referral-program`, `email-sequence`, `lead-magnets`, `pricing-strategy` | повторные продажи, опт | ESP РФ; опт-условия для бригад |
| Локальное привлечение | `directory-submissions`, `community-marketing` | каталоги, сообщества | **2ГИС/Яндекс.Бизнес** + профильные РФ-площадки; см. `prompts/local/` |

## Что НЕ использовать как основное (дубли — у нас глубже + под РФ)
`marketing-skills:seo-audit`, `ai-seo`, `programmatic-seo`, `schema-markup`,
`site-architecture` — пересекаются с `claude-seo` и `seo-cycle`. Бери идеи, но
SEO-workflow веди через seo-cycle (Яндекс-приоритет, региональные профили, E-E-A-T).

## Связка ценности
`seo-cycle` (органика + локальное SEO) → трафик → `marketing-skills:page-cro/form-cro`
(конверсия) → `referral-program/email-sequence` (удержание, повторные продажи).
Каналы привлечения — всегда через РФ-стек (таблица выше).
