#!/usr/bin/env bash
# install.sh — unified seo-cycle installer (store + versions + project attach).
#
#   curl -fsSL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/install.sh | bash
#
# Store model (v2):
#   ~/.codex/vendor/seo-cycle                  git clone — the only download location
#   ~/.codex/vendor/seo-keywords               optional sibling repo
#   ~/.codex/vendor/versions/seo-cycle/vX.Y.Z  read-only git worktree per release tag
#   ~/.codex/vendor/attached-projects.yaml     machine-local registry of attached projects
#
# A project only sees seo-cycle after an explicit attach:
#   install.sh --project /path/to/project [--pin vX.Y.Z]
# Projects without attach get zero files and zero agent context.
#
# Modes:
#   install.sh                          ensure store (clone/update) + CLI shim
#   install.sh --update                 fetch new tags/commits into the store only
#   install.sh --project DIR [opts]     attach a project / re-sync its surfaces
#   install.sh --project DIR --detach   remove seo-cycle links from a project
#   install.sh --upgrade-all [--pin T]  re-pin every attached project (default: latest tag)
#
# Project options:
#   --pin TAG       version to attach (default: existing lock pin, else latest vX tag;
#                   the special value "main" tracks the store clone HEAD)
#   --runtime R     all|claude|codex   surfaces to generate (default all)
#   --sync          only regenerate links/surfaces from the existing lock
#   --skip-init     do not run the project wizard for new projects
#   --register     allow init-project.sh to add the project to the machine-local
#                  projects registry (default ~/.seo-cycle/projects-registry.yaml,
#                  override via SEO_CYCLE_REGISTRY — see seo_cycle_core/registry.py)
#   --with-wordpress-mcp   also create project-local WordPress MCP config
# Legacy (kept for compatibility):
#   --global-skill        expose seo-cycle in global skill roots (visible everywhere — avoid)
#   --vendor-local        clone the full core into PROJECT/.codex/skills (no store)
#   --no-migrate-old-global  keep old ~/.codex/skills checkouts in place

set -euo pipefail

SHARED_DIR="${SEO_CYCLE_SHARED_DIR:-$HOME/.codex/vendor}"
CORE="${SEO_CYCLE_CORE:-$SHARED_DIR/seo-cycle}"
KW_CORE="${SEO_KEYWORDS_CORE:-$SHARED_DIR/seo-keywords}"
VERSIONS_DIR="$SHARED_DIR/versions"
REGISTRY_FILE="$SHARED_DIR/attached-projects.yaml"
REPO="${SEO_CYCLE_REPO:-https://github.com/turvodnik/seo-cycle}"
KW_REPO="${SEO_KEYWORDS_REPO:-https://github.com/turvodnik/seo-keywords}"

PROJECT_DIR=""
PIN=""
RUNTIME="all"
MODE="store"          # store | update | project | upgrade-all
DETACH=0
SYNC_ONLY=0
# NETWORK_ALLOWED is DELIBERATELY separate from SYNC_ONLY (R7): SYNC_ONLY
# means "skip the project wizard/registry, just re-link" and is also reused
# internally by upgrade_all() (which already called ensure_store and DOES
# want an origin/SHA check with the data it just fetched). NETWORK_ALLOWED=0
# means "make zero network calls" and is set ONLY by the user-facing --sync
# flag below — it, not SYNC_ONLY, is what ensure_worktree()'s origin check
# gates on.
NETWORK_ALLOWED=1
RUN_INIT=1
REGISTER=0
WITH_WORDPRESS_MCP="${SEO_CYCLE_WITH_WORDPRESS_MCP:-0}"
LEGACY_GLOBAL_SKILL=0
VENDOR_LOCAL=0
MIGRATE_OLD_GLOBAL=1

usage() {
    sed -n '2,40p' "$0" 2>/dev/null | sed 's/^# \{0,1\}//'
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --project) PROJECT_DIR="${2:?--project requires a directory}"; MODE="project"; shift 2 ;;
        --pin) PIN="${2:?--pin requires a tag}"; shift 2 ;;
        --runtime) RUNTIME="${2:?--runtime requires all|claude|codex}"; shift 2 ;;
        --sync) SYNC_ONLY=1; RUN_INIT=0; NETWORK_ALLOWED=0; shift ;;
        --detach) DETACH=1; shift ;;
        --update) MODE="update"; shift ;;
        --upgrade-all) MODE="upgrade-all"; shift ;;
        --skip-init) RUN_INIT=0; shift ;;
        --register) REGISTER=1; shift ;;
        --with-wordpress-mcp) WITH_WORDPRESS_MCP=1; shift ;;
        --global|--global-skill) LEGACY_GLOBAL_SKILL=1; shift ;;
        --vendor-local) VENDOR_LOCAL=1; shift ;;
        --no-migrate-old-global) MIGRATE_OLD_GLOBAL=0; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "ERROR: unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

# O1: --upgrade-all --sync is an UNDOCUMENTED combination (usage lists only
# --upgrade-all [--pin T]; --sync is a --project-mode flag) that silently
# bypassed the origin/SHA check in ensure_worktree(): --sync sets
# NETWORK_ALLOWED=0 globally, and upgrade_all()'s internal SYNC_ONLY=1 reuse
# of attach_project() never resets it. That let a diverged tag get written
# to the lock of all four live sites with exit code 0 (found in the T-049
# review, O1). Refuse outright rather than silently ignoring --sync here —
# the caller typed a flag that does something other than what they asked for.
if [ "$MODE" = "upgrade-all" ] && [ "$SYNC_ONLY" = "1" ]; then
    echo "ERROR: --upgrade-all не принимает --sync — эта комбинация обходит сверку origin/SHA (O1). Используй install.sh --upgrade-all [--pin T]." >&2
    exit 2
fi

log()  { echo "$*"; }
warn() { echo "⚠ $*" >&2; }

abs_path() {
    (cd "$1" && pwd)
}

abs_path_create() {
    mkdir -p "$1"
    (cd "$1" && pwd)
}

# ---------------------------------------------------------------- store layer

# True when $1 is a git *worktree* checkout (a linked working tree whose
# .git is a FILE pointing at the real repo's .git/worktrees/<name>, not a
# normal clone's .git DIRECTORY). `test -d .git` cannot see this and
# misreports a worktree as "not a git repo" (O3) — confirmed via
# `git rev-parse --git-dir` per the ticket, not just the file/dir shape.
is_git_worktree_checkout() {
    # T-064: a linked worktree's ".git" is a FILE containing a "gitdir:"
    # pointer at the main repo's internal worktree metadata. The old check
    # also required `git rev-parse --is-inside-work-tree` to succeed — but
    # that fails when the main repo the worktree points at has since been
    # deleted (orphaned worktree), so an orphaned worktree was NOT detected
    # here and fell straight into install_or_update_repo()'s "not a git dir"
    # branch, which backs it up and clones fresh over it (reproducing the O3
    # incident this guard exists to stop). The gitdir-pointer file itself is
    # the worktree's signature regardless of whether its target still
    # exists — check for that directly instead of asking git to prove it.
    [ -f "$1/.git" ] && grep -q '^gitdir:' "$1/.git" 2>/dev/null
}

install_or_update_repo() {
    local repo="$1" dest="$2" label="$3"
    mkdir -p "$(dirname "$dest")"
    if [ -L "$dest" ]; then rm "$dest"; fi
    if is_git_worktree_checkout "$dest"; then
        # O3 (live incident during a T-051 run): the old `test -d .git` check
        # saw a worktree's gitfile-not-a-directory .git and treated the
        # worktree as an empty/foreign directory, backing it up and cloning
        # fresh over it — silently relocating someone's uncommitted branch
        # and, as a side effect, re-pointing ~/.local/bin/seo-cycle at the
        # freshly cloned store. Refuse instead of guessing: this is either a
        # misconfigured SEO_CYCLE_CORE/SEO_KEYWORDS_CORE, or a real working
        # copy that must not be touched by an installer.
        echo "ERROR: $dest — это git worktree (рабочая копия с несохранённой работой), а не место для клона $label. Установщик отказывается клонировать/переносить его (O3). Укажи корректный путь для хранилища или убери этот worktree вручную." >&2
        exit 1
    fi
    if [ -d "$dest/.git" ]; then
        log "▶ обновляю $label..."
        git -C "$dest" fetch --tags --quiet 2>/dev/null || warn "$label: fetch не удался (offline?)"
        git -C "$dest" pull --quiet --ff-only 2>/dev/null || log "  (есть локальные изменения — pull пропущен)"
    else
        if [ -e "$dest" ]; then
            local backup="${dest}.backup.$(date +%Y%m%d-%H%M%S)"
            mv "$dest" "$backup"
            log "  (backup: $backup)"
        fi
        log "▶ клонирую $label..."
        git clone --quiet "$repo" "$dest"
    fi
}

install_or_update_optional_repo() {
    local repo="$1" dest="$2" label="$3"
    mkdir -p "$(dirname "$dest")"
    if [ -L "$dest" ]; then rm "$dest"; fi
    if [ -d "$dest/.git" ]; then
        git -C "$dest" fetch --tags --quiet 2>/dev/null || true
        git -C "$dest" pull --quiet --ff-only 2>/dev/null || true
    elif git clone --quiet "$repo" "$dest" 2>/dev/null; then
        log "▶ $label установлен"
    else
        log "  ($label пропущен — необязателен)"
    fi
}

ensure_python_deps() {
    log "▶ проверяю python-зависимости (pyyaml, requests, pillow, beautifulsoup4, google-auth)..."
    if ! python3 -c "import yaml, requests, PIL, bs4; import google.auth, google.oauth2.service_account" 2>/dev/null; then
        python3 -m pip install --quiet pyyaml requests pillow beautifulsoup4 google-auth 2>/dev/null \
            || pip3 install --quiet pyyaml requests pillow beautifulsoup4 google-auth 2>/dev/null \
            || python3 -m pip install --quiet --break-system-packages pyyaml requests pillow beautifulsoup4 google-auth 2>/dev/null \
            || warn "установи вручную: python3 -m pip install [--break-system-packages] pyyaml requests pillow beautifulsoup4 google-auth"
    fi
}


# Tags that exist on origin AND locally (sorted newest-first). Empty (refuse)
# when origin cannot be reached at all while NETWORK_ALLOWED=1 (T-064): a
# caller that did not pass --sync explicitly wants a network-verified pin,
# so a dropped connection here must not be papered over with the newest
# local tag — that tag is unverified against origin and this is exactly the
# path --upgrade-all uses to re-pin four live sites (D3).
latest_tag() {
    local repo_dir="$1"
    local local_tags remote_tags common
    local_tags="$(git -C "$repo_dir" tag --list 'v*' --sort=-v:refname 2>/dev/null)"
    [ -n "$local_tags" ] || return 0
    # O2: this used to run ls-remote unconditionally, so --sync's promise of
    # zero network calls (CHANGELOG) was false whenever a caller resolved a
    # pin through latest_tag() (e.g. attach_project() falling back to it when
    # a project has no lock entry yet). Gate on NETWORK_ALLOWED like every
    # other network call in this script (R7) — but do NOT fall back to "the
    # newest local tag" here: that tag is unverified against origin, and
    # ensure_worktree()'s own origin/SHA check is ALSO gated on
    # NETWORK_ALLOWED (deliberately — see its comment), so it would NOT
    # catch a stale/renamed local tag on this path either. The ticket's own
    # two options are "take it from the lock, or refuse" — this function has
    # no lock to read, so it refuses (returns empty) and lets the caller's
    # existing "could not resolve a version" path handle it honestly.
    if [ "$NETWORK_ALLOWED" != "1" ]; then
        warn "--sync: сеть отключена — версию беру только из лока/--pin, локальные теги без сверки с origin не использую (O2)" >&2
        return 0
    fi
    remote_tags="$(git -C "$repo_dir" ls-remote --tags origin 'refs/tags/v*' 2>/dev/null \
        | sed -E 's#.*refs/tags/(v[^\^]+)(\^\{\})?$#\1#' | sort -u)"
    if [ -z "$remote_tags" ]; then
        # T-064: an empty listing here means origin could not be reached at
        # all (not "origin has no tags" — a real GitHub origin always has
        # some once a release shipped). NETWORK_ALLOWED=1 means the caller
        # wants a network-verified pin; silently falling back to "the newest
        # local tag" let a single dropped connection during --upgrade-all
        # re-pin four live sites onto an origin-unverified tag with exit
        # code 0 — the incident this SPEC exists to fix. Refuse instead.
        warn "origin недоступен — версию не определяю без сетевой проверки (T-064)" >&2
        return 1
    fi
    common="$(printf "%s\n" "$local_tags" | while IFS= read -r t; do
        [ -n "$t" ] || continue
        printf "%s\n" "$remote_tags" | grep -qxF "$t" && printf "%s\n" "$t"
    done)"
    printf "%s\n" "$common" | head -1
}

# Create (or reuse) a read-only worktree for a tag. Prints the worktree path.
# Verifies the existing snapshot's HEAD still matches the tag's commit and
# rebuilds it on mismatch (D4) — a tag can be moved to a new commit after the
# worktree was created (e.g. a re-tagged release).
ensure_worktree() {
    local repo_dir="$1" tool="$2" tag="$3"
    local dest="$VERSIONS_DIR/$tool/$tag"
    local tag_commit
    tag_commit="$(git -C "$repo_dir" rev-parse "refs/tags/$tag^{commit}" 2>/dev/null || true)"
    if [ -z "$tag_commit" ]; then
        warn "тег $tag не найден в $repo_dir"
        return 1
    fi
    # Gated on NETWORK_ALLOWED, NOT SYNC_ONLY (R7): the user-facing --sync
    # sets both and promises zero network calls, but upgrade_all() also sets
    # SYNC_ONLY=1 to reuse this light re-link path while it already has
    # network (it just ran ensure_store) and NEEDS the origin/SHA check —
    # a divergent tag must not be silently written to the lock of four live
    # sites during a re-pin. Only the local snapshot reconciliation below
    # (no network) is unconditional.
    if [ "$NETWORK_ALLOWED" = "1" ]; then
        local remote_out
        remote_out="$(git -C "$repo_dir" ls-remote --tags origin "refs/tags/$tag" 2>/dev/null || true)"
        if [ -z "$remote_out" ]; then
            if git -C "$repo_dir" ls-remote --tags origin 'refs/tags/v*' >/dev/null 2>&1; then
                warn "тег $tag не найден на origin ($tool)"
                return 1
            fi
            # T-064: this second ls-remote also failing means origin is
            # unreachable, not just missing this tag. NETWORK_ALLOWED=1
            # means the caller (a real --sync sets it to 0 and returns
            # before this block) wants a network-verified pin — silently
            # trusting the local tag here let --upgrade-all re-pin all
            # registered projects onto an unverified tag with exit code 0
            # whenever the connection dropped mid-run (the incident this
            # SPEC exists to fix). Refuse instead of guessing.
            warn "origin недоступен, проверить тег $tag невозможно — перепин отменён (T-064)"
            return 1
        else
            # Compare commits, not just the tag name (R6/D3): a local tag can
            # share a name with origin's tag while pointing at a different
            # commit (re-tagged release, stale local clone).
            local remote_commit
            remote_commit="$(printf '%s\n' "$remote_out" | grep '\^{}$' | awk '{print $1}')"
            [ -n "$remote_commit" ] || remote_commit="$(printf '%s\n' "$remote_out" | awk 'NR==1{print $1}')"
            if [ -n "$remote_commit" ] && [ "$remote_commit" != "$tag_commit" ]; then
                warn "тег $tag локально указывает на ${tag_commit:0:8}, а на origin — на ${remote_commit:0:8}; запусти install.sh --update"
                return 1
            fi
        fi
    fi
    if [ -e "$dest/SKILL.md" ] || [ -e "$dest/VERSION" ]; then
        local snapshot_commit
        snapshot_commit="$(git -C "$dest" rev-parse HEAD 2>/dev/null || true)"
        if [ "$snapshot_commit" = "$tag_commit" ]; then
            printf "%s\n" "$dest"
            return 0
        fi
        warn "снапшот $tag пересобран: ${snapshot_commit:0:8}→${tag_commit:0:8}"
        chmod -R u+w "$dest" 2>/dev/null || true
        git -C "$repo_dir" worktree remove --force "$dest" 2>/dev/null || rm -rf "$dest"
    fi
    rm -rf "$dest" 2>/dev/null || true
    git -C "$repo_dir" worktree prune 2>/dev/null || true
    mkdir -p "$(dirname "$dest")"
    if ! git -C "$repo_dir" worktree add --quiet --detach "$dest" "refs/tags/$tag" 2>/dev/null; then
        warn "не удалось создать worktree для $tool@$tag"
        return 1
    fi
    chmod -R a-w "$dest" 2>/dev/null || true
    printf "%s\n" "$dest"
}

replace_with_symlink() {
    local target="$1" link="$2"
    mkdir -p "$(dirname "$link")"
    if [ "$target" = "$link" ]; then return 0; fi
    if [ -L "$link" ]; then
        rm "$link"
    elif [ -e "$link" ]; then
        local backup="${link}.backup.$(date +%Y%m%d-%H%M%S)"
        mv "$link" "$backup"
        log "  (backup: $backup)"
    fi
    ln -s "$target" "$link"
}

migrate_old_global_checkout() {
    [ "$MIGRATE_OLD_GLOBAL" = "1" ] || return 0
    local old="$HOME/.codex/skills/seo-cycle" old_kw="$HOME/.codex/skills/seo-keywords"
    mkdir -p "$SHARED_DIR"
    if [ "$old" != "$CORE" ] && [ -d "$old/.git" ] && [ ! -e "$CORE" ]; then
        log "▶ переношу старый global skill checkout в shared vendor..."
        mv "$old" "$CORE"
    elif [ "$old" != "$CORE" ] && [ -L "$old" ] && [ "$LEGACY_GLOBAL_SKILL" != "1" ]; then
        rm "$old"
    fi
    if [ "$old_kw" != "$KW_CORE" ] && [ -d "$old_kw/.git" ] && [ ! -e "$KW_CORE" ]; then
        mv "$old_kw" "$KW_CORE"
    elif [ "$old_kw" != "$KW_CORE" ] && [ -L "$old_kw" ] && [ "$LEGACY_GLOBAL_SKILL" != "1" ]; then
        rm "$old_kw"
    fi
}

cleanup_legacy_global_links() {
    [ "$LEGACY_GLOBAL_SKILL" = "1" ] && return 0
    local root name
    for root in "$HOME/.codex/skills" "$HOME/.agents/skills" "$HOME/.claude/skills"; do
        for name in seo-cycle seo-keywords codex-primary-runtime; do
            [ -L "$root/$name" ] && rm "$root/$name"
        done
    done
    return 0
}

install_legacy_global_skill_links() {
    local root
    for root in "$HOME/.codex/skills" "$HOME/.agents/skills" "$HOME/.claude/skills"; do
        replace_with_symlink "$CORE" "$root/seo-cycle"
        [ -d "$KW_CORE" ] && replace_with_symlink "$KW_CORE" "$root/seo-keywords"
        [ -d "$CORE/codex-primary-runtime" ] && replace_with_symlink "$CORE/codex-primary-runtime" "$root/codex-primary-runtime"
    done
    warn "legacy global skill links включены: seo-cycle виден во всех проектах"
}

install_cli_shim() {
    if [ -f "$CORE/bin/seo-cycle" ]; then
        mkdir -p "$HOME/.local/bin"
        chmod +x "$CORE/bin/seo-cycle" 2>/dev/null || true
        ln -sf "$CORE/bin/seo-cycle" "$HOME/.local/bin/seo-cycle"
        log "✓ CLI: ~/.local/bin/seo-cycle → $CORE/bin/seo-cycle"
        case ":$PATH:" in
            *":$HOME/.local/bin:"*) ;;
            *) warn "~/.local/bin не в PATH. Добавь в shell rc: export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
        esac
    fi
}

ensure_store() {
    migrate_old_global_checkout
    install_or_update_repo "$REPO" "$CORE" "seo-cycle shared vendor core"
    install_or_update_optional_repo "$KW_REPO" "$KW_CORE" "seo-keywords shared vendor"
    ensure_python_deps
    if [ ! -e "$CORE/AGENTS.md" ]; then
        ( cd "$CORE" && ln -sf SKILL.md AGENTS.md )
    fi
    cleanup_legacy_global_links
    install_cli_shim
    if [ "$LEGACY_GLOBAL_SKILL" = "1" ]; then
        install_legacy_global_skill_links
    fi
}

update_store_only() {
    for pair in "seo-cycle:$CORE" "seo-keywords:$KW_CORE"; do
        local_dir="${pair#*:}"
        label="${pair%%:*}"
        if [ -d "$local_dir/.git" ]; then
            git -C "$local_dir" fetch --tags --quiet && log "✓ $label: fetch ok, latest tag: $(latest_tag "$local_dir")"
        else
            warn "$label: клона нет — запусти install.sh без аргументов"
        fi
    done
}

# ------------------------------------------------------------- project layer

# Read the pinned version of one tool from an existing lock (empty if absent).
read_lock_version() {
    local project_dir="$1" tool="$2"
    local lock_path="$project_dir/.agents/external-skills.lock.yaml"
    [ -f "$lock_path" ] || return 0
    python3 - "$lock_path" "$tool" <<'PYEOF' 2>/dev/null || true
import sys
try:
    import yaml
except ImportError:
    sys.exit(0)
data = yaml.safe_load(open(sys.argv[1])) or {}
print(((data.get("external") or {}).get(sys.argv[2]) or {}).get("version") or "")
PYEOF
}

# Update the managed entries of .agents/external-skills.lock.yaml (preserves the
# rest of the file). Requires pyyaml; degrades to a warning without it.
write_lock_entry() {
    local project_dir="$1" tool="$2" version="$3" commit="$4" path="$5"
    python3 - "$project_dir/.agents/external-skills.lock.yaml" "$tool" "$version" "$commit" "$path" <<'PYEOF' || warn "lock не обновлён (нет pyyaml?)"
import sys, datetime, pathlib
try:
    import yaml
except ImportError:
    sys.exit(1)
lock_path = pathlib.Path(sys.argv[1])
tool, version, commit, store_path = sys.argv[2:6]
data = {}
if lock_path.exists():
    data = yaml.safe_load(lock_path.read_text()) or {}
ext = data.setdefault("external", {})
ext[tool] = {
    "integration": "vendor-worktree",
    "version": version,
    "commit": commit,
    "path": store_path,
    "updated": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
}
lock_path.parent.mkdir(parents=True, exist_ok=True)
lock_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
print(f"✓ lock: {tool} @ {version} ({commit[:8]})")
PYEOF
}

remove_lock_entry() {
    local project_dir="$1" tool="$2"
    local lock_path="$project_dir/.agents/external-skills.lock.yaml"
    [ -f "$lock_path" ] || return 0
    python3 - "$lock_path" "$tool" <<'PYEOF' || warn "lock не очищен (нет pyyaml?)"
import sys, pathlib
try:
    import yaml
except ImportError:
    sys.exit(1)
lock_path = pathlib.Path(sys.argv[1])
tool = sys.argv[2]
data = yaml.safe_load(lock_path.read_text()) or {}
ext = data.get("external") or {}
if tool in ext:
    del ext[tool]
    data["external"] = ext
    lock_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    print(f"✓ lock: {tool} запись удалена")
PYEOF
}

registry_update() {
    local action="$1" project_dir="$2" pin="${3:-}"
    mkdir -p "$SHARED_DIR"
    python3 - "$REGISTRY_FILE" "$action" "$project_dir" "$pin" <<'PYEOF' || true
import sys, pathlib
try:
    import yaml
except ImportError:
    sys.exit(0)
reg_path = pathlib.Path(sys.argv[1]); action = sys.argv[2]; proj = sys.argv[3]; pin = sys.argv[4]
data = {}
if reg_path.exists():
    data = yaml.safe_load(reg_path.read_text()) or {}
projects = [p for p in data.get("projects", []) if p.get("path") != proj]
if action == "add":
    projects.append({"path": proj, "pin": pin})
data["projects"] = projects
reg_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
PYEOF
}

ensure_project_entrypoints() {
    local project_dir="$1" target="$2"
    if [ ! -e "$project_dir/AGENTS.md" ]; then
        cat > "$project_dir/AGENTS.md" <<'EOF'
# Project Agent Instructions

Canonical instructions file for every agent (Codex, Claude Code, Gemini/Antigravity).
`CLAUDE.md` and `GEMINI.md` are symlinks to this file — never fork them.

This project uses seo-cycle through the project surface `./.claude/skills/seo-cycle`
(= `./.codex/skills/seo-cycle` → `.agents/external/seo-cycle`, pinned in
`.agents/external-skills.lock.yaml`).

Read order for SEO/AEO/GEO work:
1. `./.claude/skills/seo-cycle/SKILL.md` — shared workflow contract (thin orchestrator).
2. `./seo-cycle.yaml` — project config.
3. `./seo/project-rules.md` — project-specific overrides.
4. `./seo/setup/context-pack.md` — task-scoped low-token context when present.

Secrets: never store values in `.env` or configs. Use the macOS Keychain via the
`ai-secret` tool (`ai-secret run <scope> -- <command>`); `.env.example` lists names only.

Do not edit the shared seo-cycle skill to handle one project's exception.
Put project-specific rules, exclusions, approvals and notes in
`seo/project-rules.md`, `seo-cycle.yaml`, or the relevant `seo/*.yaml` policy.
EOF
        log "✓ AGENTS.md создан (канонический файл проекта)"
    else
        log "ℹ AGENTS.md уже существует — не трогаю"
    fi
    if [ ! -e "$project_dir/CLAUDE.md" ]; then
        ln -s "AGENTS.md" "$project_dir/CLAUDE.md"
        log "✓ CLAUDE.md → AGENTS.md"
    elif [ ! -L "$project_dir/CLAUDE.md" ]; then
        warn "CLAUDE.md — отдельный файл. Конвенция: перенести содержимое в AGENTS.md и заменить симлинком."
    fi
    if [ ! -e "$project_dir/GEMINI.md" ]; then
        ln -s "AGENTS.md" "$project_dir/GEMINI.md"
        log "✓ GEMINI.md → AGENTS.md"
    fi
    # Legacy layouts pointed CLAUDE.md straight into the vendor SKILL.md — leave a hint.
    if [ -L "$project_dir/CLAUDE.md" ] && [ "$(readlink "$project_dir/CLAUDE.md")" != "AGENTS.md" ]; then
        warn "CLAUDE.md указывает не на AGENTS.md ($(readlink "$project_dir/CLAUDE.md")) — рекомендуется перевесить."
    fi
    : "$target"
}

ensure_project_overlay() {
    local project_dir="$1"
    mkdir -p "$project_dir/seo" "$project_dir/.codex"
    if [ ! -f "$project_dir/seo/project-rules.md" ]; then
        cat > "$project_dir/seo/project-rules.md" <<'EOF'
# Project-Specific SEO Rules

Use this file for rules that apply only to this project.

Examples:
- hosting/CDN constraints;
- regional legal or analytics restrictions;
- CMS/plugin quirks;
- publishing approvals;
- URLs, templates or bot policies that differ from the shared seo-cycle defaults.

Do not change the shared seo-cycle skill for one project's exception.
EOF
        log "✓ seo/project-rules.md создан"
    fi
    if [ ! -f "$project_dir/.codex/PROJECT.md" ]; then
        cat > "$project_dir/.codex/PROJECT.md" <<'EOF'
# Project-Local Codex Overlay

Shared code is reached through `./.codex/skills/seo-cycle` (symlink chain into the
versioned vendor store). Project MCP endpoints live in `.codex/config.toml`.
Secrets live in the macOS Keychain (`ai-secret`), never in files.

Keep project-specific behavior in `seo/project-rules.md` or `seo-cycle.yaml`.
EOF
        log "✓ .codex/PROJECT.md создан"
    fi
}

ensure_env_template() {
    local project_dir="$1" target="$2"
    if [ ! -f "$project_dir/.env.example" ] && [ -f "$target/.env.example" ]; then
        cp "$target/.env.example" "$project_dir/.env.example"
        log "✓ .env.example создан (только имена ключей; значения — в Keychain через ai-secret)"
    fi
    if [ -f "$project_dir/.env" ]; then
        warn ".env с значениями найден в проекте. Политика: значения в Keychain (ai-secret import), файл удалить."
    fi
    local gi="$project_dir/.gitignore"
    [ -f "$gi" ] || : > "$gi"
    local line
    for line in ".env" "__pycache__/" "*.pyc" ".DS_Store" "workspace/artifacts/" "workspace/cache/" "workspace/tmp/" "seo/cache/"; do
        grep -qxF "$line" "$gi" 2>/dev/null || printf "%s\n" "$line" >> "$gi"
    done
}

ensure_surfaces() {
    local project_dir="$1" runtime="$2" have_kw="$3"
    local rel_target="../../.agents/external"
    mkdir -p "$project_dir/.agents/external"
    local roots=()
    case "$runtime" in
        all) roots=(".claude/skills" ".codex/skills") ;;
        claude) roots=(".claude/skills") ;;
        codex) roots=(".codex/skills") ;;
        *) warn "неизвестный runtime '$runtime', использую all"; roots=(".claude/skills" ".codex/skills") ;;
    esac
    local root
    for root in "${roots[@]}"; do
        mkdir -p "$project_dir/$root"
        replace_with_symlink "$rel_target/seo-cycle" "$project_dir/$root/seo-cycle"
        if [ "$have_kw" = "1" ]; then
            replace_with_symlink "$rel_target/seo-keywords" "$project_dir/$root/seo-keywords"
        fi
        replace_with_symlink "$rel_target/seo-cycle/codex-primary-runtime" "$project_dir/$root/codex-primary-runtime"
    done
    # v1 legacy chain (.agents/skills/seo-cycle → .codex/skills/...) — remove symlink duplicates.
    local name
    for name in seo-cycle seo-keywords codex-primary-runtime; do
        [ -L "$project_dir/.agents/skills/$name" ] && rm "$project_dir/.agents/skills/$name"
    done
    return 0
}

detach_project() {
    local project_dir="$1"
    local root name
    for root in ".claude/skills" ".codex/skills" ".agents/skills"; do
        for name in seo-cycle seo-keywords codex-primary-runtime; do
            [ -L "$project_dir/$root/$name" ] && rm "$project_dir/$root/$name"
        done
    done
    for name in seo-cycle seo-keywords; do
        [ -L "$project_dir/.agents/external/$name" ] && rm "$project_dir/.agents/external/$name"
    done
    for name in seo-cycle seo-keywords; do
        remove_lock_entry "$project_dir" "$name"
    done
    registry_update remove "$project_dir"
    log "✓ seo-cycle отключён от проекта: $project_dir"
    log "  (AGENTS.md, seo-cycle.yaml и данные проекта не тронуты)"
}

find_project_config() {
    local project_dir="$1" rel
    for rel in seo-cycle.yaml .seo-cycle.yaml seo/seo-cycle.yaml .claude/seo-cycle.yaml; do
        if [ -f "$project_dir/$rel" ]; then
            printf "%s\n" "$project_dir/$rel"
            return 0
        fi
    done
    return 1
}

run_existing_project_upgrade() {
    local target="$1" cfg_path="$2"
    log "▶ existing seo-cycle project detected: $cfg_path"
    python3 "$target/scripts/project-upgrade-assistant.py" "$cfg_path" --write \
        || log "ℹ project-upgrade-assistant failed; run it manually after checking config"
    python3 "$target/scripts/access-key-assistant.py" "$cfg_path" --write \
        || log "ℹ access-key-assistant failed; run it manually after checking tool stack"
    python3 "$target/scripts/setup-control-plane.py" "$cfg_path" --write --skip-intake \
        || log "ℹ setup-control-plane reported validation/setup issues; open seo/setup/setup-control-plane.md"
    if [ "$WITH_WORDPRESS_MCP" = "1" ]; then
        python3 "$target/scripts/project-mcp-config.py" "$cfg_path" --write \
            || log "ℹ project-mcp-config failed; run it manually"
    fi
}

attach_project() {
    local project_dir="$1"
    if [ "$DETACH" = "1" ] || [ "$SYNC_ONLY" = "1" ]; then
        if [ ! -d "$1" ]; then
            echo "ERROR: путь не существует: $1" >&2
            exit 1
        fi
        project_dir="$(abs_path "$1")"
    else
        project_dir="$(abs_path_create "$1")"
    fi
    log ""
    log "▶ Project: $project_dir"

    if [ "$DETACH" = "1" ]; then
        detach_project "$project_dir"
        return 0
    fi

    if [ "$VENDOR_LOCAL" = "1" ]; then
        # Legacy: full clone inside the project.
        install_or_update_repo "$REPO" "$project_dir/.codex/skills/seo-cycle" "seo-cycle project-local"
        install_or_update_optional_repo "$KW_REPO" "$project_dir/.codex/skills/seo-keywords" "seo-keywords project-local"
        warn "vendor-local режим: проект несёт собственную копию, обновляется отдельно"
        return 0
    fi

    # Resolve pin: explicit → existing lock → latest tag → main.
    local pin="$PIN"
    if [ -z "$pin" ] && [ -f "$project_dir/.agents/external-skills.lock.yaml" ]; then
        pin="$(python3 - "$project_dir/.agents/external-skills.lock.yaml" <<'PYEOF' 2>/dev/null || true
import sys
try:
    import yaml
except ImportError:
    sys.exit(0)
data = yaml.safe_load(open(sys.argv[1])) or {}
print(((data.get("external") or {}).get("seo-cycle") or {}).get("version") or "")
PYEOF
)"
    fi
    [ -n "$pin" ] || pin="$(latest_tag "$CORE")"
    if [ -z "$pin" ]; then
        # O2: latest_tag() now returns empty both when store has no tags at
        # all AND when NETWORK_ALLOWED=0 and there is no lock to read a pin
        # from (it refuses to guess an origin-unverified local tag) — this
        # message must stay honest for both causes, not claim "no tags"
        # when tags exist but --sync just won't trust them unverified.
        warn "не удалось определить версию: либо в store нет тегов (запусти install.sh --update), либо сеть отключена (--sync) и в проекте ещё нет лока с пином. Укажи --pin явно, либо запусти без --sync для сетевой проверки."
        exit 1
    fi

    local target commit
    if [ "$pin" = "main" ]; then
        target="$CORE"
    else
        target="$(ensure_worktree "$CORE" "seo-cycle" "$pin")" || {
            warn "тег $pin не найден; запусти install.sh --update"
            exit 1
        }
    fi
    commit="$(git -C "$target" rev-parse HEAD 2>/dev/null || echo unknown)"
    log "▶ seo-cycle @ $pin ($commit)"

    # seo-keywords (optional sibling): pinned to a tag, same as seo-cycle —
    # no silent "track HEAD" default (R4/D5: that was D5 renamed, not fixed).
    # Gated on NETWORK_ALLOWED, not SYNC_ONLY (R7 — see ensure_worktree()):
    # a real --sync reuses the already-locked pin instead of recomputing
    # latest_tag(); upgrade_all() (SYNC_ONLY=1 but NETWORK_ALLOWED=1) still
    # gets a fresh latest_tag() against the network it already has.
    local have_kw=0 kw_target="" kw_pin="" kw_commit=""
    if [ -d "$KW_CORE/.git" ]; then
        if [ "$NETWORK_ALLOWED" != "1" ]; then
            kw_pin="$(read_lock_version "$project_dir" "seo-keywords")"
        else
            # T-064: seo-keywords is OPTIONAL — its own origin being
            # unreachable must not abort the whole attach. latest_tag() now
            # returns 1 (not just empty) when NETWORK_ALLOWED=1 and origin
            # is down; a bare `kw_pin="$(latest_tag ...)"` is a plain
            # assignment, and under `set -e` a failing command substitution
            # in a bare assignment DOES abort the shell (unlike one used as
            # a plain argument) — without the `|| kw_pin=""` fallback here,
            # seo-keywords' own outage would kill attach_project() entirely,
            # refusing the MANDATORY, independently-healthy seo-cycle pin
            # too (caught live: gate064's kwint.sh — seo-cycle origin up,
            # seo-keywords origin down, whole --upgrade-all still failed).
            kw_pin="$(latest_tag "$KW_CORE")" || kw_pin=""
        fi
        if [ -n "$kw_pin" ]; then
            kw_target="$(ensure_worktree "$KW_CORE" "seo-keywords" "$kw_pin")" || kw_target=""
            if [ -n "$kw_target" ]; then
                kw_commit="$(git -C "$kw_target" rev-parse HEAD 2>/dev/null || echo unknown)"
                have_kw=1
            else
                warn "seo-keywords: тег $kw_pin недоступен — пропускаю подключение"
            fi
        elif [ "$NETWORK_ALLOWED" = "1" ]; then
            warn "seo-keywords: в store нет тегов — пропускаю подключение (первый релиз ещё не вышел)"
        fi
    fi

    # T-064: this mkdir used to have no failure check at all — with `set -e`
    # active and correctly propagating (see upgrade_all()'s subshell
    # isolation), a bare failure here already stops the function; this
    # explicit guard exists only to print a specific, honest message instead
    # of leaving nothing but git/mkdir's own raw stderr line.
    mkdir -p "$project_dir/.agents/external" || { warn "$project_dir: не удалось создать .agents/external — перепин прерван"; exit 1; }
    replace_with_symlink "$target" "$project_dir/.agents/external/seo-cycle"
    if [ "$have_kw" = "1" ]; then
        replace_with_symlink "$kw_target" "$project_dir/.agents/external/seo-keywords"
    fi
    ensure_surfaces "$project_dir" "$RUNTIME" "$have_kw"
    write_lock_entry "$project_dir" "seo-cycle" "$pin" "$commit" "$target"
    if [ "$have_kw" = "1" ]; then
        write_lock_entry "$project_dir" "seo-keywords" "$kw_pin" "$kw_commit" "$kw_target"
    fi
    registry_update add "$project_dir" "$pin"

    if [ "$SYNC_ONLY" = "1" ]; then
        log "✓ sync завершён"
        return 0
    fi

    ensure_project_entrypoints "$project_dir" "$target"
    ensure_project_overlay "$project_dir"
    ensure_env_template "$project_dir" "$target"

    if [ "$RUN_INIT" = "1" ]; then
        cd "$project_dir"
        if [ "$REGISTER" = "1" ]; then
            unset SEO_CYCLE_SKIP_REGISTRY
        else
            export SEO_CYCLE_SKIP_REGISTRY="${SEO_CYCLE_SKIP_REGISTRY:-1}"
        fi
        local cfg_path
        cfg_path="$(find_project_config "$project_dir" || true)"
        if [ -n "$cfg_path" ]; then
            run_existing_project_upgrade "$target" "$cfg_path"
        else
            if [ "$WITH_WORDPRESS_MCP" = "1" ]; then
                SEO_CYCLE_WITH_WORDPRESS_MCP=1 "$target/scripts/init-project.sh"
            else
                "$target/scripts/init-project.sh"
            fi
            ensure_env_template "$project_dir" "$target"
        fi
    fi

    log ""
    log "✓ Проект подключён: seo-cycle @ $pin"
    log "  Обновление:   install.sh --project \"$project_dir\" --pin <новый-тег> --sync"
    log "  Отключение:   install.sh --project \"$project_dir\" --detach"
}

upgrade_all() {
    local pin="$PIN"
    [ -n "$pin" ] || pin="$(latest_tag "$CORE")"
    [ -n "$pin" ] || { warn "нет тегов в store — сначала install.sh --update"; exit 1; }
    if [ ! -f "$REGISTRY_FILE" ]; then
        warn "реестр подключённых проектов пуст: $REGISTRY_FILE"
        exit 0
    fi
    local projects
    projects="$(python3 - "$REGISTRY_FILE" <<'PYEOF' 2>/dev/null || true
import sys
try:
    import yaml
except ImportError:
    sys.exit(0)
data = yaml.safe_load(open(sys.argv[1])) or {}
for p in data.get("projects", []):
    print(p.get("path", ""))
PYEOF
)"
    # T-064: attach_project() calls `exit` (not `return`) on every failure
    # path — without isolation here, one project failing mid-registry would
    # kill this whole loop, leaving the rest of the portfolio in an
    # UNREPORTED state (the reviewer's live 3-project run: first re-pinned,
    # second failed, third never touched, no summary, exit code whatever the
    # failure happened to produce). Run each project's attach in its own
    # subshell so a failure there only ends that subshell — this function
    # keeps control, tracks every outcome, and prints an explicit portfolio
    # report instead of leaving a silent mixed state. Chosen over two-phase
    # atomicity (verify-all-then-write-all): an explicit partial report is
    # simpler, cannot itself have a distinct failure mode, and needs no extra
    # network round-trip per project.
    #
    # bash's errexit has a documented quirk: a command's failure does not
    # trigger -e when that command is itself the thing being tested by an
    # if/&&/||, and this exemption propagates into every function and
    # subshell called from there. A first version of this fix wrote
    # `( set -e; attach_project "$p" ) || rc=$?` — the subshell is the LEFT
    # operand of `||`, so it is exactly such a tested command: the inner
    # `set -e` was inert, EVERY plain command inside attach_project (mkdir,
    # ln -s, mv, rm — exactly what T-055 runs against live sites) could fail
    # silently, and a failed `ln -s` produced an unnoticed "✓ lock" and a
    # false "перепинено" (caught live: gate064, bash 3.2.57, the shell this
    # machine actually runs). The subshell must NOT be the tested command of
    # any conditional — disable -e in THIS shell first (`set +e`), run the
    # subshell as a bare, untested statement (its own `set -e` then genuinely
    # governs everything inside it), capture $? only afterward, then restore
    # `set -e` here.
    local updated=() failed=() missing=()
    local p rc
    while IFS= read -r p; do
        [ -n "$p" ] || continue
        if [ -d "$p" ]; then
            set +e
            ( set -e; PIN="$pin" SYNC_ONLY=1 RUN_INIT=0 DETACH=0 attach_project "$p" )
            rc=$?
            set -e
            if [ "$rc" -eq 0 ]; then
                updated+=("$p")
            else
                failed+=("$p")
            fi
        else
            warn "проект из реестра не найден: $p"
            missing+=("$p")
        fi
    done <<< "$projects"

    log ""
    log "Итог --upgrade-all → $pin:"
    log "  перепинено (${#updated[@]}):"
    [ "${#updated[@]}" -gt 0 ] && printf '    %s\n' "${updated[@]}"
    log "  не тронуто/отсутствует (${#missing[@]}):"
    [ "${#missing[@]}" -gt 0 ] && printf '    %s\n' "${missing[@]}"
    if [ "${#failed[@]}" -gt 0 ]; then
        warn "упало при перепине (${#failed[@]}):"
        printf '    %s\n' "${failed[@]}" >&2
        if [ "${#updated[@]}" -gt 0 ]; then
            warn "портфель в СМЕШАННОМ состоянии — часть проектов перепинена на $pin, часть нет. Проверь каждый упавший вручную (см. лог выше) перед повторным запуском."
        else
            warn "ни один проект не перепинен на $pin — портфель остался на прежних версиях."
        fi
        exit 1
    fi
}

# ------------------------------------------------------------------- main

log "════════════════════════════════════════════════"
log "  seo-cycle installer"
log "════════════════════════════════════════════════"

case "$MODE" in
    update)
        update_store_only
        ;;
    store)
        ensure_store
        log ""
        log "✓ Store: $CORE (клон), версии: $VERSIONS_DIR/seo-cycle/"
        log "  latest tag: $(latest_tag "$CORE" || echo '—')"
        log ""
        log "Подключение проекта:"
        log "  install.sh --project /path/to/project [--pin vX.Y.Z]"
        ;;
    project)
        if [ "$SYNC_ONLY" = "1" ] || [ "$DETACH" = "1" ]; then
            [ -d "$CORE/.git" ] || { warn "store не инициализирован — запусти install.sh без флагов"; exit 1; }
        else
            ensure_store
        fi
        attach_project "$PROJECT_DIR"
        ;;
    upgrade-all)
        ensure_store
        upgrade_all
        ;;
esac
