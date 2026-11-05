"""Regression tests for MINE:D. Each test drives the real page; page-side bodies use the helpers in harness.PRE."""
import json
import time

import pytest

chromium_only = pytest.mark.only_browser("chromium")


# ---------------- first click ----------------

def test_first_click_every_position_all_levels(game):
    """Safe mode keeps the clicked cell and its 8 neighbors clear, for every cell of all 7 levels."""
    out = game.run(r"""
      return E(`(() => {
        const out = {}; gameMode = "safe";
        for (const [key, l] of Object.entries(LEVELS)) {
          cfg = { key, ...l }; const n = l.w * l.h; let bad = 0;
          for (let p = 0; p < n; p++) {
            gameNo = 1000 + p; mines = new Uint8Array(n); placeMines(p);
            const N = neighbors(p); let c = 0; for (const v of mines) c += v;
            if (c !== l.m || mines[p] || N.some(j => mines[j]) || firstGuard !== N.length + 1) bad++;
          }
          out[key] = { positions: n, bad };
        }
        return out; })()`);
    """)
    assert all(v["bad"] == 0 for v in out.values()), out
    assert sum(v["positions"] for v in out.values()) == 81 + 256 + 480 + 1000 + 1600 + 2560 + 4000


def test_first_click_real_clicks_corners_edges_center(game):
    """Real clicks on corners, edge midpoints and the center open the cell and all its neighbors (safe, no-guess)."""
    out = game.run(r"""
      const out = {};
      for (const mode of ["safe", "noguess"]) {
        gmode(mode);
        for (const [key, l] of Object.entries(LV())) {
          if (mode === "noguess" && !["beginner", "intermediate", "expert", "god"].includes(key)) continue;
          level(key);
          const w = l.w, h = l.h;
          const spots = { tl: 0, tr: w - 1, bl: (h - 1) * w, br: h * w - 1, top: w >> 1, left: (h >> 1) * w, right: (h >> 1) * w + w - 1, bottom: (h - 1) * w + (w >> 1), center: (h >> 1) * w + (w >> 1) };
          for (const [name, p] of Object.entries(spots)) {
            E(`newGame(${4242 + p})`);
            E("cells")[p].click();
            assert(await until(() => E("started") || E("over"), 30000), `${mode} ${key} ${name} never started`);
            const N = E("neighbors")(p), open = E("open");
            assert(!E("over") || E("openedCount") === w * h - l.m, `${mode} ${key} ${name} lost on first click`);
            assert(open[p] && N.every(j => open[j]), `${mode} ${key} ${name} neighbors not all open`);
          }
          out[mode + ":" + key] = "ok";
        }
      }
      return out;
    """)
    assert len(out) == 11


def test_first_click_dense_custom_boards(game):
    """5×5·24 and 6×6·30: only the clicked cell can be kept clear, and the player is told so."""
    out = game.run(r"""
      gmode("safe");
      const out = {};
      for (const [w, h, m] of [[5, 5, 24], [6, 6, 30]]) {
        custom(w, h, m);
        const msgs = new Set();
        for (let p = 0; p < w * h; p++) {
          E(`newGame(${77 + p})`);
          E("cells")[p].click();
          const mines = E("mines");
          assert(!mines[p] && mines.reduce((a, b) => a + b, 0) === m, `${w}x${h} p${p}`);
          assert(E("started") && E("open")[p], `${w}x${h} p${p} not opened`);
          const guard = E("firstGuard"), area = E("neighbors")(p).length + 1;
          assert(guard === (w * h - area >= m ? area : 1), `${w}x${h} p${p} guard ${guard}`);
          if (guard === 1) msgs.add(status());
        }
        out[`${w}x${h}-${m}`] = [...msgs];
      }
      assert(out["6x6-30"].includes(T("denseFirst")), "dense message not shown");
      assert(out["5x5-24"].every(s => s.startsWith("클리어")), "5x5-24 should win at once");
      custom(5, 5, 16); E("newGame(5)"); E("cells")[12].click(); assert(E("firstGuard") === 9, "5x5-16 center guard");
      out.tooltip = document.querySelector('[data-gmode="safe"]').title;
      assert(out.tooltip.includes("클릭한 칸만"), "tooltip");
      return out;
    """)
    assert out["6x6-30"]


# ---------------- no-guess generation ----------------

def test_noguess_boards_replay_cleanly(game):
    """Every cell the solver opened by inference is truly safe, every mine it marked is a mine, and all safe cells end open."""
    out = game.run(r"""
      gmode("noguess");
      const out = [];
      for (const [key, runs] of [["beginner", 4], ["intermediate", 3], ["expert", 3], ["god", 2]]) {
        level(key);
        for (let r = 0; r < runs; r++) {
          E(`newGame(${900 + r})`);
          const l = LV()[key], p = ((r * 37) % l.h) * l.w + (r * 53) % l.w;
          E("cells")[p].click();
          assert(await until(() => E("started"), 30000), key + " not started: " + status());
          const layout = E("savedMines"), N = E("nbs()"), steps = [];
          const res = E("solveFrom")(N, l.m, layout, p, steps);
          assert(res.solved && !res.unsound, "replay not solved");
          const n = l.w * l.h, open = new Uint8Array(n);
          const cnt = i => N[i].reduce((s, j) => s + layout[j], 0);
          const flood = i => { const st = [i]; while (st.length) { const k = st.pop(); if (open[k]) continue; assert(!layout[k], "opened a mine at " + k); open[k] = 1; if (!cnt(k)) st.push(...N[k]); } };
          flood(p);
          for (const s of steps) {
            for (const j of s.mines) assert(layout[j], "claimed mine is safe: " + j);
            for (const j of s.safe) { assert(!layout[j], "claimed safe is a mine: " + j); flood(j); }
          }
          let unopened = 0; for (let i = 0; i < n; i++) if (!layout[i] && !open[i]) unopened++;
          assert(!unopened, "safe cells left closed: " + unopened);
          assert(E("open")[p] && E("firstClick") === p, "first cell not open");
          out.push({ key, p, steps: steps.length });
        }
      }
      return out;
    """)
    assert len(out) == 12


def test_noguess_timeout_starts_nothing_and_retry_uses_new_number(game):
    st = game.run(r"""
      gmode("noguess");
      E(`window.__rev = 0; window.__term = 0; { const r = URL.revokeObjectURL.bind(URL); URL.revokeObjectURL = u => { window.__rev++; r(u); };
         const t = Worker.prototype.terminate; Worker.prototype.terminate = function () { window.__term++; return t.call(this); }; }`);
      level("god");
      E("genLimitMs = 1");
      const no = E("gameNo");
      E("cells")[25 * 80 + 40].click();
      assert(E("gen"), "not generating");
      assert(await until(() => !E("gen"), 10000), "still generating");
      const st = { status: status(), started: E("started"), savedMines: E("savedMines"), stats: JSON.stringify(E("stats")), act: $("statusAct").textContent, actHidden: $("statusAct").hidden, revoked: E("window.__rev"), terminated: E("window.__term") };
      assert(st.status === T("genTimeout") && !st.started && st.savedMines === null && st.stats === "{}", "timeout state");
      assert(!st.actHidden && st.act === T("genRetry"), "retry button");
      assert(st.revoked === 1 && st.terminated === 1, "cleanup " + st.revoked + "/" + st.terminated);
      $("statusAct").click();
      assert(E("gen") && E("gameNo") !== no, "retry did not start a new number");
      assert(await until(() => !E("gen"), 10000), "retry still generating");
      st.afterRetry = { status: status(), revoked: E("window.__rev"), terminated: E("window.__term") };
      assert(st.afterRetry.revoked === 2 && st.afterRetry.terminated === 2, "cleanup 2");
      return st;
    """)
    assert st["afterRetry"]["revoked"] == 2


def test_noguess_page_watchdog_ends_silent_worker(game):
    assert game.run(r"""
      gmode("noguess");
      E(`window.__term = 0; window.Worker = class { postMessage() {} terminate() { window.__term++; } }`);
      E("genLimitMs = 50; genGraceMs = 100");
      E("cells")[40].click();
      await sleep(500);
      return status() === T("genTimeout") && !E("started") && !E("gen") && E("window.__term") === 1;
    """)


def test_noguess_worker_errors_and_bad_answers(game):
    """onerror, onmessageerror and every kind of bad answer: nothing starts, nothing is saved or counted, the worker is cleaned up."""
    out = game.run(r"""
      gmode("noguess");
      E(`{ const N = nbs(); let r = rng(5);
           for (;;) { const mm = new Uint8Array(81); let k = 0; while (k < 10) { const i = Math.floor(r() * 81); if (!mm[i] && i !== 40 && !N[40].includes(i)) { mm[i] = 1; k++; } }
                      if (!solveFrom(N, 10, mm, 40).solved) { window.__unsolvable = mm; break; } } }`);
      const out = {};
      for (const kind of ["error", "messageerror", "mineOnFirst", "wrongCount", "unsolvable", "notOk", "wrongId"]) {
        E(`window.__term = 0; window.__kind = "${kind}"; window.Worker = class {
            postMessage(job) { setTimeout(() => {
              const k = window.__kind;
              if (k === "error") this.onerror && this.onerror({ preventDefault() {} });
              else if (k === "messageerror") this.onmessageerror && this.onmessageerror({});
              else { let mines = window.__unsolvable.slice();
                     if (k === "mineOnFirst") { mines[mines.indexOf(1)] = 0; mines[job.first] = 1; }
                     if (k === "wrongCount") mines[mines.indexOf(1)] = 0;
                     this.onmessage && this.onmessage({ data: { id: k === "wrongId" ? job.id + 99 : job.id, ok: k !== "notOk", reason: "x", mines } }); }
            }, 20); }
            terminate() { window.__term++; } }`);
        E("workerBroken = false");
        E("newGame(31)");
        E("cells")[40].click();
        assert(await until(() => !E("gen"), 3000), kind + " stuck");
        const o = { status: status(), started: E("started"), savedMines: E("savedMines"), played: E("stats")["beginner@noguess"]?.played || 0, terminated: E("window.__term") };
        assert(o.status === T("genError") && !o.started && o.savedMines === null && !o.played && o.terminated === 1, kind + " " + JSON.stringify(o));
        out[kind] = "rejected";
      }
      // after a worker error the page builds boards itself
      E("workerBroken = false; window.__kind = 'error'"); E("newGame(32)"); E("cells")[40].click(); await until(() => !E("gen"), 3000);
      assert(E("workerBroken"), "workerBroken not set");
      E("newGame(33)"); E("cells")[40].click();
      assert(await until(() => E("started"), 10000), "fallback after error did not start");
      return out;
    """)
    assert len(out) == 7


def test_noguess_without_workers_runs_in_short_steps(game):
    """Worker constructor throws: the page builds the board in slices. Each generator step stays short, the board is verified."""
    res = game.run(r"""
      gmode("noguess"); level("god");
      E(`window.Worker = function () { throw new Error("blocked"); }`);
      // time every step the page runs (generator steps and verification steps)
      E(`{ const s = runSliced; runSliced = (it, ms, done, fail) => s({ next() { const t = performance.now(); const r = it.next(); (window.__steps = window.__steps || []).push(performance.now() - t); return r; } }, ms, done, fail); }`);
      const gaps = []; let last = performance.now();
      const iv = setInterval(() => { const now = performance.now(); gaps.push(now - last); last = now; }, 4);
      E("newGame(1003)");
      E("cells")[25 * 80 + 40].click();
      assert(E("gen"), "not generating");
      assert(await until(() => E("started") || !E("gen"), 60000), "fallback never finished");
      clearInterval(iv);
      assert(E("started"), "did not start: " + status());
      assert(E("solveFrom")(E("nbs()"), 760, E("savedMines"), 25 * 80 + 40).solved, "fallback layout not verified");
      const st = window.__steps.slice().sort((a, b) => b - a); gaps.sort((a, b) => b - a);
      return { steps: st.length, maxStepMs: +st[0].toFixed(1), p99StepMs: +st[Math.floor(st.length / 100)].toFixed(2), maxGapMs: Math.round(gaps[0]), p95GapMs: Math.round(gaps[Math.floor(gaps.length / 20)]) };
    """)
    print("fallback:", res)
    assert res["p99StepMs"] < 8, res      # steps sit far below the 8 ms slice target
    assert res["maxStepMs"] < 100, res    # catches a step that does real work in one go; GC pauses and a busy
                                          # machine can stretch single steps (seen up to ~75 ms in Firefox under load)


def test_noguess_cancel_and_takeovers_ignore_late_answers(game):
    out = game.run(r"""
      gmode("noguess");
      E(`window.__term = 0; window.Worker = class {
          postMessage(job) { const h = this.onmessage, it = genNoGuess(job.w, job.h, job.m, job.first, job.seed, 20000); let r; do r = it.next(); while (!r.done);
                             setTimeout(() => h && h({ data: { id: job.id, ...r.value } }), 250); }
          terminate() { window.__term++; } }`);
      const out = {};
      const cases = { cancel: () => $("statusAct").click(), newGame: () => $("newGame").click(), level: () => level("intermediate"), mode: () => gmode("safe") };
      for (const [name, act] of Object.entries(cases)) {
        gmode("noguess"); level("beginner"); E("newGame(55)");
        E("cells")[40].click();
        assert(E("gen"), name + ": not generating");
        if (name === "cancel") assert($("statusAct").textContent === T("genCancel"), "cancel button");
        act();
        await sleep(400);
        const o = { started: E("started"), gen: !!E("gen"), status: status(), opened: E("openedCount") };
        assert(!o.started && !o.gen && o.opened === 0, name + " " + JSON.stringify(o));
        out[name] = o.status;
      }
      assert(out.cancel === T("genCanceled"), "cancel message");
      gmode("noguess"); level("beginner"); E("newGame(56)"); E("cells")[40].click(); $("statusAct").click();
      E("cells")[40].click(); assert(await until(() => E("started"), 3000), "restart after cancel");
      return out;
    """)
    assert set(out) == {"cancel", "newGame", "level", "mode"}


def test_noguess_cancel_during_page_verification(game):
    """The answer is replayed on the page in slices before the game starts; cancelling then still starts nothing."""
    out = game.run(r"""
      gmode("noguess"); level("god"); E("newGame(1001)");
      // slow the page-side replay down (the worker keeps its own copy of the solver)
      E(`{ const s = solveSteps; solveSteps = function* (...a) { const it = s(...a); for (;;) { const t = performance.now(); while (performance.now() - t < 2); const r = it.next(); if (r.done) return r.value; yield; } }; }`);
      E(`{ const s = runSliced; runSliced = (...a) => { window.__slicers = (window.__slicers || 0) + 1; return s(...a); }; }`);
      E("cells")[2040].click();
      assert(await until(() => E("window.__slicers") >= 1, 30000), "verification never started");
      await sleep(30);
      const verifying = !!E("gen") && !E("started");
      $("statusAct").click();
      await sleep(1500);
      return { verifying, started: E("started"), gen: !!E("gen"), status: status() };
    """)
    assert out["verifying"] and not out["started"] and not out["gen"], out


def test_noguess_keys_during_generation(game):
    """R and H while a board is being built leave the build and its cancel button alone; N answers at once."""
    o = game.run(r"""
      gmode("noguess"); level("god"); E("newGame(1001)");
      E("cells")[2040].click();
      $("restart").click(); $("hint").click();
      const o = { gen: !!E("gen"), status: status(), cancelShown: !$("statusAct").hidden && $("statusAct").textContent === T("genCancel") };
      assert(o.gen && o.status === T("generating") && o.cancelShown, JSON.stringify(o));
      const t = performance.now(); $("newGame").click(); o.newGameMs = +(performance.now() - t).toFixed(1);
      assert(!E("gen"), "N did not cancel");
      await sleep(1500);
      assert(!E("started"), "late answer applied");
      return o;
    """)
    assert o["gen"]


# ---------------- restart ----------------

def test_restart_policy(game):
    out = game.run(r"""
      const out = {};
      for (const mode of ["safe", "noguess", "random"]) {
        gmode(mode); level("expert");
        const p = 8 * 30 + 15; let tries = 0;
        E("newGame(321)");
        E("cells")[p].click();
        await until(() => E("started"), 20000);
        while (mode === "random" && E("over") && tries++ < 50) { E(`newGame(${400 + tries})`); E("cells")[p].click(); }
        const firstOpen = Array.from(E("open")).join("");
        const m = E("mines").findIndex((v, i) => v && !E("open")[i]); E("cells")[m].click();
        assert(E("over"), "did not lose");
        $("restart").click();
        const o = { status: status(), started: E("started"), opened: E("openedCount"), sameOpening: Array.from(E("open")).join("") === firstOpen };
        out[mode] = o;
        if (mode === "random") assert(!o.started && o.opened === 0 && o.status === T("restarted"), "random restart");
        else assert(o.started && o.sameOpening && o.status === T("restartedFirst"), mode + " restart");
        if (mode === "noguess") assert(E("solveFrom")(E("nbs()"), 99, E("mines"), E("firstClick")).solved, "noguess restart not solvable");
      }
      $("editorBtn").click();
      for (const i of [0, 1, 2, 3, 4]) E("cells")[i].click();
      $("editPlay").click();
      assert(status() === T("editedNote"), "edited note");
      E("cells")[300].click();
      $("restart").click();
      assert(!E("started") && E("openedCount") === 0 && status() === T("restarted"), "edited restart");
      return out;
    """)
    assert out["safe"]["started"]


# ---------------- hints ----------------

def test_hint_wrong_flag_next_to_open_zero(game):
    o = game.run(r"""
      gmode("safe");
      for (let seed = 1; seed < 500; seed++) {
        E(`newGame(${seed}); placeMines(40);`);
        const counts = E("counts"), mines = E("mines"), N = E("neighbors");
        let z = -1, q = -1;
        for (let i = 0; i < 81 && z < 0; i++) if (!mines[i] && counts[i] === 0) { const ns = N(i).filter(j => !mines[j] && counts[j] > 0); if (ns.length) { z = i; q = ns[0]; } }
        if (z < 0) continue;
        E("begin()"); E(`toggleFlag(${q})`); E(`reveal(${z})`);
        if (E("openedCount") === 71) continue;
        const mv = E("hintMove()");
        assert(mv.type === "safe" && mv.cells.includes(q), "flagged cell not in safe set");
        $("hint").click();
        assert([T("hintWrongFlag"), T("hintSafe")].includes(status()), "status " + status());
        return { seed, zero: z, wrongFlag: q, status: status() };
      }
      throw new Error("no case found");
    """)
    assert o["wrongFlag"] >= 0


def test_engine_sound_and_exact_matches_brute_force(game):
    """deduce() never claims a wrong cell; exactCheck() finds exactly the cells brute force proves (incl. endgames)."""
    o = game.run(r"""
      const deduce = E("deduce"), exactCheck = E("exactCheck"), nbTable = E("nbTable"), rng = E("rng");
      let positions = 0, claims = 0, mismatches = [], unsound = [], dup = 0, invalid = 0;
      for (let seed = 1; seed <= 6000 && mismatches.length + unsound.length < 3; seed++) {
        const rand = rng(seed * 101), w = 4 + Math.floor(rand() * 3), h = 4 + Math.floor(rand() * 2), n = w * h, N = nbTable(w, h);
        const m = 2 + Math.floor(rand() * (n / 3));
        const layout = new Uint8Array(n); { const pool = [...Array(n).keys()]; for (let k = 0; k < m; k++) { const j = k + Math.floor(rand() * (n - k)); [pool[k], pool[j]] = [pool[j], pool[k]]; layout[pool[k]] = 1; } }
        const cnt = new Uint8Array(n); for (let i = 0; i < n; i++) if (!layout[i]) cnt[i] = N[i].reduce((s, j) => s + layout[j], 0);
        const opened = new Uint8Array(n), p = 0.3 + rand() * 0.6;
        for (let i = 0; i < n; i++) if (!layout[i] && rand() < p) opened[i] = 1;
        const hidden = []; for (let i = 0; i < n; i++) if (!opened[i]) hidden.push(i);
        if (hidden.length > 20 || hidden.length === m) continue;
        const canMine = new Uint8Array(n), canSafe = new Uint8Array(n), H = hidden.length, cur = new Uint8Array(n);
        const rec = (d, left) => {
          if (left > H - d) return;
          if (d === H) { if (left) return; for (let i = 0; i < n; i++) if (opened[i] && N[i].reduce((s, j) => s + cur[j], 0) !== cnt[i]) return;
            for (const x of hidden) (cur[x] ? canMine : canSafe)[x] = 1; return; }
          const x = hidden[d];
          cur[x] = 0; rec(d + 1, left);
          if (left) { cur[x] = 1; rec(d + 1, left - 1); cur[x] = 0; }
        };
        rec(0, m);
        positions++;
        const mine = new Uint8Array(n);
        for (let round = 0; round < 50; round++) {
          const r = deduce(N, m, opened, cnt, mine);
          if (r.invalid) { invalid++; break; }
          if (new Set(r.safe).size !== r.safe.length || new Set(r.mines).size !== r.mines.length) dup++;
          for (const j of r.safe) { claims++; if (canMine[j]) unsound.push({ seed, j, kind: "safe" }); }
          for (const j of r.mines) { claims++; if (canSafe[j]) unsound.push({ seed, j, kind: "mine" }); }
          if (r.safe.length || !r.mines.length) break;
          for (const j of r.mines) mine[j] = 1;
        }
        const x = exactCheck(N, m, opened, cnt, 1e7);
        assert(x.complete && !x.invalid, "exact incomplete on tiny board");
        const bfSafe = hidden.filter(i => !canMine[i]).join(), bfMine = hidden.filter(i => !canSafe[i]).join();
        if (x.safe.slice().sort((a, b) => a - b).join() !== bfSafe || x.mines.slice().sort((a, b) => a - b).join() !== bfMine) mismatches.push({ seed });
      }
      assert(!unsound.length, "deduce unsound " + JSON.stringify(unsound));
      assert(!mismatches.length, "exactCheck mismatch " + JSON.stringify(mismatches));
      assert(!dup && !invalid, "duplicates " + dup + " invalid " + invalid);
      return { positions, claims };
    """)
    assert o["positions"] > 5000


def test_hint_wall_pattern(game):
    seen = game.run(r"""
      const nbTable = E("nbTable"), deduce = E("deduce");
      const w = 5, h = 3, N = nbTable(w, h), n = w * h;
      const layout = new Uint8Array(n); layout[1] = 1; layout[3] = 1;
      const cnt = new Uint8Array(n); for (let i = 0; i < n; i++) if (!layout[i]) cnt[i] = N[i].reduce((s, j) => s + layout[j], 0);
      const opened = new Uint8Array(n); for (let i = w; i < n; i++) opened[i] = 1;
      const mine = new Uint8Array(n), seen = { safe: [], mines: [] };
      for (let k = 0; k < 10; k++) { const r = deduce(N, 2, opened, cnt, mine); assert(!r.invalid, "invalid"); if (!r.safe.length && !r.mines.length) break;
        seen.safe.push(...r.safe); seen.mines.push(...r.mines); r.mines.forEach(j => mine[j] = 1); r.safe.forEach(j => opened[j] = 1); }
      return { safe: seen.safe.sort().join(), mines: seen.mines.sort().join() };
    """)
    assert seen == {"safe": "0,2,4", "mines": "1,3"}


FIFTY_FIFTY = r"""
  // a 6x5 endgame where everything is open except one mine and one safe cell that no number can tell apart
  const exactCheck = E("exactCheck");
  let found = null;
  for (let seed = 1; seed < 3000 && !found; seed++) {
    E(`cfg = { key: "custom", w: 6, h: 5, m: 6 }; newGame(${seed}); placeMines(${seed % 30}); begin();`);
    const lay = E("mines");
    for (let i = 0; i < 30; i++) if (!lay[i]) E(`reveal(${i})`);
    const N = E("nbs()");
    for (let a = 0; a < 30 && !found; a++) for (const b of N[a]) {
      if (!(lay[a] && !lay[b])) continue;
      const open = E("open"); open[b] = 0;
      const x = exactCheck(N, 6, open, E("counts"), 1e6);
      const leftover = [...open].filter((v, i) => !v && !lay[i]).length;
      if (x.complete && !x.safe.length && leftover === 1) { found = { seed, a, b }; break; }
      open[b] = 1;
    }
  }
  assert(found, "no 50/50 found");
  E("openedCount = cfg.w * cfg.h - cfg.m - 1");
  { const lay = E("mines"); for (let i = 0; i < 30; i++) if (lay[i] && i !== found.a) E(`toggleFlag(${i})`); }
"""


def test_hint_guess_only_when_proven(game):
    o = game.run(FIFTY_FIFTY + r"""
      $("hint").click();
      await until(() => !E("hintStop"), 5000);
      const proven = status();
      assert(proven === T("noLogic"), "proven: " + proven);
      return { proven };
    """)
    assert o["proven"]


def test_hint_budget_cut_never_claims_a_guess(game):
    """With the search cut short by its budget, the hint says 'not sure', never 'a guess is needed' — on many positions."""
    o = game.run(FIFTY_FIFTY + r"""
      const out = { unsureTexts: new Set() };
      for (const budget of [1, 2, 5, 20]) {
        E(`exactBudget = ${budget}`); $("hint").click(); await until(() => !E("hintStop"), 5000);
        out.unsureTexts.add(status());
      }
      E("exactBudget = 300000");
      // positions where the rules are stuck (a solver run from the first click that got nowhere further):
      // cut short, the check must say "unsure"; given its full budget it may prove a guess or find a cell
      const N = E("nbTable")(30, 16), rng = E("rng");
      let checked = 0, guessWithCut = 0, unsure = 0, full = { guess: 0, safe: 0, mine: 0, unsure: 0 };
      for (let s = 1; s <= 300 && checked < 60; s++) {
        const r = rng(s), lay = new Uint8Array(480); let k = 0;
        while (k < 99) { const i = Math.floor(r() * 480); if (!lay[i] && i !== 240 && !N[240].includes(i)) { lay[i] = 1; k++; } }
        const st = E("solveFrom")(N, 99, lay, 240);
        if (st.solved) continue;
        const cnt = new Uint8Array(480); for (let i = 0; i < 480; i++) if (!lay[i]) cnt[i] = N[i].reduce((a, j) => a + lay[j], 0);
        checked++;
        const cut = E("exactCheck")(N, 99, st.opened, cnt, 3), mv = E("hintExact")(cut);
        if (!cut.complete && mv.type === "guess") guessWithCut++;
        if (mv.type === "unsure") unsure++;
        full[E("hintExact")(E("exactCheck")(N, 99, st.opened, cnt, 300000)).type]++;
      }
      return { unsureTexts: [...out.unsureTexts], checked, guessWithCut, unsure, full };
    """)
    assert o["unsureTexts"] == [game.ev('L().noLogicUnsure')], o
    assert o["checked"] > 0 and o["guessWithCut"] == 0 and o["unsure"] == o["checked"], o


def test_hint_exact_check_in_slices_matches_one_go(game):
    """The sliced exhaustive check gives exactly the one-go result, on stuck positions of a 100×60 board."""
    o = game.run(r"""
      gmode("random"); custom(100, 60, 1200);
      let compared = 0, slicesMax = 0;
      for (let s = 1; s <= 25; s++) {
        E(`newGame(${s}); placeMines(0); begin();`);
        const m = E("mines"), r = E("rng")(s * 3);
        for (let i = 0; i < m.length; i++) if (!m[i] && r() < 0.7) E(`open[${i}] = 1`);
        const args = [E("nbs()"), 1200, E("open").slice(), E("counts"), 300000];
        const one = E("exactCheck")(...args);
        let slices = 0;
        const sliced = await new Promise((res, rej) => { E("runSliced")(E("exactSteps")(...args), 8, res, rej); });
        const key = x => JSON.stringify([x.complete, x.invalid, (x.safe || []).slice().sort((a, b) => a - b), (x.mines || []).slice().sort((a, b) => a - b)]);
        assert(key(one) === key(sliced), "differs at seed " + s);
        compared++;
      }
      return { compared };
    """)
    assert o["compared"] == 25


def test_hint_check_shows_progress_and_a_move_cancels_it(game):
    o = game.run(r"""
      gmode("safe"); level("expert"); E("newGame(7)"); E("cells")[245].click();
      // pretend the rules are stuck and the exhaustive check is slow (40 steps of 6 ms)
      E(`hintRules = () => null; exactSteps = function* () { for (let i = 0; i < 40; i++) { const t = performance.now(); while (performance.now() - t < 6); yield; } return { complete: true, safe: [], mines: [] }; }`);
      $("hint").click();
      await sleep(200);
      const during = status(), running = !!E("hintStop");
      await until(() => !E("hintStop"), 5000);
      const after = status();
      // run again and make a move while it is checking: the result is dropped
      E("setStatus(null)"); $("hint").click(); await sleep(50);
      const closed = E("cells").findIndex((c, i) => !E("open")[i] && !E("mines")[i]);
      E(`toggleFlag(${closed})`);
      const cancelled = !E("hintStop"); await sleep(400);
      return { during, running, after, cancelled, afterMove: status() };
    """)
    checking = "확실한 칸을 찾는 중…"
    assert o["during"] == checking and o["running"], o
    assert o["after"] == "지금은 숫자로 확실히 알 수 있는 칸이 하나도 없어요. 추측이 꼭 필요한 상황이에요.", o
    assert o["cancelled"] and o["afterMove"] == "", o


def test_noguess_boards_won_by_hints_alone(game):
    out = game.run(r"""
      gmode("noguess");
      const out = [];
      for (const [key, no] of [["expert", 11], ["expert", 12], ["god", 14]]) {
        level(key); E(`newGame(${no})`);
        const l = LV()[key], p = (l.h >> 1) * l.w + (l.w >> 1);
        E("cells")[p].click();
        assert(await until(() => E("started"), 30000), "gen");
        let moves = 0;
        while (!E("over")) {
          const mv = E("hintMove()");
          assert(mv.type === "safe" || mv.type === "mine", key + " hint said " + mv.type + " after " + moves);
          if (mv.type === "safe") E("cells")[mv.cells[0]].click(); else E(`toggleFlag(${mv.cells[0]})`);
          moves++;
        }
        assert(E("openedCount") === l.w * l.h - l.m, "did not win");
        out.push({ key, moves });
      }
      return out;
    """)
    assert len(out) == 3


# ---------------- stats & editing ----------------

def test_stats_time_goes_to_the_running_games_entry(game):
    out = game.run(r"""
      const out = {};
      const run = async (name, act) => {
        E("stats = {}"); gmode("safe"); level("beginner"); E("newGame(5)");
        E("cells")[40].click(); assert(E("started"), "start");
        await sleep(300);
        act();
        out[name] = JSON.parse(JSON.stringify(E("stats")));
        const s = out[name].beginner;
        assert(s && s.played === 1 && s.time > 0.25 && s.time < 2, name + " time on beginner " + JSON.stringify(out[name]));
        for (const [k, v] of Object.entries(out[name])) if (k !== "beginner") assert(!v.time, name + " leaked time into " + k);
      };
      await run("modeChange", () => { E(`stats["beginner@random"] = { played: 3, won: 1, best: null, time: 0 }`); gmode("random"); });
      await run("levelChange", () => level("expert"));
      await run("editorOpen", () => $("editorBtn").click());
      await run("editorLoadCode", () => { $("editorBtn").click(); $("codeIn").value = E("encodeBoard")(10, 10, new Uint8Array(100).map((_, i) => i < 5 ? 1 : 0)); $("loadForm").requestSubmit(); });
      await run("sharedBoard", () => E(`playEdited(new Uint8Array(100).map((_, i) => i < 5 ? 1 : 0), 10, 10, true)`));
      await run("customSubmit", () => custom(10, 10, 10));
      return out;
    """)
    assert len(out) == 6


def test_stats_reset_mid_game_keeps_won_at_most_played(game):
    o = game.run(r"""
      gmode("safe"); level("beginner");
      E("newGame(8)"); E("cells")[40].click(); await sleep(150);
      $("statsBtn").click(); $("statsReset").click(); $("statsReset2").click(); $("statsClose").click();
      assert(JSON.stringify(E("stats")) === "{}", "not cleared");
      winNow();
      assert(!E("stats").beginner, "detached game was recorded");
      const seq = ["win", "lose", "win", "lose", "lose", "win"];
      for (const [k, r] of seq.entries()) {
        E(`newGame(${20 + k})`); E("cells")[40].click();
        if (r === "win") winNow(); else { const m = E("mines").findIndex((v, i) => v && !E("open")[i]); E("cells")[m].click(); }
      }
      const s = E("stats").beginner;
      assert(s.played === 6 && s.won === 3, JSON.stringify(s));
      return s;
    """)
    assert o["won"] <= o["played"]


def test_editing_blocks_restart_and_never_reuses_arrays(game):
    assert game.run(r"""
      gmode("safe"); level("beginner");
      E("newGame(3)"); E("cells")[40].click();
      $("editorBtn").click();
      assert($("restart").disabled && $("hint").disabled, "buttons not disabled");
      assert(E("savedMines") === null && E("mines") === null, "play layout still held while editing");
      level("intermediate");
      assert(E("editing") && E("editMines").length === 256 && E("cells").length === 256, "editor size");
      E("restart()"); document.dispatchEvent(new KeyboardEvent("keydown", { code: "KeyR", key: "r", bubbles: true }));
      assert(E("editing") && E("cells").length === 256 && !$("editBar").hidden, "restart changed the editor");
      E("cells")[0].click(); E("cells")[17].click();
      $("editExit").click();
      assert(!E("editing") && !$("restart").disabled && E("mines").length === 256 && E("open").length === 256, "after exit");
      $("restart").click();
      assert(status() === T("restartNone"), "restart after exit: " + status());
      $("editorBtn").click(); level("expert"); E("cells")[0].click(); $("editPlay").click();
      assert(E("cfg").key === "edited" && E("mines").length === 480 && E("savedMines").length === 480, "edited arrays");
      return true;
    """)


# ---------------- storage & share codes ----------------

NORMAL = {"beginner": {"played": 12, "won": 7, "best": 4.2, "time": 321.5}, "expert@noguess": {"played": 3, "won": 0, "best": None},
          "custom-10x10-12@random": {"played": 1, "won": 1, "best": 9.9, "time": 9.9}, "intermediate": {"played": 1, "won": 1, "best": 0}}


def test_clean_stats_repairs_only_bad_fields(game):
    rep = game.run(r"""
      const normal = arg;
      assert(JSON.stringify(E("cleanStats")(normal)) === JSON.stringify(normal), "normal data changed");
      const rep = E("cleanStats")({ beginner: { played: "7", won: 9, best: -3, time: -1 }, expert: { played: 4, won: 9, best: 12.5 }, x: 5, y: null, z: [1],
                                    god: { played: 2.5, won: 1, best: "fast", time: 1 }, g: { played: 2, won: 1, best: Infinity, time: Infinity } });
      assert(JSON.stringify(E("cleanStats")([1, 2])) === "{}" && JSON.stringify(E("cleanStats")("x")) === "{}", "non-object");
      return rep;
    """, NORMAL)
    assert rep["beginner"] == {"played": 0, "won": 0, "best": None, "time": 0}
    assert rep["expert"] == {"played": 4, "won": 4, "best": 12.5}
    assert rep["god"] == {"played": 0, "won": 0, "best": None, "time": 1}
    assert rep["g"] == {"played": 2, "won": 1, "best": None, "time": 0}
    assert not {"x", "y", "z"} & set(rep)


def test_storage_survives_reload(game):
    g = game
    g.page.evaluate("d => { localStorage.setItem('minesweeper-stats-v3', JSON.stringify(d)); localStorage.setItem('minesweeper-gamemode', JSON.stringify('noguess')); }", NORMAL)
    g.goto("/", clear=False)
    assert json.loads(g.page.evaluate("localStorage.getItem('minesweeper-stats-v3')")) == NORMAL
    assert g.ev("gameMode") == "noguess"
    g.goto("/")
    g.page.evaluate("localStorage.removeItem('minesweeper-stats-v3'); localStorage.setItem('minesweeper-stats-v2', JSON.stringify({ beginner: { played: 5, won: 2, best: 7.5, time: 80 } }))")
    g.goto("/", clear=False)
    assert json.loads(g.page.evaluate("localStorage.getItem('minesweeper-stats-v3')")) == {"beginner": {"played": 5, "won": 2, "best": None, "time": 80}}
    g.goto("/")
    g.page.evaluate("localStorage.setItem('minesweeper-stats-v3', JSON.stringify({ beginner: { played: 2, won: 5, best: 3 }, bad: 7 }))")
    g.goto("/", clear=False)
    assert json.loads(g.page.evaluate("localStorage.getItem('minesweeper-stats-v3')")) == {"beginner": {"played": 2, "won": 2, "best": 3}}
    g.goto("/")
    g.page.evaluate("localStorage.setItem('minesweeper-stats-v3', '{oops')")
    g.goto("/", clear=False)
    assert g.ev("JSON.stringify(stats)") == "{}"


def test_share_code_length_checked_first(game):
    o = game.run(r"""
      const dec = E("decodeBoard"), enc = E("encodeBoard");
      const mm = new Uint8Array(100 * 60); for (let i = 0; i < mm.length; i += 7) mm[i] = 1;
      const code = enc(100, 60, mm), back = dec(code);
      assert(back && back.w === 100 && back.mines.every((v, i) => v === mm[i]), "roundtrip");
      assert(dec(code.slice(0, -1)) === null && dec(code + "A") === null, "length");
      const t = performance.now(); const huge = dec("9x9." + "A".repeat(2000000)); const hugeMs = performance.now() - t;
      assert(huge === null && hugeMs < 50, "huge " + hugeMs);
      assert(dec("https://playmined.com/?board=" + code)?.w === 100 && dec("https://playmined.com/en/?board=" + code)?.w === 100, "link forms");
      return { codeLen: code.length, hugeMs };
    """)
    assert o["codeLen"] == 1007


# ---------------- accessibility & input ----------------

def test_grid_roles_tab_stop_and_no_label_leaks(game):
    o = game.run(r"""
      gmode("safe"); level("beginner"); E("newGame(9)");
      const board = $("board");
      assert(board.getAttribute("role") === "grid" && board.querySelectorAll('[role="row"]').length === 9 && board.querySelectorAll('[role="gridcell"]').length === 81, "roles");
      const tab0 = () => E("cells").filter(c => c.tabIndex === 0).length;
      assert(tab0() === 1, "tab stops");
      E("cells")[40].click();
      assert(tab0() === 1 && E("cells")[40].tabIndex === 0, "tab after click");
      const mines = E("mines"), cs = E("L().cs");
      const leaks = E("cells").filter((c, i) => mines[i] && !c.getAttribute("aria-label").endsWith(cs.closed)).length;
      assert(!leaks, "label leak " + leaks);
      return { sample: E("cells")[40].getAttribute("aria-label") };
    """)
    assert o["sample"].startswith("5행 5열")


def test_keyboard_arrows_enter_space_and_dialog_focus(game):
    p = game.page
    game.run('gmode("safe"); E("newGame(10)"); E("focusCell(0, true)");')
    act = lambda: p.evaluate("document.activeElement.dataset.i === undefined ? null : +document.activeElement.dataset.i")
    seq = []
    for k in ["ArrowRight", "ArrowRight", "ArrowDown", "End", "Home", "ArrowLeft"]:
        p.keyboard.press(k); seq.append(act())
    p.keyboard.press("ArrowUp"); p.keyboard.press("ArrowUp"); seq.append(act())
    assert seq == [1, 2, 11, 17, 9, 9, 0], seq
    assert game.ev("cells.filter(c => c.tabIndex === 0).length") == 1
    ring = p.evaluate("getComputedStyle(document.activeElement).outlineStyle + ' ' + document.activeElement.matches(':focus-visible')")
    assert ring == "solid true", ring
    for _ in range(4):
        p.keyboard.press("ArrowDown"); p.keyboard.press("ArrowRight")
    assert act() == 40
    p.keyboard.press("Enter")
    assert game.ev("started") and game.ev("openedCount") > 0
    tgt = p.evaluate("(() => { const o = window.__ev('open'); return window.__ev('cells').findIndex((c, i) => !o[i]); })()")
    game.ev(f"focusCell({tgt}, true)")
    p.keyboard.press("Space")
    assert game.ev(f"flags[{tgt}]") == 1
    p.keyboard.press("s")
    inside = []
    for _ in range(5):
        p.keyboard.press("Tab"); inside.append(p.evaluate("document.activeElement.closest('#statsDlg') !== null"))
    p.keyboard.press("Shift+Tab"); inside.append(p.evaluate("document.activeElement.closest('#statsDlg') !== null"))
    assert all(inside) and p.evaluate("document.getElementById('menu').inert && document.getElementById('stage').getAttribute('aria-hidden') === 'true'")
    p.keyboard.press("Escape")
    assert p.evaluate("document.getElementById('statsDlg').hidden && +document.activeElement.dataset.i") == tgt
    assert not p.evaluate("document.getElementById('menu').inert || document.getElementById('stage').hasAttribute('aria-hidden')")
    p.keyboard.press("s")
    p.click("#statsReset")
    assert p.evaluate("document.activeElement.id") == "statsReset2"
    p.click("#statsReset2")
    assert p.evaluate("document.activeElement.id") == "statsReset"
    p.keyboard.press("Escape")


def test_touch_open_flag_switch(browser, server, browser_name):
    """Touch screens: the open/flag switch shows, taps flag or open; on Chromium a drag over the board scrolls and opens nothing."""
    from harness import Game
    opts = {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 3, "has_touch": True}
    if browser_name != "firefox":
        opts["is_mobile"] = True
    ctx = browser.new_context(**opts)
    try:
        g = Game(ctx.new_page(), server.url).goto("/")
        r = g.run(r"""
          gmode("safe"); E("newGame(12)");
          return { shown: getComputedStyle($("touchMode")).display, ta: getComputedStyle(E("cells")[0]).touchAction };
        """)
        assert r["shown"] != "none" and r["ta"] == "manipulation", r
        box = lambda i: g.page.evaluate(f"(() => {{ const r = window.__ev('cells')[{i}].getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; }})()")
        g.page.tap('[data-tm="flag"]')
        x, y = box(0); g.page.touchscreen.tap(x, y)
        assert g.ev("flags[0]") == 1 and not g.ev("started")
        g.page.tap('[data-tm="open"]')
        x, y = box(40); g.page.touchscreen.tap(x, y)
        assert g.ev("started")
        if browser_name == "chromium":
            g.run('level("expert"); E("newGame(13)"); window.scrollTo(0, 0); document.body.scrollTop = 0;')
            x, y = box(100)
            before = g.page.evaluate("[window.scrollY, document.body.scrollTop]")
            cdp = ctx.new_cdp_session(g.page)
            cdp.send("Input.synthesizeScrollGesture", {"x": int(x), "y": int(y), "yDistance": -300, "gestureSourceType": "touch", "speed": 800})
            time.sleep(0.4)
            after = g.page.evaluate("[window.scrollY, document.body.scrollTop]")
            assert after != before and g.ev("openedCount") == 0, (before, after)
    finally:
        ctx.close()


@chromium_only
def test_accessibility_tree_names(game, page):
    """Chromium's real accessibility tree: grid > row > gridcell, with names; closed mine cells read as closed."""
    game.run('gmode("safe"); E("newGame(15)"); E("cells")[40].click();')
    cdp = page.context.new_cdp_session(page)
    nodes = cdp.send("Accessibility.getFullAXTree")["nodes"]
    roles = {}
    for n in nodes:
        roles.setdefault(n.get("role", {}).get("value"), []).append(n.get("name", {}).get("value"))
    board_rows = [x for x in roles.get("row", []) if "1열," in x]   # the stats and guide tables have rows too
    assert len(roles.get("gridcell", [])) == 81 and len(board_rows) == 9 and "지뢰판" in roles.get("grid", [])
    names = roles["gridcell"]
    closed = sum(1 for x in names if x.endswith("닫힘"))
    mines_closed = game.ev("mines.reduce((a, v, i) => a + (v && !open[i] ? 1 : 0), 0)")
    assert closed >= mines_closed and not any("지뢰" in x for x in names)


def test_aria_model_all_browsers(game):
    """Playwright's computed ARIA model (the same algorithm in every engine, not the engine's own tree):
    grid "지뢰판" > rows > gridcells named by position and state, nothing revealing a hidden mine."""
    game.run('gmode("safe"); E("newGame(15)"); E("cells")[40].click();')
    snap = game.page.locator("#board").aria_snapshot()
    lines = [x.strip() for x in snap.splitlines()]
    assert lines[0] == '- grid "지뢰판":'
    cells = [x for x in lines if x.startswith("- gridcell")]
    rows = [x for x in lines if x.startswith("- row")]
    assert len(cells) == 81 and len(rows) == 9
    assert '- gridcell "1행 1열, 닫힘"' in cells and not any("지뢰" in x for x in cells)


# ---------------- pages ----------------

def test_language_pages_seo_and_play(game):
    import re
    from harness import ROOT
    exp = {"ko": "https://playmined.com/", "en": "https://playmined.com/en/", "ja": "https://playmined.com/ja/", "zh": "https://playmined.com/zh/"}
    scripts = set()
    for lang, sub in [("ko", ""), ("en", "en"), ("ja", "ja"), ("zh", "zh")]:
        s = (ROOT / sub / "index.html").read_text(encoding="utf-8")
        assert re.search(r'<link rel="canonical" href="([^"]+)">', s).group(1) == exp[lang]
        hre = dict(re.findall(r'<link rel="alternate" hreflang="([^"]+)" href="([^"]+)">', s))
        assert hre == {"ko": exp["ko"], "en": exp["en"], "ja": exp["ja"], "zh": exp["zh"], "x-default": exp["ko"]}
        ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', s, re.S).group(1))
        assert ld["@graph"][0]["url"] == exp[lang] and ld["@graph"][0]["inLanguage"] == lang and ld["@graph"][1]["url"] == exp[lang]
        assert f'lang="{lang}" data-page-lang="{lang}"' in s
        scripts.add(s.split("<script>", 1)[1])
    assert len(scripts) == 1, "game scripts differ between language pages: run python3 build_langs.py"
    for path, word in [("/en/", "Row 5"), ("/ja/", "5行5列"), ("/zh/", "第5行第5列")]:
        game.goto(path)
        r = game.run(r"""gmode("noguess"); E("cells")[40].click(); await until(() => E("started"), 10000);
                         return { started: E("started"), label: E("cells")[40].getAttribute("aria-label") };""")
        assert r["started"] and r["label"].startswith(word), r
