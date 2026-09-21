// Central state: the document, selection, layers and the dirty/assignment
// state.  Everything else observes this store; nothing else mutates the
// document without going through here (so history and rendering stay in sync).

import { Emitter, polyArea, uid } from './util.js';

// Edits that invalidate the automatic assignment.  A manual class override is
// deliberately NOT in this list.
export const STRUCTURAL = new Set([
  'pipe:create', 'pipe:delete', 'pipe:restore', 'pipe:geometry',
  'pipe:split', 'pipe:merge',
  'label:create', 'label:delete', 'label:move', 'label:text',
  'join:create', 'join:delete', 'join:move', 'join:resize', 'join:relink',
  'leader:create', 'leader:delete',
]);

// capture radius of a joining point, in page points
export const JOIN_RADIUS = { default: 3.5, min: 1.5, max: 60 };

export class Store extends Emitter {
  constructor() {
    super();
    this.doc = null;
    this.pipeById = new Map();
    this.labelById = new Map();
    this.joinById = new Map();
    this.selection = new Set();          // "kind:id"
    this.hover = null;
    this.dirtyEdits = 0;
    this.saved = true;
    this.layers = {
      background: { on: true, locked: false, opacity: 1 },
      wall:       { on: true, locked: true,  opacity: 1 },
      pipes:      { on: true, locked: false, opacity: 1 },
      labels:     { on: true, locked: false, opacity: 1 },
      joins:      { on: true, locked: false, opacity: 1 },
      leaders:    { on: true, locked: true,  opacity: 1 },
    };
  }

  /* ── loading ──────────────────────────────────────────────────────────── */
  load(doc) {
    this.doc = doc;
    this.reindex();
    this.dirtyEdits = doc.dirty_edits || 0;
    this.selection.clear();
    this.emit('load', doc);
    this.emit('change', { reason: 'load' });
  }

  reindex() {
    this.pipeById = new Map(this.doc.pipes.map(p => [p.id, p]));
    this.labelById = new Map(this.doc.labels.map(l => [l.id, l]));
    this.joinById = new Map(this.doc.joins.map(j => [j.id, j]));
    if (!this.doc.leaders) this.doc.leaders = [];
    if (!this.doc.base_pipes) this.doc.base_pipes = [];
    this.leaderById = new Map(this.doc.leaders.map(x => [x.id, x]));
  }

  get pipes() { return this.doc ? this.doc.pipes : []; }
  get labels() { return this.doc ? this.doc.labels : []; }
  get joins() { return this.doc ? this.doc.joins : []; }
  get leaders() { return this.doc && this.doc.leaders ? this.doc.leaders : []; }

  activePipes() { return this.pipes.filter(p => !p.deleted); }
  activeLabels() { return this.labels.filter(l => !l.deleted); }
  activeJoins() { return this.joins.filter(j => !j.deleted); }
  activeLeaders() { return this.leaders.filter(x => !x.deleted); }

  get(kind, id) {
    return kind === 'pipe' ? this.pipeById.get(id)
         : kind === 'label' ? this.labelById.get(id)
         : kind === 'leader' ? this.leaderById.get(id)
         : this.joinById.get(id);
  }

  classes() {
    const s = new Set(this.doc?.classes || []);
    for (const p of this.pipes) if (p.type && p.type !== 'Unknown') s.add(p.type);
    for (const l of this.labels) if (l.code) s.add(l.code);
    return [...s].sort();
  }

  classCounts() {
    const m = new Map();
    for (const p of this.activePipes()) m.set(p.type, (m.get(p.type) || 0) + 1);
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }

  /* ── edit bookkeeping ─────────────────────────────────────────────────── */
  /**
   * Record that an edit happened.  `kind` decides whether the automatic
   * assignment becomes stale.
   */
  touch(kind, detail) {
    this.saved = false;
    if (STRUCTURAL.has(kind)) {
      this.dirtyEdits++;
      this.emit('dirty', this.dirtyEdits);
    }
    this.emit('change', { reason: kind, detail });
  }

  markAssigned() {
    this.dirtyEdits = 0;
    this.emit('dirty', 0);
    this.emit('change', { reason: 'assigned' });
  }

  markSaved() { this.saved = true; this.emit('saved'); }

  /* ── selection ────────────────────────────────────────────────────────── */
  key(kind, id) { return `${kind}:${id}`; }

  select(items, { additive = false } = {}) {
    if (!additive) this.selection.clear();
    for (const it of [].concat(items)) {
      if (it) this.selection.add(this.key(it.kind, it.id));
    }
    this.emit('selection', this.selectionList());
  }

  toggleSelect(kind, id) {
    const k = this.key(kind, id);
    if (this.selection.has(k)) this.selection.delete(k);
    else this.selection.add(k);
    this.emit('selection', this.selectionList());
  }

  clearSelection() {
    if (!this.selection.size) return;
    this.selection.clear();
    this.emit('selection', []);
  }

  selectAll() {
    this.selection.clear();
    for (const p of this.activePipes()) this.selection.add(this.key('pipe', p.id));
    for (const l of this.activeLabels()) this.selection.add(this.key('label', l.id));
    for (const j of this.activeJoins()) this.selection.add(this.key('join', j.id));
    this.emit('selection', this.selectionList());
  }

  isSelected(kind, id) { return this.selection.has(this.key(kind, id)); }

  selectionList() {
    return [...this.selection].map(k => {
      const [kind, ...rest] = k.split(':');
      const id = rest.join(':');
      return { kind, id, obj: this.get(kind, id) };
    }).filter(s => s.obj);
  }

  setHover(h) {
    const a = this.hover ? this.key(this.hover.kind, this.hover.id) : null;
    const b = h ? this.key(h.kind, h.id) : null;
    if (a === b) return;
    this.hover = h;
    this.emit('hover', h);
  }

  /* ── mutations (each one is a single undoable step) ───────────────────── */
  recomputeStats(p) {
    p.area = +polyArea(p.polygon).toFixed(2);
  }

  addPipe(polygon, type = 'Unknown') {
    const p = {
      id: uid('P'), polygon, type, source: 'auto', origin: 'manual',
      deleted: false, area: 0, joins: [],
    };
    this.recomputeStats(p);
    this.doc.pipes.push(p);
    this.pipeById.set(p.id, p);
    this.touch('pipe:create', p.id);
    return p;
  }

  addLabel(rect, code, text) {
    const l = {
      id: uid('L'), code, rect, conf: -1, source: 'manual',
      deleted: false, block: rect.slice(),
      // everything OCR read inside the box, not just the code — a label box
      // often carries an elevation or a note alongside it
      text: text || code || '',
    };
    this.doc.labels.push(l);
    this.labelById.set(l.id, l);
    this.touch('label:create', l.id);
    return l;
  }

  /* ── detector confidence ─────────────────────────────────────────────
     The model runs at a 0.05 floor and every detection keeps its score.
     The thresholds live in the document (the server's classification
     honours them); objects below are hidden and ignored, never deleted.
     Hand-made objects carry no score and are always visible. */
  get thresholds() {
    const t = this.doc?.thresholds || {};
    return { label: t.label ?? 0.05, join: t.join ?? 0.05 };
  }

  setThreshold(key, value) {
    if (!this.doc) return;
    const v = Math.max(0.05, Math.min(1, +value || 0.05));
    this.doc.thresholds = { ...this.thresholds, [key]: v };
    this.saved = false;
    this.emit('change', { reason: 'thresholds' });
  }

  labelVisible(l) {
    return !(l.score >= 0 && l.score < this.thresholds.label - 1e-9);
  }

  joinVisible(j) {
    return !(j.conf >= 0 && j.conf < this.thresholds.join * 100 - 1e-6);
  }

  leaderVisible(e) {
    const j = e.joinId ? this.joinById.get(e.joinId) : null;
    const l = e.labelId ? this.labelById.get(e.labelId) : null;
    return (!j || this.joinVisible(j)) && (!l || this.labelVisible(l));
  }

  visibleLabels() { return this.activeLabels().filter(l => this.labelVisible(l)); }
  visibleJoins() { return this.activeJoins().filter(j => this.joinVisible(j)); }

  /** The size the detector's joining points have on this sheet, so a
   *  hand-placed one matches them (it differs by colour only: black). */
  autoJoinRadius() {
    const rs = this.activeJoins().filter(j => j.conf >= 0 && j.radius > 0)
      .map(j => j.radius).sort((a, b) => a - b);
    return rs.length ? +rs[rs.length >> 1].toFixed(2) : JOIN_RADIUS.default;
  }

  addJoin(point, code, labelId = null, radius = null) {
    if (radius === null || radius === undefined) radius = this.autoJoinRadius();
    const j = {
      id: uid('J'), point, radius, code, labelId, pipeId: null, pipeIds: [],
      // the label here is only a first guess (nearest one); leaving
      // labelSource automatic lets the resolver correct it to whichever
      // label the connection line through this point actually reaches
      anchor: null, source: 'manual', labelSource: 'auto', deleted: false,
    };
    this.doc.joins.push(j);
    this.joinById.set(j.id, j);
    this.touch('join:create', j.id);
    return j;
  }

  /** Steps 1-3 edit the segmentation itself, so `pipes` IS the base there.
   *  Classification replaces `pipes` with split stretches; going back restores
   *  the reviewed segmentation.
   *
   *  Never capture an already-classified set as the base: classification would
   *  then split the previous pieces again and stack new polygons on the old
   *  ones every time it ran. */
  syncBaseFromPipes() {
    if (this.doc.classified && this.doc.base_pipes?.length) return false;
    this.doc.base_pipes = JSON.parse(JSON.stringify(this.doc.pipes));
    return true;
  }

  get isClassified() { return !!this.doc?.classified; }

  restoreBaseSegmentation() {
    if (!this.doc.base_pipes?.length) return false;
    this.doc.pipes = JSON.parse(JSON.stringify(this.doc.base_pipes));
    this.doc.classified = false;
    this.reindex();
    this.selection.clear();
    this.emit('selection', []);
    this.emit('change', { reason: 'segmentation:restore' });
    return true;
  }

  /** The leader line a label uses to point at a pipe — annotation only, it is
   *  never merged into pipe geometry. */
  addLeader(path, { labelId = null, joinId = null, code = '', drawn = false } = {}) {
    const e = {
      id: uid('E'), labelId, joinId, path, code, drawn,
      source: 'manual', deleted: false,
    };
    this.doc.leaders.push(e);
    this.leaderById.set(e.id, e);
    this.touch('leader:create', e.id);
    return e;
  }

  leaderForJoin(joinId) {
    return this.activeLeaders().find(e => e.joinId === joinId) || null;
  }

  /** Re-point a joining point at a different label; the class follows. */
  linkJoinToLabel(joinId, labelId) {
    const j = this.joinById.get(joinId);
    const l = this.labelById.get(labelId);
    if (!j || !l) return null;
    j.labelId = labelId;
    j.code = l.code;
    // an explicit choice: the automatic resolver must not re-point it at
    // whatever label the drawing's own line happens to reach
    j.labelSource = 'manual';
    let e = this.leaderForJoin(joinId);
    const anchor = [(l.rect[0] + l.rect[2]) / 2, (l.rect[1] + l.rect[3]) / 2];
    if (e) {
      e.labelId = labelId;
      e.code = l.code;
      // re-pointing at another label leaves the drawing's own line behind, so
      // the link becomes a hint rather than a traced line
      e.path = [[anchor, j.point.slice()]];
      e.drawn = false;
    } else {
      e = this.addLeader([[anchor, j.point.slice()]],
                         { labelId, joinId, code: l.code });
    }
    j.anchor = anchor;
    this.touch('join:relink', joinId);
    return { join: j, label: l, leader: e };
  }

  /** Resize a joining point's capture radius (structural — affects assignment). */
  setJoinRadius(id, radius) {
    const j = this.joinById.get(id);
    if (!j) return;
    const r = Math.max(JOIN_RADIUS.min, Math.min(JOIN_RADIUS.max, radius));
    if (Math.abs((j.radius ?? JOIN_RADIUS.default) - r) < 1e-6) return;
    j.radius = +r.toFixed(2);
    this.touch('join:resize', id);
  }

  remove(kind, id) {
    const o = this.get(kind, id);
    if (!o || o.deleted) return;
    o.deleted = true;
    this.selection.delete(this.key(kind, id));
    this.touch(`${kind}:delete`, id);
  }

  restore(kind, id) {
    const o = this.get(kind, id);
    if (!o || !o.deleted) return;
    o.deleted = false;
    this.touch(`${kind}:restore`, id);
  }

  /** Manual class override — explicitly NOT a structural edit. */
  setPipeClass(id, type, { manual = true } = {}) {
    const p = this.pipeById.get(id);
    if (!p) return;
    p.type = type;
    p.source = manual ? 'manual' : 'auto';
    this.touch('pipe:class', id);
  }

  resetPipeClassToAuto(id) {
    const p = this.pipeById.get(id);
    if (!p) return;
    p.source = 'auto';
    this.touch('pipe:class', id);
  }

  /* ── serialisation for the API ────────────────────────────────────────── */
  toPayload() {
    return {
      stem: this.doc.stem,
      pipes: this.doc.pipes,
      labels: this.doc.labels,
      joins: this.doc.joins,
      base_pipes: this.doc.base_pipes || [],
      leaders: this.doc.leaders || [],
      classes: this.classes(),
      dirty_edits: this.dirtyEdits,
      classified: !!this.doc.classified,
      thresholds: this.thresholds,
    };
  }

  /** Deep copy of the editable collections (used by the history manager). */
  snapshot() {
    return JSON.stringify({
      pipes: this.doc.pipes, base_pipes: this.doc.base_pipes || [],
      labels: this.doc.labels, joins: this.doc.joins,
      leaders: this.doc.leaders || [], dirtyEdits: this.dirtyEdits,
      classified: !!this.doc.classified,
    });
  }

  restoreSnapshot(json) {
    const s = JSON.parse(json);
    this.doc.pipes = s.pipes;
    this.doc.labels = s.labels;
    this.doc.joins = s.joins;
    this.doc.leaders = s.leaders || [];
    this.doc.base_pipes = s.base_pipes || [];
    this.doc.classified = !!s.classified;
    this.dirtyEdits = s.dirtyEdits;
    this.reindex();
    for (const k of [...this.selection]) {
      const [kind, ...r] = k.split(':');
      if (!this.get(kind, r.join(':'))) this.selection.delete(k);
    }
    this.emit('dirty', this.dirtyEdits);
    this.emit('selection', this.selectionList());
    this.emit('change', { reason: 'history' });
  }
}
