#!/usr/bin/env bash
# img-generate.sh — генерация изображения, рантайм-aware.
#
# Usage:
#   img-generate.sh --live "<english_prompt>" <output_filename.png> [<target_dir>] [<ratio>]
#
# --live (T-069) — обязательное согласие на трату в claude-режиме: `codex exec`
#   генерирует изображение за деньги/кредиты подписки. Без --live скрипт
#   печатает план и выходит с кодом 3, codex не запускается. Перед запуском
#   пишется write-ahead строка в usage-ledger (`--service codex --category
#   llm --requests 1 --fail-on-block`); отказ леджера (потолок, битый журнал,
#   нет seo-cycle.yaml в текущем каталоге) — стоп. В codex-режиме скрипт сам
#   ничего не тратит (печатает инструкцию CODEX_NATIVE_IMAGE) — --live не
#   требуется. ALREADY_EXISTS тоже бесплатен.
#
# RUNTIME (env SEO_RUNTIME = claude | codex | auto):
#   • claude — оборачивает в `codex exec` (Codex как подчинённый image-инструмент).
#   • codex  — НЕ оборачивает (самовызов вложенный). Печатает структурированную
#              инструкцию CODEX_NATIVE_IMAGE — Codex генерит своим image-skill
#              (seo-image-gen / image / sora) напрямую и сохраняет в save_to.
#
# Поддерживаемые ratio: 4:3 (hero) | 1:1 (иконки) | 16:9 (OG) | 1.91:1 (FB OG).
# Idempotent: если файл уже есть и не пустой — ALREADY_EXISTS.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEDGER_SCRIPT="$SCRIPT_DIR/usage-ledger.py"

# T-069: --live may appear anywhere; everything else stays positional.
LIVE=0
POSITIONAL=()
for arg in "$@"; do
    if [[ "$arg" == "--live" ]]; then
        LIVE=1
    else
        POSITIONAL+=("$arg")
    fi
done
set -- "${POSITIONAL[@]+"${POSITIONAL[@]}"}"

prompt="${1:?need english prompt as first arg}"
filename="${2:?need filename as second arg (e.g. hero.png)}"
target_dir="${3:-${IMG_TARGET_DIR:-./incoming}}"
ratio="${4:-4:3}"

RUNTIME="${SEO_RUNTIME:-auto}"
if [[ "$RUNTIME" == "auto" ]]; then
    if [[ -n "${CODEX_SANDBOX:-}${CODEX_THREAD_ID:-}${CODEX_RUNNING:-}" ]]; then
        RUNTIME="codex"
    else
        RUNTIME="claude"
    fi
fi

case "$ratio" in
  4:3)    ratio_desc="4:3 landscape (1448x1086 or close)" ;;
  1:1)    ratio_desc="1:1 square (1024x1024)" ;;
  16:9)   ratio_desc="16:9 wide landscape (1920x1080 or close)" ;;
  1.91:1) ratio_desc="1.91:1 Facebook OG (1200x628 or close)" ;;
  *)      echo "Unknown ratio: $ratio (use 4:3 | 1:1 | 16:9 | 1.91:1)" >&2; exit 1 ;;
esac

mkdir -p "$target_dir"
target_path="$target_dir/$filename"

if [ -s "$target_path" ]; then
  echo "ALREADY_EXISTS: $target_path"
  exit 0
fi

# --- Codex-режим: нативная генерация (без вложенного codex exec) ---
if [[ "$RUNTIME" == "codex" ]]; then
  cat <<EOF
CODEX_NATIVE_IMAGE
  Сгенерируй фотореалистичное изображение СВОИМ image-skill (seo-image-gen / image / sora) — НЕ через codex exec.
  prompt:  "${prompt}"
  aspect:  ${ratio_desc}
  save_to: ${target_path}
  После генерации сохрани файл точно в save_to.
EOF
  exit 0
fi

# --- Claude-режим: Codex как подчинённый инструмент ---
codex_prompt="Сгенерируй фотореалистичное изображение через свой image-skill (imagegen/seo-image-gen).

Промпт для генерации (английский):
\"${prompt}\"

Параметры обязательно:
- Пропорция (aspect ratio): ${ratio_desc}
- Целевая папка: ${target_dir}
- Имя файла: ${filename}

После генерации скопируй файл в ${target_path} и напиши ТОЛЬКО одну строку:
DONE: ${target_path}"

if [[ $LIVE -ne 1 ]]; then
  echo "⛔ Нужно --live: генерация ${filename} через codex exec тратит кредиты/деньги подписки." >&2
  echo "   План: ratio ${ratio_desc}, save_to ${target_path}. Повтори с --live, чтобы согласиться на расход." >&2
  exit 3
fi
# Write-ahead ledger record (same contract as the paid Python clients):
# rc≠0 — cap/ledger block (1) or no project config (2) — codex is not run.
if ! python3 "$LEDGER_SCRIPT" record --service codex --category llm --requests 1 --fail-on-block \
        --task "img-generate" --note "img-generate ${filename} (${ratio})" >/dev/null; then
  echo "⛔ usage-ledger отказал в записи расхода (потолок, битый журнал или нет seo-cycle.yaml в $PWD) — генерация не запущена." >&2
  exit 1
fi

echo ">>> codex exec (генерация ${filename})..." >&2
timeout 300 codex exec --skip-git-repo-check --color never <<<"$codex_prompt" 2>&1 | tail -5 >&2

if [ -s "$target_path" ]; then
  size=$(stat -f%z "$target_path" 2>/dev/null || stat -c%s "$target_path" 2>/dev/null)
  echo "OK: $target_path ($size bytes)"
  exit 0
else
  echo "FAIL: $target_path не создан" >&2
  exit 1
fi
