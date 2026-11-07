"""A tiny in-memory WordPress REST server for tests (3.2.0).

Implements just what seo_cycle_core.wordpress / wp-publish.py call:
GET/POST /wp-json/wp/v2/<type>[/<id>] (slug filter, pagination headers),
POST /wp-json/wp/v2/media (+ PATCH-by-POST of alt/caption), public page GET
at each item's link, Basic auth with one user/password. Runs on 127.0.0.1
in a daemon thread; `requests` records every call for assertions.
"""

from __future__ import annotations

import base64
import json
import re
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class FakeWordPress:
    def __init__(self, user: str = "editor", password: str = "abcd efgh ijkl") -> None:
        self.user = user
        self.password = password.replace(" ", "")
        self.items: dict[str, dict[int, dict[str, Any]]] = {"posts": {}, "pages": {}, "media": {}}
        self.requests: list[tuple[str, str]] = []
        self.next_id = 100
        self.drop_meta = False          # simulate a plugin that does not expose meta in REST
        self.page_html_override: str | None = None
        self.lock = threading.Lock()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:  # silence
                return

            def _auth_ok(self) -> bool:
                header = self.headers.get("Authorization", "")
                if not header.startswith("Basic "):
                    return False
                user, _, password = base64.b64decode(header[6:]).decode("utf-8").partition(":")
                return user == fake.user and password == fake.password

            def _send(self, status: int, body: Any, headers: dict[str, str] | None = None,
                      content_type: str = "application/json") -> None:
                raw = body if isinstance(body, bytes) else (json.dumps(body, ensure_ascii=False).encode("utf-8")
                                                            if not isinstance(body, str) else body.encode("utf-8"))
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self) -> None:  # noqa: N802
                fake.requests.append(("GET", self.path))
                parsed = urllib.parse.urlparse(self.path)
                query = dict(urllib.parse.parse_qsl(parsed.query))
                match = re.fullmatch(r"/wp-json/wp/v2/(\w+)(?:/(\d+))?", parsed.path)
                if not match:
                    for store in fake.items.values():
                        for item in store.values():
                            if urllib.parse.urlparse(item.get("link", "")).path == parsed.path:
                                html = fake.page_html_override if fake.page_html_override is not None else fake.render_page(item)
                                return self._send(200, html, content_type="text/html; charset=utf-8")
                    return self._send(404, {"code": "rest_no_route", "message": "No route"})
                rest_base, item_id = match.group(1), match.group(2)
                store = fake.items.get(rest_base)
                if store is None:
                    return self._send(404, {"code": "rest_no_route", "message": "No route was found"})
                wants_private = query.get("status") in ("any", "draft") or query.get("context") == "edit"
                if wants_private and not self._auth_ok():
                    return self._send(401, {"code": "rest_not_logged_in", "message": "not logged in"})
                if item_id:
                    item = store.get(int(item_id))
                    return self._send(200, item) if item else self._send(404, {"code": "rest_post_invalid_id", "message": "Invalid id"})
                rows = list(store.values())
                if "slug" in query:
                    rows = [row for row in rows if row.get("slug") == query["slug"]]
                if query.get("status") == "publish":
                    rows = [row for row in rows if row.get("status") == "publish"]
                per_page = int(query.get("per_page", 10))
                page = int(query.get("page", 1))
                pages = max(1, -(-len(rows) // per_page))
                if page > pages and page > 1:
                    return self._send(400, {"code": "rest_post_invalid_page_number", "message": "bad page"})
                chunk = rows[(page - 1) * per_page: page * per_page]
                return self._send(200, chunk, {"X-WP-TotalPages": str(pages), "X-WP-Total": str(len(rows))})

            def do_POST(self) -> None:  # noqa: N802
                fake.requests.append(("POST", self.path))
                if not self._auth_ok():
                    return self._send(401, {"code": "rest_cannot_create", "message": "Sorry, you are not allowed"})
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length)
                parsed = urllib.parse.urlparse(self.path)
                match = re.fullmatch(r"/wp-json/wp/v2/(\w+)(?:/(\d+))?", parsed.path)
                if not match or match.group(1) not in fake.items:
                    return self._send(404, {"code": "rest_no_route", "message": "No route"})
                rest_base, item_id = match.group(1), match.group(2)
                with fake.lock:
                    if rest_base == "media" and not item_id:
                        disposition = self.headers.get("Content-Disposition", "")
                        name = urllib.parse.unquote(disposition.split("''")[-1]) if "''" in disposition else "file"
                        new_id = fake.next_id
                        fake.next_id += 1
                        item = {"id": new_id, "source_url": f"http://{self.headers['Host']}/uploads/{name}",
                                "media_type": "image", "bytes": len(raw), "alt_text": "", "caption": {"raw": ""}}
                        fake.items["media"][new_id] = item
                        return self._send(201, item)
                    payload = json.loads(raw.decode("utf-8") or "{}")
                    if item_id:
                        item = fake.items[rest_base].get(int(item_id))
                        if not item:
                            return self._send(404, {"code": "rest_post_invalid_id", "message": "Invalid post ID."})
                    else:
                        new_id = fake.next_id
                        fake.next_id += 1
                        item = {"id": new_id, "type": "post" if rest_base == "posts" else rest_base}
                        fake.items[rest_base][new_id] = item
                    if fake.drop_meta:
                        payload.pop("meta", None)
                    for key, value in payload.items():
                        if key == "caption" and rest_base == "media":
                            item["caption"] = {"raw": value}
                        elif key == "meta":
                            item.setdefault("meta", {}).update(value)
                        else:
                            item[key] = value
                    slug = item.get("slug") or f"item-{item['id']}"
                    item["slug"] = slug
                    item["link"] = f"http://{self.headers['Host']}/{slug}/"
                    item.setdefault("status", "draft")
                    return self._send(201 if not item_id else 200, item)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def start(self) -> "FakeWordPress":
        self.thread.start()
        return self

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def env(self) -> dict[str, str]:
        return {"WP_BASE_URL": self.base_url, "WP_USER": self.user, "WP_APP_PASSWORD": "abcd efgh ijkl"}

    @staticmethod
    def render_page(item: dict[str, Any]) -> str:
        title = item.get("title", "")
        if isinstance(title, dict):
            title = title.get("raw") or title.get("rendered") or ""
        content = item.get("content", "")
        if isinstance(content, dict):
            content = content.get("raw") or content.get("rendered") or ""
        return f"<html><head><title>{title}</title></head><body><h1>{title}</h1>{content}</body></html>"

    def writes(self, prefix: str) -> list[tuple[str, str]]:
        return [call for call in self.requests if call[0] == "POST" and call[1].startswith(prefix)]
