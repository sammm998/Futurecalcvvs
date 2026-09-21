// Draw Connection tool — segment the thin line that ties a label to its pipe.
//
// Click the label box, then click the pipe (or an existing joining point).
// The line is recorded as a LeaderLine, a joining point is created where it
// meets the pipe if there is not one already, and the label's class flows
// through it at the classification step.

import { Tool } from './index.js';
import { closestOnRing } from '../polyops.js';

const I_CONNECT = '<path d="M4 6h6"/><path d="M7 6v4l10 8"/>' +
                  '<circle cx="18" cy="18" r="2.4"/><rect x="2" y="3" width="8" height="6" rx="1"/>';

export class ConnectTool extends Tool {
  static id = 'connect';
  static title = 'Draw Connection';
  static key = 'C';
  static icon = I_CONNECT;
  static cursor = 'crosshair';

  activate() {
    this.label = null;
    const sel = this.store.selectionList();
    if (sel.length === 1 && sel[0].kind === 'label') this.label = sel[0].obj;
    this.app.setHint2(this._prompt());
  }

  deactivate() {
    this.label = null;
    this.renderer.overlay.rubber = null;
    this.renderer.overlay.snap = null;
    this.app.setHint2('');
    this.renderer.invalidate();
  }

  _prompt() {
    return this.label
      ? `Now click the pipe this connection points at (${this.label.code})`
      : 'Click a label box, then click the pipe it points at';
  }

  _anchor(l) {
    return [(l.rect[0] + l.rect[2]) / 2, (l.rect[1] + l.rect[3]) / 2];
  }

  /** The line the drawing itself already has for this label, if any. */
  _tracedFor(label) {
    const e = (this.store.doc.leaders || []).find(
      x => x.labelId === label.id && x.drawn !== false && x.path?.length);
    return e ? e.path : null;
  }

  /** Nearest point on any pipe, so the line lands exactly on the centreline. */
  _snapPipe(w) {
    const tol = Math.max(10, 18 / this.vp.z);
    let best = null, bestD = Infinity, pipe = null;
    for (const key of this.renderer.index.query(
        [w[0] - tol, w[1] - tol, w[0] + tol, w[1] + tol])) {
      if (!key.startsWith('pipe:')) continue;
      const p = this.store.pipeById.get(key.slice(5));
      if (!p || p.deleted) continue;
      const { point, dist } = closestOnRing(p.polygon, w[0], w[1]);
      if (dist < bestD) { bestD = dist; best = point; pipe = p; }
    }
    return bestD <= tol ? { point: best, pipe } : null;
  }

  onPointerMove(e, w) {
    const hit = this.renderer.hitTest(w[0], w[1]);
    this.store.setHover(hit ? { kind: hit.kind, id: hit.id } : null);
    if (this.label) {
      const s = this._snapPipe(w);
      this.renderer.overlay.snap = s ? s.point : null;
      this.renderer.overlay.rubber = { a: this._anchor(this.label),
                                       b: s ? s.point : w };
    }
    this.renderer.invalidate();
  }

  onPointerDown(e, w) {
    const hit = this.renderer.hitTest(w[0], w[1]);

    if (!this.label) {
      if (hit?.kind !== 'label') {
        this.app.toast('Start by clicking the label box', 'error');
        return;
      }
      this.label = hit.obj;
      this.store.select([{ kind: 'label', id: hit.id }]);
      this.app.setHint2(this._prompt());
      this.renderer.invalidate();
      return;
    }

    // second click: an existing joining point, or a fresh one on the pipe
    let join = hit?.kind === 'join' ? hit.obj : null;
    let snap = join ? null : this._snapPipe(w);
    if (!join && !snap) {
      this.app.toast('Click on the pipe this label points at', 'error');
      return;
    }

    const label = this.label;
    this.history.begin('Draw connection line');
    try {
      if (!join) {
        join = this.store.addJoin(
          [+snap.point[0].toFixed(2), +snap.point[1].toFixed(2)],
          label.code, label.id);
        join.pipeId = snap.pipe.id;
        join.pipeIds = [snap.pipe.id];
      } else {
        join.labelId = label.id;
        join.code = label.code;
        this.store.touch('join:relink', join.id);
      }
      // replace any previous connection for this joining point
      const old = this.store.leaderForJoin(join.id);
      if (old) { old.deleted = true; this.store.touch('leader:delete', old.id); }
      const anchor = this._anchor(label);
      join.anchor = anchor;
      // The drawing already carries this label's line — reuse that geometry
      // rather than inventing a second one.  Only a label with no line of its
      // own falls back to a straight hint.
      const traced = this._tracedFor(label);
      this.store.addLeader(traced ? traced.map(s => s.map(p => p.slice()))
                                  : [[anchor, join.point.slice()]],
                           { labelId: label.id, joinId: join.id,
                             code: label.code, drawn: !!traced });
      this.history.commit();
    } catch (err) {
      this.history.cancel();
      this.app.toast(`Could not connect: ${err.message}`, 'error');
      return;
    }

    this.label = null;
    this.renderer.overlay.rubber = null;
    this.renderer.overlay.snap = null;
    this.renderer.rebuildAll();
    this.store.select([{ kind: 'join', id: join.id }]);
    this.app.setHint2(this._prompt());
    this.app.toast(`Connected ${label.id} “${label.code}” → ${join.id}`);
  }

  onKeyDown(e) {
    if (e.key === 'Escape' && this.label) {
      this.label = null;
      this.renderer.overlay.rubber = null;
      this.renderer.overlay.snap = null;
      this.app.setHint2(this._prompt());
      this.renderer.invalidate();
      return true;
    }
    return false;
  }

  status() { return this._prompt(); }
}
