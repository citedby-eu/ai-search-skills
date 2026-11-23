---
name: llms-txt
description: Validates an existing llms.txt (catches HTML soft-404s, missing H1, relative links, dead links) or generates one from a site's sitemap. Use when the user asks for llms.txt, "add llms.txt", "is my llms.txt right", or wants a clean machine-readable site summary.
metadata:
  author: citedby-eu
  source: https://github.com/citedby-eu/ai-search-skills
  version: 0.1.0
---

# llms.txt: validate or generate

Format: https://llmstxt.org (H1 with the name is the only required part; then an optional blockquote summary, then H2 sections of `- [title](url): note` links).

## Say this first

There is no published evidence that AI search crawlers read llms.txt, and studies found no clear link to citations (https://citedby.eu/blog/does-llms-txt-work). Treat the file as cheap hygiene and a clean summary for agents and tools that do fetch it. Never sell it as a ranking or citation lever.

## Validate

```bash
python3 skills/llms-txt/llms_txt.py validate <domain|./llms.txt> [--check-links]
```

Errors: HTML served at `/llms.txt` (soft 404), no H1, a link that returns 4xx/5xx. Warnings: no summary, no sections, relative links, bare URLs, links without notes, file over 200 KB.

## Generate

```bash
python3 skills/llms-txt/llms_txt.py generate <domain> --max-pages 40 --out llms.txt
```

Reads `sitemap.xml` (and child sitemaps), takes the shortest paths first, fetches each page's title and meta description, groups by first path segment. Then **edit it by hand**: drop pages that are thin, duplicate, gated or stale, and rewrite notes so each says what question the page answers. A stale llms.txt that lists removed pages is worse than none.

## Report

`ai-visibility/02-llms-txt.md`: validation output, what you changed, and the sentence above.
