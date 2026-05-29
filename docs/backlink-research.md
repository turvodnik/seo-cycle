# Backlink Research & Monitoring

Workflow для аудита, отслеживания и наращивания backlink-профиля. Не отдельная Phase, а **cross-cutting** между Phase 1 (baseline audit), Phase 9 (monitoring), Phase 10 (action triggers).

Активируется через `backlinks.enabled: true` в `seo-cycle.yaml`.

## Источники данных

Сейчас — **manual import**. В будущем — API integration.

| Источник | Тип | Что даёт | Стоимость |
|---|---|---|---|
| **Ahrefs Site Explorer** | export CSV | Backlinks, DR, anchor texts, lost/new | Платно ($99+/мес) |
| **SEMrush Backlink Analytics** | export CSV | Похожее на Ahrefs | Платно ($120+/мес) |
| **Search Atlas Backlinks** | export CSV | Бюджетный аналог | Платно ($49+/мес) |
| **Google Search Console «Links»** | export | Топ-1000 ссылок, бесплатно | Free (но менее полно) |
| **Bing Webmaster Tools** | export | Доп. данные | Free |
| **Common Crawl** (через `ohcrawl` или ручной парс) | DIY | Самый широкий охват | Free + время |
| **Manual brand monitoring** | Google Alerts, Mention.com | Brand mentions (часто без ссылок) | Free / Freemium |

## Setup

```yaml
backlinks:
  enabled: true
  source: manual                              # manual | ahrefs | semrush | gsc
  file: "./backlinks.csv"                     # CSV экспорт
  min_dr_for_alerts: 30                       # уведомлять о потерях ссылок с DR >= N
```

### Формат `backlinks.csv` (универсальный)

```csv
source_url,source_domain,target_url,anchor_text,domain_rating,page_authority,first_seen,last_seen,link_type,nofollow
https://example.com/post,example.com,https://yoursite.com/page,minwool guide,55,42,2025-03-15,2026-05-20,article,false
```

Минимум: `source_url`, `target_url`, `anchor_text`, `domain_rating`. Остальное — опц.

## Phase 1: Baseline audit

При первом запуске цикла на проекте:

```bash
# 1. Export из GSC (бесплатно):
# GSC → Links → Top linking sites → Export → CSV
# Сохрани в backlinks-gsc.csv

# 2. Если есть подписка Ahrefs/SEMrush:
# Export всех backlinks за «all time» с фильтром Active=Yes
# Сохрани в backlinks.csv

# 3. Анализ:
python3 -c "
import csv
with open('backlinks.csv') as f:
    rows = list(csv.DictReader(f))
print(f'Total: {len(rows)}')
print(f'Unique domains: {len(set(r[\"source_domain\"] for r in rows))}')
print(f'DR distribution:')
from collections import Counter
buckets = Counter(['DR'+str(int(float(r['domain_rating'])//10)*10) for r in rows if r.get('domain_rating')])
for k, v in sorted(buckets.items()):
    print(f'  {k}-{int(k[2:])+9}: {v}')
"
```

Что выявить в baseline (записать в `01-audit.md` секция «Backlinks»):

- [ ] **Total backlinks** + **unique referring domains** (RD)
- [ ] **DR/DA distribution** — сколько высокоавторитетных (DR>50), средних (20-50), низких (<20)
- [ ] **Anchor text distribution** — exact match / branded / generic / naked URL ratio
- [ ] **Топ-страницы** по числу ссылок (концентрация / распределение)
- [ ] **Топ-RD** (топ-20 доменов которые ссылаются)
- [ ] **Toxic links** — спам/сетки/PBN — отметить для disavow
- [ ] **Lost backlinks** за последние 90 дней (если есть исторические данные)
- [ ] **Конкуренты vs мы** — RD ratio, gap analysis

## Phase 9: Регулярный мониторинг

Cadence из `monitoring.cadence` (default 2 weeks):

```bash
# 1. Export fresh backlinks → новый backlinks.csv (или backlinks-YYYY-MM-DD.csv)
# 2. Сравни с прошлым snapshot
diff <(sort backlinks-2026-05-12.csv) <(sort backlinks-2026-05-26.csv) > backlinks-delta.txt

# 3. Нормализуй в snapshot.json
# (TODO: scripts/backlinks-normalize.py — в roadmap)
```

В `09-monitoring/YYYY-MM-DD-snapshot.json` добавь секцию:

```json
{
  "backlinks": {
    "total": 1234,
    "referring_domains": 156,
    "delta_total": +23,
    "delta_rd": +5,
    "new": [{"domain": "example.com", "url": "...", "dr": 65}],
    "lost": [{"domain": "..., "url": "...", "dr": 52}],
    "by_dr_bucket": {"50+": 12, "30-49": 45, "10-29": 87, "0-9": 12}
  }
}
```

## Phase 10: Action triggers

В `config/triggers.yaml` уже есть базовые правила для backlinks. Расширь под проект:

```yaml
triggers:
  - id: lost_top_backlink
    when: "backlinks.lost contains domain_rating >= 50"
    scope: backlinks
    action: "Outreach к ушедшим ссылающимся для восстановления (либо найти замену)"
    priority: P1
    delegate: link_building

  - id: gained_top_backlink
    when: "backlinks.gained contains domain_rating >= 50"
    scope: backlinks
    action: "Новая авторитетная ссылка — закрепить отношения (благодарность, доп.контент)"
    priority: P2

  - id: rd_growth_slow
    when: "monitoring.delta_rd <= 0 AND days_since_baseline > 30"
    scope: backlinks
    action: "Зависший backlink-профиль — активная PR/outreach кампания"
    priority: P1
    delegate: link_building

  - id: anchor_text_overoptimization
    when: "anchor_distribution.exact_match > 0.30"
    scope: backlinks
    action: "Слишком много exact-match анкоров — риск Penguin, разбавь branded"
    priority: P0
```

## Стратегии получения новых backlinks (delegate.link_building)

См. `seo-linkbuilder` агент. Краткий чеклист подходов:

1. **Linkable assets** — данные/исследования/инфографика которыми хочется поделиться
2. **HARO** (now Connectively) — отвечать на запросы журналистов
3. **Guest posting** — гостевые статьи на тематических ресурсах
4. **Resource pages** — попадание в «top X tools/articles» списки
5. **Broken link building** — найти битые ссылки на тематических страницах и предложить свою замену
6. **Skyscraper** — улучшить существующую популярную статью и outreach
7. **PR / media outreach** — питч интересных тем журналистам
8. **Industry partnerships / sponsorships** — официальные партнёрства с упоминанием
9. **Catalogs / directories** (только профильные и moderated)
10. **Forum / Q&A participation** — полезные ответы на Reddit, Quora, Я.Кью

**Запреты:** покупка ссылок, PBN, ссылочные биржи (Sape и аналоги), comment spam, automated outreach без персонализации.

## Toxic links + Disavow

Для GSC доступна disavow tool. Не использовать без необходимости — Google уже игнорирует большинство мусора. Disavow только если:
- Получено manual action для backlinks
- Явно видна негативная SEO атака
- Унаследовали мусор от prev owner домена

Формат disavow.txt:
```
domain:spam-domain.com
https://spam-page.com/your-page/
```

Submit: GSC → Disavow links tool → upload.

## Метрики для отслеживания

| Метрика | Что значит | Цель |
|---|---|---|
| **Total backlinks** | Все ссылки (включая дубликаты с одного домена) | Рост |
| **Referring domains (RD)** | Уникальные домены | Рост — главный показатель |
| **DR / DA average** | Средний авторитет | Рост |
| **Anchor text profile** | % branded / generic / exact / naked | Branded > 50%, exact < 20% |
| **Lost / Gained ratio** | Динамика | Gained > Lost |
| **Linking root domains growth** | % рост RD за период | 5-10%/мес — здоровый |

## Связанные файлы

- `01-audit.md` — baseline secrion «Backlinks»
- `09-monitoring/` — снапшоты с backlinks секцией
- `triggers.yaml` — правила для Phase 10
- `seo-linkbuilder` агент — стратегия и тактика
- `docs/eeat-audit.md` — backlinks как сигнал Authoritativeness
