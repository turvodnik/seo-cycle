# Экосистема: что взяли, что нет, и почему

Кураторский разбор внешних скиллов/MCP/инструментов (запрос 2026-07-04,
~50 ссылок). Принципы отбора: **не дублировать** уже установленное и уже
реализованное в seo-cycle; **не нарушать** политику проекта (никаких
stealth/anti-detect инструментов, секреты только в `.env`, платное — за
approval); брать **официальное** предпочтительнее самодельного; внедрять
только то, что подключается к существующим контрактам (guarded providers,
usage-ledger, approval gates).

## ВЗЯЛИ — внедрено в seo-cycle

| Что | Откуда идея | Реализация |
|---|---|---|
| N-gram анализ wasted spend (правило 5 ads-analytics) | классика PPC-скиллов (ivangfalco/ads-skills, fourteenwm/ppc-ai-skills, AgriciDaniel/claude-ads) | `ads-analytics.py`: агрегация нулевых конверсий по 1–2-словным n-граммам — общий токен («бесплатно», «б/у») набирает бюджет, даже когда каждый терм ниже порога |
| PDF-отчёты напрямую | anthropics/skills (pdf-скилл как ориентир UX) | `client-report.py --pdf` через headless Chrome, без новых зависимостей |
| Кураторские MCP-пресеты project-local | spilnoagency WebMCP-статьи, официальные MCP-репо | `mcp-preset.py`: chrome-devtools / perplexity / google-analytics одним флагом, секреты из `.env` |

## ОПЦИОНАЛЬНО — включается `mcp-preset.py --enable <name> --write`

| Пресет | Репо | Зачем агентству | Почему не по умолчанию |
|---|---|---|---|
| `chrome-devtools` | [ChromeDevTools/chrome-devtools-mcp](https://github.com/ChromeDevTools/chrome-devtools-mcp) | официальные perf-трейсы/консоль/сеть для CWV-работ глубже Lighthouse-JSON | нужен не в каждом проекте; Chrome MCP-расширение уже покрывает браузинг |
| `perplexity` | [perplexityai/modelcontextprotocol](https://github.com/perplexityai/modelcontextprotocol) | Sonar API как замена браузерному perplexity-collect при наличии API-ключа | платный ключ; наш браузерный путь уже guarded и бесплатный |
| `google-analytics` | [googleanalytics/google-analytics-mcp](https://github.com/googleanalytics/google-analytics-mcp) | разговорные ad-hoc запросы к GA4 сверх снапшотов ga4-fetch | ga4-fetch закрывает цикл; MCP — для исследовательских сессий |

**Google Ads MCP** ([googleads/google-ads-mcp](https://github.com/googleads/google-ads-mcp),
[cohnen/mcp-google-ads](https://github.com/cohnen/mcp-google-ads)) — сознательно
НЕ пресет: у нас собственный guarded-слой (health/fetch/analytics/draft/apply
с ledger и approval), а для `region_profile: ru` Google Ads — `region_limited`.
Для не-РФ проектов, где нужен интерактивный GAQL, подключайте официальный MCP
вручную по его README (те же `GOOGLE_ADS_*` env из нашего `.env.example`).

## НЕ БЕРЁМ — уже есть у нас (дубли)

- **coreyhaines31/marketingskills** — установлен как плагин `marketing-skills` (paid-ads, copywriting, CRO и т.д.).
- **anthropics/skills, knowledge-work-plugins** — pdf/docx/xlsx/pptx уже стоят (`anthropic-skills`); `mcp-builder` возьмём, когда будем писать собственный MCP.
- **Auriti-Labs/geo-optimizer-skill, AgriciDaniel/codex-seo** — GEO/SEO-скиллы: перекрыты нашим vnext-слоем (ai-brand-audit, answer-units, geo-kpi, llms.txt-читатели) и установленным набором `geo-*`/`claude-seo`.
- **firecrawl-mcp-server** — скилл `seo-firecrawl` уже установлен; наш evidence-контур (Perplexity/NotebookLM/XMLRiver) покрывает сбор.
- **Graphify-Labs/graphify** — уже интегрирован (`install-ai-toolchain.sh`).
- **teng-lin/notebooklm-py** — у нас свой NotebookLM-мост (health/source-pack).
- **thedotmack/claude-mem** — персистентная память уже есть (file-based memory Claude Code + наш RAG `seo/rag.db`).
- **Leonxlnx/taste-skill, nextlevelbuilder/ui-ux-pro-max, multica-ai/andrej-karpathy-skills, pbakaus/impeccable, mattpocock/skills** — дизайн/инженерные скиллы: уже установлены (taste-skill, ui-ux-pro-max, karpathy-guidelines) либо не про SEO-цикл.
- **vercel-labs/agent-browser, srbhptl39/MCP-SuperAssistant** — браузер для агентов уже есть (Claude in Chrome MCP + Playwright в seo-visual).
- **mishamyrt/perplexity-web-api-mcp** — неофициальная обёртка web-API; берём официальный Sonar-пресет вместо неё.

## НЕ БЕРЁМ — против политики проекта

- **CloakHQ/CloakBrowser, overtimepog/cloakmcp** — анти-детект браузеры. `install-ai-toolchain.sh` явно обещает «не ставит stealth/anti-bot»; обход защит нарушает ToS площадок и ставит под удар аккаунты клиентов агентства.
- **D4Vinci/Scrapling** — мощный скрейпер, но его ценность — именно anti-bot-адаптивность (см. выше). Для SERP у нас XMLRiver/Serpstat по официальным API.
- **cporter202/social-media-scraping-apis** — скрейпинг соцсетей: и политика, и ToS.

## НЕ БЕРЁМ — не наш формат/домен

- **mascanho/RustySEO, DietrichGebert/ponytail, ItzCrazyKns/Vane, Zen4-bit/Proxima** — отдельные десктоп/сервис-приложения, не встраиваются в скрипт-контур; RustySEO можно использовать параллельно как GUI-краулер, интеграция не требуется.
- **wasp-lang/open-saas, garrytan/gstack** — SaaS/стек-бойлерплейты, не про SEO-цикл.
- **MDN MCP server** — веб-документация для фронтенд-разработки; не для этого репозитория.
- **Imbad0202/academic-research-skills** — академический ресёрч; наш evidence-слой уже покрывает fact-check.
- **chopratejas/headroom, revfactory/harness, ai-boost/awesome-harness-engineering** — harness-инжиниринг: идеи (context-компрессия) у нас реализованы своим governance (`token_policy`, distillates, context-pack).
- **ComposioHQ/awesome-claude-skills, cporter202/API-mega-list, itallstartedwithaidea/agent-skills, google/skills, nowork-studio/NotFair** — каталоги/сборники: источник идей, не внедряемый код. Ревизия каталогов — раз в квартал, точечно.
- **spilnoagency статьи (Claude skills for Google Ads, WebMCP)** — методички; их практики (GAQL-запросы, MCP-подключение) отражены в нашем ads-слое и `mcp-preset.py`.

## Правило на будущее

Новый инструмент попадает в seo-cycle, только если проходит четыре вопроса:
(1) не дубль ли уже установленного/реализованного; (2) совместим ли с
политикой (no stealth, secrets in .env, платное за approval, read-only по
умолчанию); (3) официальный ли источник или проверенный мейнтейнер;
(4) встраивается ли в контракты (guarded provider, ledger, approval-gate,
report bundle). Двух «нет» достаточно, чтобы не брать.
