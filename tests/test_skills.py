"""Offline tests: no network, no API keys. Run: python3 -m unittest discover -s tests"""
import importlib.util
import json
import os
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "skills")


def load(skill, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, skill, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


cc = load("ai-crawler-access", "check_crawlers")
lt = load("llms-txt", "llms_txt")
sc = load("schema-check", "schema_check")
pr = load("citation-probe", "probe")
gp = load("citation-gap", "gap")
ba = load("brand-answer-audit", "brand_audit")


class Robots(unittest.TestCase):
    def v(self, txt, bot, path="/"):
        return cc.verdict(cc.parse_robots(txt), bot, path)["verdict"]

    def test_star_block_hits_everyone(self):
        self.assertEqual(self.v("User-agent: *\nDisallow: /", "OAI-SearchBot"), "blocked")

    def test_named_group_beats_star(self):
        t = "User-agent: *\nDisallow: /\n\nUser-agent: OAI-SearchBot\nAllow: /\n"
        self.assertEqual(self.v(t, "OAI-SearchBot"), "allowed")
        self.assertEqual(self.v(t, "GPTBot"), "blocked")

    def test_gptbot_block_does_not_block_search_bot(self):
        t = "User-agent: GPTBot\nDisallow: /\n"
        self.assertEqual(self.v(t, "GPTBot"), "blocked")
        self.assertEqual(self.v(t, "OAI-SearchBot"), "allowed")

    def test_longest_match_and_allow_tie(self):
        t = "User-agent: *\nDisallow: /private\nAllow: /private/public\n"
        self.assertEqual(self.v(t, "GPTBot", "/private/x"), "blocked")
        self.assertEqual(self.v(t, "GPTBot", "/private/public/a"), "partial")  # path open, other paths closed
        t2 = "User-agent: *\nDisallow: /a\nAllow: /a\n"
        self.assertTrue(cc.is_allowed(cc.rules_for(cc.parse_robots(t2), "GPTBot")[0], "/a"))

    def test_wildcards_and_end_anchor(self):
        t = "User-agent: *\nDisallow: /*.pdf$\n"
        self.assertEqual(self.v(t, "GPTBot", "/a/b.pdf"), "blocked")
        self.assertEqual(self.v(t, "GPTBot", "/a/b.pdf?x=1"), "partial")

    def test_empty_disallow_allows(self):
        self.assertEqual(self.v("User-agent: *\nDisallow:", "GPTBot"), "allowed")

    def test_stacked_agents_share_rules(self):
        t = "User-agent: GPTBot\nUser-agent: ClaudeBot\nDisallow: /\n"
        self.assertEqual(self.v(t, "ClaudeBot"), "blocked")

    def test_case_and_comments(self):
        t = "user-agent: gptbot # training\nDISALLOW: /\n"
        self.assertEqual(self.v(t, "GPTBot"), "blocked")

    def test_crawl_delay_does_not_split_stacked_agents(self):
        t = "User-agent: GPTBot\nCrawl-delay: 5\nUser-agent: ClaudeBot\nDisallow: /\n"
        self.assertEqual(self.v(t, "GPTBot"), "blocked")

    def test_full_pattern_length_counts_wildcards(self):
        t = "User-agent: *\nDisallow: /x/*y\nAllow: /x/y\n"
        self.assertEqual(self.v(t, "GPTBot", "/x/y"), "blocked")

    def test_no_file_means_allowed(self):
        self.assertEqual(self.v("", "GPTBot"), "allowed")


class CrawlerProbeOptIn(unittest.TestCase):
    """The live user-agent probe is opt-in: default reads robots.txt only."""

    def setUp(self):
        self.calls = []
        self._orig = cc.fetch
        def fake(url, ua, timeout=15):
            self.calls.append((url, ua))
            return (200, "User-agent: *\nDisallow:\n", url) if url.endswith("/robots.txt") else (200, "ok", url)
        cc.fetch = fake

    def tearDown(self):
        cc.fetch = self._orig

    def test_default_fetches_only_robots_txt_with_our_ua(self):
        res = cc.run("example.com")
        self.assertEqual([c[0] for c in self.calls], ["https://example.com/robots.txt"])
        self.assertEqual(self.calls[0][1], cc.OUR_UA)
        self.assertNotIn("live_status", res["crawlers"][0])

    def test_main_default_sends_no_bot_ua(self):
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            cc.main(["example.com"])
        self.assertEqual(len(self.calls), 1)

    def test_live_probe_without_confirmation_exits_and_sends_nothing(self):
        import contextlib, io
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            cc.main(["example.com", "--live-probe"])
        self.assertEqual(cm.exception.code, 2)
        self.assertEqual(self.calls, [])

    def test_live_probe_with_confirmation_probes_each_crawler(self):
        import contextlib, io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cc.main(["example.com", "--live-probe", "--confirm-permission"])
        self.assertGreater(len(self.calls), 5)
        self.assertIn("not what the real crawler sees", buf.getvalue())


class Llms(unittest.TestCase):
    def test_h1_only_is_valid(self):
        e, w, _ = lt.validate_text("# Acme\n")
        self.assertEqual(e, [])

    def test_html_soft_404_is_error(self):
        e, _, _ = lt.validate_text("<!doctype html><html><body>Not found</body></html>")
        self.assertTrue(e)

    def test_missing_h1(self):
        e, _, _ = lt.validate_text("> summary\n## Docs\n- [A](https://a.com/a): x\n")
        self.assertTrue(e)

    def test_warns_relative_and_bare(self):
        _, w, _ = lt.validate_text("# A\n> s\n## D\n- [x](/x): y\n- https://a.com/b\n")
        joined = " ".join(w)
        self.assertIn("relative", joined)
        self.assertIn("bare URLs", joined)

    def test_clean_file(self):
        e, w, _ = lt.validate_text("# A\n> s\n## Docs\n- [x](https://a.com/x): what it covers\n")
        self.assertEqual((e, w), ([], []))


class Schema(unittest.TestCase):
    def test_extract_and_missing(self):
        html = ('<script type="application/ld+json">{"@context":"https://schema.org","@graph":'
                '[{"@type":"Organization","name":"A","url":"https://a.com"},'
                '{"@type":"Product","name":"P","offers":{"@type":"Offer","price":"$19","priceCurrency":""}}]}</script>')
        p = sc.LD(); p.feed(html)
        nodes = []
        sc.flatten(json.loads(p.blocks[0]), nodes)
        types = {t for n in nodes for t in sc.types_of(n)}
        self.assertEqual(types, {"Organization", "Product", "Offer"})

    def test_bad_json_block(self):
        p = sc.LD(); p.feed('<script type="application/ld+json">{bad</script>')
        self.assertEqual(len(p.blocks), 1)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(p.blocks[0])


class Probe(unittest.TestCase):
    def test_anthropic_parse(self):
        d = {"content": [
            {"type": "web_search_tool_result", "content": [{"url": "https://www.a.com/x", "title": "A"}]},
            {"type": "text", "text": "Try Acme.", "citations": [{"url": "https://b.com/y", "title": "B"}]}]}
        text, cites = pr.parse_anthropic(d)
        self.assertEqual(text, "Try Acme.")
        self.assertEqual({c["url"] for c in cites}, {"https://www.a.com/x", "https://b.com/y"})

    def test_gemini_parse_redirect_host_uses_title(self):
        d = {"candidates": [{"content": {"parts": [{"text": "Acme is good"}]},
                             "groundingMetadata": {"groundingChunks": [
                                 {"web": {"uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc", "title": "acme.com"}}]}}]}
        text, cites = pr.parse_gemini(d)
        row = pr.match_row(text, cites, "Acme", "acme.com", [])
        self.assertTrue(row["brand_named"]); self.assertTrue(row["domain_cited"])

    def test_openai_and_perplexity_parse(self):
        o = {"output": [{"type": "message", "content": [{"text": "x", "annotations": [{"type": "url_citation", "url": "https://c.com", "title": "C"}]}]}]}
        self.assertEqual(pr.parse_openai(o)[1][0]["url"], "https://c.com")
        p = {"choices": [{"message": {"content": "y"}}], "citations": ["https://d.com/z"]}
        self.assertEqual(pr.parse_perplexity(p)[1][0]["url"], "https://d.com/z")

    def test_match_is_word_bounded(self):
        row = pr.match_row("Acmeology is a field.", [], "Acme", "acme.com", ["Rival"])
        self.assertFalse(row["brand_named"])
        row = pr.match_row("Subdomain notacme.com is not it", [{"url": "https://notacme.com", "title": ""}], "Acme", "acme.com", [])
        self.assertFalse(row["domain_cited"])

    def test_max_calls_guard(self):
        with tempfile.TemporaryDirectory() as d:
            q = os.path.join(d, "q.txt"); open(q, "w").write("a\nb\n")
            rc = pr.main(["run", "--queries", q, "--brand", "A", "--domain", "a.com", "--providers", "gemini",
                          "--runs", "40", "--out", os.path.join(d, "o.jsonl")])
            self.assertEqual(rc, 2)


def row(q, hosts, ts="2026-11-23T10:00:00Z", status=200, provider="anthropic"):
    return {"query": q, "provider": provider, "ts": ts, "status": status, "brand": "Acme", "domain": "acme.com",
            "citations": [{"url": "https://%s/blog/best-tools" % h, "title": ""} for h in hosts]}


class Gap(unittest.TestCase):
    def test_gap_lists_others_not_you(self):
        rows = [row("q", ["rival.com", "acme.com"]), row("q", ["rival.com"]), row("q", ["other.io"])]
        rep = gp.analyse(rows, "acme.com", 0.5)
        self.assertEqual(rep[0]["you_cited"], 1)
        self.assertEqual([g[0] for g in rep[0]["gap"]], ["rival.com"])

    def test_page_type(self):
        self.assertEqual(gp.page_type("https://a.com/compare/x-vs-y"), "comparison")
        self.assertEqual(gp.page_type("https://a.com/"), "home")


class Brand(unittest.TestCase):
    facts = {"brand": "Acme", "facts": [{"key": "Pro plan price", "kind": "price", "expect": ["€49"], "about": ["pro"]}]}

    def r(self, text):
        return {"query": "q", "provider": "anthropic", "ts": "t", "status": 200, "answer": text}

    def test_price_differs_flagged(self):
        out = ba.audit(self.facts, [self.r("Acme Pro costs $39 per month.")])
        self.assertEqual(len(out), 1); self.assertIn("price differs", out[0]["flag"])

    def test_correct_price_not_flagged(self):
        self.assertEqual(ba.audit(self.facts, [self.r("Acme Pro costs €49 a month.")]), [])

    def test_brand_not_named_and_unknown(self):
        out = ba.audit(self.facts, [self.r("I couldn't find information about that product.")])
        self.assertIn("UNKNOWN", out[0]["detail"])


if __name__ == "__main__":
    unittest.main()
