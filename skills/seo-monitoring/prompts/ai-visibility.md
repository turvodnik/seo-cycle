# AI-visibility / GEO — единый свод присутствия в AI-поиске

Сводит в один отчёт, цитируют ли тебя AI-поверхности: **Яндекс Нейро**, **Google AI
Overviews**, **ChatGPT**, **Perplexity**, **Gemini**. Применяется в Phase 9 (мониторинг)
и Phase 4/6 (чтобы писать контент под цитируемость). Дополняет AEO (ответ в первых
400 символах, FAQPage, citable-пассажи в Entity Map).

> Цель — не просто «ранжироваться», а **попадать в AI-ответ как источник**. Для РФ
> ключевое — Яндекс Нейро (Алиса/Поиск с Нейро) + GigaChat, затем западные LLM.

## Источники данных (по доступности)
- **Платные/плагины:** `seo-seranking` (AI Share-of-Voice по ChatGPT/Gemini/Perplexity/AI Overviews/AI Mode), `seo-profound` (LLM citations time-series), `claude-seo:seo-geo` (citability scoring, llms.txt, AI-crawler доступность), DataForSEO AI visibility.
- **Браузер (бесплатно, оба рантайма):** Claude in Chrome MCP / Codex browser — задать целевые вопросы в Яндекс (с Нейро), Google (AI Overviews), ChatGPT, Perplexity и снять, цитируют ли нас/конкурентов.

## Чек-лист свода (по целевым ключам/вопросам)
```
Для каждого приоритетного вопроса (из target_local_keywords + info-интентов):
1. Яндекс: есть ли блок Нейро? кто процитирован? есть ли мы?
2. Google: есть ли AI Overview? источники? есть ли мы?
3. ChatGPT (web) / Perplexity: при вопросе по теме — упоминают ли наш бренд/сайт?
4. Зафиксируй: surface | вопрос | мы (да/нет) | кто процитирован вместо нас.
```

## Что чинить, если не цитируют
- AEO-абзац: прямой ответ 2-3 предложения в первых ~400 символах страницы.
- FAQPage + citable-пассажи (Entity Map раздел) — структурированные факты.
- E-E-A-T: канонический org-узел (`schema-org-build.py`), trust-блок источников (`eeat-render.py`).
- `llms.txt` + доступность для AI-краулеров (проверить через `seo-geo`).
- Фактическая точность (fact_check_log) — LLM цитируют то, чему «доверяют».

## Выход
`<cycle>/09-monitoring/ai-visibility-<date>.md` — таблица surface × вопрос × присутствие + список доработок (→ ICE/Phase 10). Отслеживать динамику между снапшотами.

## РФ-приоритет
Сначала Яндекс Нейро + GigaChat (российская аудитория), затем Google AI Overviews и западные LLM. Контент уже оптимизирован под AEO → это усиление под генеративные ответы.
