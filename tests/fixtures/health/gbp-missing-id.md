# Google Business Profile Health

- Generated: <TS>
- Status: `needs_credentials`
- GBP URL: https://maps.google.com/test
- OAuth env: `GBP_OAUTH_CLIENT_ID`, `GBP_OAUTH_CLIENT_SECRET`, `GBP_OAUTH_REFRESH_TOKEN`
- ID env: `GOOGLE_BUSINESS_ACCOUNT_ID`, `GOOGLE_BUSINESS_LOCATION_ID` (missing: GOOGLE_BUSINESS_ACCOUNT_ID, GOOGLE_BUSINESS_LOCATION_ID)
- Note: GBP API requires Google OAuth verification for the business.manage scope. Until approved, use the browser workflow (prompts/local/google-maps.md) and manual exports via gbp-fetch.py --input-file — this is the expected state, not an error.

## Capabilities
- locations list (name, address, phone, categories) via Business Information API
- reviews with ratings/replies via My Business v4 reviews endpoint
- offline ingestion of saved exports (--input-file) — works today without OAuth verification

## Guardrails
- No live HTTP/API call in health check.
- gbp-fetch.py is read-only; posting/replies stay manual or browser-driven with human review.
- For RF local presence, Yandex Business is the primary channel (see yandex-business-health.py).

## Official Docs
- https://developers.google.com/my-business/content/prereqs
- https://developers.google.com/my-business/content/review-data
- https://support.google.com/business/answer/7107242
