# Yandex Direct Provider Health

- Generated: <TS>
- Status: `available`
- Ads layer enabled: False · platform enabled: False
- Primary platform: `yandex_direct`
- Sandbox: False
- Env names: `YANDEX_DIRECT_TOKEN`
- API default: `read_only_fetch_behind_live_flag`

## Capabilities
- campaigns/adgroups/keywords via Direct API v5 (JSON)
- performance stats and search queries via Reports API (TSV, offline mode)
- sandbox host support for safe apply rehearsal
- draft campaigns from the semantic core via ads-draft-builder.py

## Guardrails
- No live HTTP/API call in health check.
- yandex-direct-fetch.py defaults to cache/--input-file; --live requires usage-ledger preflight.
- ads-apply.py requires an approved ads ticket, --live --allow-write, and per-run change caps.
- Budgets are frozen unless ads.apply.max_daily_budget > 0.

## Official Docs
- https://yandex.ru/dev/direct/doc/dg/concepts/about.html
- https://yandex.ru/dev/direct/doc/reports/reports.html
- https://yandex.ru/dev/direct/doc/dg/concepts/sandbox.html
