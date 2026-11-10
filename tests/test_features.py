"""Features added from player feedback: pause, efficiency (3BV) line, daily board, touch hold-to-flag,
classic chording inputs, F2, and offline support."""
import json
import time

import pytest

chromium_only = pytest.mark.only_browser("chromium")


# ---------------- pause ----------------

def test_pause_freezes_clock_covers_board_and_resumes(game):
    p = game.page
    game.run('gmode("safe"); level("beginner"); E("newGame(5)"); E("cells")[40].click(); await sleep(300);')
    p.keyboard.press("p")
    r = game.run(r"""
      const t1 = E("playSeconds()"); await sleep(500); const t2 = E("playSeconds()");
      const closed = E("cells").findIndex((c, i) => !E("open")[i]);
      const o = { frozen: Math.abs(t2 - t1) < 0.01, covered: $("board").classList.contains("paused"), pressed: $("pauseBtn").getAttribute("aria-pressed"),
                  status: status(), cover: getComputedStyle($("board"), "::after").content };
      E(`openCell(${closed})`); E(`toggleFlag(${closed})`); E("hint()");
      o.blocked = !E("open")[closed] && !E("flags")[closed] && !E("hintUsed");
      E("cells")[closed].click();   // a click on the covered board resumes, it does not open
      o.resumed = !E("paused") && !$("board").classList.contains("paused"); o.notOpened = !E("open")[closed];
      await sleep(300); o.running = E("playSeconds()") > t2 + 0.2;
      return o;
    """)
    assert r["frozen"] and r["covered"] and r["pressed"] == "true" and r["status"] == game.ev("L().pausedMsg"), r
    assert r["blocked"] and r["resumed"] and r["notOpened"] and r["running"], r
    # the cover text comes from data-pause (Firefox reports the computed content as "attr(data-pause)" itself)
    assert game.ev("board.dataset.pause") == game.ev("L().pauseCover") and r["cover"].strip('"') in (game.ev("L().pauseCover"), "attr(data-pause)")


def test_pause_time_is_not_counted_in_stats(game):
    r = game.run(r"""
      gmode("safe"); level("beginner"); E("stats = {}; newGame(5)"); E("cells")[40].click();
      await sleep(300); E("pause()"); await sleep(800); E("resume()"); await sleep(300); winNow();
      return { time: E("stats").beginner.time, best: E("stats").beginner.best, shown: $("time").textContent };
    """)
    assert 0.5 < r["time"] < 0.85 and 0.5 < r["best"] < 0.85, r   # ~0.6 s played, the 0.8 s pause left out


def test_leaving_the_tab_pauses(game):
    r = game.run(r"""
      gmode("safe"); level("beginner"); E("newGame(5)"); E("cells")[40].click();
      Object.defineProperty(document, "hidden", { configurable: true, get: () => true });
      document.dispatchEvent(new Event("visibilitychange"));
      const paused = E("paused");
      delete document.hidden;
      return { paused, before: (E("newGame(6)"), E("paused")) };
    """)
    assert r == {"paused": True, "before": False}, r


def test_pause_and_new_game_with_real_keys(game):
    p = game.page
    game.run('gmode("safe"); level("beginner"); E("newGame(5)"); E("cells")[40].click();')
    no = game.ev("gameNo")
    p.keyboard.press("p"); assert game.ev("paused")
    p.keyboard.press("p"); assert not game.ev("paused")
    p.keyboard.press("F2")
    assert game.ev("gameNo") != no and not game.ev("started")


# ---------------- efficiency ----------------

def test_3bv_matches_an_independent_count(game):
    """bbbv() against a straightforward reference on many random boards."""
    r = game.run(r"""
      const rng = E("rng"); let checked = 0, bad = [];
      for (let s = 1; s <= 300; s++) {
        const r = rng(s), w = 5 + Math.floor(r() * 12), h = 5 + Math.floor(r() * 8), n = w * h, m = 1 + Math.floor(r() * n * 0.3);
        E(`cfg = { key: "custom", w: ${w}, h: ${h}, m: ${m} }; newGame(${s}); placeMines(0);`);
        const mines = E("mines"), N = E("nbs()");
        const cnt = i => N[i].reduce((a, j) => a + mines[j], 0);
        // reference: label zero regions with union-find, then count regions + safe numbers touching no zero
        const parent = [...Array(n).keys()], find = x => parent[x] === x ? x : (parent[x] = find(parent[x]));
        for (let i = 0; i < n; i++) if (!mines[i] && !cnt(i)) for (const j of N[i]) if (!mines[j] && !cnt(j)) parent[find(i)] = find(j);
        const roots = new Set(); let lone = 0;
        for (let i = 0; i < n; i++) if (!mines[i]) {
          if (!cnt(i)) roots.add(find(i)); else if (!N[i].some(j => !mines[j] && !cnt(j))) lone++;
        }
        const ref = roots.size + lone, got = E("bbbv()");
        checked++; if (ref !== got) bad.push({ s, ref, got });
      }
      return { checked, bad };
    """)
    assert r["checked"] == 300 and not r["bad"], r


def test_win_shows_efficiency_and_records_best_3bv_per_second(game):
    r = game.run(r"""
      gmode("safe"); level("beginner"); E("stats = {}; newGame(31)");
      E("cells")[40].click(); await sleep(400);
      // win by clicking every safe cell (each counts as a click)
      const m = E("mines"); let k = 0;
      for (let i = 0; i < 81; i++) if (!m[i] && !E("open")[i] && !E("over")) { E("cells")[i].click(); k++; }
      const line = $("winStats").textContent, s = E("stats").beginner, info = E("winInfo");
      return { won: E("over") && !E("cells").some((c, i) => c.classList.contains("boom")), line, hidden: $("winStats").hidden, bps: s.bps, info, clicksExpected: 1 + k };
    """)
    assert r["won"] and not r["hidden"], r
    assert r["info"]["clicks"] == r["clicksExpected"], r
    assert r["line"].startswith(f"3BV {r['info']['b']} · 3BV/s ") and f"클릭 {r['clicksExpected']}" in r["line"], r
    assert abs(r["bps"] - round(r["info"]["bps"], 2)) < 1e-9, r
    # a hinted win does not set the best 3BV/s; a new game hides the line
    r2 = game.run(r"""
      E("newGame(32)"); const hidden = $("winStats").hidden;
      E("cells")[40].click(); E("hintUsed = true"); winNow();
      return { hidden, bps: E("stats").beginner.bps };
    """)
    assert r2["hidden"] and r2["bps"] == r["bps"], r2


def test_stats_dialog_has_best_3bv_column(game):
    r = game.run(r"""
      E(`stats = { beginner: { played: 3, won: 2, best: 5.5, bps: 1.234 } }`);
      $("statsBtn").click();
      const head = [...$("statsTable").querySelectorAll("th")].map(x => x.textContent);
      const row = [...$("statsTable").querySelector("tbody tr").children].map(x => x.textContent);
      $("statsClose").click();
      return { head, row };
    """)
    assert "최고 3BV/s" in r["head"] and "1.23" in r["row"], r


# ---------------- daily board ----------------

def test_daily_board_is_the_same_everywhere_and_starts_open(game):
    r = game.run(r"""
      E("startDaily('2026-10-11')"); await until(() => !E("gen"), 30000);
      const lay = Array.from(E("savedMines")).join("");
      const o = { key: E("cfg").key, size: [E("cfg").w, E("cfg").h, E("cfg").m], gameNo: $("gameNo").textContent, lvl: $("lvlLabel").textContent,
                  mode: $("modeLabel").textContent, started: E("started"), centerOpen: !!E("open")[8 * 30 + 15], opened: E("openedCount"), clicks: E("clicks"),
                  status: status(), pressed: $("dailyBtn").getAttribute("aria-pressed"), solvable: E("solveFrom")(E("nbs()"), 99, E("savedMines"), 8 * 30 + 15).solved };
      // the same date again gives the same board
      E("startDaily('2026-10-11')"); await until(() => !E("gen"), 30000);
      o.same = Array.from(E("savedMines")).join("") === lay;
      E("startDaily('2026-10-12')"); await until(() => !E("gen"), 30000);
      o.differentNextDay = Array.from(E("savedMines")).join("") !== lay;
      o.sha = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(lay)))).map(b => b.toString(16).padStart(2, "0")).join("");
      return o;
    """)
    assert r["key"] == "daily" and r["size"] == [30, 16, 99] and r["gameNo"] == "2026-10-11" and r["pressed"] == "true", r
    assert not r["started"] and r["centerOpen"] and r["opened"] > 1 and r["clicks"] == 1 and r["solvable"], r
    assert r["same"] and r["differentNextDay"], r
    assert r["status"].startswith("2026-10-11"), r
    # every engine builds exactly this board for that date (the fingerprint of its mine layout)
    assert r["sha"] == DAILY_2026_10_11, r["sha"]


DAILY_2026_10_11 = "cf3cbcb9d1354aaccff45514c5203885b4552ea185862ceb471272b4000431a1"


def test_daily_clock_starts_with_first_move_and_win_is_logged_and_shareable(game, browser_name):
    r = game.run(r"""
      E("stats = {}"); E("startDaily('2026-10-11')"); await until(() => !E("gen"), 30000);
      await sleep(300);
      const notStarted = !E("started") && $("time").textContent === "00:00.0";
      // first move: a chord on an open number if possible, else open a safe cell
      const m = E("mines"), o = E("open"); const safe = [...Array(480).keys()].find(i => !m[i] && !o[i]);
      E("cells")[safe].click();
      const startedAfter = E("started");
      winNow();
      return { notStarted, startedAfter, won: status().startsWith("클리어"), share: $("statusAct").textContent, log: E("dailyLog")["2026-10-11"],
               stats: E("stats").daily, line: !$("winStats").hidden };
    """)
    assert r["notStarted"] and r["startedAfter"] and r["won"] and r["line"], r
    assert r["share"] == game.ev("L().dailyShare") and r["log"]["wins"] == 1 and r["log"]["best"] is not None, r
    assert r["stats"]["played"] == 1 and r["stats"]["won"] == 1, r
    if browser_name == "chromium":
        game.page.context.grant_permissions(["clipboard-read", "clipboard-write"])
        game.run('$("statusAct").click(); await sleep(200);')
        text = game.page.evaluate("navigator.clipboard.readText()")
        assert text.startswith("MINE:D 오늘의 판 2026-10-11\n⏱ ") and "3BV/s" in text, text
        assert game.ev("statusKey") == "dailyCopied"


def test_daily_from_url_and_leaving_it(game):
    game.goto("/?daily")
    game.page.wait_for_function("() => window.__ev('cfg').key === 'daily' && !window.__ev('gen')")
    r = game.run(r"""
      const o = { key: E("cfg").key, opened: E("openedCount") > 1 };
      $("newGame").click();
      o.after = E("cfg").key; o.pressed = $("dailyBtn").getAttribute("aria-pressed");
      return o;
    """)
    assert r == {"key": "daily", "opened": True, "after": "expert", "pressed": "false"}, r


def test_daily_restart_reopens_center_and_stats_row(game):
    """A restarted daily board waits like a fresh one: center open, clock at zero until the first move,
    and the restart alone is not counted as a game played."""
    r = game.run(r"""
      E("stats = {}"); E("startDaily('2026-10-11')"); await until(() => !E("gen"), 30000);
      const m = E("mines"); const mine = [...Array(480).keys()].find(i => m[i] && !E("open")[i]);
      E("cells")[mine].click();   // lose
      $("restart").click(); await sleep(400);
      const o = { started: E("started"), clock: $("time").textContent, centerOpen: !!E("open")[8 * 30 + 15], key: E("cfg").key, status: status(),
                  clicks: E("clicks"), played: E("stats").daily.played };
      $("statsBtn").click(); o.rows = [...$("statsTable").querySelectorAll("tbody tr td:first-child")].map(x => x.textContent); $("statsClose").click();
      const safe = [...Array(480).keys()].find(i => !m[i] && !E("open")[i]);
      E("cells")[safe].click(); await sleep(250);
      o.startedByMove = E("started"); o.playedAfterMove = E("stats").daily.played; o.running = E("playSeconds()") > 0.15;
      return o;
    """)
    assert not r["started"] and r["clock"] == "00:00.0" and r["centerOpen"] and r["key"] == "daily" and r["clicks"] == 1, r
    assert r["status"].startswith("2026-10-11") and r["played"] == 1, r
    assert r["startedByMove"] and r["playedAfterMove"] == 2 and r["running"], r
    assert "오늘의 판" in r["rows"], r


# ---------------- input ----------------

def test_both_button_and_middle_click_chord(game, browser_name):
    p = game.page
    setup = r"""
      gmode("safe"); level("beginner"); E(`newGame(${arg})`); E("cells")[40].click();
      const N = E("nbs()"), m = E("mines"), o = E("open"), c = E("counts");
      for (let i = 0; i < 81; i++) if (o[i] && c[i] && N[i].some(j => !o[j] && !m[j])) {
        for (const j of N[i]) if (m[j] && !E("flags")[j]) E(`toggleFlag(${j})`);
        const r = E("cells")[i].getBoundingClientRect(); return { i, x: r.x + r.width / 2, y: r.y + r.height / 2, before: E("openedCount"), clicks: E("clicks") };
      }
      return null;
    """
    for order in ["left-first", "right-first", "middle"]:
        for seed in range(11, 60):
            t = game.run(setup, seed)
            if t:
                break
        assert t, "no chordable position"
        p.mouse.move(t["x"], t["y"])
        if order == "middle":
            p.mouse.click(t["x"], t["y"], button="middle")
        else:
            p.mouse.down(button="right"); p.mouse.down(button="left")
            if order == "left-first":
                p.mouse.up(button="left"); p.mouse.up(button="right")
            else:
                p.mouse.up(button="right"); p.mouse.up(button="left")
        r = game.run(f'return {{ opened: E("openedCount"), flagOnNumber: E("flags")[{t["i"]}], over: E("over"), clicks: E("clicks") }};')
        assert r["opened"] > t["before"] and not r["flagOnNumber"] and not r["over"], (order, t, r)
        assert r["clicks"] == t["clicks"] + 1, (order, t, r)


def test_both_buttons_on_a_closed_cell_do_nothing(game):
    p = game.page
    game.run('gmode("safe"); level("beginner"); E("newGame(12)"); E("cells")[40].click();')
    i = game.ev("cells.findIndex((c, k) => !open[k])")
    x, y = game.page.evaluate(f"(() => {{ const r = window.__ev('cells')[{i}].getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; }})()")
    before = game.ev("openedCount")
    p.mouse.move(x, y); p.mouse.down(button="left"); p.mouse.down(button="right"); p.mouse.up(button="left"); p.mouse.up(button="right")
    assert game.ev("openedCount") == before and not game.ev(f"open[{i}]") and not game.ev("over")


def test_right_click_flags_and_counts(game):
    game.run('gmode("safe"); level("beginner"); E("newGame(13)"); E("cells")[40].click();')
    i = game.ev("cells.findIndex((c, k) => !open[k])")
    game.page.locator(f'#board .cell[data-i="{i}"]').click(button="right")
    assert game.ev(f"flags[{i}]") == 1 and game.ev("clicks") == 2


def touch_ctx(browser, browser_name):
    opts = {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 3, "has_touch": True}
    if browser_name != "firefox":
        opts["is_mobile"] = True
    return browser.new_context(**opts)


def test_hold_to_flag_logic_all_engines(browser, server, browser_name):
    """Touch-type pointer events (synthetic, so every engine runs the same logic): hold flags without opening,
    a short tap opens, moving cancels, the setting is remembered, 'off' never flags."""
    from harness import Game
    ctx = touch_ctx(browser, browser_name)
    try:
        g = Game(ctx.new_page(), server.url).goto("/")
        r = g.run(r"""
          gmode("safe"); level("beginner"); E("newGame(21)"); E("cells")[40].click();
          const fire = (c, type, x = 0) => { const r = c.getBoundingClientRect();
            c.dispatchEvent(new PointerEvent(type, { bubbles: true, pointerType: "touch", isPrimary: true, clientX: r.x + 5 + x, clientY: r.y + 5 })); };
          const hold = async (i, ms, move = 0) => { const c = E("cells")[i]; fire(c, "pointerdown"); await sleep(40); const ring = c.classList.contains("holding");
            if (move) fire(c, "pointermove", move); await sleep(ms); fire(c, "pointerup"); c.click(); await sleep(20); return ring; };
          const closed = () => E("cells").findIndex((c, k) => !E("open")[k] && !E("flags")[k]);
          const a = closed(); const ring = await hold(a, 400);
          const o = { ring, flagged: E("flags")[a] === 1, notOpened: !E("open")[a], over: E("over") };
          const b = closed(); await hold(b, 400, 30); o.moveCancels = !E("flags")[b];
          // a short tap goes through as a click (opens a safe cell)
          const m = E("mines"); const safe = E("cells").findIndex((c, k) => !E("open")[k] && !m[k] && !E("flags")[k]);
          await hold(safe, 0); o.tapOpens = !!E("open")[safe];
          // the setting
          document.querySelector('#holdSet [data-hold="0"]').click(); o.saved = JSON.parse(localStorage.getItem("minesweeper-hold"));
          const d = closed(); await hold(d, 600); o.offNoFlag = !E("flags")[d];
          document.querySelector('#holdSet [data-hold="500"]').click();
          o.pressed = document.querySelector('#holdSet [data-hold="500"]').getAttribute("aria-pressed");
          // a touch contextmenu (long-press on Android) is ignored: the hold timer is the only flagger
          const e = closed(); E("cells")[e].dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, pointerType: "touch" }));
          E("endHold()");
          E("cells")[e].dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true })); o.ctxIgnored = !E("flags")[e];
          return o;
        """)
        assert r["ring"] and r["flagged"] and r["notOpened"] and not r["over"], r
        assert r["moveCancels"] and r["tapOpens"] and r["saved"] == 0 and r["offNoFlag"] and r["pressed"] == "true" and r["ctxIgnored"], r
        g.goto("/", clear=False)
        assert g.ev("holdMs") == 500
        assert g.page.evaluate("getComputedStyle(document.getElementById('holdSet')).display") != "none"
    finally:
        ctx.close()


@chromium_only
def test_hold_to_flag_with_real_touch(browser, server, browser_name):
    from harness import Game
    ctx = touch_ctx(browser, browser_name)
    try:
        page = ctx.new_page()
        g = Game(page, server.url).goto("/")
        g.run('document.getElementById("introOk").click(); gmode("safe"); level("beginner"); E("newGame(21)");')
        cdp = ctx.new_cdp_session(page)
        xy = lambda i: page.evaluate(f"(() => {{ const r = window.__ev('cells')[{i}].getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; }})()")
        x, y = xy(40); page.touchscreen.tap(x, y); time.sleep(0.2)
        assert g.ev("started")
        i = g.ev("cells.findIndex((c, k) => !open[k])")
        x, y = xy(i)
        cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]})
        time.sleep(0.15)
        ring = g.ev(f"cells[{i}].classList.contains('holding')")
        time.sleep(0.35)
        cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        time.sleep(0.3)
        assert ring and g.ev(f"flags[{i}]") == 1 and not g.ev(f"open[{i}]") and not g.ev("over")
    finally:
        ctx.close()


# ---------------- offline / install ----------------

def test_manifest_is_valid(game):
    m = game.page.evaluate("fetch('/manifest.webmanifest').then(r => r.json())")
    assert m["short_name"] == "MINE:D" and m["start_url"] == "/" and m["display"] == "standalone"
    for icon in m["icons"]:
        assert game.page.evaluate(f"fetch('{icon['src']}').then(r => r.ok)"), icon
    assert game.page.evaluate("document.querySelector('link[rel=manifest]').getAttribute('href')") == "/manifest.webmanifest"


@chromium_only
def test_works_offline_after_first_visit(game):
    p = game.page
    p.wait_for_function("() => navigator.serviceWorker && navigator.serviceWorker.controller || navigator.serviceWorker.ready.then(() => true)")
    p.evaluate("navigator.serviceWorker.ready")
    p.reload()   # the worker now controls the page and has cached the pages
    p.wait_for_function("() => !!navigator.serviceWorker.controller")
    p.wait_for_function("() => caches.keys().then(k => k.length > 0)")
    p.context.set_offline(True)
    try:
        for path in ["/", "/en/", "/?daily"]:
            p.goto(game.base + path, wait_until="domcontentloaded")
            p.wait_for_function("() => !!window.__ev")
            r = game.run('E("newGame(5)"); E("cells")[40].click(); return { started: E("started"), lang: document.documentElement.lang };')
            assert r["started"], (path, r)
    finally:
        p.context.set_offline(False)
