// Select / move / marquee, and the pan tool.

import { Tool } from './index.js';
import { translateRing } from '../polyops.js';

const ICON_SELECT = '<path d="m4 3 7 17 2.5-6.5L20 11z"/>';
const ICON_PAN = '<path d="M9 11V5.5a1.5 1.5 0 0 1 3 0V11m0-1.5a1.5 1.5 0 0 1 3 0V13m0-2a1.5 1.5 0 0 1 3 0v5a5 5 0 0 1-5 5h-1.8a5 5 0 0 1-3.6-1.5L4 16.5a1.6 1.6 0 0 1 2.3-2.2L9 16"/>';

export class SelectTool extends Tool {
  static id = 'select';
  static title = 'Select';
  static key = 'V';
  static icon = ICON_SELECT;
  static cursor = 'default';

  activate() { this.drag = null; }
  deactivate() { this._endDrag(); }

  onPointerDown(e, w) {
    // resizing a joining point takes priority over selection
    const handle = this.renderer.joinHandleAt(w[0], w[1]);
    if (handle) {
      this.history.begin('Resize joining point');
      this.drag = { mode: 'radius', join: handle, changed: false };
      return;
    }

    const hit = this.renderer.hitTest(w[0], w[1]);

    if (!hit) {
      if (!e.shiftKey) this.store.clearSelection();
      this.drag = { mode: 'marquee', start: w, additive: e.shiftKey };
      this.renderer.overlay.marquee = [w[0], w[1], w[0], w[1]];
      this.renderer.invalidate();
      return;
    }

    if (e.shiftKey) {
      this.store.toggleSelect(hit.kind, hit.id);
      this.renderer.invalidate();
      return;
    }

    if (!this.store.isSelected(hit.kind, hit.id)) {
      this.store.select([{ kind: hit.kind, id: hit.id }]);
    }
    // begin a move of everything selected
    this.history.begin('Move objects');
    this.drag = {
      mode: 'move', last: w, moved: false,
      items: this.store.selectionList(),
    };
    this.renderer.invalidate();
  }

  onPointerMove(e, w) {
    if (!this.drag) {
      const overHandle = this.renderer.joinHandleAt(w[0], w[1]);
      this.app.canvas.style.cursor = overHandle ? 'ew-resize' : 'default';
      const hit = this.renderer.hitTest(w[0], w[1]);
      this.store.setHover(hit ? { kind: hit.kind, id: hit.id } : null);
      return;
    }

    if (this.drag.mode === 'radius') {
      const j = this.drag.join;
      const r = Math.hypot(w[0] - j.point[0], w[1] - j.point[1]);
      this.store.setJoinRadius(j.id, r);
      this.drag.changed = true;
      this.renderer.invalidateObject('join', j.id);
      this.app.setHint2(`Capture radius ${(j.radius).toFixed(1)} pt`);
      this.renderer.invalidate();
      return;
    }

    if (this.drag.mode === 'marquee') {
      const s = this.drag.start;
      this.renderer.overlay.marquee = [
        Math.min(s[0], w[0]), Math.min(s[1], w[1]),
        Math.max(s[0], w[0]), Math.max(s[1], w[1]),
      ];
      this.renderer.invalidate();
      return;
    }

    const dx = w[0] - this.drag.last[0], dy = w[1] - this.drag.last[1];
    if (!dx && !dy) return;
    this.drag.last = w;
    this.drag.moved = true;
    for (const { kind, obj } of this.drag.items) {
      if (kind === 'pipe') {
        translateRing(obj.polygon, dx, dy);
        this.renderer.invalidateObject('pipe', obj.id);
      } else if (kind === 'label') {
        obj.rect[0] += dx; obj.rect[1] += dy;
        obj.rect[2] += dx; obj.rect[3] += dy;
        this.renderer.invalidateObject('label', obj.id);
      } else {
        obj.point[0] += dx; obj.point[1] += dy;
        this.renderer.invalidateObject('join', obj.id);
      }
    }
    this.renderer.invalidate();
  }

  onPointerUp() {
    if (!this.drag) return;
    if (this.drag.mode === 'radius') {
      if (this.drag.changed) {
        this.history.commit();
        this.app.toast(
          `${this.drag.join.id} capture radius ` +
          `${this.drag.join.radius.toFixed(1)} pt — re-run assignment to apply`);
      } else {
        this.history.cancel();
      }
      this._endDrag();
      return;
    }
    if (this.drag.mode === 'marquee') {
      const r = this.renderer.overlay.marquee;
      if (r && (r[2] - r[0] > 0.5 || r[3] - r[1] > 0.5)) {
        const found = this.renderer.hitRect(r)
          .map(h => ({ kind: h.kind, id: h.id }));
        this.store.select(found, { additive: this.drag.additive });
      }
    } else if (this.drag.mode === 'move' && this.drag.moved) {
      // moving geometry invalidates the automatic assignment
      const kinds = new Set(this.drag.items.map(i => i.kind));
      for (const k of kinds) {
        this.store.touch(k === 'pipe' ? 'pipe:geometry' : `${k}:move`);
      }
      for (const { kind, obj } of this.drag.items) {
        if (kind === 'pipe') this.store.recomputeStats(obj);
      }
      this.history.commit();
    } else {
      this.history.cancel();
    }
    this._endDrag();
  }

  _endDrag() {
    this.drag = null;
    this.renderer.overlay.marquee = null;
    this.renderer.invalidate();
  }

  status() { return 'Click to select · Shift adds · Drag to marquee or move'; }
}

export class PanTool extends Tool {
  static id = 'pan';
  static title = 'Pan';
  static key = 'H';
  static icon = ICON_PAN;
  static cursor = 'grab';

  onPointerDown(e) {
    this.dragging = { x: e.clientX, y: e.clientY };
    this.app.canvas.classList.add('grabbing');
  }

  onPointerMove(e) {
    if (!this.dragging) return;
    this.vp.panBy(e.clientX - this.dragging.x, e.clientY - this.dragging.y);
    this.dragging = { x: e.clientX, y: e.clientY };
  }

  onPointerUp() {
    this.dragging = null;
    this.app.canvas.classList.remove('grabbing');
  }

  status() { return 'Drag to pan · Scroll to zoom'; }
}
