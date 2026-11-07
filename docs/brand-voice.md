# Профиль голоса бренда, методов письма и изображений

С 3.1.0 у каждого проекта есть один файл, где заранее записано, **как бренд пишет**:
`seo/brand/voice.yaml` (ключ `policy_files.brand_voice_profile` в `seo-cycle.yaml`).
Раньше тон голоса жил в пяти полях секции `tone:` — и ни одно, кроме стоп-слов,
не доходило ни до брифа, ни до гейта. Теперь профиль попадает:

| Куда | Что там происходит |
|---|---|
| Бриф копирайтера (`page-outline-v3 --write`) | раздел «Голос бренда и метод» в `copywriter-ready/<slug>.md` и ключ `brand_voice` в outline JSON: голос, обращение, метод для типа страницы, лексика, стиль, изображения |
| Context pack задач «написать / переписать текст» | профиль и его примеры читаются первыми |
| Гейт черновика (`seo-cycle loop draft`) | запрещённые и предпочтительные слова, «вы»/«ты», длина предложений и абзацев, кавычки и тире, частота бренда, обязательные изображения |
| Аудит настройки (`setup-gap-audit`) | рекомендательная категория `voice`: что в профиле ещё не заполнено |

## Быстрый старт

```bash
seo-cycle voice init --write     # создать профиль: значения из tone.*, images.*, project.*, locale
seo-cycle voice validate         # структура и что осталось заполнить
seo-cycle voice show --page-type Сравнение   # как блок увидит копирайтер
seo-cycle voice check draft.md   # проверить черновик по профилю
seo-cycle voice extract-prompt --from seo/mirror/blog   # запрос модели: вывести голос из опубликованных текстов
```

Новый проект получает профиль сразу из мастера (`init-project.sh`). Существующий —
командой `seo-cycle voice init --write`; `project-upgrade-assistant` подсказывает её
как новую возможность. `init` никогда не перезаписывает готовый профиль без `--force`.

Примеры из шаблона конфига (описание тона «Деловой, конкретный…», демо-аудитории)
в профиль не переносятся — эти поля остаются пустыми и попадают в «заполни».

## Что внутри

| Раздел | Что задаёт | Пример |
|---|---|---|
| `identity` | кто мы, позиционирование, аудитории с задачей и болями | `audiences: [{name: "Частный застройщик", task: "утеплить дом", pains: ["переплата"]}]` |
| `voice` | summary, атрибуты парами `be`/`not`, formality 1–5, `address` (vy / ty / you / impersonal), `person` (we / brand / impersonal) | `{be: "конкретный: цифры, размеры", not: "«широкий выбор»"}` |
| `lexicon` | `preferred` (как не пишем → как пишем), `forbidden`, `forbidden_regex`, частота бренда, как говорим о конкурентах | `preferred: {"минвата": "минеральная вата"}` |
| `style` | длина предложений и абзацев, кавычки «», тире —, ё, числа цифрами | `sentence_max_words: 25` |
| `methods` | порядок блоков для article / category / product / landing / comparison / howto / tool, aliases, CTA | `comparison: [verdict_first, criteria_table, per_option, …]` |
| `authors`, `first_person_allowed` | реальные эксперты с `proof_url`; только с ними бриф разрешает первое лицо | `[{name: "…", role: "…", proof_url: "https://…"}]` |
| `visuals` | общий стиль, палитра, типы изображений (hero, inline_photo, diagram, comparison_table, product, screenshot, og, icon): источник, стиль, пропорция, текст на картинке, подпись, минимум на странице; какие типы обязательны для какого типа страницы | `per_page_type: {howto: [hero, inline_photo, diagram]}` |
| `examples` | пути к фрагментам «так пишем» / «так не пишем» | `good: [seo/brand/examples/good-1.md]` |
| `disclaimers` | обязательные оговорки | `["Цены — на дату публикации."]` |

Тип страницы берётся из `page_type` outline или frontmatter черновика и сводится к
словарю `article, category, product, landing, comparison, howto, tool`
(`scripts/seo_cycle_core/page_types.py`: Guide → article, «Сравнение» → comparison,
«Карточка товара» → product). Свои названия — через `methods.aliases`.

## Изображения в черновике

- Тип картинки — в title markdown-картинки: `![Плита в разрезе](https://example.com/cut.webp "hero")`.
  Без title картинка считается inline. Декоративной ставь тип `decorative` (для HTML —
  `class="decorative"` или `role="presentation"`): ей не нужны alt и подпись.
- Подпись — следующая непустая строка курсивом (`*Плиту ставят враспор.*`) или
  `<figcaption>` рядом с `<img>`. hero/og/icon подписи не требуют.
- Обложка во frontmatter: `featured_image` + `featured_image_alt`.

## Строгость проверок

В `seo-cycle.yaml`:

```yaml
brand_voice:
  enabled: true        # false — профиль не используется нигде
  enforce: warn        # error — все замечания голоса блокируют черновик
  require_review: false  # true — нужен voice_review: {verdict: pass} во frontmatter
```

Запрещённые слова профиля (`lexicon.forbidden`) — всегда error. Остальное — warning,
при `enforce: error` — error. `require_review` просит модель (или редактора) явно
сверить текст с профилем и записать итог во frontmatter, как `fact_check_log` для
фактов.

Профиль активен, только если файл существует и `brand_voice.enabled` не `false`.
Без профиля бриф, гейт и context pack ведут себя как до 3.1.0.

---

## Brand voice profile (EN)

Since 3.1.0 every project has one file, `seo/brand/voice.yaml`
(`policy_files.brand_voice_profile`), that states up front how the brand writes:
identity and audiences, voice attributes as be/not pairs, formality, how the reader is
addressed, preferred and forbidden terms, sentence/paragraph limits and typography,
the block structure per page type, real authors (the only way to allow an expert first
person), and image types with source, style, ratio, on-image text and caption rules,
plus which types each page type requires.

The profile reaches the copywriter brief (`page-outline-v3`, section «Brand voice and
method» and the `brand_voice` outline key), the context pack of writing tasks (read
first), the draft gate (forbidden/preferred terms, formal vs informal address,
long sentences and paragraphs, quotes and dashes, brand mention density, required
images) and the setup gap audit (advisory `voice` category).

Commands: `seo-cycle voice init --write`, `validate`, `show --page-type T`,
`check <draft>`, `extract-prompt --from <published texts>` (a prompt for a model to
derive the profile; no paid calls). Strictness: `brand_voice.enforce: warn | error`,
`brand_voice.require_review`. No profile file — every output stays as before 3.1.0.
