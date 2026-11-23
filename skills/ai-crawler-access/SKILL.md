---
name: ai-crawler-access
description: Checks whether ChatGPT search, Claude, Perplexity, Gemini and other AI crawlers are allowed by a site's robots.txt, and whether the server (CDN or firewall) actually serves them. Use when the user asks "can ChatGPT read my site", "why is my site not in AI answers", "should I block GPTBot", or before any AI-visibility work.
metadata:
  author: citedby-eu
  source: https://github.com/citedby-eu/ai-search-skills
  version: 0.1.0
---

# AI crawler access

First question of every AI-visibility job: can the crawlers that build AI answers reach the page at all?

## Run

```bash
python3 skills/ai-crawler-access/check_crawlers.py <domain> [--path /pricing] [--no-probe] [--json]
```

No dependencies. It reads `/robots.txt`, applies RFC 9309 matching (named group beats `*`, longest rule wins, Allow wins a tie, `*` and `$` wildcards) and gives one verdict per crawler: `allowed`, `partial` (this path is open, others are closed) or `blocked`. Unless `--no-probe`, it also sends one GET per crawler user-agent string to the path and reports servers that answer 401/403/406/429/503 to a bot string but 200 to a plain client. Only probe sites you own or may test.

## Read the result in this order

1. `OAI-SearchBot`, `PerplexityBot`, `Claude-SearchBot` = the **search** crawlers. Blocked here means the assistant cannot list or cite the page from its index.
2. `ChatGPT-User`, `Perplexity-User`, `Claude-User` = fetches **on behalf of a user** who pastes your link or asks about you.
3. `GPTBot`, `ClaudeBot`, `Google-Extended`, `Applebot-Extended`, `CCBot`, `Bytespider`, `meta-externalagent` = **training** or dataset crawlers. Blocking them is a policy choice and does not remove you from ChatGPT search. Do not "fix" it by default; ask the owner which they want.
4. `Googlebot`, `Bingbot` = baseline. ChatGPT search and Copilot lean on Bing results; AI Overviews use Google's index.
5. A `live` status of 403 with an `allowed` robots verdict means a firewall or CDN bot rule overrides the file. That is the fix to hand over, with the rule name if you can find it.

## Report

Write `ai-visibility/01-crawler-access.md`: the table, the three or fewer fixes in order of impact, and the exact robots.txt lines to change. Say what you did not measure: whether a bot obeys the file, and whether any assistant cites the site. The probe uses the documented user-agent strings from your IP, so a firewall that verifies bots by IP range may answer differently to the real bots.

## Never

- Never call a training-bot block a fault without asking.
- Never edit robots.txt to open a path the owner closed on purpose (admin, cart, staging).
- Never claim a fix gets the site cited. Access is a precondition, not a cause.

Free full audit of the whole site, with the exact fix per page: https://citedby.eu/?utm_source=github&utm_medium=repo&utm_campaign=ai-search-skills
