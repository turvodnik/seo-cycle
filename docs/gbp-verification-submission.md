# GBP verification: пакет для подачи (копипаст-тексты + чек-лист)

Дополнение к [gbp-oauth-verification.md](gbp-oauth-verification.md) (там —
устройство процесса). Здесь — всё, что вставляется в формы при подаче, чтобы
человеческий шаг занял минимум времени. **Testing-режим работает уже сегодня**
(`seo-cycle auth login gbp`); verification нужна, чтобы refresh token жил
дольше 7 дней и не требовал еженедельного повторного логина.

## Шаг 0. Что уже должно быть (см. runbook)

- [ ] Cloud-проект, включены APIs: My Business Business Information,
      My Business Account Management, Google My Business API (v4).
- [ ] OAuth consent screen: External, ваш аккаунт добавлен в Test users.
- [ ] OAuth client (Desktop или Web с `http://localhost`).
- [ ] `seo-cycle auth login gbp` прошёл: gbp-health.py показывает `available`.

## Шаг 1. Квота GBP API (отдельная форма, ДО verification)

Форма: <https://support.google.com/business/contact/api_default> (GBP API
access request). Ответы:

- **Business name**: ваше юрлицо/бренд агентства.
- **Website**: сайт агентства (должен открываться и содержать контакты).
- **Use case** (EN, копипаст, подставьте имя):

> We are a digital marketing agency managing Google Business Profiles on
> behalf of our clients (with their explicit authorization as managers of
> their locations). We request API access to READ location data and reviews
> for reporting: our internal tooling aggregates review velocity, unanswered
> review counts, and profile completeness into monthly client reports.
> We do not auto-post replies or modify profiles programmatically; all
> changes are made by humans in the GBP interface.

- **Estimated queries/day**: 100–500 (честно: по числу проектов × отчёты).

Ответ обычно 1–2 недели. Без одобрения квота = 0 даже с готовым OAuth.

## Шаг 2. OAuth verification (Cloud Console → OAuth consent screen → Publish)

Понадобится:

1. **Privacy policy URL** — страница на сайте агентства. Минимум: какие
   данные читаем (данные профилей GBP клиентов по их поручению), зачем
   (отчётность), кому не передаём (третьим лицам), контакт. 
2. **Scope justification** для `https://www.googleapis.com/auth/business.manage`
   (EN, копипаст):

> Our agency application reads Business Profile location data and reviews of
> client-owned locations that our Google account manages with the owners'
> permission. The business.manage scope is required because the Business
> Profile APIs expose location and review read endpoints only under this
> scope; no narrower scope exists. The application performs read-only
> aggregation for client reporting (review counts, ratings, response status,
> profile fields). It does not create, edit, or delete any profile content.

3. **Демо-видео** (unlisted YouTube, 2–4 минуты). Сценарий:
   - 0:00 — сайт агентства, страница privacy policy (показать URL).
   - 0:30 — экран консента: запуск `seo-cycle auth login gbp`, открывается
     Google-логин, виден запрашиваемый scope, нажимаете Allow.
   - 1:30 — терминал: `python3 scripts/gbp-fetch.py --report locations --live`
     и `--report reviews` — видно, что приложение только читает данные.
   - 2:30 — итоговый артефакт: `seo/gbp/gbp-summary.md` в клиентском отчёте
     (`seo-cycle report`) — «зачем нам эти данные».
4. **App name / logo / домены** на consent screen должны совпадать с сайтом
   из шага 1 (иначе типовой отказ «brand mismatch»).

## Шаг 3. После одобрения

- [ ] Перемонтировать токен без 7-дневного лимита: `seo-cycle auth login gbp`
      (можно `--global`, если аккаунт агентства управляет всеми локациями).
- [ ] Убрать еженедельное напоминание о re-mint, если ставили.
- [ ] `gbp-fetch.py --report reviews --live` в monthly-цикл (read-only).

## Типовые причины отказа (и наши ответы)

| Отказ | Что проверить |
|---|---|
| Homepage requirements | Сайт открывается по HTTPS, есть контакты и описание сервиса |
| Privacy policy | URL живой, упомянуты именно GBP-данные и read-only использование |
| Scope narrower | В justification уже объяснено: у Business Profile APIs нет более узкого read-scope |
| Demo unclear | В видео обязательно виден consent screen с scope и реальный вызов API |
