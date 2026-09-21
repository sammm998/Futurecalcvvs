// Link tool — set a class without ever choosing from a class list.
//
//   click a PIPE          then a label box -> that pipe takes the label's class
//   click a JOINING POINT then a label box -> the joining point re-points at
//                                             that label, the leader follows,
//                                             and every pipe it claims updates

import { Tool } from './index.js';
import { centroid } from '../polyops.js';

const I_LINK = '<path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1"/>' +
               '<path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"/>';

export class LinkTool extends Tool {
  static id = 'link';
  static title = 'Link Label';
  static key = 'K';
  static icon = I_LINK;
  static cursor = 'crosshair';

  activate() {
    this.join = null; this.pipe = null;
    const sel = this.store.selectionList();
    if (sel.length === 1 && sel[0].kind === 'join') this.join = sel[0].obj;
    if (sel.length === 1 && sel[0].kind === 'pipe') this.pipe = sel[0].obj;
    this.app.setHint2(this._prompt());
  }

  deactivate() {
    this.join = null; this.pipe = null;
    this.renderer.overlay.rubber = null;
    this.app.setHint2('');
    this.renderer.invalidate();
  }

  _prompt() {
    if (this.pipe) return `Now click a label box to classify ${this.pipe.id}`;
    if (this.join) return `Now click the label box to give ${this.join.id} its class`;
    return 'Click a pipe or a joining point, then click a label box';
  }

  get source() { return this.pipe || this.join; }

  onPointerMove(e, w) {
    const hit = this.renderer.hitTest(w[0], w[1]);
    this.store.setHover(hit ? { kind: hit.kind, id: hit.id } : null);
    const src = this.source;
    if (src) {
      // rubber-band from the chosen object to the cursor
      const from = src.point || centroid(src.polygon);
      this.renderer.overlay.rubber = { a: from, b: w };
    }
    this.renderer.invalidate();
  }

  onPointerDown(e, w) {
    const hit = this.renderer.hitTest(w[0], w[1]);

    if (!this.source) {
      if (hit?.kind === 'join') this.join = hit.obj;
      else if (hit?.kind === 'pipe') this.pipe = hit.obj;
      else {
        this.app.toast('Start by clicking a pipe or a joining point', 'error');
        return;
      }
      this.store.select([{ kind: hit.kind, id: hit.id }]);
      this.app.setHint2(this._prompt());
      this.renderer.invalidate();
      return;
    }

    if (hit?.kind !== 'label') {
      this.app.toast('Click a label bounding box to link it', 'error');
      return;
    }

    const ok = this.pipe
      ? this.app.setPipeClassFromLabel(this.pipe.id, hit.id)
      : this.app.linkJoinToLabel(this.join.id, hit.id);
    if (ok) {
      this.join = null; this.pipe = null;
      this.renderer.overlay.rubber = null;
      this.app.setHint2(this._prompt());
    }
  }

  onKeyDown(e) {
    if (e.key === 'Escape' && this.source) {
      this.join = null; this.pipe = null;
      this.renderer.overlay.rubber = null;
      this.app.setHint2(this._prompt());
      this.renderer.invalidate();
      return true;
    }
    return false;
  }

  status() { return this._prompt(); }
}
