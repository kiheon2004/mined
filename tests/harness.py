"""Test plumbing shared by the tests and tools: serve the repo over http and expose the game's internals.

The game runs inside one IIFE. When this server hands out an index.html it inserts
`window.__ev = s => eval(s)` just before the IIFE closes, so tests can read and call the
closure's state and functions with a direct eval. The files on disk are never changed.
"""
import functools
import http.server
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # the repository root (the published site)
HOOK = "\n  window.__ev = s => eval(s);\n})();\n</script>"
TAIL = "})();\n</script>"


def inject(html: str) -> str:
    k = html.rfind(TAIL)
    if k < 0:
        raise RuntimeError("game script end not found; did the IIFE ending change?")
    return html[:k] + HOOK + html[k + len(TAIL):]


class _Handler(http.server.SimpleHTTPRequestHandler):
    root = ROOT

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(self.root), **kw)

    def log_message(self, *a):
        pass

    def send_head(self):
        path = Path(self.translate_path(self.path))
        if path.is_dir():
            if not self.path.split("?")[0].endswith("/"):
                return super().send_head()          # redirect /en -> /en/
            path = path / "index.html"
        if path.suffix == ".html" and path.is_file():
            body = inject(path.read_text(encoding="utf-8")).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            import io
            return io.BytesIO(body)
        return super().send_head()


class _Httpd(http.server.ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
            return          # the browser left the page before a file was fully sent: nothing to report
        super().handle_error(request, client_address)


class Server:
    """http://127.0.0.1:<port>/ serving `root` (default: this repo) with the test hook injected."""

    def __init__(self, root: Path = ROOT):
        handler = type("H", (_Handler,), {"root": Path(root)})
        self.httpd = _Httpd(("127.0.0.1", 0), handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()


# Prelude for page-side test code: helpers every test body can use.
PRE = r"""
const E = window.__ev, sleep = ms => new Promise(r => setTimeout(r, ms)), $ = id => document.getElementById(id);
const until = async (f, ms = 30000) => { const t = performance.now(); while (!f()) { if (performance.now() - t > ms) return false; await sleep(5); } return true; };
const assert = (c, msg) => { if (!c) throw new Error("assert: " + msg); };
const status = () => $("status").textContent;
const T = k => E(`L()[${JSON.stringify(k)}]`);
const level = k => document.querySelector(`[data-level="${k}"]`).click();
const gmode = k => document.querySelector(`[data-gmode="${k}"]`).click();
const LV = () => E("LEVELS");
const custom = (w, h, m) => { level("custom"); $("cw").value = w; $("ch").value = h; $("cm").value = m; $("custom").requestSubmit(); };
// win the running game straight from the true layout (test shortcut)
const winNow = () => { const m = E("mines"); for (let i = 0; i < m.length; i++) if (!m[i] && !E("open")[i]) E(`reveal(${i})`); E("checkWin()"); };
"""


class Game:
    """A Playwright page pointed at the served site, with helpers for page-side test code."""

    def __init__(self, page, base_url):
        self.page, self.base = page, base_url

    def goto(self, path="/", clear=True):
        if clear:
            self.page.goto(self.base + "/robots.txt")
            self.page.evaluate("localStorage.clear()")
        # wait for the document and the game script, not the "load" event: that also waits for the web fonts
        # from fonts.googleapis.com, so a slow network would fail the test without anything wrong in the game
        self.page.goto(self.base + path, wait_until="domcontentloaded")
        self.page.wait_for_function("() => !!window.__ev")
        return self

    def run(self, body, arg=None):
        """Run an async JS function body (with PRE helpers; `arg` is available as `arg`) and return its value."""
        return self.page.evaluate("async (arg) => {" + PRE + body + "}", arg)

    def ev(self, expr):
        return self.page.evaluate("s => window.__ev(s)", expr)
