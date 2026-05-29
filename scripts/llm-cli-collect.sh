#!/bin/bash
# llm-cli-collect.sh — параллельный сбор семантики через Antigravity + Codex CLI
#
# Универсальная версия (project-agnostic): принимает тему, сегмент, контекст-категории.
# Сохраняет результаты в <project>/seo/research/llm-cli/results/ или в каталог,
# заданный через переменную окружения LLMCLI_OUTPUT_DIR.
#
# Использование:
#   ./llm-cli-collect.sh "<тема>" [<сегмент>] [<контекст>] [<язык>] [<регион>]
#
# Параметры адаптации под проект:
#   LLMCLI_OUTPUT_DIR   — куда сохранять (default: ./seo/research/llm-cli/results)
#   LLMCLI_LANG         — язык вывода (default: ru)
#   LLMCLI_REGION       — регион в текстовой форме (default: "Москва и Московская область")
#   LLMCLI_CITIES       — города региона для локального контекста (default: "Мытищи, Одинцово, Подольск")
#
# Antigravity ~ 40-60 сек, Codex ~ 2-4 мин → общее ≈ медленный из двух.

set -e

if [[ -z "$1" ]]; then
    echo "Usage: $0 \"<topic>\" [<segment>] [<categories>] [<lang>] [<region-text>]"
    echo "Example:"
    echo "  $0 \"минеральная вата для каркасного дома\" \"B2C+B2B\" \"минвата, пароизоляция\""
    echo "  $0 \"sneaker resale market\" \"B2C\" \"streetwear, fashion\" en \"United States\""
    exit 1
fi

TOPIC="$1"
SEGMENT="${2:-B2C+B2B}"
CATEGORIES="${3:-various categories}"
LANG="${4:-${LLMCLI_LANG:-ru}}"
REGION="${5:-${LLMCLI_REGION:-Москва и Московская область}}"
CITIES="${LLMCLI_CITIES:-Мытищи, Одинцово, Подольск, Балашиха, Химки, Красногорск}"
DATE=$(date +%F)

# RUNTIME: кто основной мозг. claude | codex | auto (default).
# В codex-режиме НЕ делаем codex-самовызов (Codex соберёт нативно через web_search),
# запускаем только agy как второе независимое мнение (Gemini).
RUNTIME="${SEO_RUNTIME:-auto}"
if [[ "$RUNTIME" == "auto" ]]; then
    # эвристика: внутри Codex-сессии обычно выставлен CODEX_* env
    if [[ -n "${CODEX_SANDBOX:-}${CODEX_THREAD_ID:-}${CODEX_RUNNING:-}" ]]; then
        RUNTIME="codex"
    else
        RUNTIME="claude"
    fi
fi

# Slug из темы (ASCII-friendly, иначе хеш)
SLUG=$(echo "$TOPIC" | iconv -t ASCII//TRANSLIT 2>/dev/null | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//;s/-$//' || echo "topic")
if [[ -z "$SLUG" || "$SLUG" == "?" || "$SLUG" == "??" ]]; then
    SLUG=$(echo "$TOPIC" | md5sum 2>/dev/null | cut -c1-12 || echo "$TOPIC" | md5 | cut -c1-12)
fi

# Output dir — можно переопределить через env
OUTDIR="${LLMCLI_OUTPUT_DIR:-./seo/research/llm-cli/results}"
mkdir -p "$OUTDIR"

# TTL-кэш: не перезапускать сбор, если свежий результат уже на диске.
# 0 = кэш отключён (всегда собирать заново). Дефолт 14 дней.
CACHE_TTL="${LLMCLI_CACHE_TTL:-14}"
CACHE_SCRIPT="$HOME/.claude/skills/seo-cycle/scripts/research-cache.py"
cache_hit() {  # $1=source → печатает путь и code 0 при HIT
    [[ "$CACHE_TTL" == "0" ]] && return 1
    [[ -f "$CACHE_SCRIPT" ]] || return 1
    python3 "$CACHE_SCRIPT" check --dir "$OUTDIR" --slug "$SLUG" \
        --source "$1" --ttl "$CACHE_TTL" --ext md 2>/dev/null
}

# Промпт. Универсальный — учитывает язык/регион через переменные.
if [[ "$LANG" == "ru" ]]; then
    PROMPT="РЕЖИМ: глубокое исследование. Думай тщательно перед ответом. Проведи ШИРОКИЙ веб-поиск по нескольким независимым источникам — не ограничивайся одной выдачей. Каждый факт (нормативы, линейки брендов, характеристики) перепроверяй по первоисточникам: официальным сайтам производителей и текстам стандартов. Не выдумывай — если факт не подтверждён источником, помечай это.

Собери семантическое ядро на русском для темы '$TOPIC'.
Рынок: $REGION.
Сегмент: $SEGMENT.
Контекст бизнеса: ассортимент включает $CATEGORIES.

Дай:

1. **30 long-tail запросов**, разделённых на:
   - **Информационные** (15): «как», «какой», «что лучше», «сравнение», «расчёт»
   - **Коммерческие** (15): «купить», «цена», «доставка», «опт»
   - С привязкой к конкретным городам региона где уместно ($CITIES).

2. **15 связанных сущностей** с короткими (1-2 предложения) определениями:
   - **Бренды-производители** с конкретными линейками
   - **Нормативы** (ГОСТ, СП, СанПиН, ТУ) — точные номера документов
   - **Альтернативные материалы/решения**
   - Если есть live web search — обязательно прикладывай URL-ы к нормативам и брендам.

3. **Классификация интента**: помечай каждый long-tail маркером [И] (info) или [К] (commercial).

4. **Конкретность важнее объёма**.

Формат: чистый markdown, два списка под заголовками '## Long-Tail запросы' и '## Связанные сущности'."
else
    PROMPT="MODE: deep research. Think carefully before answering. Perform a BROAD web search across multiple independent sources — do not rely on a single result page. Verify every fact (standards, brand product lines, specs) against primary sources: official manufacturer sites and standards texts. Do not fabricate — if a fact is not backed by a source, flag it.

Build a semantic keyword core in $LANG for the topic '$TOPIC'.
Market: $REGION.
Segment: $SEGMENT.
Business context: catalog includes $CATEGORIES.

Provide:

1. **30 long-tail queries**, split into:
   - **Informational** (15): 'how', 'what is', 'which is better', 'comparison', 'calculator'
   - **Commercial** (15): 'buy', 'price', 'delivery', 'wholesale'
   - With local references where relevant.

2. **15 related entities** with 1-2 sentence definitions:
   - **Brands** with specific product lines
   - **Standards / norms / regulations** — exact document numbers
   - **Alternative materials / solutions**
   - If live web search available — include URLs for standards and brands.

3. **Intent classification**: mark each long-tail with [I] (info) or [C] (commercial).

4. **Specificity over volume**.

Format: clean markdown with two lists under '## Long-Tail Queries' and '## Related Entities'."
fi

ANTIGRAVITY_OUT="$OUTDIR/${SLUG}-antigravity-${DATE}.md"
CODEX_OUT="$OUTDIR/${SLUG}-codex-${DATE}.md"

echo "== LLM CLI collect (runtime: $RUNTIME) =="
echo "  Topic:    $TOPIC"
echo "  Lang:     $LANG"
echo "  Region:   $REGION"
echo "  Segment:  $SEGMENT"
echo "  Slug:     $SLUG"
echo "  Date:     $DATE"
echo "  Output 1: $ANTIGRAVITY_OUT"
echo "  Output 2: $CODEX_OUT"
echo ""

write_header() {
    local cli="$1" file="$2"
    cat > "$file" <<EOF
---
topic: $TOPIC
lang: $LANG
region: $REGION
segment: $SEGMENT
categories: $CATEGORIES
cli: $cli
date: $DATE
source: llm-cli
---

EOF
}

HAS_AGY=0
HAS_CODEX=0
command -v agy >/dev/null 2>&1 && HAS_AGY=1
command -v codex >/dev/null 2>&1 && HAS_CODEX=1

if [[ $HAS_AGY -eq 1 ]]; then
    if HIT=$(cache_hit antigravity); then
        echo "↩ Antigravity: свежий кэш (<${CACHE_TTL}д) → $HIT — пропускаем сбор"
        ANTIGRAVITY_OUT="$HIT"
        HAS_AGY=2   # 2 = взято из кэша
    else
        write_header "antigravity" "$ANTIGRAVITY_OUT"
        echo "▶ Antigravity (~40-60 сек)..."
        (agy --print "$PROMPT" >> "$ANTIGRAVITY_OUT" 2>&1; echo "  ✓ Antigravity done") &
        AGY_PID=$!
    fi
else
    echo "⚠ Antigravity (agy) не установлен — пропускаем"
fi

if [[ "$RUNTIME" == "codex" ]]; then
    # Codex — основной мозг: НЕ вызываем codex exec сами в себе (вложенный процесс).
    # Codex собирает вторую половину нативно своим web_search и сам делает merge.
    HAS_CODEX=0
    echo "▶ Codex-режим: codex-самовызов пропущен. Codex, собери семантику нативно"
    echo "  (deep reasoning + web_search) по промпту ниже, сохрани в:"
    echo "    $CODEX_OUT"
    echo "  затем слей с Antigravity через llm-cli-merge.py."
    echo "  --- ПРОМПТ ДЛЯ НАТИВНОГО СБОРА ---"
    printf '%s\n' "$PROMPT"
    echo "  --- /ПРОМПТ ---"
elif [[ $HAS_CODEX -eq 1 ]]; then
    if HIT=$(cache_hit codex); then
        echo "↩ Codex: свежий кэш (<${CACHE_TTL}д) → $HIT — пропускаем сбор"
        CODEX_OUT="$HIT"
        HAS_CODEX=2
    else
        write_header "codex" "$CODEX_OUT"
        echo "▶ Codex CLI (~2-4 мин, deep reasoning + live web search)..."
        # Флаги deep reasoning + live web search прописаны явно — скрипт самодостаточен
        # и не зависит от глобального ~/.codex/config.toml при переносе на другую машину.
        (codex exec --skip-git-repo-check \
            -c model_reasoning_effort="xhigh" \
            -c web_search="live" \
            "$PROMPT" >> "$CODEX_OUT" 2>&1; echo "  ✓ Codex done") &
        CODEX_PID=$!
    fi
else
    echo "⚠ Codex CLI не установлен — пропускаем"
fi

if [[ $HAS_AGY -eq 0 && $HAS_CODEX -eq 0 ]]; then
    echo "❌ Ни одна из CLI не установлена."
    echo "  Antigravity: https://antigravity.google.dev"
    echo "  Codex CLI: https://github.com/openai/codex-cli"
    exit 2
fi

echo ""
echo "⏳ Ждём..."
[[ -n "$AGY_PID" ]] && wait $AGY_PID
[[ -n "$CODEX_PID" ]] && wait $CODEX_PID

echo ""
echo "=== Результаты ==="
[[ $HAS_AGY -ge 1 ]] && echo "  Antigravity: $(wc -l < "$ANTIGRAVITY_OUT") строк → $ANTIGRAVITY_OUT"
[[ $HAS_CODEX -ge 1 ]] && echo "  Codex:       $(wc -l < "$CODEX_OUT") строк → $CODEX_OUT"

if [[ $HAS_AGY -ge 1 && $HAS_CODEX -ge 1 ]]; then
    MERGED="$OUTDIR/${SLUG}-merged-${DATE}.md"
    echo ""
    echo "Следующий шаг — merge:"
    echo "  python3 ~/.claude/skills/seo-cycle/scripts/llm-cli-merge.py \\"
    echo "      \"$ANTIGRAVITY_OUT\" \"$CODEX_OUT\" \\"
    echo "      -o \"$MERGED\""
fi
