"""Improvements drawn from what players ask of minesweeper games (GitHub issues of open-source clients, Hacker News
threads): take back a mine and play on, winning streaks, the last level remembered, a compact phone menu,
statistics backup, and small input fixes."""
import json

import pytest

from harness import Game

PHONE = {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 2, "has_touch": True}


def phone_ctx(browser, browser_name, **extra):
    opts = dict(PHONE, **extra)
    if browser_name != "firefox":
        opts["is_mobile"] = True
    return browser.new_context(**opts)


# ---------------- take back a mine ----------------

def test_take_back_a_mine_restores_the_board_and_plays_on(game):
    r = game.run(r"""
      gmode("safe"); level("beginner"); E("stats = {}; newGame(5)"); E("cells")[40].click();
      const m = E("mines"), cells = E("cells");
      const wrong = [...Array(81).keys()].find(i => !m[i] && !E("open")[i]);      // a flag on a safe cell
      E(`toggleFlag(${wrong})`);
      await sleep(300);
      const before = { open: Array.from(E("open")).join(""), flags: Array.from(E("flags")).join(""), left: $("minesLeft").textContent, secs: E("playSeconds()") };
      const mine = [...Array(81).keys()].find(i => m[i] && !E("flags")[i]);
      cells[mine].click();
      const lost = { over: E("over"), act: $("statusAct").textContent, shown: !$("statusAct").hidden, boom: cells[mine].classList.contains("boom"),
                     wrongShown: cells[wrong].classList.contains("wrong"), stats: JSON.parse(JSON.stringify(E("stats").beginner)) };
      await sleep(600);                       // looking at the lost board is not play time
      $("statusAct").click();
      const o = { before, lost, over: E("over"), undone: E("undone"), status: E("statusKey"), actHidden: $("statusAct").hidden,
                  open: Array.from(E("open")).join(""), flagged: E("flags")[mine], wrongBack: cells[wrong].className,
                  left: $("minesLeft").textContent, secs: E("playSeconds()"),
                  leftovers: cells.filter(c => /\b(mine|boom|wrong)\b/.test(c.className)).length,
                  closedLooksOpen: cells.filter((c, i) => !E("open")[i] && c.classList.contains("open")).length,
                  leaks: cells.filter((c, i) => m[i] && !E("flags")[i] && !c.getAttribute("aria-label").endsWith(E("L().cs.closed"))).length,
                  mineLabel: cells[mine].getAttribute("aria-label") };
      await sleep(250); o.running = E("playSeconds()") > o.secs + 0.15;
      // the flag on the mine cannot be stepped on again by accident; play on to the end
      cells[mine].click(); o.stillAlive = !E("over");
      E(`toggleFlag(${wrong})`); winNow();
      o.end = { over: E("over"), status: E("statusKey"), text: status(), stats: E("stats").beginner, line: $("winStats").textContent };
      return o;
    """)
    lost, end = r["lost"], r["end"]
    assert lost["over"] and lost["shown"] and lost["act"] == game.ev("L().undoLose") and lost["boom"] and lost["wrongShown"], lost
    assert not r["over"] and r["undone"] and r["status"] == "undone" and r["actHidden"], r
    assert r["open"] == r["before"]["open"] and r["flagged"] == 1 and r["wrongBack"] == "cell flag", r
    assert r["leftovers"] == 0 and r["closedLooksOpen"] == 0 and r["leaks"] == 0 and r["mineLabel"].endswith("깃발"), r
    assert int(r["left"]) == int(r["before"]["left"]) - 1, r
    assert abs(r["secs"] - r["before"]["secs"]) < 0.25 and r["running"] and r["stillAlive"], r     # the 0.6 s pause was left out
    assert end["over"] and end["status"] == "winUndone" and end["text"].startswith("클리어"), end
    assert end["stats"]["played"] == 1 and end["stats"]["won"] == 0 and end["stats"]["best"] is None and not end["stats"].get("streak"), end
    assert lost["stats"]["played"] == 1 and "연승" not in end["line"], r


def test_take_back_after_a_chord_and_on_the_daily_board(game):
    r = game.run(r"""
      // a chord with a wrong flag steps on a mine: neighbors opened before it stay open, the rest can still be played
      gmode("safe"); level("beginner"); let found = null;
      for (let seed = 11; seed < 80 && !found; seed++) {
        E(`newGame(${seed})`); E("cells")[40].click();
        const N = E("nbs()"), m = E("mines"), o = E("open"), c = E("counts");
        for (let i = 0; i < 81 && !found; i++) {
          if (!o[i] || c[i] !== 1) continue;
          const closed = N[i].filter(j => !o[j]);
          if (closed.length >= 2 && closed.some(j => !m[j])) found = { i, wrong: closed.find(j => !m[j]), mine: closed.find(j => m[j]) };
        }
      }
      assert(found, "no chord position");
      E(`toggleFlag(${found.wrong})`); E("cells")[found.i].click();
      const o = { lost: E("over") };
      $("statusAct").click();
      o.alive = !E("over") && E("flags")[found.mine] === 1 && E("flags")[found.wrong] === 1;
      E(`toggleFlag(${found.wrong})`); winNow(); o.end = E("statusKey");
      // the daily board: a cleared game after a take-back is neither logged nor shareable
      E("stats = {}"); E("startDaily('2026-10-11')"); await until(() => !E("gen"), 30000);
      const m = E("mines"); const mine = [...Array(480).keys()].find(i => m[i]);
      E("cells")[mine].click(); $("statusAct").click(); winNow();
      o.daily = { status: E("statusKey"), log: E("dailyLog")["2026-10-11"] || null, share: !$("statusAct").hidden, stats: E("stats").daily };
      return o;
    """)
    assert r["lost"] and r["alive"] and r["end"] == "winUndone", r
    assert r["daily"] == {"status": "winUndone", "log": None, "share": False, "stats": r["daily"]["stats"]} and r["daily"]["stats"]["won"] == 0, r


# ---------------- winning streaks ----------------

def test_streak_counts_wins_in_a_row_and_breaks_on_a_loss_or_an_abandoned_game(game):
    r = game.run(r"""
      gmode("safe"); level("beginner"); E("stats = {}");
      const st = () => { const s = E("stats").beginner; return [s.streak || 0, s.maxStreak || 0]; };
      const play = (no, how) => { E(`newGame(${no})`); E("cells")[40].click();
        if (how === "win") winNow(); else if (how === "lose") { const m = E("mines").findIndex((v, i) => v && !E("open")[i]); E("cells")[m].click(); } };
      const o = {};
      play(31, "win"); o.one = st(); o.line1 = $("winStats").textContent;
      play(32, "win"); o.two = st(); o.line2 = $("winStats").textContent;
      play(33, "win"); o.three = st();
      play(34, "lose"); o.lost = st();
      play(35, "win"); o.again = st();
      play(36, "win"); o.again2 = st();
      play(37, "leave");                 // started, then dropped for a new game
      play(38, "win"); o.afterLeft = st();
      E("hintUsed = false"); play(39, "leave"); E("hintUsed = true"); winNow(); o.hinted = st();     // a hinted win is still a win
      $("statsBtn").click();
      o.head = [...$("statsTable").querySelectorAll("th")].map(x => x.textContent);
      o.cell = $("statsTable").querySelector("tbody tr").children[o.head.indexOf(E("L().cols[4]"))].textContent;
      $("statsClose").click();
      o.saved = JSON.parse(localStorage.getItem("minesweeper-stats-v3")).beginner;
      return o;
    """)
    assert [r["one"], r["two"], r["three"], r["lost"], r["again"], r["again2"]] == [[1, 1], [2, 2], [3, 3], [0, 3], [1, 3], [2, 3]], r
    assert r["afterLeft"] == [1, 3] and r["hinted"] == [2, 3], r
    assert "연승" not in r["line1"] and r["line2"].endswith(" · 2연승"), r
    assert r["head"][4] == "연승 (최고)" and r["cell"] == "2 (3)", r
    assert r["saved"]["streak"] == 2 and r["saved"]["maxStreak"] == 3 and r["saved"]["played"] == 9 and r["saved"]["won"] == 7, r


def test_streak_fields_are_cleaned_like_the_rest(game):
    r = game.run(r"""
      const c = E("cleanStats");
      const good = { a: { played: 9, won: 7, best: 3.2, streak: 2, maxStreak: 3, unfinished: false } };
      assert(JSON.stringify(c(good)) === JSON.stringify(good), "good data changed");
      return c({ a: { played: 3, won: 2, best: 1, streak: 5, maxStreak: 2 }, b: { played: 3, won: 2, best: 1, streak: -1, maxStreak: "x", unfinished: "yes" },
                 c: { played: 1, won: 1, best: 2, streak: 1 } });
    """)
    assert r["a"]["streak"] == 5 and r["a"]["maxStreak"] == 5, r
    assert r["b"] == {"played": 3, "won": 2, "best": 1} and r["c"]["maxStreak"] == 1, r


# ---------------- the level played last ----------------

def test_last_level_comes_back_on_the_next_visit(game):
    g = game
    pressed = lambda: g.page.evaluate("[...document.querySelectorAll('#levels [aria-pressed=\"true\"]')].map(b => b.dataset.level)")
    assert g.ev("cfg.key") == "beginner"
    g.run('level("expert");')
    g.goto("/", clear=False)
    assert g.ev("[cfg.key, cfg.w, cfg.h, cfg.m]") == ["expert", 30, 16, 99] and pressed() == ["expert"] and g.ev("cells.length") == 480
    g.run("custom(12, 10, 20);")
    g.goto("/", clear=False)
    assert g.ev("[cfg.key, cfg.w, cfg.h, cfg.m]") == ["custom", 12, 10, 20] and pressed() == ["custom"]
    assert g.page.evaluate("['cw', 'ch', 'cm'].map(i => +document.getElementById(i).value)") == [12, 10, 20]
    # the daily board and built boards are visits, not the player's level
    g.run('E("startDaily(\'2026-10-11\')"); await until(() => !E("gen"), 30000); E(`playEdited(new Uint8Array(100).map((_, i) => i < 5 ? 1 : 0), 10, 10, true)`);')
    g.goto("/", clear=False)
    assert g.ev("[cfg.key, cfg.w, cfg.h, cfg.m]") == ["custom", 12, 10, 20]
    # a shared board or the daily link still wins over the remembered level
    g.goto("/?board=" + g.ev("encodeBoard(9, 9, new Uint8Array(81).map((_, i) => i < 5 ? 1 : 0))"), clear=False)
    assert g.ev("cfg.key") == "edited"
    for bad in [{"key": "custom", "w": 500, "h": 10, "m": 5}, {"key": "custom", "w": 10, "h": 10, "m": 100}, {"key": "custom", "w": 10.5, "h": 10, "m": 5},
                {"key": "nope"}, {"key": "daily"}, {"key": "constructor"}, "x", [1], None]:
        g.page.evaluate("v => localStorage.setItem('minesweeper-level', JSON.stringify(v))", bad)
        g.goto("/", clear=False)
        assert g.ev("cfg.key") == "beginner" and g.ev("cells.length") == 81, bad


# ---------------- input ----------------

def test_no_browser_menu_anywhere_on_the_board(game):
    r = game.run(r"""
      gmode("safe"); level("beginner"); E("newGame(5)"); E("cells")[40].click();
      const fire = el => { const e = new MouseEvent("contextmenu", { bubbles: true, cancelable: true }); el.dispatchEvent(e); return e.defaultPrevented; };
      const closed = E("cells").findIndex((c, i) => !E("open")[i]);
      const o = { border: fire($("board")), row: fire(document.querySelector(".brow")), cell: fire(E("cells")[closed]), flagged: E("flags")[closed] };
      E("pause()"); o.paused = fire($("board")); o.outside = fire($("status"));
      return o;
    """)
    assert r == {"border": True, "row": True, "cell": True, "flagged": 1, "paused": True, "outside": False}, r


# ---------------- phone menu ----------------

def test_phone_menu_folds_so_the_board_is_on_the_first_screen(browser, server, browser_name):
    ctx = phone_ctx(browser, browser_name)
    try:
        page = ctx.new_page()
        g = Game(page, server.url).goto("/")
        look = lambda: g.run(r"""
          const vis = el => !!(el.offsetWidth || el.offsetHeight), b = $("board").getBoundingClientRect();
          const items = [...document.querySelectorAll("#menu .mi, #menu .modes button, #menu .langs button, #menu .zoom button")].filter(vis);
          return { open: $("menu").classList.contains("open"), expanded: $("menuToggle").getAttribute("aria-expanded"),
                   groups: [...document.querySelectorAll("#menu .group")].filter(vis).length, items: items.length,
                   minH: items.length ? Math.round(Math.min(...items.map(x => x.getBoundingClientRect().height))) : null,
                   bar: ["barNew", "menuToggle"].map(i => [vis($(i)), Math.round($(i).getBoundingClientRect().height), $(i).textContent]),
                   boardTop: Math.round(b.top), boardBottom: Math.round(b.bottom), viewH: innerHeight, overflowX: document.documentElement.scrollWidth - innerWidth };
        """)
        g.run('$("introOk").click();')
        c = look()
        assert not c["open"] and c["expanded"] == "false" and c["groups"] == 0 and c["items"] == 0, c
        assert c["bar"] == [[True, 38, "새 게임"], [True, 38, "메뉴"]], c
        assert c["boardTop"] < 300 and c["boardBottom"] <= c["viewH"] and c["overflowX"] <= 0, c     # the whole beginner board, no scrolling
        page.tap("#menuToggle")
        o = look()
        assert o["open"] and o["expanded"] == "true" and o["groups"] == 7 and o["items"] >= 25 and o["minH"] >= 30 and o["overflowX"] <= 0, o
        # things that change the game fold the menu; display settings and the two entries that open a form do not
        page.tap("#modeDark"); page.tap("#zoomOut")
        assert look()["open"] and page.evaluate("document.documentElement.dataset.theme") == "dark"
        page.tap('[data-level="expert"]')
        assert not look()["open"] and g.ev("cfg.key") == "expert"
        page.tap("#menuToggle"); page.tap('[data-level="custom"]')
        assert look()["open"] and not page.evaluate("document.getElementById('custom').hidden")
        page.fill("#cw", "12"); page.fill("#ch", "10"); page.fill("#cm", "500"); page.tap("#t-start")
        assert look()["open"] and not page.evaluate("document.getElementById('customErr').hidden")       # a refused size keeps the form in view
        page.fill("#cm", "20"); page.tap("#t-start")
        assert not look()["open"] and g.ev("[cfg.w, cfg.h, cfg.m]") == [12, 10, 20]
        page.tap("#menuToggle"); page.tap("#byNumber")
        assert look()["open"]
        page.fill("#numIn", "4242"); page.tap("#t-numGo")
        assert not look()["open"] and g.ev("gameNo") == 4242
        page.tap("#menuToggle"); page.tap('[data-gmode="noguess"]')
        assert not look()["open"] and g.ev("gameMode") == "noguess"
        page.tap("#menuToggle"); page.tap("#statsBtn")
        assert not look()["open"] and not page.evaluate("document.getElementById('statsDlg').hidden")
        page.tap("#statsClose"); page.tap("#menuToggle"); page.tap("#menuToggle")
        assert not look()["open"]
        page.tap("#menuToggle"); page.tap("#barNew")
        assert not look()["open"] and g.ev("gameNo") != 4242 and not g.ev("started")
    finally:
        ctx.close()


@pytest.mark.parametrize("path,new,menu", [("/", "새 게임", "메뉴"), ("/en/", "New game", "Menu"), ("/ja/", "新しいゲーム", "メニュー"), ("/zh/", "新游戏", "菜单")])
def test_desktop_keeps_the_side_menu_and_bar_texts_follow_the_language(game, path, new, menu):
    game.goto(path)
    r = game.run(r"""
      const vis = el => !!(el.offsetWidth || el.offsetHeight);
      $("menu").classList.add("open");       // the phone class changes nothing on a wide window
      const o = { bar: [vis($("barNew")), vis($("menuToggle"))], texts: [$("barNew").textContent, $("menuToggle").textContent],
                  groups: [...document.querySelectorAll("#menu .group")].filter(vis).length, w: Math.round($("menu").getBoundingClientRect().width),
                  pos: getComputedStyle($("menu")).position, miH: Math.round(document.querySelector(".mi").getBoundingClientRect().height) };
      $("menu").classList.remove("open"); o.groupsClosed = [...document.querySelectorAll("#menu .group")].filter(vis).length;
      return o;
    """)
    assert r == {"bar": [False, False], "texts": [new, menu], "groups": 7, "w": 200, "pos": "fixed", "miH": r["miH"], "groupsClosed": 7} and r["miH"] < 26, r


# ---------------- records backup ----------------

MINE = {"beginner": {"played": 12, "won": 7, "best": 4.2, "time": 321.5, "bps": 2.5, "streak": 2, "maxStreak": 4},
        "expert@noguess": {"played": 3, "won": 1, "best": 150.0, "time": 900}, "custom-10x10-12@random": {"played": 1, "won": 1, "best": 9.9}}
MINE_DAILY = {"2026-10-11": {"wins": 2, "best": 41.3}, "2026-10-12": {"wins": 1, "best": None}}


def _pick(g, path, expect):
    """Choose a file the way a player does: the Import button opens the file chooser."""
    g.page.evaluate("document.getElementById('backupMsg').dataset.key = ''")
    with g.page.expect_file_chooser() as fc:
        g.page.click("#statsImport")
    fc.value.set_files(str(path))
    g.page.wait_for_function("k => document.getElementById('backupMsg').dataset.key === k", arg=expect)


def _records(g):
    return g.run('return { stats: JSON.parse(localStorage.getItem("minesweeper-stats-v3")), daily: JSON.parse(localStorage.getItem("minesweeper-daily")), live: E("stats"), liveDaily: E("dailyLog") };')


def test_records_export_to_a_file_and_merge_into_another_browser(game, browser, server, tmp_path):
    game.run('E(`stats = ${JSON.stringify(arg[0])}; dailyLog = ${JSON.stringify(arg[1])}; write(STATS, stats); write(DAILY_LOG, dailyLog)`); $("statsBtn").click();', [MINE, MINE_DAILY])
    with game.page.expect_download() as dl:
        game.page.click("#statsExport")
    path = tmp_path / "records.json"
    dl.value.save_as(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert dl.value.suggested_filename.startswith("mined-records-") and dl.value.suggested_filename.endswith(".json")
    assert data["app"] == "MINE:D" and data["stats"] == MINE and data["daily"] == MINE_DAILY, data
    assert game.page.inner_text("#backupMsg") == game.ev("L().backupSaved")

    ctx = browser.new_context(viewport={"width": 1400, "height": 900})
    try:
        g = Game(ctx.new_page(), server.url).goto("/")
        theirs = {"beginner": {"played": 20, "won": 5, "best": 6.0, "time": 100, "streak": 1, "maxStreak": 2, "unfinished": True},
                  "god": {"played": 2, "won": 0, "best": None}}
        g.run('E(`stats = ${JSON.stringify(arg[0])}; dailyLog = ${JSON.stringify(arg[1])}; write(STATS, stats); write(DAILY_LOG, dailyLog)`); $("statsBtn").click();',
              [theirs, {"2026-10-11": {"wins": 1, "best": 30.0}, "2026-10-13": {"wins": 1, "best": 77.0}}])
        _pick(g, path, "importDone")
        want = {"beginner": {"played": 20, "won": 7, "best": 4.2, "time": 321.5, "bps": 2.5, "streak": 1, "maxStreak": 4, "unfinished": True},
                "god": {"played": 2, "won": 0, "best": None},
                "expert@noguess": {"played": 3, "won": 1, "best": 150.0, "time": 900}, "custom-10x10-12@random": {"played": 1, "won": 1, "best": 9.9}}
        want_daily = {"2026-10-11": {"wins": 2, "best": 30.0}, "2026-10-12": {"wins": 1, "best": None}, "2026-10-13": {"wins": 1, "best": 77.0}}
        r = _records(g)
        assert r["stats"] == want and r["live"] == want and r["daily"] == want_daily and r["liveDaily"] == want_daily, r
        assert g.page.inner_text("#backupMsg") == g.ev("L().importDone")
        first_row = g.page.evaluate("[...document.querySelector('#statsTable tbody tr').children].map(td => td.textContent)")
        assert first_row[1:4] == ["20", "7", "35%"] and first_row[5] == g.ev("fmt(4.2)"), first_row          # the table shows the merged numbers
        _pick(g, path, "importDone")                                                                        # the same file again changes nothing
        assert _records(g)["stats"] == want and _records(g)["daily"] == want_daily
    finally:
        ctx.close()


def test_import_refuses_other_files_and_unknown_entries(game, tmp_path):
    g = game
    g.run('E(`stats = ${JSON.stringify(arg)}; write(STATS, stats)`); $("statsBtn").click();', MINE)
    before = _records(g)["stats"]
    bad = {"not-json.json": "{oops", "other-app.json": json.dumps({"app": "Other", "stats": {"beginner": {"played": 99, "won": 99, "best": 0.1}}}),
           "no-stats.json": json.dumps({"app": "MINE:D", "stats": [1, 2]}), "list.json": "[1, 2, 3]",
           "huge.json": json.dumps({"app": "MINE:D", "stats": {}, "pad": "x" * 2_100_000})}
    for name, text in bad.items():
        f = tmp_path / name
        f.write_text(text, encoding="utf-8")
        _pick(g, f, "importBad")
        assert _records(g)["stats"] == before, name
    assert g.page.inner_text("#backupMsg") == g.ev("L().importBad")
    # a valid file with entries this game does not have: only real level names get in, values are repaired as on load
    f = tmp_path / "odd.json"
    f.write_text('{"app": "MINE:D", "stats": {"__proto__": {"played": 5, "won": 5, "best": 1}, "constructor": {"played": 5, "won": 5, "best": 1}, '
                 '"<img src=x onerror=alert(1)>": {"played": 5, "won": 5, "best": 1}, "custom-9999x9-1": {"played": 1, "won": 1, "best": 1}, '
                 '"god@noguess": {"played": 2, "won": 9, "best": -4, "bps": "fast"}, "intermediate": 7}, "daily": {"bad": {"wins": 1}, "2026-10-20": {"wins": 2, "best": 50}}}',
                 encoding="utf-8")
    _pick(g, f, "importDone")
    r = _records(g)
    assert r["stats"] == {**before, "god@noguess": {"played": 2, "won": 2, "best": None}}, r["stats"]
    assert r["daily"] == {"2026-10-20": {"wins": 2, "best": 50}}, r["daily"]
    assert g.ev("({}).played === undefined && Object.getPrototypeOf(stats) === Object.prototype")
    # the dialog keeps Tab inside with the new buttons too
    ids = []
    for _ in range(5):
        g.page.keyboard.press("Tab"); ids.append(g.page.evaluate("document.activeElement.id"))
    assert set(ids) == {"statsExport", "statsImport", "statsReset", "statsClose"}, ids


# ---------------- the safest guess ----------------

def test_chances_match_counting_every_layout(game):
    """exactCheck().odds against brute force: on thousands of small positions every closed cell's chance equals the share of
    the layouts (all ways to place the mines that fit the open numbers) in which it is a mine. On large boards, where the
    counts overflow any number type, the chances still add up to the number of mines."""
    r = game.run(r"""
      const nbTable = E("nbTable"), exactCheck = E("exactCheck"), rng = E("rng");
      let checked = 0, guessing = 0, maxErr = 0; const bad = [];
      for (let seed = 1; seed <= 2500 && bad.length < 3; seed++) {
        const r = rng(seed), w = 3 + Math.floor(r() * 4), h = 3 + Math.floor(r() * 3), n = w * h, N = nbTable(w, h);
        const m = 1 + Math.floor(r() * Math.min(n - 2, 9));
        const lay = new Uint8Array(n); for (let left = m; left;) { const i = Math.floor(r() * n); if (!lay[i]) { lay[i] = 1; left--; } }
        const cnt = new Uint8Array(n); for (let i = 0; i < n; i++) if (!lay[i]) cnt[i] = N[i].reduce((a, j) => a + lay[j], 0);
        const opened = new Uint8Array(n), p = 0.15 + r() * 0.6;
        for (let i = 0; i < n; i++) if (!lay[i] && r() < p) opened[i] = 1;
        const closed = []; for (let i = 0; i < n; i++) if (!opened[i]) closed.push(i);
        if (closed.length > 18) continue;
        const freq = new Float64Array(n), L = closed.length; let total = 0;
        for (let mask = 0; mask < (1 << L); mask++) {
          let bits = 0; for (let x = mask; x; x &= x - 1) bits++;
          if (bits !== m) continue;
          const cur = new Uint8Array(n); for (let t = 0; t < L; t++) if (mask >> t & 1) cur[closed[t]] = 1;
          let ok = true;
          for (let i = 0; i < n && ok; i++) if (opened[i]) { let s = 0; for (const j of N[i]) s += cur[j]; ok = s === cnt[i]; }
          if (ok) { total++; for (const i of closed) freq[i] += cur[i]; }
        }
        const x = exactCheck(N, m, opened, cnt, 5e6);
        checked++;
        if (!x.complete || x.invalid || !x.odds) { bad.push({ seed, why: "no odds" }); continue; }
        const got = new Float64Array(n).fill(NaN); x.odds.cells.forEach((c, t) => { got[c] = x.odds.p[t]; });
        let err = 0; for (const i of closed) err = Math.max(err, Math.abs((Number.isNaN(got[i]) ? x.odds.sea : got[i]) - freq[i] / total));
        if (!(err < 1e-9)) bad.push({ seed, err });
        maxErr = Math.max(maxErr, err || 0);
        if (!x.safe.length) guessing++;
      }
      // large boards opened the way play opens them
      const big = [];
      for (const [w, h, m] of [[80, 50, 760], [100, 60, 1200], [100, 60, 5990]]) for (let seed = 1; seed <= 3; seed++) {
        const n = w * h, N = nbTable(w, h), r = rng(seed * 31 + w);
        const lay = new Uint8Array(n); for (let left = m; left;) { const i = Math.floor(r() * n); if (!lay[i]) { lay[i] = 1; left--; } }
        const cnt = new Uint8Array(n); for (let i = 0; i < n; i++) if (!lay[i]) cnt[i] = N[i].reduce((a, j) => a + lay[j], 0);
        const opened = new Uint8Array(n);
        for (let tries = 0, starts = 0; tries < n && starts < 4; tries++) {
          const k = Math.floor(r() * n); if (lay[k] || opened[k] || (cnt[k] && m < n / 2)) continue; starts++;
          const st = [k]; while (st.length) { const c = st.pop(); if (opened[c]) continue; opened[c] = 1; if (!cnt[c]) for (const j of N[c]) if (!opened[j] && !lay[j]) st.push(j); }
        }
        const x = exactCheck(N, m, opened, cnt, 300000);
        if (!x.complete || !x.odds) { big.push({ w, m, seed, incomplete: true }); continue; }
        const edge = new Set(x.odds.cells); let sum = 0, sea = 0, inRange = true;
        x.odds.p.forEach(p => { sum += p; if (!(p >= 0 && p <= 1 + 1e-12)) inRange = false; });
        for (let i = 0; i < n; i++) if (!opened[i] && !edge.has(i)) sea++;
        big.push({ w, m, seed, off: Math.abs(sum + sea * (x.odds.sea || 0) - m), inRange });
      }
      return { checked, guessing, maxErr, bad, big };
    """)
    assert r["checked"] > 1500 and r["guessing"] > 300 and not r["bad"] and r["maxErr"] < 1e-9, r
    done = [b for b in r["big"] if not b.get("incomplete")]
    assert len(done) >= 7 and all(b["inRange"] and b["off"] < 1e-6 for b in done), r["big"]


def test_hint_offers_the_safest_cell_with_its_chance_when_nothing_is_certain(game):
    r = game.run(r"""
      // stuck positions of real expert boards (the rules and the exhaustive check prove nothing safe)
      gmode("safe"); level("expert");
      const N = E("nbs()"), rng = E("rng"), out = [];
      for (let s = 1; s <= 400 && out.length < 12; s++) {
        E(`newGame(${s}); placeMines(240); begin();`);
        const st = E("solveFrom")(N, 99, E("mines"), 240);
        if (st.solved) continue;
        for (let i = 0; i < 480; i++) if (st.opened[i] && !E("open")[i]) E(`reveal(${i})`);
        const x = E("exactCheck")(N, 99, E("open"), E("counts"), 300000);
        if (!x.complete || x.safe.length || !x.odds) continue;
        for (const j of x.mines) E(`toggleFlag(${j})`);     // the hint names certain mines first; with those flagged it comes to the guess
        // what the hint should say: the lowest chance among closed, unflagged cells
        const edge = new Set(x.odds.cells), chance = i => edge.has(i) ? x.odds.p[x.odds.cells.indexOf(i)] : x.odds.sea;
        const closed = [...Array(480).keys()].filter(i => !E("open")[i]), free = closed.filter(i => !E("flags")[i]);
        const low = Math.min(...free.map(chance));
        const used0 = E("hintUsed"), flags0 = E("flagCount");
        $("hint").click(); await until(() => !E("hintStop") && E("statusKey") !== "hintChecking", 8000);
        const lit = E("cells").findIndex(c => c.classList.contains("hint-guess"));
        const o = { s, key: E("statusKey"), text: status(), lit, litChance: chance(lit), low, used: !used0 && E("hintUsed"), closed: !E("open")[lit], sum: closed.reduce((a, i) => a + chance(i), 0) };
        o.want = T("hintGuess")(Math.max(1, Math.min(99, Math.round(low * 100))));
        // a flag on that cell is the player's own call: the hint moves on to the next best cell
        E("cells")[lit].classList.remove("hint-guess");     // the first flash would still be showing
        E(`toggleFlag(${lit})`); $("hint").click(); await until(() => !E("hintStop") && E("statusKey") !== "hintChecking", 8000);
        const lit2 = E("cells").findIndex(c => c.classList.contains("hint-guess"));
        o.next = { lit2, chance: chance(lit2), nextLow: Math.min(...free.filter(i => i !== lit).map(chance)) };
        out.push(o);
      }
      return out;
    """)
    assert len(r) >= 8, len(r)
    for o in r:
        assert o["key"] == "hintGuess" and o["text"] == o["want"] and o["used"] and o["closed"], o
        assert abs(o["litChance"] - o["low"]) < 1e-12 and 0 < o["low"] < 1 and abs(o["sum"] - 99) < 1e-6, o
        assert o["next"]["lit2"] not in (-1, o["lit"]) and abs(o["next"]["chance"] - o["next"]["nextLow"]) < 1e-12, o
    assert "%" in r[0]["text"] and "주황색" in r[0]["text"]
