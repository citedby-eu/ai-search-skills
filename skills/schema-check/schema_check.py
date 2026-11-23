#!/usr/bin/env python3
"""Read the JSON-LD a non-JavaScript crawler sees on a page and list what is missing.

  python3 schema_check.py https://example.com
  python3 schema_check.py https://example.com/pricing https://example.com/blog/post --json

Standard library only (Python 3.8+). It fetches raw HTML and does not run
JavaScript, which is the point: most AI crawlers do not run it either, so
JSON-LD injected by a script is not seen here.
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser

UA = "ai-search-skills/0.1 (+https://github.com/citedby-eu/ai-search-skills)"

# type -> (required by schema.org/Google docs, recommended)
EXPECT = {
    "Organization": (["name", "url"], ["logo", "sameAs", "description"]),
    "Product": (["name"], ["description", "image", "offers", "brand"]),
    "Offer": ([], ["price", "priceCurrency", "availability"]),
    "SoftwareApplication": (["name"], ["offers", "applicationCategory", "operatingSystem"]),
    "Article": (["headline"], ["datePublished", "dateModified", "author", "image"]),
    "BlogPosting": (["headline"], ["datePublished", "dateModified", "author", "image"]),
    "WebSite": (["name", "url"], []),
    "FAQPage": (["mainEntity"], []),
    "LocalBusiness": (["name", "address"], ["telephone", "openingHours", "url"]),
}


class LD(HTMLParser):
    def __init__(self):
        super().__init__()
        self.blocks, self._on, self._buf = [], False, ""

    def handle_starttag(self, tag, attrs):
        if tag == "script" and (dict(attrs).get("type") or "").lower() == "application/ld+json":
            self._on, self._buf = True, ""

    def handle_endtag(self, tag):
        if tag == "script" and self._on:
            self.blocks.append(self._buf)
            self._on = False

    def handle_data(self, data):
        if self._on:
            self._buf += data


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read(3_000_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return None, str(e)


def flatten(node, out):
    if isinstance(node, list):
        for n in node:
            flatten(n, out)
    elif isinstance(node, dict):
        if "@graph" in node:
            flatten(node["@graph"], out)
        t = node.get("@type")
        if t:
            out.append(node)
        for k, v in node.items():
            if k not in ("@graph",) and isinstance(v, (dict, list)):
                flatten(v, out)


def types_of(node):
    t = node.get("@type")
    return t if isinstance(t, list) else [t]


def check_page(url):
    st, html = fetch(url)
    res = {"url": url, "status": st, "blocks": 0, "parse_errors": 0, "items": [], "findings": []}
    if st != 200:
        res["findings"].append("page answers %s" % st)
        return res
    p = LD(); p.feed(html)
    res["blocks"] = len(p.blocks)
    nodes = []
    for b in p.blocks:
        try:
            flatten(json.loads(b), nodes)
        except json.JSONDecodeError as e:
            res["parse_errors"] += 1
            res["findings"].append("a JSON-LD block does not parse (%s); crawlers drop the whole block" % e.msg)
    if not p.blocks:
        res["findings"].append("no JSON-LD in the served HTML. If your site adds it with JavaScript, a non-JS crawler never sees it.")
    for n in nodes:
        for t in types_of(n):
            if t in EXPECT:
                req, rec = EXPECT[t]
                miss_req = [f for f in req if not n.get(f)]
                miss_rec = [f for f in rec if not n.get(f)]
                res["items"].append({"type": t, "name": str(n.get("name") or n.get("headline") or "")[:60],
                                     "missing_required": miss_req, "missing_recommended": miss_rec})
    is_home = re.match(r"^https?://[^/]+/?$", url) is not None
    seen = {t for n in nodes for t in types_of(n)}
    if is_home and not (seen & {"Organization", "LocalBusiness"}):
        res["findings"].append("home page has no Organization (or LocalBusiness) entity: the page that tells a model who you are")
    if is_home and "WebSite" not in seen:
        res["findings"].append("home page has no WebSite entity")
    # price check inside Offer: a string with a symbol is not machine readable
    for n in nodes:
        if "Offer" in types_of(n) or "AggregateOffer" in types_of(n):
            price = n.get("price")
            if isinstance(price, str) and re.search(r"[^\d.,\s]", price):
                res["findings"].append("Offer price %r contains symbols; use a plain number and priceCurrency" % price)
            if price is not None and not n.get("priceCurrency"):
                res["findings"].append("Offer has a price but no priceCurrency")
    return res


def render(r):
    out = ["%s  (status %s, %d JSON-LD block(s))" % (r["url"], r["status"], r["blocks"])]
    for it in r["items"]:
        line = "  %-20s %s" % (it["type"], it["name"])
        out.append(line)
        if it["missing_required"]:
            out.append("      missing required:    " + ", ".join(it["missing_required"]))
        if it["missing_recommended"]:
            out.append("      missing recommended: " + ", ".join(it["missing_recommended"]))
    for f in r["findings"]:
        out.append("  ! " + f)
    if not r["findings"] and r["items"] and not any(i["missing_required"] for i in r["items"]):
        out.append("  ok: no required property missing")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("urls", nargs="+")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    results = [check_page(u if re.match(r"^https?://", u) else "https://" + u) for u in a.urls]
    if a.json:
        print(json.dumps(results, indent=2))
    else:
        print("\n\n".join(render(r) for r in results))
        print("\nNot measured: whether any assistant uses this markup. Schema helps machines read a page; it is not a citation switch.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
