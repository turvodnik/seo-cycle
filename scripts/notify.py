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
    python3 notify.py "подпись" --file seo/reports/client-report.pdf   # отправить файл
    python3 notify.py --test               # проверить настройку / отправить пинг
    echo "текст" | python3 notify.py -      # из stdin
"""

from __future__ import annotations
import argparse, json, pathlib, sys, urllib.parse, urllib.request
import uuid

from seo_cycle_core.config import find_config, project_root_for
from seo_cycle_core.env_profile import env_chain, parse_env_file

LEVEL_ICON = {"info": "ℹ️", "warn": "⚠️", "alert": "🔴", "ok": "✅"}


def load_env() -> dict:
    """process env > project .env > ~/.seo-cycle/env.global (+legacy seo/.env)."""
    cfg_path = find_config(pathlib.Path.cwd())
    merged = env_chain(project_root_for(cfg_path) if cfg_path else None)
    legacy = pathlib.Path.cwd() / "seo" / ".env"
    for key, value in parse_env_file(legacy).items():
        merged.setdefault(key, value)
    return merged


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


def send_document(token: str, chat_id: str, path: pathlib.Path, caption: str) -> bool:
    """sendDocument через multipart/form-data на чистом stdlib."""
    boundary = f"----seo-cycle-{uuid.uuid4().hex}"
    payload = b""
    for name, value in (("chat_id", chat_id), ("caption", caption[:1000]), ("parse_mode", "HTML")):
        payload += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n"
                    f"{value}\r\n").encode()
    payload += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; "
                f"filename=\"{path.name}\"\r\nContent-Type: application/octet-stream\r\n\r\n").encode()
    payload += path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendDocument", data=payload,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read()).get("ok", False)
    except Exception as e:
        print(f"[notify] ошибка sendDocument: {e}", file=sys.stderr)
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("message", nargs="?", default="", help="текст ('-' = stdin)")
    ap.add_argument("--title")
    ap.add_argument("--level", choices=["info", "warn", "alert", "ok"], default="info")
    ap.add_argument("--file", action="append", default=[], help="отправить файл(ы) документом")
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
    if not msg and not args.file:
        print("ERROR: пустое сообщение", file=sys.stderr)
        return 2

    icon = LEVEL_ICON.get(args.level, "")
    text = f"{icon} <b>{args.title}</b>\n{msg}" if args.title else f"{icon} {msg}"

    # Graceful no-op: нет токена → печатаем, не ломаем pipeline
    if not token or not chat_id:
        files = f" files={args.file}" if args.file else ""
        print(f"[notify: telegram не настроен] {args.level}: {args.title or ''} {msg}{files}")
        return 0

    if args.file:
        sent_all = True
        for index, raw in enumerate(args.file):
            path = pathlib.Path(raw).expanduser()
            if not path.exists():
                print(f"[notify] файла нет: {path}", file=sys.stderr)
                sent_all = False
                continue
            caption = text if index == 0 else ""
            if not send_document(token, chat_id, path, caption):
                sent_all = False
        if not sent_all:
            print(f"[notify: часть файлов не отправлена] {msg}")
        return 0
    ok = send_telegram(token, chat_id, text)
    if not ok:
        print(f"[notify: не отправлено] {msg}")
    return 0   # никогда не блокируем вызывающий скрипт


if __name__ == "__main__":
    sys.exit(main())
