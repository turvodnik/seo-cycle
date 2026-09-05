# Google Ads Provider Health

- Generated: <TS>
- Status: `needs_credentials`
- Ads layer enabled: False · platform enabled: False · apply enabled: False
- Primary platform: `google_ads`
- Env names: `GOOGLE_ADS_DEVELOPER_TOKEN`, `GOOGLE_ADS_CLIENT_ID`, `GOOGLE_ADS_CLIENT_SECRET`, `GOOGLE_ADS_REFRESH_TOKEN`, `GOOGLE_ADS_CUSTOMER_ID` (missing: GOOGLE_ADS_DEVELOPER_TOKEN, GOOGLE_ADS_CLIENT_ID, GOOGLE_ADS_CLIENT_SECRET, GOOGLE_ADS_REFRESH_TOKEN, GOOGLE_ADS_CUSTOMER_ID)
- API default: `read_only_gaql_behind_live_flag`

## Capabilities
- campaigns/ad groups/keywords/search terms/metrics via REST GAQL search
- recommendations API (read-only)
- OAuth refresh-token flow via urllib (no SDK dependency)
- draft campaigns as JSON + Google Ads Editor CSV export

## Guardrails
- No live HTTP/API call in health check.
- google-ads-fetch.py defaults to cache/--input-file; --live requires usage-ledger preflight.
- API writes stay disabled unless ads.google_ads.apply_enabled is set after review.
- region_profile: ru → region_limited is the expected status.

## Official Docs
- https://developers.google.com/google-ads/api/docs/start
- https://developers.google.com/google-ads/api/docs/rest/overview
- https://developers.google.com/google-ads/api/docs/best-practices/quotas
