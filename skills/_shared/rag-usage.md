## Локальный RAG (перед написанием и ресёрчем)

`seo/rag.db` (FTS5/BM25, русский из коробки, embeddings опциональны через env `EMBEDDING_API_*`). Индексирует source packs, entity triplets, дистилляты и драфты. Перед Phase 4/6 запроси контекст:

```bash
seo-cycle rag query "<primary keyword>" --top-k 5 --source-type source_pack --source-type distillate
seo-cycle rag query "<сущность>" --global          # пересечения с другими проектами агентства
seo-cycle run script page-outline-v3 <pkg> --all-mvp --rag --write   # брифы с related_passages
```

Индекс обновляй `seo-cycle rag index --write` после новых distillates/drafts (инкрементально, дёшево). Кросс-проектный: `rag index --global` по машинному реестру проектов.

Деньги (T-069): если настроен платный провайдер эмбеддингов (`EMBEDDING_API_*`), и `rag index --write`, и `rag query` (гибридный режим) делают один и тот же платный вызов `/embeddings` — оба проходят предполётную проверку usage-ledger (`embedding_api`, категория `llm`; блок → код 2) и пишут расход после вызова. `rag query --global` вне проекта (нет `seo-cycle.yaml` в текущем каталоге) учесть расход не может: `--mode auto` откатывается на BM25 с пометкой, явный `--mode hybrid` — код 2. Без `EMBEDDING_API_*` всё офлайн и бесплатно.
