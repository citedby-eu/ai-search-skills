---
name: citation-probe
description: Asks ChatGPT-style assistants (Anthropic, Gemini, OpenAI, Perplexity APIs with web search on) the buyer questions for a site several times and logs who is named and which URLs are cited, as JSONL. Use when the user asks "does ChatGPT recommend us", "who gets cited for our keywords", or wants a baseline before and after an AI-visibility fix.
metadata:
  author: citedby-eu
  source: https://github.com/citedby-eu/ai-search-skills
  version: 0.1.0
---

# Citation probe

Needs your own API key for at least one provider (`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`, `PERPLEXITY_API_KEY`). You pay the provider; there is no CitedBy account.

## 1. Write the questions (the part that decides everything)

`queries.txt`, one per line, 5 to 10 questions in the words a **buyer** types, not your brand and not your keywords: "best invoicing app for freelancers in Spain", "is X worth it", "X vs Y". Add 1 or 2 brand questions ("what is Acme", "what does Acme cost") for `brand-answer-audit`. Do not lead the answer ("why is Acme the best"). Native language per market, read once by a native speaker.

## 2. Check the cost, then run

```bash
python3 skills/citation-probe/probe.py run --queries queries.txt --brand "Acme" --domain acme.com \
  --competitors "Rival,Other" --providers anthropic --runs 5 --dry-run
python3 skills/citation-probe/probe.py run ... --out probes/$(date +%F).jsonl   # drop --dry-run
python3 skills/citation-probe/probe.py report probes/*.jsonl
```

`--max-calls` (default 60) refuses oversized runs. Each call is a paid request with web search on.

## 3. Rules for reading it

- 5 or more runs per question per provider; answers vary run to run.
- Repeat on 3 or more different days before you call anything a pattern. `report` warns below 3 days.
- Report **"named in X of N"** and **"domain cited in Y of N"**. Never a rank, never a promise of a mention.
- These are API answers. The consumer apps differ (history, location, tools). Say so.
- Failed calls stay in the file with `status != 200` and are excluded from counts. Never refill them by hand.
- Provider status: `anthropic` tested live; `gemini`, `openai`, `perplexity` tested on fixtures only (models change: `--model provider=name`).

Keep the raw JSONL. It is the evidence.

Output: `ai-visibility/04-citation-probe.md` with the table from `report`, the dates, the model names, and the sentence on limits.
