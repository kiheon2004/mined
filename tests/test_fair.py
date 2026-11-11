"""Safe-guess mode ("추측 안전"): when the numbers prove no cell safe, the cell the player opens is never a mine.

If it was one, the mines are laid out again so that every open number stays true. A guess made while a safe cell could
still be worked out gets no help, and neither does a cell the numbers prove to be a mine."""
import json

import pytest

from harness import Game

# Real expert boards played by the quick rules until they get stuck, in safe-guess mode.
STUCK = r"""
  gmode("fair"); level("expert");
  const N = E("nbs()"), n = 480, FIRST = 240;
  const stuck = s => {
    E(`newGame(${s}); placeMines(${FIRST}); begin();`);
    const st = E("solveFrom")(N, 99, E("mines"), FIRST);
    if (st.solved) return false;
    for (let i = 0; i < n; i++) if (st.opened[i] && !E("open")[i]) E(`reveal(${i})`);
    return true;
  };
  const check = keep => E("exactCheck")(N, 99, E("open"), E("counts"), 300000, keep);
  const layout = () => Array.from(E("mines")).join("");
  // what must hold on any board the player can see: 99 mines, none under an open cell, every open number true and shown
  const sound = () => {
    const m = E("mines"), open = E("open"), cnt = E("counts"), cells = E("cells");
    let total = 0, wrong = 0;
    for (let i = 0; i < n; i++) {
      total += m[i];
      let s = 0; for (const j of N[i]) s += m[j];
      if (!m[i] && cnt[i] !== s) wrong++;
      if (open[i] && (m[i] || (cells[i].textContent || "0") !== String(s) || !cells[i].classList.contains("open"))) wrong++;
    }
    return total === 99 && wrong === 0;
  };
"""


def test_a_forced_guess_is_never_a_mine(game):
    """Stuck with nothing provably safe, the player opens a cell that hides a mine (next to a number, or far from every
    number): the mine moves, the cell opens, and the board they were looking at is still true."""
    r = game.run(STUCK + r"""
      const out = [];
      for (let s = 1; s <= 200 && out.length < 16; s++) {
        if (!stuck(s)) continue;
        const x = check();
        if (!x.complete || x.safe.length) continue;
        for (const j of x.mines) E(`toggleFlag(${j})`);              // the player has flagged what the numbers prove
        const sure = new Set(x.mines), edge = new Set(x.odds.cells), m = E("mines");
        const hidden = [...Array(n).keys()].filter(i => m[i] && !sure.has(i));
        const kind = out.length % 2 ? "sea" : "edge";
        const pick = hidden.find(i => edge.has(i) === (kind === "edge"));
        if (pick == null) continue;
        const was = { open: Array.from(E("open")), text: E("cells").map(c => c.textContent), flags: Array.from(E("flags")).join(""), opened: E("openedCount"), left: $("minesLeft").textContent };
        E("cells")[pick].click();
        const open = E("open"), cells = E("cells");
        out.push({ s, kind, over: E("over"), key: E("statusKey"), text: status(), sound: sound(), opened: !!open[pick], more: E("openedCount") > was.opened,
          mineGone: !E("mines")[pick], kept: was.open.every((v, i) => !v || (open[i] && cells[i].textContent === was.text[i])),
          sureStay: x.mines.every(j => E("mines")[j]), flags: Array.from(E("flags")).join("") === was.flags, left: $("minesLeft").textContent === was.left,
          label: cells[pick].getAttribute("aria-label").endsWith(E("L().cs.closed")), act: $("statusAct").hidden });
      }
      // and such a game can be won and counts as a win of this mode
      E("stats = {}"); let s = 1; while (!(stuck(s) && !check().safe.length)) s++;
      const m = E("mines"), sure = new Set(check().mines), pick = [...Array(n).keys()].find(i => m[i] && !sure.has(i));
      E("cells")[pick].click(); const alive = !E("over"); winNow();
      return { out, alive, end: E("statusKey"), stats: E("stats"), want: T("fairMoved") };
    """)
    out = r["out"]
    assert len(out) >= 12 and {o["kind"] for o in out} == {"edge", "sea"}, out
    for o in out:
        assert not o["over"] and o["key"] == "fairMoved" and o["text"] == r["want"] and o["act"], o
        assert o["sound"] and o["opened"] and o["more"] and o["mineGone"] and o["kept"] and o["sureStay"] and o["flags"] and o["left"] and not o["label"], o
    assert r["alive"] and r["end"] in ("win", "winRecord"), r["end"]
    assert list(r["stats"]) == ["expert@fair"] and r["stats"]["expert@fair"]["won"] == 1, r["stats"]
    assert "추측" in r["want"]


def test_no_help_while_a_safe_cell_can_be_worked_out_or_on_a_certain_mine(game):
    r = game.run(STUCK + r"""
      const unforced = [], certain = [];
      for (let s = 1; s <= 200 && (unforced.length < 8 || certain.length < 8); s++) {
        if (!stuck(s)) continue;
        const x = check();
        if (!x.complete) continue;
        const m = E("mines"), sure = new Set(x.mines), before = layout();
        const forced = !x.safe.length, list = forced ? certain : unforced;
        if (list.length >= 8) continue;
        const pick = forced ? x.mines[0] : [...Array(n).keys()].find(i => m[i] && !sure.has(i));
        if (pick == null) continue;
        E("cells")[pick].click();
        list.push({ s, over: E("over"), key: E("statusKey"), text: status(), same: layout() === before, boom: E("cells")[pick].classList.contains("boom"),
                    act: !$("statusAct").hidden && $("statusAct").textContent === T("undoLose"), sound: sound() });
      }
      // the loss can still be taken back, like any other
      $("statusAct").click();
      return { unforced, certain, undone: E("undone") && !E("over"), texts: [T("loseFairSafe"), T("loseFairMine"), T("lose")] };
    """)
    assert len(r["unforced"]) >= 6 and len(r["certain"]) >= 6, r
    for o in r["unforced"]:
        assert o["over"] and o["key"] == "loseFairSafe" and o["text"] == r["texts"][0] and o["same"] and o["boom"] and o["act"] and o["sound"], o
    for o in r["certain"]:
        assert o["over"] and o["key"] == "loseFairMine" and o["text"] == r["texts"][1] and o["same"] and o["boom"] and o["act"], o
    assert len(set(r["texts"])) == 3 and all(t.startswith("지뢰를 밟았어요") for t in r["texts"]) and r["undone"], r["texts"]


def test_a_chord_in_a_forced_guess_is_covered_too(game):
    """Flags that are a guess, then a chord: every cell it opens is clear if the numbers allow that at all (the flags then
    mark real mines); if they do not, it is a loss."""
    r = game.run(STUCK + r"""
      const ok = [], no = [];
      for (let s = 1; s <= 200 && (ok.length < 8 || no.length < 3); s++) {
        if (!stuck(s)) continue;
        const x = check();
        if (!x.complete || x.safe.length) continue;
        const m = E("mines"), open = E("open"), cnt = E("counts");
        // an open number, flags on the right count of its closed neighbors but not on the right cells
        const plans = { ok: null, no: null };
        for (let i = 0; i < n && !(plans.ok && plans.no); i++) {
          if (!open[i] || !cnt[i]) continue;
          const closed = N[i].filter(j => !open[j]), real = closed.filter(j => m[j]), rest = closed.filter(j => !m[j]);
          if (!rest.length) continue;
          for (const a of real) for (const b of rest) {
            const flags = [...real.filter(j => j !== a), b], todo = closed.filter(j => !flags.includes(j));
            const clear = new Uint8Array(n); for (const j of todo) clear[j] = 1;
            const can = !!check({ clear, rand: Math.random }).draw;
            if (!plans[can ? "ok" : "no"]) plans[can ? "ok" : "no"] = { i, flags, todo };
          }
        }
        for (const [kind, p] of Object.entries(plans)) {
          if (!p || (kind === "ok" ? ok : no).length >= (kind === "ok" ? 8 : 3)) continue;
          stuck(s);                                                   // the same position again, untouched
          const before = layout();
          for (const j of p.flags) E(`toggleFlag(${j})`);
          E("cells")[p.i].click();                                    // a click on an open number opens around it
          const o = { s, over: E("over"), key: E("statusKey"), sound: sound(), same: layout() === before,
                      allOpen: p.todo.every(j => E("open")[j]), flagsAreMines: p.flags.every(j => E("mines")[j] && E("flags")[j]) };
          (kind === "ok" ? ok : no).push(o);
        }
      }
      return { ok, no };
    """)
    assert len(r["ok"]) >= 6 and len(r["no"]) >= 1, r
    for o in r["ok"]:
        assert not o["over"] and o["key"] == "fairMoved" and o["sound"] and o["allOpen"] and o["flagsAreMines"] and not o["same"], o
    for o in r["no"]:
        assert o["over"] and o["key"] == "loseFairMine" and o["same"], o


def test_a_player_who_only_guesses_when_forced_never_loses(game):
    """Whole games played by the exhaustive check: it opens what is provably safe, and when nothing is, a closed cell that
    is not a proven mine (next to a number if there is one). In this mode that player wins every game, on boards that
    stay true after every move. (A game is left unfinished if a position gets too tangled for the check to finish.)"""
    r = game.run(r"""
      gmode("fair");
      const rng = E("rng"), out = [];
      Math.random = rng(20261111);                                    // the same games on every run
      for (const [lv, games] of [["beginner", 12], ["intermediate", 8], ["expert", 6]]) {
        level(lv);
        const cfg = E("cfg"), n = cfg.w * cfg.h, N = E("nbs()");
        for (let g = 1; g <= games; g++) {
          const r = rng(g * 977 + n), o = { lv, g, guesses: 0, moved: 0, broken: 0 };
          E(`newGame(${g + 40})`); E(`openCell(${Math.floor(r() * n)})`);
          for (let turn = 0; turn < 2000 && !E("over"); turn++) {
            const x = E("exactCheck")(N, cfg.m, E("open"), E("counts"), 300000);
            if (!x.complete || !x.odds) { o.unsure = true; break; }
            if (x.safe.length) { for (const j of x.safe) E(`openCell(${j})`); }
            else {
              const sure = new Set(x.mines), open = E("open");
              const edge = x.odds.cells.filter(i => !sure.has(i)), free = edge.length ? edge : [...Array(n).keys()].filter(i => !open[i] && !sure.has(i));
              const pick = free[Math.floor(r() * free.length)], mine = E("mines")[pick];
              E(`openCell(${pick})`); o.guesses++;
              if (mine) o.moved++;
              if (mine && E("statusKey") !== "fairMoved" && !E("over")) o.broken++;
            }
            // the board is still true after the move
            const m = E("mines"), open = E("open"), cells = E("cells"); let total = 0;
            for (let i = 0; i < n; i++) { total += m[i]; if (open[i]) { let s = 0; for (const j of N[i]) s += m[j]; if (m[i] || (cells[i].textContent || "0") !== String(s)) o.broken++; } }
            if (total !== cfg.m) o.broken++;
          }
          o.key = E("statusKey"); o.over = E("over"); out.push(o);
        }
      }
      return out;
    """)
    played = [o for o in r if not o.get("unsure")]
    assert len(r) == 26 and len(played) >= 22, [o for o in r if o.get("unsure")]
    assert all(o["over"] and o["key"] in ("win", "winRecord") and not o["broken"] for o in played), [o for o in played if o["key"] not in ("win", "winRecord") or o["broken"]]
    assert not any(o["broken"] for o in r), r
    moved, guesses = sum(o["moved"] for o in r), sum(o["guesses"] for o in r)
    assert moved >= 5 and guesses > moved, (guesses, moved)


def test_the_new_layout_is_drawn_evenly_from_all_that_fit(game):
    """exactCheck(…, keep).draw against brute force on small positions: it is there exactly when a guess is forced and some
    layout leaves the cells clear, it is one of those layouts, and over many draws each of them comes up equally often."""
    r = game.run(r"""
      const nbTable = E("nbTable"), exactCheck = E("exactCheck"), rng = E("rng");
      const st = { tried: 0, forced: 0, drawn: 0, none: 0, notForced: 0, even: 0, worst: 0 }, bad = [];
      for (let seed = 1; seed <= 1400 && bad.length < 3; seed++) {
        const r = rng(seed + 50000), w = 3 + Math.floor(r() * 4), h = 3 + Math.floor(r() * 3), n = w * h, N = nbTable(w, h);
        const m = 1 + Math.floor(r() * Math.min(n - 2, 9));
        const lay = new Uint8Array(n); for (let left = m; left;) { const i = Math.floor(r() * n); if (!lay[i]) { lay[i] = 1; left--; } }
        const cnt = new Uint8Array(n); for (let i = 0; i < n; i++) if (!lay[i]) cnt[i] = N[i].reduce((a, j) => a + lay[j], 0);
        const opened = new Uint8Array(n), p = 0.15 + r() * 0.6;
        for (let i = 0; i < n; i++) if (!lay[i] && r() < p) opened[i] = 1;
        const closed = []; for (let i = 0; i < n; i++) if (!opened[i]) closed.push(i);
        if (closed.length > 15) continue;
        const sols = [], L = closed.length, freq = new Float64Array(n);
        for (let mask = 0; mask < (1 << L); mask++) {
          let bits = 0; for (let x = mask; x; x &= x - 1) bits++;
          if (bits !== m) continue;
          const cur = new Uint8Array(n); for (let t = 0; t < L; t++) if (mask >> t & 1) cur[closed[t]] = 1;
          let ok = true;
          for (let i = 0; i < n && ok; i++) if (opened[i]) { let s = 0; for (const j of N[i]) s += cur[j]; ok = s === cnt[i]; }
          if (ok) { sols.push(cur.join("")); for (const i of closed) freq[i] += cur[i]; }
        }
        // cells to keep clear: one closed cell, or some of the closed cells around one open number (as a chord opens)
        const clear = new Uint8Array(n), nums = [];
        for (let i = 0; i < n; i++) if (opened[i] && N[i].some(j => !opened[j])) nums.push(i);
        if (nums.length && r() < 0.34) { const i = nums[Math.floor(r() * nums.length)]; for (const j of N[i]) if (!opened[j] && r() < 0.6) clear[j] = 1; }
        if (!clear.some(v => v)) clear[closed[Math.floor(r() * L)]] = 1;
        const want = sols.filter(k => [...k].every((v, i) => !(v === "1" && clear[i])));
        const anySafe = closed.some(i => freq[i] === 0), R = rng(seed * 31 + 7);
        const x = exactCheck(N, m, opened, cnt, 5e6, { clear, rand: R });
        st.tried++;
        if (!x.complete || x.invalid) { bad.push({ seed, why: "incomplete" }); continue; }
        if (anySafe) { st.notForced++; if (x.draw) bad.push({ seed, why: "drew though a safe cell exists" }); continue; }
        st.forced++;
        if (!want.length) { st.none++; if (x.draw) bad.push({ seed, why: "drew a layout that cannot be" }); continue; }
        if (!x.draw) { bad.push({ seed, why: "no draw" }); continue; }
        st.drawn++;
        if (!want.includes(x.draw.join(""))) { bad.push({ seed, why: "draw does not fit" }); continue; }
        if (want.length < 2 || want.length > 24 || st.even >= 60) continue;
        const seen = new Map(want.map(k => [k, 0])), reps = want.length * 60;
        for (let k = 0; k < reps; k++) { const y = exactCheck(N, m, opened, cnt, 5e6, { clear, rand: R }).draw.join(""); seen.set(y, (seen.get(y) ?? NaN) + 1); }
        let chi = 0; for (const v of seen.values()) chi += (v - 60) ** 2 / 60;
        const df = want.length - 1, z = (chi - df) / Math.sqrt(2 * df);
        st.even++; st.worst = Math.max(st.worst, z);
        if (!(z < 6) || seen.size !== want.length) bad.push({ seed, why: "uneven", z, counts: [...seen.values()] });
      }
      return { st, bad };
    """)
    st = r["st"]
    assert not r["bad"], r
    assert st["tried"] > 800 and st["drawn"] > 150 and st["none"] > 50 and st["notForced"] > 300 and st["even"] >= 40, st


def test_a_check_cut_short_gives_the_benefit_of_the_doubt(game):
    """When the edge is too tangled to check in full, the guess is treated as forced: the layout is patched around the
    cell (when the search had met an arrangement that leaves it clear), and the board is true either way."""
    r = game.run(STUCK + r"""
      const out = [];
      for (const budget of [3, 25, 120]) for (let s = 1, got = 0; s <= 200 && got < 5; s++) {
        E("exactBudget = 300000");
        if (!stuck(s)) continue;
        const full = check();
        if (!full.complete || full.safe.length) continue;
        const m = E("mines"), sure = new Set(full.mines), edge = new Set(full.odds.cells);
        const kind = got % 2 ? "sea" : "edge", pick = [...Array(n).keys()].find(i => m[i] && !sure.has(i) && edge.has(i) === (kind === "edge"));
        if (pick == null) continue;
        const clear = new Uint8Array(n); clear[pick] = 1;
        const cut = E("exactCheck")(N, 99, E("open"), E("counts"), budget, { clear, rand: Math.random });
        if (cut.complete) continue;                                   // small enough to finish even on this budget
        got++;
        const before = layout();
        E(`exactBudget = ${budget}`); E("cells")[pick].click();
        out.push({ budget, s, kind, parts: cut.part.length, over: E("over"), key: E("statusKey"), sound: sound(), opened: !!E("open")[pick], same: layout() === before });
      }
      return out;
    """)
    assert len(r) >= 10, r
    for o in r:
        assert o["sound"], o
        if o["over"]:
            assert o["key"] == "lose" and o["same"] and not o["opened"] and o["parts"] == 0, o
        else:
            assert o["key"] == "fairMoved" and o["opened"] and not o["same"] and o["parts"] >= 1, o
    assert sum(not o["over"] for o in r) >= 6 and {o["kind"] for o in r if not o["over"]} == {"edge", "sea"}, r


def test_built_boards_and_the_daily_board_are_never_changed(game):
    r = game.run(r"""
      gmode("fair");
      const mm = new Uint8Array(81); for (const i of [0, 10, 20, 30, 44, 58, 66, 71, 80]) mm[i] = 1;
      E("playEdited")(mm, 9, 9, false);
      const o = { fair: E("fairGame()"), label: $("modeLabel").textContent };
      E("cells")[44].click();                                         // nothing is open: any first cell is a guess
      o.over = E("over"); o.key = E("statusKey"); o.same = Array.from(E("mines")).join("") === Array.from(mm).join("");
      E("startDaily()"); await until(() => !E("gen"), 30000);
      o.daily = { fair: E("fairGame()"), label: $("modeLabel").textContent, noguess: T("gm").noguess };
      // an ordinary board of the mode, replayed with R: the layout it started with comes back, first cell open
      level("beginner"); E("newGame(3)"); E("cells")[40].click();
      const start = Array.from(E("mines")).join(""), N = E("nbs()");
      for (let turn = 0; turn < 500 && !E("over") && Array.from(E("mines")).join("") === start; turn++) {
        const x = E("exactCheck")(N, 10, E("open"), E("counts"), 300000);
        if (x.safe.length) { for (const j of x.safe) E(`openCell(${j})`); continue; }
        const sure = new Set(x.mines); E(`openCell(${[...Array(81).keys()].find(i => E("mines")[i] && !sure.has(i))})`);
      }
      o.moved = Array.from(E("mines")).join("") !== start;
      E("restart()");
      o.restart = { same: Array.from(E("mines")).join("") === start, open: !!E("open")[40], key: E("statusKey") };
      return o;
    """)
    assert not r["fair"] and r["over"] and r["key"] == "lose" and r["same"] and r["label"] == "편집한 판", r
    assert not r["daily"]["fair"] and r["daily"]["label"] == r["daily"]["noguess"], r
    assert r["restart"] == {"same": True, "open": True, "key": "restartedFirst"}, r


def test_hint_says_any_cell_will_do_and_that_is_true(game):
    r = game.run(STUCK + r"""
      const out = [];
      for (let s = 1; s <= 200 && out.length < 6; s++) {
        if (!stuck(s)) continue;
        const x = check();
        if (!x.complete || x.safe.length) continue;
        for (const j of x.mines) E(`toggleFlag(${j})`);
        const used0 = E("hintUsed");
        $("hint").click(); await until(() => !E("hintStop") && E("statusKey") !== "hintChecking", 8000);
        const o = { s, key: E("statusKey"), text: status(), used: !used0 && E("hintUsed"), lit: E("cells").filter(c => /hint/.test(c.className)).length, lost: 0, opened: 0 };
        // every cell the player may open now: none of them ends the game (each tried on the same position)
        const free = [...Array(n).keys()].filter(i => !E("open")[i] && !E("flags")[i]);
        for (const i of free.filter((_, k) => k % 7 === s % 7).slice(0, 25)) {
          stuck(s); for (const j of x.mines) E(`toggleFlag(${j})`);
          E("cells")[i].click(); o.opened++; if (E("over") || !E("open")[i] || !sound()) o.lost++;
        }
        out.push(o);
      }
      return { out, want: T("hintFair") };
    """)
    assert len(r["out"]) >= 5, r
    for o in r["out"]:
        assert o["key"] == "hintFair" and o["text"] == r["want"] and o["used"] and o["lit"] == 0 and o["opened"] >= 5 and o["lost"] == 0, o


@pytest.mark.parametrize("path,name", [("/", "추측 안전"), ("/en/", "Safe guessing"), ("/ja/", "推測保護"), ("/zh/", "猜测保护")])
def test_mode_is_on_the_menu_in_every_language_and_keeps_its_own_records(game, path, name):
    game.goto(path)
    r = game.run(r"""
      const b = document.querySelector('[data-gmode="fair"]'), order = [...document.querySelectorAll("[data-gmode]")].map(x => x.dataset.gmode);
      const o = { order, name: b.textContent, tip: b.title, before: b.getAttribute("aria-pressed") };
      b.click(); o.said = [E("statusKey"), status(), T("fairOn")]; level("beginner");
      o.pressed = b.getAttribute("aria-pressed"); o.stored = localStorage.getItem("minesweeper-gamemode"); o.hud = $("modeLabel").textContent;
      // the first click is kept clear as in "safe first click", and the same number gives the same board as there
      E("stats = {}; newGame(77)"); E("cells")[40].click();
      const here = Array.from(E("mines")).join(""); o.firstOpen = E("open")[40] === 1 && E("counts")[40] === 0;
      winNow();
      o.stats = JSON.parse(JSON.stringify(E("stats"))); o.key = E("statusKey");
      $("statsBtn").click(); o.title = $("t-statsTitle").textContent; o.row = $("statsTable").querySelector("tbody tr").textContent; $("statsClose").click();
      gmode("safe"); E("newGame(77)"); E("cells")[40].click(); o.sameBoard = Array.from(E("mines")).join("") === here;
      // a backup file may carry this mode's records
      o.imported = E("importStats")(JSON.stringify({ app: "MINE:D", stats: { "expert@fair": { played: 4, won: 2, best: 99.5 }, "expert@nope": { played: 1, won: 1, best: 1 } } }));
      o.keys = Object.keys(E("stats")).sort();
      gmode("fair");
      return o;
    """)
    assert r["order"] == ["random", "safe", "fair", "noguess"] and r["name"] == name and len(r["tip"]) > 20 and r["before"] == "false", r
    assert r["said"][0] == "fairOn" and r["said"][1] == r["said"][2] and len(r["said"][1]) > 20, r["said"]
    assert r["pressed"] == "true" and r["stored"] == '"fair"' and r["hud"] == name and r["firstOpen"] and r["sameBoard"], r
    assert r["key"] in ("win", "winRecord") and r["stats"]["beginner@fair"]["won"] == 1 and "beginner" not in r["stats"], r
    assert name in r["title"] and r["row"].count("1") >= 2, r
    assert r["imported"] and "expert@fair" in r["keys"] and "expert@nope" not in r["keys"], r
    game.goto(path, clear=False)
    again = game.run('return { mode: E("gameMode"), pressed: document.querySelector(\'[data-gmode="fair"]\').getAttribute("aria-pressed"), hud: $("modeLabel").textContent };')
    assert again == {"mode": "fair", "pressed": "true", "hud": name}, again
