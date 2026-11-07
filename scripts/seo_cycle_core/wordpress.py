"""WordPress REST API client (3.2.0): Application Password auth, stdlib only.

One place for the HTTP details that `wp-content-pull.py` (read) and
`wp-publish.py` (write) share. Credentials come from the environment the
`seo-cycle` launcher builds (`env_chain`: process env from `ai-secret run`,
then legacy `.env`): `WP_BASE_URL`, `WP_USER`, `WP_APP_PASSWORD`.

Errors are `WPError` with a one-line, operator-readable message — 401 names
the Application Password, a missing route names the REST API — never a
traceback for the CLI to print.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import pathlib
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

USER_AGENT = "seo-cycle wordpress"
ENV_NAMES = ("WP_BASE_URL", "WP_USER", "WP_APP_PASSWORD")

# Per-plugin post meta keys for the SEO title / description. They are written
# through the REST `meta` field, which only works when the plugin (or a small
# snippet) registers them with `show_in_rest`; an unregistered key is dropped
# by WordPress silently — `upsert` reports that back as a warning.
SEO_META_KEYS: dict[str, tuple[str, str]] = {
    "yoast": ("_yoast_wpseo_title", "_yoast_wpseo_metadesc"),
    "rankmath": ("rank_math_title", "rank_math_description"),
    "seopress": ("_seopress_titles_title", "_seopress_titles_desc"),
}


class WPError(Exception):
    """A WordPress call failed; `str()` is a ready one-line message."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def credentials(env: dict[str, str] | None = None) -> dict[str, str]:
    source = os.environ if env is None else env
    return {
        "base_url": str(source.get("WP_BASE_URL", "")).strip().rstrip("/"),
        "user": str(source.get("WP_USER", "")).strip(),
        # Application Passwords are shown with spaces; WordPress accepts both.
        "app_password": str(source.get("WP_APP_PASSWORD", "")).replace(" ", ""),
    }


def missing_credentials(env: dict[str, str] | None = None) -> list[str]:
    creds = credentials(env)
    pairs = zip(ENV_NAMES, (creds["base_url"], creds["user"], creds["app_password"]), strict=True)
    return [name for name, value in pairs if not value]


def seo_meta(plugin: str, title: str, description: str) -> dict[str, str]:
    keys = SEO_META_KEYS.get(str(plugin or "").strip().lower())
    if not keys:
        return {}
    meta: dict[str, str] = {}
    if title:
        meta[keys[0]] = title
    if description:
        meta[keys[1]] = description
    return meta


def _describe(status: int, body: str, url: str) -> str:
    code = ""
    message = ""
    try:
        payload = json.loads(body)
        if isinstance(payload, dict):
            code = str(payload.get("code") or "")
            message = str(payload.get("message") or "")
    except (json.JSONDecodeError, ValueError):
        message = body.strip()[:160]
    if status == 401 or code in ("rest_not_logged_in", "incorrect_password", "invalid_username"):
        hint = "проверь WP_USER и Application Password (seo-cycle auth login wordpress)"
    elif status == 403:
        hint = "у пользователя нет прав на это действие (нужна роль Editor/Administrator)"
    elif status == 404 and code == "rest_no_route":
        hint = "REST API недоступен по этому адресу — проверь WP_BASE_URL и что REST не отключён плагином"
    elif status == 404:
        hint = "объект не найден"
    else:
        hint = message or "ошибка WordPress"
    detail = f" ({code}: {message})" if code and message and hint != message else ""
    return f"WordPress {status} {url}: {hint}{detail}"


class WPClient:
    def __init__(self, base_url: str, user: str = "", app_password: str = "", *, timeout: float = 60) -> None:
        if not base_url:
            raise WPError("не задан WP_BASE_URL")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if user and app_password:
            token = base64.b64encode(f"{user}:{app_password}".encode("utf-8")).decode("ascii")
            self.headers["Authorization"] = f"Basic {token}"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None, *, timeout: float = 60) -> "WPClient":
        creds = credentials(env)
        return cls(creds["base_url"], creds["user"], creds["app_password"], timeout=timeout)

    def api_url(self, route: str, query: dict[str, Any] | None = None) -> str:
        url = f"{self.base_url}/wp-json/{route.lstrip('/')}"
        if query:
            url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
        return url

    def request(
        self,
        method: str,
        url: str,
        *,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[Any, dict[str, str]]:
        req = urllib.request.Request(url, data=data, method=method, headers={**self.headers, **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                resp_headers = {key: value for key, value in resp.headers.items()}
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            raise WPError(_describe(exc.code, body, url), exc.code) from None
        except urllib.error.URLError as exc:
            raise WPError(f"WordPress недоступен ({url}): {exc.reason}") from None
        except (TimeoutError, OSError) as exc:
            raise WPError(f"WordPress не ответил ({url}): {exc}") from None
        if not raw.strip():
            return None, resp_headers
        try:
            return json.loads(raw), resp_headers
        except json.JSONDecodeError:
            raise WPError(f"WordPress вернул не JSON ({url}): {raw.strip()[:120]}") from None

    def get(self, route: str, query: dict[str, Any] | None = None) -> tuple[Any, dict[str, str]]:
        return self.request("GET", self.api_url(route, query))

    def post(self, route: str, payload: dict[str, Any]) -> Any:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        body, _headers = self.request("POST", self.api_url(route), data=data,
                                      headers={"Content-Type": "application/json; charset=utf-8"})
        return body

    def list_items(self, rest_base: str, *, status: str = "publish", fields: str | None = None,
                   max_pages: int = 10) -> list[dict[str, Any]]:
        """Paginated GET of a collection (`posts`, `pages`, a CPT rest_base)."""
        items: list[dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            try:
                batch, headers = self.get(f"wp/v2/{rest_base}",
                                          {"per_page": 100, "page": page, "status": status, "_fields": fields})
            except WPError as exc:
                if exc.status == 400 and page > 1:  # past the last page
                    break
                raise
            if not isinstance(batch, list) or not batch:
                break
            items.extend(item for item in batch if isinstance(item, dict))
            if page >= int(headers.get("X-WP-TotalPages") or headers.get("x-wp-totalpages") or "1"):
                break
        return items

    def find_by_slug(self, rest_base: str, slug: str) -> dict[str, Any] | None:
        """Any status (needs auth for drafts): the first item with this slug."""
        found, _headers = self.get(f"wp/v2/{rest_base}",
                                   {"slug": slug, "status": "any", "context": "edit", "_fields": "id,slug,link,status"})
        if isinstance(found, list):
            for item in found:
                if isinstance(item, dict) and item.get("slug") == slug:
                    return item
        return None

    def get_item(self, rest_base: str, item_id: int) -> dict[str, Any] | None:
        try:
            item, _headers = self.get(f"wp/v2/{rest_base}/{item_id}", {"context": "edit", "_fields": "id,slug,link,status"})
        except WPError as exc:
            if exc.status in (404, 410):
                return None
            raise
        return item if isinstance(item, dict) else None

    def upsert(self, rest_base: str, payload: dict[str, Any], existing_id: int | None = None) -> dict[str, Any]:
        route = f"wp/v2/{rest_base}/{existing_id}" if existing_id else f"wp/v2/{rest_base}"
        result = self.post(route, payload)
        if not isinstance(result, dict) or not result.get("id"):
            raise WPError(f"WordPress не вернул id после записи в {rest_base}")
        return result

    def upload_media(self, path: pathlib.Path, *, alt: str = "", caption: str = "", title: str = "") -> dict[str, Any]:
        data = path.read_bytes()
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        filename = urllib.parse.quote(path.name)
        body, _headers = self.request(
            "POST", self.api_url("wp/v2/media"), data=data,
            headers={"Content-Type": mime, "Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
        )
        if not isinstance(body, dict) or not body.get("id"):
            raise WPError(f"WordPress не вернул id медиа для {path.name}")
        fields = {key: value for key, value in (("alt_text", alt), ("caption", caption), ("title", title)) if value}
        if fields:
            updated = self.post(f"wp/v2/media/{body['id']}", fields)
            if isinstance(updated, dict):
                body = {**body, **updated}
        return body

    def fetch_page(self, url: str) -> str:
        """GET a public page (not the API) — for verification after publishing."""
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise WPError(f"страница {url} ответила {exc.code}", exc.code) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise WPError(f"страница {url} недоступна: {exc}") from None
