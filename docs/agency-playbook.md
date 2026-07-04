# Agency playbook: как сотрудник работает с seo-cycle

Один документ вместо устных передач. Три уровня: новый проект → неделя → месяц.
Всё выполняется через `seo-cycle <команда>`, дашборд (`seo-cycle web --open`
или иконка «SEO Cycle») или агентом в Claude Code / Codex («запусти X для проекта Y»).

## Роли

- **Аккаунт/стратег** — смотрит дашборд (Портфель, Проект), решает approvals,
  отправляет клиенту отчёты. Не трогает терминал.
- **Специалист** — ведёт цикл: ресёрч, брифы, качество, публикация. Работает
  агентом + CLI.
- **Владелец** — верификации у платформ (Google OAuth, Директ-доступы),
  бюджеты (`governance`), реестр проектов.

## День 1: новый проект

```bash
seo-cycle init                      # мастер: конфиг, политики, реестр
seo-cycle auth list                 # чего не хватает из доступов
seo-cycle auth login yandex --global   # общие ключи агентства — один раз
seo-cycle auth login wordpress         # клиентские — в проект
seo-cycle doctor                    # всё ли зелёное
seo-cycle status                    # journey скажет первый шаг
```

Дальше ведёт `seo-cycle status`: он всегда показывает текущую стадию,
блокеры и точную следующую команду. Не перепрыгивать стадии.

## Каждая статья (Phase 6)

1. `seo-cycle rag query "<ключ>"` — контекст из своих же материалов.
2. Драфт из copywriter-ready брифа.
3. `seo-cycle loop draft <draft.md> --outline <outline.json>` — автоцикл
   качества (максимум попыток ограничен; exit 3 = доработай по инструкции
   и `--resume`). Оценка запуска сама попадает в scorecards.
4. Публикация — CMS-делегат; индексация — indexnow/gsc queue.
5. `seo-cycle repurpose <draft.md> --write` — TG/VK/видео/email каркасы.

## Неделя

| День | Что | Команда/место |
|---|---|---|
| пн | очередь и публикация | monthly-runner / weekly-publisher агент |
| ср | прогресс позиций | `seo-cycle progress` или вкладка «Проект» |
| чт | approvals ≤ 5 мин | вкладка «Approvals» |
| пт | внешние источники живы? | `seo-cycle links --live` |

Автоматизировать снапшоты: `bash scripts/install-schedule.sh --project <path>`
(daily db+progress, weekly портфель; `--with-monthly` для полного цикла).

## Месяц

1. `seo-cycle run monthly` — 4 системы с approval-гейтами.
2. `seo-cycle crawl --live && seo-cycle structure` — техничка + карта сайта.
3. `seo-cycle intel --write` — SERP-сдвиги: merge/split кластеров, AEO-фичи.
4. `seo-cycle kpi && seo-cycle forecast` — план/факт, при отставании появятся
   corrective actions (и эскалация в Telegram).
5. `seo-cycle report --write --pdf --send` — клиентский отчёт улетает в Telegram.
6. Портфель целиком: вкладка «Портфель» или `seo-cycle progress --global`.

## Правила, которые не обсуждаются

- Платное (XMLRiver/NW/embeddings/ads) — только после `seo-cycle spend` и
  ledger-preflight; расход записывается после.
- Публикация, реклама, индексация, расписания — через approval-тикеты.
- Секреты только в `.env`/`env.global` (0600); в чаты и отчёты не попадают.
- Достоверность: findings класса evidence лечатся источниками, не рерайтом.
- После каждой задачи — самооценка 0–10 (`seo-cycle score record`), честная.

## Где что лежит

`seo/setup/` статус и журналы онбординга · `seo/research-package/` семантика,
брифы, драфты · `seo/loops/` циклы качества · `seo/scorecards/` самооценки ·
`seo/crawl/` краулер и карта структуры · `seo/reports/` клиентские отчёты и
прогресс · `seo/ads/` реклама · `seo/rag.db` знания проекта · `seo/logs/` логи.
Портфельные сводки: `~/.seo-cycle/reports/`.

## Если что-то пошло не так

`seo-cycle doctor` → `docs/troubleshooting.md` → журналы `seo/logs/` →
эскалация-тикет уже в Telegram, если это цикл качества или KPI.
