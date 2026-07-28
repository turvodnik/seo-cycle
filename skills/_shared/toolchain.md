## Optional AI/dev support toolchain

Если задача касается развития самого `seo-cycle`, больших рефакторингов, evidence ingestion или построения графов знаний, можно использовать локальный support-набор:

```bash
bash ~/.codex/skills/seo-cycle/scripts/install-ai-toolchain.sh --codex
```

Назначение:

- GitHub Spec Kit (`specify`) — только для крупных изменений в коде/архитектуре: constitution/spec/plan/tasks/implementation. Не использовать как замену SEO-фазам.
- Microsoft MarkItDown (`markitdown`) — trusted local ingestion: PDF/XLSX/DOCX/PPTX/HTML/YouTube в Markdown перед fact-check/evidence extraction. Не передавать ему непроверенные пользовательские URL без явного разрешения.
- Graphify (`graphify`) — mixed graph по коду, docs, markdown, research artifacts и media; полезен для cross-project knowledge graph и связи docs/code/research.
- CodeGraph (`codegraph`) — local code-symbol graph и Codex MCP для навигации по коду без массового чтения файлов.
- NotebookLM MCP (`notebooklm`) — gated bridge к curated expert knowledge base пользователя. Подключать только через `install-ai-toolchain.sh --codex --notebooklm`, после Google `setup_auth`, и использовать ответы только с citations/source excerpts. Не считать NotebookLM прямым ranking signal; это synthesis из загруженных пользователем источников.

Не ставить по умолчанию и не использовать без отдельного решения: CloakBrowser/CloakMCP и другие stealth/anti-bot инструменты; paid APIs; memory-сервисы, которые уводят данные во внешний сервис. Для SEO-сбора соблюдай robots, rate limits, project policy и source terms.
