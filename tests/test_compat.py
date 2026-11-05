"""Compatibility with the version before the 2026-10 fixes (tests/fixtures/golden.json, made by tools/make_golden.py):
same game number + first cell -> same board, and share codes read and write the same."""
import hashlib
import json
from pathlib import Path

GOLDEN = json.loads((Path(__file__).resolve().parent / "fixtures" / "golden.json").read_text(encoding="utf-8"))
sha = lambda s: hashlib.sha256(s.encode()).hexdigest()

LAYOUTS = r"""
(cases) => cases.map(([key, w, h, m, mode, no, p]) => {
  const E = window.__ev;
  E(`cfg = { key: "${key}", w: ${w}, h: ${h}, m: ${m} }; gameMode = "${mode}"; newGame(${no});`);
  if (mode !== "noguess") { E(`placeMines(${p})`); return Array.from(E("mines")).join(""); }
  const it = E("genNoGuess")(w, h, m, p, no * 7919 + p, 60000); let r; do r = it.next(); while (!r.done);
  return r.value.ok ? Array.from(r.value.mines).join("") : "FAIL";
})
"""


def test_same_number_same_board(game):
    cases = [c["case"] for c in GOLDEN["cases"]]
    layouts = game.page.evaluate(LAYOUTS, cases)
    diff = [c for c, g, l in zip(cases, GOLDEN["cases"], layouts) if sha(l) != g["sha256"]]
    assert not diff, f"{len(diff)} of {len(cases)} boards changed, e.g. {diff[:3]}"
    assert sum(1 for c in cases if c[4] == "noguess") == 16


def test_share_codes_unchanged(game):
    for c in GOLDEN["codes"]:
        got = game.page.evaluate("""([w, h, seed]) => { const E = window.__ev, r = E("rng")(seed), mm = new Uint8Array(w * h).map(() => r() < 0.2 ? 1 : 0); mm[0] = 1; mm[1] = 0;
            const code = E("encodeBoard")(w, h, mm), back = E("decodeBoard")(code);
            return { code, layout: Array.from(mm).join(""), back: back && Array.from(back.mines).join("") }; }""", [c["w"], c["h"], c["seed"]])
        assert got["code"] == c["code"], "encoding changed"
        assert sha(got["layout"]) == c["sha256"] and got["back"] == got["layout"]
        for form in [c["code"], "https://playmined.com/?board=" + c["code"], "https://playmined.com/ja/?board=" + c["code"]]:
            dec = game.page.evaluate("s => { const b = window.__ev('decodeBoard')(s); return b && [b.w, b.h, Array.from(b.mines).join('')]; }", form)
            assert dec and dec[0] == c["w"] and dec[1] == c["h"] and sha(dec[2]) == c["sha256"], form


def test_shared_link_opens_the_board(game):
    c = GOLDEN["codes"][1]
    game.goto("/?board=" + c["code"])
    r = game.run("""return { key: E("cfg").key, w: E("cfg").w, layout: Array.from(E("mines")).join(""), status: status() };""")
    assert r["key"] == "edited" and r["w"] == c["w"] and sha(r["layout"]) == c["sha256"]
    assert r["status"] == game.ev("L().sharedBoard")
