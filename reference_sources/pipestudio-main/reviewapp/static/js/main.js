// Application shell: wires the store, renderer, tools and panels together and
// owns the high-level commands (assignment, file operations, focus helpers).

import { api } from './api.js';
import { ClassCombo } from './combo.js';
import { History } from './history.js';
import { Inspector } from './inspector.js';
import {
  ContextMenu, HistoryPanel, LayersPanel, Minimap, Search, StatusBar,
} from './panels.js';
import { Renderer } from './renderer.js';
import { installShortcuts, shortcutDialog } from './shortcuts.js';
import { Store } from './store.js';
import { ToolManager } from './tools/index.js';
import { AddJoinTool, AddLabelTool } from './tools/annotate.js';
import {
  DrawPipeTool, EditVertexTool, MergeTool, SplitTool,
} from './tools/geometry.js';
import { ConnectTool } from './tools/connect.js';
import { LinkTool } from './tools/link.js';
import { PanTool, SelectTool } from './tools/select.js';
import { Viewport } from './viewport.js';
import { Wizard } from './wizard.js';
import {
  Emitter, classColor, debounce, el, polyBounds, simplify, smooth,
} from './util.js';
import {
  centroid, closestOnRing, localAngle, principalAngle, splitRingByLine,
} from './polyops.js';

class App extends Emitter {
  constructor() {
    super();
    this.canvas = document.getElementById('scene');
    this.store = new Store();
    this.viewport = new Viewport(this.canvas);
    this.renderer = new Renderer(this.canvas, this.store, this.viewport);
    this.history = new History(this.store);
    this.tools = new ToolManager(this);
    this.contextMenu = new ContextMenu(this, document.getElementById('contextMenu'));

    this._autosave = debounce(() => this.autosave(), 1500);
  }

  /* ── boot ─────────────────────────────────────────────────────────────── */
  async start() {
    this.buildToolbar();
    installShortcuts(this);
    this.bindTopbar();
    this.bindTabs();
    this.bindCanvas();

    this.status = new StatusBar(this);
    new Search(this, document.getElementById('search'),
               document.getElementById('searchResults'));

    await this.waitForDocument();

    this.inspector = new Inspector(this, document.getElementById('tab-inspect'));
    this.layersPanel = new LayersPanel(this, document.getElementById('tab-layers'));
    this.historyPanel = new HistoryPanel(this, document.getElementById('tab-history'));
    this.minimap = new Minimap(this, document.getElementById('minimapCanvas'),
                               document.getElementById('minimapView'));
    this.wizard = new Wizard(this, document.getElementById('wizard'));

    this.viewport.on('change', () => this.renderer.invalidate());
    this.store.on('change', () => {
      this._autosave();
      this.updateAssignmentState();
      this.status.updateCounts();
    });
    this.store.on('selection', () => this.renderer.invalidate());
    this.store.on('hover', () => this.renderer.invalidate());
    this.history.on('change', () => this.updateUndoRedo());

    window.addEventListener('resize', () => this.renderer.resize());
    window.addEventListener('beforeunload', (e) => {
      if (!this.store.saved) { e.preventDefault(); e.returnValue = ''; }
    });

    this.renderer.resize();
    this.fit();
    this.updateAssignmentState();
    this.updateUndoRedo();
    this.status.updateCounts();
    this.status.updateZoom();
  }

  async waitForDocument() {
    const bootStage = document.getElementById('bootStage');
    const bootBar = document.getElementById('bootBar');
    for (;;) {
      const doc = await api.document().catch(() => null);
      if (doc && doc.pipes) {
        bootStage.textContent = 'Loading background…';
        bootBar.style.width = '97%';
        this.store.load(doc);
        document.getElementById('docName').textContent = doc.stem;
        await this.loadBackground(doc.background);
        this.renderer.rebuildAll();
        bootBar.style.width = '100%';
        const boot = document.getElementById('boot');
        boot.classList.add('done');
        setTimeout(() => boot.classList.add('hidden'), 400);
        return;
      }
      const p = await api.progress().catch(() => null);
      if (p) {
        bootStage.textContent = p.stage;
        bootBar.style.width = `${Math.round((p.value || 0) * 92)}%`;
      }
      await new Promise(r => setTimeout(r, 350));
    }
  }

  loadBackground(url) {
    return new Promise((resolve) => {
      const img = new Image();
      img.onload = () => { this.renderer.setBackground(img); resolve(); };
      img.onerror = () => resolve();
      img.src = url;
    });
  }

  /* ── toolbar ──────────────────────────────────────────────────────────── */
  buildToolbar() {
    for (const T of [SelectTool, PanTool, null, DrawPipeTool, EditVertexTool,
                     SplitTool, MergeTool, null, AddLabelTool, AddJoinTool,
                     ConnectTool, LinkTool]) {
      if (T) this.tools.register(T);
    }
    const bar = document.getElementById('toolbar');
    const groups = [
      [SelectTool, PanTool],
      [DrawPipeTool, EditVertexTool, SplitTool, MergeTool],
      [AddLabelTool, AddJoinTool, ConnectTool, LinkTool],
    ];
    groups.forEach((group, gi) => {
      if (gi) bar.append(el('div', { class: 'tool-sep' }));
      for (const T of group) {
        bar.append(el('button', {
          class: 'tool', 'data-tool': T.id,
          'data-tip': `${T.title} (${T.key})`,
          html: `<svg viewBox="0 0 24 24">${T.icon}</svg>`,
          onclick: () => this.tools.activate(T.id),
        }));
      }
    });
    bar.append(el('div', { class: 'tool-sep' }));
    bar.append(el('button', {
      class: 'tool', 'data-tip': 'Keyboard shortcuts (?)',
      html: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M9.6 9a2.5 2.5 0 1 1 3.4 2.3c-.6.3-1 .9-1 1.6v.3"/><circle cx="12" cy="17" r=".6" fill="currentColor"/></svg>',
      onclick: () => this.showShortcuts(),
    }));

    this.on('tool', (t) => {
      for (const b of bar.querySelectorAll('.tool[data-tool]')) {
        b.classList.toggle('active', b.dataset.tool === t.constructor.id);
      }
      this.canvas.style.cursor = t.constructor.cursor;
    });
  }

  /** Restrict the toolbar to the tools a wizard step allows. */
  setAvailableTools(ids) {
    this.allowedTools = new Set(ids);
    for (const b of document.querySelectorAll('#toolbar .tool[data-tool]')) {
      b.classList.toggle('disabled', !this.allowedTools.has(b.dataset.tool));
    }
  }

  bindTabs() {
    for (const tab of document.querySelectorAll('.tab')) {
      tab.addEventListener('click', () => {
        for (const t of document.querySelectorAll('.tab')) {
          t.classList.toggle('active', t === tab);
        }
        for (const body of document.querySelectorAll('.tab-body')) {
          body.classList.toggle('hidden', body.id !== `tab-${tab.dataset.tab}`);
        }
      });
    }
  }

  bindTopbar() {
    document.getElementById('btnUndo').onclick = () => this.undo();
    document.getElementById('btnRedo').onclick = () => this.redo();
    document.getElementById('btnFit').onclick = () => this.fit();
    document.getElementById('btnZoomSel').onclick = () => this.zoomToSelection();
    document.getElementById('btnSave').onclick = () => this.save();
    document.getElementById('btnReassign').onclick = () => this.reassign();
    document.getElementById('btnMenu').onclick = (e) => {
      e.stopPropagation();
      const r = e.currentTarget.getBoundingClientRect();
      this.contextMenu.show(r.left - 150, r.bottom + 6, [{
        title: 'File',
        items: [
          { label: 'Save review', key: '⌘S', action: () => this.save() },
          { label: 'Export pipes JSON', action: () => this.exportJSON() },
          { label: 'Export painted PNG', action: () => this.exportPNG() },
          '-',
          { label: 'Keyboard shortcuts', key: '?', action: () => this.showShortcuts() },
          '-',
          { label: 'Reset session (re-process PDF)', danger: true,
            action: () => this.resetSession() },
        ],
      }]);
    };
  }

  /* ── canvas interaction ───────────────────────────────────────────────── */
  bindCanvas() {
    const c = this.canvas;
    const world = (e) => {
      const r = c.getBoundingClientRect();
      return this.viewport.toWorld(e.clientX - r.left, e.clientY - r.top);
    };

    c.addEventListener('pointerdown', (e) => {
      c.setPointerCapture(e.pointerId);
      if (e.button === 1) {                      // middle-drag pans
        this._midPan = { x: e.clientX, y: e.clientY };
        c.classList.add('grabbing');
        e.preventDefault();
        return;
      }
      if (e.button !== 0) return;
      this.tools.current?.onPointerDown(e, world(e));
    });

    c.addEventListener('pointermove', (e) => {
      const w = world(e);
      this.status.updateCursor(w);
      if (this._midPan) {
        this.viewport.panBy(e.clientX - this._midPan.x, e.clientY - this._midPan.y);
        this._midPan = { x: e.clientX, y: e.clientY };
        return;
      }
      this.tools.current?.onPointerMove(e, w);
    });

    const up = (e) => {
      if (this._midPan) {
        this._midPan = null;
        c.classList.remove('grabbing');
        return;
      }
      this.tools.current?.onPointerUp(e, world(e));
    };
    c.addEventListener('pointerup', up);
    c.addEventListener('pointercancel', up);

    c.addEventListener('dblclick', (e) =>
      this.tools.current?.onDoubleClick(e, world(e)));

    c.addEventListener('wheel', (e) => {
      e.preventDefault();
      const r = c.getBoundingClientRect();
      const f = e.deltaY < 0 ? 1.12 : 1 / 1.12;
      this.viewport.zoomAt(e.clientX - r.left, e.clientY - r.top, f);
    }, { passive: false });

    c.addEventListener('contextmenu', (e) => {
      e.preventDefault();
      const w = world(e);
      const hit = this.renderer.hitTest(w[0], w[1]);
      if (hit && !this.store.isSelected(hit.kind, hit.id)) {
        this.store.select([{ kind: hit.kind, id: hit.id }]);
      }
      this.showContextMenu(e.clientX, e.clientY, hit);
    });
  }

  showContextMenu(x, y, hit) {
    const sel = this.store.selectionList();
    if (!hit && !sel.length) {
      return this.contextMenu.show(x, y, [{
        title: 'View',
        items: [
          { label: 'Fit to screen', key: 'F', action: () => this.fit() },
          { label: 'Select all', key: '⌘A', action: () => this.store.selectAll() },
        ],
      }]);
    }
    const kind = hit?.kind || sel[0].kind;
    const items = [];
    if (kind === 'pipe') {
      items.push(
        { label: 'Change class…', action: () => this.promptClassFor(sel) },
        { label: 'Edit polygon', key: 'E', action: () => this.tools.activate('vertex') },
        { label: 'Split pipe', key: 'X', action: () => this.tools.activate('split') },
      );
      if (sel.filter(s => s.kind === 'pipe').length >= 2) {
        items.push({ label: 'Merge pipes', key: 'M', action: () => this.mergeSelectedPipes() });
      }
      items.push({ label: 'Simplify', action: () => this.simplifySelected() },
                 { label: 'Smooth', action: () => this.smoothSelected() }, '-');
    } else if (kind === 'label') {
      items.push(
        { label: 'Edit text…', action: () => this.promptClassFor(sel) },
        { label: 'Duplicate', key: '⌘D', action: () => this.duplicateSelection() },
        { label: 'Add joining point', key: 'J', action: () => this.tools.activate('join') },
        '-');
    } else {
      items.push(
        { label: 'Snap to nearest pipe', action: () => this.snapJoinToPipe(hit?.id || sel[0].id) },
        { label: 'Change class…', action: () => this.promptClassFor(sel) },
        '-');
    }
    items.push({ label: 'Zoom to object', key: '⇧F', action: () => this.zoomToSelection() });
    items.push({ label: `Delete ${sel.length > 1 ? sel.length + ' objects' : kind}`,
                 key: 'Del', danger: true, action: () => this.deleteSelection() });
    this.contextMenu.show(x, y, [{ title: kind, items }]);
  }

  /* ── commands ─────────────────────────────────────────────────────────── */
  undo() {
    const label = this.history.undo();
    if (label) { this.renderer.rebuildAll(); this.toast(`Undo: ${label}`); }
    this.updateUndoRedo();
  }

  redo() {
    const label = this.history.redo();
    if (label) { this.renderer.rebuildAll(); this.toast(`Redo: ${label}`); }
    this.updateUndoRedo();
  }

  updateUndoRedo() {
    document.getElementById('btnUndo').disabled = !this.history.canUndo;
    document.getElementById('btnRedo').disabled = !this.history.canRedo;
  }

  deleteSelection() {
    const sel = this.store.selectionList();
    if (!sel.length) return;
    this.history.run(`Delete ${sel.length} object(s)`, () => {
      for (const s of sel) this.store.remove(s.kind, s.id);
    });
    this.renderer.rebuildAll();
    this.toast(`Deleted ${sel.length} object(s) — Undo with ⌘Z`);
  }

  restoreSelection() {
    const sel = this.store.selectionList();
    this.history.run('Restore objects', () => {
      for (const s of sel) this.store.restore(s.kind, s.id);
    });
    this.renderer.rebuildAll();
  }

  duplicateSelection() {
    const sel = this.store.selectionList();
    if (!sel.length) return;
    const made = [];
    this.history.run('Duplicate', () => {
      for (const s of sel) {
        if (s.kind === 'label') {
          const r = s.obj.rect;
          const h = r[3] - r[1];
          made.push({ kind: 'label',
            id: this.store.addLabel([r[0], r[1] + h * 1.4, r[2], r[3] + h * 1.4],
                                    s.obj.code).id });
        } else if (s.kind === 'pipe') {
          const poly = s.obj.polygon.map(([x, y]) => [x + 6, y + 6]);
          made.push({ kind: 'pipe', id: this.store.addPipe(poly, s.obj.type).id });
        } else {
          made.push({ kind: 'join',
            id: this.store.addJoin([s.obj.point[0] + 6, s.obj.point[1] + 6],
                                   s.obj.code, s.obj.labelId).id });
        }
      }
    });
    this.renderer.rebuildAll();
    this.store.select(made);
    this.toast(`Duplicated ${made.length} object(s)`);
  }

  simplifySelected() {
    const pipes = this.store.selectionList().filter(s => s.kind === 'pipe');
    if (!pipes.length) return;
    this.history.run('Simplify polygon', () => {
      for (const { obj } of pipes) {
        const before = obj.polygon.length;
        obj.polygon = simplify(obj.polygon, 0.35);
        this.store.recomputeStats(obj);
        this.renderer.invalidateObject('pipe', obj.id);
        if (before !== obj.polygon.length) this.store.touch('pipe:geometry', obj.id);
      }
    });
    this.renderer.invalidate();
    this.toast('Simplified');
  }

  smoothSelected() {
    const pipes = this.store.selectionList().filter(s => s.kind === 'pipe');
    if (!pipes.length) return;
    this.history.run('Smooth polygon', () => {
      for (const { obj } of pipes) {
        obj.polygon = smooth(obj.polygon, 1);
        this.store.recomputeStats(obj);
        this.renderer.invalidateObject('pipe', obj.id);
        this.store.touch('pipe:geometry', obj.id);
      }
    });
    this.renderer.invalidate();
    this.toast('Smoothed');
  }

  async mergeSelectedPipes() {
    const pipes = this.store.selectionList().filter(s => s.kind === 'pipe');
    if (pipes.length < 2) {
      this.toast('Select two or more pipes to merge', 'error');
      return;
    }
    try {
      const { rings } = await api.mergeRings(pipes.map(p => p.obj.polygon));
      if (!rings?.length) throw new Error('merge produced no geometry');
      const type = pipes.find(p => p.obj.type !== 'Unknown')?.obj.type || 'Unknown';
      const manual = pipes.some(p => p.obj.source === 'manual');
      const made = [];
      this.history.run(`Merge ${pipes.length} pipes`, () => {
        for (const p of pipes) this.store.remove('pipe', p.id);
        for (const ring of rings) {
          const np = this.store.addPipe(ring, type);
          np.source = manual ? 'manual' : 'auto';
          made.push({ kind: 'pipe', id: np.id });
        }
        this.store.touch('pipe:merge');
      });
      this.renderer.rebuildAll();
      this.store.select(made);
      this.toast(rings.length === 1
        ? `Merged ${pipes.length} pipes into ${made[0].id}`
        : `Merged ${pipes.length} pipes into ${rings.length} polygons`);
    } catch (err) {
      this.toast(`Merge failed: ${err.message}`, 'error');
    }
  }

  /**
   * Merge every polygon that is really the SAME pipe broken into pieces,
   * across the whole drawing, without selecting anything.
   *
   * Only end-to-end continuations are joined — one piece carrying on where
   * the other stops.  Pipes that cross, or that run alongside each other, are
   * two different pipes and are left alone.  One undo step puts it all back.
   */
  async autoMergeSamePipe() {
    const pipes = this.store.activePipes();
    if (pipes.length < 2) {
      this.toast('Nothing to merge', 'error');
      return;
    }
    this.toast('Looking for pipes split into pieces…');
    try {
      const { groups, skipped } = await api.autoMerge(pipes.map(p => p.polygon));
      // groups that would have closed a loop, or painted over the gap between
      // two pipes meeting at an angle, are reported rather than done quietly
      const held = skipped ? ` · ${skipped} left alone` : '';
      if (!groups?.length) {
        this.toast('No split pipes found — every polygon is already one pipe'
                   + held);
        return;
      }
      const made = [];
      const absorbed = groups.reduce((n, g) => n + g.indices.length, 0);
      this.history.run(`Merge ${absorbed} polygons into ${groups.length} pipes`, () => {
        for (const g of groups) {
          const members = g.indices.map(i => pipes[i]);
          // keep whatever the pieces already knew: a class if any of them had
          // one, and manual origin if the user drew any of them
          const type = members.find(p => p.type && p.type !== 'Unknown')?.type
                       || 'Unknown';
          const manual = members.some(p => p.source === 'manual');
          for (const p of members) this.store.remove('pipe', p.id);
          const np = this.store.addPipe(g.ring, type);
          np.source = manual ? 'manual' : 'auto';
          made.push({ kind: 'pipe', id: np.id });
        }
        this.store.touch('pipe:merge');
      });
      this.renderer.rebuildAll();
      this.store.select(made);
      this.toast(`Merged ${absorbed} polygons into ${groups.length} pipes — ` +
                 `${this.store.activePipes().length} pipes now${held} (⌘Z to undo)`);
    } catch (err) {
      this.toast(`Merge failed: ${err.message}`, 'error');
    }
  }

  /** Give a pipe the class of a label the user clicked (manual override). */
  setPipeClassFromLabel(pipeId, labelId) {
    const p = this.store.pipeById.get(pipeId);
    const l = this.store.labelById.get(labelId);
    if (!p || !l || !l.code) {
      this.toast('That label has no class code', 'error');
      return false;
    }
    this.history.run(`Set ${p.id} class from ${l.id}`, () =>
      this.store.setPipeClass(p.id, l.code));
    this.renderer.invalidateObject('pipe', p.id);
    this.renderer.invalidate();
    this.toast(`${p.id} → “${l.code}” from ${l.id} (manual override)`);
    return true;
  }

  /** Re-point a joining point at a label; its class flows to the pipes. */
  linkJoinToLabel(joinId, labelId) {
    let res = null;
    this.history.run('Link joining point to label', () => {
      res = this.store.linkJoinToLabel(joinId, labelId);
      if (!res) return;
      const targets = (res.join.pipeIds?.length ? res.join.pipeIds
                                                : [res.join.pipeId]).filter(Boolean);
      for (const pid of targets) {
        const p = this.store.pipeById.get(pid);
        if (p && p.source !== 'manual') { p.type = res.label.code; }
      }
    });
    if (!res) { this.toast('Could not link those two', 'error'); return null; }
    this.renderer.rebuildAll();
    const n = (res.join.pipeIds?.length || (res.join.pipeId ? 1 : 0));
    this.toast(`${res.join.id} → ${res.label.id} · class “${res.label.code}” ` +
               `applied to ${n} pipe${n === 1 ? '' : 's'}`);
    return res;
  }

  /**
   * The joining-point workflow, in one step:
   *   1. split the pipe polygon at the joining point
   *   2. link the associated label through a leader line
   *   3. give the claimed side the label's class
   * No manual class selection is required.
   */
  placeJoiningPoint(point, pipe, label) {
    const code = label?.code || '';
    let made = null;
    this.history.begin('Add joining point');
    try {
      const j = this.store.addJoin(point, code, label?.id || null);

      // 1. split the pipe polygon at the joining point.  The cut is square to
      //    the pipe's LOCAL direction there, so a run that turns a corner is
      //    still one pipe and only the leg carrying the joining point is cut.
      const ang = localAngle(pipe.polygon, point);
      const parts = splitRingByLine(pipe.polygon, point, ang + Math.PI / 2);
      let claimed = pipe;
      if (parts) {
        this.store.remove('pipe', pipe.id);
        const a = this.store.addPipe(parts[0], pipe.type);
        const b = this.store.addPipe(parts[1], pipe.type);
        for (const np of [a, b]) np.source = pipe.source;
        this.store.touch('pipe:split', pipe.id);
        // 3. the claimed side is the one left of / above the joining point
        claimed = this._claimedSide([a, b], point, ang);
      }

      // 2. leader line from the label to the joining point (annotation only)
      if (label) {
        const anchor = [(label.rect[0] + label.rect[2]) / 2,
                        (label.rect[1] + label.rect[3]) / 2];
        // the drawing's own leader line is what the user sees; this records
        // the link, and is only hinted at on screen when nothing is drawn
        this.store.addLeader([[anchor, point.slice()]],
                             { labelId: label.id, joinId: j.id, code });
        j.anchor = anchor;
      }

      if (code && claimed) {
        claimed.type = code;
        claimed.source = 'auto';
        j.pipeId = claimed.id;
        j.pipeIds = [claimed.id];
      }
      this.history.commit();
      made = { join: j, pipe: claimed };
    } catch (err) {
      this.history.cancel();
      this.toast(`Could not place joining point: ${err.message}`, 'error');
      return null;
    }
    this.renderer.rebuildAll();
    this.store.select([{ kind: 'join', id: made.join.id }]);
    const cut = made.pipe !== pipe;
    this.toast(label
      ? (cut ? `Split ${pipe.id} at the joining point — class “${code}” from ${label.id}`
             : `Joining point added on ${pipe.id} — class “${code}” from ${label.id}; ` +
               `the pipe is cut here when classification runs`)
      : `Joining point added — no label nearby, pipe left Unknown`);
    return made;
  }

  /**
   * Of two split halves, the stretch this joining point starts.
   * The class goes to the LEFT of the joining point (ABOVE it for a vertical
   * pipe) — matching pipe_types TYPE_CONFIG["claim_direction"] = "backward".
   */
  _claimedSide(parts, point, ang) {
    // read left/above along the pipe's local direction at the joining point
    const a = ang ?? localAngle(parts[0].polygon, point);
    const horizontal = Math.abs(Math.cos(a)) >= Math.SQRT1_2;
    let best = parts[0], bestKey = Infinity;
    for (const p of parts) {
      const c = centroid(p.polygon);
      const key = horizontal ? c[0] - point[0] : c[1] - point[1];
      if (key < bestKey) { bestKey = key; best = p; }
    }
    return best;
  }

  /** Grow (+1) or shrink (-1) the capture radius of every selected join. */
  resizeSelectedJoins(dir, step = 1.0) {
    const joins = this.store.selectionList().filter(s => s.kind === 'join');
    if (!joins.length) return;
    this.history.run(`Resize ${joins.length} joining point(s)`, () => {
      for (const { obj } of joins) {
        this.store.setJoinRadius(obj.id, (obj.radius ?? 6) + dir * step);
        this.renderer.invalidateObject('join', obj.id);
      }
    });
    this.renderer.invalidate();
    if (joins.length === 1) {
      this.toast(`${joins[0].id} capture radius ` +
                 `${joins[0].obj.radius.toFixed(1)} pt`);
    }
  }

  snapJoinToPipe(id) {
    const j = this.store.joinById.get(id);
    if (!j) return;
    let best = null, bestD = Infinity;
    for (const p of this.store.activePipes()) {
      const { point, dist } = closestOnRing(p.polygon, j.point[0], j.point[1]);
      if (dist < bestD) { bestD = dist; best = { point, pipe: p }; }
    }
    if (!best) return;
    this.history.run('Snap joining point', () => {
      j.point = [+best.point[0].toFixed(2), +best.point[1].toFixed(2)];
      j.pipeId = best.pipe.id;
      this.store.touch('join:move', j.id);
    });
    this.renderer.invalidateObject('join', j.id);
    this.renderer.invalidate();
    this.toast(`Snapped to ${best.pipe.id}`);
  }

  /* ── selection helpers ────────────────────────────────────────────────── */
  selectByClass(code) {
    const items = this.store.activePipes().filter(p => p.type === code)
      .map(p => ({ kind: 'pipe', id: p.id }));
    this.store.select(items);
    this.toast(`${items.length} pipes of class ${code}`);
    this.zoomToSelection();
  }

  selectByPredicate(fn, label) {
    const items = this.store.activePipes().filter(fn)
      .map(p => ({ kind: 'pipe', id: p.id }));
    this.store.select(items);
    this.toast(`${items.length} · ${label}`);
  }

  selectOrphanJoins() {
    const items = this.store.activeJoins().filter(j => !j.pipeId)
      .map(j => ({ kind: 'join', id: j.id }));
    this.store.select(items);
    this.toast(`${items.length} unconnected joining points`);
  }

  focusObject(kind, id) {
    const o = this.store.get(kind, id);
    if (!o) return;
    this.store.select([{ kind, id }]);
    const b = kind === 'pipe' ? polyBounds(o.polygon)
            : kind === 'label' ? o.rect
            : [o.point[0] - 14, o.point[1] - 14, o.point[0] + 14, o.point[1] + 14];
    this.viewport.animateTo({ bounds: b });
  }

  fit() {
    const doc = this.store.doc;
    if (doc) this.viewport.fitBounds([0, 0, doc.page[0], doc.page[1]]);
  }

  zoomToSelection() {
    const sel = this.store.selectionList();
    if (!sel.length) return this.fit();
    let b = [Infinity, Infinity, -Infinity, -Infinity];
    for (const s of sel) {
      const ob = s.kind === 'pipe' ? polyBounds(s.obj.polygon)
               : s.kind === 'label' ? s.obj.rect
               : [s.obj.point[0] - 10, s.obj.point[1] - 10,
                  s.obj.point[0] + 10, s.obj.point[1] + 10];
      b = [Math.min(b[0], ob[0]), Math.min(b[1], ob[1]),
           Math.max(b[2], ob[2]), Math.max(b[3], ob[3])];
    }
    this.viewport.animateTo({ bounds: b });
  }

  toggleLayer(key) {
    const L = this.store.layers[key];
    L.on = !L.on;
    this.renderer.invalidate();
    this.layersPanel?.render();
    this.toast(`${key} ${L.on ? 'shown' : 'hidden'}`);
  }

  /* ── assignment ───────────────────────────────────────────────────────── */
  updateAssignmentState() {
    const n = this.store.dirtyEdits;
    const pill = document.getElementById('assignState');
    const text = document.getElementById('assignText');
    const btn = document.getElementById('btnReassign');
    if (n > 0) {
      pill.className = 'assign-state stale';
      text.textContent = `Results require recomputation — ${n} edit${n === 1 ? '' : 's'}`;
      btn.classList.add('attention');
    } else {
      pill.className = 'assign-state ok';
      text.textContent = 'Results are up to date';
      btn.classList.remove('attention');
    }
  }

  /**
   * Step 5: classify the REVIEWED SEGMENTATION (splits it at joining points).
   *
   * Every run replaces the previous result. If the document already holds a
   * classified set — after a reload, or coming back to this step — the
   * segmentation is put back first, so classification never splits its own
   * output again and leaves the old polygons stacked underneath.
   */
  async classify() {
    if (this.store.isClassified) this.store.restoreBaseSegmentation();
    else this.store.syncBaseFromPipes();
    return this.reassign();
  }

  async reassign() {
    const btn = document.getElementById('btnReassign');
    btn.disabled = true;
    this.toast('Re-running label assignment…');
    try {
      const res = await api.reassign(this.store.toPayload());
      this.store.load(res.document);
      this.store.markAssigned();
      this.store.markSaved();
      this.history.reset();
      this.renderer.rebuildAll();
      const s = res.summary;
      this.toast(
        `Assignment complete — ${s.typedPipes} pipes classified, ` +
        `${s.unknown} Unknown, ${s.manual} manual override(s) preserved`,
        'success');
    } catch (err) {
      this.toast(`Assignment failed: ${err.message}`, 'error');
    } finally {
      btn.disabled = false;
      this.updateAssignmentState();
    }
  }

  /* ── file ─────────────────────────────────────────────────────────────── */
  async save() {
    try {
      await api.save(this.store.toPayload());
      this.store.markSaved();
      this.status.updateCounts();
      this.toast('Review saved', 'success');
    } catch (err) { this.toast(`Save failed: ${err.message}`, 'error'); }
  }

  async autosave() {
    try {
      await api.autosave(this.store.toPayload());
      this.store.markSaved();
      this.status.updateCounts();
    } catch { /* autosave stays silent */ }
  }

  async exportJSON() {
    try {
      const r = await api.exportJSON(this.store.toPayload());
      this.toast(`Exported ${r.pipes} pipes → ${r.path}`, 'success');
    } catch (err) { this.toast(`Export failed: ${err.message}`, 'error'); }
  }

  async exportPNG() {
    this.toast('Rendering PNG at 300 DPI…');
    try {
      const r = await api.exportPNG(this.store.toPayload());
      this.toast(`Exported → ${r.paths.join(', ')}`, 'success');
    } catch (err) { this.toast(`Export failed: ${err.message}`, 'error'); }
  }

  async resetSession() {
    if (!confirm('Discard all edits and re-process the PDF from scratch?')) return;
    this.toast('Re-processing the drawing…');
    try {
      const r = await api.reset();
      this.store.load(r.document);
      this.history.reset();
      this.renderer.rebuildAll();
      this.fit();
      this.toast('Session reset', 'success');
    } catch (err) { this.toast(`Reset failed: ${err.message}`, 'error'); }
  }

  /* ── small UI helpers ─────────────────────────────────────────────────── */
  toast(msg, kind = '') {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.className = `toast show ${kind}`;
    clearTimeout(this._toastT);
    this._toastT = setTimeout(() => { t.className = 'toast'; }, 3400);
  }

  setHint(text) { if (text) this.toast(text); }

  /** Transient hint in the status bar (no toast). */
  setHint2(text) {
    if (this.store.selection.size && !text) return this.status.updateSelection();
    document.getElementById('statSel').textContent =
      text || (this.store.selection.size ? `${this.store.selection.size} selected`
                                         : 'No selection');
  }


  modal(content) {
    const back = document.getElementById('modal');
    const body = document.getElementById('modalBody');
    body.replaceChildren(content);
    back.classList.remove('hidden');
    const close = () => back.classList.add('hidden');
    back.onclick = (e) => { if (e.target === back) close(); };
    window.addEventListener('keydown', function esc(e) {
      if (e.key === 'Escape') { close(); window.removeEventListener('keydown', esc); }
    });
    return close;
  }

  showShortcuts() { this.modal(shortcutDialog()); }

  /** Modal class picker; resolves to a code or null. */
  promptClass(title, initial) {
    return new Promise((resolve) => {
      const wrap = el('div');
      wrap.append(el('h2', {}, title));
      let done = false;
      const finish = (v) => { if (!done) { done = true; close(); resolve(v); } };
      const combo = new ClassCombo(this, initial, (code) => finish(code),
                                   { free: true });
      wrap.append(combo.element);
      wrap.append(el('div', { class: 'btn-row' },
        el('button', { class: 'btn ghost', onclick: () => finish(null) }, 'Cancel'),
        el('button', {
          class: 'btn primary',
          onclick: () => finish(combo.input.value.trim() || null),
        }, 'OK')));
      const close = this.modal(wrap);
      setTimeout(() => combo.input.focus(), 40);
    });
  }

  async promptClassFor(sel) {
    const code = await this.promptClass('Set class', sel[0]?.obj.type || sel[0]?.obj.code || '');
    if (!code) return;
    this.history.run('Set class', () => {
      for (const s of sel) {
        if (s.kind === 'pipe') this.store.setPipeClass(s.id, code);
        else if (s.kind === 'label') {
          s.obj.code = code; s.obj.source = 'manual';
          this.store.touch('label:text', s.id);
        } else { s.obj.code = code; this.store.touch('join:move', s.id); }
      }
    });
    this.renderer.rebuildAll();
  }

  /* ── geometry helpers used by tools ───────────────────────────────────── */
  medianPipeHalfWidth() {
    const ws = this.store.activePipes()
      .map(p => (p.length > 0 ? p.area / p.length / 2 : 0))
      .filter(w => w > 0.1 && w < 4)
      .sort((a, b) => a - b);
    return ws.length ? ws[Math.floor(ws.length / 2)] : 0.72;
  }

  distanceToRing(w, ring) {
    return closestOnRing(ring, w[0], w[1]).dist;
  }
}

const app = new App();
window.__app = app;          // handy for debugging in the console
app.start();
