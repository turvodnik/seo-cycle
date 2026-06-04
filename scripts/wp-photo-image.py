#!/usr/bin/env python3
"""Prepare photo-style SEO images and optionally upload them to WordPress.

The tool is deterministic by design: it takes a local image or HTTP(S) URL,
center-crops it to a configured ratio, converts it to WebP, and can upload the
result through SSH/WP-CLI. Defaults can come from `seo-cycle.yaml` (`images.*`),
CLI args, or a JSON manifest.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

try:
    import yaml
except ImportError:  # pragma: no cover - optional until --config is used
    yaml = None

try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover - reported only when processing images
    Image = None
    ImageOps = None


CONFIG_SEARCH_PATHS = [
    "seo-cycle.yaml",
    ".seo-cycle.yaml",
    "seo/seo-cycle.yaml",
    ".claude/seo-cycle.yaml",
]

PRESET_RATIO_ALIASES = {
    "featured": ("featured", "hero", "article_inline"),
    "hero": ("hero", "featured", "article_inline"),
    "inline": ("article_inline", "inline", "featured"),
    "article_inline": ("article_inline", "inline", "featured"),
    "og": ("og", "featured"),
    "icon": ("icon",),
}


def require_pillow() -> None:
    if Image is None or ImageOps is None:
        raise RuntimeError("Pillow is required: python3 -m pip install pillow")


def find_config(start_dir: Path) -> Path | None:
    for rel in CONFIG_SEARCH_PATHS:
        candidate = start_dir / rel
        if candidate.exists():
            return candidate
    return None


def load_config(path: str | None) -> dict[str, Any]:
    if yaml is None:
        if path:
            raise RuntimeError("PyYAML is required for --config: python3 -m pip install pyyaml")
        return {}

    cfg_path = Path(path).expanduser() if path else find_config(Path.cwd())
    if not cfg_path:
        return {}
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise RuntimeError(f"Config is not a YAML object: {cfg_path}")
    return data


def load_env(path: Path) -> dict[str, str]:
    data = dict(os.environ)
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return data


def parse_ratio(value: str) -> float:
    if ":" in value:
        left, right = value.split(":", 1)
        return float(left) / float(right)
    return float(value)


def is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def download_source(source: str, tmp_dir: Path) -> Path:
    if not is_url(source):
        path = Path(source).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Source file not found: {path}")
        return path

    suffix = Path(urlparse(source).path).suffix or ".img"
    out = tmp_dir / f"source{suffix}"
    req = Request(source, headers={"User-Agent": "Mozilla/5.0 Chrome/125 Safari/537.36"})
    with urlopen(req, timeout=60) as response:
        out.write_bytes(response.read())
    return out


def center_crop_box(width: int, height: int, ratio: float) -> tuple[int, int, int, int]:
    current = width / height
    if abs(current - ratio) < 0.0001:
        return (0, 0, width, height)
    if current > ratio:
        new_width = int(height * ratio)
        left = (width - new_width) // 2
        return (left, 0, left + new_width, height)
    new_height = int(width / ratio)
    top = (height - new_height) // 2
    return (0, top, width, top + new_height)


def get_image_defaults(cfg: dict[str, Any], preset: str) -> dict[str, Any]:
    images = cfg.get("images", {}) if isinstance(cfg.get("images"), dict) else {}
    output = images.get("output", {}) if isinstance(images.get("output"), dict) else {}
    upload = images.get("upload", {}) if isinstance(images.get("upload"), dict) else {}
    presets = images.get("presets", {}) if isinstance(images.get("presets"), dict) else {}
    preset_cfg = presets.get(preset, {}) if isinstance(presets.get(preset), dict) else {}
    ratios = images.get("aspect_ratios", {}) if isinstance(images.get("aspect_ratios"), dict) else {}

    ratio = None
    for key in PRESET_RATIO_ALIASES.get(preset, (preset,)):
        if ratios.get(key):
            ratio = ratios[key]
            break

    return {
        "ratio": ratio,
        "width": preset_cfg.get("width") or output.get("width"),
        "quality": preset_cfg.get("quality") or output.get("quality"),
        "out_dir": preset_cfg.get("out_dir") or output.get("dir") or images.get("output_dir"),
        "remote_root_env": upload.get("remote_root_env", "WP_REMOTE_ROOT"),
        "env": upload.get("env_file", ".env"),
    }


def pick(record: dict[str, Any], args: argparse.Namespace, defaults: dict[str, Any], key: str, fallback: Any) -> Any:
    value = record.get(key)
    if value is None:
        value = getattr(args, key, None)
    if value is None:
        value = defaults.get(key)
    return fallback if value is None else value


def prepare_image(
    source: str,
    out_dir: Path,
    slug: str,
    ratio: float,
    width: int,
    quality: int,
) -> dict[str, Any]:
    require_pillow()
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="wp-photo-image-") as tmp:
        source_path = download_source(source, Path(tmp))
        image = Image.open(source_path)
        image = ImageOps.exif_transpose(image).convert("RGB")
        original_size = image.size
        image = image.crop(center_crop_box(image.width, image.height, ratio))
        target_height = int(round(width / ratio))
        image = image.resize((width, target_height), Image.Resampling.LANCZOS)

        out_path = out_dir / f"{slug}.webp"
        image.save(out_path, "WEBP", quality=quality, method=6)

    return {
        "source": source,
        "output": str(out_path),
        "original_size": list(original_size),
        "size": [width, target_height],
        "ratio": ratio,
        "quality": quality,
        "bytes": out_path.stat().st_size,
    }


def run_command(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def ssh_commands(env_cfg: dict[str, str]) -> tuple[list[str], list[str], dict[str, str]]:
    required = ["SSH_USER", "SSH_HOST"]
    missing = [key for key in required if not env_cfg.get(key)]
    if missing:
        raise RuntimeError(f"Missing SSH env keys: {', '.join(missing)}")

    port = env_cfg.get("SSH_PORT", "22")
    userhost = f"{env_cfg['SSH_USER']}@{env_cfg['SSH_HOST']}"
    proc_env = os.environ.copy()

    if env_cfg.get("SSH_PASSWORD"):
        if not shutil.which("sshpass"):
            raise RuntimeError("SSH_PASSWORD is set, but sshpass is not installed")
        proc_env["SSHPASS"] = env_cfg["SSH_PASSWORD"]
        ssh = ["sshpass", "-e", "ssh", "-o", "StrictHostKeyChecking=no", "-p", port, userhost]
        scp = ["sshpass", "-e", "scp", "-o", "StrictHostKeyChecking=no", "-P", port]
    else:
        ssh = ["ssh", "-o", "StrictHostKeyChecking=no", "-p", port, userhost]
        scp = ["scp", "-o", "StrictHostKeyChecking=no", "-P", port]

    return ssh, scp, proc_env


def wp_upload(
    local_file: Path,
    env_path: Path,
    remote_root: str,
    title: str,
    alt: str,
    caption: str,
    post_id: int | None,
    set_featured: bool,
) -> dict[str, Any]:
    env_cfg = load_env(env_path)
    ssh, scp, proc_env = ssh_commands(env_cfg)
    userhost = f"{env_cfg['SSH_USER']}@{env_cfg['SSH_HOST']}"
    remote_dir = f"/tmp/wp-photo-image-{int(time.time())}"
    remote_file = f"{remote_dir}/{local_file.name}"

    mkdir = run_command(ssh + [f"mkdir -p {shlex.quote(remote_dir)}"], env=proc_env)
    if mkdir.returncode != 0:
        raise RuntimeError(mkdir.stderr)

    copy = run_command(scp + [str(local_file), f"{userhost}:{remote_file}"], env=proc_env)
    if copy.returncode != 0:
        raise RuntimeError(copy.stderr)

    import_cmd = (
        f"cd {shlex.quote(remote_root)} && "
        f"wp media import {shlex.quote(remote_file)} "
        f"--title={shlex.quote(title)} "
        f"--caption={shlex.quote(caption)} "
        f"--porcelain --allow-root"
    )
    imported = run_command(ssh + [import_cmd], env=proc_env)
    if imported.returncode != 0:
        raise RuntimeError(imported.stderr)
    media_id = int(imported.stdout.strip().splitlines()[-1])

    meta_cmd = (
        f"cd {shlex.quote(remote_root)} && "
        f"wp post meta update {media_id} _wp_attachment_image_alt {shlex.quote(alt)} --allow-root >/dev/null && "
        f"wp post update {media_id} "
        f"--post_title={shlex.quote(title)} "
        f"--post_excerpt={shlex.quote(caption)} --allow-root >/dev/null && "
        f"wp eval {shlex.quote('echo wp_get_attachment_url(' + str(media_id) + ');')} --allow-root"
    )
    meta = run_command(ssh + [meta_cmd], env=proc_env)
    if meta.returncode != 0:
        raise RuntimeError(meta.stderr)
    media_url = meta.stdout.strip()

    featured_result: dict[str, Any] | None = None
    if post_id and set_featured:
        featured_cmd = (
            f"cd {shlex.quote(remote_root)} && "
            f"old=$(wp post meta get {post_id} _thumbnail_id --allow-root); "
            f"wp post meta update {post_id} _thumbnail_id {media_id} --allow-root >/dev/null; "
            f"printf '%s' \"$old\""
        )
        featured = run_command(ssh + [featured_cmd], env=proc_env)
        if featured.returncode != 0:
            raise RuntimeError(featured.stderr)
        featured_result = {
            "post_id": post_id,
            "previous_thumbnail_id": featured.stdout.strip(),
            "thumbnail_id": media_id,
        }

    return {
        "media_id": media_id,
        "media_url": media_url,
        "remote_file": remote_file,
        "featured": featured_result,
    }


def process_record(record: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    source = record.get("source")
    slug = record.get("slug")
    if not source or not slug:
        raise ValueError("Each job requires source and slug")

    preset = str(record.get("preset") or args.preset or "inline")
    defaults = get_image_defaults(args.config_data, preset)
    ratio_text = str(pick(record, args, defaults, "ratio", "16:9"))
    width = int(pick(record, args, defaults, "width", 1200))
    quality = int(pick(record, args, defaults, "quality", 86))
    out_dir = Path(str(pick(record, args, defaults, "out_dir", "seo/generated-images")))

    upload = bool(record.get("upload", args.upload))
    set_featured = bool(record.get("set_featured", args.set_featured))
    post_id = record.get("post_id", args.post_id)
    if set_featured and not post_id:
        raise ValueError(f"{slug}: set_featured requires post_id")
    if upload:
        for field in ["title", "alt", "caption"]:
            if not str(record.get(field, getattr(args, field, ""))).strip():
                raise ValueError(f"{slug}: upload requires {field}")

    prepared = prepare_image(
        source=str(source),
        out_dir=out_dir,
        slug=str(slug),
        ratio=parse_ratio(ratio_text),
        width=width,
        quality=quality,
    )

    result: dict[str, Any] = {"preset": preset, "prepared": prepared}
    if upload:
        env_path = Path(str(pick(record, args, defaults, "env", ".env")))
        env_cfg = load_env(env_path)
        remote_root_env = str(pick(record, args, defaults, "remote_root_env", "WP_REMOTE_ROOT"))
        remote_root = str(record.get("remote_root") or args.remote_root or env_cfg.get(remote_root_env, "")).strip()
        if not remote_root:
            raise ValueError(f"{slug}: upload requires --remote-root or {remote_root_env} in {env_path}")
        result["wordpress"] = wp_upload(
            local_file=Path(prepared["output"]),
            env_path=env_path,
            remote_root=remote_root,
            title=str(record.get("title", args.title)),
            alt=str(record.get("alt", args.alt)),
            caption=str(record.get("caption", args.caption)),
            post_id=int(post_id) if post_id else None,
            set_featured=set_featured,
        )
    return result


def read_manifest(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        defaults = data.get("defaults", {})
        items = data.get("items", [])
        if not isinstance(defaults, dict) or not isinstance(items, list):
            raise ValueError("Manifest object must contain object defaults and list items")
        merged = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Every manifest item must be an object")
            merged.append({**defaults, **item})
        return merged
    raise ValueError("--manifest must contain a JSON list or {defaults, items}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare and upload photo-style WordPress images.")
    parser.add_argument("--source", help="Local image path or HTTP(S) URL.")
    parser.add_argument("--slug", help="Output basename without extension.")
    parser.add_argument("--manifest", help="JSON file: list or {defaults, items}.")
    parser.add_argument("--manifest-out", help="Write batch results JSON to this path.")
    parser.add_argument("--config", help="Path to seo-cycle.yaml. If omitted, standard locations are searched.")
    parser.add_argument("--preset", default="inline", help="Config preset: featured, inline, og, icon, hero.")
    parser.add_argument("--out-dir", help="Directory for prepared WebP.")
    parser.add_argument("--ratio", help="Crop ratio, e.g. 16:9 or 1.777. Defaults to images.aspect_ratios.*.")
    parser.add_argument("--width", type=int, help="Output width in pixels. Defaults to images.output.width.")
    parser.add_argument("--quality", type=int, help="WebP quality. Defaults to images.output.quality.")
    parser.add_argument("--title", default="", help="WordPress media title.")
    parser.add_argument("--alt", default="", help="WordPress alt text.")
    parser.add_argument("--caption", default="", help="WordPress media caption.")
    parser.add_argument("--upload", action="store_true", help="Upload to WordPress through SSH/WP-CLI.")
    parser.add_argument("--post-id", type=int, help="Post ID for featured image assignment.")
    parser.add_argument("--set-featured", action="store_true", help="Set uploaded image as post featured image.")
    parser.add_argument("--env", help="Env file with SSH_* and WP_REMOTE_ROOT values. Defaults to images.upload.env_file.")
    parser.add_argument("--remote-root", help="Remote WordPress root. Prefer env var configured by images.upload.remote_root_env.")
    parser.add_argument("--remote-root-env", help="Env var name containing the remote WordPress root.")
    parser.add_argument("--json-out", help="Write result JSON to this path.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.config_data = load_config(args.config)

    if args.manifest:
        result = [process_record(item, args) for item in read_manifest(Path(args.manifest))]
        output = json.dumps(result, ensure_ascii=False, indent=2)
        if args.manifest_out:
            Path(args.manifest_out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.manifest_out).write_text(output + "\n", encoding="utf-8")
        print(output)
        return 0

    if not args.source or not args.slug:
        raise SystemExit("--source and --slug are required unless --manifest is used")
    if args.set_featured and not args.post_id:
        raise SystemExit("--set-featured requires --post-id")

    result = process_record(vars(args), args)
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
