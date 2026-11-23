#!/usr/bin/env python3
"""Validate or generate an llms.txt file (format: https://llmstxt.org).

  python3 llms_txt.py validate example.com            # fetch /llms.txt and check it
  python3 llms_txt.py validate ./llms.txt --check-links
  python3 llms_txt.py generate example.com --max-pages 40 --out llms.txt

Standard library only (Python 3.8+). Honest scope: there is no published evidence
that AI search crawlers read llms.txt (see https://citedby.eu/blog/does-llms-txt-work). This checks that the file is well formed
if you choose to ship one; it is not a ranking or citation lever.
"""
import argparse
import html
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

UA = "ai-search-skills/0.1 (+https://github.com/citedby-eu/ai-search-skills)"
LINK_RE = re.compile(r"^\s*[-*]\s+\[([^\]]+)\]\(([^)\s]+)\)\s*(?::\s*(.*))?$")


def fetch(url, timeout=15, method="GET"):
    req = urllib.request.Request(url, method=method, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(3_000_000) if method == "GET" else b""
            return r.status, r.headers.get("Content-Type", ""), body.decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, "", ""
    except Exception as e:
        return None, "", str(e)


def base_of(target):
    if not re.match(r"^https?://", target):
        target = "https://" + target
    p = urllib.parse.urlsplit(target)
    return p.scheme + "://" + p.netloc


# ---------------- validate ----------------

def validate_text(text, content_type="", base=None, check_links=False):
    """Return (errors, warnings, info). Only the H1 is required by the format."""
    errors, warnings, info = [], [], []
    if "<html" in text[:600].lower() or "text/html" in content_type.lower():
        errors.append("The file is an HTML page, not Markdown (common soft-404: the server returns its 404 page with status 200).")
        return errors, warnings, info
    lines = text.splitlines()
    first = next((l for l in lines if l.strip()), "")
    if not first.startswith("# "):
        errors.append("First line must be an H1 with the site or project name ('# Name'). Found: %r" % first[:60])
    if sum(1 for l in lines if l.startswith("# ")) > 1:
        warnings.append("More than one H1. The format has one: the project name.")
    if not any(l.startswith(">") for l in lines):
        warnings.append("No blockquote summary after the H1 (recommended: one or two sentences saying what the site is).")
    h2 = [l for l in lines if l.startswith("## ")]
    links = []
    for l in lines:
        m = LINK_RE.match(l)
        if m:
            links.append((m.group(1), m.group(2), m.group(3) or ""))
    if not h2:
        warnings.append("No H2 sections. Group links under headings like '## Docs' or '## Products'.")
    if not links:
        warnings.append("No '- [title](url): note' list items found.")
    bare = [l for l in lines if re.match(r"^\s*[-*]\s+https?://", l)]
    if bare:
        warnings.append("%d list item(s) are bare URLs. Use '- [title](url): what it covers'." % len(bare))
    rel = [u for _, u, _ in links if not re.match(r"^https?://", u)]
    if rel:
        warnings.append("%d link(s) are relative; a model reading the file alone cannot resolve them. Use absolute URLs." % len(rel))
    nonote = [t for t, _, n in links if not n.strip()]
    if links and len(nonote) > len(links) / 2:
        warnings.append("Most links have no note after the colon; the note is what tells a model which page to open.")
    if len(text.encode("utf-8")) > 200_000:
        warnings.append("File is over 200 KB; models read it from a limited context. Keep it short and link out.")
    info.append("%d line(s), %d section(s), %d link(s)" % (len(lines), len(h2), len(links)))
    if check_links:
        bad = 0
        for t, u, _ in links[:25]:
            absu = u if re.match(r"^https?://", u) else (urllib.parse.urljoin(base + "/", u) if base else None)
            if not absu:
                continue
            st, _, _ = fetch(absu, method="GET")
            if st is None or st >= 400:
                bad += 1
                errors.append("Link does not load (%s): %s" % (st, absu))
            time.sleep(0.3)
        info.append("checked %d of %d link(s), %d failing" % (min(25, len(links)), len(links), bad))
    return errors, warnings, info


def cmd_validate(a):
    target = a.target
    base = None
    if re.match(r"^(\.|/|~)", target) or target.endswith(".txt") and "/" not in target.replace("llms.txt", ""):
        try:
            text, ctype = open(target, encoding="utf-8").read(), ""
        except OSError as e:
            print("cannot read %s: %s" % (target, e)); return 2
    else:
        base = base_of(target)
        url = base + "/llms.txt"
        st, ctype, text = fetch(url)
        if st != 200:
            print("%s answers %s. No llms.txt (fine: it is optional)." % (url, st)); return 1
    errors, warnings, info = validate_text(text, ctype, base, a.check_links)
    for i in info: print("info   ", i)
    for w in warnings: print("warn   ", w)
    for e in errors: print("ERROR  ", e)
    if not errors and not warnings:
        print("ok      well formed")
    print("\nNote: there is no published evidence that AI assistants read llms.txt. Valid is not the same as used.")
    return 1 if errors else 0


# ---------------- generate ----------------

class Meta(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title, self.desc, self.site, self._t = "", "", "", False

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "title":
            self._t = True
        elif tag == "meta":
            n = (d.get("name") or d.get("property") or "").lower()
            if n == "description" and not self.desc:
                self.desc = d.get("content", "")
            elif n == "og:description" and not self.desc:
                self.desc = d.get("content", "")
            elif n == "og:site_name":
                self.site = d.get("content", "")

    def handle_endtag(self, tag):
        if tag == "title":
            self._t = False

    def handle_data(self, data):
        if self._t:
            self.title += data


def sitemap_urls(base, limit):
    seen, queue, urls = set(), [base + "/sitemap.xml"], []
    while queue and len(urls) < limit * 4:
        sm = queue.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        st, _, body = fetch(sm)
        if st != 200:
            continue
        try:
            root = ET.fromstring(body.encode("utf-8"))
        except ET.ParseError:
            continue
        for el in root.iter():
            tag = el.tag.split("}")[-1]
            if tag == "loc" and el.text:
                u = el.text.strip()
                (queue if u.endswith(".xml") else urls).append(u)
    return urls


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(s or "")).strip()


def cmd_generate(a):
    base = base_of(a.target)
    host = urllib.parse.urlsplit(base).netloc
    urls = [u for u in sitemap_urls(base, a.max_pages) if urllib.parse.urlsplit(u).netloc == host]
    if not urls:
        print("no sitemap.xml with URLs found at %s/sitemap.xml" % base, file=sys.stderr); return 1
    # shortest paths first: home, top-level pages and hubs come before deep pages
    urls = sorted(set(urls), key=lambda u: (u.rstrip("/").count("/"), u))[: a.max_pages]
    st, _, home = fetch(base + "/")
    hm = Meta(); hm.feed(home if st == 200 else "")
    name = clean(hm.site) or clean(hm.title).split("|")[0].split(" - ")[0].strip() or host
    summary = clean(hm.desc)
    sections = {}
    for u in urls:
        st, _, body = fetch(u)
        time.sleep(a.delay)
        if st != 200:
            continue
        m = Meta(); m.feed(body)
        title = clean(m.title).split("|")[0].strip() or u
        seg = urllib.parse.urlsplit(u).path.strip("/").split("/")[0] or "home"
        sections.setdefault(seg.replace("-", " ").title(), []).append((title, u, clean(m.desc)[:160]))
    out = ["# " + name, ""]
    if summary:
        out += ["> " + summary, ""]
    for sec, items in sections.items():
        out.append("## " + sec)
        for t, u, d in items:
            out.append("- [%s](%s)%s" % (t, u, (": " + d) if d else ""))
        out.append("")
    text = "\n".join(out).rstrip() + "\n"
    if a.out:
        open(a.out, "w", encoding="utf-8").write(text)
        print("wrote %s (%d pages). Review it by hand: titles and notes come from your own meta tags." % (a.out, sum(len(v) for v in sections.values())))
    else:
        sys.stdout.write(text)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate"); v.add_argument("target"); v.add_argument("--check-links", action="store_true")
    g = sub.add_parser("generate"); g.add_argument("target"); g.add_argument("--max-pages", type=int, default=40)
    g.add_argument("--delay", type=float, default=0.5); g.add_argument("--out")
    a = ap.parse_args(argv)
    return cmd_validate(a) if a.cmd == "validate" else cmd_generate(a)


if __name__ == "__main__":
    sys.exit(main())
