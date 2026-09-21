// Annotation tools: label boxes and joining points.

import { Tool } from './index.js';
import { closestOnRing } from '../polyops.js';
import { api } from '../api.js';

/** How far a new joining point looks for the label whose class it inherits. */
const TYPE_LABEL_REACH = 140;   // page points

const I_LABEL = '<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M7 10h6M7 14h4"/>';
const I_JOIN = '<circle cx="12" cy="12" r="3.4"/><path d="M12 3v5M12 16v5M3 12h5M16 12h5"/>';

/* ── add label ───────────────────────────────────────────────────────────── */
export class AddLabelTool extends Tool {
  static id = 'label';
  static title = 'Add Label';
  static key = 'L';
  static icon = I_LABEL;
  static cursor = 'crosshair';

  onPointerDown(e, w) {
    this.start = w;
    this.renderer.overlay.marquee = [w[0], w[1], w[0], w[1]];
    this.renderer.invalidate();
  }

  onPointerMove(e, w) {
    if (!this.start) return;
    const s = this.start;
    this.renderer.overlay.marquee = [
      Math.min(s[0], w[0]), Math.min(s[1], w[1]),
      Math.max(s[0], w[0]), Math.max(s[1], w[1]),
    ];
    this.renderer.invalidate();
  }

  async onPointerUp(e, w) {
    if (!this.start) return;
    const r = this.renderer.overlay.marquee;
    this.renderer.overlay.marquee = null;
    this.start = null;
    this.renderer.invalidate();
    if (!r || (r[2] - r[0]) < 1.5 || (r[3] - r[1]) < 1) return;

    // Read the text under the box automatically instead of asking the user
    // to type it from scratch — they only need to fix it if OCR got it
    // wrong, not fill it in from nothing.
    const rect = r.map(v => +v.toFixed(2));
    let guess = '';
    let read = '';
    this.app.toast('Reading label…');
    try {
      const res = await api.ocrLabel(rect);
      guess = res.code || '';
      // the whole box, extra rows included — kept on the label even though
      // the prompt only asks for the code
      read = res.text || '';
    } catch (err) {
      this.app.toast(`OCR failed: ${err.message}`, 'error');
    }

    const code = await this.app.promptClass('New label', guess);
    if (!code) return;
    this.history.begin('Add label');
    const l = this.store.addLabel(r.map(v => +v.toFixed(2)), code, read);
    this.history.commit();
    this.renderer.invalidateObject('label', l.id);
    this.store.select([{ kind: 'label', id: l.id }]);
    this.app.toast(`Label ${l.id} added — add a joining point to connect it`);
    this.renderer.invalidate();
  }

  deactivate() { this.start = null; this.renderer.overlay.marquee = null; }
  status() { return 'Drag a box around the label text'; }
}

/* ── add joining point ───────────────────────────────────────────────────── */
export class AddJoinTool extends Tool {
  static id = 'join';
  static title = 'Add Joining Point';
  static key = 'J';
  static icon = I_JOIN;
  static cursor = 'crosshair';

  /** Nearest point on any pipe, for the snap preview. */
  _snap(w) {
    const tol = Math.max(8, 14 / this.vp.z);
    const cands = this.renderer.index.query(
      [w[0] - tol, w[1] - tol, w[0] + tol, w[1] + tol]);
    let best = null, bestD = Infinity, bestPipe = null;
    for (const key of cands) {
      if (!key.startsWith('pipe:')) continue;
      const p = this.store.pipeById.get(key.slice(5));
      if (!p || p.deleted) continue;
      const { point, dist } = closestOnRing(p.polygon, w[0], w[1]);
      if (dist < bestD) { bestD = dist; best = point; bestPipe = p; }
    }
    return bestD <= tol ? { point: best, pipe: bestPipe, dist: bestD } : null;
  }

  /** The label a new joining point belongs to: the selected one, else the
   *  nearest label box. Its class is inherited automatically. */
  _associatedLabel(w) {
    const sel = this.store.selectionList().find(x => x.kind === 'label');
    if (sel) return sel.obj;
    let best = null, bestD = Infinity;
    for (const l of this.store.activeLabels()) {
      if (!l.code) continue;
      const [x0, y0, x1, y1] = l.rect;
      const dx = Math.max(x0 - w[0], 0, w[0] - x1);
      const dy = Math.max(y0 - w[1], 0, w[1] - y1);
      const d = Math.hypot(dx, dy);
      if (d < bestD) { bestD = d; best = l; }
    }
    return bestD <= TYPE_LABEL_REACH ? best : null;
  }

  onPointerMove(e, w) {
    const s = this._snap(w);
    this.renderer.overlay.snap = s ? s.point : null;
    this.store.setHover(s ? { kind: 'pipe', id: s.pipe.id } : null);
    const lab = this._associatedLabel(w);
    this.app.setHint2(lab
      ? `Will inherit “${lab.code}” from ${lab.id}`
      : 'No label nearby — you will be asked for the class');
    this.renderer.invalidate();
  }

  onPointerDown(e, w) {
    const s = this._snap(w);
    if (!s) {
      this.app.toast('Move closer to a pipe — joining points snap to pipes',
                     'error');
      return;
    }
    const lab = this._associatedLabel(w);
    // Adding a joining point runs the whole workflow in one step: split the
    // pipe polygon here, link the label through a leader line, and take the
    // label's class. No manual class selection.
    const res = this.app.placeJoiningPoint(
      [+s.point[0].toFixed(2), +s.point[1].toFixed(2)], s.pipe, lab);
    if (!res) return;
    this.renderer.invalidate();
  }

  deactivate() { this.renderer.overlay.snap = null; this.app.setHint2(''); }
  status() {
    return 'Click near a pipe — snaps to the centreline and inherits the ' +
           'nearest label’s class';
  }
}
