## Самооценка результатов (scorecard, обязательна)

**После каждой содержательной задачи ставь честную оценку 0–10 в двух местах: в ответе пользователю и в scorecard проекта.** Loop-runner делает это сам (passed/escalated); всё остальное — руками:

```bash
seo-cycle score record --tool <task-name> --score 8.5 \
  --done "что сделано" --done "ещё пункт" \
  --missing "чего не хватает" [--status done|partial|failed]
seo-cycle score show               # таблица последних оценок (видна и в journey)
seo-cycle score record --tool gate --findings-json <report.json>  # авто-оценка из findings
```

Правила честной оценки: 10 = сделано полностью и проверено; каждая нерешённая критика −3, ошибка −2, warning −0.75 (та же формула, что в `score_from_findings`). Не завышай: «частично» = `--status partial` со списком `--missing`. В чате всегда дублируй кратко: «Оценка: 8.5/10 — сделано X, Y; не хватает Z».
