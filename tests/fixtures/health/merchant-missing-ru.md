# Google Merchant Provider Health

- Generated: <TS>
- Status: `region_limited`
- Note: Google Shopping is suspended for RF stores; region_limited is expected. Use yml-feed-audit.py for the Yandex product feed instead.
- Env names: `GOOGLE_MERCHANT_ACCOUNT_ID`, `GOOGLE_APPLICATION_CREDENTIALS` (missing: GOOGLE_MERCHANT_ACCOUNT_ID, GOOGLE_APPLICATION_CREDENTIALS)

## Capabilities
- account-level issues via Content API accountstatuses
- product disapprovals with reasons via productstatuses
- offline mode: ingest a saved statuses export via --input-file

## Guardrails
- No live HTTP/API call in health check.
- merchant-fetch.py defaults to --input-file/cache; --live is read-only statuses.
- Feed writes/uploads are out of scope: fix the source feed, not the API.

## Official Docs
- https://developers.google.com/shopping-content/guides/quickstart
- https://support.google.com/merchants/answer/6363310
