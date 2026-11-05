"""Measure MINE:D on big boards with real input: input-to-paint latency, and (Chromium) where the main thread spends it.

    python tests/tools/perf.py                                  # this checkout, Chromium, 15 runs per scenario
    python tests/tools/perf.py --cpu 4 --cpu 6                  # also with the CPU slowed 4x and 6x (Chromium emulation)
    python tests/tools/perf.py --mobile --cpu 4                 # phone-sized touch viewport + CPU 4x (emulation, not a phone)
    python tests/tools/perf.py --browser firefox --browser webkit
    python tests/tools/perf.py --compare old=/path/to/old/site  # A/B: each run alternates between versions (same load)

An older version to compare against can be extracted with:  git archive 109b1da | tar -x -C /tmp/old

Per scenario and run:
  input_to_paint  input event timestamp -> first frame after the handlers ran (rAF, then one task); all engines
  event_timing    PerformanceEventTiming duration (input -> next paint, 8 ms steps). Entries under 16 ms are not
                  reported, so 16 means "16 or less". Where the engine supports Event Timing (Chromium, Firefox, WebKit 26)
  longest_task    longest main-thread task in the run (Long Tasks API, >= 50 ms; 0 = none). Chromium
  main_script / main_style / main_layout / main_paint
                  main-thread time in the run's window from a Chrome trace (paint = pre-paint, paint, layerize,
                  commit; rasterization runs on other threads and is not included). Chromium
  time_to_start   no-guess scenarios: click until the game has started
Prints min / median / p90 / max per version and writes the raw runs to tests/results/ (git-ignored).
"""
import argparse
import collections
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from harness import ROOT, Game, Server  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

PROBE = r"""
(() => {
  if (window.__perf) return;
  const P = window.__perf = { inputs: [], events: [], tasks: [] };
  // WebKit stamps automated input on another clock; when the stamp is not page time, fall back to the moment the
  // listener runs (then input delay before the first listener is not counted)
  const stamp = e => e.timeStamp >= 0 && e.timeStamp <= performance.now() ? e.timeStamp : performance.now();
  P.eventTiming = typeof PerformanceEventTiming === "function";
  for (const type of ["pointerdown", "click", "keydown"]) document.addEventListener(type, e => {
    const rec = { type, t: stamp(e), paint: null };
    P.inputs.push(rec);
    requestAnimationFrame(() => { const ch = new MessageChannel(); ch.port1.onmessage = () => { rec.paint = performance.now(); }; ch.port2.postMessage(0); });
  }, true);
  try { new PerformanceObserver(l => { for (const e of l.getEntries()) P.events.push({ name: e.name, dur: e.duration }); })
          .observe({ type: "event", durationThreshold: 16, buffered: false }); } catch {}
  try { new PerformanceObserver(l => { for (const e of l.getEntries()) P.tasks.push(e.duration); }).observe({ type: "longtask", buffered: false }); } catch {}
})()
"""
SETTLE = "new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 60))))"
MAIN = {"FunctionCall": "script", "EventDispatch": "script", "TimerFire": "script", "FireAnimationFrame": "script", "EvaluateScript": "script",
        "UpdateLayoutTree": "style", "Layout": "layout", "PrePaint": "paint", "Paint": "paint", "Layerize": "paint", "Commit": "paint"}
INPUTS = ("click", "pointerdown", "pointerup", "keydown", "mousedown", "mouseup")
BOARDS = {"80×50": (80, 50, 760), "100×60": (100, 60, 1200), "100×60·1": (100, 60, 1)}


class Version:
    """One version of the site in its own tab."""

    def __init__(self, label, ctx, server, browser_name):
        self.label, self.name, self.k = label, browser_name, 0
        self.page = ctx.new_page()
        self.page.set_default_timeout(120_000)
        self.game = Game(self.page, server.url)

    def ev(self, s):
        return self.page.evaluate("s => window.__ev(s)", s)

    def fresh(self, board):
        self.game.goto("/")
        self.page.evaluate(PROBE)
        self.to_board(board)

    def to_board(self, board):
        w, h, m = board
        if (w, h, m) == (80, 50, 760):
            self.page.click('[data-level="god"]')
        else:
            p = self.page
            p.click('[data-level="custom"]'); p.fill("#cw", str(w)); p.fill("#ch", str(h)); p.fill("#cm", str(m)); p.click("#t-start")

    def cell(self, i):
        return self.page.locator(f'#board .cell[data-i="{i}"]')

    def mode(self, m):
        self.ev(f'document.querySelector(\'[data-gmode="{m}"]\').click()')

    def measure(self, act):
        p = self.page
        p.evaluate("window.__perf.inputs.length = 0; window.__perf.events.length = 0; window.__perf.tasks.length = 0")
        self.k += 1
        mark = f"{self.label}-w{self.k}"
        p.evaluate(f"performance.mark('{mark}s')")
        t0 = time.perf_counter()
        act()
        p.evaluate(SETTLE)
        wall = (time.perf_counter() - t0) * 1000 - 60
        p.evaluate(f"performance.mark('{mark}e')")
        d = p.evaluate("window.__perf")
        lat = [x["paint"] - x["t"] for x in d["inputs"] if x["paint"] is not None]
        ev = [x["dur"] for x in d["events"] if x["name"] in INPUTS]
        return {"mark": mark, "input_to_paint": max(lat) if lat else None,
                "event_timing": max(ev) if ev else (16 if d.get("eventTiming") else None),
                "longest_task": max(d["tasks"], default=0) if self.name == "chromium" else None, "wall": wall}


def center(board):
    w, h, _ = board
    return (h // 2) * w + w // 2


def closed_mine(v):
    return v.ev("(() => { for (let i = cells.length - 1; i >= 0; i--) if (mines[i] && !open[i]) return i; return -1; })()")


def scenario_list():
    """(name, board label, setup(v, k), act(v), after(v) or None); setup runs before every measured act."""
    out = []
    for bl in ["80×50", "100×60"]:
        board = BOARDS[bl]
        c = center(board)
        out.append(("build board (level change)", bl, lambda v, k: (v.page.click('[data-level="beginner"]'), v.ev("startZoom()")),
                    lambda v, board=board: v.to_board(board), None))
        out.append(("new game (N key)", bl, lambda v, k: v.page.evaluate("document.activeElement.blur()"), lambda v: v.page.keyboard.press("n"), None))
        out.append(("first click", bl, lambda v, k: (v.mode("safe"), v.ev(f"newGame({100 + k})")), lambda v, c=c: v.cell(c).click(), None))
        out.append(("hint", bl, lambda v, k, c=c: (v.mode("safe"), v.ev(f"newGame({100 + k})"), v.cell(c).click(), v.ev("hintUsed = false")),
                    lambda v: v.page.click("#hint"), None))
        st = {}

        def lose_setup(v, k, c=c, st=st):
            v.mode("safe"); v.ev(f"newGame({100 + k})"); v.cell(c).click(); st[v.label] = closed_mine(v)
        out.append(("loss: reveal all mines", bl, lose_setup, lambda v, st=st: v.cell(st[v.label]).click(), None))
        for fallback in (False, True):
            def ng_setup(v, k, fallback=fallback):
                v.mode("noguess"); v.ev(f"newGame({2000 + k})")
                if fallback:
                    v.ev('window.Worker = function () { throw new Error("blocked"); }')

            def ng_act(v, c=c):
                v.cell(c).click()
                v.page.wait_for_function("() => window.__ev('started') || !window.__ev(\"typeof gen === 'undefined' ? generating : gen\")", timeout=120_000)
            out.append((f"no-guess: click → game starts ({'no worker' if fallback else 'worker'})", bl, ng_setup, ng_act, None))

        def stats_after(v):
            v.page.keyboard.press("Escape")
            v.ev("typeof cancelGen === 'function' ? cancelGen() : 0")

        def busy_setup(v, k, c=c):
            v.mode("noguess"); v.ev(f"newGame({3000 + k})")
            v.ev('window.Worker = function () { throw new Error("blocked"); }')
            v.cell(c).click(no_wait_after=True)
            time.sleep(0.05)
        out.append(("stats dialog click, idle", bl, lambda v, k: (v.mode("safe"), v.ev(f"newGame({3000 + k})")), lambda v: v.page.click("#statsBtn"), stats_after))
        out.append(("stats dialog click while building (no worker)", bl, busy_setup, lambda v: v.page.click("#statsBtn", no_wait_after=True), stats_after))
    out.append(("one click opens ~6000 cells", "100×60·1", lambda v, k: (v.mode("safe"), v.ev(f"newGame({k + 3})")), lambda v: v.cell(3050).click(), None))
    return out


def summarize(vals):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    pct = lambda q: vals[min(len(vals) - 1, int(round(q * (len(vals) - 1))))]
    return {"min": vals[0], "median": statistics.median(vals), "p90": pct(0.9), "max": vals[-1], "n": len(vals)}


def trace_breakdown(path):
    """Main-thread time per measured window: {mark: Counter(script, style, layout, paint)}."""
    ev = json.load(open(path))["traceEvents"]
    mains = {(e["pid"], e["tid"]) for e in ev if e.get("name") == "thread_name" and e.get("args", {}).get("name") == "CrRendererMain"}
    marks = {e["name"]: (e["ts"], e["pid"]) for e in ev if e.get("cat", "").startswith("blink.user_timing") and "-w" in e.get("name", "")}
    windows = {n[:-1]: (pid, ts, marks[n[:-1] + "e"][0]) for n, (ts, pid) in marks.items() if n.endswith("s") and n[:-1] + "e" in marks}
    by_pid = collections.defaultdict(list)
    for x in ev:
        if x.get("ph") == "X" and (x["pid"], x["tid"]) in mains and x.get("name") in MAIN:
            by_pid[x["pid"]].append(x)
    out = collections.defaultdict(collections.Counter)
    for mark, (pid, s, e) in windows.items():
        for x in by_pid[pid]:
            if s <= x["ts"] <= e:
                out[mark][MAIN[x["name"]]] += x.get("dur", 0) / 1000
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--browser", action="append", choices=["chromium", "firefox", "webkit"])
    ap.add_argument("--cpu", action="append", type=float, help="Chromium CPU slowdown (emulation); repeatable; 1 = none")
    ap.add_argument("--runs", type=int, default=15)
    ap.add_argument("--mobile", action="store_true", help="390x844 touch viewport, DPR 3 (emulation)")
    ap.add_argument("--only", default="", help="only scenarios whose name contains this")
    ap.add_argument("--compare", action="append", default=[], metavar="LABEL=DIR", help="another version of the site to alternate with")
    ap.add_argument("--no-current", action="store_true", help="leave out this checkout")
    a = ap.parse_args()
    versions = ([] if a.no_current else [("current", ROOT)]) + [(x.split("=", 1)[0], Path(x.split("=", 1)[1]).resolve()) for x in a.compare]
    servers = {label: Server(root) for label, root in versions}
    (ROOT / "tests" / "results").mkdir(exist_ok=True)
    report = []
    try:
        with sync_playwright() as pw:
            for bname in a.browser or ["chromium"]:
                for cpu in (a.cpu or [1]) if bname == "chromium" else [1]:
                    br = getattr(pw, bname).launch()
                    opts = {"viewport": {"width": 1400, "height": 900}}
                    if a.mobile:
                        opts = {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 3, "has_touch": True,
                                **({"is_mobile": True} if bname != "firefox" else {})}
                    setup_label = f"{bname}{' cpu×%g (emulated)' % cpu if cpu != 1 else ''}{' mobile viewport (emulated)' if a.mobile else ''}"
                    ctx = br.new_context(**opts)
                    vs = [Version(label, ctx, servers[label], bname) for label, _ in versions]
                    if bname == "chromium" and cpu != 1:
                        for v in vs:
                            ctx.new_cdp_session(v.page).send("Emulation.setCPUThrottlingRate", {"rate": cpu})
                    for name, bl, setup, act, after in scenario_list():
                        full = f"{bl} {name}"
                        if a.only and a.only not in full:
                            continue
                        for v in vs:
                            v.fresh(BOARDS[bl])
                        runs = a.runs if "no-guess" not in name else max(4, a.runs // 2)
                        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
                        if bname == "chromium":
                            br.start_tracing(page=vs[0].page, path=tmp, categories=["devtools.timeline", "blink.user_timing"])
                        rows = collections.defaultdict(list)
                        failed = {}
                        for k in range(runs):
                            for v in (vs if k % 2 == 0 else vs[::-1]):   # alternate who goes first
                                if v.label in failed:
                                    continue
                                try:
                                    v.page.bring_to_front()
                                    setup(v, k)
                                    v.page.evaluate(SETTLE)
                                    row = v.measure(lambda: act(v))
                                    if "game starts" in name:
                                        row["time_to_start"] = row["wall"]
                                    if after:
                                        after(v)
                                    rows[v.label].append(row)
                                except Exception as e:   # e.g. a version that blocks its page for minutes
                                    failed[v.label] = f"run {k + 1}: {type(e).__name__}: {str(e).splitlines()[0][:160]}"
                        for lab, why in failed.items():
                            print(f"  {lab:>8s} FAILED {why}")
                            report.append({"setup": setup_label, "version": lab, "scenario": full, "failed": why})
                        if bname == "chromium":
                            br.stop_tracing()
                            bd = trace_breakdown(tmp)
                            for lab in rows:
                                for row in rows[lab]:
                                    row.update({f"main_{key}": val for key, val in bd.get(row["mark"], {}).items()})
                        Path(tmp).unlink(missing_ok=True)
                        print(f"\n[{setup_label}] {full}   (min / median / p90 / max ms)")
                        for lab in rows:
                            stats = {}
                            for key in ["input_to_paint", "event_timing", "longest_task", "main_script", "main_style", "main_layout", "main_paint", "time_to_start"]:
                                s = summarize([r.get(key) for r in rows[lab]])
                                if s:
                                    stats[key] = s
                                    print(f"  {lab:>8s} {key:15s} {s['min']:7.1f} {s['median']:7.1f} {s['p90']:7.1f} {s['max']:7.1f}  n={s['n']}")
                            report.append({"setup": setup_label, "version": lab, "scenario": full, "stats": stats, "runs": rows[lab]})
                    br.close()
    finally:
        for s in servers.values():
            s.close()
        out = ROOT / "tests" / "results" / f"perf-{time.strftime('%Y%m%d-%H%M%S')}.json"
        out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")   # also what was measured before a crash
        print("\nraw results:", out.relative_to(ROOT))


if __name__ == "__main__":
    main()
