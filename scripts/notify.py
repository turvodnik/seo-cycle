#!/usr/bin/env python3
"""
notify.py — лёгкие уведомления (Telegram) без отдельной инфраструктуры.
Закрывает «алерты» Этапа 1: просадка позиций, новый approval-тикет, кредиты
API на исходе, ошибка сбора — вызывается из monthly-runner.sh и approval-gate.py.

Намеренно НЕ требует n8n: один скрипт + Telegram Bot API. Если токен не
настроен — graceful no-op (печатает в stdout, exit 0), не ломает pipeline.

Настройка (.env проекта или env):
    TELEGRAM_BOT_TOKEN=123456:ABC...        # от @BotFather
    TELEGRAM_CHAT_ID=123456789              # свой chat id (от @userinfobot)

Использование:
    python3 notify.py "текст сообщения" [--title "Заголовок"] [--level info|warn|alert]
    python3 notify.py --test               # проверить настройку / отправить пинг
    echo "текст" | python3 notify.py -      # из stdin
"""

from __future__ import annotations
import argparse, json, os, pathlib, sys, urllib.parse, urllib.request

LEVEL_ICON = {"info": "ℹ️", "warn": "⚠️", "alert": "🔴", "ok": "✅"}


def load_env() -> dict:
    env = dict(os.environ)
    for rel in (".env", "seo/.env"):
        p = pathlib.Path.cwd() / rel
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return env


def send_telegram(token: str, chat_id: str, text: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id, "text": text,
        "parse_mode": "HTML", "disable_web_page_preview": "true",
    }).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception as e:
        print(f"[notify] ошибка Telegram: {e}", file=sys.stderr)
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("message", nargs="?", default="", help="текст ('-' = stdin)")
    ap.add_argument("--title")
    ap.add_argument("--level", choices=["info", "warn", "alert", "ok"], default="info")
    ap.add_argument("--test", action="store_true")
    args = ap.parse_args()

    env = load_env()
    token = env.get("TELEGRAM_BOT_TOKEN")
    chat_id = env.get("TELEGRAM_CHAT_ID")

    if args.test:
        if not token or not chat_id:
            print("Telegram НЕ настроен. Добавь в .env:\n"
                  "  TELEGRAM_BOT_TOKEN=...  (от @BotFather)\n"
                  "  TELEGRAM_CHAT_ID=...    (от @userinfobot)")
            return 0
        ok = send_telegram(token, chat_id, "✅ <b>notify.py</b>: тестовое сообщение, связь работает.")
        print("Отправлено." if ok else "Не удалось отправить — проверь токен/chat_id.")
        return 0 if ok else 1

    msg = args.message
    if msg == "-":
        msg = sys.stdin.read().strip()
    if not msg:
        print("ERROR: пустое сообщение", file=sys.stderr)
        return 2

    icon = LEVEL_ICON.get(args.level, "")
    text = f"{icon} <b>{args.title}</b>\n{msg}" if args.title else f"{icon} {msg}"

    # Graceful no-op: нет токена → печатаем, не ломаем pipeline
    if not token or not chat_id:
        print(f"[notify: telegram не настроен] {args.level}: {args.title or ''} {msg}")
        return 0

    ok = send_telegram(token, chat_id, text)
    if not ok:
        print(f"[notify: не отправлено] {msg}")
    return 0   # никогда не блокируем вызывающий скрипт


if __name__ == "__main__":
    sys.exit(main())
