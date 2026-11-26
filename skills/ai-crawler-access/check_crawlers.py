#!/usr/bin/env python3
"""Per-crawler robots.txt verdicts for AI search and training bots, plus an
optional live check of what your server answers to each bot's user-agent string.

Usage:
  python3 check_crawlers.py example.com
  python3 check_crawlers.py https://example.com --path /pricing --json
  python3 check_crawlers.py example.com --no-probe        # robots.txt only

Standard library only (Python 3.8+). Run it only on sites you own or may test:
the live check sends one GET per bot user-agent string to your home page.
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

OUR_UA = "ai-search-skills/0.1 (+https://github.com/citedby-eu/ai-search-skills)"

# name = robots.txt product token; role says what blocking it does.
# ua = the string the operator documents for fetches (None: robots-only control token).
CRAWLERS = [
    ("OAI-SearchBot", "search", "ChatGPT search index. Block it and ChatGPT search cannot list or cite you.",
     "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot"),
    ("ChatGPT-User", "user-fetch", "Fetches a page when a ChatGPT user asks about it or a link is opened.",
     "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ChatGPT-User/1.0; +https://openai.com/bot"),
    ("GPTBot", "training", "OpenAI model training. Blocking it does not remove you from ChatGPT search.",
     "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.2; +https://openai.com/gptbot"),
    ("Claude-SearchBot", "search", "Anthropic search index for Claude answers.",
     "Claude-SearchBot/1.0"),
    ("Claude-User", "user-fetch", "Fetches a page when a Claude user asks about it.",
     "Claude-User/1.0"),
    ("ClaudeBot", "training", "Anthropic model training.",
     "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ClaudeBot/1.0; +claudebot@anthropic.com)"),
    ("PerplexityBot", "search", "Perplexity search index. Block it and Perplexity cannot list you.",
     "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)"),
    ("Perplexity-User", "user-fetch", "Fetches a page when a Perplexity user asks about it. Perplexity says this fetcher generally ignores robots.txt, so the verdict is what the file says, not what governs it.",
     "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Perplexity-User/1.0; +https://perplexity.ai/perplexity-user)"),
    ("Google-Extended", "training", "Control token for Gemini training and grounding. Not a separate fetcher; does not affect Google Search ranking.",
     None),
    ("Applebot-Extended", "training", "Control token for Apple model training. Not a separate fetcher.",
     None),
    ("CCBot", "training", "Common Crawl, a dataset many models train on.",
     "CCBot/2.0 (https://commoncrawl.org/faq/)"),
    ("Bytespider", "training", "ByteDance crawler.",
     "Mozilla/5.0 (Linux; Android 5.0) AppleWebKit/537.36 (KHTML, like Gecko) Mobile Safari/537.36 (compatible; Bytespider; spider-feedback@bytedance.com)"),
    ("Amazonbot", "search", "Amazon crawler (Alexa answers).",
     "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Amazonbot/0.1; +https://developer.amazon.com/support/amazonbot)"),
    ("meta-externalagent", "training", "Meta model training and Meta AI.",
     "meta-externalagent/1.1 (+https://developers.facebook.com/docs/sharing/webmasters/crawler)"),
    ("Googlebot", "baseline", "Google Search. Baseline for comparison; AI Overviews use Google's index.",
     "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"),
    ("Bingbot", "baseline", "Bing index. ChatGPT search and Copilot lean on Bing results.",
     "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)"),
]


# ---------- robots.txt parsing and matching (RFC 9309 semantics) ----------

def parse_robots(text):
    """Return a list of groups: {'agents': [lowercase tokens], 'rules': [(allow, path)]}."""
    groups, cur, last_was_agent = [], None, False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        field, value = [p.strip() for p in line.split(":", 1)]
        field = field.lower()
        if field == "user-agent":
            if cur is None or not last_was_agent:
                cur = {"agents": [], "rules": []}
                groups.append(cur)
            cur["agents"].append(value.lower())
            last_was_agent = True
        elif field in ("allow", "disallow"):
            last_was_agent = False
            if cur is not None:
                cur["rules"].append((field == "allow", value))
        # any other line (Crawl-delay, Sitemap, ...) is ignored and does not end the agent run
    return groups


def _pattern_to_regex(path):
    out = ""
    for ch in path:
        if ch == "*":
            out += ".*"
        elif ch == "$":
            out += "$"
        else:
            out += re.escape(ch)
    return re.compile("^" + out)


def rules_for(groups, token):
    """Rules of the most specific group for a product token (merged if repeated)."""
    token = token.lower()
    exact = [g for g in groups if token in g["agents"]]
    chosen = exact or [g for g in groups if "*" in g["agents"]]
    rules = []
    for g in chosen:
        rules.extend(g["rules"])
    return rules, bool(exact)


def is_allowed(rules, path):
    """Longest matching rule wins; Allow wins a tie; empty Disallow matches nothing."""
    best_len, best_allow = -1, True
    for allow, pat in rules:
        if pat == "":
            continue
        if _pattern_to_regex(pat).match(path):
            ln = len(pat)
            if ln > best_len or (ln == best_len and allow and not best_allow):
                best_len, best_allow = ln, allow
    return best_allow


def verdict(groups, token, path):
    rules, named = rules_for(groups, token)
    allowed = is_allowed(rules, path)
    has_blocks = any((not a) and p != "" for a, p in rules)
    if not allowed:
        v = "blocked"
    elif has_blocks:
        v = "partial"   # this path is open but other paths are disallowed
    else:
        v = "allowed"
    return {"verdict": v, "named_in_robots": named, "rules": len(rules)}


# ---------- network ----------

def fetch(url, ua, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(2_000_000)
            return r.status, body.decode("utf-8-sig", "replace"), r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, "", url
    except Exception as e:  # network, TLS, DNS
        return None, str(e), url


def normalise(target):
    if not re.match(r"^https?://", target):
        target = "https://" + target
    p = urllib.parse.urlsplit(target)
    return p.scheme + "://" + p.netloc


def run(target, path="/", probe=False):
    base = normalise(target)
    status, body, final = fetch(base + "/robots.txt", OUR_UA)
    out = {"site": base, "path": path, "robots_status": status, "crawlers": []}
    if status == 200 and "<html" in body[:500].lower():
        out["robots_note"] = "robots.txt answers 200 but looks like an HTML page (soft 404): crawlers treat it as no rules."
        groups = []
    elif status == 200:
        groups = parse_robots(body)
        out["robots_note"] = "%d group(s) read" % len(groups)
    elif status in (404, 410):
        groups = []
        out["robots_note"] = "no robots.txt: every crawler is allowed everywhere."
    elif status is None or status >= 500:
        groups = [{"agents": ["*"], "rules": [(False, "/")]}]
        out["robots_note"] = ("robots.txt unreachable (status %s). RFC 9309: crawlers must assume everything is disallowed, "
                              "so every verdict below is 'blocked'. Fix the server error first." % status)
    else:
        groups = []
        out["robots_note"] = "robots.txt answers %s (client error): RFC 9309 treats it as no rules, every crawler allowed." % status
    base_status = None
    if probe:
        base_status, _, _ = fetch(base + path, OUR_UA)
        out["baseline_status"] = base_status
    for name, role, note, ua in CRAWLERS:
        row = {"crawler": name, "role": role, "note": note}
        row.update(verdict(groups, name, path))
        if probe:
            if ua is None:
                row["live_status"] = None
                row["live_note"] = "token only, no fetch to test"
            else:
                st, _, _ = fetch(base + path, ua)
                row["live_status"] = st
                if base_status and st and st != base_status and st in (401, 403, 406, 429, 503):
                    row["live_note"] = "server answers %s to this user-agent string but %s to a plain client" % (st, base_status)
        out["crawlers"].append(row)
    return out


def headline(res):
    by = {c["crawler"]: c for c in res["crawlers"]}
    lines = []
    s, u = by["OAI-SearchBot"]["verdict"], by["ChatGPT-User"]["verdict"]
    if s == "blocked":
        lines.append("ChatGPT search cannot index this path: OAI-SearchBot is blocked in robots.txt.")
    elif u == "blocked":
        lines.append("ChatGPT can index this path but not open it for a user: ChatGPT-User is blocked.")
    else:
        lines.append("ChatGPT search is not blocked by robots.txt on this path.")
    if by["PerplexityBot"]["verdict"] == "blocked":
        lines.append("Perplexity cannot index this path: PerplexityBot is blocked.")
    if by["Claude-SearchBot"]["verdict"] == "blocked":
        lines.append("Claude search cannot index this path: Claude-SearchBot is blocked.")
    waf = [c["crawler"] for c in res["crawlers"] if c.get("live_note", "").startswith("server answers")]
    if waf:
        lines.append("Server (not robots.txt) refuses these user-agent strings: " + ", ".join(waf)
                     + ". A firewall or CDN bot rule is the likely cause.")
    return lines


def render(res):
    out = ["%s%s  (robots.txt status: %s; %s)" % (res["site"], res["path"], res["robots_status"], res.get("robots_note", ""))]
    out.append("")
    w = max(len(c["crawler"]) for c in res["crawlers"])
    probed = "live_status" in res["crawlers"][0]
    out.append("%-*s  %-10s  %-8s  %s" % (w, "crawler", "role", "robots", "live" if probed else ""))
    for c in res["crawlers"]:
        live = "" if "live_status" not in c else ("-" if c["live_status"] is None and c.get("live_note") else str(c["live_status"]))
        out.append("%-*s  %-10s  %-8s  %s" % (w, c["crawler"], c["role"], c["verdict"], live))
    out.append("")
    out.extend(headline(res))
    out.append("")
    out.append("Not measured: whether a bot obeys the file, or what any assistant cites.")
    if probed:
        out.append("The live column is the answer to a request that only carries the crawler's user-agent string, sent from this machine. "
                   "It is not what the real crawler sees: firewalls that verify bots by IP range can answer the real bot differently.")
    else:
        out.append("Live user-agent probe not run (opt-in: --live-probe --confirm-permission, only for a site you own or may test).")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("site")
    ap.add_argument("--path", default="/", help="path to test (default /)")
    ap.add_argument("--live-probe", action="store_true",
                    help="OPT-IN. Also send one GET per crawler user-agent string to the site. Needs --confirm-permission.")
    ap.add_argument("--confirm-permission", action="store_true",
                    help="state that you own the site or have permission to test it (required with --live-probe)")
    ap.add_argument("--no-probe", action="store_true", help=argparse.SUPPRESS)  # old flag, now the default, kept so old calls still work
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.live_probe and not a.confirm_permission:
        ap.error("--live-probe sends requests with each AI crawler's user-agent string to the site. "
                 "Add --confirm-permission only if you own this site or have permission to test it.")
    res = run(a.site, a.path, probe=a.live_probe and not a.no_probe)
    print(json.dumps(res, indent=2) if a.json else render(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
