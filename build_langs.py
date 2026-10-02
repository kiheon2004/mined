#!/usr/bin/env python3
"""Generate the English, Japanese and Chinese pages (en/, ja/, zh/) and sitemap.xml from index.html.
Run after every change to index.html:   python3 build_langs.py
"""
import json, os, re
ROOT = os.path.dirname(os.path.abspath(__file__))
SITE = "https://playmined.com"
LEVELS = [("beginner", 9, 9, 10), ("intermediate", 16, 16, 40), ("expert", 30, 16, 99), ("nothuman", 40, 25, 200),
          ("superman", 50, 32, 320), ("alien", 64, 40, 512), ("god", 80, 50, 760)]
PAGES = {
    "en": dict(title="Minesweeper Online | MINE:D", locale="en_US",
               desc="Play free online Minesweeper in your browser with MINE:D. No install. Safe first click, a no-guessing mode, and 7 levels from Beginner up to an 80×50 God board, plus hints and stats.",
               og="Free Minesweeper you play right in your browser. 7 levels from Beginner to God."),
    "ja": dict(title="マインスイーパー オンライン | MINE:D", locale="ja_JP",
               desc="無料のオンラインマインスイーパー MINE:D。インストール不要でブラウザからすぐ遊べます。初手保証、推測不要モード、初級から80×50の「神」まで7段階、ヒントと統計付き。",
               og="ブラウザですぐ遊べる無料マインスイーパー。初級から「神」まで7段階。"),
    "zh": dict(title="在线扫雷 | MINE:D", locale="zh_CN",
               desc="免费在线扫雷 MINE:D,无需安装,在浏览器中直接玩。首次点击安全、无需猜测模式、从初级到 80×50「神」级共 7 个难度,还有提示和统计。",
               og="在浏览器中直接玩的免费扫雷。从初级到「神」级共 7 个难度。"),
}
src = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
about = json.loads(re.search(r'<script type="application/json" id="about-data">(.*?)</script>', src, re.S).group(1))
esc = lambda t: t.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")
for lang, meta in PAGES.items():
    url = f"{SITE}/{lang}/"
    s = src.replace('<html lang="ko" data-page-lang="ko">', f'<html lang="{lang}" data-page-lang="{lang}">')
    head = re.search(r"<!-- seo:start.*?<!-- seo:end -->", s, re.S).group(0)
    new = head
    new = re.sub(r"<title>.*?</title>", f"<title>{meta['title']}</title>", new)
    new = re.sub(r'<meta name="description" content="[^"]*">', f'<meta name="description" content="{esc(meta["desc"])}">', new)
    new = new.replace(f'<link rel="canonical" href="{SITE}/">', f'<link rel="canonical" href="{url}">')
    new = re.sub(r'<meta property="og:title" content="[^"]*">', f'<meta property="og:title" content="{esc(meta["title"])}">', new)
    new = re.sub(r'<meta property="og:description" content="[^"]*">', f'<meta property="og:description" content="{esc(meta["og"])}">', new)
    new = new.replace(f'<meta property="og:url" content="{SITE}/">', f'<meta property="og:url" content="{url}">')
    new = new.replace('<meta property="og:locale" content="ko_KR">', f'<meta property="og:locale" content="{meta["locale"]}">')
    new = new.replace('"name":"지뢰찾기 온라인 | MINE:D","url":"https://playmined.com/"', f'"name":"{meta["title"]}","url":"{url}"')
    new = new.replace('"url":"https://playmined.com/","inLanguage":"ko"', f'"url":"{url}","inLanguage":"{lang}"')
    s = s.replace(head, new)
    # guide below the board, pre-rendered so search engines read it in this language
    a = about[lang]
    rows = "".join(f"<tr><td>{a['lv'][k]}</td><td>{w}×{h}</td><td>{m:,}</td></tr>" for k, w, h, m in LEVELS)
    article = (f'<article class="about" id="about" lang="{lang}">\n  <h1>{a["h1"]}</h1>\n  <p>{a["intro"]}</p>\n'
               f'  <h2>{a["how"]}</h2>\n  <ul>' + "".join(f"<li>{x}</li>" for x in a["steps"]) + "</ul>\n"
               f'  <h2>{a["levels"]}</h2>\n  <table><tr>' + "".join(f"<th>{c}</th>" for c in a["cols"]) + f"</tr>{rows}</table>\n"
               f'  <h2>{a["keys"]}</h2>\n  <p>{a["keyLine"]}</p>\n  <footer>{a["foot"]}</footer>\n</article>')
    s = re.sub(r'<article class="about" id="about" lang="ko">.*?</article>', lambda _: article, s, flags=re.S)
    os.makedirs(os.path.join(ROOT, lang), exist_ok=True)
    open(os.path.join(ROOT, lang, "index.html"), "w", encoding="utf-8").write(s)
# sitemap with language alternates
alts = "".join(f'\n    <xhtml:link rel="alternate" hreflang="{l}" href="{SITE}{p}"/>' for l, p in [("ko", "/"), ("en", "/en/"), ("ja", "/ja/"), ("zh", "/zh/"), ("x-default", "/")])
urls = "".join(f"\n  <url><loc>{SITE}{p}</loc>{alts}\n  </url>" for p in ["/", "/en/", "/ja/", "/zh/"])
open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8").write(
    '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">'
    + urls + "\n</urlset>\n")
print("built: en/ ja/ zh/ and sitemap.xml")
