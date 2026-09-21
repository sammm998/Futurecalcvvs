// Layers panel, history panel, search, context menu, minimap, status bar.

import { classColor, el, fmt, polyBounds } from './util.js';

const EYE = '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/>';
const EYE_OFF = '<path d="M3 3l18 18"/><path d="M10.6 5.1A10 10 0 0 1 12 5c6.4 0 10 7 10 7a17 17 0 0 1-3.3 4M6.3 6.3A17 17 0 0 0 2 12s3.6 7 10 7a10 10 0 0 0 4-.8"/>';
const LOCK = '<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>';
const UNLOCK = '<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 7.5-2"/>';

/* ── layers ──────────────────────────────────────────────────────────────── */
export class LayersPanel {
  constructor(app, root) {
    this.app = app; this.root = root;
    this.defs = [
      ['background', 'Background PDF', '#6b7484'],
      ['wall', 'Wall mask', '#fbbf24'],
      ['pipes', 'Pipes', '#e879f9'],
      ['labels', 'Labels', '#60a5fa'],
      ['joins', 'Joining points', '#fb923c'],
      ['leaders', 'Leader lines', '#a3e635'],
    ];
    app.store.on('change', (ev) => { if (ev?.reason !== 'thresholds') this.render(); });
    this.render();
  }

  counts(key) {
    const s = this.app.store;
    const frac = (vis, all) => (vis < all ? `${vis}/${all}` : String(all));
    return { pipes: s.activePipes().length,
             labels: frac(s.visibleLabels().length, s.activeLabels().length),
             joins: frac(s.visibleJoins().length, s.activeJoins().length),
             leaders: s.activeLeaders().length,
             wall: (s.doc?.wall || []).length, background: '' }[key];
  }

  render() {
    if (!this.app.store.doc) return;
    this.root.replaceChildren();
    const sec = el('div', { class: 'section' },
      el('div', { class: 'section-title' }, 'Layers'));

    for (const [key, name, colour] of this.defs) {
      const L = this.app.store.layers[key];
      const row = el('div', { class: 'layer' },
        el('button', {
          class: 'ltoggle' + (L.on ? ' on' : ''),
          title: L.on ? 'Hide layer' : 'Show layer',
          html: `<svg viewBox="0 0 24 24">${L.on ? EYE : EYE_OFF}</svg>`,
          onclick: () => { L.on = !L.on; this.app.renderer.invalidate(); this.render(); },
        }),
        el('span', { class: 'layer-swatch', style: `background:${colour}` }),
        el('span', { class: 'lname' }, name),
        el('span', { class: 'lcount' }, String(this.counts(key) ?? '')),
        el('button', {
          class: 'llock' + (L.locked ? ' on' : ''),
          title: L.locked ? 'Unlock layer' : 'Lock layer (not selectable)',
          html: `<svg viewBox="0 0 24 24">${L.locked ? LOCK : UNLOCK}</svg>`,
          onclick: () => { L.locked = !L.locked; this.render(); },
        }));
      sec.append(row);

      const slider = el('input', {
        type: 'range', min: '0', max: '100', value: String(L.opacity * 100),
        oninput: (e) => {
          L.opacity = e.target.value / 100;
          this.app.renderer.invalidate();
        },
      });
      sec.append(el('div', { style: 'padding:0 9px 8px' }, slider));
    }
    this.root.append(sec);

    // detector confidence: the model runs at 0.05; below a slider a
    // detection is hidden and skipped by classification, never deleted
    const st = this.app.store;
    const th = el('div', { class: 'section' },
      el('div', { class: 'section-title' }, 'Detector confidence'));
    for (const [key, name] of [['label', 'Labels'], ['join', 'Joining points']]) {
      const val = el('span', { class: 'v' }, st.thresholds[key].toFixed(2));
      const cnt = el('span', { class: 'lcount' },
        String(this.counts(key === 'label' ? 'labels' : 'joins')));
      th.append(el('div', { class: 'kv' },
        el('span', { class: 'k' }, name), val, cnt));
      const slider = el('input', {
        type: 'range', min: '5', max: '100',
        value: String(Math.round(st.thresholds[key] * 100)),
        oninput: (e) => {
          st.setThreshold(key, e.target.value / 100);
          val.textContent = st.thresholds[key].toFixed(2);
          cnt.textContent = String(this.counts(key === 'label' ? 'labels' : 'joins'));
          this.app.renderer.invalidate();
        },
        onchange: () => this.render(),
      });
      th.append(el('div', { style: 'padding:0 9px 8px' }, slider));
    }
    th.append(el('div', { class: 'empty-state' },
      'Hidden detections are ignored by the assignment; hand-placed objects ' +
      '(black) are never filtered. Re-run assignment after a change.'));
    this.root.append(th);

    // filters
    const f = el('div', { class: 'section' },
      el('div', { class: 'section-title' }, 'Filters'));
    f.append(el('button', {
      class: 'btn block ghost',
      onclick: () => this.app.selectByPredicate(
        p => p.type === 'Unknown', 'Unclassified pipes'),
    }, 'Select unclassified pipes'));
    f.append(el('button', {
      class: 'btn block ghost',
      onclick: () => this.app.selectByPredicate(
        p => p.source === 'manual', 'Manually overridden pipes'),
    }, 'Select manual overrides'));
    f.append(el('button', {
      class: 'btn block ghost',
      onclick: () => this.app.selectOrphanJoins(),
    }, 'Select unconnected joining points'));
    this.root.append(f);
  }
}

/* ── history ─────────────────────────────────────────────────────────────── */
export class HistoryPanel {
  constructor(app, root) {
    this.app = app; this.root = root;
    app.history.on('change', () => this.render());
    this.render();
  }

  render() {
    this.root.replaceChildren();
    const h = this.app.history;
    const sec = el('div', { class: 'section' },
      el('div', { class: 'section-title' }, 'Recent edits'));
    const items = h.recent(30);
    if (!items.length) {
      sec.append(el('div', { class: 'empty-state' }, 'No edits yet.'));
    }
    for (const it of items) {
      sec.append(el('div', { class: 'hist-item current' },
        el('span', { class: 'hi-idx' }, String(it.index)),
        el('span', {}, it.label || 'edit')));
    }
    this.root.append(sec);

    const row = el('div', { class: 'btn-row' },
      el('button', {
        class: 'btn', onclick: () => this.app.undo(),
        disabled: h.canUndo ? null : 'disabled',
      }, 'Undo'),
      el('button', {
        class: 'btn', onclick: () => this.app.redo(),
        disabled: h.canRedo ? null : 'disabled',
      }, 'Redo'));
    this.root.append(row);
  }
}

/* ── search ──────────────────────────────────────────────────────────────── */
export class Search {
  constructor(app, input, results) {
    this.app = app; this.input = input; this.results = results;
    this.active = 0;
    input.addEventListener('input', () => this.run());
    input.addEventListener('focus', () => this.run());
    input.addEventListener('blur', () => setTimeout(() => this.clear(), 160));
    input.addEventListener('keydown', (e) => this._key(e));
  }

  clear() { this.results.replaceChildren(); }

  matches() {
    const q = this.input.value.trim().toLowerCase();
    if (!q) return [];
    const st = this.app.store, out = [];
    for (const p of st.activePipes()) {
      if (p.id.toLowerCase().includes(q) || p.type.toLowerCase().includes(q)) {
        out.push({ kind: 'pipe', id: p.id, main: p.id, sub: p.type,
                   colour: classColor(p.type) });
      }
      if (out.length > 60) break;
    }
    for (const l of st.activeLabels()) {
      if (l.code.toLowerCase().includes(q) || l.id.toLowerCase().includes(q)) {
        out.push({ kind: 'label', id: l.id, main: l.code, sub: l.id,
                   colour: classColor(l.code) });
      }
      if (out.length > 90) break;
    }
    for (const j of st.activeJoins()) {
      if (j.id.toLowerCase().includes(q) || (j.code || '').toLowerCase().includes(q)) {
        out.push({ kind: 'join', id: j.id, main: j.id, sub: j.code,
                   colour: classColor(j.code) });
      }
      if (out.length > 120) break;
    }
    return out.slice(0, 60);
  }

  run() {
    const items = this.matches();
    this.active = Math.min(this.active, Math.max(0, items.length - 1));
    this.results.replaceChildren();
    items.forEach((m, i) => {
      this.results.append(el('div', {
        class: 'sr-item' + (i === this.active ? ' active' : ''),
        onmousedown: (e) => { e.preventDefault(); this.go(m); },
      },
        el('span', { class: 'sr-swatch', style: `background:${m.colour}` }),
        el('span', { class: 'sr-kind' }, m.kind),
        el('span', { class: 'sr-main' }, m.main),
        el('span', { class: 'lg-n' }, m.sub || '')));
    });
  }

  go(m) {
    this.app.focusObject(m.kind, m.id);
    this.input.blur();
    this.clear();
  }

  _key(e) {
    const items = this.matches();
    if (e.key === 'ArrowDown') { this.active = Math.min(this.active + 1, items.length - 1); this.run(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { this.active = Math.max(this.active - 1, 0); this.run(); e.preventDefault(); }
    else if (e.key === 'Enter' && items[this.active]) { this.go(items[this.active]); }
    else if (e.key === 'Escape') { this.input.value = ''; this.clear(); this.input.blur(); }
    e.stopPropagation();
  }
}

/* ── context menu ────────────────────────────────────────────────────────── */
export class ContextMenu {
  constructor(app, root) {
    this.app = app; this.root = root;
    document.addEventListener('click', () => this.hide());
    document.addEventListener('contextmenu', (e) => {
      if (!this.root.contains(e.target)) this.hide();
    }, true);
  }

  hide() { this.root.classList.add('hidden'); }

  show(x, y, sections) {
    this.root.replaceChildren();
    for (const sec of sections) {
      if (sec.title) this.root.append(el('div', { class: 'cm-title' }, sec.title));
      for (const it of sec.items) {
        if (it === '-') { this.root.append(el('div', { class: 'cm-sep' })); continue; }
        this.root.append(el('div', {
          class: 'cm-item' + (it.danger ? ' danger' : ''),
          onclick: () => { this.hide(); it.action(); },
        }, el('span', {}, it.label),
           it.key ? el('span', { class: 'cm-key' }, it.key) : null));
      }
    }
    this.root.classList.remove('hidden');
    const r = this.root.getBoundingClientRect();
    this.root.style.left = Math.min(x, window.innerWidth - r.width - 8) + 'px';
    this.root.style.top = Math.min(y, window.innerHeight - r.height - 8) + 'px';
  }
}

/* ── minimap ─────────────────────────────────────────────────────────────── */
export class Minimap {
  constructor(app, canvas, viewRect) {
    this.app = app; this.canvas = canvas; this.viewRect = viewRect;
    this.ctx = canvas.getContext('2d');
    this.dirty = true;
    app.store.on('change', () => { this.dirty = true; this.draw(); });
    app.viewport.on('change', () => this.draw());
    canvas.parentElement.addEventListener('pointerdown', (e) => this._jump(e));
    canvas.parentElement.addEventListener('pointermove', (e) => {
      if (e.buttons & 1) this._jump(e);
    });
  }

  _jump(e) {
    const r = this.canvas.getBoundingClientRect();
    const doc = this.app.store.doc;
    if (!doc) return;
    const wx = (e.clientX - r.left) / r.width * doc.page[0];
    const wy = (e.clientY - r.top) / r.height * doc.page[1];
    this.app.viewport.centerOn(wx, wy);
  }

  draw() {
    const doc = this.app.store.doc;
    if (!doc) return;
    const r = this.canvas.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    if (this.canvas.width !== Math.round(r.width * dpr)) {
      this.canvas.width = Math.round(r.width * dpr);
      this.canvas.height = Math.round(r.height * dpr);
      this.dirty = true;
    }
    const ctx = this.ctx;
    const sx = this.canvas.width / doc.page[0];
    const sy = this.canvas.height / doc.page[1];
    const s = Math.min(sx, sy);

    if (this.dirty) {
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.fillStyle = '#14171c';
      ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
      ctx.setTransform(s, 0, 0, s, 0, 0);
      // draw the real outlines — bounding boxes would read as solid blobs
      for (const p of this.app.store.activePipes()) {
        const ring = p.polygon;
        if (ring.length < 3) continue;
        ctx.fillStyle = classColor(p.type);
        ctx.beginPath();
        ctx.moveTo(ring[0][0], ring[0][1]);
        for (let i = 1; i < ring.length; i++) ctx.lineTo(ring[i][0], ring[i][1]);
        ctx.closePath();
        ctx.fill();
      }
      this.dirty = false;
    }

    // viewport rectangle, in CSS pixels of the minimap
    const vb = this.app.viewport.visibleBounds();
    const el_ = this.viewRect;
    const k = s / dpr;
    el_.style.left = (vb[0] * k) + 'px';
    el_.style.top = (vb[1] * k) + 'px';
    el_.style.width = Math.max(4, (vb[2] - vb[0]) * k) + 'px';
    el_.style.height = Math.max(4, (vb[3] - vb[1]) * k) + 'px';
  }
}

/* ── status bar ──────────────────────────────────────────────────────────── */
export class StatusBar {
  constructor(app) {
    this.app = app;
    this.tool = document.getElementById('statTool');
    this.cursor = document.getElementById('statCursor');
    this.zoom = document.getElementById('statZoom');
    this.counts = document.getElementById('statCounts');
    this.sel = document.getElementById('statSel');
    this.saved = document.getElementById('statSaved');

    app.viewport.on('change', () => this.updateZoom());
    app.store.on('selection', () => this.updateSelection());
    app.store.on('change', () => this.updateCounts());
    app.on('tool', (t) => {
      this.tool.textContent = t.constructor.title;
      this.app.setHint(t.status());
    });
  }

  updateCursor(w) {
    this.cursor.textContent = `x ${fmt(w[0])}, y ${fmt(w[1])} pt`;
  }

  updateZoom() {
    this.zoom.textContent = `${Math.round(this.app.viewport.z * 100)}%`;
  }

  updateCounts() {
    const s = this.app.store;
    if (!s.doc) return;
    this.counts.textContent =
      `${s.activePipes().length} pipes · ${s.activeLabels().length} labels · ` +
      `${s.activeJoins().length} joins`;
    this.saved.textContent = s.saved ? 'Saved' : 'Unsaved changes';
    this.saved.classList.toggle('unsaved', !s.saved);
  }

  updateSelection() {
    const n = this.app.store.selection.size;
    this.sel.textContent = n ? `${n} selected` : 'No selection';
  }
}
