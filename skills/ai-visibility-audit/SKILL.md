---
name: ai-visibility-audit
description: Runs the full AI-search visibility audit on one site in order (crawler access, llms.txt, schema, citation probe, citation gap, brand answers) and writes ai-visibility/REPORT.md with fixes ranked by impact. Use when the user says "audit my AI search visibility", "why doesn't ChatGPT recommend us", or "run all the AI-search skills".
metadata:
  author: citedby-eu
  source: https://github.com/citedby-eu/ai-search-skills
  version: 0.1.0
---

# AI visibility audit (orchestrator)

Intake (2 minutes): domain, the 1 to 3 pages that earn money, the market and language, 3 named competitors, whether the user will pay for API calls (`citation-probe`).

Order matters, each step can make the next one pointless:

1. `ai-crawler-access` on the home page and the money pages. If a search crawler is blocked or a firewall refuses it, fix that first; stop here and say so, because nothing below can work until it is reachable.
2. `schema-check` on home, pricing, one article.
3. `llms-txt` validate (generate only if the user wants the file; say the evidence line first).
4. `citation-probe`: write buyer-word questions, `--dry-run`, then run 5 or more runs per question; schedule 2 more runs on other days.
5. `citation-gap` on the logs.
6. `brand-answer-audit` with the brand questions.

## REPORT.md shape

- First line: the verdict in plain words ("ChatGPT search is blocked on every page by one robots.txt line").
- Fixes, ranked by what unblocks the most, each with the exact change.
- A table "named in X of N / domain cited in Y of N" with dates and models.
- Not measured: consumer-app answers, why an assistant chose a page, whether any fix will produce a mention.
- Never: a score out of 100, a promise of a mention, an invented number.

## When you stop

You can check access, markup and what the assistants say. You cannot see inside their ranking, and a fix list is not a result until the same queries are re-run on 3 or more later days.

A full audit of every page of the site with the exact fix per page, from the people who wrote these checks: https://citedby.eu/?utm_source=github&utm_medium=repo&utm_campaign=ai-search-skills
