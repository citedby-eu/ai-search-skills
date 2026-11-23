---
name: schema-check
description: Lists the JSON-LD (Organization, Product/Offer, Article, WebSite, FAQPage, LocalBusiness) that a non-JavaScript crawler sees on a page and what required or recommended properties are missing. Use when the user asks about structured data, schema markup, or why an AI answer gets the product name, price or company facts wrong.
metadata:
  author: citedby-eu
  source: https://github.com/citedby-eu/ai-search-skills
  version: 0.1.0
---

# Schema check (what a crawler without JavaScript sees)

```bash
python3 skills/schema-check/schema_check.py <url> [<url> ...] [--json]
```

It fetches the raw HTML, parses every `application/ld+json` block, flattens `@graph`, and reports per entity the missing required and recommended properties. It does not run JavaScript on purpose: markup a script injects after load is invisible to most AI crawlers too.

## Pages to run it on

Home (needs Organization and WebSite), the pricing page (Product or SoftwareApplication with Offers), one article, and any page where an assistant got a fact wrong.

## Findings worth a fix, in order

1. No JSON-LD in the served HTML (rendered by script only).
2. A block that does not parse: the whole block is dropped.
3. Home without Organization: the page that tells a model who you are, with `name`, `url`, `logo`, `sameAs` (your real profiles).
4. Offer prices with symbols (`"$19"`) or no `priceCurrency`: use a number string plus a currency code, and keep it equal to the visible price.
5. Missing recommended properties.

## Honest limits

Schema helps machines read a page. It is not a citation switch, and we do not know that any assistant ranks on it. Do not invent properties to fill gaps (no fake ratings, reviews or authors); a missing property is better than a false one.

## Report

`ai-visibility/03-schema.md`: per page, entities found, fixes as ready-to-paste JSON-LD with the real values from the page.
