## Локальный RAG (перед написанием и ресёрчем)

`seo/rag.db` (FTS5/BM25, русский из коробки, embeddings опциональны через env `EMBEDDING_API_*`). Индексирует source packs, entity triplets, дистилляты и драфты. Перед Phase 4/6 запроси контекст:

```bash
seo-cycle rag query "<primary keyword>" --top-k 5 --source-type source_pack --source-type distillate
seo-cycle rag query "<сущность>" --global          # пересечения с другими проектами агентства
seo-cycle run script page-outline-v3 <pkg> --all-mvp --rag --write   # брифы с related_passages
```

Индекс обновляй `seo-cycle rag index --write` после новых distillates/drafts (инкрементально, дёшево). Кросс-проектный: `rag index --global` по машинному реестру проектов.
