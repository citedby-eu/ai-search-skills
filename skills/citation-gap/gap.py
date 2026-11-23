#!/usr/bin/env python3
"""Competitor citation gap from probe.py logs: who gets cited where you do not.

  python3 gap.py probes/*.jsonl --domain acme.com
  python3 gap.py probes/*.jsonl --domain acme.com --min-share 0.3 --md gap.md

Standard library only (Python 3.8+). Input is the JSONL written by
citation-probe/probe.py (rows with status 200). For each query it lists the domains
the assistants cited, how often, whether you were among them, and the page types
those domains were cited for. The output is a list of pages to look at and build,
not a verdict on why an assistant chose them.
"""
import argparse
import glob
import json
import re
import sys
import urllib.parse
from collections import Counter, defaultdict


def load(paths):
    rows = []
    for pat in paths:
        for p in glob.glob(pat):
            for line in open(p, encoding="utf-8"):
                if line.strip():
                    r = json.loads(line)
                    if r.get("status") == 200:
                        rows.append(r)
    return rows


def host(url, title=""):
    h = urllib.parse.urlsplit(url).netloc.lower()
    h = h[4:] if h.startswith("www.") else h
    if "vertexaisearch" in h and re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", title.lower()):
        return title.lower()
    return h


def page_type(url):
    p = urllib.parse.urlsplit(url).path.lower().strip("/")
    if not p:
        return "home"
    for key, label in (("vs", "comparison"), ("compare", "comparison"), ("alternative", "alternatives"),
                       ("pricing", "pricing"), ("blog", "blog post"), ("guide", "guide"), ("tool", "free tool"),
                       ("docs", "docs"), ("best", "list"), ("review", "review")):
        if re.search(r"(^|[/-])" + key, p):
            return label
    return "page"


def analyse(rows, domain, min_share):
    dom = domain.lower().replace("www.", "")
    per_q = defaultdict(list)
    for r in rows:
        per_q[r["query"]].append(r)
    report = []
    for q, rs in per_q.items():
        n = len(rs)
        cited_in = Counter()
        types = defaultdict(Counter)
        urls = defaultdict(Counter)
        you = 0
        for r in rs:
            seen = set()
            for c in r.get("citations", []):
                h = host(c["url"], c.get("title", ""))
                if not h:
                    continue
                seen.add(h)
                types[h][page_type(c["url"])] += 1
                if "vertexaisearch" not in c["url"]:
                    urls[h][c["url"]] += 1
            for h in seen:
                cited_in[h] += 1
            if any(h == dom or h.endswith("." + dom) for h in seen):
                you += 1
        gap = [(h, k, k / n, types[h].most_common(2), urls[h].most_common(1))
               for h, k in cited_in.most_common()
               if not (h == dom or h.endswith("." + dom)) and k / n >= min_share]
        report.append({"query": q, "answers": n, "you_cited": you, "gap": gap})
    return report


def to_md(report, domain):
    out = ["# Citation gap for %s" % domain, ""]
    for r in report:
        out.append("## %s" % r["query"])
        out.append("Answers read: %d. %s cited in %d of %d." % (r["answers"], domain, r["you_cited"], r["answers"]))
        if not r["gap"]:
            out.append("\nNo other domain reaches the share threshold on this query.\n")
            continue
        out += ["", "| Domain | Cited in | Page types | Example URL |", "|---|---|---|---|"]
        for h, k, share, ty, ex in r["gap"][:10]:
            out.append("| %s | %d of %d | %s | %s |" % (
                h, k, r["answers"], ", ".join("%s x%d" % t for t in ty), ex[0][0] if ex else ""))
        out.append("")
    out.append("Read this as: which pages the assistants reached for, on these runs. "
               "Open each example URL and ask what it answers that your page does not. "
               "It does not tell you why the assistant chose it.")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--domain", required=True)
    ap.add_argument("--min-share", type=float, default=0.3, help="share of answers a domain must be cited in (default 0.3)")
    ap.add_argument("--md")
    a = ap.parse_args(argv)
    rows = load(a.files)
    if not rows:
        print("no successful rows"); return 1
    md = to_md(analyse(rows, a.domain, a.min_share), a.domain)
    if a.md:
        open(a.md, "w", encoding="utf-8").write(md + "\n"); print("wrote", a.md)
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
