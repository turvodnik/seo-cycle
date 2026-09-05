# Yandex Business Health

- Generated: <TS>
- Status: `partner_limited` — Публичного API управления карточкой Яндекс.Бизнес нет (Справочник — партнёрский). Это ожидаемое состояние, не ошибка конфигурации.
- Business ID env present: True (YANDEX_MERCHANT_BUSINESS_ID)
- Card links: {"yandex_business": "https://yandex.ru/business/test", "gbp": "https://maps.google.com/test"}

## Working paths
- Браузерный workflow: prompts/local/yandex-maps.md (Chrome MCP) — карточка, рубрики, фото, посты, ответы на отзывы с human review.
- Отзывы: ручная выгрузка/копия из кабинета → анализ в review-velocity.py.
- Товары/цены на картах: фид Яндекс.Товаров — валидируй yml-feed-audit.py.
- Трафик-сигналы: metrika-fetch.py / metrika-logs-fetch.py (переходы с Карт видны как источник).
- 2ГИС: партнёрский API — та же браузерная механика, отдельного скрипта нет намеренно.

## Guardrails
- Никаких live-вызовов в health check.
- Любые изменения карточки — только вручную/браузером с явным подтверждением человека.
- Не хранить пароли; браузерный профиль живёт вне репозитория проекта.

## Official Docs
- https://yandex.ru/support/business/
- https://yandex.ru/dev/sprav/
- https://dev.2gis.ru/
