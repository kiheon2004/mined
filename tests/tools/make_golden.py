"""Record reference boards and share codes from an older version of the game, for tests/test_compat.py.

    python tests/tools/make_golden.py            # from commit 109b1da (the version before the 2026-10 fixes)
    python tests/tools/make_golden.py --ref HEAD

Writes tests/fixtures/golden.json: for each (level, mode, game number, first cell) the SHA-256 of the mine layout
that version produced, plus share codes it encoded. Run it only when the reference version itself should change.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from harness import ROOT, Server  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

LV = {"beginner": (9, 9, 10), "intermediate": (16, 16, 40), "expert": (30, 16, 99), "nothuman": (40, 25, 200),
      "superman": (50, 32, 320), "alien": (64, 40, 512), "god": (80, 50, 760)}


def cases():
    out = []
    for key, (w, h, m) in LV.items():
        for mode in ["safe", "random"]:
            for no in [1, 4242, 999999]:
                for p in [0, w - 1, (h // 2) * w + w // 2, w * h - 1]:
                    out.append([key, w, h, m, mode, no, p])
    for key in ["beginner", "intermediate", "expert", "god"]:
        w, h, m = LV[key]
        for no in [7, 123456]:
            for p in [0, (h // 2) * w + w // 2]:
                out.append([key, w, h, m, "noguess", no, p])
    out += [["custom", 5, 5, 24, "safe", 3, 12], ["custom", 6, 6, 30, "safe", 3, 0], ["custom", 100, 60, 1200, "safe", 77, 3050]]
    return out


# Page-side: the layout for each case, as a "0101…" string. Works on both the old and the new script
# (the old one built no-guess boards from the NOGUESS_SRC string, the new one exposes the genNoGuess generator).
LAYOUTS = r"""
(cases) => cases.map(([key, w, h, m, mode, no, p]) => {
  const E = window.__ev;
  E(`cfg = { key: "${key}", w: ${w}, h: ${h}, m: ${m} }; gameMode = "${mode}"; newGame(${no});`);
  if (mode !== "noguess") { E(`placeMines(${p})`); return Array.from(E("mines")).join(""); }
  const seed = no * 7919 + p;
  if (E("typeof NOGUESS_SRC") === "string") {
    const gen = new Function("self", "postMessage", E("NOGUESS_SRC") + "; return genNoGuess;")({}, () => {});
    const r = gen(w, h, m, p, seed); return r.gaveUp ? "GAVEUP" : Array.from(r.mines).join("");
  }
  const it = E("genNoGuess")(w, h, m, p, seed, 60000); let r; do r = it.next(); while (!r.done);
  return r.value.ok ? Array.from(r.value.mines).join("") : "FAIL";
})
"""
CODE_SIZES = [[5, 5, 1], [9, 9, 2], [16, 16, 3], [30, 16, 4], [80, 50, 5], [100, 60, 6], [7, 11, 7], [13, 5, 8]]
CODES = r"""
(sizes) => sizes.map(([w, h, seed]) => { const E = window.__ev, r = E("rng")(seed), mm = new Uint8Array(w * h).map(() => r() < 0.2 ? 1 : 0); mm[0] = 1; mm[1] = 0;
  return { w, h, seed, layout: Array.from(mm).join(""), code: E("encodeBoard")(w, h, mm) }; })
"""
sha = lambda s: hashlib.sha256(s.encode()).hexdigest()


def collect(root):
    srv = Server(root)
    try:
        with sync_playwright() as p:
            br = p.chromium.launch()
            page = br.new_page()
            page.goto(srv.url + "/")
            page.wait_for_function("() => !!window.__ev")
            cs = cases()
            layouts = page.evaluate(LAYOUTS, cs)
            codes = page.evaluate(CODES, CODE_SIZES)
            br.close()
    finally:
        srv.close()
    return cs, layouts, codes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="109b1da", help="git ref of the version to record (default: before the 2026-10 fixes)")
    a = ap.parse_args()
    html = subprocess.run(["git", "-C", str(ROOT), "show", f"{a.ref}:index.html"], check=True, capture_output=True, text=True).stdout
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "index.html").write_text(html, encoding="utf-8")
        Path(tmp, "robots.txt").write_text("", encoding="utf-8")
        cs, layouts, codes = collect(Path(tmp))
    bad = [c for c, l in zip(cs, layouts) if l in ("GAVEUP", "FAIL")]
    if bad:
        sys.exit(f"reference version could not build: {bad}")
    out = {"ref": a.ref, "note": "sha256 of the mine layout ('0'/'1' per cell, row by row) for each case",
           "cases": [{"case": c, "sha256": sha(l), "mines": l.count("1")} for c, l in zip(cs, layouts)],
           "codes": [{"w": c["w"], "h": c["h"], "seed": c["seed"], "code": c["code"], "sha256": sha(c["layout"])} for c in codes]}
    path = HERE.parent / "fixtures" / "golden.json"
    path.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}: {len(out['cases'])} boards, {len(out['codes'])} share codes from {a.ref}")


if __name__ == "__main__":
    main()
