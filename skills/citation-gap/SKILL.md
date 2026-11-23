---
name: citation-gap
description: Turns citation-probe logs into a competitor citation gap - which domains and page types assistants cite on your buyer questions where your domain is absent. Use after citation-probe, when the user asks "why do competitors get cited instead of us" or "what page should we build".
metadata:
  author: citedby-eu
  source: https://github.com/citedby-eu/ai-search-skills
  version: 0.1.0
---

# Citation gap

```bash
python3 skills/citation-gap/gap.py probes/*.jsonl --domain acme.com [--min-share 0.3] [--md ai-visibility/05-citation-gap.md]
```

Per question: how many answers were read, in how many your domain was cited, and every other domain cited in at least `--min-share` of them, with the page types (comparison, list, pricing, blog post, free tool, docs) and an example URL.

## Turn it into work

1. Open each example URL for the top 3 domains per question. Write one line: what does it answer in its first screen that your page does not?
2. Group by page type. If three rivals are cited through "vs" or "best X" pages and you have none, that page type is the first build.
3. A page you already have that is never cited: run `ai-crawler-access` and `schema-check` on it before writing anything new.
4. Sources that are directories, review sites or forums are not pages to copy; they are places to be listed or to answer honestly, under your own name.

## Limits

It shows what the assistants reached for on these runs. It does not show why, and a page of the same type is not a guarantee of being cited. Re-run after you ship, on 3 or more days, and report the change as "cited in X of N before, Y of N after".
