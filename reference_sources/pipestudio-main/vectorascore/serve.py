"""Stage-by-stage review server (stdlib only).

    python -m vectorascore.serve            # http://127.0.0.1:8770

Upload a PDF, the pipeline runs in a background thread, the page shows every
stage's output as its own layer and lets the reviewer record what is missing
or wrong into feedback/<sheet>.json.
"""
import json
import gzip
import hashlib
import os
import re
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
DEBUG = os.environ.get("PIPE_STUDIO_DEBUG", os.path.join(ROOT, "debug"))
UPLOADS = os.path.join(ROOT, "uploads")
FEEDBACK = os.path.join(ROOT, "feedback")
JOBS = {}          # sheet -> {"stage": int, "name": str, "status": running|done|error, "error": str}
# buckets a later stage reads (assemble: pipe/circle/tick/coupling/leader/leader_in_wall,
# associate: leader/leader_wall_label); every other bucket is noise from stage 5 on
USED_BUCKETS = {"pipe", "circle", "tick", "coupling", "leader", "leader_in_wall", "leader_wall_label"}
LOCK = threading.Lock()


def load_dotenv():
    p = os.path.join(ROOT, ".env")
    if not os.path.exists(p):
        return
    for line in open(p):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def _pdf_for(sheet):
    for d in (UPLOADS, os.path.join(ROOT, "clean")):
        p = os.path.join(d, sheet + ".pdf")
        if os.path.exists(p):
            return p
    return None


def _run_job(sheet, upto, use_llm, style_id="style-1"):
    from studio.engine import analyze
    pdf = _pdf_for(sheet)

    def progress(i, name):
        with LOCK:
            JOBS[sheet] = {"stage": i, "name": name, "status": "running"}
    try:
        from studio.storage import drawing_lock
        with drawing_lock(os.path.join(DEBUG, sheet)):
            analyze(pdf, os.path.join(DEBUG, sheet), style_id=style_id, binding="astra" if use_llm else "preview", progress=progress, studio=True,
                    fallback="style-1")                       # an unknown style runs as style-1 and is flagged, never refused
        with LOCK:
            JOBS[sheet] = {"stage": 9, "name": "done", "status": "done"}
    except Exception as e:
        traceback.print_exc()
        with LOCK:
            JOBS[sheet] = {"stage": JOBS.get(sheet, {}).get("stage", 0), "name": "error", "status": "error",
                           "error": f"{type(e).__name__}: {e}"}


def _start(sheet, upto=9, use_llm=True, style_id="style-1"):
    with LOCK:
        if JOBS.get(sheet, {}).get("status") == "running":
            return False
        JOBS[sheet] = {"stage": 0, "name": "queued", "status": "running"}
    threading.Thread(target=_run_job, args=(sheet, upto, use_llm, style_id), daemon=True).start()
    return True


def _keys():
    return os.environ.get("REVIEW_KEY", ""), os.environ.get("ADMIN_KEY", "")


class H(BaseHTTPRequestHandler):
    def end_headers(self):
        # Authenticated drawings and UI must not be reused by shared caches.
        self.send_header("Cache-Control", "private, no-store")
        super().end_headers()

    def do_GET(self):
        self._guard(self._get)

    def do_POST(self):
        self._guard(self._post)

    def _guard(self, operation):
        try:
            operation()
        except (ValueError, KeyError, TypeError) as exc:
            self._json({"error": str(exc)}, 400)
        except FileNotFoundError:
            self._json({"error": "Not found"}, 404)
        except Exception:
            traceback.print_exc()
            self._json({"error": "Operation failed; see server logs"}, 500)

    def _role(self, q):
        review, admin = _keys()
        if not review and not admin:
            return "admin"
        # the owner's own browser: a loopback request that did not come through the Cloudflare tunnel
        # (cloudflared adds Cf-Connecting-Ip to everything it forwards, and it too connects from loopback)
        if self.client_address[0] in ("127.0.0.1", "::1") and not self.headers.get("Cf-Connecting-Ip"):
            return "admin"
        cookie = self.headers.get("Cookie", "")
        m = re.search(r"(?:^|;\s*)rk=([^;]*)", cookie)
        key = q.get("key") or (m.group(1) if m else "")
        return "admin" if (admin and key == admin) or (review and key == review) else None

    def _login_page(self):
        body = (b"<!doctype html><meta charset=utf-8><title>FutureCalc Pipe Studio</title>"
                b"<form style='font:14px system-ui;margin:40px'>Access key: <input name=key autofocus> <button>Open</button></form>")
        self.send_response(401); self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        # the feedback overview is megabytes of text; over the tunnel that is the wait
        encoding = None
        if len(body) > 32768 and "gzip" in self.headers.get("Accept-Encoding", ""):
            body, encoding = gzip.compress(body, 5), "gzip"
        if encoding:
            self.send_header("Content-Encoding", encoding)
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, ctype):
        if not os.path.exists(path):
            return self._json({"error": "not found"}, 404)
        data = open(path, "rb").read()
        if path == os.path.join(STATIC, "index.html"):
            # New asset URLs also bypass copies cached before no-store was set.
            def version_asset(match):
                name = match.group(1).decode("ascii")
                with open(os.path.join(STATIC, name), "rb") as asset:
                    version = hashlib.sha256(asset.read()).hexdigest()[:16]
                return b'/static/' + match.group(1) + b'?v=' + version.encode("ascii")
            data = re.sub(rb'/static/([A-Za-z0-9_-]+\.(?:js|css))', version_asset, data)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        if "/api/progress" not in str(args[0] if args else ""):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _get(self):
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}
        from studio.storage import ident
        if "sheet" in q:
            ident(q["sheet"])
        role = self._role(q)
        if role is None:
            return self._login_page()
        from studio.http import dispatch
        if u.path == "/api/studio/snapshot-bg":
            from studio.storage import data_root
            return self._file(str(data_root()/"snapshots"/ident(q["id"])/"bg.png"), "image/png")
        handled = dispatch("GET", u.path, q, None, role, DEBUG)
        if handled is not None:
            return self._json(*handled)
        if u.path == "/":
            if "key" in q:   # first visit with ?key=: remember it in a cookie and drop it from the address
                self.send_response(302); self.send_header("Location", "/")
                self.send_header("Set-Cookie", f"rk={q['key']}; Path=/; Max-Age=2592000; SameSite=Lax; HttpOnly")
                self.send_header("Content-Length", "0"); self.end_headers(); return
            return self._file(os.path.join(STATIC, "index.html"), "text/html; charset=utf-8")
        if u.path == "/api/me":
            return self._json({"role": role})
        if u.path.startswith("/static/"):
            name = os.path.basename(u.path)
            import mimetypes
            ct = mimetypes.guess_type(name)[0] or "application/octet-stream"
            return self._file(os.path.join(STATIC, name), ct)
        if u.path == "/api/sheets":
            sheets = []
            for s in sorted(os.listdir(DEBUG)) if os.path.exists(DEBUG) else []:
                d = os.path.join(DEBUG, s)
                if os.path.isdir(d):
                    have = sorted(f for f in os.listdir(d) if re.match(r"\d\d_", f))
                    sheets.append({"sheet": s, "stages": have, "job": JOBS.get(s),
                                   "has_review": os.path.exists(os.path.join(d, "09_review.json")),
                                   "has_pdf": _pdf_for(s) is not None})
            return self._json(sheets)
        if u.path == "/api/progress":
            return self._json(JOBS.get(q.get("sheet"), {"status": "idle"}))
        if u.path == "/api/review":
            from studio.storage import read, digest
            rv = read(os.path.join(DEBUG, q["sheet"], "09_review.json"))
            if rv is None:
                return self._json({"error": "No analysis yet"}, 404)
            if "metadata" not in rv:
                rv["metadata"] = {"run_id": digest(rv)[:24], "style_id": "style-1", "style_version": None, "binding_mode": "legacy", "assignmentMethod": None}
            return self._json(rv)
        if u.path == "/api/stage":
            d = os.path.join(DEBUG, q["sheet"])
            fs = [f for f in os.listdir(d) if f.startswith(q["n"])] if os.path.isdir(d) else []
            return self._file(os.path.join(d, fs[0]), "application/json") if fs else self._json({"error": "no stage"}, 404)
        if u.path == "/api/export":
            # the Bindings view as a vector overlay on the original PDF
            from .export import annotate_pdf
            sheet = q["sheet"]; pdf = _pdf_for(sheet); rv = os.path.join(DEBUG, sheet, "09_review.json")
            if pdf is None or not os.path.exists(rv):
                return self._json({"error": "no pdf or review for sheet"}, 404)
            out = os.path.join(DEBUG, sheet, "bindings.pdf")
            annotate_pdf(pdf, json.load(open(rv)), out)
            data = open(out, "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Disposition", f'attachment; filename="{sheet}-bindings.pdf"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            return self.wfile.write(data)
        if u.path == "/api/bg":
            return self._file(os.path.join(DEBUG, q["sheet"], "bg.png"), "image/png")
        if u.path == "/api/noise":
            # the paths no stage after bucket reads, built on demand: too big for the review JSON
            from . import extract
            from .geom import flatten
            d = os.path.join(DEBUG, q["sheet"])
            if not all(os.path.exists(os.path.join(d, f)) for f in ("01_extract.json", "04_bucket.json")):
                return self._json({"error": "no extract/bucket stage for sheet"}, 404)
            ex = extract.load(os.path.join(d, "01_extract.json")); B = json.load(open(os.path.join(d, "04_bucket.json")))
            paths, layers = [], {}
            for p in ex.paths:
                b = B["buckets"].get(str(p.id), "unknown")
                layers.setdefault(p.layer or "", {}).setdefault(b, 0); layers[p.layer or ""][b] += 1
                if b in USED_BUCKETS:
                    continue
                paths.append({"id": p.id, "bucket": b, "width": p.width, "layer": p.layer, "kind": p.kind, "color": p.color,
                              "segs": [[round(a[0], 1), round(a[1], 1), round(c[0], 1), round(c[1], 1)] for a, c in flatten(p.items)],
                              "reason": B["reasons"].get(str(p.id), "")})
            return self._json({"paths": paths, "layers": layers})
        if u.path == "/api/feedback":
            p = os.path.join(FEEDBACK, q["sheet"] + ".json")
            return self._json(json.load(open(p)) if os.path.exists(p) else {"sheet": q["sheet"], "records": []})
        self._json({"error": "not found"}, 404)

    def _post(self):
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}
        n = int(self.headers.get("Content-Length", 0))
        if n < 0 or n > 64 * 1024 * 1024:
            return self._json({"error": "Upload limit is 64 MB"}, 413)
        body = self.rfile.read(n) if n else b""
        from studio.storage import ident
        if "sheet" in q:
            ident(q["sheet"])
        role = self._role(q)
        if role is None:
            return self._json({"error": "no access"}, 401)
        from studio.http import dispatch
        handled = dispatch("POST", u.path, q, json.loads(body) if u.path.startswith("/api/studio/") else None, role, DEBUG)
        if handled is not None:
            return self._json(*handled)
        if u.path == "/api/upload":
            # raw PDF body; the file name comes in X-File-Name
            name = os.path.basename(self.headers.get("X-File-Name", "upload.pdf"))
            sheet = re.sub(r"[^A-Za-z0-9_.-]", "_", name.rsplit(".", 1)[0])
            ident(sheet)
            if not body.startswith(b"%PDF-"):
                return self._json({"error": "Choose a PDF file"}, 400)
            if _pdf_for(sheet) or os.path.exists(os.path.join(DEBUG, sheet, "09_review.json")):
                from studio.storage import new_id
                sheet += "-" + new_id("upload").split("-")[1][:8]
            from studio.styles import get_style
            style_id = q.get("style", "auto")                 # detected from the drawing unless the reviewer picked one
            if style_id != "auto":
                get_style(style_id)
            os.makedirs(UPLOADS, exist_ok=True)
            with open(os.path.join(UPLOADS, sheet + ".pdf"), "wb") as f:
                f.write(body)
            started = _start(sheet, use_llm=False, style_id=style_id)          # a model runs only from the Run Fable / Run Astra button
            return self._json({"sheet": sheet, "started": started})
        if u.path == "/api/rerun":
            sheet = q["sheet"]
            if _pdf_for(sheet) is None:
                return self._json({"error": "no pdf for sheet"}, 400)
            started = _start(sheet, upto=int(q.get("upto", 9)), use_llm=False)
            return self._json({"sheet": sheet, "started": started})
        if u.path == "/api/bind":
            provider = q.get("provider", "astra")           # astra = Main Branch Mode (default, as on main); flow = Dimension-Based Mode
            if provider not in ("flow", "astra"):
                return self._json({"error": "provider must be flow or astra"}, 400)
            result, status = dispatch("POST", "/api/studio/replay", q,
                {"sheet": q["sheet"], "binding": provider, "style_id": q.get("style", "style-1")}, role, DEBUG)
            return self._json(result, status)
        if u.path == "/api/feedback":
            return self._json({"error": "Use /api/studio/feedback to capture versioned evidence"}, 409)
        self._json({"error": "not found"}, 404)


if __name__ == "__main__":
    load_dotenv()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8770
    os.makedirs(DEBUG, exist_ok=True)
    print(f"FutureCalc Pipe Studio on http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
