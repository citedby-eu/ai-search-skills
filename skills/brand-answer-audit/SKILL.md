---
name: brand-answer-audit
description: Checks what AI answers say about your own brand (price, plans, what it does, who runs it) against facts you wrote down, and lists answers that are wrong, missing or say "I don't know". Use when the user asks "what does ChatGPT say about us", "AI quotes our old price", or "is the AI description of our product right".
metadata:
  author: citedby-eu
  source: https://github.com/citedby-eu/ai-search-skills
  version: 0.1.0
---

# Brand answer audit

## Steps

1. Copy `facts.example.json` to `facts.json` and fill it from your own live pages: brand, plans with prices, what the product does, anything you never offer. Each fact has `expect` (strings that are true), optional `forbid` (wording that is false), and `kind: "price"` for money.
2. Add 3 to 5 brand questions to a queries file ("What is Acme?", "How much does Acme cost?", "Acme pricing plans", "Is Acme legit?", "Acme vs Rival") and run `citation-probe` with `--runs 5`.
3. ```bash
   python3 skills/brand-answer-audit/brand_audit.py facts.json probes/brand-*.jsonl --csv ai-visibility/06-brand-rows.csv
   ```

## The rule that matters

Every flagged row is a place to look, not a verdict. A pattern match cannot tell a wrong price from a competitor's price in the same sentence, a yearly price from a monthly one, or a different product line. Open each flagged sentence, fill `your_verdict` in the CSV (true error / misread), and report only the rows you confirmed. Also report coverage: an answer that never names your brand is "not found", which is a different finding from "wrong".

## Fixing a confirmed error

Find where the wrong fact comes from: the `citation-probe` JSONL lists the cited URLs. The usual causes are an old page still live, a price only in an image, a rival's comparison page, or two prices on one page. Fix the source page, then re-run on 3 or more days. Do not promise the assistant will change.
