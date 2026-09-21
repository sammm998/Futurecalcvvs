"""HTTP server and JSON API for the review application."""

import json
import math
import mimetypes
import os
import posixpath
import socketserver
import threading
from http.server import BaseHTTPRequestHandler

import pipe_seg as ps
import pipe_types as pt

from .session import SESSION_DIR, Session

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def _mean_width(polys):
    """Rough stroke width of a set of pipe polygons (area / half-perimeter)."""
    ws = []
    for p in polys:
        per = p.exterior.length
        if per > 1e-6:
            ws.append(max(0.4, 2.0 * p.area / per))
    return sum(ws) / len(ws) if ws else 1.5


def _bridge_parts(geom, width):
    """Join the parts of a MultiPolygon with thin corridors until it is one
    polygon.  Each pass connects the two closest parts along their shortest
    gap, so the result follows the drawing instead of hulling over it."""
    from shapely.geometry import LineString
    from shapely.ops import nearest_points, unary_union

    for _ in range(64):
        if geom.geom_type != "MultiPolygon" or len(geom.geoms) < 2:
            break
        parts = list(geom.geoms)
        best = None
        for i in range(len(parts)):
            for j in range(i + 1, len(parts)):
                d = parts[i].distance(parts[j])
                if best is None or d < best[0]:
                    best = (d, i, j)
        _d, i, j = best
        a, b = nearest_points(parts[i], parts[j])
        dx, dy = b.x - a.x, b.y - a.y
        L = math.hypot(dx, dy)
        # Polygons that only touch along their boundary stay separate under a
        # union, so the corridor overhangs both ends and genuinely overlaps.
        over = max(width, 1.0)
        if L < 1e-9:
            ux, uy = 1.0, 0.0
        else:
            ux, uy = dx / L, dy / L
        corridor = LineString([(a.x - ux * over, a.y - uy * over),
                               (b.x + ux * over, b.y + uy * over)]).buffer(
            width / 2, cap_style=1, join_style=1)
        geom = unary_union(parts + [corridor])
    return geom


# "Same pipe" for the one-click merge: one polygon carries on where the other
# stops.  Measured on the step-1 output of the sample sheets, adjacent pairs
# fall into clean groups — end-to-end continuations (what we want), crossings,
# and side-by-side parallel runs (two different pipes, must never fuse).  These
# thresholds are the ones that separate them, with a wider gap than the
# extraction pass uses because this action is explicit and undoable.
SAME_PIPE_GAP = 6.0        # pt, largest break that is still one pipe
SAME_PIPE_ANGLE = 20.0     # deg, how far the two long axes may differ
SAME_PIPE_OFFAXIS = 35.0   # deg, gap must run ALONG that axis, not across it
# Holes bigger than this mean the pieces closed a loop, not a break in one run.
# Rounding from the buffer round-trip leaves slivers of well under a point.
MAX_ENCLOSED_AREA = 4.0    # pt^2
# Re-joining one pipe barely changes how much ink is covered — measured across
# the sample sheets, sound merges land between +0.0% and +2.5%, while ones that
# fill the notch between two pipes meeting at a shallow angle jump straight to
# +9% and beyond.  Past this the merge would paint space that is not pipe, so
# it is refused and those pieces are left alone.
MAX_AREA_GROWTH = 0.05     # fraction


def _long_axis(poly):
    """Orientation of a polygon's long axis, degrees in [0, 180)."""
    try:
        cs = list(poly.minimum_rotated_rectangle.exterior.coords)[:4]
    except Exception:
        return 0.0
    best, blen = 0.0, -1.0
    for i in range(len(cs)):
        x1, y1 = cs[i]
        x2, y2 = cs[(i + 1) % len(cs)]
        L = math.hypot(x2 - x1, y2 - y1)
        if L > blen:
            blen, best = L, math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180.0
    return best


def _ang_diff(a, b):
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def same_pipe_groups(rings):
    """Group polygon rings that are the SAME pipe, broken into pieces.

    Only end-to-end continuations are grouped: the two pieces must be
    collinear AND meet along that shared axis, so one continues where the
    other stops.  A pipe that merely CROSSES another fails the angle test, and
    one running alongside it fails the off-axis test, so two different pipes
    are never fused.  Grouping is transitive, so a run broken into three or
    more pieces comes back as one group.
    """
    from shapely.geometry import Polygon
    from shapely.ops import nearest_points
    from shapely.strtree import STRtree

    polys, idx = [], []
    for i, r in enumerate(rings):
        if len(r) < 4:
            continue
        p = Polygon(r)
        if not p.is_valid:
            p = p.buffer(0)
        if p.geom_type == "MultiPolygon":
            p = max(p.geoms, key=lambda g: g.area)
        if not p.is_empty and p.area > 0:
            polys.append(p)
            idx.append(i)
    if len(polys) < 2:
        return []

    ang = [_long_axis(p) for p in polys]
    parent = list(range(len(polys)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    tree = STRtree(polys)
    for i, p in enumerate(polys):
        for k in tree.query(p.buffer(SAME_PIPE_GAP)):
            j = int(k)
            if j <= i:
                continue
            if p.distance(polys[j]) > SAME_PIPE_GAP:
                continue
            if _ang_diff(ang[i], ang[j]) > SAME_PIPE_ANGLE:
                continue                      # not collinear -> not one pipe
            a, b = nearest_points(p, polys[j])
            if a.distance(b) < 1e-9:          # touching: read across centroids
                gv = math.degrees(math.atan2(
                    polys[j].centroid.y - p.centroid.y,
                    polys[j].centroid.x - p.centroid.x)) % 180.0
            else:
                gv = math.degrees(math.atan2(b.y - a.y, b.x - a.x)) % 180.0
            if _ang_diff(gv, ang[i]) > SAME_PIPE_OFFAXIS or \
                    _ang_diff(gv, ang[j]) > SAME_PIPE_OFFAXIS:
                continue                      # side by side, not end to end
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[rj] = ri

    buckets = {}
    for i in range(len(polys)):
        buckets.setdefault(find(i), []).append(idx[i])
    return [sorted(g) for g in buckets.values() if len(g) > 1]


def merged_geometry(rings, snap=1.2, single=True):
    """Union polygon rings into one geometry, holes and all."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    polys = []
    for r in rings:
        if len(r) < 4:
            continue
        p = Polygon(r)
        if not p.is_valid:
            p = p.buffer(0)
        if not p.is_empty:
            polys.append(p)
    if not polys:
        return None
    merged = unary_union([p.buffer(snap / 2, join_style=2) for p in polys])
    merged = merged.buffer(-snap / 2, join_style=2)
    if merged.is_empty:
        merged = unary_union(polys)
    if single:
        merged = _bridge_parts(merged, _mean_width(polys))
    return merged


def enclosed_area(geom):
    """Area of any holes the union closed around.

    A pipe polygon is a single ring, so exporting the union keeps only its
    outer boundary — which means a run that loops back on itself would come
    out as a filled slab covering everything inside the loop.  Measuring the
    holes first is what lets the caller refuse that.
    """
    from shapely.geometry import Polygon

    if geom is None or geom.is_empty:
        return 0.0
    geoms = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
    return sum(Polygon(r).area for g in geoms
               for r in getattr(g, "interiors", []))


def _grows_too_much(members, ring):
    """Would this merge paint noticeably more than the pieces already cover?"""
    from shapely.geometry import Polygon

    before = 0.0
    for r in members:
        g = Polygon(r).buffer(0)
        if not g.is_empty:
            before += g.area
    if before <= 0:
        return False
    return Polygon(ring).buffer(0).area > before * (1.0 + MAX_AREA_GROWTH)


def merge_rings(rings, snap=1.2, single=True):
    """Union polygon rings server-side (shapely), returning the merged rings.

    Rings that do not quite touch are nudged together with a small buffer so
    that visually-connected pipes merge into one polygon.  With `single`, parts
    that stay apart are joined by a thin corridor along their shortest gap, so
    "select several polygons and merge" always yields ONE pipe polygon.
    """
    merged = merged_geometry(rings, snap, single)
    if merged is None:
        return []
    geoms = merged.geoms if merged.geom_type == "MultiPolygon" else [merged]
    out = []
    for g in geoms:
        if g.is_empty or g.area <= 0:
            continue
        out.append([[round(x, 2), round(y, 2)] for x, y in g.exterior.coords])
    return out


class Handler(BaseHTTPRequestHandler):
    session: Session = None
    protocol_version = "HTTP/1.1"

    # -- plumbing ---------------------------------------------------------- #
    def log_message(self, *a):
        pass

    def _send(self, code, ctype, body, extra=None):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code=200):
        self._send(code, "application/json; charset=utf-8", json.dumps(obj))

    def _body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return {}

    def _static(self, rel):
        rel = posixpath.normpath(rel).lstrip("/")
        path = os.path.join(STATIC_DIR, rel)
        if not os.path.abspath(path).startswith(STATIC_DIR) or \
                not os.path.isfile(path):
            self._send(404, "text/plain", "not found")
            return
        ctype, _ = mimetypes.guess_type(path)
        if path.endswith(".js"):
            ctype = "text/javascript; charset=utf-8"
        elif path.endswith(".css"):
            ctype = "text/css; charset=utf-8"
        with open(path, "rb") as f:
            self._send(200, ctype or "application/octet-stream", f.read())

    # -- routes ------------------------------------------------------------ #
    def do_GET(self):
        s = Handler.session
        path = self.path.split("?")[0]

        if path == "/":
            return self._static("index.html")
        if path.startswith("/static/"):
            return self._static(path[len("/static/"):])
        if path == "/api/progress":
            return self._json(s.progress)
        if path == "/api/document":
            if not s.progress.get("ready"):
                return self._json({"progress": s.progress}, 202)
            return self._json(s.payload())
        if path == "/api/background.png":
            bg = s.extraction.background_path(SESSION_DIR)
            if not os.path.exists(bg):
                s.extraction.render_background(SESSION_DIR)
            with open(bg, "rb") as f:
                return self._send(200, "image/png", f.read())
        return self._send(404, "text/plain", "not found")

    def do_POST(self):
        s = Handler.session
        path = self.path.split("?")[0]
        body = self._body()

        try:
            if path == "/api/save":
                if "pipes" in body:
                    s.replace_document(body)
                return self._json({"ok": True, "path": s.save()})

            if path == "/api/autosave":
                if "pipes" in body:
                    s.replace_document(body)
                p = s.autosave()
                return self._json({"ok": True, "path": p, "skipped": p is None})

            if path == "/api/reassign":
                if "pipes" in body:
                    s.replace_document(body)
                summary = s.run_assignment()
                return self._json({"ok": True, "summary": summary,
                                   "document": s.payload()})

            if path == "/api/export/json":
                if "pipes" in body:
                    s.replace_document(body)
                    s.save()
                return self._json({"ok": True, **s.export_json()})

            if path == "/api/export/png":
                if "pipes" in body:
                    s.replace_document(body)
                    s.save()
                return self._json({"ok": True, **s.export_png()})

            if path == "/api/reset":
                s.reset()
                return self._json({"ok": True, "document": s.payload()})

            if path == "/api/geometry/merge":
                return self._json({"ok": True,
                                   "rings": merge_rings(body.get("rings", []))})

            if path == "/api/geometry/automerge":
                rings = body.get("rings", [])
                out, n_skip = [], 0
                for group in same_pipe_groups(rings):
                    members = [rings[i] for i in group]
                    geom = merged_geometry(members)
                    # A run that loops back on itself would export as a filled
                    # slab covering the middle, because a pipe polygon is one
                    # ring and cannot carry a hole.  Leave those pieces alone
                    # rather than paint over the space between them.
                    if enclosed_area(geom) > MAX_ENCLOSED_AREA:
                        n_skip += 1
                        continue
                    merged = merge_rings(members)
                    # one pipe in, one pipe out — if the union somehow came
                    # back in pieces, leave that group alone rather than
                    # silently turning N polygons into a different N
                    if len(merged) != 1:
                        continue
                    if _grows_too_much(members, merged[0]):
                        n_skip += 1
                        continue
                    out.append({"indices": group, "ring": merged[0]})
                return self._json({"ok": True, "groups": out,
                                   "skipped": n_skip})

            if path == "/api/ocr/label":
                rect = body.get("rect")
                if not rect or len(rect) != 4:
                    return self._json({"ok": False, "error": "bad rect"}, 400)
                page = s.extraction.ensure_page()
                # `text` is everything inside the box, `code` only the part
                # that parsed as a pipe-type code — a hand-drawn box over a
                # label with extra rows hands back both
                code, text = pt.read_label_text(page, rect)
                return self._json({"ok": True, "code": code, "text": text})

        except Exception as exc:                      # keep the server alive
            import traceback
            traceback.print_exc()
            return self._json({"ok": False, "error": str(exc)}, 500)

        return self._send(404, "text/plain", "not found")


class ThreadingServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve(pdf_path, port=8765, open_browser=True):
    session = Session(pdf_path)
    Handler.session = session

    # extract in the background so the UI can show a progress screen
    threading.Thread(target=session.load, daemon=True).start()

    httpd = ThreadingServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    ps.log(f"review UI ready on {url}   (Ctrl-C to stop)")
    if open_browser:
        import webbrowser
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        ps.log("review UI stopped")
    finally:
        httpd.server_close()
