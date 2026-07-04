#!/usr/bin/env python3
"""Local OAuth helper for Google Business Profile: mint a refresh token.

Google's OAuth verification for the business.manage scope is a human process
(see docs/gbp-oauth-verification.md for the runbook). Once your OAuth client
exists — even in "Testing" mode with your own account added as a test user —
this helper performs the standard authorization-code dance locally:

  1. prints the authorization URL (offline access, business.manage scope);
  2. catches the redirect on http://localhost:<port> with a tiny stdlib server;
  3. exchanges the code and prints the REFRESH TOKEN to stderr once — copy it
     into .env as GBP_OAUTH_REFRESH_TOKEN yourself; nothing is written to disk
     unless you pass --write-env <path>, which upserts the variable into that
     env file (0600) and never displays the value.

Requires GBP_OAUTH_CLIENT_ID and GBP_OAUTH_CLIENT_SECRET in the environment
(create a "Desktop app" or "Web" client with http://localhost redirect).
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import pathlib
import sys
import threading
import urllib.parse
import urllib.request

from seo_cycle_core.env_profile import upsert_env_var

SCOPE = "https://www.googleapis.com/auth/business.manage"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


class CodeCatcher(http.server.BaseHTTPRequestHandler):
    code: str | None = None
    error: str | None = None

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        CodeCatcher.code = (query.get("code") or [None])[0]
        CodeCatcher.error = (query.get("error") or [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        message = "Готово — вернитесь в терминал." if CodeCatcher.code else f"Ошибка: {CodeCatcher.error}"
        self.wfile.write(f"<h2>{message}</h2>".encode("utf-8"))

    def log_message(self, *args) -> None:  # silence request logging
        return


def exchange_code(code: str, client_id: str, client_secret: str, redirect_uri: str) -> dict:
    body = urllib.parse.urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode("utf-8")
    req = urllib.request.Request(TOKEN_URL, data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8765, help="Localhost port for the redirect")
    parser.add_argument("--print-url-only", action="store_true",
                        help="Only print the authorization URL (paste the redirect URL manually)")
    parser.add_argument("--redirect-url", help="With --print-url-only: paste the full redirect URL here to finish")
    parser.add_argument("--write-env", metavar="PATH",
                        help="Save GBP_OAUTH_REFRESH_TOKEN into this env file (0600) instead of displaying it")
    args = parser.parse_args()

    client_id = os.environ.get("GBP_OAUTH_CLIENT_ID", "")
    client_secret = os.environ.get("GBP_OAUTH_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        print("ERROR: set GBP_OAUTH_CLIENT_ID and GBP_OAUTH_CLIENT_SECRET env first "
              "(Google Cloud Console → Credentials → OAuth client).", file=sys.stderr)
        return 2

    redirect_uri = f"http://localhost:{args.port}"
    auth_url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
    })

    if args.redirect_url:
        query = urllib.parse.parse_qs(urllib.parse.urlparse(args.redirect_url).query)
        code = (query.get("code") or [None])[0]
        if not code:
            print("ERROR: no ?code= in the pasted URL", file=sys.stderr)
            return 2
    else:
        print("1) Откройте в браузере (аккаунт — владелец/менеджер GBP):\n", file=sys.stderr)
        print(auth_url + "\n", file=sys.stderr)
        if args.print_url_only:
            print("2) После согласия скопируйте полный redirect-URL и запустите:\n"
                  f"   python3 scripts/gbp-oauth-helper.py --print-url-only --redirect-url '<url>'",
                  file=sys.stderr)
            return 0
        print(f"2) Жду redirect на {redirect_uri} ...", file=sys.stderr)
        server = http.server.HTTPServer(("localhost", args.port), CodeCatcher)
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()
        thread.join(timeout=300)
        server.server_close()
        if CodeCatcher.error:
            print(f"ERROR: consent screen returned: {CodeCatcher.error}", file=sys.stderr)
            return 1
        code = CodeCatcher.code
        if not code:
            print("ERROR: no authorization code received within 5 minutes", file=sys.stderr)
            return 1

    try:
        tokens = exchange_code(code, client_id, client_secret, redirect_uri)
    except urllib.error.URLError as exc:
        print(f"ERROR: token exchange failed: {exc}", file=sys.stderr)
        return 1
    refresh = tokens.get("refresh_token")
    if not refresh:
        print("ERROR: no refresh_token in the response (re-run with prompt=consent; "
              "check that access_type=offline was preserved)", file=sys.stderr)
        return 1
    if args.write_env:
        import datetime as dt

        target = upsert_env_var(pathlib.Path(args.write_env).expanduser(), "GBP_OAUTH_REFRESH_TOKEN", refresh)
        upsert_env_var(target, "GBP_TOKEN_MINTED_AT", dt.date.today().isoformat())
        print(f"\n✓ GBP_OAUTH_REFRESH_TOKEN сохранён в {target} (0600); значение не показывается.\n"
              "Дата минта записана в GBP_TOKEN_MINTED_AT (в Testing-режиме токен живёт 7 дней).\n"
              "Проверка: python3 scripts/gbp-health.py && python3 scripts/gbp-fetch.py --report locations --live",
              file=sys.stderr)
        return 0
    print("\n✓ REFRESH TOKEN (показывается один раз, никуда не сохранён):\n", file=sys.stderr)
    print(refresh, file=sys.stderr)
    print("\nДобавьте в .env проекта: GBP_OAUTH_REFRESH_TOKEN=<значение>\n"
          "Проверка: python3 scripts/gbp-health.py && python3 scripts/gbp-fetch.py --report locations --live",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
