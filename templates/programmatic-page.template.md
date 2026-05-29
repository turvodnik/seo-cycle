---
target_url: /{{category_slug}}/{{slug}}/
type: programmatic
template_version: 1.0
generated_from: programmatic-template-gen.py
dataset_row: {{slug}}
mode: programmatic
tags: [programmatic, {{category_slug}}]
---

# {{h1}}

> {{lead_short}}

## Что это

{{description}}

## Характеристики / параметры

| Параметр | Значение |
|---|---|
| {{param_1_name}} | {{param_1_value}} |
| {{param_2_name}} | {{param_2_value}} |
| {{param_3_name}} | {{param_3_value}} |
| Регион | {{city}} |
| Категория | [[{{category_name}}]] |

## Применение

{{application_text}}

## Цена и доставка в {{city}}

{{price_info}}

**Доставка:** {{delivery_info}}

## FAQ

**{{faq_q1}}**

{{faq_a1}}

**{{faq_q2}}**

{{faq_a2}}

## Связанные страницы

- [[{{category_name}}]] — категория каталога
- [[{{related_1}}]]
- [[{{related_2}}]]

---

## Meta

```yaml
meta_title: "{{meta_title}}"
meta_description: "{{meta_description}}"
canonical: https://{{domain}}/{{category_slug}}/{{slug}}/
og_image: {{og_image}}
```

## JSON-LD plan

- WebPage
- BreadcrumbList
- {{schema_type}}  # Product | Service | LocalBusiness — по project_type

---

<!--
Этот файл сгенерирован программно. Источник данных: `<dataset>.csv`, строка `{{slug}}`.
Для редактирования отдельной страницы — правь напрямую (станет «owned»),
для bulk обновления — изменяй template + dataset → re-run programmatic-template-gen.py.

Уникальные dataset поля доступны как {{field_name}}. Dotted-path: {{nested.field}}.
-->
