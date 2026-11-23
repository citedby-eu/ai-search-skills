#!/usr/bin/env python3
"""Ask AI assistants your money queries, several times, and log who gets named and cited.

  export GEMINI_API_KEY=...        # and/or ANTHROPIC_API_KEY, OPENAI_API_KEY, PERPLEXITY_API_KEY
  python3 probe.py run --queries queries.txt --brand "Acme" --domain acme.com \
        --providers gemini,anthropic --runs 5 --out probes/2026-11-23.jsonl
  python3 probe.py report probes/*.jsonl

Standard library only (Python 3.8+). Your keys, your cost: each call is one paid API
request with the provider's web search on. `--dry-run` prints the call count first;
`--max-calls` (default 60) stops a typo from spending money.

What this is not: the API answers are not the consumer apps' answers (no personal
history, different location, different tools), and every run differs. Read it as
"named in X of N runs", repeated on several days, never as a ranking or a promise.
Provider status: anthropic was tested live (23 Nov 2026). gemini, openai and perplexity
are written from the vendors' docs and tested on fixtures only (our Gemini key hit its
quota, so the live check did not complete). Model names change: pass --model provider=name.
"""
import argparse
import datetime
import glob
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_MODELS = {
    "gemini": "gemini-3.8-flash",
    "anthropic": "claude-haiku-4-5",
    "openai": "gpt-5-mini",
    "perplexity": "sonar",
}
KEYS = {"gemini": "GEMINI_API_KEY", "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY", "perplexity": "PERPLEXITY_API_KEY"}


def post(url, headers, body, timeout=120):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers=dict(headers, **{"Content-Type": "application/json"}))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            return e.code, {}
    except Exception as e:
        return None, {"error": str(e)}


# ---- providers: each returns (answer_text, [ {url,title} ]) from a raw response ----

def parse_gemini(d):
    c = (d.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in (c.get("content") or {}).get("parts", []))
    cites = []
    for ch in (c.get("groundingMetadata") or {}).get("groundingChunks", []):
        w = ch.get("web") or {}
        if w.get("uri"):
            cites.append({"url": w["uri"], "title": w.get("title", "")})
    return text, cites


def parse_anthropic(d):
    text, cites = "", []
    for b in d.get("content", []):
        if b.get("type") == "text":
            text += b.get("text", "")
            for c in b.get("citations") or []:
                if c.get("url"):
                    cites.append({"url": c["url"], "title": c.get("title", "")})
        elif b.get("type") == "web_search_tool_result" and isinstance(b.get("content"), list):
            for r in b["content"]:
                if r.get("url"):
                    cites.append({"url": r["url"], "title": r.get("title", "")})
    return text, cites


def parse_openai(d):
    text, cites = "", []
    for item in d.get("output", []):
        if item.get("type") == "message":
            for part in item.get("content", []):
                text += part.get("text", "")
                for a in part.get("annotations", []):
                    if a.get("type") == "url_citation" and a.get("url"):
                        cites.append({"url": a["url"], "title": a.get("title", "")})
    return text, cites


def parse_perplexity(d):
    text = ((d.get("choices") or [{}])[0].get("message") or {}).get("content", "")
    cites = [{"url": u, "title": ""} for u in d.get("citations", []) if isinstance(u, str)]
    for r in d.get("search_results", []) or []:
        if r.get("url") and not any(c["url"] == r["url"] for c in cites):
            cites.append({"url": r["url"], "title": r.get("title", "")})
    return text, cites


def call(provider, model, query, key):
    if provider == "gemini":
        st, d = post("https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % model,
                     {"x-goog-api-key": key},
                     {"contents": [{"parts": [{"text": query}]}], "tools": [{"google_search": {}}]})
        return st, d, parse_gemini
    if provider == "anthropic":
        st, d = post("https://api.anthropic.com/v1/messages",
                     {"x-api-key": key, "anthropic-version": "2023-06-01"},
                     {"model": model, "max_tokens": 1200, "messages": [{"role": "user", "content": query}],
                      "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}]})
        return st, d, parse_anthropic
    if provider == "openai":
        st, d = post("https://api.openai.com/v1/responses", {"Authorization": "Bearer " + key},
                     {"model": model, "input": query, "tools": [{"type": "web_search"}]})
        return st, d, parse_openai
    if provider == "perplexity":
        st, d = post("https://api.perplexity.ai/chat/completions", {"Authorization": "Bearer " + key},
                     {"model": model, "messages": [{"role": "user", "content": query}]})
        return st, d, parse_perplexity
    raise SystemExit("unknown provider " + provider)


# ---- matching ----

def host_of(url, title=""):
    h = urllib.parse.urlsplit(url).netloc.lower()
    if h.startswith("www."):
        h = h[4:]
    # Gemini returns a redirect host; the title then holds the real domain
    if "vertexaisearch" in h and re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", title.lower()):
        h = title.lower()
    return h


def match_row(text, cites, brand, domain, competitors):
    hosts = [host_of(c["url"], c.get("title", "")) for c in cites]
    dom = domain.lower().replace("www.", "") if domain else ""
    return {
        "brand_named": bool(brand and re.search(r"(?<!\w)" + re.escape(brand) + r"(?!\w)", text, re.I)),
        "domain_cited": bool(dom and any(h == dom or h.endswith("." + dom) for h in hosts)),
        "domain_in_text": bool(dom and dom in text.lower()),
        "cited_hosts": sorted(set(hosts)),
        "competitors_named": [c for c in competitors if re.search(r"(?<!\w)" + re.escape(c) + r"(?!\w)", text, re.I)],
    }


def cmd_run(a):
    queries = [l.strip() for l in open(a.queries, encoding="utf-8") if l.strip() and not l.startswith("#")]
    providers = [p.strip() for p in a.providers.split(",") if p.strip()]
    comps = [c.strip() for c in (a.competitors or "").split(",") if c.strip()]
    total = len(queries) * len(providers) * a.runs
    print("%d queries x %d providers x %d runs = %d paid calls" % (len(queries), len(providers), a.runs, total))
    if total > a.max_calls:
        print("over --max-calls %d; raise it on purpose or cut the list" % a.max_calls); return 2
    if a.dry_run:
        return 0
    keys = {}
    for p in providers:
        keys[p] = os.environ.get(KEYS[p], "")
        if not keys[p]:
            print("missing env var %s for %s" % (KEYS[p], p)); return 2
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    n = fails = 0
    with open(a.out, "a", encoding="utf-8") as f:
        for q in queries:
            for p in providers:
                model = a.model.get(p) if isinstance(a.model, dict) else DEFAULT_MODELS[p]
                for i in range(a.runs):
                    st, d, parse = call(p, model or DEFAULT_MODELS[p], q, keys[p])
                    row = {"ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                           "provider": p, "model": model or DEFAULT_MODELS[p], "query": q, "run": i + 1,
                           "brand": a.brand, "domain": a.domain, "status": st}
                    if st == 200:
                        text, cites = parse(d)
                        row.update(answer=text, citations=cites)
                        row.update(match_row(text, cites, a.brand, a.domain, comps))
                    else:
                        fails += 1
                        row["error"] = json.dumps(d)[:300]
                    f.write(json.dumps(row, ensure_ascii=False) + "\n"); f.flush()
                    n += 1
                    time.sleep(a.delay)
    print("wrote %d rows to %s (%d failed calls: failed rows are kept and excluded from counts)" % (n, a.out, fails))
    return 0


def load(paths):
    rows = []
    for pat in paths:
        for p in glob.glob(pat):
            for line in open(p, encoding="utf-8"):
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def cmd_report(a):
    rows = [r for r in load(a.files) if r.get("status") == 200]
    if not rows:
        print("no successful rows"); return 1
    days = sorted({r["ts"][:10] for r in rows})
    print("%d answers on %d day(s): %s" % (len(rows), len(days), ", ".join(days)))
    if len(days) < 3:
        print("note: fewer than 3 days. One day is a snapshot, not a pattern.")
    print()
    groups = {}
    for r in rows:
        groups.setdefault((r["query"], r["provider"]), []).append(r)
    print("%-56s %-10s %-10s %s" % ("query", "provider", "named", "domain cited"))
    for (q, p), rs in sorted(groups.items()):
        nm = sum(r["brand_named"] for r in rs); dc = sum(r["domain_cited"] for r in rs)
        print("%-56s %-10s %-10s %s" % (q[:55], p, "%d of %d" % (nm, len(rs)), "%d of %d" % (dc, len(rs))))
    tn = sum(r["brand_named"] for r in rows); td = sum(r["domain_cited"] for r in rows)
    print("\nTotal: named in %d of %d answers, domain cited in %d of %d." % (tn, len(rows), td, len(rows)))
    print("Read as a rate over repeated runs of an API with web search on. It is not the consumer app and not a promise.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--queries", required=True, help="text file, one buyer question per line")
    r.add_argument("--brand", required=True); r.add_argument("--domain", required=True)
    r.add_argument("--competitors", help="comma list of brand names to look for in answers")
    r.add_argument("--providers", default="gemini,anthropic")
    r.add_argument("--model", action="append", default=[], help="provider=model, repeatable")
    r.add_argument("--runs", type=int, default=3); r.add_argument("--delay", type=float, default=1.0)
    r.add_argument("--max-calls", type=int, default=60); r.add_argument("--dry-run", action="store_true")
    r.add_argument("--out", required=True)
    p = sub.add_parser("report"); p.add_argument("files", nargs="+")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        a.model = dict(m.split("=", 1) for m in a.model)
        return cmd_run(a)
    return cmd_report(a)


if __name__ == "__main__":
    sys.exit(main())
