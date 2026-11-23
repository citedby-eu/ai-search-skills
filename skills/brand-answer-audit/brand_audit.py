#!/usr/bin/env python3
"""Check what AI answers say ABOUT your brand against facts you wrote down.

  1. Write facts.json (see facts.example.json): what is true, per fact.
  2. Ask brand questions with citation-probe, e.g. "What does Acme cost?", "What is Acme?"
  3. python3 brand_audit.py facts.json probes/brand-*.jsonl [--csv rows.csv]

Standard library only (Python 3.8+). Every row it flags is a place to LOOK, not a
verdict. A regex cannot tell a wrong price from a rival's price in the same sentence,
so read each flagged sentence yourself and keep your verdict. Report the number you
confirmed by hand, never the number the script flagged.
"""
import argparse
import csv
import glob
import json
import re
import sys

MONEY = re.compile(r"(?:[$€£]\s?\d[\d.,]*|\d[\d.,]*\s?(?:€|EUR|USD|GBP|dollars?|euros?)\b)", re.I)
UNKNOWN = re.compile(r"(i (don't|do not|couldn't|could not) (have|find)|no (information|results)|not (familiar|aware)|unable to find|doesn't appear to exist|cannot find)", re.I)


def norm_money(s):
    return re.sub(r"\s+", "", s).lower()


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def audit(facts, rows):
    brand = facts["brand"]
    out = []
    for r in rows:
        if r.get("status") != 200:
            continue
        text = r.get("answer", "")
        if not re.search(r"(?<!\w)" + re.escape(brand) + r"(?!\w)", text, re.I):
            out.append({"query": r["query"], "provider": r["provider"], "ts": r["ts"], "flag": "brand not named",
                        "detail": "UNKNOWN: says it has no information" if UNKNOWN.search(text) else "answer does not mention the brand", "sentence": ""})
            continue
        sents = sentences(text)
        for fact in facts.get("facts", []):
            expect = [norm_money(e) if MONEY.search(e) else e.lower() for e in fact.get("expect", [])]
            about = [a.lower() for a in fact.get("about", [fact["key"]])]
            rel = [s for s in sents if re.search(r"(?<!\w)" + re.escape(brand) + r"(?!\w)", s, re.I)
                   and any(a in s.lower() for a in about)]
            if fact.get("kind") == "price":
                rel = [s for s in sents if re.search(r"(?<!\w)" + re.escape(brand) + r"(?!\w)", s, re.I) and MONEY.search(s)] or rel
            for s in rel:
                low, flat = s.lower(), norm_money(s)
                has_expected = any(e in low or e in flat for e in expect)
                if fact.get("kind") == "price":
                    amounts = {norm_money(m) for m in MONEY.findall(s)}
                    if amounts and not any(e in amounts or any(e in a for a in amounts) for e in expect):
                        out.append({"query": r["query"], "provider": r["provider"], "ts": r["ts"],
                                    "flag": "price differs: %s" % fact["key"],
                                    "detail": "expected %s, sentence has %s" % ("/".join(fact["expect"]), ", ".join(sorted(amounts))),
                                    "sentence": s})
                elif expect and not has_expected:
                    out.append({"query": r["query"], "provider": r["provider"], "ts": r["ts"],
                                "flag": "fact missing: %s" % fact["key"], "detail": "expected one of %s" % fact["expect"], "sentence": s})
                for bad in fact.get("forbid", []):
                    if bad.lower() in low:
                        out.append({"query": r["query"], "provider": r["provider"], "ts": r["ts"],
                                    "flag": "forbidden wording: %s" % fact["key"], "detail": bad, "sentence": s})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("facts"); ap.add_argument("files", nargs="+"); ap.add_argument("--csv")
    a = ap.parse_args(argv)
    facts = json.load(open(a.facts, encoding="utf-8"))
    rows = []
    for pat in a.files:
        for p in glob.glob(pat):
            rows += [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    ok = [r for r in rows if r.get("status") == 200]
    res = audit(facts, rows)
    print("%d answers read, %d rows to check by hand" % (len(ok), len(res)))
    for x in res:
        print("\n[%s] %s | %s\n  %s\n  %s" % (x["provider"], x["flag"], x["query"], x["detail"], x["sentence"][:240]))
    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["ts", "provider", "query", "flag", "detail", "sentence", "your_verdict"])
            w.writeheader()
            for x in res:
                w.writerow(dict(x, your_verdict=""))
        print("\nwrote %s: fill in your_verdict (true error / misread) for each row" % a.csv)
    print("\nFlags are places to look. Count only what you confirmed on the answer itself.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
