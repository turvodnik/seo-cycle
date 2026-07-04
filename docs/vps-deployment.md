# VPS и долгоживущие агенты: чтобы работа не останавливалась

Задача: автоматизация (monthly-циклы, мониторинг, очереди) продолжает крутиться,
когда ноутбук закрыт, а агентские сессии не «умирают» посреди работы.

## Что выносить на VPS, а что нет

| Выносим | Оставляем на рабочей машине |
|---|---|
| `monthly-runner.sh --all` по расписанию | Браузерные шаги (Perplexity/NotebookLM/WriterZen collect, GSC browser export) |
| `seo-cycle db` + снапшоты мониторинга (gsc/metrika/psi fetch) | Approvals — решения принимает человек |
| `position-progress --global --write` (портфельная сводка) | GBP OAuth-flow (нужен браузер владельца) |
| `rag index --write` после новых артефактов | Всё, что требует macOS-приложений |
| Telegram-уведомления (`notify.py`) — алерты придут сами | |

Правило: на VPS — только guarded-скрипты с кэшем/ledger; всё платное остаётся
за `--live`-флагами и approval-тикетами, как и локально.

## Минимальный VPS (1 vCPU / 1 GB достаточно)

```bash
# 1. Python 3.11+ и git
apt update && apt install -y python3 python3-pip git
pip3 install pyyaml pydantic

# 2. Репо скилла + проекты
git clone https://github.com/turvodnik/seo-cycle ~/.codex/skills/seo-cycle
git clone <репо проекта> ~/projects/<name>          # seo-cycle.yaml внутри

# 3. Ключи: глобальный профиль агентства (0600)
mkdir -p ~/.seo-cycle && touch ~/.seo-cycle/env.global && chmod 600 ~/.seo-cycle/env.global
# заполнить: ~/.codex/skills/seo-cycle/scripts/auth-assistant.py set YANDEX_OAUTH_TOKEN --global
# клиентские ключи проекта — в .env проекта (auth-assistant.py set ... без --global)

# 4. Реестр проектов
cp ~/.codex/skills/seo-cycle/config/projects-registry.yaml ~/.seo-cycle/  # и правьте пути
```

## Расписание: systemd timer (надёжнее cron)

`/etc/systemd/system/seo-monthly.service`:

```ini
[Unit]
Description=seo-cycle monthly automation

[Service]
Type=oneshot
User=seo
WorkingDirectory=/home/seo/projects/<name>
ExecStart=/home/seo/.codex/skills/seo-cycle/bin/seo-cycle run monthly
```

`/etc/systemd/system/seo-monthly.timer`:

```ini
[Timer]
OnCalendar=Mon 06:00
Persistent=true          # догоняет пропущенные запуски после ребута

[Install]
WantedBy=timers.target
```

`systemctl enable --now seo-monthly.timer`. Логи: `journalctl -u seo-monthly` +
файловые `seo/logs/seo-cycle-YYYY-MM-DD.log`.

Аналогично — ежедневный `seo-cycle db && seo-cycle progress --write` и
еженедельный `position-progress --global --write` для портфеля.

## Долгоживущие агентские сессии (Claude Code / Codex CLI)

- **tmux** — сессия переживает разрыв SSH: `tmux new -s seo` → работа →
  `Ctrl-b d`; вернуться: `tmux attach -t seo`. Это главный инструмент «агент
  не закрылся, пока что-то происходит».
- **Headless-прогоны** по расписанию: `claude -p "запусти monthly для <проекта>"
  --permission-mode acceptEdits` внутри systemd-сервиса (или `codex exec`).
  Всё опасное остаётся за approval-тикетами — агент создаст тикет и пришлёт
  Telegram-алерт, а не сделает сам.
- **Уведомления**: `notifications.enabled: true` + `TELEGRAM_*` в
  `~/.seo-cycle/env.global` — эскалации loop/KPI и approvals приходят в чат,
  отвечать можно с телефона, зайдя по SSH позже.
- На macOS то же самое даёт **launchd** (`~/Library/LaunchAgents/*.plist`) +
  `caffeinate -s` для запусков при закрытой крышке на питании.

## Безопасность

- Секреты только в `.env`/`env.global` (0600); в git они не попадают.
- Отдельный unix-пользователь `seo` без sudo; SSH-ключи вместо паролей.
- `usage-ledger` и `spend-guard` работают и на VPS — бюджеты не улетят.
- Бэкап: `seo/` каталоги проектов (артефакты + seo.db) — в приватный git
  или restic; ключи НЕ бэкапить вместе с данными.

## Частые вопросы

- **«Агент завис/умер посреди»** — journey и cycle-state держат прогресс на
  диске: новый агент читает `seo-cycle status` и продолжает с того же места;
  loop-runner продолжается через `--resume`.
- **«Хочу видеть, что происходит»** — `seo-cycle dashboard`, `seo-cycle
  progress`, `seo/logs/*.log`, Telegram-алерты.
- **«VPS в другой стране, а проект под Яндекс»** — для API это не важно;
  для SERP-снапшотов используйте XMLRiver (регион задаётся параметром).
