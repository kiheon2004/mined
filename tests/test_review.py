"""Fixes from the 2026-11 review: daily-board storage and share sheet, a board built while the tab is away,
keyboard focus across N and R, the editor's corner cases, names for controls, the phone layout, and set-domain.sh."""
import json
import re
import shutil
import subprocess

import pytest

from harness import ROOT, Game

PHONE = {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 2, "has_touch": True}


def phone_ctx(browser, browser_name):
    opts = dict(PHONE)
    if browser_name != "firefox":
        opts["is_mobile"] = True
    return browser.new_context(**opts)


# ---------------- daily board ----------------

def test_clean_daily_keeps_good_entries_and_repairs_bad_ones(game):
    r = game.run(r"""
      const clean = E("cleanDaily"), good = { "2026-10-11": { wins: 2, best: 41.3 }, "2026-10-12": { wins: 1, best: null } };
      assert(JSON.stringify(clean(good)) === JSON.stringify(good), "good data changed");
      for (const bad of [null, 5, "x", [1, 2]]) assert(JSON.stringify(clean(bad)) === "{}", "non-object " + JSON.stringify(bad));
      return clean({ "2026-10-11": { wins: 1, best: "abc" }, "2026-10-12": 5, "2026-10-13": null, "2026-10-14": { wins: -2, best: -1 },
                     "2026-10-15": { wins: 1.5, best: Infinity }, "not-a-date": { wins: 1, best: 3 }, "2026-10-16": { wins: 3, best: 0, extra: 1 } });
    """)
    assert r == {"2026-10-11": {"wins": 1, "best": None}, "2026-10-14": {"wins": 0, "best": None},
                 "2026-10-15": {"wins": 0, "best": None}, "2026-10-16": {"wins": 3, "best": 0}}, r


@pytest.mark.parametrize("stored", [
    {"wins": 1, "best": "abc"},      # used to leave "building…" on screen over a finished board, and never took a new best
    5,                                 # used to swallow every win of the day
    None,
])
def test_daily_board_survives_damaged_storage(game, stored):
    p = game.page
    errors = []
    p.on("pageerror", lambda e: errors.append(str(e)))
    day = game.ev("today()")
    p.evaluate("d => localStorage.setItem('minesweeper-daily', JSON.stringify(d))", {day: stored})
    game.goto("/?daily", clear=False)
    p.wait_for_function("() => window.__ev('cfg').key === 'daily' && !window.__ev('gen') && window.__ev('openedCount') > 1")
    r = game.run(r"""
      const ready = E("statusKey");
      const m = E("mines"), o = E("open"); const safe = [...Array(480).keys()].find(i => !m[i] && !o[i]);
      E("cells")[safe].click(); await sleep(150); winNow();
      return { ready, won: E("statusKey"), log: E("dailyLog")[arg], saved: JSON.parse(localStorage.getItem("minesweeper-daily"))[arg] };
    """, day)
    assert not errors, errors
    assert r["ready"] == "dailyReady" and r["won"] in ("win", "winRecord"), r
    wins = 2 if isinstance(stored, dict) else 1
    assert r["log"]["wins"] == wins and isinstance(r["log"]["best"], (int, float)) and r["saved"] == r["log"], r


def test_closing_the_share_sheet_is_not_an_error(browser, server, browser_name):
    """On a touch device the result goes to the system share sheet; closing it must not open a prompt.
    A real failure (no share sheet, no clipboard) still falls back to the prompt so the text can be copied by hand."""
    ctx = phone_ctx(browser, browser_name)
    try:
        g = Game(ctx.new_page(), server.url).goto("/")
        r = g.run(r"""
          let prompts = 0, shared = 0; window.prompt = () => { prompts++; return null; };
          const share = f => Object.defineProperty(navigator, "share", { configurable: true, value: f });
          E("startDaily('2026-10-11')"); await until(() => !E("gen"), 30000);
          const m = E("mines"), o = E("open"); const safe = [...Array(480).keys()].find(i => !m[i] && !o[i]);
          E("cells")[safe].click(); winNow();
          const coarse = matchMedia("(any-pointer: coarse)").matches;
          share(() => { shared++; return Promise.reject(new DOMException("closed", "AbortError")); });
          $("statusAct").click(); await sleep(200);
          const afterClose = prompts;
          share(() => { shared++; return Promise.reject(new DOMException("blocked", "NotAllowedError")); });
          $("statusAct").click(); await sleep(200);
          return { coarse, shared, afterClose, afterFailure: prompts };
        """)
        assert r == {"coarse": True, "shared": 2, "afterClose": 0, "afterFailure": 1}, r
    finally:
        ctx.close()


# ---------------- a board built while the tab is away ----------------

def test_noguess_board_finished_in_a_hidden_tab_waits_paused(game):
    r = game.run(r"""
      gmode("noguess"); level("expert"); E("stats = {}; newGame(321)");
      Object.defineProperty(document, "hidden", { configurable: true, get: () => true });
      E("cells")[8 * 30 + 15].click();
      const built = await until(() => E("started"), 30000);
      await sleep(400);
      const o = { built, paused: E("paused"), covered: $("board").classList.contains("paused"), seconds: E("playSeconds()"), status: E("statusKey") };
      delete document.hidden;
      E("cells")[0].click();   // back in the tab: a click on the cover resumes
      await sleep(250);
      o.resumed = !E("paused") && E("playSeconds()") > 0.15; o.time = E("stats")["expert@noguess"].time || 0;
      return o;
    """)
    assert r["built"] and r["paused"] and r["covered"] and r["status"] == "pausedMsg" and r["seconds"] < 0.1, r
    assert r["resumed"] and r["time"] < 0.1, r


# ---------------- a slow font server ----------------

def test_game_plays_and_timers_run_while_the_font_server_hangs(page, server):
    """The web fonts come from another server. While it does not answer, the page counts as still loading:
    the game must start anyway (the font stylesheet used to block the game script), and timers must keep firing
    during sliced work (Firefox holds timeouts back behind other tasks while a page loads, which froze the clock
    and held back the "still checking" message until the check was over)."""
    asked = []
    page.route(re.compile(r"^https://fonts\.(googleapis|gstatic)\.com/"), lambda route: asked.append(route.request.url))   # never answered
    page.set_default_timeout(20_000)
    g = Game(page, server.url).goto("/")
    assert asked and g.page.evaluate("document.readyState") == "interactive"
    r = g.run(r"""
      gmode("safe"); level("expert"); E("newGame(7)"); E("cells")[245].click();
      const o = { started: E("started"), opened: E("openedCount") };
      E(`hintRules = () => null; exactSteps = function* () { for (let i = 0; i < 100; i++) { const t = performance.now(); while (performance.now() - t < 6); yield; } return { complete: true, safe: [], mines: [] }; }`);
      const gaps = []; let last = performance.now();
      const iv = setInterval(() => { const now = performance.now(); gaps.push(now - last); last = now; }, 10);
      const clock0 = $("time").textContent;
      $("hint").click();
      await sleep(300);
      o.during = E("statusKey"); o.running = !!E("hintStop"); o.clockMoved = $("time").textContent !== clock0;
      await until(() => !E("hintStop"), 10000);
      clearInterval(iv);
      o.after = E("statusKey"); o.maxGapMs = Math.round(Math.max(...gaps)); o.ticks = gaps.length; o.state = document.readyState;
      return o;
    """)
    assert r["started"] and r["opened"] > 0 and r["state"] == "interactive", r
    assert r["during"] == "hintChecking" and r["running"] and r["clockMoved"] and r["after"] == "noLogic", r
    assert r["maxGapMs"] < 200 and r["ticks"] >= 10, r      # was one gap as long as the whole check (600 ms and more)


# ---------------- keyboard focus ----------------

def test_keyboard_player_keeps_their_cell_across_new_game_and_restart(game):
    p = game.page
    active = lambda: p.evaluate("document.activeElement.dataset.i === undefined ? document.activeElement.tagName : +document.activeElement.dataset.i")
    game.run('gmode("safe"); level("beginner"); E("newGame(5)"); E("focusCell(0, true)");')
    for _ in range(4):
        p.keyboard.press("ArrowDown"); p.keyboard.press("ArrowRight")
    p.keyboard.press("Enter")
    assert active() == 40 and game.ev("started")
    p.keyboard.press("n")
    assert active() == 40 and not game.ev("started") and game.ev("cells[40].tabIndex") == 0
    assert game.ev("cells.filter(c => c.tabIndex === 0).length") == 1
    p.keyboard.press("ArrowRight"); p.keyboard.press("Enter")          # the arrows still work without a Tab back in
    assert active() == 41 and game.ev("started") and game.ev("firstClick") == 41
    p.keyboard.press("r")
    assert active() == 41 and game.ev("statusKey") == "restartedFirst"
    assert p.evaluate("document.activeElement.matches(':focus-visible')")
    # tabbing into the board counts as keyboard play too (the board's one tab stop follows the last menu control)
    p.locator('#board .cell[data-i="7"]').click()
    p.focus('#langs [data-lang="zh"]'); p.keyboard.press("Tab")
    assert active() == 7
    p.keyboard.press("n")
    assert active() == 7


def test_mouse_player_never_gets_a_focus_ring(game):
    """Click a cell, then use keys the way mouse players do (space flags the hovered cell, H, N): no cell shows a ring
    and N does not pull focus back. Chromium and WebKit used to ring the cell clicked last at the first key press.
    Moving with the arrow keys afterwards is keyboard play again and shows the ring."""
    p = game.page
    rings = lambda: p.evaluate("[...document.querySelectorAll('#board .cell')].filter(c => getComputedStyle(c).outlineStyle !== 'none').map(c => +c.dataset.i)")
    focused = lambda: p.evaluate("document.activeElement.dataset.i === undefined ? document.activeElement.tagName : +document.activeElement.dataset.i")
    game.run('$("introOk").click(); gmode("safe"); level("beginner"); E("newGame(5)");')
    p.locator('#board .cell[data-i="40"]').click()
    assert game.ev("started") and rings() == []
    closed = game.ev("cells.findIndex((c, k) => !open[k])")
    p.locator(f'#board .cell[data-i="{closed}"]').hover()
    p.keyboard.press("Space")
    assert game.ev(f"flags[{closed}]") == 1 and rings() == []
    p.keyboard.press("h")
    assert game.ev("hintUsed") and rings() == [] and focused() in (40, "BODY")      # focus does not chase the hint
    p.keyboard.press("s"); p.keyboard.press("Escape")                                # focus comes back from the stats window without a ring
    assert p.evaluate("document.getElementById('statsDlg').hidden") and rings() == []
    p.keyboard.press("n")
    assert not game.ev("started") and rings() == [] and focused() == "BODY"
    # a keyboard-focused cell that is then clicked loses its ring too
    game.run('E("focusCell(0, true)");')
    p.keyboard.press("ArrowRight")
    assert rings() == [1]
    p.locator('#board .cell[data-i="1"]').click()
    assert rings() == []
    p.keyboard.press("ArrowRight")                                                    # ...and gets it back by moving with the keys
    assert focused() == 2 and rings() == [2]


# ---------------- editor ----------------

def test_editor_leaves_the_daily_board(game):
    r = game.run(r"""
      E("startDaily('2026-10-11')"); await until(() => !E("gen"), 30000);
      $("editorBtn").click();
      const pressed = () => [...document.querySelectorAll('#levels [aria-pressed="true"]')].map(b => b.dataset.level);
      const o = { editing: E("editing"), key: E("cfg").key, size: [E("cfg").w, E("cfg").h], daily: $("dailyBtn").getAttribute("aria-pressed"), level: pressed() };
      $("codeIn").value = E("encodeBoard")(10, 10, new Uint8Array(100).map((_, i) => i < 5 ? 1 : 0)); $("loadForm").requestSubmit();
      o.afterLoad = pressed();
      return o;
    """)
    assert r == {"editing": True, "key": "expert", "size": [30, 16], "daily": "false", "level": ["expert"], "afterLoad": ["custom"]}, r


def test_zoom_keys_work_in_the_editor_and_other_shortcuts_stay_off(game):
    p = game.page
    game.run('level("beginner"); $("editorBtn").click();')
    z = game.ev("cellPx")
    p.keyboard.press("Minus")
    smaller = game.ev("cellPx")
    p.keyboard.press("Equal")
    assert smaller < z and game.ev("cellPx") == z
    for key in ["n", "r", "h", "p", "s"]:
        p.keyboard.press(key)
    assert game.ev("editing") and p.evaluate("document.getElementById('statsDlg').hidden")


# ---------------- names, markup, colors ----------------

@pytest.mark.parametrize("path,menu,zoom_in", [("/", "메뉴", "확대"), ("/en/", "Menu", "Zoom in"), ("/ja/", "メニュー", "拡大"), ("/zh/", "菜单", "放大")])
def test_every_control_has_a_name_in_the_page_language(game, path, menu, zoom_in):
    game.goto(path)
    r = game.run(r"""
      $("editorBtn").click(); $("byNumber").click(); level("custom");
      const name = el => (el.getAttribute("aria-label") || "").trim()
        || (el.getAttribute("aria-labelledby") || "").split(" ").map(i => $(i)?.textContent || "").join(" ").trim()
        || (el.labels ? [...el.labels].map(l => l.textContent).join(" ").trim() : "") || (el.tagName === "BUTTON" ? el.textContent.trim() : "");
      const unnamed = [...document.querySelectorAll("button, input, textarea, [role=group], [role=grid], [role=dialog], nav")]
        .filter(el => !el.classList.contains("cell") && el.getAttribute("aria-hidden") !== "true" && !el.closest("[hidden]") && !name(el)).map(el => el.tagName + "#" + el.id);
      return { unnamed, menu: $("menu").getAttribute("aria-label"), zoomIn: name($("zoomIn")), zoomOut: name($("zoomOut")), code: name($("codeIn")),
               hold: name($("holdSet")), langs: [...document.querySelectorAll("#langs button")].map(b => b.lang + ":" + b.dataset.lang) };
    """)
    assert r["unnamed"] == [], r
    assert r["menu"] == menu and r["zoomIn"] == zoom_in and r["zoomOut"] and r["zoomOut"] != r["zoomIn"], r
    assert r["code"] == game.ev("L().editLoadPh") and r["hold"] == game.ev("L().hold"), r
    assert r["langs"] == ["ko:ko", "en:en", "ja:ja", "zh:zh"], r


def test_info_panel_is_a_valid_list_with_the_same_layout(game):
    r = game.run(r"""
      const kids = [...document.querySelector("dl.hud").children], box = el => el.getBoundingClientRect();
      const rows = [0, 1, 2].map(k => kids.slice(k * 4, k * 4 + 4));
      return { tags: kids.map(k => k.tagName).join(""),
               sameRow: rows.every(r => r.every(el => Math.abs(box(el).top - box(r[0]).top) < 4)),
               leftToRight: rows.every(r => box(r[0]).right <= box(r[1]).left + 1 && box(r[1]).right < box(r[2]).left && box(r[2]).right <= box(r[3]).left + 1),
               columns: [0, 1, 2, 3].every(c => Math.abs(box(rows[0][c]).right - box(rows[2][c]).right) < 1 || Math.abs(box(rows[0][c]).left - box(rows[2][c]).left) < 1),
               split: box(rows[0][2]).left - box(rows[0][1]).right > 40,
               width: Math.round(box(document.querySelector("dl.hud")).width) };
    """)
    assert r == {"tags": "DTDD" * 6, "sameRow": True, "leftToRight": True, "columns": True, "split": True, "width": 520}, r


def test_picked_color_mode_reaches_the_browser_bar(game):
    r = game.run(r"""
      const bars = () => [...document.querySelectorAll('meta[name="theme-color"]')].map(m => m.content);
      const o = { start: bars() };
      $("modeDark").click(); o.dark = bars(); o.ground = getComputedStyle(document.body).backgroundColor;
      $("modeLight").click(); o.light = bars();
      return o;
    """)
    assert r["start"] == ["#e3e0d9", "#0f1215"] and r["dark"] == ["#0f1215"] * 2 and r["light"] == ["#e3e0d9"] * 2, r
    assert r["ground"] == "rgb(15, 18, 21)", r
    game.run('$("modeDark").click();')
    game.goto("/", clear=False)    # a saved pick is applied again on the next visit
    assert game.page.evaluate("[...document.querySelectorAll('meta[name=\"theme-color\"]')].map(m => m.content)") == ["#0f1215"] * 2


# ---------------- phones ----------------

def _contrast(fg, bg):
    def lum(c):
        ch = [(v / 255 / 12.92) if v / 255 <= 0.03928 else ((v / 255 + 0.055) / 1.055) ** 2.4 for v in c]
        return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]
    a, b = sorted([lum(fg), lum(bg)], reverse=True)
    return (a + 0.05) / (b + 0.05)


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_phone_menu_text_keeps_its_contrast(browser, server, browser_name, scheme):
    """The menu's resting colors are chosen for 4.5:1 against the page; nothing on a phone may fade them further."""
    opts = dict(PHONE, color_scheme=scheme)
    if browser_name != "firefox":
        opts["is_mobile"] = True
    ctx = browser.new_context(**opts)
    try:
        g = Game(ctx.new_page(), server.url).goto("/")
        r = g.run(r"""
          const rgb = s => s.match(/[\d.]+/g).slice(0, 3).map(Number);
          $("menuToggle").click();     // unfold the phone menu
          let fade = 1; for (let el = document.querySelector(".mi"); el; el = el.parentElement) fade *= +getComputedStyle(el).opacity;
          return { strip: getComputedStyle($("menu")).position, fade, bg: rgb(getComputedStyle(document.body).backgroundColor),
                   item: rgb(getComputedStyle(document.querySelector('.mi[aria-pressed="false"]')).color),
                   head: rgb(getComputedStyle(document.querySelector(".group > span")).color) };
        """)
        assert r["strip"] == "static" and r["fade"] == 1, r
        assert _contrast(r["item"], r["bg"]) >= 4.5 and _contrast(r["head"], r["bg"]) >= 4.5, (r, _contrast(r["item"], r["bg"]))
    finally:
        ctx.close()


@pytest.mark.parametrize("path", ["/", "/en/", "/ja/", "/zh/"])
def test_first_visit_note_matches_the_input_device(browser, server, browser_name, game, path):
    """A touch screen has no space bar or right-click, so its first-visit note explains taps and holds instead."""
    game.goto(path)
    desk = game.run('return { shown: !$("intro").hidden, text: $("introText").textContent, want: E("L().introText"), touch: E("L().introTextTouch") };')
    assert desk["shown"] and desk["text"] == desk["want"] and desk["touch"] and desk["touch"] != desk["want"], desk
    ctx = phone_ctx(browser, browser_name)
    try:
        g = Game(ctx.new_page(), server.url).goto(path)
        r = g.run('return { coarse: matchMedia("(pointer: coarse)").matches, shown: !$("intro").hidden, text: $("introText").textContent, controls: $("t-controls").textContent, wantControls: E("L().controlsTouch") };')
        if not r["coarse"]:
            pytest.skip("this engine does not emulate a coarse pointer")
        assert r["shown"] and r["text"] == desk["touch"] and r["controls"] == r["wantControls"], r
    finally:
        ctx.close()


def test_every_language_has_every_text(game):
    """The four language tables must hold the same keys (nested ones included), each with a value of the same kind."""
    r = game.run(r"""
      const TX = E("T"), shape = (v, p = "") => typeof v === "object" && v !== null && !Array.isArray(v)
        ? Object.entries(v).flatMap(([k, x]) => shape(x, p + k + ".")) : [p + (Array.isArray(v) ? "array" + v.length : typeof v)];
      const ko = shape(TX.ko).sort(), out = {};
      for (const l of ["en", "ja", "zh"]) { const s = new Set(shape(TX[l])); out[l] = [...ko.filter(k => !s.has(k)), ...[...s].filter(k => !ko.includes(k)).map(k => "+" + k)]; }
      const empty = Object.entries(TX).flatMap(([l, t]) => Object.entries(t).filter(([, v]) => v === "").map(([k]) => l + "." + k));
      return { n: ko.length, out, empty };
    """)
    assert r["n"] > 150 and r["out"] == {"en": [], "ja": [], "zh": []} and r["empty"] == [], r


# ---------------- repository tools ----------------

def _site_copy(tmp_path):
    for name in ["index.html", "CNAME", "build_langs.py", "set-domain.sh", "sitemap.xml", "robots.txt"]:
        shutil.copy2(ROOT / name, tmp_path / name)
    for lang in ["en", "ja", "zh"]:
        (tmp_path / lang).mkdir()
        shutil.copy2(ROOT / lang / "index.html", tmp_path / lang / "index.html")
    return tmp_path


def _site_files(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_generated_pages_are_up_to_date(tmp_path):
    """en/ ja/ zh/, sitemap.xml and robots.txt must be what build_langs.py makes from the current index.html."""
    site = _site_copy(tmp_path)
    before = _site_files(site)
    subprocess.run(["python3", "build_langs.py"], cwd=site, check=True, capture_output=True)
    after = _site_files(site)
    stale = [k for k in before if before[k] != after[k]]
    assert not stale and before.keys() == after.keys(), f"run python3 build_langs.py: {stale}"


def test_set_domain_moves_every_link_and_back(tmp_path):
    site = _site_copy(tmp_path)
    before = _site_files(site)
    old = (site / "CNAME").read_text().strip()
    run = lambda *a: subprocess.run(["sh", "set-domain.sh", *a], cwd=site, capture_output=True, text=True)
    assert run().returncode != 0 and run("not a domain").returncode != 0 and _site_files(site) == before   # bad input changes nothing
    done = run("https://Mines.Example.org/")
    assert done.returncode == 0, done.stderr
    moved = _site_files(site)
    assert moved.keys() == before.keys(), sorted(set(moved) ^ set(before))    # no backup files left behind
    assert moved["CNAME"] == b"mines.example.org\n"
    for name, body in moved.items():
        text = body.decode("utf-8")
        assert old not in text, name
        if name.endswith("index.html"):
            assert 'const SITE_HOST = "mines.example.org";' in text
            assert re.search(r'<link rel="canonical" href="https://mines\.example\.org/', text), name
            json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', text, re.S).group(1))
    assert b"Sitemap: https://mines.example.org/sitemap.xml" in moved["robots.txt"]
    assert run(old).returncode == 0 and _site_files(site) == before          # and back again, byte for byte
