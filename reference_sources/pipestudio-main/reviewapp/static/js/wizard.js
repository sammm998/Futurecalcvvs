// Step-by-step review workflow.
//
// The review is a five-step wizard instead of one screen showing everything:
//
//   1  Pipe segmentation   add / delete / edit pipes
//   2  Label detection     add / delete / move / edit labels
//   3  Joining points      add / delete / move joining points
//   4  Connection lines    the label -> pipe leader lines
//   5  Pipe classification runs the assignment on the reviewed inputs
//
// Each step shows only the layers it is about and enables only the tools that
// make sense there, so the user confirms one stage before the next depends on
// it.  Adding a step means adding one entry to STEPS.

import { el } from './util.js';

export const STEPS = [
  {
    id: 'pipes',
    title: 'Pipe Segmentation',
    hint: 'Review the detected pipes. Draw missing ones, delete wrong ones, ' +
          'or edit their outlines. "Merge Same Pipe" joins every run that ' +
          'was split into pieces, in one go.',
    layers: { background: true, wall: true, pipes: true,
              labels: false, joins: false, leaders: false },
    editable: ['pipes'],
    tools: ['select', 'pan', 'draw', 'vertex', 'split', 'merge'],
    defaultTool: 'select',
    counts: (s) => `${s.activePipes().length} pipes`,
    action: {
      label: 'Merge Same Pipe',
      title: 'Join every polygon that is one pipe broken into pieces. ' +
             'Crossing and side-by-side pipes are left alone.',
      run: (app) => app.autoMergeSamePipe(),
    },
  },
  {
    id: 'labels',
    title: 'Label Detection',
    hint: 'Review the detected labels. Add missing ones, move or delete ' +
          'boxes, and correct any OCR mistakes.',
    layers: { background: true, wall: true, pipes: true,
              labels: true, joins: false, leaders: false },
    editable: ['labels'],
    tools: ['select', 'pan', 'label'],
    defaultTool: 'select',
    counts: (s) => `${s.activeLabels().length} labels`,
  },
  {
    id: 'joins',
    title: 'Joining Points',
    hint: 'Review the joining points. Add, move, resize or delete them — ' +
          'each one marks where a label identifies a pipe.',
    layers: { background: true, wall: true, pipes: true,
              labels: true, joins: true, leaders: false },
    editable: ['joins'],
    tools: ['select', 'pan', 'join'],
    defaultTool: 'select',
    counts: (s) => `${s.activeJoins().length} joining points`,
  },
  {
    id: 'lines',
    title: 'Connection Lines',
    hint: 'Review the thin lines that tie each label to its pipe. Draw a ' +
          'missing one (C), or select a line and delete it.',
    layers: { background: true, wall: true, pipes: true,
              labels: true, joins: true, leaders: true },
    editable: ['leaders', 'labels', 'joins'],
    tools: ['select', 'pan', 'connect', 'join'],
    defaultTool: 'select',
    counts: (s) => `${s.activeLeaders().length} connection lines`,
  },
  {
    id: 'classify',
    title: 'Pipe Classification',
    hint: 'Classification runs on your reviewed pipes, labels, joining points ' +
          'and connection lines. Link (K): click a pipe or joining point, ' +
          'then a label, to set its class.',
    layers: { background: true, wall: true, pipes: true,
              labels: true, joins: true, leaders: true },
    editable: ['joins', 'labels', 'pipes'],
    tools: ['select', 'pan', 'join', 'link'],
    defaultTool: 'select',
    counts: (s) => {
      const p = s.activePipes();
      const typed = p.filter(x => x.type && x.type !== 'Unknown').length;
      return `${typed}/${p.length} classified`;
    },
    onEnter: (app) => app.classify(),
  },
];

export class Wizard {
  constructor(app, root) {
    this.app = app;
    this.root = root;
    this.index = 0;
    this.visited = new Set([0]);
    this.build();
    app.store.on('change', () => this.refresh());
  }

  get step() { return STEPS[this.index]; }

  build() {
    this.stepsEl = el('div', { class: 'wz-steps' });
    this.hintEl = el('div', { class: 'wz-hint' });
    this.countEl = el('div', { class: 'wz-count' });

    // optional per-step action (e.g. "Merge Same Pipe" on the segmentation
    // step) — hidden on steps that do not declare one
    this.actionBtn = el('button', {
      class: 'btn ghost hidden',
      onclick: () => this.step.action?.run(this.app),
    });

    this.backBtn = el('button', {
      class: 'btn ghost', onclick: () => this.go(this.index - 1),
      html: '<svg viewBox="0 0 24 24"><path d="m15 18-6-6 6-6"/></svg> Back',
    });
    this.nextBtn = el('button', {
      class: 'btn primary', onclick: () => this.go(this.index + 1),
    });

    this.root.append(this.stepsEl, this.hintEl, this.countEl,
                     el('div', { class: 'spacer' }),
                     this.actionBtn, this.backBtn, this.nextBtn);
    this.renderSteps();
    this.apply();
  }

  renderSteps() {
    this.stepsEl.replaceChildren();
    STEPS.forEach((s, i) => {
      if (i) this.stepsEl.append(el('div', { class: 'wz-sep' }));
      const state = i === this.index ? 'active'
                  : this.visited.has(i) ? 'done' : 'todo';
      this.stepsEl.append(el('button', {
        class: `wz-step ${state}`,
        // only steps already reached are clickable, so the order is preserved
        onclick: () => { if (this.visited.has(i)) this.go(i); },
        title: s.title,
      },
        el('span', { class: 'wz-num' }, state === 'done' ? '✓' : String(i + 1)),
        el('span', { class: 'wz-name' }, s.title)));
    });
  }

  /** Apply the current step's layers, tools and copy. */
  apply() {
    const st = this.step;
    const store = this.app.store;

    // Every step but the last works on the reviewed segmentation.  A document
    // that still holds a classified result (a reloaded session, or stepping
    // back) is put back to that segmentation, so the split pieces never become
    // the input to the next classification run.
    if (st.id !== 'classify' && store.isClassified) {
      store.restoreBaseSegmentation();
    }

    for (const [key, on] of Object.entries(st.layers)) {
      if (store.layers[key]) store.layers[key].on = on;
    }
    // Only the kinds this step edits are selectable; everything else is
    // context.  That is what makes a selection box in the Joining Points step
    // pick up joining points only — and stops a drag from moving a pipe.
    const editable = new Set(st.editable || []);
    for (const key of Object.keys(store.layers)) {
      store.layers[key].locked = !editable.has(key);
    }
    store.clearSelection();

    this.app.setAvailableTools(st.tools);
    this.app.tools.activate(st.defaultTool);

    this.hintEl.textContent = st.hint;
    this.actionBtn.classList.toggle('hidden', !st.action);
    if (st.action) {
      this.actionBtn.textContent = st.action.label;
      this.actionBtn.title = st.action.title || '';
    }
    this.backBtn.disabled = this.index === 0;
    const last = this.index === STEPS.length - 1;
    this.nextBtn.innerHTML = last
      ? 'Finish &amp; Export'
      : 'Next <svg viewBox="0 0 24 24"><path d="m9 18 6-6-6-6"/></svg>';
    this.renderSteps();
    this.refresh();
    this.app.renderer.rebuildAll();
    this.app.layersPanel?.render();
  }

  refresh() {
    if (!this.app.store.doc) return;
    this.countEl.textContent = this.step.counts(this.app.store);
  }

  async go(i) {
    if (i < 0) return;
    if (i >= STEPS.length) return this.finish();
    if (i === this.index) return;

    this.index = i;
    this.visited.add(i);
    this.apply();

    const st = this.step;
    if (st.onEnter) {
      try { await st.onEnter(this.app); }
      catch (err) { this.app.toast(`Step failed: ${err.message}`, 'error'); }
      this.refresh();
    }
    this.app.toast(`Step ${i + 1} of ${STEPS.length} — ${st.title}`);
  }

  async finish() {
    this.app.toast('Saving and exporting…');
    await this.app.save();
    await this.app.exportJSON();
    await this.app.exportPNG();
  }
}
